import json
from datetime import date

from tests.fixtures_dart import PIIC_DOC, PIIC_FIELDS
from tests.test_prices import RIGHTS_ROW
from yujeung import db
from yujeung.config import Config
from yujeung.detect import is_piic_report, is_rights_offering
from yujeung.export import build_site
from yujeung.pipeline import run_daily


class FakeDart:
    def __init__(self, reports, fields, docs):
        self.reports, self.fields, self.docs = reports, fields, docs

    def search(self, bgn, end, pblntf_ty="B", **kw):
        return [r for r in self.reports if bgn <= r["rcept_dt"] <= end]

    def piic_decisions(self, corp_code, bgn, end):
        return [f for f in self.fields if f["corp_code"] == corp_code]

    def equity_registrations(self, corp_code, bgn, end):
        return {}

    def latest_op_income(self, corp_code, today):
        return None

    def document(self, rcept_no):
        return {"main.xml": self.docs.get(rcept_no, "<DOCUMENT></DOCUMENT>")}


class FakeNaver:
    def daily(self, symbol, count=400):
        return []


class FakeKrx:
    def rights(self, bas_dd):
        return [RIGHTS_ROW] if bas_dd == "20260923" else []

    def stocks(self, bas_dd, mkt):
        return [{"BAS_DD": bas_dd, "ISU_CD": "210980", "ISU_NM": "SK디앤디", "TDD_CLSPRC": "3,395"}] \
            if bas_dd == "20260923" else []


def cfg():
    return Config("dart", "krx", db_path=":memory:", gap_alert_pct=20)


def run(conn, today, dart, krx=None, **kw):
    kw.setdefault("lookback_days", 90)
    kw.setdefault("price_days", 3)
    return run_daily(cfg(), conn, today, dart=dart, krx=krx or FakeKrx(), naver=FakeNaver(), **kw)


REPORT = {"rcept_no": "20260728000100", "corp_code": "01234567", "corp_name": "테스트디앤디",
          "stock_code": "210980", "corp_cls": "Y", "report_nm": "주요사항보고서(유상증자결정)", "rcept_dt": "20260728"}
CORR = dict(REPORT, rcept_no="20260806000200", rcept_dt="20260806",
            report_nm="[기재정정]주요사항보고서(유상증자결정)")


def test_keyword_filters():
    assert is_piic_report("[기재정정]주요사항보고서(유상증자결정)")
    assert not is_piic_report("주요사항보고서(유무상증자결정)")
    assert is_rights_offering("주주배정후 실권주 일반공모")
    assert not is_rights_offering("제3자배정증자")


def test_daily_end_to_end(capsys):
    conn = db.connect(":memory:")
    doc2 = PIIC_DOC.replace("3,060", "2,260")   # 정정: 1차 발행가 확정
    dart = FakeDart([REPORT, CORR], [PIIC_FIELDS, dict(PIIC_FIELDS, rcept_no=CORR["rcept_no"])],
                    {REPORT["rcept_no"]: PIIC_DOC, CORR["rcept_no"]: doc2})
    run(conn, date(2026, 9, 24), dart)

    # 정정은 같은 케이스로 묶인다
    assert conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM schedule_versions").fetchone()[0] == 2

    texts = [r["text"] for r in conn.execute("SELECT text FROM notifications ORDER BY seq")]
    # 헤더 규칙: [작업명 #순번] 소주제
    assert texts[0].startswith("[유증수집 #1] 신규 유증 테스트디앤디")
    assert any(t.startswith("[유증수집 #2] 일정 변경") and "3,060 → 2,260" in t for t in texts)
    assert any("인수권 괴리 SK디앤디 12R" in t and "-44.0%" in t for t in texts)

    # 다시 돌려도 중복 알림 없음
    n = len(texts)
    run(conn, date(2026, 9, 24), dart)
    assert conn.execute("SELECT COUNT(*) FROM notifications").fetchone()[0] == n

    site = build_site(conn, cfg(), date(2026, 9, 24))
    json.dumps(site, ensure_ascii=False)
    [case] = site["cases"]
    assert case["schedule"]["issue_price"] == 2260
    assert case["schedule"]["rights_start"] == "2026-09-21"
    assert case["summary"]["purpose_pct"] == {"채무상환": 100.0}
    assert site["rights_today"][0]["gap"] == -44.0
    assert case["rights_series"][0]["gap"] == -44.0


