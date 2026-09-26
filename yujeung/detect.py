"""유상증자결정 공시 감지 → 케이스/공시 테이블 적재."""
from __future__ import annotations

import json
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


LISTED = ("Y", "K")   # 코스피 / 코스닥만. 코넥스(N)·기타법인(E)은 제외
SAME_DEAL_DAYS = 60   # 정정 표시 없이 다시 낸 원공시를 같은 건으로 보는 기간


def is_listed(rep: dict, listed: tuple = LISTED) -> bool:
    return rep.get("corp_cls") in listed and bool((rep.get("stock_code") or "").strip())


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


def _find_piic_fields(client: DartClient, corp_code: str, rcept_no: str, rcept_dt: str,
                     cache: dict | None = None) -> dict:
    # piicDecsn 의 기간은 "최초접수일" 기준 → 정정 공시는 원공시 날짜로 잡힌다. 넉넉히 1년 전부터.
    # 같은 회사 공시가 여러 건이면 한 번만 조회 (cache: corp_code → items)
    if cache is not None and corp_code in cache:
        items = cache[corp_code]
    else:
        items = client.piic_decisions(corp_code, _shift(rcept_dt, -365), _shift(rcept_dt, 30))
        if cache is not None:
            cache[corp_code] = items
    for it in items:
        if it.get("rcept_no") == rcept_no:
            return it
    return max(items, key=lambda it: it.get("rcept_no", ""), default={})


def exclude(conn: sqlite3.Connection, rcept_no: str, corp_code: str | None, corp_name: str | None,
            reason: str, stock_code: str | None = None) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO excluded_disclosures (rcept_no, corp_code, corp_name, stock_code, reason, created_at)"
        " VALUES (?,?,?,?,?,?)", (rcept_no, corp_code, corp_name, stock_code, reason, db.now()))


def is_known(conn: sqlite3.Connection, rcept_no: str) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM disclosures WHERE rcept_no=? UNION SELECT 1 FROM excluded_disclosures WHERE rcept_no=?",
        (rcept_no, rcept_no)).fetchone())


def _nstk(fields: dict) -> int | None:
    return to_int(fields.get("nstk_ostk_cnt"))


def _case_share_counts(conn: sqlite3.Connection, case_id: int) -> set[int]:
    out = set()
    for r in conn.execute("SELECT fields_json FROM disclosures WHERE case_id=? AND kind='piic'", (case_id,)):
        n = _nstk(json.loads(r[0] or "{}"))
        if n:
            out.add(n)
    return out


def _same_deal_case(conn: sqlite3.Connection, rep: dict, fields: dict) -> sqlite3.Row | None:
    """정정 표시 없이 다시 제출한 원공시(예: 셀리드 9/21·9/22) → 같은 회사·같은 증자방식·같은 신주수면 같은 건."""
    n = _nstk(fields)
    if not n:
        return None
    for case in conn.execute(
        "SELECT * FROM cases WHERE corp_code=? AND status='open' AND IFNULL(ic_mthn,'')=? AND first_rcept_dt>=? "
        "ORDER BY first_rcept_dt DESC", (rep["corp_code"], fields.get("ic_mthn") or "", _shift(rep["rcept_dt"], -SAME_DEAL_DAYS))
    ).fetchall():
        if n in _case_share_counts(conn, case["case_id"]):
            return case
    return None


def _open_case_for(conn: sqlite3.Connection, corp_code: str, rcept_dt: str) -> sqlite3.Row | None:
    """정정공시가 붙을 케이스: 같은 회사, 240일 안에 '먼저' 시작한 진행 중 케이스 중 가장 최근 것.
    정정이 자기보다 늦게 시작한 케이스에 붙으면 안 된다 (실측 이렘: 3/31 정정이 9/23 에 시작한 케이스에 붙음)."""
    return conn.execute(
        "SELECT * FROM cases WHERE corp_code=? AND status='open' AND first_rcept_dt>=? AND first_rcept_dt<=? "
        "ORDER BY first_rcept_dt DESC LIMIT 1",
        (corp_code, _shift(rcept_dt, -240), rcept_dt),
    ).fetchone()


def upsert_disclosure(conn, rep: dict, fields: dict, rights_only: bool = False) -> DetectEvent | None:
    """공시 1건을 적재. 이미 알거나(적재·제외) 제외 대상이면 None."""
    rcept_no = rep["rcept_no"]
    if is_known(conn, rcept_no):
        return None

    ic_mthn = fields.get("ic_mthn") or None
    correction = is_correction(rep["report_nm"])
    case = (_open_case_for(conn, rep["corp_code"], rep["rcept_dt"]) if correction
            else _same_deal_case(conn, rep, fields))

    if case is None:
        # 새 케이스인데 증자방식·금액이 비어 있으면 판단 재료가 없다 → 제외
        if not ic_mthn or not summarize_fields(fields)["total_amount"]:
            exclude(conn, rcept_no, rep["corp_code"], rep["corp_name"], "증자방식·금액 없음", rep.get("stock_code"))
            conn.commit()
            return None
        # 백필: 관찰용(비주주배정)은 과거분을 들이지 않는다 — 일일 수집분만 관찰 탭에
        if rights_only and not is_rights_offering(ic_mthn):
            exclude(conn, rcept_no, rep["corp_code"], rep["corp_name"], f"백필 제외(비주주배정: {ic_mthn})",
                    rep.get("stock_code"))
            conn.commit()
            return None
        cur = conn.execute(
            "INSERT INTO cases (corp_code, corp_name, stock_code, corp_cls, first_rcept_no, first_rcept_dt,"
            " ic_mthn, is_rights, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (rep["corp_code"], rep["corp_name"], rep.get("stock_code") or None, rep.get("corp_cls"),
             rcept_no, rep["rcept_dt"], ic_mthn, int(is_rights_offering(ic_mthn)), db.now()),
        )
        case_id, kind, is_rights = cur.lastrowid, "new_case", is_rights_offering(ic_mthn)
    else:
        case_id, kind = case["case_id"], "correction" if correction else "duplicate"
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


