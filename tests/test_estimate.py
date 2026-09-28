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
    assert estimate.recheck("yellow", g3, -5, None, -20, 20) == "괴리율 -20% 이하 + 신주원가 할인율 -20% 초과(너무 깊지 않게) 시 🟢 인수권 매수+청약 검토"
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


def test_review_11_fixes():
    """[11] 검수: SG 청약 후 재추정 금지 · 🟢 인수권 종료 후 문구 · 경남제약 인수권 일정 미정 · 원가 확정가."""
    from yujeung import paper
    from yujeung.schedule_parser import issue_kind
    sg = {"record_date": "2026-07-22", "ex_rights_date": "2026-07-21", "rights_start": "2026-08-19",
          "rights_end": "2026-08-25", "subs_start": "2026-09-03", "subs_end": "2026-09-04",
          "listing_date": "2026-09-29", "issue_price": 911, "alloc_ratio": 0.41, "issue_kind": "1차"}
    closes = [("2026-07-20", 1500), ("2026-09-25", 1210)]
    e = estimate.issue_estimate(sg, 0.4, 0.41, closes, date(2026, 9, 26))
    assert e["value"] == 911 and e["kind"] == "확정" and "재추정 안 함" in e["text"]   # 726 아님
    # 확정 산정일이 없으면 청약 전 3거래일(8/31) 이후 공시 = 확정 → SG 9/01 911원
    assert issue_kind(None, "20260901", sg) == "확정" and issue_kind(None, "20260828", sg) == "1차"
    ok = {"purpose_pct": {"운영": 100.0}, "dilution_ratio": 0.37}
    g = gate1(ok, {"major_holder": {"level": "full"}, "underwriting": "총액인수"}, 10, "", 0.3, "SG")
    q = estimate.quick("green", g, -38.8, sg, {"discount": 0.4}, closes, [1] * 20, None, 1, 0.37, None,
                       date(2026, 9, 26), False)
    assert q["word"] == "진입 구간 종료 — 성과 추적 중" and q["stage"] == "5" and "가상 성과" in q["recheck"]
    q3 = estimate.quick("green", g, -38.8, sg, {"discount": 0.4}, closes, [1] * 20, 500, 1, 0.37, None,
                        date(2026, 8, 20), False)
    assert q3["word"] == "매수 검토"                                               # 인수권 거래 중엔 그대로
    kn = {"record_date": "2026-09-22", "ex_rights_date": "2026-09-21", "subs_start": "2026-11-02",
          "subs_end": "2026-11-03", "listing_date": "2026-11-17", "issue_price": 1499}
    assert estimate.stage(kn, date(2026, 9, 26)) == "tbd"
    assert estimate.STAGES["tbd"] == "인수권 일정 미정"
    # 가상 성과 원가: 청약이 시작됐으면 최신(확정) 발행가 — 판정 당시 1,064 → 911
    assert paper.final_issue_price(1064, sg, date(2026, 9, 26)) == (911, "확정발행가 911 반영 (판정 당시 1,064)")
    assert paper.final_issue_price(1064, sg, date(2026, 8, 25)) == (1064, None)          # 청약 전·1차면 판정 당시
    assert paper.final_issue_price(900, dict(sg, issue_kind="확정"), date(2026, 8, 30))[0] == 911


def test_review_17_dilution_ratio_denominator():
    """[17] 1차 발행가·Px 분모 = 증자비율(신주 ÷ 증자 전 발행주식총수), 배정비율이 아니라."""
    sch = dict(SCH, issue_kind="예정")
    ok = gate1({"purpose_pct": {"운영": 100.0}, "dilution_ratio": 0.3}, {}, -1, "2026 반기", 0.3, "X")
    q = estimate.quick("white", ok, None, sch, {"discount": 0.2}, [("2026-08-20", 3000)], [1] * 20, None, 1,
                       0.30, None, date(2026, 8, 20), False, disc=-12.0)
    assert q["issue"]["r"] == 0.30                                     # alloc_ratio 2.4014 가 아니라 증자비율 0.30
    assert q["issue"]["value"] == round(3000 * 0.8 / (1 + 0.30 * 0.2)) and "증자비율 30.0%" in q["issue"]["text"]
    assert q["green_check"] == {"gap": None, "disc": -12.0, "cheap": -20, "disc_floor": -20.0,
                                "gap_ok": False, "disc_ok": True, "ok": False}


