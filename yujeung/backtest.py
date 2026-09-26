"""과거 유증 백테스트 (Phase 1 + H1) — '기출문제'.

대상: 2020-01 ~ 2026-06 DART 유상증자결정 중 주주배정 계열, 상장사. 연도별로 나눠 실행한다.
    python -m yujeung backtest --year 2020      → data/backtest/2020.json + data/backtest.json(전체 합산)

흐름 (연도마다 빈 임시 DB에서 새로 — 운영 DB 는 건드리지 않는다)
  1. 네이버 지수 일봉 → 실제 거래일로 과거 휴장일 채우기 (calendar_kr 는 2026 만 들고 있음)
  2. 공시 감지: 그해 원공시 + 정정은 해 넘어 120일까지. 상장폐지 회사(현재 법인구분 E)도 포함
  3. 원문·증권신고서 파싱 → 파싱 성공률 (필수: 기준일·인수권 기간·청약 시작·상장일)
  4. KRX: 각 케이스의 '인수권 거래기간 날짜'와 '상장일~+25거래일'만 조회 (상장폐지 종목 포함)
     네이버 일봉은 KRX 에 없는 날(52주 위치용 과거 1년)만 보충
  5. 미래 정보 금지: 영업이익 = 판정일(인수권 마지막 날)까지 제출기한이 지난 마지막 보고서,
     52주 위치 = 공시일 직전 250거래일, 괴리율 = 인수권 기간 당일 KRX 종가·KRX 발행가
  6. 판정 = verdict.py 그대로(pipeline.live_verdict), 가상 진입·측정 = paper.py 그대로
     + 비교 기준(모든 케이스 '인수권 매수+청약')으로 필터별 결과
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from . import db, paper
from .calendar_kr import is_business_day, register_trading_days, shift_business_days
from .config import Config
from .dart import DartClient, DartError
from .detect import detect, merge_duplicate_cases
from .krx import KrxClient, KrxError
from .naver import INDEX_SYMBOL, NaverClient, NaverError
from .pipeline import (MAX_RIGHTS_SPAN_DAYS, checked_schedule, latest_facts, live_verdict, save_pos52, step_estk,
                       step_schedules)
from .prices import relink_rights, store_rights_rows, store_stock_rows
from .verdict import LOGIC_VERSION, VERDICTS, base

FIRST_YEAR = 2020
LAST_DAY = date(2026, 6, 30)          # 원공시 대상 마지막 날
CORRECTION_TAIL_DAYS = 120            # 정정공시는 해를 넘겨서도 이만큼 더 본다
ESTK_WINDOW_DAYS = 150                # 증권신고서는 최초 공시 후 이 기간만 (다른 해 유증 섞임 방지)
LISTING_WINDOW = 25                   # 상장일 ~ +25거래일 KRX 조회 (+20일 측정 여유)
INDEX_COUNT = 2600                    # 네이버 지수 일봉 개수 (~10년)
REQUIRED = ("record_date", "rights_start", "rights_end", "subs_start", "listing_date")
MIN_CARD_N = 5                        # 카드 손익표를 실제 분포로 바꾸는 최소 표본
BACKTEST_DIR = Path("data/backtest")
BACKTEST_JSON = Path("data/backtest.json")
KRX_MARKET = {"Y": "Y", "K": "K"}


def _log(msg: str) -> None:
    print(f"[backtest {datetime.now(db.KST).strftime('%H:%M:%S')}] {msg}", flush=True)


def _d(yyyymmdd: str) -> date:
    return date(int(yyyymmdd[:4]), int(yyyymmdd[4:6]), int(yyyymmdd[6:8]))


def year_range(year: int, today: date, months: int = 12) -> tuple[date, date]:
    end = date(year, 12, 31) if months >= 12 else date(year, months + 1, 1) - timedelta(days=1)
    return date(year, 1, 1), min(end, LAST_DAY, today)


def windows(bgn: date, end: date) -> list[tuple[date, date]]:
    """공시검색은 corp_code 없이 3개월 제한 → 30일 구간."""
    out, d = [], bgn
    while d <= end:
        out.append((d, min(d + timedelta(days=29), end)))
        d += timedelta(days=30)
    return out


# ---- 1. 거래일 ----
def load_index(naver: NaverClient, conn) -> list[str]:
    days: list[str] = []
    for mkt, sym in INDEX_SYMBOL.items():
        rows = naver.daily(sym, INDEX_COUNT)
        for r in rows:
            conn.execute("INSERT OR REPLACE INTO index_daily (bas_dd, idx, open, high, low, close) VALUES (?,?,?,?,?,?)",
                         (r["date"], sym, r["open"], r["high"], r["low"], r["close"]))
        if mkt == "Y":
            days = [r["date"] for r in rows]
    conn.commit()
    return days


# ---- 2. 감지 범위 ----
def scope_cases(conn, bgn: date, end: date) -> dict:
    """그해 원공시로 시작한 주주배정 케이스만 남긴다. 정정으로 시작한 케이스 = 원공시가 전년도 → 전년도 실행 몫."""
    out = {"out_of_year": 0, "starts_with_correction": 0}
    for c in conn.execute("SELECT * FROM cases").fetchall():
        first = conn.execute("SELECT is_correction FROM disclosures WHERE rcept_no=?", (c["first_rcept_no"],)).fetchone()
        reason = None
        if not (bgn <= _d(c["first_rcept_dt"]) <= end):
            reason = "out_of_year"
        elif first and first["is_correction"]:
            reason = "starts_with_correction"
        if reason:
            out[reason] += 1
            for t in ("schedule_versions", "disclosures", "case_facts", "paper_trades"):
                conn.execute(f"DELETE FROM {t} WHERE case_id=?", (c["case_id"],))
            conn.execute("DELETE FROM cases WHERE case_id=?", (c["case_id"],))
    conn.commit()
    return out


# ---- 4. KRX (필요한 날짜만) ----
def _bdays(a: date, b: date) -> list[date]:
    out = []
    while a <= b:
        if is_business_day(a):
            out.append(a)
        a += timedelta(days=1)
    return out


def rights_days(sch: dict, disc: date, last: date) -> list[date]:
    if not (sch.get("rights_start") and sch.get("rights_end")):
        return []
    a, b = date.fromisoformat(sch["rights_start"]), date.fromisoformat(sch["rights_end"])
    if a < disc or b < a or (b - a).days > MAX_RIGHTS_SPAN_DAYS:
        return []
    return _bdays(a, min(b, last))


def listing_days(sch: dict, last: date) -> list[date]:
    if not sch.get("listing_date"):
        return []
    a = date.fromisoformat(sch["listing_date"])
    return _bdays(a, min(shift_business_days(a, LISTING_WINDOW), last))


def fetch_krx(krx: KrxClient, conn, plans: dict[int, dict], last: date) -> dict:
    """인수권 기간 → sr_bydd_trd, 그다음 케이스 시장을 정해 본주(인수권 기간 + 상장 창) 조회."""
    stats = {"rights_days": 0, "stock_calls": 0, "errors": 0}
    r_days = sorted({d for p in plans.values() for d in p["rights"]})
    for d in r_days:
        try:
            store_rights_rows(conn, krx.rights(d.strftime("%Y%m%d")))
            stats["rights_days"] += 1
        except KrxError as e:
            stats["errors"] += 1
            _log(f"KRX 인수권 {d} 실패: {e}")
    relink_rights(conn)
    # 법인구분이 E(현재 상장폐지)면 인수권 시장명으로 당시 시장을 정한다
    for cid, p in plans.items():
        c = conn.execute("SELECT * FROM cases WHERE case_id=?", (cid,)).fetchone()
        mkt = KRX_MARKET.get(c["corp_cls"])
        if not mkt:
            r = conn.execute("SELECT mkt_nm FROM rights_daily WHERE substr(isu_cd,1,6)=? AND mkt_nm IS NOT NULL "
                             "LIMIT 1", (c["stock_code"],)).fetchone()
            if r:
                mkt = "K" if "KOSDAQ" in r[0].upper() or "코스닥" in r[0] else "Y"
                conn.execute("UPDATE cases SET corp_cls=? WHERE case_id=?", (mkt, cid))
        p["market"] = mkt
    conn.commit()
    need: dict[date, dict[str, set[str]]] = {}
    for p in plans.values():
        if not p.get("market"):
            continue
        for d in p["rights"] + p["listing"]:
            need.setdefault(d, {}).setdefault(p["market"], set()).add(p["code"])
    for d in sorted(need):
        for mkt, codes in need[d].items():
            try:
                store_stock_rows(conn, krx.stocks(d.strftime("%Y%m%d"), mkt), codes)
                stats["stock_calls"] += 1
            except KrxError as e:
                stats["errors"] += 1
                _log(f"KRX 본주 {d} {mkt} 실패: {e}")
    return stats


# ---- 5. 네이버 보충 + 52주 위치 ----
def naver_fill(naver: NaverClient, conn, c: sqlite3.Row, trading_days: list[str], today: date) -> bool:
    disc = _d(c["first_rcept_dt"])
    since = (disc - timedelta(days=380)).isoformat()
    count = sum(1 for d in trading_days if d >= since) + 5
    try:
        rows = naver.daily(c["stock_code"], count)
    except NaverError:
        return False     # 상장폐지 종목은 네이버에 없다 → 52주 위치 미확인
    for r in rows:
        conn.execute(
            "INSERT INTO stock_daily (bas_dd, code, close, open, high, low, volume) VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(bas_dd, code) DO NOTHING",   # KRX 값이 있으면 KRX 우선
            (r["date"], c["stock_code"], int(r["close"]), int(r["open"]), int(r["high"]), int(r["low"]), r["volume"]))
    return save_pos52(conn, c["case_id"], rows, disc.isoformat())


def financials_asof(dart: DartClient, conn, c: sqlite3.Row, asof: date) -> bool:
    try:
        res = dart.op_income_asof(c["corp_code"], asof)
    except DartError:
        res = None
    if not res:
        return False
    conn.execute(
        "INSERT INTO case_facts (case_id, op_income, op_period, updated_at) VALUES (?,?,?,?) "
        "ON CONFLICT(case_id) DO UPDATE SET op_income=excluded.op_income, op_period=excluded.op_period, "
        "updated_at=excluded.updated_at", (c["case_id"], res[0], res[1], db.now()))
    return True


def _compact(ev: dict) -> dict:
    return {"entry": ev.get("entry"), "entry_date": ev.get("entry_date"), "error": ev.get("error"),
            "pending": ev.get("pending"), "issue_note": ev.get("issue_note"),
            "points": [{k: p.get(k) for k in ("label", "date", "price", "ret", "excess", "pending") if p.get(k) is not None}
                       for p in ev.get("points", [])]}


# ---- 공시 감지 (본 기간 + 꼬리) ----
def tail_keep(end: date):
    """꼬리 기간(해 넘어간 +120일) 공시는 '그 회사 케이스가 이미 있을 때만' 상세 조회.
    케이스가 없는 회사의 꼬리 공시는 새 케이스(원공시 → out_of_year, 정정 → 정정으로 시작)만 만들고
    scope_cases 에서 지워지므로 결과에 영향이 없다. 케이스가 있는 회사는 원공시까지 전부 조회해야 한다 —
    꼬리 원공시가 새 케이스를 열어야 뒤따르는 정정이 그해 케이스에 잘못 붙지 않는다."""
    cut = end.strftime("%Y%m%d")

    def keep(conn, rep: dict) -> bool:
        return rep["rcept_dt"] <= cut or conn.execute(
            "SELECT 1 FROM cases WHERE corp_code=? LIMIT 1", (rep["corp_code"],)).fetchone() is not None
    return keep


def detect_year(dart: DartClient, conn, bgn: date, end: date, last: date, tail_filter: bool = True) -> dict:
    tail = min(end + timedelta(days=CORRECTION_TAIL_DAYS), last)
    fmt = "%Y%m%d"
    detect(dart, conn, bgn.strftime(fmt), tail.strftime(fmt),
           [(a.strftime(fmt), b.strftime(fmt)) for a, b in windows(bgn, tail)],
           rights_only=True, listed=("Y", "K", "E"), keep=tail_keep(end) if tail_filter else None)
    scope = scope_cases(conn, bgn, end)
    merge_duplicate_cases(conn)
    return scope


def case_signature(conn) -> dict:
    """채점 대상을 결정하는 것 = 남은 주주배정 케이스와 거기 붙은 공시(원문 파싱·시세·판정은 이것의 함수)."""
    out = {}
    for c in conn.execute("SELECT * FROM cases WHERE is_rights=1").fetchall():
        out[c["first_rcept_no"]] = {
            "corp_name": c["corp_name"], "ic_mthn": c["ic_mthn"], "status": c["status"],
            "disclosures": [tuple(r) for r in conn.execute(
                "SELECT rcept_no, kind, is_correction FROM disclosures WHERE case_id=? ORDER BY rcept_no",
                (c["case_id"],))]}
    return out


class CallCounter:
    """API 클라이언트 감싸기: 호출 수를 세고, 같은 인자 호출은 캐시(비교 실행 두 번째에 네트워크 안 씀)."""
    def __init__(self, inner, cache: dict):
        self._inner, self._cache, self.calls = inner, cache, {}

    def __getattr__(self, name):
        fn = getattr(self._inner, name)

        def call(*a, **kw):
            self.calls[name] = self.calls.get(name, 0) + 1
            key = (name, a, tuple(sorted(kw.items())))
            if key not in self._cache:
                self._cache[key] = fn(*a, **kw)
            return self._cache[key]
        return call


def compare_tail(year: int, dart: DartClient, today: date, months: int = 12) -> dict:
    """꼬리 기간 상세 조회 생략 전후 비교 — 감지 단계만 두 번(두 번째는 캐시) 돌려 케이스·공시 묶음이 같은지."""
    bgn, end = year_range(year, today, months)
    last = today - timedelta(days=1)
    cache, out = {}, {}
    for mode, flt in (("before", False), ("after", True)):
        client = CallCounter(dart, cache)
        conn = db.connect(":memory:")
        scope = detect_year(client, conn, bgn, end, last, tail_filter=flt)
        out[mode] = {"sig": case_signature(conn), "calls": dict(client.calls), "scope": scope}
    a, b = out["before"]["sig"], out["after"]["sig"]
    diff = sorted(set(a) ^ set(b)) + sorted(k for k in set(a) & set(b) if a[k] != b[k])
    res = {"year": year, "cases_before": len(a), "cases_after": len(b), "identical": not diff, "diff": diff,
           "calls_before": out["before"]["calls"], "calls_after": out["after"]["calls"],
           "scope_before": out["before"]["scope"], "scope_after": out["after"]["scope"]}
    _log(f"비교 {year}: {json.dumps(res, ensure_ascii=False)}")
    return res


# ---- 연도 실행 ----
def run_year(year: int, cfg: Config, dart: DartClient, krx: KrxClient, naver: NaverClient,
             today: date, out_dir: Path = BACKTEST_DIR, db_path: str = ":memory:", months: int = 12) -> dict:
    if not (FIRST_YEAR <= year <= LAST_DAY.year):
        raise ValueError(f"백테스트 대상은 {FIRST_YEAR}~{LAST_DAY.year}년")
    conn = db.connect(db_path)
    bgn, end = year_range(year, today, months)
    last = today - timedelta(days=1)
    _log(f"{year}: 원공시 {bgn}~{end}, 정정은 +{CORRECTION_TAIL_DAYS}일까지")

    trading_days = load_index(naver, conn)
    holidays = register_trading_days(trading_days)
    _log(f"거래일 {len(trading_days)}일 (휴장일 {holidays}일 보충)")

    scope = detect_year(dart, conn, bgn, end, last)
    cases = conn.execute("SELECT * FROM cases WHERE is_rights=1 ORDER BY first_rcept_dt").fetchall()
    _log(f"주주배정 케이스 {len(cases)}건 {scope} → 원문 파싱")
    step_schedules(dart, conn, alerts=False)
    step_estk(dart, conn, today, alerts=False, discount=False, window_days=ESTK_WINDOW_DAYS)

    plans: dict[int, dict] = {}
    parse: dict[int, tuple[dict, list[str]]] = {}
    missing_by_field = {k: 0 for k in REQUIRED}
    unlisted: set[int] = set()
    for c in cases:
        sch, _ = checked_schedule(conn, c["case_id"])
        missing = [k for k in REQUIRED if not sch.get(k)]
        parse[c["case_id"]] = (sch, missing)
        # '신주인수권증서의 상장여부 아니오'(최대주주 단독 배정 등) — 인수권 거래가 원래 없다. 파싱 실패가 아니라 대상 밖
        if missing and latest_facts(conn, c["case_id"]).get("rights_listed") is False:
            unlisted.add(c["case_id"])
            continue
        for k in missing:
            missing_by_field[k] += 1
        if not missing:
            plans[c["case_id"]] = {"code": c["stock_code"], "rights": rights_days(sch, _d(c["first_rcept_dt"]), last),
                                   "listing": listing_days(sch, last)}
    n_ok = len(plans)
    n_target = len(cases) - len(unlisted)
    _log(f"인수권 비상장 주주배정 {len(unlisted)}건 제외 · 파싱 성공 {n_ok}/{n_target} → KRX 인수권 {len({d for p in plans.values() for d in p['rights']})}일 조회")
    krx_stats = fetch_krx(krx, conn, plans, last)

    records = []
    for c in conn.execute("SELECT * FROM cases WHERE is_rights=1 ORDER BY first_rcept_dt").fetchall():
        sch, missing = parse[c["case_id"]]
        rec = {"case_id": c["case_id"], "corp_name": c["corp_name"], "stock_code": c["stock_code"],
               "market": c["corp_cls"], "first_rcept_dt": c["first_rcept_dt"],
               "rcept_nos": [r[0] for r in conn.execute("SELECT rcept_no FROM disclosures WHERE case_id=? "
                                                        "ORDER BY rcept_no", (c["case_id"],))],
               "schedule": {k: sch.get(k) for k in ("record_date", "rights_start", "rights_end", "subs_start",
                                                    "listing_date", "issue_price", "alloc_ratio")},
               "missing": missing}
        if c["case_id"] in unlisted:
            rec["status"] = "no_rights_listing"
            records.append(rec)
            continue
        if missing:
            rec["status"] = "parse_fail"
            records.append(rec)
            continue
        rec["naver"] = naver_fill(naver, conn, c, trading_days, today)
        decision = date.fromisoformat(sch["rights_end"])
        rec["financials"] = financials_asof(dart, conn, c, decision)
        conn.commit()
        live = live_verdict(conn, c, cfg)
        paper.record_if_due(conn, c, sch, live, backfilled=True)
        trade = conn.execute("SELECT * FROM paper_trades WHERE case_id=?", (c["case_id"],)).fetchone()
        f = conn.execute("SELECT * FROM case_facts WHERE case_id=?", (c["case_id"],)).fetchone()
        sm = live["summary"]
        rec.update({
            "debt_pct": (sm.get("purpose_pct") or {}).get("채무상환", 0.0), "dilution": sm.get("dilution_ratio"),
            "op_income": f["op_income"] if f else None, "op_period": f["op_period"] if f else None,
            "pos52": f["pos52"] if f else None,
            "gate": {x["key"]: x["status"] for x in live["gate1"]["criteria"]}, "gate_passed": live["gate1"]["passed"],
        })
        if not trade:
            rec["status"] = "no_rights_price"
            records.append(rec)
            continue
        snap = json.loads(trade["snapshot_json"])
        base_trade = {"verdict": "white", "decided_on": trade["decided_on"], "snapshot_json": trade["snapshot_json"]}
        rec.update({
            "status": "scored", "verdict": trade["verdict"], "decided_on": trade["decided_on"],
            "reason": snap["reason"], "gap": snap.get("gap"),
            "eval": _compact(paper.evaluate(conn, c, trade, sch, today)),
            "base": _compact(paper.evaluate(conn, c, base_trade, sch, today)),
        })
        records.append(rec)

    summary = {
        "year": year, "months": months, "generated_at": db.now(), "logic_version": LOGIC_VERSION, "range": [bgn.isoformat(), end.isoformat()],
        "counts": {
            "cases": len(cases), "no_rights_listing": len(unlisted), "parse_target": n_target, "parse_ok": n_ok,
            "parse_rate": round(n_ok / n_target * 100, 1) if n_target else None,
            "parse_rate_all": round(n_ok / len(cases) * 100, 1) if cases else None,
            "missing_by_field": missing_by_field, **scope,
            "no_rights_price": sum(r["status"] == "no_rights_price" for r in records),
            "scored": sum(r["status"] == "scored" for r in records),
            "naver_missing": sum(r.get("naver") is False for r in records),
            "financials_missing": sum(r.get("financials") is False for r in records),
            "krx": krx_stats, "holidays_registered": holidays,
        },
        "cases": records,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{year}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    _log(f"{year} 완료: {summary['counts']}")
    return summary


# ---- 합산 ----
def percentile(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    k = (len(s) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 1)


def stats(points: list[dict]) -> dict:
    rets = [p["ret"] for p in points if p.get("ret") is not None]
    exc = [p["excess"] for p in points if p.get("excess") is not None]
    if not rets:
        return {"n": 0}
    return {"n": len(rets), "win_rate": round(sum(r > 0 for r in rets) / len(rets) * 100),
            "mean": round(sum(rets) / len(rets), 1), "median": percentile(rets, 0.5),
            "p25": percentile(rets, 0.25), "p75": percentile(rets, 0.75), "worst": min(rets),
            "excess_mean": round(sum(exc) / len(exc), 1) if exc else None,
            "excess_median": percentile(exc, 0.5)}


def _point(ev: dict | None, label: str) -> dict:
    return next((p for p in (ev or {}).get("points", []) if p.get("label") == label), {})


def _bucket(rec: dict, key: str) -> str:
    if key == "debt":
        return "채무상환 50% 미만" if (rec.get("debt_pct") or 0) < 50 else "채무상환 50% 이상"
    if key == "dilution":
        d = rec.get("dilution")
        return "희석 미확인" if d is None else "희석 50% 미만" if d < 0.5 else "희석 50~100%" if d < 1 else "희석 100% 이상"
    if key == "profit":
        o = rec.get("op_income")
        return "영업 미확인" if o is None else "직전 분기 흑자" if o > 0 else "직전 분기 적자"
    if key == "gap":
        g = rec.get("gap")
        if g is None:
            return "괴리 없음"
        return ("괴리 −40% 이하" if g <= -40 else "괴리 −40~−20%" if g <= -20 else "괴리 −20~0%" if g < 0
                else "괴리 0~+20%" if g < 20 else "괴리 +20% 이상")
    if key == "gate":
        return "관문1 통과" if rec.get("gate_passed") else "관문1 탈락"
    raise KeyError(key)


FILTERS = [("gate", "관문1 전체"), ("debt", "채무상환 비중"), ("dilution", "희석률"), ("profit", "흑자 여부"),
           ("gap", "괴리율 구간 (H1)")]
BASE_POINTS = ("상장일 시가", "+5일", "+20일")


def aggregate(out_dir: Path = BACKTEST_DIR) -> dict:
    years, recs = [], []
    for f in sorted(out_dir.glob("*.json")):
        y = json.loads(f.read_text(encoding="utf-8"))
        years.append({"year": y["year"], "generated_at": y["generated_at"], **{k: v for k, v in y["counts"].items()
                                                                            if k != "krx"}})
        recs += [dict(r, year=y["year"]) for r in y["cases"] if r.get("status") == "scored"]

    by_verdict = []
    for v, (emoji, name) in VERDICTS.items():
        mine = [r for r in recs if r["verdict"] == v]
        labels = [lb for lb, _, _ in paper.POINTS["yellow" if base(v) == "yellow" else "rights"]]
        by_verdict.append({"verdict": v, "emoji": emoji, "name": name, "n": len(mine),
                           "points": [{"label": lb, **stats([_point(r["eval"], lb) for r in mine])} for lb in labels]})
    filters = []
    for key, title in FILTERS:
        groups: dict[str, list[dict]] = {}
        for r in recs:
            groups.setdefault(_bucket(r, key), []).append(r)
        filters.append({"key": key, "title": title, "rows": [
            {"bucket": b, "n": len(rs), "points": [{"label": lb, **stats([_point(r["base"], lb) for r in rs])}
                                                  for lb in BASE_POINTS]}
            for b, rs in sorted(groups.items())]})
    # 카드 손익표: 판정별 '인수권 매수+청약 → 상장일 시가' 실제 분포 (표본 부족하면 기본값 유지)
    card = {}
    for v in VERDICTS:
        rets = [p["ret"] for p in (_point(r["base"], "상장일 시가") for r in recs if r["verdict"] == v)
                if p.get("ret") is not None]
        card[v] = {"n": len(rets), "p75": percentile(rets, 0.75), "p50": percentile(rets, 0.5),
                   "p25": percentile(rets, 0.25), "min": min(rets) if rets else None,
                   "use": len(rets) >= MIN_CARD_N}
    out = {"generated_at": db.now(), "logic_version": LOGIC_VERSION, "years": years, "n_scored": len(recs),
           "by_verdict": by_verdict, "filters": filters, "card_scenarios": card, "min_card_n": MIN_CARD_N,
           "base_note": "필터별 결과는 판정과 무관하게 모든 케이스를 '인수권 마지막 날 인수권 매수 + 청약'으로 "
                        "진입했다고 보고 잰 비교 기준",
           "cases": [{k: r.get(k) for k in ("year", "corp_name", "stock_code", "first_rcept_dt", "verdict", "reason",
                                            "gap", "decided_on")} | {"ret20": _point(r["eval"], "+20일").get("ret"),
                                                                     "base_open": _point(r["base"], "상장일 시가").get("ret")}
                     for r in recs]}
    return out


def write_aggregate(out_dir: Path = BACKTEST_DIR, path: Path = BACKTEST_JSON) -> dict:
    agg = aggregate(out_dir)
    path.write_text(json.dumps(agg, ensure_ascii=False, indent=1), encoding="utf-8")
    return agg


def load_card_scenarios(path: Path = BACKTEST_JSON) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("card_scenarios") or {}
    except (OSError, ValueError):
        return {}
