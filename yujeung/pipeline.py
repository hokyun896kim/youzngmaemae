"""하루 한 번 도는 전체 흐름 (GitHub Actions 에서 실행)."""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import json

from . import db, notify, paper
from .calendar_kr import is_business_day, prev_business_day
from .config import Config
from .dart import DartClient, DartError, to_int
from .detect import (DetectEvent, detect, drop_case, merge_duplicate_cases, purge_unlisted,
                     summarize_fields)
from .krx import KrxClient, KrxError
from .naver import INDEX_SYMBOL, NaverClient, NaverError
from .prices import collect_day, compute_gap, gaps_for_day, relink_rights
from .schedule_parser import (PARSER_VERSION, Schedule, clean, extract_discount, find_dates, issue_kind,
                              parse_documents, validate_schedule)
from .verdict import decide, gate1, reason_line

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


_DATE_FIELDS = ("record_date", "rights_start", "subs_start", "payment_date", "listing_date")


def latest_schedule(conn: sqlite3.Connection, case_id: int, exclude: str | None = None) -> dict:
    """케이스의 최신 일정.
    정정공시가 뜨면 옛 일정은 통째로 버린다: 가장 최근 유상증자결정 원문(날짜가 하나라도 잡힌 것) 하나가 기준이고,
    그보다 뒤에 나온 증권신고서 값만 위에 덮는다. (옛 공시 값이 빈칸을 메우지 않게)"""
    rows = conn.execute(
        "SELECT s.*, IFNULL(d.kind, 'piic') AS kind FROM schedule_versions s "
        "LEFT JOIN disclosures d USING (rcept_no) WHERE s.case_id=? AND s.rcept_no != ? ORDER BY s.rcept_no",
        (case_id, exclude or "")).fetchall()
    piic = [r for r in rows if r["kind"] == "piic" and any(r[k] for k in _DATE_FIELDS)]
    base = piic[-1] if piic else next((r for r in reversed(rows) if r["kind"] == "piic"), None)
    merged: dict = {k: base[k] for k in SCHEDULE_LABELS if base[k] is not None} if base else {}
    price_row = base if base is not None and base["issue_price"] is not None else None
    for r in rows:
        if r["kind"] == "piic" or (base is not None and r["rcept_no"] < base["rcept_no"]):
            continue
        for k in SCHEDULE_LABELS:
            if r[k] is not None:
                merged[k] = r[k]
        if r["issue_price"] is not None:
            price_row = r
    if merged.get("record_date"):
        from .calendar_kr import ex_rights_date
        merged["ex_rights_date"] = ex_rights_date(merged["record_date"])
    if price_row is not None:
        # 발행가 구분: 라벨(확정발행가/1차/예정발행가) 우선, 없으면 그 값을 낸 공시의 날짜로
        label_kind = json.loads(price_row["extras_json"] or "{}").get("issue_label_kind")
        merged["issue_kind"] = issue_kind(label_kind, price_row["rcept_no"][:8], merged)
        merged["issue_rcept_dt"] = price_row["rcept_no"][:8]
    return merged


def latest_facts(conn: sqlite3.Connection, case_id: int) -> dict:
    """원문·증권신고서에서 뽑은 판정 재료(최대주주 청약, 인수방식) — 최신 공시 우선."""
    facts: dict = {}
    for r in conn.execute("SELECT extras_json FROM schedule_versions WHERE case_id=? ORDER BY rcept_no", (case_id,)):
        f = json.loads(r[0] or "{}").get("facts") or {}
        for k, v in f.items():
            if v:
                facts[k] = v
    return facts


def checked_schedule(conn: sqlite3.Connection, case_id: int) -> tuple[dict, list[str]]:
    """합친 일정 + 논리 검사(인수권 기간 = 청약일이면 비움, 청약 5거래일 전 규칙)."""
    return validate_schedule(latest_schedule(conn, case_id))


def _fmt(v) -> str:
    if v is None:
        return "없음"
    return f"{v:,}" if isinstance(v, int) else str(v)


def schedule_diff(before: dict, after: dict) -> list[str]:
    return [f"{SCHEDULE_LABELS[k]}: {_fmt(before.get(k))} → {_fmt(after.get(k))}"
            for k in SCHEDULE_LABELS if after.get(k) is not None and before.get(k) != after.get(k)]


