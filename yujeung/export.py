"""SQLite → data/site.json (index.html 이 읽는 파일)."""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

from . import db, paper
from .calendar_kr import KRX_HOLIDAYS
from .config import Config
from .pipeline import SCHEDULE_LABELS, checked_schedule, live_verdict
from .prices import compute_gap
from .verdict import VERDICTS


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
    for r in paper.rights_rows(conn, c):
        s_row = conn.execute("SELECT close FROM stock_daily WHERE bas_dd=? AND code=?",
                             (r["bas_dd"], c["stock_code"])).fetchone()
        stock = (s_row[0] if s_row else None) or r["tar_price"]
        g = compute_gap(r["close"], stock, r["issue_price"] or sch.get("issue_price"))
        series.append({"d": r["bas_dd"], "name": r["isu_nm"], "rights": r["close"], "stock": stock,
                       "issue": r["issue_price"], "fair": g.fair if g else None, "gap": g.gap_pct if g else None,
                       "cost": g.effective_cost if g else None})
    stock_series = [{"d": r["bas_dd"], "close": r["close"]} for r in conn.execute(
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
    base.update({
        "summary": live["summary"], "gate1": live["gate1"], "rights_series": series, "stock_series": stock_series,
        "facts": {"op_income": f["op_income"] if f else None, "op_period": f["op_period"] if f else None,
                  "pos52": f["pos52"] if f else None, "pos52_basis": f["pos52_basis"] if f else None},
        "verdict": {"code": v, "emoji": emoji, "name": name,
                    "reason": json.loads(trade["snapshot_json"])["reason"] if trade else live["reason"],
                    "provisional": not trade, "decided_on": trade["decided_on"] if trade else None,
                    "live_reason": live["reason"]},
        "paper": paper_json,
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
                "fair": g.fair if g else None, "gap": g.gap_pct if g else None,
                "cost": g.effective_cost if g else None,
            })
    cases = [_case_json(conn, c, cfg, today) for c in conn.execute(
        "SELECT * FROM cases ORDER BY status='open' DESC, is_rights DESC, first_rcept_dt DESC LIMIT 300")]
    results = [{"verdict": c["paper"]["verdict"], "eval": c["paper"]["eval"]} for c in cases if c.get("paper")]
    notes = [dict(r) for r in conn.execute(
        "SELECT seq, topic, text, sent_at FROM notifications ORDER BY seq DESC LIMIT 40")]
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("cases", "disclosures", "rights_daily", "stock_daily", "excluded_disclosures", "paper_trades")}
    first_rights = conn.execute("SELECT MIN(bas_dd) FROM rights_daily").fetchone()[0]
    return {"generated_at": db.now(), "last_rights_date": last, "first_rights_date": first_rights,
            "counts": counts, "holidays": sorted(KRX_HOLIDAYS), "gap_threshold": cfg.gap_alert_pct,
            "verdicts": {k: {"emoji": e, "name": n} for k, (e, n) in VERDICTS.items()},
            "rights_today": rights_today, "cases": cases, "scorecard": paper.scorecard(results),
            "notifications": notes}


def write_site(conn: sqlite3.Connection, path: Path, cfg: Config | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_site(conn, cfg), ensure_ascii=False, indent=1), encoding="utf-8")
