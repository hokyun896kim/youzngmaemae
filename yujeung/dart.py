"""OpenDART 클라이언트.

엔드포인트·필드명 출처: OpenDART 개발가이드 (DS001 공시검색 2019001, 공시서류원본파일 2019003,
DS005 유상증자 결정 2020023, DS006 지분증권 2020054). docs/verification.md 참고.

주의: piicDecsn / estkRs 는 corp_code 가 **필수**라서 전 종목 감시에 직접 못 쓴다.
→ list.json(주요사항보고, 3개월 이내)으로 "유상증자결정" 보고서를 먼저 찾고, 회사별로 상세 조회.
"""
from __future__ import annotations

import io
import json
import sqlite3
import time
import zipfile
from typing import Any, Callable

import requests

from .http import retrying

from . import db

BASE = "https://opendart.fss.or.kr/api"

STATUS_OK = "000"
STATUS_NO_DATA = "013"


class DartError(RuntimeError):
    def __init__(self, status: str, message: str):
        super().__init__(f"DART {status}: {message}")
        self.status = status


def to_int(value: Any) -> int | None:
    """'1,234' / '-' / '' → int | None"""
    if value is None:
        return None
    s = str(value).replace(",", "").strip()
    if s in ("", "-"):
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


class DartClient:
    def __init__(
        self,
        api_key: str,
        conn: sqlite3.Connection | None = None,
        http_get: Callable[..., requests.Response] | None = None,
        min_interval: float = 0.3,
    ):
        if not api_key:
            raise ValueError("DART_API_KEY 가 없습니다 (.env 확인)")
        self.api_key = api_key
        self.conn = conn
        self._get = retrying(http_get or requests.get)
        self._min_interval = min_interval
        self._last = 0.0

    # ---- 저수준 ----
    def _request(self, path: str, params: dict) -> requests.Response:
        wait = self._min_interval - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        resp = self._get(f"{BASE}/{path}", params={"crtfc_key": self.api_key, **params}, timeout=30)
        resp.raise_for_status()
        return resp

    def _json(self, path: str, params: dict) -> dict:
        resp = self._request(path, params)
        if self.conn is not None:
            key = json.dumps(params, ensure_ascii=False, sort_keys=True)
            db.save_raw(self.conn, f"dart.{path}", key, resp.content)
        data = resp.json()
        status = data.get("status")
        if status not in (STATUS_OK, STATUS_NO_DATA):
            raise DartError(status, data.get("message", ""))
        return data

    # ---- 공시검색 ----
    def search(self, bgn_de: str, end_de: str, pblntf_ty: str = "B", **extra) -> list[dict]:
        """공시검색 전체 페이지. corp_code 없이 부르면 기간은 3개월 이내여야 한다."""
        items: list[dict] = []
        page = 1
        while True:
            data = self._json(
                "list.json",
                {"bgn_de": bgn_de, "end_de": end_de, "pblntf_ty": pblntf_ty,
                 "page_no": page, "page_count": 100, **extra},
            )
            items.extend(data.get("list", []))
            if page >= int(data.get("total_page") or 1):
                return items
            page += 1

    # ---- 주요사항보고서: 유상증자 결정 ----
    def piic_decisions(self, corp_code: str, bgn_de: str, end_de: str) -> list[dict]:
        data = self._json("piicDecsn.json", {"corp_code": corp_code, "bgn_de": bgn_de, "end_de": end_de})
        return data.get("list", [])

    # ---- 증권신고서: 지분증권 (그룹 응답) ----
    def equity_registrations(self, corp_code: str, bgn_de: str, end_de: str) -> dict[str, list[dict]]:
        data = self._json("estkRs.json", {"corp_code": corp_code, "bgn_de": bgn_de, "end_de": end_de})
        groups = data.get("group") or []
        if isinstance(groups, dict):
            groups = [groups]
        return {g.get("title", ""): g.get("list", []) for g in groups}

    # ---- 재무: 직전 분기 영업이익 ----
    def statement(self, corp_code: str, year: int, reprt_code: str, fs_div: str) -> list[dict]:
        """단일회사 전체 재무제표 (fnlttSinglAcntAll). KR-hegemony 에서 쓰는 것과 같은 API."""
        data = self._json("fnlttSinglAcntAll.json", {"corp_code": corp_code, "bsns_year": str(year),
                                                      "reprt_code": reprt_code, "fs_div": fs_div})
        return data.get("list", [])

    def _op_income(self, corp_code: str, year: int, reprt: str, label: str) -> tuple[int, str] | None:
        """한 보고서의 영업이익(3개월). 사업보고서면 4분기 = 연간 − 3분기 누적."""
        for fs in ("CFS", "OFS"):
            try:
                rows = self.statement(corp_code, year, reprt, fs)
            except DartError:
                rows = []
            if not rows:
                continue
            if reprt == "11011":
                annual = pick_account(rows, OP_IDS, OP_NM, ["thstrm_amount"])
                q3 = None
                try:
                    q3_rows = self.statement(corp_code, year, "11014", fs)
                    q3 = pick_account(q3_rows, OP_IDS, OP_NM, ["thstrm_add_amount"])
                except DartError:
                    pass
                if annual is not None:
                    if q3 is not None:
                        return int(annual - q3), f"{year} 4분기(연간−3분기누적, {fs})"
                    return int(annual), f"{year} 연간({fs})"
            else:
                v = pick_account(rows, OP_IDS, OP_NM, ["thstrm_amount"])
                if v is not None:
                    return int(v), f"{year} {label}(3개월, {fs})"
        return None

    def latest_op_income(self, corp_code: str, today) -> tuple[int, str] | None:
        """가장 최근에 공시된 분기의 영업이익(3개월)과 그 기간 라벨.
        분기·반기보고서 손익계산서의 thstrm_amount 는 해당 3개월 금액, 사업보고서는 연간 금액(→ 4분기 = 연간 − 3분기 누적)."""
        tries = [(today.year, "11014", "3분기"), (today.year, "11012", "반기"), (today.year, "11013", "1분기"),
                 (today.year - 1, "11011", "4분기"), (today.year - 1, "11014", "3분기")]
        for year, reprt, label in tries:
            res = self._op_income(corp_code, year, reprt, label)
            if res:
                return res
        return None

    def op_income_asof(self, corp_code: str, asof, max_tries: int = 3) -> tuple[int, str] | None:
        """백테스트용: asof 날짜에 '이미 공시돼 있던' 마지막 보고서의 영업이익 (미래 정보 금지).
        실제 제출일 대신 법정 제출기한(분기말+45일, 사업보고서 다음 해 3/31)으로 판단 — 보수적."""
        return next((r for r in (self._op_income(corp_code, y, reprt, label)
                                 for _, y, reprt, label in reports_available(asof)[:max_tries]) if r), None)

    # ---- 원문 ----
    def document(self, rcept_no: str) -> dict[str, str]:
        """공시서류원본파일(zip) → {파일명: 본문 텍스트}"""
        resp = self._request("document.xml", {"rcept_no": rcept_no})
        content = resp.content
        if self.conn is not None:
            db.save_raw(self.conn, "dart.document", rcept_no, content)
        if not content.startswith(b"PK"):
            # 오류면 zip 대신 XML/JSON 메시지가 온다
            raise DartError("doc", content[:200].decode("utf-8", "replace"))
        return unzip_document(content)