def detect(client: DartClient, conn: sqlite3.Connection, bgn_de: str, end_de: str,
           windows: list[tuple[str, str]] | None = None, rights_only: bool = False,
           listed: tuple = LISTED, keep=None) -> list[DetectEvent]:
    """windows 가 있으면 여러 구간(월 단위)을 모두 모은 뒤 처리 — 구간 순서와 무관하게 원공시 → 정정 순.
    listed: 받을 법인구분. 백테스트는 상장폐지 회사(현재 'E')도 넣어 생존편향을 줄인다.
    keep(conn, rep): False 면 상세 조회(piicDecsn)·적재 없이 건너뜀 — 백테스트 꼬리 기간용."""
    seen, reports = set(), []
    for bgn, end in windows or [(bgn_de, end_de)]:
        for r in client.search(bgn, end, pblntf_ty="B"):
            if r["rcept_no"] not in seen and is_piic_report(r.get("report_nm", "")) and is_listed(r, listed):
                seen.add(r["rcept_no"])
                reports.append(r)
    reports.sort(key=lambda r: r["rcept_no"])   # 원공시 → 정정 순서 보장
    events, cache = [], {}
    todo = [r for r in reports if not is_known(conn, r["rcept_no"])]
    print(f"[detect] 유상증자결정 {len(reports)}건 중 신규 {len(todo)}건", flush=True)
    skipped = 0
    for i, rep in enumerate(todo, 1):
        if i % 100 == 0:
            print(f"[detect] {i}/{len(todo)}", flush=True)
        if keep is not None and not keep(conn, rep):
            skipped += 1
            continue
        fields = _find_piic_fields(client, rep["corp_code"], rep["rcept_no"], rep["rcept_dt"], cache)
        ev = upsert_disclosure(conn, rep, fields, rights_only)
        if ev:
            events.append(ev)
    if skipped:
        print(f"[detect] 상세 조회 생략 {skipped}건", flush=True)
    return events


def drop_case(conn: sqlite3.Connection, case_id: int, reason: str) -> None:
    """케이스를 지우고 그 공시들을 제외 목록에 남긴다 (다음 실행 때 다시 받지 않음)."""
    case = conn.execute("SELECT * FROM cases WHERE case_id=?", (case_id,)).fetchone()
    if not case:
        return
    for (rn,) in conn.execute("SELECT rcept_no FROM disclosures WHERE case_id=?", (case_id,)).fetchall():
        exclude(conn, rn, case["corp_code"], case["corp_name"], reason, case["stock_code"])
        conn.execute("DELETE FROM notifications WHERE dedup_key IN (?, ?)", (f"new:{rn}", f"chg:{rn}"))
    for t in ("schedule_versions", "disclosures", "case_facts", "paper_trades"):
        conn.execute(f"DELETE FROM {t} WHERE case_id=?", (case_id,))
    conn.execute("UPDATE rights_daily SET case_id=NULL WHERE case_id=?", (case_id,))
    conn.execute("DELETE FROM cases WHERE case_id=?", (case_id,))


def purge_unlisted(conn: sqlite3.Connection) -> int:
    """코스피·코스닥이 아닌 케이스(비상장·코넥스)를 정리. 멱등."""
    ids = [r[0] for r in conn.execute(
        "SELECT case_id FROM cases WHERE IFNULL(stock_code,'')='' OR corp_cls NOT IN ('Y','K')")]
    for cid in ids:
        drop_case(conn, cid, "코스피·코스닥 아님")
    conn.commit()
    return len(ids)


def merge_duplicate_cases(conn: sqlite3.Connection) -> int:
    """이미 따로 잡힌 같은 건(같은 회사·증자방식·신주수, 60일 이내)을 먼저 잡힌 케이스로 합친다."""
    merged = 0
    cases = conn.execute("SELECT * FROM cases ORDER BY corp_code, first_rcept_dt, case_id").fetchall()
    for i, a in enumerate(cases):
        for b in cases[i + 1:]:
            if b["corp_code"] != a["corp_code"]:
                break
            if (a["ic_mthn"] or "") != (b["ic_mthn"] or "") or b["first_rcept_dt"] > _shift(a["first_rcept_dt"], SAME_DEAL_DAYS):
                continue
            if not conn.execute("SELECT 1 FROM cases WHERE case_id=?", (a["case_id"],)).fetchone():
                continue
            if _case_share_counts(conn, a["case_id"]) & _case_share_counts(conn, b["case_id"]):
                for t in ("disclosures", "schedule_versions", "rights_daily"):
                    conn.execute(f"UPDATE {t} SET case_id=? WHERE case_id=?", (a["case_id"], b["case_id"]))
                for t in ("case_facts", "paper_trades"):
                    conn.execute(f"DELETE FROM {t} WHERE case_id=?", (b["case_id"],))
                conn.execute("DELETE FROM cases WHERE case_id=?", (b["case_id"],))
                merged += 1
    conn.commit()
    return merged


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
