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


# 실측 이렘(9/23 기재정정) 재발: 정정사항 표가 '정정전/정정후' 머리글이 아니어서 안 걸렸다 (옛 값과 새 값이 한 행)
CORR_ALT = """<TABLE><TBODY>
<TR><TD>정정항목</TD><TD>정정사유</TD><TD>당초</TD><TD>변경</TD></TR>
<TR><TD>8. 신주배정기준일</TD><TD>일정변경에 따른 정정</TD><TD>2026년 10월 01일</TD><TD>2026년 10월 13일</TD></TR>
<TR><TD>라. 신주인수권에 관한 사항 - 2) 신주인수권증서 상장예정기간</TD><TD>일정변경</TD>
<TD>2026년 10월 22일</TD><TD>2026년 10월 28일</TD><TD>2026년 11월 10일</TD><TD>2026년 11월 16일</TD></TR>
<TR><TD>6. 신주 발행가액</TD><TD>일정변경에 따른 정정</TD><TD>확정예정일</TD><TD>2026년 11월 04일</TD><TD>2026년 11월 20일</TD></TR>
<TR><TD>11. 청약예정일</TD><TD>구주주</TD><TD>시작일</TD><TD>2026년 11월 09일</TD><TD>2026년 11월 25일</TD></TR>
<TR><TD>16. 신주의 상장 예정일</TD><TD>일정변경</TD><TD>2026년 11월 25일</TD><TD>2026년 12월 11일</TD></TR>
</TBODY></TABLE>
<P>정정 전 신주인수권증서 상장예정기간은 2026년 10월 22일부터 2026년 10월 28일까지였습니다.</P>"""
BODY_ALT = """<TABLE><TBODY>
<TR><TD>1. 신주의 종류와 수</TD><TD>보통주식 (주)</TD><TD>4,800,000</TD></TR>
<TR><TD>6. 신주 발행가액</TD><TD>예정발행가</TD><TD>보통주식 (원)</TD><TD>2,360</TD><TD>확정 예정일</TD><TD>2026년 11월 20일</TD></TR>
<TR><TD>8. 신주배정기준일</TD><TD>2026년 10월 13일</TD></TR>
<TR><TD>11. 청약예정일</TD><TD>구주주</TD><TD>시작일</TD><TD>2026년 11월 25일</TD></TR>
<TR><TD>종료일</TD><TD>2026년 11월 26일</TD></TR>
<TR><TD>12. 납입일</TD><TD>2026년 12월 01일</TD></TR>
<TR><TD>16. 신주의 상장 예정일</TD><TD>2026년 12월 11일</TD></TR>
</TBODY></TABLE>
<P>구주주 1주당 배정비율 산정 시 할인율은 35%를 적용하며, 신주인수권증서의 상장예정기간은 2026년 11월 10일부터 2026년 11월 16일까지입니다.</P>"""


def test_correction_preamble_without_before_after_header():
    s = parse_document("<DOCUMENT>" + CORR_ALT + BODY_ALT + "</DOCUMENT>")
    assert s.record_date == "2026-10-13"
    assert (s.rights_start, s.rights_end) == ("2026-11-10", "2026-11-16")   # 앞머리 문장의 옛 기간이 아니라 본문
    assert s.price_fix_date == "2026-11-20"
    assert (s.subs_start, s.subs_end) == ("2026-11-25", "2026-11-26")
    assert s.listing_date == "2026-12-11"
    assert s.extras["facts"]["discount"] == 0.35                            # '할인율은 35%를'
    assert s.extras["issue_label_kind"] == "예정"


def test_correction_preamble_fills_missing_with_after_half():
    body = BODY_ALT.split("<P>")[0]   # 본문에 인수권 기간 문장이 없으면 → 정정 행의 뒤쪽 절반(11/10~16)
    s = parse_document("<DOCUMENT>" + CORR_ALT + body + "</DOCUMENT>")
    assert (s.rights_start, s.rights_end) == ("2026-11-10", "2026-11-16")
    assert s.record_date == "2026-10-13"


