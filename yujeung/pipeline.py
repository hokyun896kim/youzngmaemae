"""하루 한 번 도는 전체 흐름 (GitHub Actions 에서 실행)."""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from . import db, notify
from .calendar_kr import is_business_day
from .config import Config
from .dart import DartClient, DartError, to_int
from .detect import DetectEvent, detect, purge_unlisted, summarize_fields
from .krx import KrxClient, KrxError
from .prices import collect_day, gaps_for_day
from .schedule_parser import PARSER_VERSION, Schedule, find_dates, parse_documents

SCHEDULE_LABELS = {
    "record_date": "신주배정기준일", "ex_rights_date": "권리락일(추정)", "rights_start": "인수권 상장 시작",
    "rights_end": "인수권 상장 종료", "price_fix_date": "확정발행가 산정일", "subs_start": "청약 시작",
    "subs_end": "청약 종료", "payment_date": "납입일", "listing_date": "신주 상장일",
    "issue_price": "발행가", "alloc_ratio": "배정비율",
}


# ---- 일정 저장 ----
def save_schedule(conn: sqlite3.Connection, rcept_no: str, case_id: int, s: Schedule) -> None:
    row = s.as_row()
    conn.execute(
        "INSERT OR REPLACE INTO schedule_versions (rcept_no, case_id, parsed_at, " + ", ".join(row) +
        ", extras_json, warnings_json) VALUES (" + ",".join("?" * (len(row) + 5)) + ")",
        (rcept_no, case_id, db.now(), *row.values(), db.dumps(s.extras), db.dumps(s.warnings)),
    )
    conn.commit()


def latest_schedule(conn: sqlite3.Connection, case_id: int, exclude: str | None = None) -> dict:
    """케이스의 최신 일정 = 공시 순서대로 값이 있는 필드를 덮어쓴 결과."""
    merged: dict = {}
    for r in conn.execute(
        "SELECT * FROM schedule_versions WHERE case_id=? AND rcept_no != ? ORDER BY rcept_no",
        (case_id, exclude or ""),
    ):
        for k in SCHEDULE_LABELS:
            if r[k] is not None:
                merged[k] = r[k]
    return merged


def _fmt(v) -> str:
    if v is None:
        return "없음"
    return f"{v:,}" if isinstance(v, int) else str(v)


def schedule_diff(before: dict, after: dict) -> list[str]:
    return [f"{SCHEDULE_LABELS[k]}: {_fmt(before.get(k))} → {_fmt(after.get(k))}"
            for k in SCHEDULE_LABELS if after.get(k) is not None and before.get(k) != after.get(k)]


def estk_schedule(general: dict, types: list[dict]) -> Schedule:
    """증권신고서(지분증권) API 필드 → Schedule. 청약기일은 '시작 ~ 종료' 문자열일 수 있다."""
    s = Schedule()
    ds = find_dates(general.get("asstd") or "")
    s.record_date = ds[0] if ds else None
    ds = find_dates(general.get("sbd") or "")
    s.subs_start, s.subs_end = (ds[0], ds[-1]) if ds else (None, None)
    ds = find_dates(general.get("pymd") or "")
    s.payment_date = ds[0] if ds else None
    prices = [to_int(t.get("slprc")) for t in types if "보통" in (t.get("stksen") or "")]
    s.issue_price = next((p for p in prices if p), None)
    s.extras = {"source": "estkRs", "general": general}
    return s


