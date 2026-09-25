"""DART 원문 형태를 흉내 낸 합성 픽스처 (실제 공시 아님)."""

PIIC_DOC = """<?xml version="1.0" encoding="utf-8"?>
<DOCUMENT><DOCUMENT-NAME>주요사항보고서(유상증자결정)</DOCUMENT-NAME>
<TABLE><TBODY>
<TR><TD>1. 신주의 종류와 수</TD><TD>보통주식 (주)</TD><TD>44,681,000</TD></TR>
<TR><TD>기타주식 (주)</TD><TD>-</TD></TR>
<TR><TD>2. 1주당 액면가액 (원)</TD><TD>1,000</TD></TR>
<TR><TD>5. 신주 발행가액</TD><TD>보통주식 (원)</TD><TD>3,060</TD></TR>
<TR><TD>확정예정일</TD><TD>2026년 10월 06일</TD></TR>
<TR><TD>6. 신주배정기준일</TD><TD>2026년 09월 02일</TD></TR>
<TR><TD>7. 1주당 신주배정주식수 (주)</TD><TD>2.4014</TD></TR>
<TR><TD>9. 청약예정일</TD><TD>우리사주조합</TD><TD>시작일</TD><TD>2026년 10월 12일</TD></TR>
<TR><TD>종료일</TD><TD>2026년 10월 12일</TD></TR>
<TR><TD>구주주</TD><TD>시작일</TD><TD>2026년 10월 12일</TD></TR>
<TR><TD>종료일</TD><TD>2026년 10월 13일</TD></TR>
<TR><TD>10. 납입일</TD><TD>2026년 10월 15일</TD></TR>
<TR><TD>13. 신주의 상장 예정일</TD><TD>2026년 10월 28일</TD></TR>
<TR><TD>14. 신주인수권양도여부</TD><TD>예</TD></TR>
</TBODY></TABLE>
<P>신주인수권증서의 상장예정기간은 2026년 09월 21일부터 2026년 09월 29일까지이며, 거래소 승인에 따라 변경될 수 있습니다.</P>
</DOCUMENT>
"""

PIIC_FIELDS = {
    "rcept_no": "20260728000100", "corp_cls": "Y", "corp_code": "01234567", "corp_name": "테스트디앤디",
    "nstk_ostk_cnt": "44,681,000", "nstk_estk_cnt": "-", "fv_ps": "1,000",
    "bfic_tisstk_ostk": "18,617,382", "bfic_tisstk_estk": "-",
    "fdpp_fclt": "-", "fdpp_bsninh": "-", "fdpp_op": "-", "fdpp_dtrp": "136,723,860,000",
    "fdpp_ocsa": "-", "fdpp_etc": "-", "ic_mthn": "주주배정후 실권주 일반공모", "ssl_at": "N",
}
