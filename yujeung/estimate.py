"""카드 맨 위 '30초 결론' + 발행가 추정 + 본전선 + 어림 손익표 (사이트 자동 계산).

발행가 추정 (d = 증권신고서의 할인율, r = 1주당 배정주식수)
  권리락 전  1차 추정 I1 = 현재가 × (1−d) / (1 + r×d),  권리락 이론가 Px = 현재가 / (1 + r×d)
  권리락 후  2차 추정 I2 = 현재가 × (1−d)   ← 반드시 권리락 '후' 주가
             I1 = 공시된 1차 발행가 (없으면 권리락 직전 종가로 계산),  최종 추정 = min(I1, I2)
  확정발행가가 공시되면 추정 대신 확정값
본전선 (사이클 단계별)
  ① 권리락 전 본주 매수+청약         = Px
  ③ 인수권 거래 중 인수권 매수+청약  = 인수권 가격 + 발행가
  ⑤ 상장 대기 본주 매수              = 현재가   (②·④ 도 이때 할 수 있는 건 본주 매수라 같은 기준)
어림 손익표: 상장일 주가 = 본전선 × (1 + 시나리오)
"""
from __future__ import annotations

import re
from datetime import date

SCENARIOS = [("좋음", 0.15), ("보통", 0.0), ("나쁨", -0.15), ("최악", -0.30)]
SCENARIO_NOTE = ("기본값 시나리오 — Phase 1 백테스트 완료 시 실제 상장일 수익률 분포(25/50/75 퍼센타일)로 "
                 "교체 예정")
OVERHANG_RED_DAYS = 60
AVG_VOLUME_DAYS = 20

STAGES = {
    "1": "① 권리락 전", "2": "② 권리락 후 · 인수권 상장 전", "3": "③ 인수권 거래 중",
    "4": "④ 인수권 종료 · 청약 전", "5": "⑤ 청약 후 · 상장 대기", "listed": "신주 상장 후",
}
CONCLUSION = {"green": "매수 검토", "yellow": "상장일 대기", "blue": "인수권 매도", "white": "패스"}
NEXT_QUARTER = {"1분기": "2Q", "반기": "3Q", "3분기": "4Q", "4분기": "1Q"}


def stage(sch: dict, today: date) -> str:
    t = today.isoformat()
    if sch.get("listing_date") and t >= sch["listing_date"]:
        return "listed"
    if not sch.get("ex_rights_date") or t < sch["ex_rights_date"]:
        return "1"
    rs, re_ = sch.get("rights_start"), sch.get("rights_end")
    if rs and t < rs:
        return "2"
    if rs and re_ and rs <= t <= re_:
        return "3"
    if sch.get("subs_end") and t <= sch["subs_end"]:
        return "4"
    return "5"


def issue_estimate(sch: dict, d: float | None, r: float | None, closes: list[tuple[str, int]],
                   today: date, confirmed: bool) -> dict:
    """closes: [(YYYY-MM-DD, 종가)] 오름차순. 반환 value = 이번 계산에 쓸 발행가."""
    disclosed = sch.get("issue_price")
    if confirmed and disclosed:
        return {"value": disclosed, "kind": "확정", "text": f"확정발행가 {disclosed:,}원"}
    if not d or not r or not closes:
        why = "할인율 미확인" if not d else "배정비율 미확인" if not r else "주가 없음"
        return {"value": disclosed, "kind": "공시", "d": d, "r": r,
                "text": f"공시 발행가 {disclosed:,}원 ({why} — 추정 불가)" if disclosed else f"발행가 미확인 ({why})"}
    ex = sch.get("ex_rights_date")
    p_now = closes[-1][1]
    out = {"d": d, "r": r, "disclosed": disclosed}
    if not ex or today.isoformat() < ex:
        i1 = p_now * (1 - d) / (1 + r * d)
        out.update(value=round(i1), kind="1차 추정", i1=round(i1), px=round(p_now / (1 + r * d)),
                   text=f"1차 추정 {round(i1):,}원 = 현재가 {p_now:,} × (1−{d:.0%}) ÷ (1 + {r:g}×{d:.0%})")
        return out
    pre = [c for dd, c in closes if dd < ex]
    post = [c for dd, c in closes if dd >= ex]
    # 권리락 후엔 1차 발행가가 이미 공시돼 있다(기준일 전 산정) → 공시값이 계산값보다 정확. 없을 때만 계산
    i1 = disclosed or (pre[-1] * (1 - d) / (1 + r * d) if pre else None)
    i1_src = "공시" if disclosed else "추정"
    if not post:
        out.update(value=round(i1) if i1 else None, kind="1차 추정", i1=round(i1) if i1 else None,
                   text="권리락 후 주가 없음 — 1차 추정만")
        return out
    i2 = post[-1] * (1 - d)
    est = min(v for v in (i1, i2) if v)
    out.update(value=round(est), kind="최종 추정", i1=round(i1) if i1 else None, i2=round(i2),
               text=f"최종 추정 {round(est):,}원 = min(1차({i1_src}) {round(i1):,}, 2차 {round(i2):,})"
                    f" · 2차 = 권리락 후 주가 {post[-1]:,} × (1−{d:.0%})" if i1 else
                    f"2차 추정 {round(i2):,}원 (1차 미확인)")
    return out