def estk_schedule(general: dict, types: list[dict], underwriters: list[dict] | None = None) -> Schedule:
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
    uw = next((u.get("udtmth") for u in (underwriters or []) if u.get("udtmth")), None)
    facts = {}
    for k in ("잔액인수", "총액인수", "모집주선"):
        if uw and k in uw.replace(" ", ""):
            facts["underwriting"] = k
            break
    s.extras = {"source": "estkRs", "general": general, "facts": facts}
    return s


# ---- 단계들 ----
def step_housekeeping(conn) -> None:
    purge_unlisted(conn)
    merge_duplicate_cases(conn)
    # 초기 버전이 남긴 비주주배정 '신규 유증' 알림 정리 (알림은 주주배정 건만)
    conn.execute(
        "DELETE FROM notifications WHERE dedup_key IN (SELECT 'new:' || d.rcept_no FROM disclosures d "
        "JOIN cases c USING (case_id) WHERE c.is_rights=0)")
    conn.commit()


def step_detect(dart: DartClient, conn, today: date, bgn: date, alerts: bool = True,
                windows: list[tuple[date, date]] | None = None) -> list[DetectEvent]:
    fmt = "%Y%m%d"
    events = detect(dart, conn, bgn.strftime(fmt), today.strftime(fmt),
                    [(a.strftime(fmt), b.strftime(fmt)) for a, b in windows] if windows else None,
                    rights_only=bool(windows))
    for ev in events:
        # 브리프 파이프라인 1단계: 주주배정 계열만 알림 문구. 나머지는 사이트 '관찰' 탭에만 기록
        if not alerts or ev.kind != "new_case" or not ev.is_rights:
            continue
        sm = summarize_fields(ev.fields)
        purpose = ", ".join(f"{k} {v}%" for k, v in sm["purpose_pct"].items()) or "-"
        amount = f"{sm['total_amount'] / 1e8:,.0f}억" if sm["total_amount"] else "-"
        dilution = f"{sm['dilution_ratio'] * 100:.0f}%" if sm["dilution_ratio"] else "-"
        tag = "주주배정 ✅ 인수권 발생"
        if ev.report_nm.strip().startswith("["):
            tag += " (정정 공시로 처음 감지 — 원공시는 수집 이전)"
        notify.record(conn, f"신규 유증 {ev.corp_name}",
                      f"{tag}\n증자방식: {ev.fields.get('ic_mthn', '-')}\n규모: {amount} / 신주÷기존주 {dilution}\n"
                      f"자금목적: {purpose}\nhttps://dart.fss.or.kr/dsaf001/main.do?rcpNo={ev.rcept_no}",
                      dedup_key=f"new:{ev.rcept_no}")
    return events


