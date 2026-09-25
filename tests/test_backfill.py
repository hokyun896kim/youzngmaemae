"""백필 → 연결 → 판정 → 가상 성과까지 한 번에 (합성 데이터, SK디앤디 흐름을 흉내)."""
import json
from datetime import date, timedelta

from tests.fixtures_dart import PIIC_DOC, PIIC_FIELDS
from tests.test_prices import RIGHTS_ROW
from yujeung import db
from yujeung.calendar_kr import is_business_day
from yujeung.config import Config
from yujeung.export import build_site
from yujeung.pipeline import run_daily
from yujeung.schedule_parser import validate_schedule
from yujeung.verdict import decide, gate1, reason_line

TODAY = date(2026, 11, 26)   # 상장(10/28)+20거래일(11/25) 측정 후, 상장+30일(11/27) 전
SK = {"rcept_no": "20260728000100", "corp_code": "01234567", "corp_name": "SK디앤디", "stock_code": "210980",
      "corp_cls": "Y", "report_nm": "주요사항보고서(유상증자결정)", "rcept_dt": "20260728"}
SK_CORR = dict(SK, rcept_no="20260806000200", rcept_dt="20260806", report_nm="[기재정정]주요사항보고서(유상증자결정)")
SK_FIELDS = dict(PIIC_FIELDS, corp_code="01234567", corp_name="SK디앤디")
# 셀리드: 정정 표시 없이 다시 낸 원공시 (같은 신주수)
CEL1 = {"rcept_no": "20260921000434", "corp_code": "00000299", "corp_name": "셀리드", "stock_code": "299660",
        "corp_cls": "K", "report_nm": "주요사항보고서(유상증자결정)", "rcept_dt": "20260921"}
CEL2 = dict(CEL1, rcept_no="20260922000533", rcept_dt="20260922")
CEL_FIELDS = dict(PIIC_FIELDS, corp_code="00000299", ic_mthn="제3자배정증자", nstk_ostk_cnt="1,333,332",
                  fdpp_dtrp="-", fdpp_op="5,000,000,000")
# 제외 대상들
EMPTY = dict(CEL1, rcept_no="20260910000001", corp_code="00000777", corp_name="빈공시", stock_code="777777")
INTERNAL = dict(CEL1, rcept_no="20260911000001", corp_code="00000888", corp_name="내부증자", stock_code="888888")
INTERNAL_FIELDS = dict(CEL_FIELDS, corp_code="00000888", nstk_ostk_cnt="10,000")
INTERNAL_DOC = """<DOCUMENT><TABLE><TBODY>
<TR><TD>청약일</TD><TD>2026년 09월 20일</TD></TR><TR><TD>납입일</TD><TD>2026년 09월 20일</TD></TR>
</TBODY></TABLE></DOCUMENT>"""
OLD = dict(CEL1, rcept_no="20260710000001", rcept_dt="20260710", corp_code="00000999", corp_name="끝난건",
           stock_code="999999")
OLD_FIELDS = dict(CEL_FIELDS, corp_code="00000999", nstk_ostk_cnt="20,000")
OLD_DOC = "<DOCUMENT><TABLE><TBODY><TR><TD>신주의 상장 예정일</TD><TD>2026년 08월 20일</TD></TR></TBODY></TABLE></DOCUMENT>"