def test_dump_restore_roundtrip(tmp_path):
    conn = db.connect(tmp_path / "a.db")
    dart = FakeDart([REPORT], [PIIC_FIELDS], {REPORT["rcept_no"]: PIIC_DOC})
    run(conn, date(2026, 9, 24), dart)
    db.save_raw(conn, "x", "k", b"big")
    db.dump_sql(conn, tmp_path / "d.sql")
    conn2 = db.restore_sql(tmp_path / "d.sql", tmp_path / "b.db")
    assert build_site(conn2, cfg(), date(2026, 9, 24))["cases"] == build_site(conn, cfg(), date(2026, 9, 24))["cases"]
    assert conn2.execute("SELECT COUNT(*) FROM raw_responses").fetchone()[0] == 0


def test_only_listed_and_rights_alerts():
    conn = db.connect(":memory:")
    # 이전 버전이 남긴 비상장 케이스 + 알림
    conn.execute("INSERT INTO cases (corp_code, corp_name, stock_code, corp_cls, first_rcept_no, first_rcept_dt,"
                 " ic_mthn, is_rights, created_at) VALUES ('X','비상장','', 'E','20260901000001','20260901',NULL,0,'t')")
    conn.execute("INSERT INTO disclosures VALUES ('20260901000001',1,'piic','r','20260901',0,'{}')")
    conn.execute("INSERT INTO notifications (topic, dedup_key, text, sent_at) "
                 "VALUES ('신규 유증 비상장','new:20260901000001','x','t')")
    conn.commit()

    unlisted = dict(REPORT, rcept_no="20260920000001", corp_code="11111111", corp_name="기타법인",
                    stock_code="", corp_cls="E", rcept_dt="20260920")
    third = dict(REPORT, rcept_no="20260921000001", corp_code="22222222", corp_name="제삼자",
                 stock_code="123456", corp_cls="K", rcept_dt="20260921")
    fields3 = dict(PIIC_FIELDS, rcept_no=third["rcept_no"], corp_code="22222222", ic_mthn="제3자배정증자",
                   nstk_ostk_cnt="1,000")
    dart = FakeDart([REPORT, unlisted, third], [PIIC_FIELDS, fields3], {REPORT["rcept_no"]: PIIC_DOC})
    run(conn, date(2026, 9, 24), dart, price_days=1)

    names = {r[0] for r in conn.execute("SELECT corp_name FROM cases")}
    assert names == {"테스트디앤디", "제삼자"}               # 비상장 제외 + 기존 비상장 정리
    topics = [r[0] for r in conn.execute("SELECT topic FROM notifications")]
    assert "신규 유증 테스트디앤디" in topics
    assert not any("제삼자" in t or "비상장" in t for t in topics)   # 제3자배정은 알림 없음


def test_reparse_on_parser_version_bump():
    conn = db.connect(":memory:")
    dart = FakeDart([REPORT], [PIIC_FIELDS], {REPORT["rcept_no"]: PIIC_DOC})
    run(conn, date(2026, 9, 24), dart, price_days=1)
    # 옛 파서가 남긴 틀린 값 흉내
    conn.execute("UPDATE schedule_versions SET rights_start='2026-10-12', extras_json='{}'")
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM notifications").fetchone()[0]
    run(conn, date(2026, 9, 24), dart, price_days=1)
    assert conn.execute("SELECT rights_start FROM schedule_versions").fetchone()[0] == "2026-09-21"
    assert conn.execute("SELECT COUNT(*) FROM notifications").fetchone()[0] == n   # 재파싱은 알림 없음


def test_correction_discards_old_schedule():
    """정정공시가 뜨면 옛 일정은 버리고 최신 원문 기준 — 정정본에 없는 값(인수권 기간)이 옛 값으로 메워지지 않는다."""
    from yujeung.pipeline import latest_schedule
    conn = db.connect(":memory:")
    corr_doc = PIIC_DOC.replace("2026년 09월 02일", "2026년 09월 09일").split("<P>신주인수권증서")[0] + "</DOCUMENT>"
    dart = FakeDart([REPORT, CORR], [PIIC_FIELDS], {REPORT["rcept_no"]: PIIC_DOC, CORR["rcept_no"]: corr_doc})
    run(conn, date(2026, 9, 24), dart, price_days=1)
    case_id = conn.execute("SELECT case_id FROM cases").fetchone()[0]
    s = latest_schedule(conn, case_id)
    assert s["record_date"] == "2026-09-09" and s["ex_rights_date"] == "2026-09-08"
    assert s.get("rights_start") is None and s.get("rights_end") is None
    # 발행가 구분: 라벨 없음 + 1차 산정일(기준일 9/09 전 3거래일 = 9/04) 전 공시 → 예정
    assert s["issue_kind"] == "예정" and s["issue_rcept_dt"] == CORR["rcept_dt"]
    # 정정 이전 공시만 보면 옛 일정
    assert latest_schedule(conn, case_id, exclude=CORR["rcept_no"])["rights_start"] == "2026-09-21"
