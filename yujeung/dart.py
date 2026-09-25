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
        self._get = http_get or requests.get
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
