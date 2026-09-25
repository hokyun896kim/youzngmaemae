"""SQLite → data/site.json (index.html 이 읽는 파일)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from . import db
from .detect import summarize_fields
from .pipeline import SCHEDULE_LABELS, latest_schedule
from .prices import compute_gap


def _case_json(conn: sqlite3.Connection, c: sqlite3.Row) -> dict:
    first = conn.execute("SELECT fields_json FROM disclosures WHERE rcept_no=?", (c["first_rcept_no"],)).fetchone()
    fields = json.loads(first["fields_json"] or "{}") if first else {}
    history = []
    for d in conn.execute(
        "SELECT d.rcept_no, d.report_nm, d.rcept_dt, d.kind, s.* FROM disclosures d "
        "LEFT JOIN schedule_versions s USING (rcept_no) WHERE d.case_id=? ORDER BY d.rcept_no", (c["case_id"],)
    ):
        history.append({
            "rcept_no": d["rcept_no"], "report_nm": d["report_nm"], "rcept_dt": d["rcept_dt"], "kind": d["kind"],
            "schedule": {k: d[k] for k in SCHEDULE_LABELS if d[k] is not None},
            "warnings": json.loads(d["warnings_json"] or "[]"),
        })
    series = []
    for r in conn.execute(
        "SELECT r.bas_dd, r.isu_nm, r.close, r.issue_price, r.tar_price, s.close AS s_close FROM rights_daily r "
        "LEFT JOIN stock_daily s ON s.bas_dd=r.bas_dd AND s.code=r.tar_code "
        "WHERE r.case_id=? OR (r.tar_code=? AND r.bas_dd>=?) ORDER BY r.bas_dd",
        (c["case_id"], c["stock_code"], f"{c['first_rcept_dt'][:4]}-{c['first_rcept_dt'][4:6]}-{c['first_rcept_dt'][6:]}"),
    ):
        stock = r["s_close"] or r["tar_price"]
        g = compute_gap(r["close"], stock, r["issue_price"])
        series.append({"d": r["bas_dd"], "name": r["isu_nm"], "rights": r["close"], "stock": stock,
                       "issue": r["issue_price"], "fair": g.fair if g else None, "gap": g.gap_pct if g else None})
    stock_series = [{"d": r["bas_dd"], "close": r["close"]} for r in conn.execute(
        "SELECT bas_dd, close FROM stock_daily WHERE code=? ORDER BY bas_dd", (c["stock_code"],))]
    return {
        "case_id": c["case_id"], "corp_name": c["corp_name"], "stock_code": c["stock_code"],
        "market": {"Y": "코스피", "K": "코스닥", "N": "코넥스"}.get(c["corp_cls"], c["corp_cls"]),
        "ic_mthn": c["ic_mthn"], "is_rights": bool(c["is_rights"]), "status": c["status"],
        "first_rcept_dt": c["first_rcept_dt"], "first_rcept_no": c["first_rcept_no"],
        "summary": summarize_fields(fields), "schedule": latest_schedule(conn, c["case_id"]),
        "history": history, "rights_series": series, "stock_series": stock_series,
    }


def build_site(conn: sqlite3.Connection) -> dict:
    last = conn.execute("SELECT MAX(bas_dd) FROM rights_daily").fetchone()[0]
    rights_today = []
    if last:
        for r in conn.execute(
            "SELECT r.*, s.close AS s_close FROM rights_daily r LEFT JOIN stock_daily s "
            "ON s.bas_dd=r.bas_dd AND s.code=r.tar_code WHERE r.bas_dd=? ORDER BY r.isu_nm", (last,)
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
    cases = [_case_json(conn, c) for c in conn.execute(
        "SELECT * FROM cases ORDER BY status='open' DESC, first_rcept_dt DESC LIMIT 200")]
    notes = [dict(r) for r in conn.execute(
        "SELECT seq, topic, text, sent_at, delivered FROM notifications ORDER BY seq DESC LIMIT 40")]
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("cases", "disclosures", "rights_daily", "stock_daily")}
    first_rights = conn.execute("SELECT MIN(bas_dd) FROM rights_daily").fetchone()[0]
    return {"generated_at": db.now(), "last_rights_date": last, "first_rights_date": first_rights,
            "counts": counts, "rights_today": rights_today, "cases": cases, "notifications": notes}


def write_site(conn: sqlite3.Connection, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_site(conn), ensure_ascii=False, indent=1), encoding="utf-8")
