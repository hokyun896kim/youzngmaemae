"""실전 전략 배지 ([18]) — 기존 판정(🟢🟡🔵⚪) 위에 얹는 '행동 카드'.

근거: docs/backtest.md 기출 287건. 숫자 조정은 이 파일 상수만 고치면 된다 (화면·기록·백테스트 공통).
근거 숫자(건수·중앙값·승률)는 하드코딩하지 않는다 — backtest.aggregate 가 data/backtest.json 의
"strategies" 에 계산해 두고 화면이 그걸 읽는다 (백테스트를 다시 돌리면 자동 갱신).

금지 규칙 (최우선)
  희석 ≥ 100%           → ⛔ 전략 전부 끔
  직전 분기 적자        → 전략 2·3 불가 (전략 1은 가능)
  괴리 ≤ −40%           → 전략 3 불가 (너무 싼 인수권)
  남는 전략이 없고 금지 규칙이 걸렸으면 카드에 ⛔
전략
  🥇 s1 비싼 인수권 팔기     괴리 ≥ +20% (인수권 거래기간)           → 보유자는 매도 / 신규 매수 금지
  🥈 s2 신주 상장일 매수      흑자 + 희석 < 50% + 채무상환 < 50%       → 상장일 종가 진입, +10거래일 청산,
                               (표시: 상장 D-3 ~ +10거래일)              손절 = 진입가 − ATR(14)×2, 비중 절반,
                                                                         게이트 = 상장일 종가 RSI(14) ≤ 50
  🥉 s3 적당히 싼 인수권      흑자 + 희석 < 100% + −20% < 괴리 < 0%    → 인수권 매수 + 청약, 상장 후 +5거래일 안에 청산, 소액
가상 성과 (strategy_trades, 전략별·불변 스냅샷)
  s1·s3: 인수권 마지막 날 (판정 스냅샷과 같은 순간). 원금 = 인수권 종가 + 발행가.
         s1 은 🔵 처럼 "팔지 않고 청약했다면" 수익률 → 낮을수록 적중 (매도 유리 비율로 집계)
  s2   : 신주 상장일 종가가 들어온 순간. +5 / +10거래일(청산), 손절선을 치면 그 가격에 청산
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date
from statistics import median

from . import db
from .calendar_kr import shift_business_days

STRATEGY_VERSION = 3   # 3: 전략2에 '판정 🟡/🟡?' 조건 추가 (형님 B안 — 기출 조건 전체 70건 +0.5% vs 🟡? 14건 +5.0%)
#                        2: ATR·RSI 를 한 출처(네이버 수정주가)로만 계산, ATR 은 % 로 진입가에 적용
#                        1: KRX 원주가와 네이버 수정주가가 섞여 ATR 이 부풀었음 (손절선이 음수가 되기도)

# ---- 금지 규칙 ----
BAN_DILUTION = 1.0            # 희석(신주 ÷ 기존주) ≥ 100% → ⛔
TOO_CHEAP_GAP = -40.0         # 괴리 ≤ −40% → 전략 3 불가

# ---- 전략 1: 비싼 인수권 팔기 ----
S1_GAP_MIN = 20.0

# ---- 전략 2: 신주 상장일 매수 → 10거래일 보유 ----
S2_VERDICTS = ("yellow",)     # 판정(verdict.base) 🟡 · 🟡? 일 때만 = 관문1 통과 + 괴리 신호 없음
S2_DATA_MIN = 2               # 백테스트 연도 결과의 전략2 평가가 쓸 만한 최소 전략 버전 (v1 = ATR 출처 혼합 버그)
S2_DILUTION_MAX = 0.5
S2_DEBT_MAX = 50.0
S2_SHOW_BEFORE = 3            # 상장 D-3(거래일)부터 표시
S2_HOLD_DAYS = 10
S2_ATR_N = 14
S2_ATR_MULT = 2.0
S2_RSI_N = 14
S2_RSI_MAX = 50.0             # 상장일 종가 RSI ≤ 50 → 진입 가능
S2_SIZE = "평소의 절반"

# ---- 전략 3: 적당히 싼 인수권 매수 + 청약 ----
S3_GAP_LO = -20.0             # 괴리 −20% 초과 (−20% 이하는 기출 '−40~−20%' 구간)
S3_GAP_HI = 0.0
S3_DILUTION_MAX = 1.0
S3_EXIT_DAYS = 5
S3_SIZE = "소액"

STRATEGIES = {
    "s1": {"medal": "🥇", "name": "비싼 인수권 팔기", "evidence": "강", "title": "인수권 보유자는 매도 / 신규 매수 금지",
           "action": "인수권 보유자는 매도 / 신규 매수 금지",
           "cond": f"괴리율 ≥ +{S1_GAP_MIN:.0f}% (인수권 거래기간)",
           "point": "+20일", "win": "sell"},
    "s2": {"medal": "🥈", "name": "신주 상장일 매수 → 10거래일 보유", "evidence": "중",
           "title": f"신주 상장일 매수 → {S2_HOLD_DAYS}거래일 보유",
           "action": f"상장일 종가 진입 · +{S2_HOLD_DAYS}거래일 청산 · 손절 진입가 − ATR({S2_ATR_N})×{S2_ATR_MULT:g} · "
                     f"비중 {S2_SIZE}",
           "cond": f"판정 🟡/🟡? + 직전 분기 흑자 + 희석 < {S2_DILUTION_MAX * 100:.0f}% + 채무상환 < {S2_DEBT_MAX:.0f}%",
           "point": f"+{S2_HOLD_DAYS}일", "win": "up"},
    "s3": {"medal": "🥉", "name": "적당히 싼 인수권 매수 + 청약", "evidence": "약~중",
           "title": "적당히 싼 인수권 매수 + 청약",
           "action": f"인수권 매수 → 청약 → 상장 후 +{S3_EXIT_DAYS}거래일 안에 청산 · 비중 {S3_SIZE}",
           "cond": f"직전 분기 흑자 + 희석 < {S3_DILUTION_MAX * 100:.0f}% + 괴리율 {S3_GAP_LO:.0f}% ~ {S3_GAP_HI:.0f}%",
           "point": f"+{S3_EXIT_DAYS}일", "win": "up"},
}
BANS = {
    "dilution": {"label": f"희석 {BAN_DILUTION * 100:.0f}%↑", "effect": "패스", "blocks": ("s1", "s2", "s3")},
    "loss": {"label": "직전 분기 적자", "effect": "전략 2·3 불가 (전략 1은 가능)", "blocks": ("s2", "s3")},
    "too_cheap": {"label": "너무 싼 인수권", "effect": "전략 3 불가", "blocks": ("s3",)},
}


def rules() -> dict:
    """화면에 내보내는 규칙 문구 (site.json)."""
    return {"version": STRATEGY_VERSION, "strategies": STRATEGIES, "bans": BANS,
            "too_cheap_gap": TOO_CHEAP_GAP, "rsi_max": S2_RSI_MAX, "s1_gap_min": S1_GAP_MIN,
            "s2_atr_mult": S2_ATR_MULT, "s2_hold_days": S2_HOLD_DAYS, "s3_exit_days": S3_EXIT_DAYS}


# ---- 조건 ----
def conditions(dilution: float | None, debt_pct: float | None, op_income: int | None, gap: float | None,
               verdict: str | None = None) -> dict:
    """전략별 조건 충족 여부 + 걸린 금지 규칙. 미확인 값은 '충족 아님'(보수적).
    verdict = 판정 코드(green/yellow_q/…) — 전략2는 🟡/🟡? 일 때만."""
    from .verdict import base
    debt = debt_pct or 0.0                           # 자금 목적에 채무상환이 없으면 0% (관문1과 같음)
    profit = op_income is not None and op_income > 0
    bans = []
    if dilution is not None and dilution >= BAN_DILUTION:
        bans.append("dilution")
    if op_income is not None and op_income <= 0:
        bans.append("loss")
    if gap is not None and gap <= TOO_CHEAP_GAP:
        bans.append("too_cheap")
    blocked = {s for b in bans for s in BANS[b]["blocks"]}
    ok = {
        "s1": gap is not None and gap >= S1_GAP_MIN,
        "s2": (profit and dilution is not None and dilution < S2_DILUTION_MAX and debt < S2_DEBT_MAX
               and verdict is not None and base(verdict) in S2_VERDICTS),
        "s3": (profit and dilution is not None and dilution < S3_DILUTION_MAX
               and gap is not None and S3_GAP_LO < gap < S3_GAP_HI),
    }
    return {"ok": {k: v and k not in blocked for k, v in ok.items()}, "bans": bans}


# ---- 지표 (Wilder) ----
def rsi(closes: list[float], n: int = S2_RSI_N) -> float | None:
    if len(closes) < n + 1:
        return None
    ch = [b - a for a, b in zip(closes, closes[1:])]
    up = sum(max(c, 0) for c in ch[:n]) / n
    dn = sum(max(-c, 0) for c in ch[:n]) / n
    for c in ch[n:]:
        up = (up * (n - 1) + max(c, 0)) / n
        dn = (dn * (n - 1) + max(-c, 0)) / n
    if dn == 0:
        return 100.0 if up > 0 else 50.0
    return round(100 - 100 / (1 + up / dn), 1)


def atr(rows: list[dict], n: int = S2_ATR_N) -> float | None:
    """rows: [{high, low, close}] 오래된 순. 고저가 빈 날은 뺀다."""
    rows = [r for r in rows if r.get("high") and r.get("low") and r.get("close")]
    if len(rows) < n + 1:
        return None
    tr = [max(b["high"] - b["low"], abs(b["high"] - a["close"]), abs(b["low"] - a["close"]))
          for a, b in zip(rows, rows[1:])]
    v = sum(tr[:n]) / n
    for t in tr[n:]:
        v = (v * (n - 1) + t) / n
    return round(v, 1)


def _stock(conn: sqlite3.Connection, code: str) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT bas_dd, open, high, low, close, n_close, n_high, n_low FROM stock_daily WHERE code=? AND close IS NOT NULL "
        "ORDER BY bas_dd",
        (code,))]


def indicators(rows: list[dict], upto: str) -> dict:
    """upto(포함)까지의 RSI·ATR(% of 종가). 최근 120거래일, **한 출처로만** 계산한다.
    네이버 일봉은 이후 액면분할·유증까지 반영한 수정주가라 KRX 원주가와 섞으면 날짜 사이에 가짜 급등락이 생긴다
    (백테스트 v1 실측: 이렘 2024 ATR 3,184원 vs 종가 1,483원 → 손절선 음수). 네이버 원값(n_*)이 충분하면 그것만,
    아니면(상장폐지 등) 저장된 가격만. ATR 은 % 로 돌려 진입가(KRX 원주가)에 곱한다 — 출처 간 배율 차이와 무관."""
    hist = [r for r in rows if r["bas_dd"] <= upto][-120:]
    nav = [{"bas_dd": r["bas_dd"], "close": r["n_close"], "high": r["n_high"], "low": r["n_low"]}
           for r in hist if r.get("n_close")]
    src, ser = ("naver", nav) if len(nav) >= S2_ATR_N + 1 else ("stored", hist)
    a = atr(ser)
    last = ser[-1]["close"] if ser else None
    return {"asof": ser[-1]["bas_dd"] if ser else None, "src": src, "rsi": rsi([r["close"] for r in ser]),
            "atr_pct": round(a / last * 100, 2) if a and last else None,
            "close": hist[-1]["close"] if hist else None}


def stop_price(entry: float | None, atr_pct: float | None) -> int | None:
    """손절선 = 진입가 − ATR × 2 (ATR 은 % → 진입가 기준 원화)."""
    return round(entry * (1 - S2_ATR_MULT * atr_pct / 100)) if entry and atr_pct else None


# ---- 전략 2 평가 (가상 성과·백테스트 공통) ----
INDEX_OF = {"Y": "KOSPI", "K": "KOSDAQ"}


def eval_s2(conn: sqlite3.Connection, code: str, market: str | None, listing: str | None) -> dict | None:
    """상장일 종가 진입 → +5 / +10거래일. 손절선(진입가 − ATR×2)을 치면 그날 청산
    (시가가 이미 손절선 밑이면 시가, 아니면 손절가). 상장일 시세가 없으면 None."""
    if not listing:
        return None
    rows = _stock(conn, code)
    i = next((k for k, r in enumerate(rows) if r["bas_dd"] == listing), None)
    if i is None:
        return None
    ind = indicators(rows, listing)
    entry = rows[i]["close"]
    stop = stop_price(entry, ind["atr_pct"])
    idx = {r["bas_dd"]: r["close"] for r in conn.execute(
        "SELECT bas_dd, close FROM index_daily WHERE idx=?", (INDEX_OF.get(market or "", "KOSPI"),))}
    out = {"entry": entry, "entry_date": listing, "rsi": ind["rsi"], "atr_pct": ind["atr_pct"], "ind_src": ind["src"],
           "atr": round(entry * ind["atr_pct"] / 100, 1) if ind["atr_pct"] else None, "stop": stop,
           "gate": None if ind["rsi"] is None else ind["rsi"] <= S2_RSI_MAX, "points": []}
    stopped = None
    for n in range(1, S2_HOLD_DAYS + 1):
        if i + n >= len(rows):
            break
        r = rows[i + n]
        if stopped is None and stop and r["low"] and r["low"] <= stop:
            stopped = {"date": r["bas_dd"], "price": r["open"] if r["open"] and r["open"] <= stop else stop}
        if n in (5, S2_HOLD_DAYS):
            px, d = (stopped["price"], stopped["date"]) if stopped else (r["close"], r["bas_dd"])
            pt = {"label": f"+{n}일", "date": r["bas_dd"], "price": px, "ret": round((px / entry - 1) * 100, 1)}
            if stopped:
                pt["stopped"] = stopped["date"]
            b, e = idx.get(listing), idx.get(d)
            if b and e:
                pt["excess"] = round(pt["ret"] - (e / b - 1) * 100, 1)
            out["points"].append(pt)
    done = {p["label"] for p in out["points"]}
    for n in (5, S2_HOLD_DAYS):
        if f"+{n}일" not in done:
            out["points"].append({"label": f"+{n}일", "pending":
                                  f"대기 중 ({shift_business_days(date.fromisoformat(listing), n).isoformat()})"})
    out["points"].sort(key=lambda p: int(p["label"][1:-1]))
    return out


# ---- 카드 (export) ----
def _state(today: str, a: str | None, b: str | None) -> str:
    if not a:
        return "wait"
    return "wait" if today < a else "live" if today <= (b or a) else "past"


def card(conn: sqlite3.Connection, c: sqlite3.Row, sch: dict, summary: dict, op_income: int | None,
         gap: float | None, today: date, verdict: str | None = None) -> dict:
    """카드 최상단 전략 배지. state: live(지금 해당) / wait(조건 충족, 시점 전) / past(시점 지남)."""
    t = today.isoformat()
    debt = (summary.get("purpose_pct") or {}).get("채무상환", 0.0)
    cond = conditions(summary.get("dilution_ratio"), debt, op_income, gap, verdict)
    items = []
    rs, re_ = sch.get("rights_start"), sch.get("rights_end") or sch.get("rights_start")
    listing = sch.get("listing_date")
    for k in ("s1", "s3"):
        if cond["ok"][k]:
            it = {"key": k, "state": _state(t, rs, re_), "window": [rs, re_]}
            if k == "s3" and listing:
                it["exit_by"] = shift_business_days(date.fromisoformat(listing), S3_EXIT_DAYS).isoformat()
            items.append(it)
    if cond["ok"]["s2"]:
        it = {"key": "s2"}
        if listing:
            ld = date.fromisoformat(listing)
            a = shift_business_days(ld, -S2_SHOW_BEFORE).isoformat()
            b = shift_business_days(ld, S2_HOLD_DAYS).isoformat()
            it.update(state=_state(t, a, b), window=[a, b], listing=listing, exit_on=b)
            rows = _stock(conn, c["stock_code"]) if c["stock_code"] else []
            on_listing = next((r for r in rows if r["bas_dd"] == listing), None)
            ind = indicators(rows, listing if on_listing else t)
            entry = on_listing["close"] if on_listing else None
            base_px = entry or ind["close"]
            it.update(entry=entry, rsi=ind["rsi"], atr_pct=ind["atr_pct"], ind_asof=ind["asof"], ind_src=ind["src"],
                      atr=round(base_px * ind["atr_pct"] / 100, 1) if base_px and ind["atr_pct"] else None,
                      confirmed=bool(on_listing), stop=stop_price(base_px, ind["atr_pct"]),
                      stop_basis="상장일 종가" if on_listing else "최근 종가(미리보기)",
                      gate=None if ind["rsi"] is None else ind["rsi"] <= S2_RSI_MAX)
        else:
            it.update(state="wait", window=[None, None])
        items.append(it)
    order = {"live": 0, "wait": 1, "past": 2}
    items.sort(key=lambda x: (order[x["state"]], x["key"]))
    ban = None
    if cond["bans"] and (not items or "dilution" in cond["bans"]):
        ban = cond["bans"]
        items = [] if "dilution" in cond["bans"] else items
    rank = 0 if any(x["state"] == "live" for x in items) else 1 if items else 2 if ban else 3
    return {"items": items, "bans": cond["bans"], "ban": ban, "rank": rank, "gap": gap}


# ---- 가상 성과 기록 ----
def _has(conn, case_id: int, key: str) -> bool:
    return conn.execute("SELECT 1 FROM strategy_trades WHERE case_id=? AND strategy=?", (case_id, key)).fetchone() is not None


def _insert(conn, case_id: int, key: str, decided_on: str, snap: dict) -> None:
    conn.execute("INSERT INTO strategy_trades (case_id, strategy, decided_on, strategy_version, snapshot_json, "
                 "created_at) VALUES (?,?,?,?,?,?)",
                 (case_id, key, decided_on, STRATEGY_VERSION, db.dumps(snap), db.now()))


def record_if_due(conn: sqlite3.Connection, c: sqlite3.Row, sch: dict, live: dict, op_income: int | None,
                  backfilled: bool) -> int:
    """전략별 스냅샷 (한 번만, 불변). s1·s3 = 인수권 마지막 날, s2 = 신주 상장일 종가."""
    from .paper import rights_last_day, rights_rows
    n = 0
    sm = live["summary"]
    debt = (sm.get("purpose_pct") or {}).get("채무상환", 0.0)
    rows = rights_rows(conn, c)
    last = rights_last_day(sch, rows)
    row = next((r for r in rows if r["bas_dd"] == last), None)
    if last and row is not None:
        gap = live["gap_on"].get(last)
        ok = conditions(sm.get("dilution_ratio"), debt, op_income, gap)["ok"]
        for k in ("s1", "s3"):
            if ok[k] and not _has(conn, c["case_id"], k):
                _insert(conn, c["case_id"], k, last, {
                    "gap": gap, "rights_close": row["close"], "issue_price": sch.get("issue_price") or row["issue_price"],
                    "stock_close": live["stock_on"].get(last), "listing_date": sch.get("listing_date"),
                    "dilution": sm.get("dilution_ratio"), "debt_pct": debt, "op_income": op_income,
                    "market": c["corp_cls"], "backfilled": backfilled})
                n += 1
    listing = sch.get("listing_date")
    if listing and not _has(conn, c["case_id"], "s2"):
        # 판정 = 인수권 마지막 날 확정 스냅샷(있으면), 없으면 현재 판정
        pt = conn.execute("SELECT verdict FROM paper_trades WHERE case_id=?", (c["case_id"],)).fetchone()
        verdict = pt[0] if pt else live.get("verdict")
        ok = conditions(sm.get("dilution_ratio"), debt, op_income, None, verdict)["ok"]
        ev = eval_s2(conn, c["stock_code"], c["corp_cls"], listing) if ok["s2"] else None
        if ev:
            _insert(conn, c["case_id"], "s2", listing, {
                "entry": ev["entry"], "rsi": ev["rsi"], "atr": ev["atr"], "stop": ev["stop"], "gate": ev["gate"],
                "verdict": verdict,
                "listing_date": listing, "dilution": sm.get("dilution_ratio"), "debt_pct": debt,
                "op_income": op_income, "market": c["corp_cls"], "backfilled": backfilled})
            n += 1
    conn.commit()
    return n


def evaluate(conn: sqlite3.Connection, c: sqlite3.Row, trade: sqlite3.Row, sch: dict, today: date) -> dict:
    """전략 기록 하나의 현재 성과. s1·s3 는 paper.evaluate(인수권+발행가 원금) 재사용."""
    from . import paper
    snap = json.loads(trade["snapshot_json"])
    key = trade["strategy"]
    if key == "s2":
        ev = eval_s2(conn, c["stock_code"], c["corp_cls"], trade["decided_on"]) or {"points": []}
        ev["exit_label"] = f"+{S2_HOLD_DAYS}일"
        return ev
    fake = {"verdict": "blue" if key == "s1" else "white", "decided_on": trade["decided_on"],
            "snapshot_json": db.dumps({"rights_close": snap["rights_close"], "issue_price": snap["issue_price"],
                                       "listing_date": snap.get("listing_date")})}
    ev = paper.evaluate(conn, c, fake, sch, today)
    ev["exit_label"] = STRATEGIES[key]["point"]
    return ev


def exit_point(ev: dict) -> dict:
    return next((p for p in ev.get("points", []) if p.get("label") == ev.get("exit_label")), {})


def scorecard(results: list[dict]) -> list[dict]:
    """전략별 실전 성적 (청산 시점). results: [{strategy, eval}]. s1 승률 = 매도가 유리했던 비율(ret < 0)."""
    out = []
    for k, s in STRATEGIES.items():
        mine = [r for r in results if r["strategy"] == k]
        rets = [p["ret"] for p in (exit_point(r["eval"]) for r in mine) if p.get("ret") is not None]
        win = (sum(x < 0 for x in rets) if s["win"] == "sell" else sum(x > 0 for x in rets))
        out.append({"strategy": k, "n": len(mine), "done": len(rets), "point": s["point"],
                    "win_rate": round(win / len(rets) * 100) if rets else None,
                    "median": round(median(rets), 1) if rets else None,
                    "worst": (max(rets) if s["win"] == "sell" else min(rets)) if rets else None})
    return out
