"""외부 API 호출 재시도. 실측 2026-09-26 01:53: opendart 연결 시간 초과 한 번에 daily 전체가 실패했다."""
from __future__ import annotations

import time
from typing import Callable

import requests

RETRY_WAITS = (5, 20)     # 연결 실패·시간 초과면 5초, 20초 쉬고 다시 (총 3번)


def retrying(get: Callable[..., requests.Response], waits: tuple = RETRY_WAITS,
             sleep: Callable[[float], None] = time.sleep) -> Callable[..., requests.Response]:
    """연결 오류·시간 초과만 재시도한다 (HTTP 오류 응답·잘못된 키는 바로 올려보냄)."""
    def call(*args, **kwargs):
        for wait in (*waits, None):
            try:
                return get(*args, **kwargs)
            except (requests.ConnectionError, requests.Timeout) as e:
                if wait is None:
                    raise
                print(f"[retry] {type(e).__name__} — {wait}초 뒤 다시", flush=True)
                sleep(wait)
    return call