def breakeven(stg: str, sch: dict, issue: dict, closes: list[tuple[str, int]], rights_close: int | None) -> dict | None:
    if stg == "listed" or not closes:
        return None
    p_now = closes[-1][1]
    if stg == "1":
        d, r = issue.get("d"), issue.get("r")
        if not d or not r:
            return None
        return {"stage": stg, "how": "본주 매수 + 청약", "value": round(p_now / (1 + r * d)),
                "text": f"권리락 이론가 Px = {p_now:,} ÷ (1 + {r:g}×{d:.0%})"}
    if stg == "3":
        if rights_close is None or not issue.get("value"):
            return None
        return {"stage": stg, "how": "인수권 매수 + 청약", "value": rights_close + issue["value"],
                "text": f"인수권 {rights_close:,} + 발행가 {issue['value']:,}"}
    return {"stage": stg, "how": "본주 매수 (상장 대기)", "value": p_now, "text": f"현재가 {p_now:,}"}


def pnl_table(be: dict | None) -> list[dict]:
    if not be:
        return []
    return [{"name": n, "pct": round(s * 100), "price": round(be["value"] * (1 + s))} for n, s in SCENARIOS]


def overhang(new_shares: int | None, volumes: list[int]) -> dict | None:
    """매물 소화일수 = 신주 수 ÷ 최근 20거래일 평균 거래량."""
    vols = [v for v in volumes[-AVG_VOLUME_DAYS:] if v]
    if not new_shares or not vols:
        return None
    avg = sum(vols) / len(vols)
    days = new_shares / avg
    return {"days": round(days, 1), "avg_volume": round(avg), "new_shares": new_shares, "n": len(vols),
            "red": days >= OVERHANG_RED_DAYS}


def _next_quarter(op_period: str | None) -> str:
    m = re.search(r"(1분기|반기|3분기|4분기)", op_period or "")
    return NEXT_QUARTER[m.group(1)] if m else "다음 분기"


def recheck(verdict: str, g1: dict, gap: float | None, op_period: str | None, cheap: float, rich: float) -> str:
    if verdict == "blue":
        return f"괴리율 +{rich:.0f}% 아래로 내려오면 청약 유지 검토"
    if verdict == "green":
        return f"괴리율 {cheap:.0f}% 위로 오르면(할인 축소) 🟡 재판정"
    if verdict == "yellow":
        return f"괴리율 {cheap:.0f}% 이하 시 🟢 인수권 매수+청약 검토"
    if g1.get("hard_fail"):
        return "희석 100% 이상 — 조건이 정정되지 않는 한 재검토 없음 (상장일까지 관찰 샘플)"
    conds = []
    for c in g1["criteria"]:
        if c["status"] != "fail":
            continue
        if c["key"] == "op":
            conds.append(f"{_next_quarter(op_period)} 영업흑자 전환 시")
        elif c["key"] == "pos52":
            conds.append("주가가 52주 범위 중간 아래로 내려오면")
        elif c["key"] == "major":
            conds.append("최대주주 전량 청약 확인 시")
        elif c["key"] == "debt":
            conds.append("자금목적 정정(채무상환 50% 미만) 시")
        elif c["key"] == "dilution":
            conds.append("희석 50% 미만으로 정정 시")
        elif c["key"] == "uw":
            conds.append("총액·잔액인수로 바뀌면")
    return " · ".join(conds) or "상장일까지 관찰 (가설 검증 샘플)"


def conclusion(verdict: str, g1: dict, gap: float | None) -> dict:
    if not g1["passed"]:
        fails = [c["text"].replace(" (100% 이상 즉시 탈락)", "") for c in g1["criteria"] if c["status"] == "fail"]
        reason = "관문1 탈락: " + " · ".join(fails[:3])
    else:
        reason = f"괴리율 {gap:+.1f}%" if gap is not None else "관문1 통과 · 괴리율 대기"
        if g1.get("n_unknown"):
            reason += f" (관문1 미확인 {g1['n_unknown']}개 — GPT 확인)"
    if verdict == "blue" and not g1["passed"]:
        reason = f"인수권 고평가 괴리율 {gap:+.1f}% · " + reason
    return {"word": CONCLUSION[verdict], "reason": reason}


def quick(verdict: str, g1: dict, gap: float | None, sch: dict, facts: dict, closes: list[tuple[str, int]],
          volumes: list[int], rights_close: int | None, new_shares: int | None, dilution: float | None,
          op_period: str | None, today: date, confirmed: bool, cheap: float = -20, rich: float = 20) -> dict:
    stg = stage(sch, today)
    r = sch.get("alloc_ratio") or dilution
    issue = issue_estimate(sch, facts.get("discount"), r, closes, today, confirmed)
    be = breakeven(stg, sch, issue, closes, rights_close)
    return {
        **conclusion(verdict, g1, gap),
        "recheck": recheck(verdict, g1, gap, op_period, cheap, rich),
        "stage": stg, "stage_name": STAGES[stg],
        "issue": issue, "breakeven": be, "table": pnl_table(be), "table_note": SCENARIO_NOTE,
        "overhang": overhang(new_shares, volumes),
    }
