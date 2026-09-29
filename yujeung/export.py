"""SQLite → data/site.json (index.html 이 읽는 파일)."""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

from . import db, estimate, paper, strategy
from .backtest import load_card_scenarios
from .calendar_kr import KRX_HOLIDAYS, prev_business_day
from .config import Config
from .pipeline import SCHEDULE_LABELS, checked_schedule, latest_facts, latest_schedule, live_verdict
from .prices import compute_gap
from .verdict import VERDICTS, unconfirmed


def _history(conn: sqlite3.Connection, case_id: int) -> list[dict]:
    out = []
    for d in conn.execute(
        "SELECT d.rcept_no, d.report_nm, d.rcept_dt, d.kind, s.* FROM disclosures d "
        "LEFT JOIN schedule_versions s USING (rcept_no) WHERE d.case_id=? ORDER BY d.rcept_no", (case_id,)
    ):
        out.append({
            "rcept_no": d["rcept_no"], "report_nm": d["report_nm"], "rcept_dt": d["rcept_dt"], "kind": d["kind"],
            "schedule": {k: d[k] for k in SCHEDULE_LABELS if d[k] is not None},
            "warnings": json.loads(d["warnings_json"] or "[]"),
        })
    return out


def _case_json(conn: sqlite3.Connection, c: sqlite3.Row, cfg: Config, today: date) -> dict:
    sch, sch_warn = checked_schedule(conn, c["case_id"])
    base = {
        "case_id": c["case_id"], "corp_name": c["corp_name"], "stock_code": c["stock_code"],
        "market": {"Y": "코스피", "K": "코스닥"}.get(c["corp_cls"], c["corp_cls"]),
        "ic_mthn": c["ic_mthn"], "is_rights": bool(c["is_rights"]), "status": c["status"],
        "first_rcept_dt": c["first_rcept_dt"], "first_rcept_no": c["first_rcept_no"],
        "schedule": sch, "schedule_warnings": sch_warn, "history": _history(conn, c["case_id"]),
    }
    if not c["is_rights"]:
        first = conn.execute("SELECT fields_json FROM disclosures WHERE rcept_no=?", (c["first_rcept_no"],)).fetchone()
        from .detect import summarize_fields
        base["summary"] = summarize_fields(json.loads(first[0] or "{}") if first else {})
        return base

    live = live_verdict(conn, c, cfg)
    series = []
    r_rows = paper.rights_rows(conn, c)
    for r in r_rows:
        s_row = conn.execute("SELECT close FROM stock_daily WHERE bas_dd=? AND code=?",
                             (r["bas_dd"], c["stock_code"])).fetchone()
        stock = (s_row[0] if s_row else None) or r["tar_price"]
        g = compute_gap(r["close"], stock, r["issue_price"] or sch.get("issue_price"))
        series.append({"d": r["bas_dd"], "name": r["isu_nm"], "rights": r["close"], "stock": stock,
                       "issue": r["issue_price"], "fair": g.fair if g else None, "gap": g.gap_pct if g else None,
                       "cost": g.effective_cost if g else None, "disc": g.discount_pct if g else None})
    stock_series = [{"d": r["bas_dd"], "close": r["close"], "price_type": strategy.price_type(r["bas_dd"], today)}
                    for r in conn.execute(
        "SELECT bas_dd, close FROM stock_daily WHERE code=? ORDER BY bas_dd DESC LIMIT 30", (c["stock_code"],))][::-1]
    f = conn.execute("SELECT * FROM case_facts WHERE case_id=?", (c["case_id"],)).fetchone()

    trade = conn.execute("SELECT * FROM paper_trades WHERE case_id=?", (c["case_id"],)).fetchone()
    paper_json = None
    if trade:
        snap = json.loads(trade["snapshot_json"])
        paper_json = {"verdict": trade["verdict"], "decided_on": trade["decided_on"],
                      "logic_version": trade["logic_version"], "snapshot": snap,
                      "eval": paper.evaluate(conn, c, trade, sch, today)}
    v = trade["verdict"] if trade else live["verdict"]
    emoji, name = VERDICTS[v]
    daily = conn.execute("SELECT bas_dd, close, volume, value FROM stock_daily WHERE code=? AND close IS NOT NULL "
                         "AND bas_dd <= ? ORDER BY bas_dd DESC LIMIT 300",
                         (c["stock_code"], today.isoformat())).fetchall()[::-1]
    confirmed = sch.get("issue_kind") == "확정"   # 확정발행가 라벨 또는 확정 산정일 이후 공시
    quick = estimate.quick(
        v, live["gate1"], live["gap"], sch, latest_facts(conn, c["case_id"]),
        [(r["bas_dd"], r["close"]) for r in daily],
        [r["volume"] for r in daily if not sch.get("listing_date") or r["bas_dd"] < sch["listing_date"]],
        next((x["rights"] for x in reversed(series) if x["d"] <= today.isoformat()), None), live["summary"].get("new_shares"),
        live["summary"].get("dilution_ratio"), f["op_period"] if f else None, today, confirmed,
        -cfg.gap_alert_pct, cfg.gap_alert_pct, load_card_scenarios(), live.get("disc"), [dict(r) for r in daily])
    # A 3층 분석 추이: 인수권 거래일마다 그날까지의 시세로 ① 1차가 기준 · ② 예상 최종가 기준 괴리를 다시 계산
    if not confirmed:
        facts_now = latest_facts(conn, c["case_id"])
        r_ = live["summary"].get("dilution_ratio") or sch.get("alloc_ratio")
        for x in series:
            if not x["rights"] or not x["stock"]:
                continue
            upto = [r for r in daily if r["bas_dd"] <= x["d"]]
            est = estimate.issue_estimate(sch, facts_now.get("discount"), r_, [(r["bas_dd"], r["close"]) for r in upto],
                                          date.fromisoformat(x["d"]), False, [dict(r) for r in upto])
            if est.get("kind") == "최종 추정" and est.get("value") and x["stock"] > est["value"]:
                x["i_hat"] = est["value"]
                x["gap_hat"] = round((x["rights"] / (x["stock"] - est["value"]) - 1) * 100, 1)
    # A = 인수권 할인 포착: 같은 날의 인수권·본주 KRX 종가로 총원가 쿠션 · ATR(10) 쿠션 (인수권 시세 전이면 최근 본주 종가만)
    last_r = next((x for x in reversed(series) if x["rights"] and x["d"] <= today.isoformat()), None)
    p_now, p_date = (last_r["stock"], last_r["d"]) if last_r else \
        ((daily[-1]["close"], daily[-1]["bas_dd"]) if daily else (None, None))
    ind = strategy.indicators(strategy._stock(conn, c["stock_code"]), p_date, estimate.A_ATR_N) if p_date else {}
    # 매매종료일(마지막 매매가능일) ≠ KRX 상장폐지일 — 발행회사 공시와 KRX(상장폐지일 전 영업일)를 대조
    end_check = estimate.rights_end_check(sch.get("rights_end"),
                                          next((r["delist_dd"] for r in reversed(r_rows) if r["delist_dd"]), None))
    if end_check and end_check["status"] == "mismatch":
        sch_warn = [*sch_warn, f"인수권 매매종료일 불일치: 공시 {end_check['disclosed']} vs KRX 상장폐지일 "
                               f"{end_check['delist']} 전 영업일 {end_check['krx_last']} — 원문·KRX 확인"]
        base["schedule_warnings"] = sch_warn
    # A 의사결정값은 반드시 P/R 날짜 당시 공개돼 있던 공시와 시세만 사용한다.
    # 최신 확정발행가를 과거 인수권 마지막 날에 소급하면 룩어헤드 바이어스가 생긴다.
    decision_sch = latest_schedule(conn, c["case_id"], as_of=p_date) if p_date else sch
    decision_facts = latest_facts(conn, c["case_id"], as_of=p_date) if p_date else latest_facts(conn, c["case_id"])
    daily_asof = [r for r in daily if not p_date or r["bas_dd"] <= p_date]
    decision_r = live["summary"].get("dilution_ratio") or decision_sch.get("alloc_ratio")
    decision_confirmed = decision_sch.get("issue_kind") == "확정"
    decision_issue = estimate.issue_estimate(
        decision_sch, decision_facts.get("discount"), decision_r,
        [(r["bas_dd"], r["close"]) for r in daily_asof],
        date.fromisoformat(p_date) if p_date else today, decision_confirmed, [dict(r) for r in daily_asof]
    )
    realized_issue = quick["issue"] if quick["issue"].get("kind") == "확정" and not decision_confirmed else None
    a_margin = estimate.a_margin(
        decision_sch, decision_issue, p_now, p_date, last_r["rights"] if last_r else None,
        last_r["d"] if last_r else None, ind.get("atr_pct"), today, end_check,
        current_sch=sch, realized_issue=realized_issue
    )
    lst = sch.get("listing_date")
    lst_bar = next((dict(r) for r in daily if r["bas_dd"] == lst), None) if lst else None
    supply = estimate.supply(
        live["summary"].get("new_shares"), live["summary"].get("dilution_ratio"), p_now,
        [(r["close"], r["volume"]) for r in daily if not lst or r["bas_dd"] < lst],
        listing_bar=lst_bar, listing_price_type=(strategy.price_type(lst, today) if lst_bar else None)
    )
    trade_v = conn.execute("SELECT verdict FROM paper_trades WHERE case_id=?", (c["case_id"],)).fetchone()
    strat = strategy.card(conn, c, sch, live["summary"], f["op_income"] if f else None, live["gap"], today,
                          trade_v[0] if trade_v else live["verdict"])
    strat["paper"] = [{"strategy": t["strategy"], "decided_on": t["decided_on"], "version": t["strategy_version"],
                       "snapshot": json.loads(t["snapshot_json"]), "eval": strategy.evaluate(conn, c, t, sch, today)}
                      for t in conn.execute("SELECT * FROM strategy_trades WHERE case_id=? ORDER BY strategy",
                                            (c["case_id"],))]
    base.update({
        "strategy": strat,
        "summary": live["summary"], "gate1": live["gate1"], "rights_series": series, "stock_series": stock_series,
        "facts": {"op_income": f["op_income"] if f else None, "op_period": f["op_period"] if f else None,
                  "pos52": f["pos52"] if f else None, "pos52_basis": f["pos52_basis"] if f else None},
        "verdict": {"code": v, "emoji": emoji, "name": name,
                    "reason": json.loads(trade["snapshot_json"])["reason"] if trade else live["reason"],
                    "provisional": not trade, "decided_on": trade["decided_on"] if trade else None,
                    "live_reason": live["reason"],
                    # 🟢?/🟡? 확인 필요: 관문1 자동 항목 중 미확인 (화면 빨간 글씨 + 그 항목만 묻는 GPT 프롬프트)
                    "unconfirmed": unconfirmed(live["gate1"]) if v.endswith("_q") else []},
        "paper": paper_json, "quick": quick, "a_margin": a_margin, "supply": supply,
    })
    return base