class FakeDart:
    def __init__(self):
        self.reports = [SK, SK_CORR, CEL1, CEL2, EMPTY, INTERNAL, OLD]
        self.fields = {"01234567": [SK_FIELDS, dict(SK_FIELDS, rcept_no=SK_CORR["rcept_no"])],
                       "00000299": [dict(CEL_FIELDS, rcept_no=CEL2["rcept_no"])],
                       "00000777": [{}], "00000888": [INTERNAL_FIELDS], "00000999": [OLD_FIELDS]}
        self.docs = {SK["rcept_no"]: PIIC_DOC, SK_CORR["rcept_no"]: PIIC_DOC.replace("3,060", "2,260"),
                     INTERNAL["rcept_no"]: INTERNAL_DOC, OLD["rcept_no"]: OLD_DOC}
        self.search_calls, self.doc_calls = [], []

    def search(self, bgn, end, pblntf_ty="B", **kw):
        self.search_calls.append((bgn, end))
        return [r for r in self.reports if bgn <= r["rcept_dt"] <= end]

    def piic_decisions(self, corp_code, bgn, end):
        return self.fields.get(corp_code, [])

    def equity_registrations(self, corp_code, bgn, end):
        return {}

    def document(self, rcept_no):
        self.doc_calls.append(rcept_no)
        return {"main.xml": self.docs.get(rcept_no, "<DOCUMENT></DOCUMENT>")}

    def latest_op_income(self, corp_code, today):
        return (-5_000_000_000, "2026 반기(3개월, CFS)")


RIGHTS_CLOSE = {"20260921": 700, "20260922": 660, "20260923": 636, "20260928": 610, "20260929": 600}
STOCK_CLOSE = {"2026-09-21": 3450, "2026-09-22": 3410, "2026-09-23": 3335, "2026-09-28": 3200, "2026-09-29": 3100}


class FakeKrx:
    def __init__(self):
        self.calls = []

    def rights(self, bas_dd):
        self.calls.append(bas_dd)
        if bas_dd not in RIGHTS_CLOSE:
            return []
        return [dict(RIGHTS_ROW, BAS_DD=bas_dd, TDD_CLSPRC=str(RIGHTS_CLOSE[bas_dd]))]

    def stocks(self, bas_dd, mkt):
        d = f"{bas_dd[:4]}-{bas_dd[4:6]}-{bas_dd[6:]}"
        return [{"BAS_DD": bas_dd, "ISU_CD": "210980", "TDD_CLSPRC": str(STOCK_CLOSE[d])}] if d in STOCK_CLOSE else []


def _bdays(start: date, end: date):
    d = start
    while d <= end:
        if is_business_day(d):
            yield d
        d += timedelta(days=1)


class FakeNaver:
    """210980: 2025-08 에 고점 6,000 → 공시 전 3,500 부근 (52주 위치 낮음). 상장일 10/28 시가 2,900."""
    def daily(self, symbol, count=400):
        rows = []
        days = list(_bdays(date(2025, 8, 1), TODAY))
        listing_i = days.index(date(2026, 10, 28))
        for i, d in enumerate(days):
            iso = d.isoformat()
            if symbol in ("KOSPI", "KOSDAQ"):
                c = 2500 + (i - listing_i) * 1.0 if i >= listing_i else 2500
                rows.append({"date": iso, "open": c, "high": c, "low": c, "close": c, "volume": 0})
                continue
            c = 6000 if d.year == 2025 and d.month == 10 else 3500
            c = STOCK_CLOSE.get(iso, c)
            o = c
            if i >= listing_i:
                c = {0: 2950, 5: 3000, 20: 3300}.get(i - listing_i, 3100)
                o = 2900 if i == listing_i else c
            rows.append({"date": iso, "open": o, "high": c, "low": c, "close": c, "volume": 1})
        return rows


def cfg():
    return Config("dart", "krx", db_path=":memory:", gap_alert_pct=20)


def backfill(conn, dart, krx):
    return run_daily(cfg(), conn, TODAY, price_days=2, dart=dart, krx=krx, naver=FakeNaver(), backfill_months=5)


