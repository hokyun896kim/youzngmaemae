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


def test_parse_correction_ignores_before_values():
    """이렘 기재정정: 앞머리 정정표의 '정정전' 값(10/01·11/09 등)이 아니라 정정 반영 본문을 쓴다."""
    from tests.fixtures_dart import PIIC_DOC_REAL_SHAPE
    s = parse_document(PIIC_DOC_REAL_SHAPE)
    assert s.issue_price == 2360                 # 확정발행가 '-' → 예정발행가 사용
    assert s.record_date == "2026-10-13"
    assert (s.rights_start, s.rights_end) == ("2026-11-10", "2026-11-16")
    assert s.price_fix_date == "2026-11-20"
    assert (s.subs_start, s.subs_end) == ("2026-11-25", "2026-11-26")
    assert s.listing_date == "2026-12-11"
    assert s.extras["facts"]["discount"] == 0.35
    assert not any("불일치" in w for w in s.warnings)


def test_parse_correction_table_only_uses_after_values():
    from tests.fixtures_dart import PIIC_DOC_CORR_ONLY
    s = parse_document(PIIC_DOC_CORR_ONLY)
    assert s.record_date == "2026-10-13" and s.ex_rights_date == "2026-10-12"
    assert (s.subs_start, s.subs_end) == ("2026-11-25", "2026-11-26")
    assert s.price_fix_date == "2026-11-20" and s.listing_date == "2026-12-11"
    assert "record_date 못 찾음" not in s.warnings


def test_extract_discount():
    from yujeung.schedule_parser import extract_discount
    assert extract_discount("할인율 25% ... 할인율(25%) ... 할인율: 20%") == 0.25
    assert extract_discount("할인율 없음") is None


def test_rights_traps_holder_row_and_tbd():
    from tests.fixtures_dart import PIIC_DOC_TRAPS
    s = parse_document(PIIC_DOC_TRAPS)
    assert s.rights_start is None and s.rights_end is None   # '보유자' 청약행·'추후결정' 무시
    assert any("추후결정" in w for w in s.warnings)
    assert any("정정신고서 제출요구" in w for w in s.warnings)
    assert (s.subs_start, s.subs_end) == ("2026-11-02", "2026-11-03")


def test_rights_after_subscription_rejected():
    doc = PIIC_DOC.replace("2026년 09월 21일부터 2026년 09월 29일까지", "2026년 10월 12일부터 2026년 10월 13일까지")
    s = parse_document(doc)
    assert s.rights_start is None
    assert any("인수권 상장기간" in w for w in s.warnings)
