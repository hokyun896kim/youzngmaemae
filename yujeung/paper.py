"""가상 성과 기록 ("들어갔다면?").

판정이 확정되는 순간 = 인수권 마지막 거래일 종가가 들어온 첫 실행. 그때의 판정·근거를 paper_trades 에
스냅샷으로 남기고(불변), 결과는 매 실행 때 저장된 시세로 다시 계산한다.

진입
  🟢⚪ 인수권 마지막 날 종가 + 발행가 = 신주 원가            → 수익률 = 가격 / 원가 − 1
  🟡   신주 상장일 종가로 본주 매수                          → 수익률 = 가격 / 진입가 − 1
  🔵   인수권 마지막 날 매도(R) vs 청약 유지(가격 − 발행가)  → (가격 − 발행가) / R − 1  (+면 청약 유지가 나았음)
측정
  🟢⚪🔵 신주 상장일 시가 / +5거래일 종가 / +20거래일 종가
  🟡     +5 / +10 / +20거래일 종가
지수 대비 초과수익(%p) = 수익률 − 같은 기간 지수 수익률 (코스피/코스닥)
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date

from . import db
from .calendar_kr import prev_business_day, shift_business_days
from .verdict import LOGIC_VERSION, VERDICTS, base

POINTS = {
    "rights": [("상장일 시가", "open", 0), ("+5일", "close", 5), ("+20일", "close", 20)],
    "yellow": [("+5일", "close", 5), ("+10일", "close", 10), ("+20일", "close", 20)],
}
INDEX_OF = {"Y": "KOSPI", "K": "KOSDAQ"}


def rights_rows(conn: sqlite3.Connection, case: sqlite3.Row) -> list[sqlite3.Row]:
    """이 케이스의 인수권 일별 행 (isu_cd 앞 6자리 = 본주 코드, 공시 이후)."""
    since = f"{case['first_rcept_dt'][:4]}-{case['first_rcept_dt'][4:6]}-{case['first_rcept_dt'][6:]}"
    return conn.execute(
        "SELECT * FROM rights_daily WHERE substr(isu_cd,1,6)=? AND bas_dd>=? ORDER BY bas_dd",
        (case["stock_code"], since)).fetchall()


def rights_last_day(schedule: dict, rows: list[sqlite3.Row]) -> str | None:
    """인수권 마지막 거래일: 일정의 종료일, 없으면 KRX 상장폐지일 전 영업일."""
    if schedule.get("rights_end"):
        return schedule["rights_end"]
    delist = next((r["delist_dd"] for r in reversed(rows) if r["delist_dd"]), None)
    return prev_business_day(date.fromisoformat(delist)).isoformat() if delist else None


def record_if_due(conn: sqlite3.Connection, case: sqlite3.Row, schedule: dict, live: dict, backfilled: bool) -> bool:
    """인수권 마지막 날 종가가 있으면 판정 스냅샷을 남긴다. 이미 있으면 아무것도 안 함 (불변)."""
    if conn.execute("SELECT 1 FROM paper_trades WHERE case_id=?", (case["case_id"],)).fetchone():
        return False
    rows = rights_rows(conn, case)
    last = rights_last_day(schedule, rows)
    row = next((r for r in rows if r["bas_dd"] == last), None)
    if not last or row is None:
        return False
    snap = {
        "verdict": live["verdict"], "reason": live["reason"], "gate1": live["gate1"],
        "gap": live["gap_on"].get(last), "disc": live.get("disc_on", {}).get(last), "rights_close": row["close"],
        "issue_price": schedule.get("issue_price") or row["issue_price"],
        "stock_close": live["stock_on"].get(last), "listing_date": schedule.get("listing_date"),
        "market": case["corp_cls"], "backfilled": backfilled,
    }
    # 마지막 날 괴리로 판정을 다시 확정 (라이브 판정은 최신 괴리 기준이라 다를 수 있음)
    snap["verdict"] = live["decide"](snap["gap"], snap["disc"])
    snap["reason"] = live["reason_for"](snap["gap"], snap["verdict"], snap["disc"])
    conn.execute(
        "INSERT INTO paper_trades (case_id, verdict, decided_on, logic_version, snapshot_json, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (case["case_id"], snap["verdict"], last, LOGIC_VERSION, db.dumps(snap), db.now()))
    conn.commit()
    return True


def final_issue_price(snap_issue: int | None, schedule: dict, today: date) -> tuple[int | None, str | None]:
    """청약 원가에 쓸 발행가. 청약에서 실제로 내는 돈은 확정발행가 →
    확정 공시가 있거나 청약이 시작됐으면 최신 공시 발행가를 쓴다(높든 낮든). 그 전엔 판정 당시 값."""
    latest = schedule.get("issue_price")
    started = bool(schedule.get("subs_start")) and today.isoformat() >= schedule["subs_start"]
    if latest and (schedule.get("issue_kind") == "확정" or started):
        note = None if latest == snap_issue else f"확정발행가 {latest:,} 반영 (판정 당시 {snap_issue:,})" \
            if snap_issue else f"확정발행가 {latest:,}"
        return latest, note
    return snap_issue or latest, None


def _series(conn, table: str, key_col: str, key: str) -> list[sqlite3.Row]:
    return conn.execute(f"SELECT * FROM {table} WHERE {key_col}=? ORDER BY bas_dd", (key,)).fetchall()


def evaluate(conn: sqlite3.Connection, case: sqlite3.Row, trade: sqlite3.Row, schedule: dict, today: date) -> dict:
    snap = json.loads(trade["snapshot_json"])
    verdict = trade["verdict"]
    listing = schedule.get("listing_date") or snap.get("listing_date")
    stock = _series(conn, "stock_daily", "code", case["stock_code"])
    index = _series(conn, "index_daily", "idx", INDEX_OF.get(case["corp_cls"], "KOSPI"))
    idx_by_day = {r["bas_dd"]: r for r in index}
    kind = "yellow" if base(verdict) == "yellow" else "rights"

    issue, issue_note = final_issue_price(snap.get("issue_price"), schedule, today)

    out = {"entry": None, "entry_date": None, "points": [], "issue_note": issue_note}
    listing_idx = next((i for i, r in enumerate(stock) if listing and r["bas_dd"] >= listing), None)

    if kind == "rights":
        entry_date = trade["decided_on"]
        rc = snap.get("rights_close")
        if not (rc and issue):
            out["error"] = "인수권 종가 또는 발행가 없음"
            return out
        # 분모 = 투입 원금(인수권+발행가). 🔵(인수권 매도)도 같은 원금 기준 — '팔지 않고 청약했다면'의 수익률,
        # 낮을수록 매도 판정 적중. 예전 (가격−발행가)÷인수권−1 은 가격<발행가면 −100% 밑으로 떨어졌다 (2020 최악 −214.9%)
        entry = rc + issue
        out.update(entry=entry, entry_date=entry_date,
                   entry_label="신주 원가(인수권+발행가)" if verdict != "blue"
                   else "신주 원가(인수권+발행가) · 🔵은 팔지 않았다면 — 낮을수록 적중")
    else:
        if listing_idx is None or stock[listing_idx]["bas_dd"] != listing:
            out.update(entry_label="상장일 종가", pending=f"대기 중 ({listing or '상장일 미정'})")
            entry = None
        else:
            entry = stock[listing_idx]["close"]
            out.update(entry=entry, entry_date=listing, entry_label="상장일 종가")
        entry_date = listing

    base_idx = idx_by_day.get(entry_date) if entry_date else None
    for label, field, n in POINTS[kind]:
        pt = {"label": label}
        if listing_idx is not None and listing_idx + n < len(stock) and stock[listing_idx]["bas_dd"] >= (listing or ""):
            r = stock[listing_idx + n]
            price = r[field]
            pt["date"] = r["bas_dd"]
            pt["price"] = price
            if entry and price:
                ret = (price / entry - 1) * 100      # 투입 원금 대비 — 가격 ≥ 0 이면 항상 −100% 이상
                pt["ret"] = round(ret, 1)
                ir = idx_by_day.get(r["bas_dd"])
                if base_idx and ir and base_idx["close"] and ir[field]:
                    idx_ret = (ir[field] / base_idx["close"] - 1) * 100
                    pt["idx_ret"] = round(idx_ret, 1)
                    pt["excess"] = round(ret - idx_ret, 1)
        else:
            when = shift_business_days(date.fromisoformat(listing), n).isoformat() if listing else "상장일 미정"
            pt["pending"] = f"대기 중 ({when})"
        out["points"].append(pt)
    return out


def scorecard(results: list[dict]) -> list[dict]:
    """판정별 성적 (마지막 측정 시점 = +20일 기준). results: [{verdict, eval}]"""
    rows = []
    for v in VERDICTS:          # 확인 필요(🟢?/🟡?)도 따로 집계
        mine = [r for r in results if r["verdict"] == v]
        done = [r["eval"]["points"][-1] for r in mine if r["eval"].get("points") and "ret" in r["eval"]["points"][-1]]
        rets = [p["ret"] for p in done]
        exc = [p["excess"] for p in done if "excess" in p]
        rows.append({
            "verdict": v, "n": len(mine), "done": len(done),
            "win_rate": round(sum(x > 0 for x in rets) / len(rets) * 100, 0) if rets else None,
            "avg": round(sum(rets) / len(rets), 1) if rets else None,
            "worst": min(rets) if rets else None,
            "avg_excess": round(sum(exc) / len(exc), 1) if exc else None,
        })
    return rows