def test_backfill_end_to_end_and_idempotent():
    conn = db.connect(":memory:")
    dart, krx = FakeDart(), FakeKrx()
    backfill(conn, dart, krx)

    # [1] 월 단위(30일) 5구간 조회
    assert len(dart.search_calls) == 5
    assert all(len(set(c)) == 2 for c in dart.search_calls)

    names = sorted(r[0] for r in conn.execute("SELECT corp_name FROM cases"))
    # 백필은 주주배정만 들인다. 빈 공시는 '증자방식·금액 없음', 관찰용(3자배정)은 '백필 제외'
    assert names == ["SK디앤디"]
    reasons = {r[0]: r[1] for r in conn.execute("SELECT rcept_no, reason FROM excluded_disclosures")}
    assert reasons[EMPTY["rcept_no"]] == "증자방식·금액 없음"
    for rep in (CEL1, CEL2, INTERNAL, OLD):
        assert reasons[rep["rcept_no"]] == "백필 제외(비주주배정)"

    # [2] 인수권 isu_cd 앞 6자리로 케이스 연결 + 인수권 기간 과거 시세 보충
    sk_id, sk_first = conn.execute("SELECT case_id, first_rcept_no FROM cases WHERE stock_code='210980'").fetchone()
    assert sk_first == SK["rcept_no"]      # 최근 달부터 조회해도 원공시(7/28)가 최초 공시
    linked = {r[0] for r in conn.execute("SELECT bas_dd FROM rights_daily WHERE case_id=?", (sk_id,))}
    assert linked == {"2026-09-21", "2026-09-22", "2026-09-23", "2026-09-28", "2026-09-29"}

    # [6][7] 판정 스냅샷: 인수권 마지막 날(9/29) 괴리 = 600 / (3100-2260) - 1 = -28.6%
    trade = conn.execute("SELECT * FROM paper_trades WHERE case_id=?", (sk_id,)).fetchone()
    snap = json.loads(trade["snapshot_json"])
    assert trade["verdict"] == "white" and trade["decided_on"] == "2026-09-29"
    assert snap["gap"] == -28.6 and snap["backfilled"] is True
    assert snap["reason"].startswith("채무상환 100% · 희석 240%") and "→ 패스" in snap["reason"]

    assert conn.execute("SELECT status FROM cases WHERE case_id=?", (sk_id,)).fetchone()[0] == "open"

    site = build_site(conn, cfg(), TODAY)
    sk = next(c for c in site["cases"] if c["stock_code"] == "210980")
    ev = sk["paper"]["eval"]
    assert ev["entry"] == 600 + 2260
    rets = [p.get("ret") for p in ev["points"]]
    assert rets == [round((2900 / 2860 - 1) * 100, 1), round((3000 / 2860 - 1) * 100, 1),
                    round((3300 / 2860 - 1) * 100, 1)]
    assert all("excess" in p for p in ev["points"])
    white = next(r for r in site["scorecard"] if r["verdict"] == "white")
    assert white["n"] == 1 and white["done"] == 1 and white["win_rate"] == 100
    assert sk["verdict"]["provisional"] is False

    # 재실행해도 결과 동일 + 제외된 공시의 원문은 다시 받지 않음
    before = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("cases", "disclosures", "excluded_disclosures", "paper_trades", "rights_daily")}
    snap_before = trade["snapshot_json"]
    docs_before = len(dart.doc_calls)
    backfill(conn, dart, krx)
    after = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in before}
    assert after == before
    assert len(dart.doc_calls) == docs_before
    assert conn.execute("SELECT snapshot_json FROM paper_trades WHERE case_id=?", (sk_id,)).fetchone()[0] == snap_before

    # 12/1: 상장+30일(11/27) 경과 → 가상성과가 있으니 지우지 않고 '종료'
    run_daily(cfg(), conn, date(2026, 12, 1), lookback_days=7, price_days=1, dart=dart, krx=krx, naver=FakeNaver())
    assert conn.execute("SELECT status FROM cases WHERE case_id=?", (sk_id,)).fetchone()[0] == "closed"
    assert conn.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0] == 1


def test_daily_merge_internal_and_expired():
    """일일 수집(관찰용 포함): 셀리드 재제출 병합 · 청약일=납입일 제외 · 상장+30일 경과 제외."""
    conn = db.connect(":memory:")
    dart = FakeDart()
    dart.reports = [CEL1, CEL2, INTERNAL, OLD]
    run_daily(cfg(), conn, date(2026, 9, 25), lookback_days=90, price_days=1, dart=dart, krx=FakeKrx(),
              naver=FakeNaver())
    assert [r[0] for r in conn.execute("SELECT corp_name FROM cases")] == ["셀리드"]
    assert conn.execute("SELECT COUNT(*) FROM disclosures d JOIN cases c USING(case_id) "
                        "WHERE c.corp_name='셀리드'").fetchone()[0] == 2
    reasons = {r[0]: r[1] for r in conn.execute("SELECT rcept_no, reason FROM excluded_disclosures")}
    assert reasons[INTERNAL["rcept_no"]].startswith("청약일=납입일")
    assert "경과" in reasons[OLD["rcept_no"]]


