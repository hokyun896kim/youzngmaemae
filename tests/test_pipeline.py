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

    def document(self, rcept_no):
        return {"main.xml": self.docs[rcept_no]}


class FakeKrx:
    def rights(self, bas_dd):
        return [RIGHTS_ROW] if bas_dd == "20260923" else []

    def stocks(self, bas_dd, mkt):
        return [{"BAS_DD": bas_dd, "ISU_CD": "210980", "ISU_NM": "SK디앤디", "TDD_CLSPRC": "3,395"}] \
            if bas_dd == "20260923" else []


def cfg():
    return Config("dart", "krx", "", "", db_path=":memory:", gap_alert_pct=20)


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
    run_daily(cfg(), conn, date(2026, 9, 24), lookback_days=90, price_days=3, dart=dart, krx=FakeKrx())

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
    run_daily(cfg(), conn, date(2026, 9, 24), lookback_days=90, price_days=3, dart=dart, krx=FakeKrx())
    assert conn.execute("SELECT COUNT(*) FROM notifications").fetchone()[0] == n

    site = build_site(conn)
    json.dumps(site, ensure_ascii=False)
    [case] = site["cases"]
    assert case["schedule"]["issue_price"] == 2260
    assert case["schedule"]["rights_start"] == "2026-09-21"
    assert case["summary"]["purpose_pct"] == {"채무상환": 100.0}
    assert site["rights_today"][0]["gap"] == -44.0
    assert case["rights_series"][0]["gap"] == -44.0


def test_listing_reminder():
    conn = db.connect(":memory:")
    dart = FakeDart([REPORT], [PIIC_FIELDS], {REPORT["rcept_no"]: PIIC_DOC})
    run_daily(cfg(), conn, date(2026, 10, 27), lookback_days=120, price_days=1, dart=dart, krx=FakeKrx())
    assert conn.execute("SELECT COUNT(*) FROM notifications WHERE topic LIKE '신주상장 D-1%'").fetchone()[0] == 1


def test_dump_restore_roundtrip(tmp_path):
    conn = db.connect(tmp_path / "a.db")
    dart = FakeDart([REPORT], [PIIC_FIELDS], {REPORT["rcept_no"]: PIIC_DOC})
    run_daily(cfg(), conn, date(2026, 9, 24), lookback_days=90, price_days=3, dart=dart, krx=FakeKrx())
    db.save_raw(conn, "x", "k", b"big")
    db.dump_sql(conn, tmp_path / "d.sql")
    conn2 = db.restore_sql(tmp_path / "d.sql", tmp_path / "b.db")
    assert build_site(conn2)["cases"] == build_site(conn)["cases"]
    assert conn2.execute("SELECT COUNT(*) FROM raw_responses").fetchone()[0] == 0
