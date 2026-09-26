"""[18] 실전 전략 배지 — 조건·금지 규칙·지표·전략2 손절·카드 상태·기록."""
import json
from datetime import date

from yujeung import db, strategy
from yujeung.backtest import strategy_stats


def test_conditions_cards_to_check():
    # 툴젠: 괴리 +66%, 적자, 희석 8.6% → 🥇 (적자는 전략 2·3만 막는다)
    c = strategy.conditions(0.0864, None, -6_891_483_126, 66.2)
    assert c["ok"] == {"s1": True, "s2": False, "s3": False} and c["bans"] == ["loss"]
    # SK디앤디: 희석 240% → ⛔ (다른 조건과 무관하게 전부 끔)
    c = strategy.conditions(2.4, 100.0, -42_817_140_616, 25.0)
    assert not any(c["ok"].values()) and c["bans"][0] == "dilution"
    # 아이에이: 흑자 15억 · 희석 49.2% · 채무상환 없음 → 🥈
    c = strategy.conditions(0.4924, None, 1_543_828_572, None)
    assert c["ok"]["s2"] and not c["bans"]
    # 희석 50% 이상·채무상환 50% 이상·영업이익 미확인 → 전략2 아님
    assert not strategy.conditions(0.5, 0, 1, None)["ok"]["s2"]
    assert not strategy.conditions(0.2, 50.0, 1, None)["ok"]["s2"]
    assert not strategy.conditions(0.2, 0, None, None)["ok"]["s2"]


def test_s3_range_and_too_cheap():
    ok = lambda gap, dil=0.8, op=1: strategy.conditions(dil, 0, op, gap)["ok"]["s3"]
    assert ok(-19.9) and ok(-0.1)
    assert not ok(-20.0) and not ok(0.0)            # 경계: −20% 이하는 기출 '−40~−20%' 구간, 0 이상은 고평가 쪽
    assert not ok(-10, dil=1.0) and not ok(-10, op=-1)
    c = strategy.conditions(0.3, 0, 1, -40.0)
    assert c["bans"] == ["too_cheap"] and not c["ok"]["s3"] and c["ok"]["s2"]   # 너무 싸도 전략2는 가능


def test_rsi_atr():
    assert strategy.rsi(list(range(1, 17))) == 100.0
    assert strategy.rsi([10] * 16) == 50.0
    assert strategy.rsi([10] * 10) is None
    down = [100 - i for i in range(16)]
    assert strategy.rsi(down) == 0.0
    rows = [{"high": 110, "low": 90, "close": 100}] * 15
    assert strategy.atr(rows) == 20.0
    assert strategy.atr(rows[:14]) is None


def _seed(conn, closes, listing_i, lows=None, opens=None):
    days = []
    d = date(2026, 1, 5)
    from datetime import timedelta

    from yujeung.calendar_kr import is_business_day
    while len(days) < len(closes):
        if is_business_day(d):
            days.append(d.isoformat())
        d += timedelta(days=1)
    for i, (dd, c) in enumerate(zip(days, closes)):
        lo = (lows or {}).get(i, c - 50)
        op = (opens or {}).get(i, c)
        conn.execute("INSERT INTO stock_daily (bas_dd, code, close, open, high, low) VALUES (?,?,?,?,?,?)",
                     (dd, "111110", c, op, c + 50, lo))
        conn.execute("INSERT INTO index_daily (bas_dd, idx, close) VALUES (?,?,?)", (dd, "KOSDAQ", 1000.0))
    return days


def test_eval_s2_stop_loss():
    conn = db.connect(":memory:")
    closes = [1000] * 30 + [1000] + [1010] * 12            # 상장일 = 30번째, ATR = 100 (고저 ±50)
    days = _seed(conn, closes, 30, lows={33: 750})           # +3일 저가 750 → 손절선 800 터치
    ev = strategy.eval_s2(conn, "111110", "K", days[30])
    assert ev["entry"] == 1000 and ev["atr"] == 100.0 and ev["stop"] == 800
    assert ev["rsi"] == 50.0 and ev["gate"] is True
    p = {x["label"]: x for x in ev["points"]}
    assert p["+5일"]["ret"] == -20.0 and p["+10일"]["ret"] == -20.0 and p["+10일"]["stopped"] == days[33]
    # 시가가 이미 손절선 밑(갭 하락) → 시가에 청산
    conn2 = db.connect(":memory:")
    days = _seed(conn2, closes, 30, lows={33: 700}, opens={33: 720})
    ev = strategy.eval_s2(conn2, "111110", "K", days[30])
    assert {x["label"]: x for x in ev["points"]}["+10일"]["ret"] == -28.0
    # 손절 없이 보유 → +10일 종가
    conn3 = db.connect(":memory:")
    days = _seed(conn3, closes, 30)
    ev = strategy.eval_s2(conn3, "111110", "K", days[30])
    assert {x["label"]: x for x in ev["points"]}["+10일"]["ret"] == 1.0
    # 시세가 모자라면 대기
    ev = strategy.eval_s2(conn3, "111110", "K", days[38])
    assert "pending" in {x["label"]: x for x in ev["points"]}["+10일"]
    assert strategy.eval_s2(conn3, "111110", "K", "2027-01-04") is None


def _case(conn, code="111110"):
    conn.execute("INSERT INTO cases (corp_code, corp_name, stock_code, corp_cls, first_rcept_no, first_rcept_dt, "
                 "is_rights, created_at) VALUES ('c','테스트',?,'K','r1','20260105',1,'x')", (code,))
    return conn.execute("SELECT * FROM cases").fetchone()


