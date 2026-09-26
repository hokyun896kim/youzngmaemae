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


def test_tbd_only_in_correction_preamble_body_dash():
    """실측 경남제약 9/18 (v9): 정정표에만 '추후결정', 정정 반영 본문은 '-'. 날짜 없음 + 미정 기록이 남아야
    케이스 일정이 이전 정정 날짜로 되돌아가지 않는다."""
    why = "관계기관의 정정신고서 제출요구에 따른 정정"
    corr = f"""<TABLE><TBODY>
<TR><TD>항 목</TD><TD>정정사유</TD><TD>정 정 전</TD><TD>정 정 후</TD></TR>
<TR><TD>8. 신주배정기준일</TD><TD>{why}</TD><TD>2026년 09월 22일</TD><TD>추후결정</TD></TR>
<TR><TD>12. 납입일</TD><TD>{why}</TD><TD>2026년 11월 05일</TD><TD>추후결정</TD></TR>
<TR><TD>16. 신주의 상장예정일</TD><TD>{why}</TD><TD>2026년 11월 17일</TD><TD>추후결정</TD></TR>
</TBODY></TABLE>"""
    body = """<TABLE><TBODY>
<TR><TD>1. 신주의 종류와 수</TD><TD>보통주식 (주)</TD><TD>6,000,000</TD></TR>
<TR><TD>6. 신주 발행가액</TD><TD>예정발행가</TD><TD>보통주식 (원)</TD><TD>1,499</TD></TR>
<TR><TD>8. 신주배정기준일</TD><TD>-</TD></TR>
<TR><TD>12. 납입일</TD><TD>-</TD></TR>
<TR><TD>16. 신주의 상장예정일</TD><TD>-</TD></TR>
</TBODY></TABLE>"""
    s = parse_document("<DOCUMENT>" + corr + body + "</DOCUMENT>")
    assert (s.record_date, s.payment_date, s.listing_date) == (None, None, None)
    assert {"record_date", "payment_date", "listing_date"} <= set(s.extras["tbd"])


# 2020 옛 양식(실측 유네코 4/14 원문 모양): 표엔 '상장여부 예'만, 기간은 '기타 투자판단' 5)번 문장에.
# 앞쪽 '상장여부 예 … 이사회결의일 2020년 04월 14일' · '전자증권 시행일(2019년 9월 16일)' 날짜에 걸려 멈추면 안 된다
OLD_2020 = (PIIC_DOC.replace("2026년 09월 02일", "2020년 05월 19일").replace("2026년 10월 12일", "2020년 06월 23일")
            .replace("2026년 10월 13일", "2020년 06월 24일").replace("2026년 10월 06일", "2020년 06월 18일")
            .replace("2026년 10월 15일", "2020년 07월 02일").replace("2026년 10월 28일", "2020년 07월 14일")
            .replace("<TR><TD>14. 신주인수권양도여부</TD><TD>예</TD></TR>",
                     "<TR><TD>18. 신주인수권양도여부</TD><TD>예</TD></TR>"
                     "<TR><TD>- 신주인수권증서의 상장여부</TD><TD>예</TD></TR>"
                     "<TR><TD>- 신주인수권증서의 매매 및 매매의 중개를 담당할 금융투자업자</TD><TD>한양증권(주)</TD></TR>"
                     "<TR><TD>19. 이사회결의일(결정일)</TD><TD>2020년 04월 14일</TD></TR>")
            .replace("<P>신주인수권증서의 상장예정기간은 2026년 09월 21일부터 2026년 09월 29일까지이며, 거래소 승인에 따라 변경될 수 있습니다.</P>",
                     "<P>1) 신주인수권증서는 전자증권제도 시행일(2019년 9월 16일) 이후 전자등록 방식으로 발행됩니다.&cr;"
                     "3) 신주인수권증서 매매의 중개를 할 증권회사는 한양증권(주)로 합니다.&cr;"
                     "4) 신주인수권증서는 한국거래소에 상장 예정입니다.&cr;"
                     "5) 신주인수권증서 상장예정기간 : 2020년 06월 08일~ 2020년 06월 12일&cr;</P>"))


def test_old_2020_form_rights_period_in_text():
    s = parse_document(OLD_2020)
    assert s.record_date == "2020-05-19" and s.subs_start == "2020-06-23"
    assert (s.rights_start, s.rights_end) == ("2020-06-08", "2020-06-12")
    assert s.extras["facts"]["rights_listed"] is True


def test_rights_period_securities_registration_table_form():
    """증권신고서 일정표(실측 유네코 5/26): 기간이 라벨 앞. 뒤의 '상장 폐지 6/26' 을 시작일로 잡으면 안 된다."""
    from yujeung.schedule_parser import extract_rights_period
    text = ("2020년 05월 29일 권리락 - 2020년 06월 01일 신주배정 기준일(주주확정) - 2020년 06월 12일 신주배정 통지 - "
            "2020년 06월 19일 ~&cr;2020년 06월 25일 신주인수권증서 상장 거래기간 5거래일 이상 거래 "
            "2020년 06월 26일 신주인수권증서 상장 폐지 구주주 청약초일 5거래일 전 2020년 07월 01일 확정 발행가액 산정")
    assert extract_rights_period(text, "2020-06-01", "2020-07-06") == ("2020-06-19", "2020-06-25")
    assert extract_rights_period(text, "2020-06-20", "2020-07-06") is None       # 기준일보다 이르면 버림
    assert extract_rights_period(text, "2020-06-01", "2020-06-24") is None       # 청약보다 늦으면 버림


def test_rights_not_listed_marked():
    """'신주인수권증서의 상장여부 아니오'(실측 케이비캐피탈·에스케이엔펄스) — 인수권 거래가 원래 없다."""
    doc = PIIC_DOC.replace("<TR><TD>14. 신주인수권양도여부</TD><TD>예</TD></TR>",
                           "<TR><TD>18. 신주인수권양도여부</TD><TD>아니오</TD></TR>"
                           "<TR><TD>- 신주인수권증서의 상장여부</TD><TD>아니오</TD></TR>")
    assert parse_document(doc).extras["facts"]["rights_listed"] is False


def test_electronic_securities_date_not_rights_when_record_tbd():
    """기준일이 추후결정이면 '기준일 이전' 검사가 안 걸린다 → 전자증권 시행일(2019-09-16)을 인수권 시작으로 잡으면 안 됨."""
    doc = (PIIC_DOC.replace("<TD>6. 신주배정기준일</TD><TD>2026년 09월 02일</TD>", "<TD>6. 신주배정기준일</TD><TD>추후결정</TD>")
           .replace("<P>신주인수권증서의 상장예정기간은 2026년 09월 21일부터 2026년 09월 29일까지이며, 거래소 승인에 따라 변경될 수 있습니다.</P>",
                    "<P>신주인수권증서는 전자증권제도 시행일(2019년 9월 16일) 이후 전자등록 방식으로 상장되어 거래됩니다.</P>"))
    s = parse_document(doc)
    assert s.record_date is None and s.rights_start is None
