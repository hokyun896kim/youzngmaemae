"""네이버 금융 일봉 (fchart). 본주·지수의 긴 일봉을 한 번에 받는다 — 52주 위치, 상장 후 수익률, 지수 대비 초과수익용.
pykrx 의 OHLCV 도 같은 곳에서 받는다(KR-hegemony 가 Actions 에서 사용 중). 검증 상태는 docs/verification.md.

응답 예: <item data="20260923|3300|3400|3280|3335|123456" />  (날짜|시가|고가|저가|종가|거래량)
"""
from __future__ import annotations

import re
from typing import Callable

import requests

URL = "https://fchart.stock.naver.com/sise.nhn"
INDEX_SYMBOL = {"Y": "KOSPI", "K": "KOSDAQ"}
_ITEM_RE = re.compile(r'data="([^"]+)"')


class NaverError(RuntimeError):
    pass


def parse_items(text: str) -> list[dict]:
    out = []
    for raw in _ITEM_RE.findall(text):
        parts = raw.split("|")
        if len(parts) < 5 or not re.fullmatch(r"\d{8}", parts[0]):
            continue
        d = parts[0]
        try:
            o, h, lo, c = (float(x) for x in parts[1:5])
        except ValueError:
            continue
        vol = int(float(parts[5])) if len(parts) > 5 and parts[5] else None
        out.append({"date": f"{d[:4]}-{d[4:6]}-{d[6:]}", "open": o, "high": h, "low": lo, "close": c, "volume": vol})
    return out


class NaverClient:
    def __init__(self, http_get: Callable[..., requests.Response] | None = None):
        self._get = http_get or requests.get

    def daily(self, symbol: str, count: int = 400) -> list[dict]:
        resp = self._get(URL, params={"symbol": symbol, "timeframe": "day", "count": count, "requestType": 0},
                         headers={"User-Agent": "Mozilla/5.0 yujeung-collector"}, timeout=20)
        if resp.status_code != 200:
            raise NaverError(f"naver {symbol}: HTTP {resp.status_code}")
        rows = parse_items(resp.content.decode("euc-kr", "replace"))
        if not rows:
            raise NaverError(f"naver {symbol}: 빈 응답")
        return rows