def test_merge_existing_duplicate_cases():
    """이미 DB 에 따로 들어가 있던 셀리드 23·29 같은 중복을 합친다."""
    conn = db.connect(":memory:")
    for cid, rn in ((23, CEL1["rcept_no"]), (29, CEL2["rcept_no"])):
        conn.execute("INSERT INTO cases (case_id, corp_code, corp_name, stock_code, corp_cls, first_rcept_no,"
                     " first_rcept_dt, ic_mthn, is_rights, created_at) VALUES (?,?,?,?,?,?,?,?,0,'t')",
                     (cid, "00000299", "셀리드", "299660", "K", rn, rn[:8], "제3자배정증자"))
        conn.execute("INSERT INTO disclosures VALUES (?,?,'piic','r',?,0,?)", (rn, cid, rn[:8], json.dumps(CEL_FIELDS)))
    conn.commit()
    from yujeung.detect import merge_duplicate_cases
    assert merge_duplicate_cases(conn) == 1
    assert [r[0] for r in conn.execute("SELECT case_id FROM cases")] == [23]
    assert conn.execute("SELECT COUNT(*) FROM disclosures WHERE case_id=23").fetchone()[0] == 2


def test_validate_schedule_rules():
    # 인수권 기간 = 청약 기간 → 파싱 실패로 비움 (엔젠바이오·삼성FN리츠 패턴)
    s, w = validate_schedule({"rights_start": "2026-11-03", "rights_end": "2026-11-04",
                              "subs_start": "2026-11-03", "subs_end": "2026-11-04"})
    assert s["rights_start"] is None and any("파싱 실패" in x for x in w)
    # 인수권 마지막 날이 청약 시작 5거래일 전보다 늦음 → 경고 (10/12 청약 → 5거래일 전 10/01)
    s, w = validate_schedule({"rights_start": "2026-09-28", "rights_end": "2026-10-02", "subs_start": "2026-10-12"})
    assert s["rights_end"] == "2026-10-02" and any("5거래일" in x for x in w)
    s, w = validate_schedule({"rights_start": "2026-09-21", "rights_end": "2026-09-29", "subs_start": "2026-10-12"})
    assert w == []


def test_gate_and_verdicts():
    good = {"purpose_pct": {"시설": 80.0, "채무상환": 20.0}, "dilution_ratio": 0.3}
    facts = {"major_holder": {"level": "full"}, "underwriting": "총액인수"}
    g = gate1(good, facts, 1_000_000_000, "2026 반기", 0.3, "좋은회사")
    assert g["passed"] and g["n_pass"] == 6
    assert decide(g, -35.0) == "green"
    assert decide(g, -5.0) == "yellow"
    assert decide(g, None) == "yellow"
    assert decide(g, 25.0) == "blue"
    bad = gate1({"purpose_pct": {"채무상환": 100.0}, "dilution_ratio": 2.4}, {}, None, None, None, "SK디앤디")
    assert not bad["passed"] and bad["hard_fail"]
    assert decide(bad, -40.8) == "white"
    assert reason_line(bad, -40.8, "white") == "채무상환 100% · 희석 240% → 패스 · 괴리 -40.8% → ⚪ 관찰 샘플"
    assert any(c["status"] == "manual" and c["text"] == "GPT 확인 필요" for c in bad["criteria"])
    reit = gate1({"purpose_pct": {"채무상환": 90.0}, "dilution_ratio": 0.2}, {}, None, None, None, "삼성FN리츠")
    assert reit["reit"] and "완화" in reit["reit_note"]
