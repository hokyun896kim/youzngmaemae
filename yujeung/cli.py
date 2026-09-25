"""python -m yujeung <명령>

  daily            감지 → 일정 파싱 → 시세 → 판정·가상성과 → site.json → SQL 덤프 (Actions 가 매일 실행)
  backfill-cases   최근 N개월 유상증자결정 공시를 월 단위로 조회해 진행 중 케이스 채우기 (멱등)
  report-case      종목코드로 케이스 요약 출력 (일정·괴리율 추이·판정·가상성과)
  backfill-rights  KRX 인수권 일별 시세 과거분 적재 (2010-02-12~)
  import-rights    HTS 에서 옮긴 인수권 종가 CSV 적재
  export           site.json 만 다시 생성
  verify           실제 API 를 한 번씩 불러 필드명/응답 형태 확인 (검증 필요 항목 점검)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import db
from .config import DUMP_PATH, SITE_JSON, Config
from .export import write_site


def open_db(cfg: Config):
    if DUMP_PATH.exists():
        return db.restore_sql(DUMP_PATH, cfg.db_path)
    return db.connect(cfg.db_path)


def save(conn, cfg: Config | None = None) -> None:
    write_site(conn, SITE_JSON, cfg)
    db.dump_sql(conn, DUMP_PATH)


KST = timezone(timedelta(hours=9))


def today_kst() -> date:
    """Actions 러너는 UTC 라서 반드시 한국 날짜로 계산 (UTC 23:40 = KST 다음날 08:40)."""
    return datetime.now(KST).date()


def _date(s: str) -> date:
    return datetime.strptime(s.replace("-", ""), "%Y%m%d").date()


def cmd_daily(args, cfg: Config) -> int:
    from .pipeline import run_daily
    conn = open_db(cfg)
    today = _date(args.today) if args.today else today_kst()
    report = run_daily(cfg, conn, today, args.lookback, args.price_days)
    save(conn, cfg)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    errors = [p for p in report.get("prices", []) if "error" in p]
    # 전부 실패했을 때만 실패 처리 (휴장일·미갱신 하루 정도는 정상)
    return 1 if report.get("prices") and len(errors) == len(report["prices"]) else 0


def cmd_backfill_cases(args, cfg: Config) -> int:
    from .pipeline import run_daily
    conn = open_db(cfg)
    today = _date(args.today) if args.today else today_kst()
    report = run_daily(cfg, conn, today, price_days=args.price_days, backfill_months=args.months)
    if not args.dry_run:
        save(conn, cfg)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    for code in args.report or []:
        print_case(conn, cfg, code, today)
    return 0


def print_case(conn, cfg: Config, code: str, today) -> None:
    from .export import _case_json
    rows = conn.execute("SELECT * FROM cases WHERE stock_code=? ORDER BY first_rcept_dt DESC", (code,)).fetchall()
    print(f"\n===== {code} : 케이스 {len(rows)}건 =====")
    for c in rows:
        j = _case_json(conn, c, cfg, today)
        print(f"[case {j['case_id']}] {j['corp_name']} {j['ic_mthn']} 최초공시 {j['first_rcept_dt']} 상태 {j['status']}")
        print("  공시:", " / ".join(f"{h['rcept_dt']} {h['report_nm']}" for h in j["history"]))
        print("  일정:", json.dumps(j["schedule"], ensure_ascii=False))
        if j["schedule_warnings"]:
            print("  일정 경고:", j["schedule_warnings"])
        if not j["is_rights"]:
            continue
        print("  판정:", j["verdict"]["emoji"], j["verdict"]["name"], "|", j["verdict"]["reason"],
              "(잠정)" if j["verdict"]["provisional"] else f"(확정 {j['verdict']['decided_on']})")
        print("  관문1:", "; ".join(f"{x['label']}={x['status']}({x['text']})" for x in j["gate1"]["criteria"]))
        print("  재무/52주:", json.dumps(j["facts"], ensure_ascii=False))
        print("  인수권 괴리율 추이:")
        for p in j["rights_series"]:
            print(f"    {p['d']} {p['name']} 인수권 {p['rights']} 본주 {p['stock']} 발행가 {p['issue']} "
                  f"이론가 {p['fair']} 괴리 {p['gap']}% 원가 {p['cost']}")
        if j["paper"]:
            print("  가상성과:", json.dumps(j["paper"]["eval"], ensure_ascii=False))


def cmd_report_case(args, cfg: Config) -> int:
    conn = open_db(cfg)
    for code in args.codes:
        print_case(conn, cfg, code, today_kst())
    return 0


def cmd_backfill(args, cfg: Config) -> int:
    from .calendar_kr import is_business_day
    from .krx import KrxClient, KrxError
    from .prices import collect_day
    conn = open_db(cfg)
    krx = KrxClient(cfg.krx_api_key, conn)
    d, end, n, fails = _date(args.start), _date(args.end), 0, 0
    while d <= end:
        if d.weekday() < 5 and is_business_day(d):
            try:
                r = collect_day(krx, conn, d.strftime("%Y%m%d"))
                n += r["rights"]
            except KrxError as e:
                fails += 1
                print(e, file=sys.stderr)
        d += timedelta(days=1)
    save(conn)
    print(f"인수권 {n}행 적재, 실패 {fails}일")
    return 0


def cmd_import(args, cfg: Config) -> int:
    from .prices import import_manual_csv
    conn = open_db(cfg)
    print(f"{import_manual_csv(conn, Path(args.csv))}행 적재")
    save(conn)
    return 0


def cmd_export(args, cfg: Config) -> int:
    save(open_db(cfg))
    return 0


def cmd_verify(args, cfg: Config) -> int:
    from .calendar_kr import prev_business_day
    from .dart import DartClient
    from .detect import is_piic_report
    from .krx import KrxClient

    ok = True

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal ok
        ok &= cond
        print(f"{'✅' if cond else '❌'} {name} {detail}")

    def guarded(name, fn):
        try:
            fn()
        except Exception as e:  # noqa: BLE001 — 점검 명령은 모든 오류를 보고만 한다
            check(name, False, f"{type(e).__name__}: {e}")

    def dart_checks():
        dart = DartClient(cfg.dart_api_key)
        end = today_kst()
        items = dart.search((end - timedelta(days=80)).strftime("%Y%m%d"), end.strftime("%Y%m%d"))
        check("DART list.json", bool(items), f"{len(items)}건, 키: {sorted(items[0])[:8] if items else '-'}")
        piic = [i for i in items if is_piic_report(i.get("report_nm", ""))]
        check("유상증자결정 보고서 검색", bool(piic), f"{len(piic)}건")
        from .detect import is_rights_offering
        from .schedule_parser import parse_documents
        need = {"rcept_no", "ic_mthn", "nstk_ostk_cnt", "bfic_tisstk_ostk", "fdpp_dtrp", "fdpp_op"}
        seen, parsed = set(), 0
        for p in piic:
            if p["corp_code"] in seen or len(seen) >= 6:
                continue
            seen.add(p["corp_code"])
            rows = dart.piic_decisions(p["corp_code"], (end - timedelta(days=400)).strftime("%Y%m%d"),
                                       end.strftime("%Y%m%d"))
            row = next((r for r in rows if r.get("rcept_no") == p["rcept_no"]), rows[0] if rows else {})
            check(f"piicDecsn {p['corp_name']}", need <= set(row), f"증자방식={row.get('ic_mthn')} "
                  f"신주={row.get('nstk_ostk_cnt')} 채무상환={row.get('fdpp_dtrp')}")
            # 원문 파서는 주주배정 건으로 최대 3건 실측
            if is_rights_offering(row.get("ic_mthn")) and parsed < 3:
                parsed += 1
                files = dart.document(p["rcept_no"])
                sch = parse_documents(files)
                from .schedule_parser import labeled_rows, table_rows
                price_rows = [(lb, v) for body in files.values() for lb, v in labeled_rows(table_rows(body))
                              if "발행가" in lb][:8]
                print("   발행가 관련 행:", json.dumps(price_rows, ensure_ascii=False))
                print(f"   [{p['report_nm']} {p['rcept_no']}] 원문 파싱:", json.dumps(sch.as_row(), ensure_ascii=False))
                print("   근거:", json.dumps(sch.extras.get("evidence"), ensure_ascii=False))
                print("   경고:", sch.warnings)
        if not parsed:
            print("   (최근 80일 안에 주주배정 건이 없어 원문 파서 실측 못 함)")

    def krx_checks():
        # API 마다 따로 점검: 전부 401 이면 키 문제, 일부만 401 이면 해당 서비스 이용신청 미승인
        krx = KrxClient(cfg.krx_api_key)
        d = prev_business_day(today_kst()).strftime("%Y%m%d")

        def rights_today():
            rows = krx.rights(d)
            need = {"BAS_DD", "ISU_CD", "ISU_NM", "TDD_CLSPRC", "ISU_PRC", "TARSTK_ISU_SRT_CD", "TARSTK_ISU_PRSNT_PRC"}
            check("KRX sr_bydd_trd (신주인수권증서 일별)", need <= set(rows[0]) if rows else True,
                  f"{d} {len(rows)}종목 " + (json.dumps(rows[0], ensure_ascii=False) if rows else "(그날 상장 인수권 없음)"))

        def rights_old():
            check("KRX sr_bydd_trd 과거분(2020-04-14)", True, f"{len(krx.rights('20200414'))}종목")

        def rights_sk():
            sk = [r for r in krx.rights("20260923") if "디앤디" in (r.get("ISU_NM") or "")]
            check("SK디앤디 12R (2026-09-23, 브리프: 636원)", bool(sk),
                  json.dumps(sk[0], ensure_ascii=False) if sk else "못 찾음")

        def tar_price_vs_close():
            # 인수권 행의 TARSTK_ISU_PRSNT_PRC 가 본주 종가인지 확인 (실측: SK디앤디 9/23 3,335 vs 브리프 3,395)
            sk = next((r for r in krx.rights("20260923") if "디앤디" in (r.get("ISU_NM") or "")), None)
            close = next((r.get("TDD_CLSPRC") for r in krx.stocks("20260923", "Y") if r.get("ISU_CD") == "210980"), None)
            tar = sk.get("TARSTK_ISU_PRSNT_PRC") if sk else None
            # 정보용: 달라도 실패가 아님 (괴리율은 이미 stk/ksq 종가 우선으로 계산)
            print(f"{'✅' if tar == close else 'ℹ️'} 대상 본주 가격 vs 본주 종가: "
                  f"TARSTK_ISU_PRSNT_PRC={tar} / stk_bydd_trd 종가={close}"
                  + ("" if tar == close else " → 다름: 괴리율은 stk/ksq 종가로 계산"))

        def stk():
            rows = krx.stocks(d, "Y")
            check("KRX stk_bydd_trd (유가증권 일별)", bool(rows) and "TDD_CLSPRC" in rows[0],
                  f"{len(rows)}종목 " + (json.dumps(rows[0], ensure_ascii=False) if rows else ""))

        def ksq():
            check("KRX ksq_bydd_trd (코스닥 일별)", True, f"{len(krx.stocks(d, 'K'))}종목")

        for name, fn in [("KRX sr_bydd_trd (신주인수권증서 일별)", rights_today), ("KRX sr_bydd_trd 과거분", rights_old),
                         ("SK디앤디 12R", rights_sk), ("대상 본주 가격 비교", tar_price_vs_close),
                         ("KRX stk_bydd_trd (유가증권 일별)", stk),
                         ("KRX ksq_bydd_trd (코스닥 일별)", ksq)]:
            guarded(name, fn)

    def naver_checks():
        from .naver import NaverClient
        n = NaverClient()
        rows = n.daily("210980", 30)
        check("네이버 일봉 210980", bool(rows), f"{len(rows)}일, 마지막 {rows[-1] if rows else '-'}")
        idx = n.daily("KOSPI", 5)
        check("네이버 일봉 KOSPI", bool(idx), f"마지막 {idx[-1] if idx else '-'}")

    def fin_checks():
        dart = DartClient(cfg.dart_api_key)
        res = None
        # 최근 30일 유상증자결정 공시를 낸 상장사 하나로 점검
        items = dart.search((today_kst() - timedelta(days=30)).strftime("%Y%m%d"), today_kst().strftime("%Y%m%d"))
        corp = next((i for i in items if is_piic_report(i.get("report_nm", "")) and i.get("corp_cls") in ("Y", "K")), None)
        if corp:
            res = dart.latest_op_income(corp["corp_code"], today_kst())
        check("DART 재무(직전 분기 영업이익)", res is not None, f"{corp['corp_name'] if corp else '-'} {res}")

    if cfg.dart_api_key:
        guarded("DART", dart_checks)
        guarded("DART 재무", fin_checks)
    else:
        check("DART_API_KEY", False, "없음")
    guarded("네이버 일봉", naver_checks)
    if cfg.krx_api_key:
        guarded("KRX", krx_checks)
    else:
        check("KRX_API_KEY", False, "없음")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="yujeung", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("daily")
    p.add_argument("--today")
    p.add_argument("--lookback", type=int, default=7, help="DART 감지 기간(일)")
    p.add_argument("--price-days", type=int, default=5, help="KRX 재수집 영업일 수")
    p = sub.add_parser("backfill-cases")
    p.add_argument("--months", type=int, default=5)
    p.add_argument("--today")
    p.add_argument("--price-days", type=int, default=5)
    p.add_argument("--dry-run", action="store_true", help="결과를 저장하지 않음 (점검용)")
    p.add_argument("--report", nargs="*", help="끝나고 요약할 종목코드")
    p = sub.add_parser("report-case")
    p.add_argument("codes", nargs="+")
    p = sub.add_parser("backfill-rights")
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p = sub.add_parser("import-rights")
    p.add_argument("csv")
    sub.add_parser("export")
    sub.add_parser("verify")
    args = ap.parse_args(argv)
    cfg = Config.load()
    return {"daily": cmd_daily, "backfill-cases": cmd_backfill_cases, "report-case": cmd_report_case,
            "backfill-rights": cmd_backfill, "import-rights": cmd_import,
            "export": cmd_export, "verify": cmd_verify}[args.cmd](args, cfg)
