"""과거 유증 백테스트 (합성 2021년 시나리오)."""
import json
from datetime import date, timedelta

from tests.fixtures_dart import PIIC_DOC, PIIC_FIELDS
from yujeung import backtest, estimate
from yujeung.calendar_kr import KRX_HOLIDAYS
from yujeung.config import Config
from yujeung.dart import DartClient, reports_available

TODAY = date(2026, 9, 26)
HOLIDAYS_2021 = {"2021-02-11", "2021-02-12", "2021-09-20", "2021-09-21", "2021-09-22"}
# 2021 주주배정: 기준일 4/01, 인수권 4/20~26, 확정 4/28, 청약 5/03~04, 납입 5/07, 상장 5/18, 발행가 5,000
DOC_2021 = (PIIC_DOC.replace("3,060", "5,000").replace("2026년 09월 02일", "2021년 04월 01일")
            .replace("2026년 10월 06일", "2021년 04월 28일").replace("2026년 10월 12일", "2021년 05월 03일")
            .replace("2026년 10월 13일", "2021년 05월 04일").replace("2026년 10월 15일", "2021년 05월 07일")
            .replace("2026년 10월 28일", "2021년 05월 18일")
            .replace("2026년 09월 21일부터 2026년 09월 29일까지", "2021년 04월 20일부터 2021년 04월 26일까지"))
A = {"rcept_no": "20210302000100", "corp_code": "00000001", "corp_name": "기출전자", "stock_code": "123450",
     "corp_cls": "E", "report_nm": "주요사항보고서(유상증자결정)", "rcept_dt": "20210302"}   # 지금은 상장폐지(E)
A_CORR = dict(A, rcept_no="20210320000200", rcept_dt="20210320", report_nm="[기재정정]주요사항보고서(유상증자결정)")
B = dict(A, rcept_no="20210601000100", rcept_dt="20210601", corp_code="00000002", corp_name="파싱실패",
         stock_code="222220", corp_cls="K")
PREV = dict(A, rcept_no="20210105000100", rcept_dt="20210105", corp_code="00000003", corp_name="작년건",
            stock_code="333330", corp_cls="Y", report_nm="[기재정정]주요사항보고서(유상증자결정)")
NEXT = dict(B, rcept_no="20220110000100", rcept_dt="20220110", corp_code="00000004", corp_name="내년건",
            stock_code="444440")
THIRD = dict(B, rcept_no="20210701000100", rcept_dt="20210701", corp_code="00000005", corp_name="3자배정",
             stock_code="555550")
UNLISTED = dict(B, rcept_no="20210801000100", rcept_dt="20210801", corp_code="00000006", corp_name="비상장",
                stock_code="", corp_cls="E")
FIELDS = {c: dict(PIIC_FIELDS, corp_code=c, ic_mthn="주주배정후 실권주 일반공모", fdpp_dtrp="-",
                  fdpp_op="10,000,000,000", nstk_ostk_cnt="3,000,000", bfic_tisstk_ostk="10,000,000")
          for c in ("00000001", "00000002", "00000003", "00000004", "00000006")}
FIELDS["00000005"] = dict(FIELDS["00000002"], corp_code="00000005", ic_mthn="제3자배정증자")
RIGHTS_DAYS = ["20210420", "20210421", "20210422", "20210423", "20210426"]
RIGHTS_CLOSE = dict(zip(RIGHTS_DAYS, [1500, 1400, 1300, 1200, 1000]))


def trading_days(a: date, b: date):
    d = a
    while d <= b:
        if d.weekday() < 5 and d.isoformat() not in HOLIDAYS_2021:
            yield d
        d += timedelta(days=1)


DAYS = [d.isoformat() for d in trading_days(date(2019, 1, 2), date(2026, 9, 25))]
LISTING_I = DAYS.index("2021-05-18")


def stock_close(iso: str) -> int:
    i = DAYS.index(iso)
    if i < LISTING_I:
        return 9000 if iso < "2020-09-01" else 7000
    return {0: 6600, 5: 6800, 20: 7200}.get(i - LISTING_I, 6700)