def test_card_states_and_ban():
    conn = db.connect(":memory:")
    days = _seed(conn, [1000] * 45, 0)
    c = _case(conn)
    sch = {"rights_start": days[5], "rights_end": days[9], "listing_date": days[30]}
    sm = {"dilution_ratio": 0.3, "purpose_pct": {"운영": 100.0}}
    # 상장 D-4 → 대기, D-3 → 지금 해당, +10일 지나면 종료
    k = strategy.card(conn, c, sch, sm, 10, None, date.fromisoformat(days[26]))
    assert [(i["key"], i["state"]) for i in k["items"]] == [("s2", "wait")] and k["rank"] == 1
    k = strategy.card(conn, c, sch, sm, 10, None, date.fromisoformat(days[27]))
    assert k["items"][0]["state"] == "live" and k["rank"] == 0 and k["items"][0]["exit_on"] == days[40]
    s2 = strategy.card(conn, c, sch, sm, 10, None, date.fromisoformat(days[31]))["items"][0]
    assert s2["confirmed"] and s2["entry"] == 1000 and s2["stop"] == 800 and s2["stop_basis"] == "상장일 종가"
    assert strategy.card(conn, c, sch, sm, 10, None, date.fromisoformat(days[41]))["items"][0]["state"] == "past"
    # 희석 100% 이상 → ⛔ 만 (전략 배지 없음)
    k = strategy.card(conn, c, sch, dict(sm, dilution_ratio=1.2), 10, 30.0, date.fromisoformat(days[7]))
    assert k["items"] == [] and k["ban"][0] == "dilution" and k["rank"] == 2
    # 적자 + 괴리 +30% → 🥇 은 살아 있고 금지 규칙은 참고로만
    k = strategy.card(conn, c, sch, sm, -1, 30.0, date.fromisoformat(days[7]))
    assert [i["key"] for i in k["items"]] == ["s1"] and k["ban"] is None and k["bans"] == ["loss"]
    # 적자 + 괴리 −10% → 남는 전략 없음 → ⛔
    k = strategy.card(conn, c, sch, sm, -1, -10.0, date.fromisoformat(days[7]))
    assert k["items"] == [] and k["ban"] == ["loss"]
    # 조건 없음(흑자·희석 70%·괴리 +5%) → 해당 전략 없음
    k = strategy.card(conn, c, sch, dict(sm, dilution_ratio=0.7), 10, 5.0, date.fromisoformat(days[7]))
    assert k["items"] == [] and k["ban"] is None and k["rank"] == 3


def test_record_and_scorecard():
    conn = db.connect(":memory:")
    days = _seed(conn, [1000] * 45, 0)
    c = _case(conn)
    for d in days[5:10]:
        conn.execute("INSERT INTO rights_daily (bas_dd, isu_cd, isu_nm, close, issue_price) VALUES (?,?,?,?,?)",
                     (d, "1111101G", "테스트 1R", 150, 800))
    sch = {"rights_start": days[5], "rights_end": days[9], "listing_date": days[30], "issue_price": 800}
    live = {"summary": {"dilution_ratio": 0.3, "purpose_pct": {}}, "gap_on": {days[9]: -25.0 + 15},
            "stock_on": {days[9]: 1000}}
    assert strategy.record_if_due(conn, c, sch, live, 10, False) == 2        # 🥉(괴리 −10%) + 🥈(상장일 종가)
    assert strategy.record_if_due(conn, c, sch, live, 10, False) == 0        # 불변: 두 번 기록 안 함
    trades = conn.execute("SELECT * FROM strategy_trades ORDER BY strategy").fetchall()
    assert [t["strategy"] for t in trades] == ["s2", "s3"]
    res = [{"strategy": t["strategy"], "eval": strategy.evaluate(conn, c, t, sch, date.fromisoformat(days[44]))}
           for t in trades]
    s3 = next(r["eval"] for r in res if r["strategy"] == "s3")
    assert s3["entry"] == 950 and strategy.exit_point(s3)["label"] == "+5일"
    card = {r["strategy"]: r for r in strategy.scorecard(res)}
    assert card["s3"]["done"] == 1 and card["s3"]["median"] == round((1000 / 950 - 1) * 100, 1)
    assert card["s2"]["done"] == 1 and card["s2"]["median"] == 0.0 and card["s1"]["n"] == 0
    json.dumps(strategy.rules(), ensure_ascii=False)


def test_strategy_stats_sell_rate():
    def rec(gap, r20, op=1, dil=0.3):
        pts = [{"label": lb, "ret": r20} for lb in ("상장일 시가", "+5일", "+20일")]
        return {"gap": gap, "op_income": op, "dilution": dil, "debt_pct": 0, "base": {"points": pts}}
    recs = [rec(30, -10), rec(25, -5), rec(40, 8, op=-1), rec(30, -20, dil=1.5), rec(-10, 4), rec(-45, -3)]
    st = strategy_stats(recs, [], [2020])
    assert st["s1"]["n"] == 3 and st["s1"]["sell_rate"] == 67             # 희석 150% 는 ⛔ 라 빠짐
    assert st["s3"]["n"] == 1 and st["s3"]["points"]["+5일"]["median"] == 4
    assert st["bans"]["dilution"]["n"] == 1 and st["bans"]["too_cheap"]["n"] == 1 and st["bans"]["loss"]["n"] == 1
    assert st["s2"]["n"] == 0 and st["s2"]["missing_years"] == [2020]