def test_a_margin_three_layers():
    """A = 인수권 할인 포착, 발행가 3층: ① 1차가 기준 · ② 예상 최종가 기준 · ③ 확정가 기준.
    SK디앤디 12R(9/23) 실측: 괴리율 −41% 이어도 총원가 할인율 13.2% · 쿠션 439원 = ATR 1.25배.
    2차 추정(2,816)이 1차(2,260)보다 높으면 min 규칙으로 예상 최종 = 1차."""
    sch = {"rights_start": "2026-09-17", "rights_end": "2026-09-29", "subs_start": "2026-10-08",
           "listing_date": "2026-10-28", "issue_price": 2260, "issue_kind": "1차", "price_fix_date": "2026-10-02"}
    issue = {"kind": "최종 추정", "issue_kind": "1차", "i1": 2260, "i2": 2816, "value": 2260, "d": 0.25,
             "second": {"vwap": 3760, "close_base": 3335, "projected": True, "vwap_src": "x", "window": ["2026-09-23"]}}
    a = estimate.a_margin(sch, issue, 3335, "2026-09-23", 636, "2026-09-23", 351 / 3335 * 100, date(2026, 9, 28))
    r1, r2, r3 = a["rows"]
    assert (r1["kind"], r1["p_minus_i"], r1["gap"], r1["cost"], r1["cost_disc"], r1["cushion"], r1["cushion_atr"]) == \
           ("1차", 1075, -40.8, 2896, 13.2, 439, 1.25)
    assert (r2["kind"], r2["issue"], r2["gap"]) == ("예상 최종", 2260, -40.8) and a["gap_shift"] == 0.0
    assert r3["kind"] == "확정" and r3["issue"] is None and "10-02" in r3["note"]
    assert not a["confirmed"] and a["atr"] == 351 and a["final"]["i2"] == 2816 and a["final"]["floor"] is None
    # 남은 거래일(오늘 포함): 9/28(월)·9/29(화) = 2 / 청약 10/8 = 8 (10/5 휴장) / 상장 10/28 = 21 (10/9 휴장)
    assert [d["left"] for d in a["days"]] == [2, 8, 21]
    # 2차가 1차보다 낮으면(에코프로비엠형) ② 가 더 낮은 발행가 → P−Î 가 커져 같은 인수권 가격의 괴리가 더 싸 보인다
    lo = estimate.a_margin(sch, dict(issue, i2=2000, value=2000), 3335, "d", 636, "d", 351 / 3335 * 100, date(2026, 9, 28))
    assert lo["rows"][1]["issue"] == 2000 and lo["rows"][1]["gap"] == -52.4 and lo["gap_shift"] == -11.6
    # 인수권 시세 전: 쿠션이 ATR 1배 남는 R 상한 = P − I − ATR
    b = estimate.a_margin(sch, issue, 3335, "2026-09-23", None, None, 351 / 3335 * 100, date(2026, 9, 28))
    assert b["rows"][0]["cost"] is None and b["rows"][0]["r_for_1atr"] == 3335 - 2260 - 351
    # 확정이면 ③ 한 줄, 예정발행가는 1차로 쓰지 않음, 권리락 전이면 ② = 1차
    c = estimate.a_margin(sch, {"kind": "확정", "value": 2300}, 3335, "d", 636, "d", None, date(2026, 9, 28))
    assert [r["kind"] for r in c["rows"]] == ["확정"] and c["rows"][0]["cushion_atr"] is None and c["final"] is None
    d = estimate.a_margin(dict(sch, issue_kind="예정"), {"kind": "1차 추정", "issue_kind": "예정", "i1": 2100},
                          3335, "d", None, None, None, date(2026, 9, 28))
    assert [(r["kind"], r["issue"]) for r in d["rows"]] == [("1차", 2100), ("예상 최종", 2100), ("확정", None)]
    assert "권리락 전" in d["rows"][1]["note"]
    assert estimate.a_margin({}, issue, 3335, "d", 636, "d", 5, date(2026, 9, 28)) is None   # 인수권 없는 케이스
    assert estimate.trading_days_left(date(2026, 9, 28), "2026-09-27") is None