class FakeDart:
    def __init__(self):
        self.reports = [A, A_CORR, B, PREV, NEXT, THIRD, UNLISTED]
        self.asof = {}

    def search(self, bgn, end, pblntf_ty="B", **kw):
        return [r for r in self.reports if bgn <= r["rcept_dt"] <= end]

    def piic_decisions(self, corp_code, bgn, end):
        return [dict(FIELDS[corp_code], rcept_no=r["rcept_no"]) for r in self.reports if r["corp_code"] == corp_code]

    def equity_registrations(self, corp_code, bgn, end):
        self.estk_ranges = getattr(self, "estk_ranges", []) + [(corp_code, bgn, end)]
        return {}

    def document(self, rcept_no):
        return {"main.xml": DOC_2021 if rcept_no.startswith("2021030") or rcept_no.startswith("2021032")
                else "<DOCUMENT></DOCUMENT>"}

    def op_income_asof(self, corp_code, asof):
        self.asof[corp_code] = asof
        return (2_000_000_000, "2021 1분기(3개월, CFS)")


class FakeKrx:
    def __init__(self):
        self.rights_calls, self.stock_calls = [], []

    def rights(self, bas_dd):
        self.rights_calls.append(bas_dd)
        if bas_dd not in RIGHTS_CLOSE:
            return []
        return [{"BAS_DD": bas_dd, "ISU_CD": "1234501G", "ISU_NM": "기출전자 1R", "MKT_NM": "KOSDAQ",
                 "TDD_CLSPRC": str(RIGHTS_CLOSE[bas_dd]), "ISU_PRC": "5,000", "DELIST_DD": "20210427",
                 "TARSTK_ISU_SRT_CD": "123450", "TARSTK_ISU_NM": "기출전자"}]

    def stocks(self, bas_dd, mkt):
        self.stock_calls.append((bas_dd, mkt))
        iso = f"{bas_dd[:4]}-{bas_dd[4:6]}-{bas_dd[6:]}"
        c = stock_close(iso)
        o = 6500 if iso == "2021-05-18" else c
        return [{"BAS_DD": bas_dd, "ISU_CD": "123450", "TDD_CLSPRC": str(c), "TDD_OPNPRC": str(o),
                 "TDD_HGPRC": str(c), "TDD_LWPRC": str(c), "ACC_TRDVOL": "1000"}]


class FakeNaver:
    """지수는 전 기간, 기출전자는 상장폐지라 네이버에 없음(→ 52주 위치 미확인)."""
    def daily(self, symbol, count=400):
        from yujeung.naver import NaverError
        if symbol in ("KOSPI", "KOSDAQ"):
            return [{"date": d, "open": 1000.0, "high": 1000.0, "low": 1000.0,
                     "close": 1000.0 + max(0, i - LISTING_I), "volume": 0} for i, d in enumerate(DAYS)][-count:]
        raise NaverError("없음")


def test_reports_available_no_lookahead():
    got = [(y, r) for _, y, r, _ in reports_available(date(2021, 4, 26))]
    assert got[:3] == [(2020, "11011"), (2020, "11014"), (2020, "11012")]   # 2021 1분기(5/15 기한)는 아직
    assert (2021, "11013") in [(y, r) for _, y, r, _ in reports_available(date(2021, 5, 15))]


def test_op_income_asof_uses_first_available_report():
    class D(DartClient):
        def __init__(self):
            self.calls = []

        def statement(self, corp_code, year, reprt, fs):
            self.calls.append((year, reprt, fs))
            if (year, reprt) == (2020, "11014"):
                return [{"sj_div": "IS", "account_id": "dart_OperatingIncomeLoss", "thstrm_amount": "-300"}]
            return []
    d = D()
    assert d.op_income_asof("x", date(2021, 4, 26)) == (-300, "2020 3분기(3개월, CFS)")
    assert (2021, "11013", "CFS") not in d.calls        # 판정일 이후 기한인 보고서는 조회조차 안 함


