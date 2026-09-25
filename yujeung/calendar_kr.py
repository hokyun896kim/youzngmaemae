"""한국 증시 영업일 계산 (권리락일 추정용).

권리락일 = 신주배정기준일의 직전 영업일 (T+2 결제 기준).
휴장일 목록은 검증 필요: KRX 공식 휴장일 공지로 매년 갱신할 것. 누락 시 권리락일이 하루 틀어질 수 있어
schedule_versions.warnings_json 에 '권리락일 추정' 표시를 항상 남긴다.
"""
from __future__ import annotations

from datetime import date, timedelta

KRX_HOLIDAYS: set[str] = {
    # 2026 (검증 필요 — KRX 휴장일 공지와 대조)
    "2026-01-01", "2026-02-16", "2026-02-17", "2026-02-18", "2026-03-02",
    "2026-05-01", "2026-05-05", "2026-05-25", "2026-06-03", "2026-08-17",
    "2026-09-24", "2026-09-25", "2026-10-05", "2026-10-09", "2026-12-25", "2026-12-31",
}


def is_business_day(d: date) -> bool:
    return d.weekday() < 5 and d.isoformat() not in KRX_HOLIDAYS


def prev_business_day(d: date) -> date:
    d -= timedelta(days=1)
    while not is_business_day(d):
        d -= timedelta(days=1)
    return d


def ex_rights_date(record_date: str) -> str:
    return prev_business_day(date.fromisoformat(record_date)).isoformat()


def shift_business_days(d: date, n: int) -> date:
    """n 영업일 뒤(n<0 이면 앞). n=0 이면 d 가 영업일이 아닐 때 다음 영업일."""
    step = 1 if n >= 0 else -1
    if n == 0:
        while not is_business_day(d):
            d += timedelta(days=1)
        return d
    left = abs(n)
    while left:
        d += timedelta(days=step)
        if is_business_day(d):
            left -= 1
    return d
