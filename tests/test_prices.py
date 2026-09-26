from yujeung import db
from yujeung.prices import compute_gap, gaps_for_day, short_code, store_rights_rows

RIGHTS_ROW = {
    "BAS_DD": "20260923", "MKT_NM": "KOSPI", "ISU_CD": "2109801G", "ISU_NM": "SK디앤디 12R",
    "TDD_CLSPRC": "636", "TDD_OPNPRC": "650", "TDD_HGPRC": "700", "TDD_LWPRC": "600",
    "ACC_TRDVOL": "1,234,567", "ACC_TRDVAL": "800,000,000", "LIST_SHRS": "44,681,000",
    "ISU_PRC": "2,260", "DELIST_DD": "20260930", "TARSTK_ISU_SRT_CD": "210980",
    "TARSTK_ISU_NM": "SK디앤디", "TARSTK_ISU_PRSNT_PRC": "3,395",
}


def test_gap_matches_brief_sk_dnd():
    # 브리프 §3 산식 재현 (브리프의 본주 3,395 는 오기 — KRX 실측 종가는 3,335, docs/decisions.md)
    g = compute_gap(636, 3395, 2260)
    assert g.fair == 1135
    assert g.gap_pct == -44.0
    assert g.effective_cost == 2896


def test_gap_sk_dnd_krx_actual():
    g = compute_gap(636, 3335, 2260)          # KRX 실측 9/23
    assert (g.fair, g.gap_pct, g.effective_cost) == (1075, -40.8, 2896)


def test_gap_none_when_out_of_money():
    assert compute_gap(100, 2000, 2260) is None


def test_short_code():
    assert short_code("A210980") == "210980"
    assert short_code("KR7210980009") == "210980"
    assert short_code("210980") == "210980"


def test_store_and_gap_from_krx_row():
    conn = db.connect(":memory:")
    assert store_rights_rows(conn, [RIGHTS_ROW]) == 1
    r = conn.execute("SELECT * FROM rights_daily").fetchone()
    assert (r["bas_dd"], r["close"], r["issue_price"], r["tar_code"], r["delist_dd"]) == \
        ("2026-09-23", 636, 2260, "210980", "2026-09-30")
    [g] = gaps_for_day(conn, "20260923")
    assert g.gap_pct == -44.0


def test_retrying_on_connect_timeout():
    import requests
    from yujeung.http import retrying
    calls, slept = [], []

    def flaky(*a, **kw):
        calls.append(1)
        if len(calls) < 3:
            raise requests.ConnectTimeout("opendart 연결 시간 초과")
        return "ok"
    assert retrying(flaky, sleep=slept.append)("u") == "ok" and slept == [5, 20]
    calls.clear()

    def dead(*a, **kw):
        raise requests.ConnectTimeout("x")
    dead_slept = []
    try:
        retrying(dead, sleep=dead_slept.append)("u")
        raise AssertionError("재시도 후에도 실패면 예외를 올려야 함")
    except requests.ConnectTimeout:
        pass
    assert dead_slept == [5, 20, 60]          # 4번 시도 (09-26 opendart 연결 시간 초과 3연속 실측)


def test_krx_non_json_body_retried_then_krx_error():
    """KRX 가 200 + 빈 본문(JSON 아님)을 주면 재시도, 끝까지 아니면 KrxError — 백테스트가 그날만 건너뛰게
    (실측 2026-09-26 백테스트 2020 이 JSONDecodeError 로 통째로 중단)."""
    import json as _json
    import pytest
    from yujeung.krx import KrxClient, KrxError

    class R:
        def __init__(self, body):
            self.status_code, self.text, self.content = 200, body, body.encode()

        def json(self):
            return _json.loads(self.text)

    bodies = ["", '{"OutBlock_1": [{"ISU_CD": "1"}]}']
    slept = []
    k = KrxClient("key", http_get=lambda *a, **kw: R(bodies.pop(0)), min_interval=0, sleep=slept.append)
    assert k.stocks("20200102", "K") == [{"ISU_CD": "1"}] and slept == [5]
    k2 = KrxClient("key", http_get=lambda *a, **kw: R("<html>점검</html>"), min_interval=0, sleep=slept.append)
    with pytest.raises(KrxError):
        k2.rights("20200102")