def test_backtest_year(tmp_path):
    dart, krx = FakeDart(), FakeKrx()
    cfg = Config("d", "k", db_path=":memory:", gap_alert_pct=20)
    out = backtest.run_year(2021, cfg, dart, krx, FakeNaver(), TODAY, out_dir=tmp_path)
    assert HOLIDAYS_2021 <= KRX_HOLIDAYS                              # 거래일로 과거 휴장일 보충
    c = out["counts"]
    # 대상: 기출전자(상장폐지 E 포함) + 파싱실패. 작년건(정정으로 시작) 제외, 3자배정·비상장 제외
    # 내년건(꼬리 기간, 그 회사 케이스 없음)은 상세 조회조차 안 함 → out_of_year 0
    assert c["cases"] == 2 and c["parse_ok"] == 1 and c["parse_rate"] == 50.0
    assert c["starts_with_correction"] == 1 and c["out_of_year"] == 0
    assert c["missing_by_field"]["record_date"] == 1
    # KRX 인수권은 인수권 기간 날짜만 조회
    assert sorted(krx.rights_calls) == RIGHTS_DAYS
    stock_days = {d for d, _ in krx.stock_calls}
    assert stock_days >= set(RIGHTS_DAYS) and "20210518" in stock_days and len(stock_days) == 5 + 26
    assert {m for _, m in krx.stock_calls} == {"K"}                   # E → 인수권 시장명으로 코스닥
    # 미래 정보 금지: 재무는 판정일(인수권 마지막 날) 기준
    assert dart.asof["00000001"] == date(2021, 4, 26)
    # 증권신고서는 최초 공시 +150일까지만 (몇 년 뒤 다른 유증이 섞이지 않게)
    assert ("00000001", "20210302", "20210730") in dart.estk_ranges

    rec = next(r for r in out["cases"] if r["corp_name"] == "기출전자")
    assert rec["status"] == "scored" and rec["naver"] is False and rec["pos52"] is None
    assert rec["decided_on"] == "2021-04-26"
    # 괴리 = 1000 / (7000 − 5000) − 1 = −50% → 관문1 통과(채무상환 0·희석 30%·흑자, 나머지 미확인) → 🟢
    assert rec["gap"] == -50.0 and rec["verdict"] == "green"
    base = {p["label"]: p for p in rec["base"]["points"]}
    assert rec["base"]["entry"] == 6000
    assert base["상장일 시가"]["ret"] == round((6500 / 6000 - 1) * 100, 1)
    assert base["+20일"]["ret"] == 20.0 and base["+20일"]["excess"] == 20.0 - 2.0
    assert next(r for r in out["cases"] if r["corp_name"] == "파싱실패")["status"] == "parse_fail"
    assert (tmp_path / "2021.json").exists()

    agg = backtest.aggregate(tmp_path)
    assert agg["n_scored"] == 1 and agg["years"][0]["parse_rate"] == 50.0
    green = next(v for v in agg["by_verdict"] if v["verdict"] == "green")
    assert green["n"] == 1 and green["points"][-1]["median"] == 20.0 and green["points"][-1]["win_rate"] == 100
    gap_rows = {r["bucket"]: r for r in next(f for f in agg["filters"] if f["key"] == "gap")["rows"]}
    assert gap_rows["괴리 −40% 이하"]["n"] == 1
    assert agg["card_scenarios"]["green"]["n"] == 1 and agg["card_scenarios"]["green"]["use"] is False
    json.dumps(agg, ensure_ascii=False)


def test_stats_and_card_scenarios():
    pts = [{"ret": r, "excess": r - 1} for r in (-30, -10, 0, 10, 50)]
    s = backtest.stats(pts)
    assert (s["n"], s["win_rate"], s["mean"], s["median"], s["p25"], s["p75"], s["worst"]) == (5, 40, 4.0, 0, -10, 10, -30)
    card = {"white": {"n": 8, "p75": 12.0, "p50": 1.5, "p25": -9.0, "min": -35.0, "use": True}}
    scen, note = estimate.scenarios_for("white", card)
    assert [round(v * 100, 1) for _, v in scen] == [12.0, 1.5, -9.0, -35.0] and "기출 8건" in note
    assert estimate.scenarios_for("green", card) == (estimate.SCENARIOS, estimate.SCENARIO_NOTE)
    t = estimate.pnl_table({"value": 1000}, scen)
    assert [x["price"] for x in t] == [1120, 1015, 910, 650]


