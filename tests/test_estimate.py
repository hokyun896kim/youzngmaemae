from datetime import date

from yujeung import estimate
from yujeung.verdict import gate1

SCH = {"record_date": "2026-09-02", "ex_rights_date": "2026-09-01", "rights_start": "2026-09-21",
       "rights_end": "2026-09-29", "price_fix_date": "2026-10-06", "subs_start": "2026-10-12",
       "subs_end": "2026-10-13", "payment_date": "2026-10-15", "listing_date": "2026-10-28",
       "issue_price": 2260, "alloc_ratio": 2.4014}


def test_stage_cycle():
    got = [estimate.stage(SCH, date(2026, m, d)) for m, d in
           [(8, 20), (9, 1), (9, 21), (9, 29), (10, 12), (10, 20), (10, 28)]]
    assert got == ["1", "2", "3", "3", "4", "5", "listed"]


def test_issue_estimate_before_and_after_ex_rights():
    d, r = 0.2, 2.4014
    pre = estimate.issue_estimate(SCH, d, r, [("2026-08-20", 3000)], date(2026, 8, 20), False)
    assert pre["kind"] == "1차 추정"
    assert pre["value"] == round(3000 * 0.8 / (1 + r * d)) and pre["px"] == round(3000 / (1 + r * d))
    closes = [("2026-08-31", 3500), ("2026-09-01", 3300), ("2026-09-23", 3335)]
    first = dict(SCH, issue_kind="1차")
    post = estimate.issue_estimate(first, d, r, closes, date(2026, 9, 23), False)
    # 1차 발행가로 구분된 공시값 → I1 = 2,260, I2 = 권리락 후 주가 × (1−d) = 2,668 → min = 2,260
    assert post["kind"] == "최종 추정" and post["value"] == 2260 and post["i2"] == round(3335 * 0.8)
    low = estimate.issue_estimate(first, d, r, closes[:-1] + [("2026-09-23", 2500)], date(2026, 9, 23), False)
    assert low["value"] == 2000                          # 주가가 빠지면 2차(2,500×0.8)가 더 낮다
    # '예정발행가'면 공시값을 I1 로 쓰지 않고 권리락 직전 종가로 계산
    plan = estimate.issue_estimate(dict(SCH, issue_kind="예정"), d, r, closes, date(2026, 9, 23), False)
    assert plan["i1"] == round(3500 * 0.8 / (1 + r * d)) and plan["value"] == plan["i1"]
    assert "권리락 직전 종가 3,500" in plan["text"]
    nodis = estimate.issue_estimate(dict(SCH, issue_price=None), d, r, closes, date(2026, 9, 23), False)
    assert nodis["i1"] == round(3500 * 0.8 / (1 + r * d))  # 공시 없으면 권리락 직전 종가로 계산
    pre1 = estimate.issue_estimate(first, d, r, [("2026-08-20", 3000)], date(2026, 8, 20), False)
    assert pre1["value"] == 2260 and pre1["kind"] == "1차 공시"
    fixed = estimate.issue_estimate(dict(SCH, issue_kind="확정"), d, r, closes, date(2026, 10, 7))
    assert fixed["value"] == 2260 and fixed["kind"] == "확정"
    done = estimate.issue_estimate(SCH, d, r, closes, date(2026, 10, 7), True)
    assert done["value"] == 2260 and done["kind"] == "확정" and done["text"] == "확정발행가 2,260원"
    none = estimate.issue_estimate(SCH, None, r, closes, date(2026, 9, 23), False)
    assert none["value"] == 2260 and "할인율 미확인" in none["text"] and "예정발행가" in none["text"]


def test_breakeven_by_stage_and_table():
    closes = [("2026-08-31", 3500), ("2026-09-23", 3335)]
    issue = {"value": 2260, "d": 0.2, "r": 2.4014}
    b3 = estimate.breakeven("3", SCH, issue, closes, 636)
    assert b3["value"] == 2896 and b3["how"] == "인수권 매수 + 청약"
    b1 = estimate.breakeven("1", SCH, issue, closes, None)
    assert b1["value"] == round(3335 / (1 + 2.4014 * 0.2))
    b5 = estimate.breakeven("5", SCH, issue, closes, None)
    assert b5["value"] == 3335
    assert estimate.breakeven("listed", SCH, issue, closes, None) is None
    t = estimate.pnl_table(b3)
    assert [(x["name"], x["pct"], x["price"]) for x in t] == [
        ("좋음", 15, 3330), ("보통", 0, 2896), ("나쁨", -15, 2462), ("최악", -30, 2027)]


def test_overhang_days():
    o = estimate.overhang(44_681_000, [500_000] * 25)
    assert o["days"] == 89.4 and o["red"] and o["n"] == 20
    assert not estimate.overhang(1_000_000, [100_000] * 20)["red"]
    assert estimate.overhang(None, [1]) is None


def test_conclusion_and_recheck():
    sm = {"purpose_pct": {"채무상환": 100.0}, "dilution_ratio": 2.4}
    g = gate1(sm, {}, -42_817_140_616, "2026 반기(3개월, CFS)", 0.04, "SK디앤디")
    c = estimate.conclusion("white", g, -40.8)
    assert c["word"] == "패스" and c["reason"].startswith("관문1 탈락: 채무상환 100%")
    assert "재검토 없음" in estimate.recheck("white", g, -40.8, "2026 반기(3개월, CFS)", -20, 20)
    ok = {"purpose_pct": {"운영": 100.0}, "dilution_ratio": 0.3}
    g2 = gate1(ok, {}, -1, "2026 반기(3개월, CFS)", 0.3, "X")
    assert estimate.recheck("white", g2, None, "2026 반기(3개월, CFS)", -20, 20) == "3Q 영업흑자 전환 시"
    g3 = gate1(ok, {"major_holder": {"level": "full"}, "underwriting": "총액인수"}, 10, "", 0.3, "X")
    assert estimate.recheck("yellow", g3, -5, None, -20, 20) == "괴리율 -20% 이하 시 🟢 인수권 매수+청약 검토"
    assert estimate.conclusion("yellow", g3, -5.0)["reason"] == "괴리율 -5.0%"


def test_issue_kind_label_and_date():
    from yujeung.schedule_parser import first_price_date, issue_kind, price_label_kind
    assert price_label_kind("6.신주발행가액예정발행가보통주식(원)확정예정일") == "예정"
    assert price_label_kind("5.1차발행가액보통주식(원)") == "1차"
    assert price_label_kind("6.신주발행가액확정발행가보통주식(원)") == "확정"
    assert first_price_date("2026-09-02") == "2026-08-28"            # 기준일 전 3거래일
    sch = {"record_date": "2026-09-02", "price_fix_date": "2026-10-06"}
    assert issue_kind("예정", "20260728", sch) == "예정"              # 이사회 당시
    assert issue_kind("예정", "20260831", sch) == "1차"               # 1차 산정일 이후 정정공시
    assert issue_kind(None, "20260909", sch) == "1차"                 # 증권신고서(라벨 없음)
    assert issue_kind("1차", "20260801", sch) == "1차"
    assert issue_kind(None, "20261006", sch) == "확정"
