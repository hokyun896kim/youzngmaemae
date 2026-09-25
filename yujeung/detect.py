"""유상증자결정 공시 감지 → 케이스/공시 테이블 적재."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from . import db
from .dart import DartClient, to_int

PIIC_KEYWORD = "유상증자결정"          # "주요사항보고서(유상증자결정)", "[기재정정]주요사항보고서(유상증자결정)"
ESTK_KEYWORD = "증권신고서(지분증권)"


def is_piic_report(report_nm: str) -> bool:
    # "유무상증자결정" 은 별도 API(pifricDecsn)라 여기선 제외 — 부분문자열로도 안 걸린다
    return PIIC_KEYWORD in report_nm.replace(" ", "")


def is_correction(report_nm: str) -> bool:
    return report_nm.strip().startswith("[")


def is_rights_offering(ic_mthn: str | None) -> bool:
    """신주인수권증서가 나오는 방식 = 주주배정 계열(주주배정증자, 주주배정후 실권주 일반공모)."""
    return bool(ic_mthn) and "주주배정" in ic_mthn.replace(" ", "")


@dataclass
class DetectEvent:
    kind: str                 # new_case / correction
    case_id: int
    rcept_no: str
    corp_name: str
    stock_code: str | None
    report_nm: str
    is_rights: bool
    fields: dict = field(default_factory=dict)


def _shift(yyyymmdd: str, days: int) -> str:
    return (datetime.strptime(yyyymmdd, "%Y%m%d") + timedelta(days=days)).strftime("%Y%m%d")


def _find_piic_fields(client: DartClient, corp_code: str, rcept_no: str, rcept_dt: str) -> dict:
    # piicDecsn 의 기간은 "최초접수일" 기준 → 정정 공시는 원공시 날짜로 잡힌다. 넉넉히 1년 전부터.
    items = client.piic_decisions(corp_code, _shift(rcept_dt, -365), rcept_dt)
    for it in items:
        if it.get("rcept_no") == rcept_no:
            return it
    return max(items, key=lambda it: it.get("rcept_no", ""), default={})


def _open_case_for(conn: sqlite3.Connection, corp_code: str, rcept_dt: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM cases WHERE corp_code=? AND status='open' AND first_rcept_dt>=? "
        "ORDER BY first_rcept_dt DESC LIMIT 1",
        (corp_code, _shift(rcept_dt, -240)),
    ).fetchone()


def upsert_disclosure(conn, rep: dict, fields: dict) -> DetectEvent | None:
    """공시 1건을 적재. 이미 있으면 None."""
    rcept_no = rep["rcept_no"]
    if conn.execute("SELECT 1 FROM disclosures WHERE rcept_no=?", (rcept_no,)).fetchone():
        return None

    ic_mthn = fields.get("ic_mthn") or None
    correction = is_correction(rep["report_nm"])
    case = _open_case_for(conn, rep["corp_code"], rep["rcept_dt"]) if correction else None

    if case is None:
        cur = conn.execute(
            "INSERT INTO cases (corp_code, corp_name, stock_code, corp_cls, first_rcept_no, first_rcept_dt,"
            " ic_mthn, is_rights, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (rep["corp_code"], rep["corp_name"], rep.get("stock_code") or None, rep.get("corp_cls"),
             rcept_no, rep["rcept_dt"], ic_mthn, int(is_rights_offering(ic_mthn)), db.now()),
        )
        case_id, kind, is_rights = cur.lastrowid, "new_case", is_rights_offering(ic_mthn)
    else:
        case_id, kind = case["case_id"], "correction"
        if ic_mthn and ic_mthn != case["ic_mthn"]:
            conn.execute("UPDATE cases SET ic_mthn=?, is_rights=? WHERE case_id=?",
                         (ic_mthn, int(is_rights_offering(ic_mthn)), case_id))
        is_rights = is_rights_offering(ic_mthn or case["ic_mthn"])

    conn.execute(
        "INSERT INTO disclosures (rcept_no, case_id, kind, report_nm, rcept_dt, is_correction, fields_json)"
        " VALUES (?,?,?,?,?,?,?)",
        (rcept_no, case_id, "piic", rep["report_nm"], rep["rcept_dt"], int(correction), db.dumps(fields)),
    )
    conn.commit()
    return DetectEvent(kind, case_id, rcept_no, rep["corp_name"], rep.get("stock_code"),
                       rep["report_nm"], is_rights, fields)


def detect(client: DartClient, conn: sqlite3.Connection, bgn_de: str, end_de: str) -> list[DetectEvent]:
    reports = [r for r in client.search(bgn_de, end_de, pblntf_ty="B") if is_piic_report(r.get("report_nm", ""))]
    reports.sort(key=lambda r: r["rcept_no"])   # 원공시 → 정정 순서 보장
    events = []
    for rep in reports:
        if conn.execute("SELECT 1 FROM disclosures WHERE rcept_no=?", (rep["rcept_no"],)).fetchone():
            continue
        fields = _find_piic_fields(client, rep["corp_code"], rep["rcept_no"], rep["rcept_dt"])
        ev = upsert_disclosure(conn, rep, fields)
        if ev:
            events.append(ev)
    return events


def summarize_fields(fields: dict) -> dict:
    """알림/점수화용 숫자 요약 (자금목적 비중, 증자비율)."""
    purposes = {
        "시설": to_int(fields.get("fdpp_fclt")),
        "영업양수": to_int(fields.get("fdpp_bsninh")),
        "운영": to_int(fields.get("fdpp_op")),
        "채무상환": to_int(fields.get("fdpp_dtrp")),
        "타법인취득": to_int(fields.get("fdpp_ocsa")),
        "기타": to_int(fields.get("fdpp_etc")),
    }
    total = sum(v for v in purposes.values() if v)
    new_shares = (to_int(fields.get("nstk_ostk_cnt")) or 0) + (to_int(fields.get("nstk_estk_cnt")) or 0)
    old_shares = (to_int(fields.get("bfic_tisstk_ostk")) or 0) + (to_int(fields.get("bfic_tisstk_estk")) or 0)
    return {
        "total_amount": total,
        "purpose_pct": {k: round(v / total * 100, 1) for k, v in purposes.items() if v and total},
        "new_shares": new_shares,
        "dilution_ratio": round(new_shares / old_shares, 4) if old_shares else None,
    }
