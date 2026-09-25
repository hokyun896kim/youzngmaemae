"""KRX Open API (openapi.krx.co.kr) 클라이언트.

- 인증: 요청 헤더 AUTH_KEY (KRX Open API 에서 발급 + 서비스별 이용신청 필요)
- 호출: GET https://data-dbg.krx.co.kr/svc/apis/sto/<api_id>?basDd=YYYYMMDD → {"OutBlock_1": [...]}
- sr_bydd_trd (신주인수권증서 일별매매정보, 2010-02-12~) 한 번 호출로 그날 상장된 모든 인수권 +
  발행가(ISU_PRC) + 대상 본주 코드/가격(TARSTK_*)이 함께 온다 → 괴리율 계산에 충분.

출처: KRX Open API 서비스 목록, seokhoonj/krx-openapi 카탈로그. 실측 전이라 docs/verification.md 에서 '검증 필요'.
"""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Callable

import requests

from .http import retrying

from . import db

BASE = "https://data-dbg.krx.co.kr/svc/apis"

RIGHTS_API = "sr_bydd_trd"                       # 신주인수권증서 일별매매정보
STOCK_APIS = {"Y": "stk_bydd_trd", "K": "ksq_bydd_trd", "N": "knx_bydd_trd"}   # DART corp_cls → 시장
RIGHTS_FIRST_DATE = "20100212"


class KrxError(RuntimeError):
    pass


class KrxClient:
    def __init__(
        self,
        api_key: str,
        conn: sqlite3.Connection | None = None,
        http_get: Callable[..., requests.Response] | None = None,
        min_interval: float = 0.2,
    ):
        if not api_key:
            raise ValueError("KRX_API_KEY 가 없습니다")
        self.api_key = api_key.strip()
        self.conn = conn
        self._get = retrying(http_get or requests.get)
        self._min_interval = min_interval
        self._last = 0.0

    def fetch(self, api_id: str, bas_dd: str, category: str = "sto") -> list[dict]:
        wait = self._min_interval - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        resp = self._get(
            f"{BASE}/{category}/{api_id}",
            params={"basDd": bas_dd},
            headers={"AUTH_KEY": self.api_key, "User-Agent": "yujeung-collector"},
            timeout=30,
            allow_redirects=False,   # 리다이렉트로 키가 다른 호스트에 실리는 것 방지
        )
        if resp.status_code != 200:
            raise KrxError(f"KRX {api_id} {bas_dd}: HTTP {resp.status_code} {resp.text[:200]}")
        if self.conn is not None:
            db.save_raw(self.conn, f"krx.{api_id}", bas_dd, resp.content)
        data = resp.json()
        if data.get("respCode"):
            raise KrxError(f"KRX {api_id} {bas_dd}: {data.get('respCode')} {data.get('respMsg')}")
        rows = data.get("OutBlock_1") or []
        return rows if isinstance(rows, list) else [rows]

    def rights(self, bas_dd: str) -> list[dict]:
        return self.fetch(RIGHTS_API, bas_dd)

    def stocks(self, bas_dd: str, corp_cls: str) -> list[dict]:
        return self.fetch(STOCK_APIS[corp_cls], bas_dd)


def dumps_row(row: dict) -> str:
    return json.dumps(row, ensure_ascii=False, sort_keys=True)