def build_site(conn: sqlite3.Connection, cfg: Config | None = None, today: date | None = None) -> dict:
    cfg = cfg or Config.load()
    today = today or datetime.now(db.KST).date()
    last = conn.execute("SELECT MAX(bas_dd) FROM rights_daily").fetchone()[0]
    rights_today = []
    if last:
        for r in conn.execute(
            "SELECT r.*, s.close AS s_close FROM rights_daily r LEFT JOIN stock_daily s "
            "ON s.bas_dd=r.bas_dd AND s.code=substr(r.isu_cd,1,6) WHERE r.bas_dd=? ORDER BY r.isu_nm", (last,)
        ):
            stock = r["s_close"] or r["tar_price"]
            g = compute_gap(r["close"], stock, r["issue_price"])
            rights_today.append({
                "isu_cd": r["isu_cd"], "name": r["isu_nm"], "close": r["close"], "volume": r["volume"],
                "stock_code": r["tar_code"], "stock_name": r["tar_name"], "stock": stock,
                "issue": r["issue_price"], "delist": r["delist_dd"], "case_id": r["case_id"],
                # 마지막 매매일 = KRX 상장폐지일 전 영업일 (상장폐지일 ≠ 매매종료일)
                "last_trade": prev_business_day(date.fromisoformat(r["delist_dd"])).isoformat() if r["delist_dd"] else None,
                "fair": g.fair if g else None, "gap": g.gap_pct if g else None,
                "cost": g.effective_cost if g else None, "disc": g.discount_pct if g else None,
            })
    cases = [_case_json(conn, c, cfg, today) for c in conn.execute(
        "SELECT * FROM cases ORDER BY status='open' DESC, is_rights DESC, first_rcept_dt DESC LIMIT 300")]
    results = [{"verdict": c["paper"]["verdict"], "eval": c["paper"]["eval"]} for c in cases if c.get("paper")]
    s_results = [p for c in cases for p in (c.get("strategy") or {}).get("paper", [])]
    notes = [dict(r) for r in conn.execute(
        "SELECT seq, topic, text, sent_at FROM notifications ORDER BY seq DESC LIMIT 40")]
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("cases", "disclosures", "rights_daily", "stock_daily", "excluded_disclosures", "paper_trades",
                                                                             "strategy_trades")}
    first_rights = conn.execute("SELECT MIN(bas_dd) FROM rights_daily").fetchone()[0]
    return {"generated_at": db.now(), "last_rights_date": last, "first_rights_date": first_rights,
            "counts": counts, "holidays": sorted(KRX_HOLIDAYS), "gap_threshold": cfg.gap_alert_pct,
            "verdicts": {k: {"emoji": e, "name": n} for k, (e, n) in VERDICTS.items()},
            "rights_today": rights_today, "cases": cases, "scorecard": paper.scorecard(results),
            "strategy_rules": strategy.rules(), "strategy_scorecard": strategy.scorecard(s_results),
            "notifications": notes}


def write_site(conn: sqlite3.Connection, path: Path, cfg: Config | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_site(conn, cfg), ensure_ascii=False, indent=1), encoding="utf-8")