# ---- 단계들 ----
def step_detect(dart: DartClient, conn, cfg: Config, today: date, lookback_days: int) -> list[DetectEvent]:
    purge_unlisted(conn)
    # 초기 버전이 보낸 비주주배정 '신규 유증' 알림 정리 (알림은 주주배정 건만)
    conn.execute(
        "DELETE FROM notifications WHERE dedup_key IN (SELECT 'new:' || d.rcept_no FROM disclosures d "
        "JOIN cases c USING (case_id) WHERE c.is_rights=0)")
    conn.commit()
    bgn = (today - timedelta(days=lookback_days)).strftime("%Y%m%d")
    events = detect(dart, conn, bgn, today.strftime("%Y%m%d"))
    for ev in events:
        # 브리프 파이프라인 1단계: 주주배정 계열만 알림. 나머지는 사이트 '관찰' 탭에만 기록
        if ev.kind != "new_case" or not ev.is_rights:
            continue
        sm = summarize_fields(ev.fields)
        purpose = ", ".join(f"{k} {v}%" for k, v in sm["purpose_pct"].items()) or "-"
        amount = f"{sm['total_amount'] / 1e8:,.0f}억" if sm["total_amount"] else "-"
        dilution = f"{sm['dilution_ratio'] * 100:.0f}%" if sm["dilution_ratio"] else "-"
        tag = "주주배정 ✅ 인수권 발생"
        if ev.report_nm.strip().startswith("["):
            tag += " (정정 공시로 처음 감지 — 원공시는 수집 이전)"
        notify.send(conn, cfg, f"신규 유증 {ev.corp_name}",
                    f"{tag}\n증자방식: {ev.fields.get('ic_mthn', '-')}\n규모: {amount} / 신주÷기존주 {dilution}\n"
                    f"자금목적: {purpose}\nhttps://dart.fss.or.kr/dsaf001/main.do?rcpNo={ev.rcept_no}",
                    dedup_key=f"new:{ev.rcept_no}")
    return events


def step_schedules(dart: DartClient, conn, cfg: Config) -> None:
    """일정 파싱 안 된 주주배정 공시 → 원문 파싱. 정정으로 일정이 바뀌면 알림.
    파서 버전이 올라가면 기존 공시도 재파싱한다 (재파싱은 알림 없음)."""
    pending = conn.execute(
        "SELECT d.rcept_no, d.case_id, c.corp_name, s.rcept_no IS NOT NULL AS reparse "
        "FROM disclosures d JOIN cases c USING (case_id) "
        "LEFT JOIN schedule_versions s ON s.rcept_no=d.rcept_no "
        "WHERE c.is_rights=1 AND d.kind='piic' AND (s.rcept_no IS NULL "
        "OR IFNULL(json_extract(s.extras_json, '$.parser'), 1) < ?) ORDER BY d.rcept_no",
        (PARSER_VERSION,),
    ).fetchall()
    for r in pending:
        try:
            sch = parse_documents(dart.document(r["rcept_no"]))
        except DartError as e:
            sch = Schedule(warnings=[f"원문 조회 실패: {e}"])
            sch.extras = {"parser": PARSER_VERSION}
        before = latest_schedule(conn, r["case_id"], exclude=r["rcept_no"])
        save_schedule(conn, r["rcept_no"], r["case_id"], sch)
        if r["reparse"]:
            continue
        changes = schedule_diff(before, latest_schedule(conn, r["case_id"]))
        if before and changes:
            notify.send(conn, cfg, f"일정 변경 {r['corp_name']}", "\n".join(changes), dedup_key=f"chg:{r['rcept_no']}")


def step_estk(dart: DartClient, conn, cfg: Config, today: date) -> None:
    """진행 중 주주배정 케이스의 증권신고서(지분증권) 요약 → 일정 보강."""
    cases = conn.execute("SELECT * FROM cases WHERE status='open' AND is_rights=1").fetchall()
    for c in cases:
        try:
            groups = dart.equity_registrations(c["corp_code"], c["first_rcept_dt"], today.strftime("%Y%m%d"))
        except DartError:
            continue
        types = groups.get("증권의종류", [])
        for g in groups.get("일반사항", []):
            rcept_no = g.get("rcept_no")
            if not rcept_no or conn.execute("SELECT 1 FROM disclosures WHERE rcept_no=?", (rcept_no,)).fetchone():
                continue
            conn.execute(
                "INSERT INTO disclosures (rcept_no, case_id, kind, report_nm, rcept_dt, is_correction, fields_json)"
                " VALUES (?,?,?,?,?,?,?)",
                (rcept_no, c["case_id"], "estk", "증권신고서(지분증권)", rcept_no[:8], 0, db.dumps(g)),
            )
            before = latest_schedule(conn, c["case_id"])
            save_schedule(conn, rcept_no, c["case_id"],
                          estk_schedule(g, [t for t in types if t.get("rcept_no") == rcept_no]))
            changes = schedule_diff(before, latest_schedule(conn, c["case_id"]))
            if before and changes:
                notify.send(conn, cfg, f"일정 변경 {c['corp_name']}", "증권신고서 기준\n" + "\n".join(changes),
                            dedup_key=f"chg:{rcept_no}")