def test_correction_table_after_body_and_tbd_rights():
    """실측 경남제약 9/18 기재정정: 정정표가 본문 '뒤'에 붙고(그 안에도 '신주의 종류와 수' 행),
    인수권 기간은 '추후결정 4) … 전자증권제도 시행일(2019년 9월 16일)' 문장 — v6 에서 본문을 버리고 2019 를 집었다."""
    body = """<TABLE><TBODY>
<TR><TD>1. 신주의 종류와 수</TD><TD>보통주식 (주)</TD><TD>6,000,000</TD></TR>
<TR><TD>6. 신주 발행가액</TD><TD>예정발행가</TD><TD>보통주식 (원)</TD><TD>1,499</TD><TD>확정 예정일</TD><TD>2026년 10월 28일</TD></TR>
<TR><TD>8. 신주배정기준일</TD><TD>2026년 09월 22일</TD></TR>
<TR><TD>11. 청약예정일</TD><TD>구주주</TD><TD>시작일</TD><TD>2026년 11월 02일</TD></TR>
<TR><TD>종료일</TD><TD>2026년 11월 03일</TD></TR>
<TR><TD>12. 납입일</TD><TD>2026년 11월 05일</TD></TR>
<TR><TD>16. 신주의 상장 예정일</TD><TD>2026년 11월 17일</TD></TR>
</TBODY></TABLE>
<P>3) 신주인수권증서 상장예정기간 : 추후결정4) 금번 유상증자시 신주인수권증서는 전자증권제도 시행일(2019년 9월 16일) 이후에 발행되고 상장될 예정</P>"""
    corr = """<TABLE><TBODY>
<TR><TD>정정사항</TD><TD>정정전</TD><TD>정정후</TD></TR>
<TR><TD>1. 신주의 종류와 수</TD><TD>6,000,000</TD><TD>6,000,000</TD></TR>
<TR><TD>신주인수권증서 상장예정기간</TD><TD>2026년 10월 15일 ~ 2026년 10월 21일</TD><TD>추후결정</TD></TR>
</TBODY></TABLE>"""
    s = parse_document("<DOCUMENT>" + body + corr + "</DOCUMENT>")
    assert s.record_date == "2026-09-22" and s.listing_date == "2026-11-17"
    assert (s.subs_start, s.subs_end) == ("2026-11-02", "2026-11-03") and s.payment_date == "2026-11-05"
    assert s.rights_start is None and s.rights_end is None                   # 2019-09-16 아님
    assert any("추후결정" in w for w in s.warnings)


def test_tbd_after_correction_rows_kyungnam_real_shape():
    """실측 경남제약 9/18 원문 행: '8. 신주배정기준일 | 관계기관의 … 정정 | 2026-09-22 | 추후결정'.
    같은 행의 날짜는 정정전 값 → 항목은 미정. v7 은 옛 날짜를 되살렸다."""
    why = "관계기관의 '증권신고서에 대한 정정신고서 제출요구'에 따른 정정"
    doc = f"""<DOCUMENT><TABLE><TBODY>
<TR><TD>1. 신주의 종류와 수</TD><TD>보통주식 (주)</TD><TD>6,000,000</TD></TR>
<TR><TD>6. 신주 발행가액</TD><TD>예정발행가</TD><TD>보통주식 (원)</TD><TD>1,499</TD><TD>확정 예정일</TD><TD>2026년 10월 28일</TD></TR>
<TR><TD>8. 신주배정기준일</TD><TD>{why}</TD><TD>2026년 09월 22일</TD><TD>추후결정</TD></TR>
<TR><TD>11. 청약예정일</TD><TD>{why}</TD><TD>구주주</TD><TD>시작일</TD><TD>2026년 11월 02일</TD></TR>
<TR><TD>종료일</TD><TD>2026년 11월 03일</TD></TR>
<TR><TD>시작일</TD><TD>추후결정</TD></TR>
<TR><TD>12. 납입일</TD><TD>{why}</TD><TD>2026년 11월 05일</TD><TD>추후결정</TD></TR>
<TR><TD>16. 신주의 상장예정일</TD><TD>{why}</TD><TD>2026년 11월 17일</TD><TD>추후결정</TD></TR>
</TBODY></TABLE>
<P>3) 신주인수권증서 상장예정기간 : 추후결정4) 금번 유상증자시 신주인수권증서는 전자증권제도 시행일(2019년 9월 16일) 이후</P>
</DOCUMENT>"""
    s = parse_document(doc)
    # 청약은 '시작일 | 11/02' 행이 먼저, '추후결정' 행이 뒤에 온다 (실측) → 먼저 잡힌 날짜도 지움
    assert (s.record_date, s.ex_rights_date, s.subs_start, s.subs_end, s.payment_date, s.listing_date) == (None,) * 6
    assert s.rights_start is None and s.issue_price == 1499
    assert set(s.extras["tbd"]) >= {"record_date", "subs_start", "payment_date", "listing_date"}
    assert any("신주배정기준일 추후결정" in w for w in s.warnings)


def test_rights_start_equal_to_record_date_dropped():
    """실측 클로봇: 인수권 시작일이 기준일(7/07)과 같은 날로 잡힘 — 인수권은 기준일 뒤에 상장된다."""
    doc = PIIC_DOC.replace("2026년 09월 21일부터 2026년 09월 29일까지", "2026년 09월 02일")
    s = parse_document(doc)
    assert s.record_date == "2026-09-02" and s.rights_start is None
