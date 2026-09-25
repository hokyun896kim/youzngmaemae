"""python -m yujeung <명령>

  daily            감지 → 일정 파싱 → 시세 → 알림 → site.json → SQL 덤프 (Actions 가 매일 실행)
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


def save(conn) -> None:
    write_site(conn, SITE_JSON)
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
    save(conn)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    errors = [p for p in report.get("prices", []) if "error" in p]
    # 전부 실패했을 때만 실패 처리 (휴장일·미갱신 하루 정도는 정상)
    return 1 if report.get("prices") and len(errors) == len(report["prices"]) else 0


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
                sch = parse_documents(dart.document(p["rcept_no"]))
                print(f"   [{p['report_nm']} {p['rcept_no']}] 원문 파싱:", json.dumps(sch.as_row(), ensure_ascii=False))
                print("   근거:", json.dumps(sch.extras.get("evidence"), ensure_ascii=False))
                print("   경고:", sch.warnings)
        if not parsed:
            print("   (최근 80일 안에 주주배정 건이 없어 원문 파서 실측 못 함)")

    def krx_checks():
        krx = KrxClient(cfg.krx_api_key)
        d = prev_business_day(today_kst()).strftime("%Y%m%d")
        rows = krx.rights(d)
        need = {"BAS_DD", "ISU_CD", "ISU_NM", "TDD_CLSPRC", "ISU_PRC", "TARSTK_ISU_SRT_CD", "TARSTK_ISU_PRSNT_PRC"}
        check("KRX sr_bydd_trd", need <= set(rows[0]) if rows else True,
              f"{d} {len(rows)}종목 " + (json.dumps(rows[0], ensure_ascii=False) if rows else "(그날 상장 인수권 없음)"))
        old = krx.rights("20200414")
        check("KRX 과거분(2020-04-14)", True, f"{len(old)}종목")
        sk = [r for r in krx.rights("20260923") if "디앤디" in (r.get("ISU_NM") or "")]
        check("SK디앤디 12R (2026-09-23, 브리프: 636원)", bool(sk),
              json.dumps(sk[0], ensure_ascii=False) if sk else "못 찾음")
        stk = krx.stocks(d, "Y")
        check("KRX stk_bydd_trd", bool(stk) and "TDD_CLSPRC" in stk[0],
              f"{len(stk)}종목 " + (json.dumps(stk[0], ensure_ascii=False) if stk else ""))
        ksq = krx.stocks(d, "K")
        check("KRX ksq_bydd_trd", bool(ksq), f"{len(ksq)}종목")

    if cfg.dart_api_key:
        guarded("DART", dart_checks)
    else:
        check("DART_API_KEY", False, "없음")
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
    p = sub.add_parser("backfill-rights")
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p = sub.add_parser("import-rights")
    p.add_argument("csv")
    sub.add_parser("export")
    sub.add_parser("verify")
    args = ap.parse_args(argv)
    cfg = Config.load()
    return {"daily": cmd_daily, "backfill-rights": cmd_backfill, "import-rights": cmd_import,
            "export": cmd_export, "verify": cmd_verify}[args.cmd](args, cfg)