def test_tail_skip_keeps_cases_identical():
    """꼬리 기간 상세 조회 생략 전후 감지 결과가 같아야 한다.
    함정: 6월 케이스 회사가 이듬해 1/05 새 주주배정(꼬리 원공시) + 1/15 그 정정 → 원공시를 건너뛰면
    1/15 정정이 2021년 케이스(240일 안)에 붙어 일정이 덮어써진다. 그래서 '케이스가 있는 회사'는 꼬리 원공시도 조회."""
    dart = FakeDart()
    again = dict(B, rcept_no="20220105000100", rcept_dt="20220105")
    again_corr = dict(again, rcept_no="20220115000100", rcept_dt="20220115", report_nm=A_CORR["report_nm"])
    other_corr = dict(NEXT, rcept_no="20220120000100", rcept_dt="20220120", report_nm=A_CORR["report_nm"])
    dart.reports += [again, again_corr, other_corr]
    res = backtest.compare_tail(2021, dart, TODAY)
    assert res["identical"] and res["cases_before"] == res["cases_after"] == 2
    # 생략 효과: 케이스 없는 회사(내년건)의 상세 조회가 빠진다
    assert res["calls_before"]["piic_decisions"] > res["calls_after"]["piic_decisions"]
    assert res["scope_before"]["out_of_year"] == 2 and res["scope_after"]["out_of_year"] == 1

    # 정정만 조회하는 단순 규칙이었다면 1/15 정정이 2021년 케이스에 붙는다 (이 규칙을 쓰지 않는 이유)
    from yujeung import db
    from yujeung.detect import detect, is_correction
    conn = db.connect(":memory:")
    detect(dart, conn, "20210101", "20220430", rights_only=True, listed=("Y", "K", "E"),
           keep=lambda _c, r: r["rcept_dt"] <= "20211231" or is_correction(r["report_nm"]))
    first = conn.execute("SELECT case_id FROM cases WHERE first_rcept_no=?", (B["rcept_no"],)).fetchone()[0]
    assert conn.execute("SELECT 1 FROM disclosures WHERE rcept_no='20220115000100' AND case_id=?", (first,)).fetchone()


def test_returns_never_below_minus_100():
    """수익률 분모 = 투입 원금 → 어떤 판정도 −100% 밑이 나올 수 없다.
    예전 🔵 (가격−발행가)÷인수권−1: 인수권 100 · 발행가 1,000 · 상장 후 785 → −315% (2020 실측 최악 −214.9%)."""
    import sqlite3
    from yujeung import db, paper
    conn = db.connect(":memory:")
    conn.execute("INSERT INTO cases (corp_code, corp_name, stock_code, corp_cls, first_rcept_no, first_rcept_dt, "
                 "ic_mthn, is_rights, created_at) VALUES ('c','폭락','111110','K','r','20200301','주주배정',1,'x')")
    case = conn.execute("SELECT * FROM cases").fetchone()
    days = [d.isoformat() for d in trading_days(date(2020, 5, 4), date(2020, 7, 31))]
    for i, d in enumerate(days):                       # 상장 후 발행가 밑으로, 끝내 0원 근처까지
        p = max(1000 - i * 60, 0)
        conn.execute("INSERT INTO stock_daily (bas_dd, code, close, open, high, low) VALUES (?,?,?,?,?,?)",
                     (d, "111110", p, p, p, p))
        conn.execute("INSERT INTO index_daily (bas_dd, idx, open, high, low, close) VALUES (?,?,?,?,?,?)",
                     (d, "KOSDAQ", 1000, 1000, 1000, 1000))
    sch = {"listing_date": days[0], "issue_price": 1000, "subs_start": "2020-04-20"}
    for verdict in ("green", "yellow", "blue", "white"):
        snap = {"rights_close": 100, "issue_price": 1000, "listing_date": days[0], "reason": "x"}
        trade = {"verdict": verdict, "decided_on": "2020-04-10", "snapshot_json": json.dumps(snap)}
        ev = paper.evaluate(conn, case, trade, sch, TODAY)
        rets = [p["ret"] for p in ev["points"] if "ret" in p]
        assert rets and min(rets) >= -100, (verdict, rets)
        if verdict != "yellow":
            assert ev["entry"] == 1100                  # 🔵도 투입 원금(인수권+발행가)
    blue = paper.evaluate(conn, case, {"verdict": "blue", "decided_on": "2020-04-10", "snapshot_json": json.dumps(
        {"rights_close": 100, "issue_price": 1000, "listing_date": days[0], "reason": "x"})}, sch, TODAY)
    assert blue["points"][1]["ret"] == round((700 / 1100 - 1) * 100, 1)   # +5일 700원
    assert isinstance(conn, sqlite3.Connection)
