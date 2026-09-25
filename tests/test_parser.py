from tests.fixtures_dart import PIIC_DOC
from yujeung.calendar_kr import ex_rights_date
from yujeung.schedule_parser import find_dates, parse_document


def test_find_dates_formats():
    assert find_dates("2026년 9월 2일 / 2026.10.15 / 20261028") == ["2026-09-02", "2026-10-15", "2026-10-28"]


def test_parse_piic_document():
    s = parse_document(PIIC_DOC)
    assert s.record_date == "2026-09-02"
    assert s.ex_rights_date == "2026-09-01"
    assert s.issue_price == 3060
    assert s.alloc_ratio == 2.4014
    assert (s.subs_start, s.subs_end) == ("2026-10-12", "2026-10-13")   # 우리사주 말고 구주주
    assert s.payment_date == "2026-10-15"
    assert s.listing_date == "2026-10-28"
    assert (s.rights_start, s.rights_end) == ("2026-09-21", "2026-09-29")  # 본문 문장에서
    assert s.price_fix_date == "2026-10-06"
    assert any("미검증" in w for w in s.warnings)


def test_ex_rights_skips_weekend_and_holiday():
    assert ex_rights_date("2026-09-28") == "2026-09-23"   # 월요일 기준일 → 추석 연휴·주말 건너뜀
