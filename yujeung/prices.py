"""인수권·본주 일별 시세 적재 + 괴리율 계산."""
from __future__ import annotations

import csv
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .dart import to_int
from .krx import KrxClient


def iso(bas_dd: str) -> str:
    s = re.sub(r"\D", "", bas_dd)
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"


def short_code(code: str | None) -> str | None:
    """'A210980' / 'KR7210980009' 같은 것에서 6자리 단축코드만."""
    if not code:
        return None
    code = code.strip()
    if len(code) == 12 and code.startswith("KR"):
        return code[3:9]
    digits = re.sub(r"^[A-Z]", "", code)
    return digits[-6:] if len(digits) >= 6 else digits


def _case_for_stock(conn: sqlite3.Connection, stock_code: str | None) -> int | None:
    if not stock_code:
        return None
    row = conn.execute(
        "SELECT case_id FROM cases WHERE stock_code=? ORDER BY first_rcept_dt DESC LIMIT 1", (stock_code,)
    ).fetchone()
    return row["case_id"] if row else None


def store_rights_rows(conn: sqlite3.Connection, rows: list[dict], source: str = "krx") -> int:
    n = 0
    for r in rows:
        tar = short_code(r.get("TARSTK_ISU_SRT_CD"))
        conn.execute(
            "INSERT OR REPLACE INTO rights_daily (bas_dd, isu_cd, isu_nm, mkt_nm, close, open, high, low,"
            " volume, value, list_shrs, issue_price, delist_dd, tar_code, tar_name, tar_price, case_id, source)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (iso(r["BAS_DD"]), r["ISU_CD"], r.get("ISU_NM"), r.get("MKT_NM"),
             to_int(r.get("TDD_CLSPRC")), to_int(r.get("TDD_OPNPRC")), to_int(r.get("TDD_HGPRC")),
             to_int(r.get("TDD_LWPRC")), to_int(r.get("ACC_TRDVOL")), to_int(r.get("ACC_TRDVAL")),
             to_int(r.get("LIST_SHRS")), to_int(r.get("ISU_PRC")),
             iso(r["DELIST_DD"]) if re.sub(r"\D", "", r.get("DELIST_DD") or "") else None,
             tar, r.get("TARSTK_ISU_NM"), to_int(r.get("TARSTK_ISU_PRSNT_PRC")),
             _case_for_stock(conn, tar), source),
        )
        n += 1
    conn.commit()
    return n


def store_stock_rows(conn: sqlite3.Connection, rows: list[dict], codes: set[str]) -> int:
    n = 0
    for r in rows:
        code = short_code(r.get("ISU_CD"))
        if code not in codes:
            continue
        conn.execute(
            "INSERT OR REPLACE INTO stock_daily (bas_dd, code, name, close, open, high, low, volume, mktcap,"
            " list_shrs) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (iso(r["BAS_DD"]), code, r.get("ISU_NM"), to_int(r.get("TDD_CLSPRC")), to_int(r.get("TDD_OPNPRC")),
             to_int(r.get("TDD_HGPRC")), to_int(r.get("TDD_LWPRC")), to_int(r.get("ACC_TRDVOL")),
             to_int(r.get("MKTCAP")), to_int(r.get("LIST_SHRS"))),
        )
        n += 1
    conn.commit()
    return n


def tracked_stocks(conn: sqlite3.Connection, bas_dd: str) -> dict[str, set[str]]:
    """시장별 추적 종목: 진행 중 주주배정 케이스 + 그날 인수권의 대상 본주."""
    by_mkt: dict[str, set[str]] = {}
    for r in conn.execute("SELECT stock_code, corp_cls FROM cases WHERE status='open' AND stock_code IS NOT NULL"):
        by_mkt.setdefault(r["corp_cls"] or "Y", set()).add(r["stock_code"])
    for r in conn.execute(
        "SELECT DISTINCT tar_code, mkt_nm FROM rights_daily WHERE bas_dd=? AND tar_code IS NOT NULL", (iso(bas_dd),)
    ):
        mkt = "K" if (r["mkt_nm"] or "").startswith("KOSDAQ") or "코스닥" in (r["mkt_nm"] or "") else "Y"
        by_mkt.setdefault(mkt, set()).add(r["tar_code"])
    return by_mkt


def collect_day(krx: KrxClient, conn: sqlite3.Connection, bas_dd: str) -> dict:
    """하루치: 인수권 전체 → 추적 본주 시세. 멱등(같은 날 다시 돌려도 덮어쓰기)."""
    rights = krx.rights(bas_dd)
    n_rights = store_rights_rows(conn, rights)
    n_stock = 0
    for mkt, codes in tracked_stocks(conn, bas_dd).items():
        if mkt in ("Y", "K", "N") and codes:
            n_stock += store_stock_rows(conn, krx.stocks(bas_dd, mkt), codes)
    return {"bas_dd": bas_dd, "rights": n_rights, "stocks": n_stock}


# ---- 괴리율 ----
@dataclass
class Gap:
    bas_dd: str
    isu_nm: str
    rights_close: int
    stock_close: int
    issue_price: int
    fair: int            # 이론가 = 본주 − 발행가
    gap_pct: float       # (인수권 / 이론가 − 1) × 100. 음수 = 인수권이 싸다
    effective_cost: int  # 인수권 매수 + 청약 시 신주 원가


def compute_gap(rights_close, stock_close, issue_price, bas_dd="", isu_nm="") -> Gap | None:
    if not (rights_close and stock_close and issue_price):
        return None
    fair = stock_close - issue_price
    if fair <= 0:
        return None
    return Gap(bas_dd, isu_nm, rights_close, stock_close, issue_price, fair,
               round((rights_close / fair - 1) * 100, 1), rights_close + issue_price)


def gaps_for_day(conn: sqlite3.Connection, bas_dd: str) -> list[Gap]:
    """본주 가격은 stock_daily 종가 우선, 없으면 KRX 가 준 대상 본주 가격."""
    out = []
    for r in conn.execute(
        "SELECT r.*, s.close AS s_close FROM rights_daily r "
        "LEFT JOIN stock_daily s ON s.bas_dd=r.bas_dd AND s.code=r.tar_code WHERE r.bas_dd=?", (iso(bas_dd),)
    ):
        g = compute_gap(r["close"], r["s_close"] or r["tar_price"], r["issue_price"], r["bas_dd"], r["isu_nm"])
        if g:
            out.append(g)
    return out


def import_manual_csv(conn: sqlite3.Connection, path: Path) -> int:
    """HTS 에서 손으로 옮긴 인수권 종가. 컬럼: date,isu_nm,close,stock_code,stock_close,issue_price"""
    n = 0
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            code = row["stock_code"].strip()
            conn.execute(
                "INSERT OR REPLACE INTO rights_daily (bas_dd, isu_cd, isu_nm, close, issue_price, tar_code,"
                " tar_price, case_id, source) VALUES (?,?,?,?,?,?,?,?, 'manual')",
                (iso(row["date"]), f"MANUAL-{code}", row["isu_nm"].strip(), to_int(row["close"]),
                 to_int(row.get("issue_price")), code, to_int(row.get("stock_close")), _case_for_stock(conn, code)),
            )
            n += 1
    conn.commit()
    return n