# 분기·반기보고서 법정 제출기한 (분기 말 + 45일). 사업보고서는 다음 해 3/31 (결산 후 90일)
REPORT_DEADLINES = (("11013", "1분기", 5, 15), ("11012", "반기", 8, 14), ("11014", "3분기", 11, 14))


def reports_available(asof) -> list[tuple]:
    """asof 날짜까지 제출기한이 지난 보고서들 [(기한, 사업연도, reprt_code, 라벨)] — 최근 것부터."""
    from datetime import date
    out = []
    for y in (asof.year, asof.year - 1, asof.year - 2):
        for reprt, label, m, d in REPORT_DEADLINES:
            if date(y, m, d) <= asof:
                out.append((date(y, m, d), y, reprt, label))
        if date(y + 1, 3, 31) <= asof:
            out.append((date(y + 1, 3, 31), y, "11011", "4분기"))
    return sorted(out, reverse=True)


# 영업이익 계정 식별 (KR-hegemony dart.py 와 동일)
OP_IDS = {"dart_OperatingIncomeLoss", "ifrs-full_OperatingIncomeLoss",
          "ifrs-full_ProfitLossFromOperatingActivities"}
OP_NM = ("영업이익", "영업이익(손실)")


def pick_account(rows: list[dict], ids: set[str], nms: tuple, fields: list[str]) -> float | None:
    """손익계산서(IS/CIS) 행에서 계정을 찾아 fields 우선순위대로 첫 숫자."""
    def grab(r):
        for fld in fields:
            v = to_int(r.get(fld))
            if v is not None:
                return float(v)
        return None
    for r in rows:
        if r.get("sj_div") in ("IS", "CIS") and r.get("account_id") in ids:
            v = grab(r)
            if v is not None:
                return v
    for r in rows:
        if r.get("sj_div") in ("IS", "CIS") and any(k in (r.get("account_nm") or "").replace(" ", "") for k in nms):
            v = grab(r)
            if v is not None:
                return v
    return None


def unzip_document(content: bytes) -> dict[str, str]:
    out: dict[str, str] = {}
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        for name in zf.namelist():
            raw = zf.read(name)
            for enc in ("utf-8", "euc-kr", "cp949"):
                try:
                    out[name] = raw.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                out[name] = raw.decode("utf-8", "replace")
    return out
