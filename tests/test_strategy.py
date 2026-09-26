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
    # 아이에이: 🟡? · 흑자 15억 · 희석 49.2% · 채무상환 없음 → 🥈
    c = strategy.conditions(0.4924, None, 1_543_828_572, None, "yellow_q")
    assert c["ok"]["s2"] and not c["bans"]
    # B안: 판정이 🟡/🟡? 가 아니면 전략2 아님 (🟢?·⚪·🔵·판정 없음)
    for v in ("green_q", "green", "white", "blue", None):
        assert not strategy.conditions(0.4924, None, 1_543_828_572, None, v)["ok"]["s2"]
    assert strategy.conditions(0.4924, None, 1_543_828_572, None, "yellow")["ok"]["s2"]
    # 희석 50% 이상·채무상환 50% 이상·영업이익 미확인 → 전략2 아님
    assert not strategy.conditions(0.5, 0, 1, None, "yellow")["ok"]["s2"]
    assert not strategy.conditions(0.2, 50.0, 1, None, "yellow")["ok"]["s2"]
    assert not strategy.conditions(0.2, 0, None, None, "yellow")["ok"]["s2"]


def test_s3_range_and_too_cheap():
    ok = lambda gap, dil=0.8, op=1: strategy.conditions(dil, 0, op, gap)["ok"]["s3"]
    assert ok(-19.9) and ok(-0.1)
    assert not ok(-20.0) and not ok(0.0)            # 경계: −20% 이하는 기출 '−40~−20%' 구간, 0 이상은 고평가 쪽
    assert not ok(-10, dil=1.0) and not ok(-10, op=-1)
    c = strategy.conditions(0.3, 0, 1, -40.0, "yellow_q")
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
    k = strategy.card(conn, c, sch, sm, 10, None, date.fromisoformat(days[26]), "yellow_q")
    assert [(i["key"], i["state"]) for i in k["items"]] == [("s2", "wait")] and k["rank"] == 1
    k = strategy.card(conn, c, sch, sm, 10, None, date.fromisoformat(days[27]), "yellow_q")
    assert k["items"][0]["state"] == "live" and k["rank"] == 0 and k["items"][0]["exit_on"] == days[40]
    s2 = strategy.card(conn, c, sch, sm, 10, None, date.fromisoformat(days[31]), "yellow_q")["items"][0]
    assert s2["confirmed"] and s2["entry"] == 1000 and s2["stop"] == 800 and s2["stop_basis"] == "상장일 종가"
    assert strategy.card(conn, c, sch, sm, 10, None, date.fromisoformat(days[41]), "yellow_q")["items"][0]["state"] == "past"
    # 희석 100% 이상 → ⛔ 만 (전략 배지 없음)
    k = strategy.card(conn, c, sch, dict(sm, dilution_ratio=1.2), 10, 30.0, date.fromisoformat(days[7]), "yellow_q")
    assert k["items"] == [] and k["ban"][0] == "dilution" and k["rank"] == 2
    # 적자 + 괴리 +30% → 🥇 은 살아 있고 금지 규칙은 참고로만
    k = strategy.card(conn, c, sch, sm, -1, 30.0, date.fromisoformat(days[7]), "yellow_q")
    assert [i["key"] for i in k["items"]] == ["s1"] and k["ban"] is None and k["bans"] == ["loss"]
    # 적자 + 괴리 −10% → 남는 전략 없음 → ⛔
    k = strategy.card(conn, c, sch, sm, -1, -10.0, date.fromisoformat(days[7]), "yellow_q")
    assert k["items"] == [] and k["ban"] == ["loss"]
    # 조건 없음(흑자·희석 70%·괴리 +5%) → 해당 전략 없음
    k = strategy.card(conn, c, sch, dict(sm, dilution_ratio=0.7), 10, 5.0, date.fromisoformat(days[7]), "yellow_q")
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
            "stock_on": {days[9]: 1000}, "verdict": "yellow_q"}
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


def test_indicators_use_one_source():
    """v1 버그: 네이버 수정주가(이후 액면분할 반영 → 원주가의 1/5)와 KRX 원주가가 섞여 ATR 이 부풀고 손절선이 음수.
    v2: 네이버 원값(n_*)이 있으면 그것만으로 ATR%·RSI, 손절선 = 진입가(KRX) × (1 − 2 × ATR%)."""
    conn = db.connect(":memory:")
    days = _seed(conn, [5000] * 40, 0)
    for i, d in enumerate(days):
        naver = 1000.0                                        # 같은 날 네이버 수정주가 = 원주가 ÷ 5
        conn.execute("UPDATE stock_daily SET n_close=?, n_high=?, n_low=? WHERE bas_dd=?",
                     (naver, naver + 10, naver - 10, d))
        if i % 3:                                             # KRX 가 없는 날은 저장값도 네이버 값 (섞임)
            conn.execute("UPDATE stock_daily SET close=1000, high=1010, low=990, open=1000 WHERE bas_dd=?", (d,))
    rows = strategy._stock(conn, "111110")
    mixed = strategy.atr(rows[:36])
    assert mixed > 1000                                       # 섞으면 ATR 이 가격보다 커진다 (v1 증상)
    ind = strategy.indicators(rows, days[35])
    assert ind["src"] == "naver" and ind["atr_pct"] == 2.0 and ind["rsi"] == 50.0
    assert strategy.stop_price(5000, ind["atr_pct"]) == 4800  # KRX 진입가 5,000 × (1 − 2 × 2%)
    # 네이버가 없으면(상장폐지) 저장값으로
    assert strategy.indicators([dict(r, n_close=None) for r in rows], days[35])["src"] == "stored"


def test_krx_upsert_keeps_naver_columns_and_migration(tmp_path):
    import sqlite3

    from yujeung.prices import store_stock_rows
    path = tmp_path / "old.db"
    raw = sqlite3.connect(path)                               # n_* 컬럼 없는 옛 DB
    raw.execute("CREATE TABLE stock_daily (bas_dd TEXT NOT NULL, code TEXT NOT NULL, name TEXT, close INTEGER, "
                "open INTEGER, high INTEGER, low INTEGER, volume INTEGER, mktcap INTEGER, list_shrs INTEGER, "
                "PRIMARY KEY (bas_dd, code))")
    raw.commit()
    raw.close()
    conn = db.connect(path)
    conn.execute("INSERT INTO stock_daily (bas_dd, code, close, n_close) VALUES ('2026-09-23', '111110', 3395, 3395)")
    store_stock_rows(conn, [{"BAS_DD": "20260923", "ISU_CD": "111110", "ISU_NM": "x", "TDD_CLSPRC": "3,335"}],
                     {"111110"})
    r = conn.execute("SELECT close, n_close FROM stock_daily").fetchone()
    assert (r["close"], r["n_close"]) == (3335, 3395)          # 가격은 KRX, 네이버 원값은 남음