def step_schedules(dart: DartClient, conn, alerts: bool = True) -> None:
    """일정 파싱 안 된 공시(주주배정·관찰 모두) → 원문 파싱. 정정으로 주주배정 일정이 바뀌면 알림 문구.
    파서 버전이 올라가면 기존 공시도 재파싱한다 (재파싱은 알림 없음)."""
    pending = conn.execute(
        "SELECT d.rcept_no, d.case_id, c.corp_name, c.is_rights, s.rcept_no IS NOT NULL AS reparse "
        "FROM disclosures d JOIN cases c USING (case_id) "
        "LEFT JOIN schedule_versions s ON s.rcept_no=d.rcept_no "
        "WHERE d.kind='piic' AND (s.rcept_no IS NULL "
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
        if r["reparse"] or not alerts or not r["is_rights"]:
            continue
        changes = schedule_diff(before, latest_schedule(conn, r["case_id"]))
        if before and changes:
            notify.record(conn, f"일정 변경 {r['corp_name']}", "\n".join(changes), dedup_key=f"chg:{r['rcept_no']}")


def step_estk(dart: DartClient, conn, today: date, alerts: bool = True, discount: bool = True,
              window_days: int | None = None) -> None:
    """진행 중 주주배정 케이스의 증권신고서(지분증권) 요약 → 일정·인수방식 보강.
    window_days: 조회 끝을 '최초 공시 + N일'로 자른다 (백테스트 — 같은 회사의 몇 년 뒤 다른 유증이 섞이지 않게)."""
    cases = conn.execute("SELECT * FROM cases WHERE status='open' AND is_rights=1").fetchall()
    for c in cases:
        end = today
        if window_days:
            first = date(int(c["first_rcept_dt"][:4]), int(c["first_rcept_dt"][4:6]), int(c["first_rcept_dt"][6:]))
            end = min(today, first + timedelta(days=window_days))
        try:
            groups = dart.equity_registrations(c["corp_code"], c["first_rcept_dt"], end.strftime("%Y%m%d"))
        except DartError:
            continue
        types = groups.get("증권의종류", [])
        uws = groups.get("인수인정보", [])
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
            sch = estk_schedule(g, [t for t in types if t.get("rcept_no") == rcept_no],
                                [u for u in uws if u.get("rcept_no") == rcept_no])
            # 발행가 산식의 할인율은 증권신고서 본문에 있다 (어림 손익표의 발행가 추정용)
            try:
                d = next((v for v in (extract_discount(clean(b)) for b in dart.document(rcept_no).values()) if v),
                         None) if discount else None
            except DartError:
                d = None
            if d:
                sch.extras["facts"]["discount"] = d
            sch.extras["discount_checked"] = discount
            save_schedule(conn, rcept_no, c["case_id"], sch)
            changes = schedule_diff(before, latest_schedule(conn, c["case_id"]))
            if alerts and before and changes:
                notify.record(conn, f"일정 변경 {c['corp_name']}", "증권신고서 기준\n" + "\n".join(changes),
                              dedup_key=f"chg:{rcept_no}")
    if discount:
        recheck_estk_discount(dart, conn)


def recheck_estk_discount(dart: DartClient, conn) -> int:
    """할인율을 읽기 전에 들어온 증권신고서(진행 중 주주배정)는 한 번 원문을 받아 할인율을 채운다."""
    n = 0
    for r in conn.execute(
            "SELECT s.rcept_no, s.extras_json FROM schedule_versions s JOIN disclosures d USING (rcept_no) "
            "JOIN cases c ON c.case_id=d.case_id WHERE d.kind='estk' AND c.status='open' AND c.is_rights=1").fetchall():
        ex = json.loads(r["extras_json"] or "{}")
        if ex.get("discount_checked") or (ex.get("facts") or {}).get("discount"):
            continue
        try:
            d = next((v for v in (extract_discount(clean(b)) for b in dart.document(r["rcept_no"]).values()) if v), None)
        except DartError:
            continue
        ex.setdefault("facts", {})["discount"] = d
        ex["discount_checked"] = True
        conn.execute("UPDATE schedule_versions SET extras_json=? WHERE rcept_no=?", (db.dumps(ex), r["rcept_no"]))
        n += 1
    conn.commit()
    return n


RETENTION_DAYS = 30   # 신주 상장일 + 30일이 지나면 추적 종료


def step_cleanup(conn, today: date) -> dict:
    """제외: 청약일=납입일인 비주주배정(계열사 내부 증자 등). 보존: 상장일+30일 >= 오늘 또는 상장일 미확인.
    가상 성과 기록이 있는 케이스는 지우지 않고 '종료'로 둔다."""
    out = {"subs_eq_payment": 0, "expired": 0, "closed": 0}
    for c in conn.execute("SELECT * FROM cases WHERE status='open'").fetchall():
        sch = latest_schedule(conn, c["case_id"])
        if not c["is_rights"] and sch.get("subs_start") and sch.get("subs_start") == sch.get("payment_date"):
            drop_case(conn, c["case_id"], "청약일=납입일 (내부 증자)")
            out["subs_eq_payment"] += 1
            continue
        ld = sch.get("listing_date")
        if ld and date.fromisoformat(ld) + timedelta(days=RETENTION_DAYS) < today:
            if conn.execute("SELECT 1 FROM paper_trades WHERE case_id=?", (c["case_id"],)).fetchone():
                conn.execute("UPDATE cases SET status='closed' WHERE case_id=?", (c["case_id"],))
                out["closed"] += 1
            else:
                drop_case(conn, c["case_id"], f"신주 상장일({ld})+{RETENTION_DAYS}일 경과")
                out["expired"] += 1
    conn.commit()
    return out


def recent_business_days(today: date, n: int) -> list[date]:
    out, d = [], today
    while len(out) < n:
        if is_business_day(d):
            out.append(d)
        d -= timedelta(days=1)
    return sorted(out)


def step_prices(krx: KrxClient, conn, today: date, days: int) -> list[dict]:
    """최근 n 영업일 재수집 (KRX 갱신 시각과 무관하게 빠진 날을 메운다)."""
    results = []
    for d in recent_business_days(today, days):
        try:
            results.append(collect_day(krx, conn, d.strftime("%Y%m%d")))
        except KrxError as e:
            results.append({"bas_dd": d.strftime("%Y%m%d"), "error": str(e)})
    return results


MAX_RIGHTS_SPAN_DAYS = 20   # 인수권 상장기간은 보통 5거래일. 이보다 길면 파싱 이상으로 보고 건너뛴다


def step_rights_history(krx: KrxClient, conn, today: date, max_days: int = 150) -> int:
    """주주배정 케이스의 인수권 거래기간 중 아직 조회 안 한 날을 KRX 에서 채운다 (백필된 과거 케이스용).
    - 기간이 공시 전이거나 20일을 넘는 비정상 일정은 건너뜀
    - 최근 날짜부터 채우고, 한 번 조회한 날은 fetched_days 에 기억"""
    last = today - timedelta(days=1)
    need: set[date] = set()
    for c in conn.execute("SELECT * FROM cases WHERE is_rights=1").fetchall():
        sch, _ = checked_schedule(conn, c["case_id"])
        if not (sch.get("rights_start") and sch.get("rights_end")):
            continue
        d, end = date.fromisoformat(sch["rights_start"]), date.fromisoformat(sch["rights_end"])
        disc = date(int(c["first_rcept_dt"][:4]), int(c["first_rcept_dt"][4:6]), int(c["first_rcept_dt"][6:]))
        if d < disc or end < d or (end - d).days > MAX_RIGHTS_SPAN_DAYS:
            continue
        end = min(end, last)
        while d <= end:
            if is_business_day(d) and not conn.execute(
                    "SELECT 1 FROM fetched_days WHERE source='krx.rights' AND bas_dd=?", (d.isoformat(),)).fetchone():
                need.add(d)
            d += timedelta(days=1)
    done = 0
    for d in sorted(need, reverse=True)[:max_days]:
        try:
            collect_day(krx, conn, d.strftime("%Y%m%d"))
        except KrxError:
            continue
        conn.execute("INSERT OR REPLACE INTO fetched_days (source, bas_dd, fetched_at) VALUES ('krx.rights',?,?)",
                     (d.isoformat(), db.now()))
        conn.commit()
        done += 1
    return done


def save_pos52(conn, case_id: int, rows: list[dict], disc: str) -> bool:
    """52주 위치: 공시일 직전 250거래일 고저 중 공시 전일 종가의 위치 (공시일 이후 가격은 안 씀)."""
    window = [r for r in rows if r["date"] < disc][-250:]
    if len(window) < 120:
        return False
    hi, lo = max(r["high"] for r in window), min(r["low"] for r in window)
    px = window[-1]["close"]
    pos = (px - lo) / (hi - lo) if hi > lo else None
    conn.execute(
        "INSERT INTO case_facts (case_id, pos52, pos52_basis, updated_at) VALUES (?,?,?,?) "
        "ON CONFLICT(case_id) DO UPDATE SET pos52=excluded.pos52, pos52_basis=excluded.pos52_basis, "
        "updated_at=excluded.updated_at",
        (case_id, pos, f"{window[-1]['date']} 종가 {px:,.0f} / 52주 저 {lo:,.0f} 고 {hi:,.0f}", db.now()))
    return True


def step_market(naver: NaverClient, conn, today: date) -> dict:
    """주주배정 케이스 본주·지수 일봉 (네이버) → stock_daily / index_daily, 공시일 기준 52주 위치."""
    out = {"stocks": 0, "errors": []}
    cases = conn.execute(
        "SELECT * FROM cases WHERE is_rights=1 AND (status='open' OR case_id IN (SELECT case_id FROM paper_trades))"
    ).fetchall()
    for mkt in {c["corp_cls"] for c in cases if c["corp_cls"] in INDEX_SYMBOL}:
        try:
            for r in naver.daily(INDEX_SYMBOL[mkt], 400):
                conn.execute("INSERT OR REPLACE INTO index_daily (bas_dd, idx, open, high, low, close) VALUES (?,?,?,?,?,?)",
                             (r["date"], INDEX_SYMBOL[mkt], r["open"], r["high"], r["low"], r["close"]))
        except NaverError as e:
            out["errors"].append(str(e))
    for c in cases:
        try:
            rows = naver.daily(c["stock_code"], 400)
        except NaverError as e:
            out["errors"].append(str(e))
            continue
        disc = f"{c['first_rcept_dt'][:4]}-{c['first_rcept_dt'][4:6]}-{c['first_rcept_dt'][6:]}"
        keep_from = (date.fromisoformat(disc) - timedelta(days=45)).isoformat()   # 이벤트 창만 저장 (DB 크기)
        for r in rows:
            if r["date"] < keep_from:
                continue
            conn.execute(
                # KRX 정규장 종가가 이미 있으면 덮지 않는다. 실측: SK디앤디 9/23 KRX 3,335 vs 네이버 3,395
                # (네이버는 NXT 포함 통합시세로 추정). 인수권은 KRX 에서만 거래 → 괴리율은 KRX 종가 기준.
                "INSERT INTO stock_daily (bas_dd, code, close, open, high, low, volume) VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(bas_dd, code) DO NOTHING",
                (r["date"], c["stock_code"], int(r["close"]), int(r["open"]), int(r["high"]), int(r["low"]), r["volume"]))
        save_pos52(conn, c["case_id"], rows, disc)
        out["stocks"] += 1
    conn.commit()
    return out


def step_financials(dart: DartClient, conn, today: date, refresh_days: int = 20) -> int:
    """주주배정 케이스의 직전 분기 영업이익 (DART 재무). refresh_days 마다 갱신."""
    n = 0
    since = (today - timedelta(days=refresh_days)).isoformat()
    for c in conn.execute(
        "SELECT c.* FROM cases c LEFT JOIN case_facts f USING (case_id) WHERE c.is_rights=1 AND c.status='open' "
        "AND (f.op_period IS NULL OR f.updated_at < ?)", (since,)
    ).fetchall():
        try:
            res = dart.latest_op_income(c["corp_code"], today)
        except DartError:
            res = None
        if not res:
            continue
        conn.execute(
            "INSERT INTO case_facts (case_id, op_income, op_period, updated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(case_id) DO UPDATE SET op_income=excluded.op_income, op_period=excluded.op_period, "
            "updated_at=excluded.updated_at", (c["case_id"], res[0], res[1], db.now()))
        n += 1
    conn.commit()
    return n


def live_verdict(conn, c: sqlite3.Row, cfg: Config) -> dict:
    """현재 판정 (최신 괴리 기준). 스냅샷용 함수(decide/reason_for)와 날짜별 괴리도 같이 돌려준다."""
    first = conn.execute("SELECT fields_json FROM disclosures WHERE rcept_no=?", (c["first_rcept_no"],)).fetchone()
    fields = json.loads(first[0] or "{}") if first else {}
    # 정정으로 조건이 바뀌면 최신 piic 필드를 쓴다
    last_piic = conn.execute("SELECT fields_json FROM disclosures WHERE case_id=? AND kind='piic' "
                             "ORDER BY rcept_no DESC LIMIT 1", (c["case_id"],)).fetchone()
    if last_piic and json.loads(last_piic[0] or "{}").get("ic_mthn"):
        fields = json.loads(last_piic[0])
    sm = summarize_fields(fields)
    f = conn.execute("SELECT * FROM case_facts WHERE case_id=?", (c["case_id"],)).fetchone()
    g1 = gate1(sm, latest_facts(conn, c["case_id"]), f["op_income"] if f else None,
               f["op_period"] if f else None, f["pos52"] if f else None, c["corp_name"])
    sch, _ = checked_schedule(conn, c["case_id"])
    gap_on, stock_on = {}, {}
    for r in paper.rights_rows(conn, c):
        s_row = conn.execute("SELECT close FROM stock_daily WHERE bas_dd=? AND code=?",
                             (r["bas_dd"], c["stock_code"])).fetchone()
        stock = (s_row[0] if s_row else None) or r["tar_price"]
        g = compute_gap(r["close"], stock, r["issue_price"] or sch.get("issue_price"))
        stock_on[r["bas_dd"]] = stock
        if g:
            gap_on[r["bas_dd"]] = g.gap_pct
    gap = gap_on[max(gap_on)] if gap_on else None
    cheap, rich = -cfg.gap_alert_pct, cfg.gap_alert_pct
    v = decide(g1, gap, cheap, rich)
    return {"gate1": g1, "gap": gap, "verdict": v, "reason": reason_line(g1, gap, v), "summary": sm,
            "gap_on": gap_on, "stock_on": stock_on,
            "decide": lambda gp: decide(g1, gp, cheap, rich),
            "reason_for": lambda gp, vv: reason_line(g1, gp, vv)}


def step_verdicts(conn, cfg: Config, backfilled: bool = False) -> int:
    """주주배정 케이스마다 판정 → 인수권 마지막 날 종가가 있으면 가상 성과 스냅샷(1회, 불변)."""
    n = 0
    for c in conn.execute("SELECT * FROM cases WHERE is_rights=1").fetchall():
        sch, _ = checked_schedule(conn, c["case_id"])
        n += paper.record_if_due(conn, c, sch, live_verdict(conn, c, cfg), backfilled)
    return n


def step_gap_alerts(conn, cfg: Config) -> None:
    last = conn.execute("SELECT MAX(bas_dd) FROM rights_daily").fetchone()[0]
    if not last:
        return
    for g in gaps_for_day(conn, last):
        if abs(g.gap_pct) >= cfg.gap_alert_pct:
            side = "인수권 저평가 → 인수권 매수+청약 검토" if g.gap_pct < 0 else "인수권 고평가 → 인수권 매도 검토"
            notify.record(conn, f"인수권 괴리 {g.isu_nm}",
                          f"{g.bas_dd} 종가 기준\n인수권 {g.rights_close:,} / 이론가 {g.fair:,} "
                          f"(본주 {g.stock_close:,} − 발행가 {g.issue_price:,})\n괴리율 {g.gap_pct:+.1f}% · {side}\n"
                          f"인수권+청약 신주원가 {g.effective_cost:,}",
                          dedup_key=f"gap:{g.isu_nm}:{g.bas_dd}")


def _log(msg: str) -> None:
    print(f"[{db.now()[11:19]}] {msg}", flush=True)


def run_daily(cfg: Config, conn, today: date, lookback_days: int = 7, price_days: int = 5,
              dart: DartClient | None = None, krx: KrxClient | None = None,
              naver: NaverClient | None = None, backfill_months: int = 0) -> dict:
    """backfill_months > 0 이면 최근 N개월 공시를 월 단위로 조회해 진행 중 케이스를 채운다 (알림 문구 없음)."""
    report: dict = {"today": today.isoformat()}
    step_housekeeping(conn)
    alerts = backfill_months == 0
    if dart or cfg.dart_api_key:
        dart = dart or DartClient(cfg.dart_api_key, conn)
        detected = []
        if backfill_months:
            # 공시검색은 corp_code 없이 3개월 제한 → 월 단위(30일)로 쪼갠다
            windows = [(today - timedelta(days=30 * i + 29), today - timedelta(days=30 * i))
                       for i in range(backfill_months)]
            detected = step_detect(dart, conn, today, windows[-1][0], alerts=False, windows=windows)
        else:
            detected = step_detect(dart, conn, today, today - timedelta(days=lookback_days))
        report["detected"] = len(detected)
        merge_duplicate_cases(conn)
        _log(f"감지 {len(detected)}건 → 원문 일정 파싱")
        step_schedules(dart, conn, alerts)
        _log("증권신고서 보강")
        step_estk(dart, conn, today, alerts)
        report["cleanup"] = step_cleanup(conn, today)
        _log(f"정리 {report['cleanup']}")
    else:
        report["dart"] = "DART_API_KEY 없음 — 건너뜀"
    if krx or cfg.krx_api_key:
        krx = krx or KrxClient(cfg.krx_api_key, conn)
        _log("KRX 시세")
        report["prices"] = step_prices(krx, conn, today, price_days)
        report["rights_history_days"] = step_rights_history(krx, conn, today)
        _log(f"인수권 과거 시세 {report['rights_history_days']}일 보충")
    else:
        report["krx"] = "KRX_API_KEY 없음 — 건너뜀"
    report["relinked"] = relink_rights(conn)
    naver = naver or NaverClient()
    _log("네이버 일봉")
    report["market"] = step_market(naver, conn, today)
    if dart:
        _log("DART 재무")
        report["financials"] = step_financials(dart, conn, today)
    report["paper_recorded"] = step_verdicts(conn, cfg, backfilled=bool(backfill_months))
    _log(f"판정·가상성과 {report['paper_recorded']}건 기록")
    if alerts:
        step_gap_alerts(conn, cfg)
    return report