def recent_business_days(today: date, n: int) -> list[date]:
    out, d = [], today
    while len(out) < n:
        if is_business_day(d):
            out.append(d)
        d -= timedelta(days=1)
    return sorted(out)


def step_prices(krx: KrxClient, conn, cfg: Config, today: date, days: int) -> list[dict]:
    """최근 n 영업일 재수집 (KRX 갱신 시각과 무관하게 빠진 날을 메운다)."""
    results = []
    for d in recent_business_days(today, days):
        try:
            results.append(collect_day(krx, conn, d.strftime("%Y%m%d")))
        except KrxError as e:
            results.append({"bas_dd": d.strftime("%Y%m%d"), "error": str(e)})
    return results


def step_gap_alerts(conn, cfg: Config) -> None:
    last = conn.execute("SELECT MAX(bas_dd) FROM rights_daily").fetchone()[0]
    if not last:
        return
    for g in gaps_for_day(conn, last):
        if abs(g.gap_pct) >= cfg.gap_alert_pct:
            side = "인수권 저평가 → 인수권 매수+청약 검토" if g.gap_pct < 0 else "인수권 고평가 → 인수권 매도 검토"
            notify.send(conn, cfg, f"인수권 괴리 {g.isu_nm}",
                        f"{g.bas_dd} 종가 기준\n인수권 {g.rights_close:,} / 이론가 {g.fair:,} "
                        f"(본주 {g.stock_close:,} − 발행가 {g.issue_price:,})\n괴리율 {g.gap_pct:+.1f}% · {side}\n"
                        f"인수권+청약 신주원가 {g.effective_cost:,}",
                        dedup_key=f"gap:{g.isu_nm}:{g.bas_dd}")


def step_reminders(conn, cfg: Config, today: date) -> None:
    """권리락 D-1, 신주 상장 D-1 / D0 / D+5."""
    for c in conn.execute("SELECT * FROM cases WHERE status='open' AND is_rights=1").fetchall():
        sch = latest_schedule(conn, c["case_id"])
        checks = []
        if sch.get("ex_rights_date"):
            checks.append(("권리락 D-1", date.fromisoformat(sch["ex_rights_date"]) - timedelta(days=1)))
        if sch.get("listing_date"):
            ld = date.fromisoformat(sch["listing_date"])
            checks += [("신주상장 D-1", ld - timedelta(days=1)), ("신주상장 D0", ld), ("신주상장 D+5", ld + timedelta(days=5))]
        for label, when in checks:
            if when == today:
                notify.send(conn, cfg, f"{label} {c['corp_name']}",
                            "\n".join(f"{SCHEDULE_LABELS[k]}: {v}" for k, v in sch.items()),
                            dedup_key=f"rem:{c['case_id']}:{label}")
        if sch.get("listing_date") and date.fromisoformat(sch["listing_date"]) + timedelta(days=45) < today:
            conn.execute("UPDATE cases SET status='closed' WHERE case_id=?", (c["case_id"],))
    conn.commit()


def run_daily(cfg: Config, conn, today: date, lookback_days: int = 7, price_days: int = 5,
              dart: DartClient | None = None, krx: KrxClient | None = None) -> dict:
    report: dict = {"today": today.isoformat()}
    if dart or cfg.dart_api_key:
        dart = dart or DartClient(cfg.dart_api_key, conn)
        report["detected"] = [e.rcept_no for e in step_detect(dart, conn, cfg, today, lookback_days)]
        step_schedules(dart, conn, cfg)
        step_estk(dart, conn, cfg, today)
    else:
        report["dart"] = "DART_API_KEY 없음 — 건너뜀"
    if krx or cfg.krx_api_key:
        krx = krx or KrxClient(cfg.krx_api_key, conn)
        report["prices"] = step_prices(krx, conn, cfg, today, price_days)
        step_gap_alerts(conn, cfg)
    else:
        report["krx"] = "KRX_API_KEY 없음 — 건너뜀"
    step_reminders(conn, cfg, today)
    return report