def test_second_price_vwap_and_projection():
    """2차 = min(1주 VWAP, 기산일 종가) × (1−d). 권리락 후 시세만, 기산일(산정일) 이후 시세는 안 씀."""
    sch = {"ex_rights_date": "2026-09-03", "price_fix_date": "2026-09-10"}
    bars = [{"bas_dd": f"2026-09-{d:02d}", "close": c, "volume": 100, "value": v} for d, c, v in
            [(2, 200, 20000), (3, 100, 10000), (4, 110, 11000), (7, 120, 12000), (8, 130, 13000), (9, 140, 14000),
             (10, 150, 15000), (11, 90, 9000)]]
    sp = estimate.second_price(sch, 0.2, bars, date(2026, 9, 11))
    assert sp["window"] == ["2026-09-04", "2026-09-07", "2026-09-08", "2026-09-09", "2026-09-10"]
    assert (sp["vwap"], sp["close_base"], sp["base"], sp["i2"], sp["projected"]) == (130, 150, 130, 104, False)
    assert sp["vwap_src"].startswith("KRX")
    # 기산일 전: 오늘까지의 최근 5거래일로 '오늘이 기산일이라면' — 9/3(권리락일)부터만
    pj = estimate.second_price(sch, 0.2, bars, date(2026, 9, 7))
    assert pj["projected"] and pj["window"] == ["2026-09-03", "2026-09-04", "2026-09-07"] and pj["close_base"] == 120
    # 거래대금이 빠진 날이 섞이면 종가×거래량 근사
    mix = estimate.second_price(sch, 0.2, [dict(b, value=None) if b["bas_dd"] == "2026-09-08" else b for b in bars],
                                date(2026, 9, 11))
    assert mix["vwap"] == 130 and "근사" in mix["vwap_src"]


def test_supply_shock():
    daily = [(1000, 100_000)] * 25
    s = estimate.supply(2_000_000, 0.4, 1000, daily, listing_volume=500_000)
    assert (s["dilution"], s["volume_days"], s["value_days"], s["listing_turnover"], s["float_ratio"]) == \
           (40.0, 20.0, 20.0, 0.25, None)
    assert estimate.supply(None, 0.4, 1000, daily) is None


def test_rights_end_check_delist_vs_last_trade():
    """인수권 상장폐지일 ≠ 매매종료일: KRX 상장폐지일은 매매종료 다음 영업일 (실측 SK디앤디 공시 9/29 · KRX 상폐 9/30)."""
    ok = estimate.rights_end_check("2026-09-29", "2026-09-30")
    assert (ok["status"], ok["last"], ok["krx_last"]) == ("ok", "2026-09-29", "2026-09-29")
    # 상장폐지일이 휴장일 다음이면 전 '영업일'로 (10/5 휴장 → 10/6 상폐면 마지막 매매일 10/2)
    assert estimate.rights_end_check("2026-10-02", "2026-10-06")["status"] == "ok"
    bad = estimate.rights_end_check("2026-09-30", "2026-09-30")    # 상장폐지일을 매매종료일로 잘못 읽은 경우
    assert bad["status"] == "mismatch" and bad["krx_last"] == "2026-09-29"
    assert estimate.rights_end_check("2026-10-02", None)["status"] == "disclosed_only"
    assert estimate.rights_end_check(None, "2026-09-30")["last"] == "2026-09-29"
    assert estimate.rights_end_check(None, None) is None
