"""카드 맨 위 '30초 결론' + 발행가 추정 + 본전선 + 어림 손익표 (사이트 자동 계산).

발행가 추정 (d = 증권신고서의 할인율, r = 증자비율 = 신주 ÷ 증자 전 발행주식총수)
  ※ [17] 아이에이 검수: 분모는 1주당 배정주식수(alloc_ratio)가 아니라 증자비율(dilution_ratio).
     배정비율은 자기주식 등을 뺀 주주 기준이라 발행주식총수 기준 증자비율과 다를 수 있다. Px 도 같은 r
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

from .verdict import DISC_FLOOR, base, green_price, unconfirmed

SCENARIOS = [("좋음", 0.15), ("보통", 0.0), ("나쁨", -0.15), ("최악", -0.30)]
SCENARIO_NOTE = ("기본값 시나리오 — Phase 1 백테스트 완료 시 실제 상장일 수익률 분포(25/50/75 퍼센타일)로 "
                 "교체 예정")
OVERHANG_RED_DAYS = 60
AVG_VOLUME_DAYS = 20

STAGES = {
    "1": "① 권리락 전", "2": "② 권리락 후 · 인수권 상장 전", "3": "③ 인수권 거래 중",
    "4": "④ 인수권 종료 · 청약 전", "5": "⑤ 청약 후 · 상장 대기", "listed": "신주 상장 후",
    "tbd": "인수권 일정 미정",
}
TRACKING = "진입 구간 종료 — 성과 추적 중"
CONCLUSION = {"green": "매수 검토", "yellow": "상장일 대기", "blue": "인수권 매도", "white": "패스",
              "green_q": "매수 검토 전 확인 필요", "yellow_q": "상장일 대기 · 확인 필요"}
NEXT_QUARTER = {"1분기": "2Q", "반기": "3Q", "3분기": "4Q", "4분기": "1Q"}


def stage(sch: dict, today: date) -> str:
    t = today.isoformat()
    if sch.get("listing_date") and t >= sch["listing_date"]:
        return "listed"
    if not sch.get("record_date"):
        return "tbd"          # 기준일부터 '추후결정'(실측 경남제약 9/18 정정) 또는 못 찾음
    if not sch.get("ex_rights_date") or t < sch["ex_rights_date"]:
        return "1"
    rs, re_ = sch.get("rights_start"), sch.get("rights_end")
    if not rs and not (sch.get("subs_start") and t >= sch["subs_start"]):
        return "tbd"          # 권리락은 지났는데 인수권 상장기간이 '추후결정'(실측 경남제약)
    if rs and t < rs:
        return "2"
    if rs and re_ and rs <= t <= re_:
        return "3"
    if sch.get("subs_end") and t <= sch["subs_end"]:
        return "4"
    return "5"


SECOND_WINDOW = 5     # 2차 기준주가: 기산일(확정발행가 산정일 = 청약일 전 제3거래일)부터 소급 1주일(5거래일)


def second_price(sch: dict, d: float, bars: list[dict], today: date) -> dict | None:
    """2차 발행가 추정 = min(1주일 가중산술평균주가(VWAP), 기산일 종가) × (1 − 할인율). 권리락 후 주가만 쓴다.
    기산일 전이면 '오늘이 기산일이라면'으로 최근 5거래일로 대신(projected). VWAP = Σ거래대금 ÷ Σ거래량 (KRX),
    거래대금이 없는 날이 섞이면 종가×거래량 근사. bars = [{bas_dd, close, volume?, value?}] 오름차순."""
    ex, fix = sch.get("ex_rights_date"), sch.get("price_fix_date")
    upto = min(fix, today.isoformat()) if fix else today.isoformat()
    post = [b for b in bars if b.get("close") and (not ex or b["bas_dd"] >= ex) and b["bas_dd"] <= upto]
    if not post:
        return None
    win = post[-SECOND_WINDOW:]
    vols = [b.get("volume") or 0 for b in win]
    if all(b.get("value") and b.get("volume") for b in win):
        vwap, src = sum(b["value"] for b in win) / sum(vols), "KRX 거래대금 ÷ 거래량"
    elif sum(vols):
        vwap, src = sum(b["close"] * (b.get("volume") or 0) for b in win) / sum(vols), "종가×거래량 근사 (거래대금 미수집일 포함)"
    else:
        vwap, src = None, "거래량 없음 — 종가만"
    close_base = win[-1]["close"]
    base = min(vwap, close_base) if vwap else close_base
    return {"i2": round(base * (1 - d)), "base": round(base), "vwap": round(vwap) if vwap else None, "vwap_src": src,
            "close_base": close_base, "base_date": win[-1]["bas_dd"], "window": [b["bas_dd"] for b in win],
            "fix_date": fix, "projected": not fix or today.isoformat() < fix, "d": d}


# 발행가 단계 배지 — 화면·프롬프트에서 '발행가'를 단계 없이 쓰지 않는다 (1차가를 확정가로 착각 방지)
#   예정: 이사회 예정발행가만 있음(1차 미산정 — 값은 1차 추정) / 1차: 1차 발행가 산정·공시 /
#   예상최종: 권리락 후 min(1차, 2차 추정) 매일 재계산 / 확정: 확정발행가 공시(또는 청약 시작 후)
ISSUE_STAGES = {"planned": "예정", "first": "1차", "final_est": "예상최종", "confirmed": "확정"}


def issue_stage(issue: dict | None) -> dict:
    kind = (issue or {}).get("kind")
    if kind == "확정":
        code = "confirmed"
    elif kind == "최종 추정":
        code = "final_est"
    elif kind == "1차 공시" or (kind == "공시" and (issue or {}).get("issue_kind") == "1차"):
        code = "first"
    else:                     # 1차 추정 · 공시(예정) · 미확인
        code = "planned"
    return {"code": code, "label": ISSUE_STAGES[code]}


def issue_estimate(sch: dict, d: float | None, r: float | None, closes: list[tuple[str, int]],
                   today: date, confirmed: bool = False, bars: list[dict] | None = None) -> dict:
    out = _issue_estimate(sch, d, r, closes, today, confirmed, bars)
    out["stage"] = issue_stage(out)
    return out


def _issue_estimate(sch: dict, d: float | None, r: float | None, closes: list[tuple[str, int]],
                    today: date, confirmed: bool = False, bars: list[dict] | None = None) -> dict:
    """closes: [(YYYY-MM-DD, 종가)] 오름차순. 반환 value = 이번 계산에 쓸 발행가.
    공시 발행가는 구분(sch.issue_kind)에 따라 다르게 쓴다:
      확정 → 그대로 / 1차('1차' 라벨 또는 1차 산정일 이후 공시) → I1 로 사용 /
      예정(예정발행가 = 이사회 당시 가격) → I1 로 쓰지 않고 권리락 직전 종가(권리락 전이면 현재가)로 계산"""
    disclosed = sch.get("issue_price")
    kind = "확정" if confirmed else (sch.get("issue_kind") or "예정")
    if kind == "확정" and disclosed:
        return {"value": disclosed, "kind": "확정", "issue_kind": kind, "text": f"확정발행가 {disclosed:,}원"}
    if disclosed and sch.get("subs_start") and today.isoformat() >= sch["subs_start"]:
        # 청약이 시작됐으면 발행가는 이미 정해졌다 → 재추정 금지 (실측 SG: 청약 후 '최종 추정 726' 오류)
        return {"value": disclosed, "kind": "확정", "issue_kind": kind,
                "text": f"확정발행가 {disclosed:,}원 (청약 시작 후 — 재추정 안 함, 공시 구분 '{kind}')"}
    if not d or not r or not closes:
        why = "할인율 미확인" if not d else "증자비율 미확인" if not r else "주가 없음"
        return {"value": disclosed, "kind": "공시", "issue_kind": kind, "d": d, "r": r,
                "text": f"공시 {kind}발행가 {disclosed:,}원 ({why} — 추정 불가)" if disclosed else f"발행가 미확인 ({why})"}
    ex = sch.get("ex_rights_date")
    p_now = closes[-1][1]
    out = {"d": d, "r": r, "disclosed": disclosed, "issue_kind": kind}
    use_disclosed = kind == "1차" and bool(disclosed)
    formula = f"× (1−{d:.0%}) ÷ (1 + 증자비율 {r:.1%}×{d:.0%})"
    if not ex or today.isoformat() < ex:
        px = round(p_now / (1 + r * d))
        if use_disclosed:
            out.update(value=disclosed, kind="1차 공시", i1=disclosed, px=px, text=f"1차 발행가(공시) {disclosed:,}원")
        else:
            i1 = round(p_now * (1 - d) / (1 + r * d))
            out.update(value=i1, kind="1차 추정", i1=i1, px=px,
                       text=f"1차 추정 {i1:,}원 = 현재가 {p_now:,} {formula}"
                            + (f" (공시 {disclosed:,}원은 예정발행가라 안 씀)" if disclosed else ""))
        return out
    pre = [c for dd, c in closes if dd < ex]
    post = [c for dd, c in closes if dd >= ex]
    if use_disclosed:
        i1, i1_txt = disclosed, f"1차(공시) {disclosed:,}"
    elif pre:
        i1 = round(pre[-1] * (1 - d) / (1 + r * d))
        i1_txt = f"1차(권리락 직전 종가 {pre[-1]:,} {formula}) {i1:,}"
    else:
        i1, i1_txt = None, "1차 미확인"
    if not post:
        out.update(value=i1, kind="1차 추정", i1=i1, text=f"{i1_txt} — 권리락 후 주가 없음")
        return out
    sp = second_price(sch, d, bars or [{"bas_dd": dd, "close": c} for dd, c in closes], today) or \
        {"i2": round(post[-1] * (1 - d)), "vwap": None, "close_base": post[-1], "projected": True}   # 산정일 창에 시세 없음
    i2 = sp["i2"]
    est = min(v for v in (i1, i2) if v)
    # 최저발행가 제한(액면가·신고서의 하한)은 아직 파싱하지 않는다 → floor 미확인 (min 결과가 하한 밑이면 하한이 확정가)
    base_txt = (f"min(1주 VWAP {sp['vwap']:,}, {'기산일' if not sp['projected'] else '최근'} 종가 {sp['close_base']:,})"
                if sp["vwap"] else f"권리락 후 주가 {sp['close_base']:,}")
    out.update(value=est, kind="최종 추정", i1=i1, i2=i2, second=sp, floor=None,
               text=f"최종 추정 {est:,}원 = min({i1_txt}, 2차 {i2:,}) · 2차 = {base_txt} × (1−{d:.0%})"
                    + (" — 산정일 전이라 오늘 기준 예상" if sp["projected"] else ""))
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
                "text": f"권리락 이론가 Px = {p_now:,} ÷ (1 + 증자비율 {r:.1%}×{d:.0%})"}
    if stg == "3":
        if rights_close is None or not issue.get("value"):
            return None
        return {"stage": stg, "how": "인수권 매수 + 청약", "value": rights_close + issue["value"],
                "text": f"인수권 {rights_close:,} + 발행가 {issue['value']:,}"}
    return {"stage": stg, "how": "본주 매수 (상장 대기)", "value": p_now, "text": f"현재가 {p_now:,}"}


def scenarios_for(verdict: str, card: dict | None) -> tuple[list[tuple[str, float]], str]:
    """판정별 기출(백테스트) 분포가 표본 MIN 이상이면 그걸로, 아니면 기본값. (시나리오, 표 아래 문구)"""
    c = (card or {}).get(verdict) or {}
    if c.get("use"):
        rows = [("좋음(상위 25%)", c["p75"]), ("보통(중앙값)", c["p50"]), ("나쁨(하위 25%)", c["p25"]), ("최악", c["min"])]
        return ([(n, v / 100) for n, v in rows],
                f"기출 {c['n']}건 실제 분포 — 인수권 마지막 날 인수권 매수+청약 → 신주 상장일 시가 수익률의 "
                f"75/50/25 퍼센타일·최저 (data/backtest.json)")
    return SCENARIOS, SCENARIO_NOTE


def pnl_table(be: dict | None, scenarios: list[tuple[str, float]] = SCENARIOS) -> list[dict]:
    if not be:
        return []
    return [{"name": n, "pct": round(s * 100, 1), "price": round(be["value"] * (1 + s))} for n, s in scenarios]


def overhang(new_shares: int | None, volumes: list[int]) -> dict | None:
    """매물 소화일수 = 신주 수 ÷ 최근 20거래일 평균 거래량."""
    vols = [v for v in volumes[-AVG_VOLUME_DAYS:] if v]
    if not new_shares or not vols:
        return None
    avg = sum(vols) / len(vols)
    days = new_shares / avg
    return {"days": round(days, 1), "avg_volume": round(avg), "new_shares": new_shares, "n": len(vols),
            "red": days >= OVERHANG_RED_DAYS}


# ---- A = 인수권 할인 포착: 괴리 → 총원가 쿠션 → ATR 쿠션 → 신주 공급압력 ----
# 본주를 공매도해 가격을 고정할 수 없으니 무위험 차익이 아니다. 인수권을 싸게 사도 청약 → 상장까지 본주가 빠지면 손실.
# 그래서 "−60% 괴리"가 실제로 몇 %의 안전마진(총원가 쿠션)이고, 그 쿠션이 평소 하루 변동(ATR)의 몇 배인지를 본다.
# 쿠션÷ATR 의 합격선은 두지 않는다 — H1 데이터가 쌓일 때까지 연속형으로 기록만.
A_ATR_N = 10
A_DAY_KEYS = (("rights_end", "인수권 매매종료"),("subs_start", "청약 시작"), ("listing_date", "신주 상장"))


def trading_days_left(today: date, target: str | None) -> int | None:
    """오늘(거래일이면 포함)부터 target 까지의 거래일 수. 이미 지났으면 None."""
    if not target or target < today.isoformat():
        return None
    from .calendar_kr import is_business_day
    d, end, n = today, date.fromisoformat(target), 0
    while d <= end:
        n += is_business_day(d)
        d = date.fromordinal(d.toordinal() + 1)
    return n


def rights_end_check(disclosed: str | None, delist: str | None) -> dict | None:
    """인수권 '매매종료일'(마지막 실제 매매가능일)과 KRX '상장폐지일'은 다르다 — 상장폐지일은 매매종료 다음 영업일.
    발행회사 공시(일정의 인수권 종료일)와 KRX(상장폐지일 전 영업일)를 대조한다. 증권사 화면의 종료일은 쓰지 않는다."""
    if not disclosed and not delist:
        return None
    from .calendar_kr import prev_business_day
    krx_last = prev_business_day(date.fromisoformat(delist)).isoformat() if delist else None
    if disclosed and krx_last:
        status = "ok" if disclosed == krx_last else "mismatch"
    else:
        status = "disclosed_only" if disclosed else "krx_only"
    text = {"ok": "공시·KRX 일치", "mismatch": "⚠ 공시와 KRX 불일치 — 원문·KRX 확인",
            "disclosed_only": "공시만 (KRX 인수권 시세 전 — 상장폐지일 미수집)", "krx_only": "KRX만 (공시 일정 미파싱)"}[status]
    return {"last": disclosed or krx_last, "disclosed": disclosed, "delist": delist, "krx_last": krx_last,
            "status": status, "text": text}


def _a_row(label: str, kind: str, p: int, i: int, r: int | None, atr: float | None) -> dict:
    cost = r + i if r else None
    cushion = p - cost if cost else None
    iv_prem = round((r / (p - i) - 1) * 100, 1) if r and p > i else None
    return {"label": label, "kind": kind, "issue": i, "p_minus_i": p - i,
            # 내재가치 IV = max(P−I, 0). R/IV − 1 = 내재가치 대비 프리미엄(구 '괴리율') — 시간가치·발행가 하향 기대가 들어 있어 '오가격'이 아니다.
            # P−I ≤ 0 이면 비율을 내지 않는다(내재가치 0 — 시간가치·발행가 재조정 기대만 존재)
            "iv": max(p - i, 0), "iv_zero": p <= i, "iv_premium": iv_prem,
            "gap": iv_prem,                                                     # 구 키 호환 (= iv_premium)
            "d_implied": p - r - i if r else None,                              # ΔI = 시장 암시 발행가(P−R) − 이 행의 발행가
            "cost": cost,
            "cost_disc": round((1 - cost / p) * 100, 1) if cost else None,      # 총원가 할인율 = 1 − (R+I)/P (양수 = 쿠션)
            "cushion": cushion,                                                 # 원화 쿠션 = P − (R+I)
            "cushion_atr": round(cushion / atr, 2) if cushion is not None and atr else None,
            "r_for_1atr": round(p - i - atr) if atr and p - i - atr > 0 else None}   # 쿠션이 ATR 1배 남는 인수권 가격 상한


def a_margin(sch: dict, issue: dict, p: int | None, p_date: str | None, r: int | None, r_date: str | None,
             atr_pct: float | None, today: date, end_check: dict | None = None,
             current_sch: dict | None = None, realized_issue: dict | None = None,
             r_bar: dict | None = None, p_pre: int | None = None) -> dict | None:
    """발행가 단계는 섞지 않는다: 확정이면 한 줄, 아니면 1차(공시 또는 추정) + 2차 시나리오를 따로."""
    if not p or not sch.get("rights_start"):
        return None
    atr = round(p * atr_pct / 100) if atr_pct else None
    confirmed = issue.get("kind") == "확정"
    kind = issue.get("issue_kind") or sch.get("issue_kind") or "예정"
    # 3층: ① 1차가 기준 R/(P−I₁)−1 · ② 현재 시점 예상 최종가 기준 R/(P−Î_final)−1 · ③ 실제 확정가 기준 R/(P−I_final)−1
    # ①만 보면 min(1차, 2차)로 확정가를 정하는 유증에서 틀린다 — ①과 ②의 차이로 "권리가 비싼 건지,
    # 시장이 미래 발행가 인하를 먼저 반영한 건지"를 가른다.
    rows = []
    i1 = sch.get("issue_price") if kind == "1차" and sch.get("issue_price") else issue.get("i1")
    if i1 and not confirmed:
        rows.append(_a_row("① 1차가 기준" + ("" if kind == "1차" else " (1차 추정 — 공시가 예정발행가라 안 씀)"),
                           "1차", p, i1, r, atr))
    if not confirmed:
        i_hat = issue.get("value") if issue.get("kind") == "최종 추정" else i1
        if i_hat:
            row = _a_row("② 현재 시점 예상 최종가 기준", "예상 최종", p, i_hat, r, atr)
            if issue.get("kind") != "최종 추정":
                row["note"] = "권리락 전 — 2차 미산정, 예상 최종 = 1차"
            rows.append(row)
        rows.append({"label": "③ 실제 확정가 기준", "kind": "확정", "issue": None,
                     "note": f"확정 전 (확정발행가 산정일 {sch.get('price_fix_date') or '미확인'})"})
    elif issue.get("value"):
        rows.append(_a_row("③ 실제 확정가 기준", "확정", p, issue["value"], r, atr))
    if realized_issue and realized_issue.get("value"):
        rr = _a_row("사후 확정가 기준 (결과 · 진입신호 아님)", "사후 확정", p, realized_issue["value"], r, atr)
        rr["note"] = "인수권 거래 당시에는 알 수 없던 확정발행가를 사후 적용한 결과값 — H1 의사결정 신호에 사용 금지"
        rows.append(rr)
    g1 = next((x.get("gap") for x in rows if x["kind"] == "1차"), None)
    g2 = next((x.get("gap") for x in rows if x["kind"] == "예상 최종"), None)
    sp = issue.get("second") or {}
    final = None if confirmed else {
        "i1": i1, "i2": issue.get("i2"), "i_hat": next((x["issue"] for x in rows if x["kind"] == "예상 최종"), None),
        "d": issue.get("d"), "vwap": sp.get("vwap"), "vwap_src": sp.get("vwap_src"), "close_base": sp.get("close_base"),
        "base_date": sp.get("base_date"), "window": sp.get("window"), "fix_date": sch.get("price_fix_date"),
        "projected": sp.get("projected"), "floor": None, "rule": "min(1차, 2차) — 회사별 산식은 증권신고서 확인"}
    cur = current_sch or sch
    out = {"p": p, "p_date": p_date, "r": r, "r_date": r_date, "atr": atr, "atr_n": A_ATR_N, "atr_pct": atr_pct,
           "confirmed": confirmed, "rows": rows, "end_check": end_check, "final": final,
           "issue_stage": issue_stage(issue),
           "decision_asof": p_date, "price_type": "종가" if p_date and p_date < today.isoformat() else "동일일 스냅샷",
           "gap_shift": round(g2 - g1, 1) if g1 is not None and g2 is not None else None,
           "days": [{"key": k, "label": lab, "date": cur.get(k), "left": trading_days_left(today, cur.get(k))}
                    for k, lab in A_DAY_KEYS]}
    row = a_applied_row(out)
    # 시장 암시 발행가: R ≈ P − I 를 뒤집은 I_implied = P − R. 예상 최종가와의 차이 ΔI 로
    # "권리가 비싼가 / 시장이 추가 발행가 인하를 기대하는가 / 인수권이 싼가"를 가른다.
    if r:
        out["implied"] = {"i_implied": p - r, "i_hat": row["issue"] if row else None,
                          "row_kind": row["kind"] if row else None,
                          "d_i": p - r - row["issue"] if row else None,
                          "d_i_pct": round((p - r - row["issue"]) / row["issue"] * 100, 1) if row else None}
    out["exec"] = a_exec(row, p, r, r_bar, atr, cur, r_date or today.isoformat()) if row and r else None
    out["exposure"] = exposure(cur.get("listing_date"), r_date or today.isoformat(),
                               row.get("cushion_atr") if row else None)
    out["funding"] = funding_burden(sch.get("alloc_ratio"), row["issue"] if row else None, p_pre or p,
                                    "권리락 전 종가" if p_pre else "현재 본주")
    out["stage"] = a_stage(out, cur, today)
    return out


# ---- A_exec: 연구용 종가와 '실제로 살 수 있었던 가격'을 분리 ----
# KRX 일별 API 에는 호가가 없다 → R_exec = max(R 종가, R 당일 VWAP) 로 보수 근사 (최우선 매도호가·스프레드 미수집).
# 비용 상수는 가정값 — 증권사 수수료·증권거래세율은 실제 계좌·현행 세법으로 검증 필요.
BUY_FEE_PCT = 0.015      # 인수권 매수 수수료 (가정)
SELL_COST_PCT = 0.20     # 신주 매도 수수료 + 증권거래세 (가정 · 검증 필요)
CARRY_RATE_PCT = 3.5     # 자금 묶임 금융비용 연율 (가정)


def _cal_days(a: str | None, b: str | None) -> int | None:
    if not a or not b or b < a:
        return None
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def a_exec(row: dict, p: int, r: int, r_bar: dict | None, atr: float | None, sch: dict, buy_date: str) -> dict:
    """C_exec = R_exec(1+수수료) + I + 금융비용(R: 매수→상장, I: 납입→상장) + 매도비용(P 기준)."""
    rb = r_bar or {}
    vwap = round(rb["value"] / rb["volume"]) if rb.get("value") and rb.get("volume") else None
    r_exec = max(r, vwap) if vwap else r
    i, lst = row["issue"], sch.get("listing_date")
    pay = sch.get("payment_date") or sch.get("subs_end") or sch.get("subs_start")
    dr, di = _cal_days(buy_date, lst), _cal_days(pay, lst)
    fee = round(r_exec * BUY_FEE_PCT / 100)
    carry = round((r_exec * (dr or 0) + i * (di or 0)) * CARRY_RATE_PCT / 100 / 365)
    sell = round(p * SELL_COST_PCT / 100)
    c = r_exec + fee + i + carry + sell
    return {"r_close": r, "r_vwap": vwap, "r_exec": r_exec, "r_basis": "max(종가, VWAP)" if vwap else "종가(거래대금 없음)",
            "r_volume": rb.get("volume"), "r_range_pct": round((rb["high"] - rb["low"]) / r * 100, 1)
            if rb.get("high") and rb.get("low") else None, "issue": i, "fee": fee, "carry": carry, "sell_cost": sell,
            "carry_days": {"r": dr, "i": di}, "cost": c, "cushion": p - c,
            "cost_disc": round((1 - c / p) * 100, 1), "cushion_atr": round((p - c) / atr, 2) if atr else None,
            "assumptions": f"매수수수료 {BUY_FEE_PCT}% · 매도비용 {SELL_COST_PCT}%(검증 필요) · 금융비용 연 {CARRY_RATE_PCT}% (가정)",
            "missing": "최우선 매도호가·호가 스프레드 미수집 (KRX 일별 API 에 없음)"}


def exposure(listing: str | None, buy_date: str, cushion_atr: float | None) -> dict | None:
    """노출기간 T = 인수권 매수일부터 신주 상장일까지 거래일. 기간보정 쿠션 = (쿠션÷ATR)/√T — H1 연구변수, 매수 기준 아님."""
    if not listing or listing < buy_date:
        return None
    t = trading_days_left(date.fromisoformat(buy_date), listing)
    return {"t_listing": t, "time_adj_cushion": round(cushion_atr / t ** 0.5, 2) if cushion_atr is not None and t else None,
            "note": "√T 정규화는 대략적 기간 보정 — 연구용, 진입 기준으로 쓰지 않음"}


def funding_burden(q: float | None, i: int | None, p_pre: int | None, basis: str) -> dict | None:
    """청약자금 부담률 = q × I / P_pre (q = 구주 1주당 배정 신주). 높을수록 '청약할 돈이 없어 권리라도 판다' 압력 가설(H1 설명변수)."""
    if not q or not i or not p_pre:
        return None
    return {"q": q, "issue": i, "p_pre": p_pre, "basis": basis, "pct": round(q * i / p_pre * 100, 1)}


# ---- A_realized: 인수권 마지막 날 C_exec 로 산 뒤의 결과 (사후값 — 진입신호에 쓰지 않음) ----
A_REALIZED_POINTS = (("D0", 0), ("D+3", 3), ("D+5", 5), ("D+10", 10))


def a_realized(cost: int | None, buy_date: str | None, listing: str | None, bars: list[dict],
               sell_cost_pct: float = SELL_COST_PCT) -> dict | None:
    """수익률은 (P_t − C)/C, 매도비용은 C_exec 에 이미 포함. MAE/MFE = 매수 다음 날 ~ D+10 종가 기준 최저/최고 평가손익."""
    if not cost or not buy_date or not listing:
        return None
    post = [b for b in bars if b["bas_dd"] >= listing and b.get("close")]
    if not post:
        return None
    pts = []
    for lab, k in A_REALIZED_POINTS:
        b = post[k] if k < len(post) else None
        pts.append({"label": lab, "date": b["bas_dd"] if b else None, "price": b["close"] if b else None,
                    "ret": round((b["close"] - cost) / cost * 100, 1) if b else None})
    end = post[min(10, len(post) - 1)]["bas_dd"]
    path = [b["close"] for b in bars if buy_date < b["bas_dd"] <= end and b.get("close")]
    return {"cost": cost, "buy_date": buy_date, "points": pts,
            "mae": round((min(path) - cost) / cost * 100, 1) if path else None,
            "mfe": round((max(path) - cost) / cost * 100, 1) if path else None,
            "path_end": end, "complete": len(post) > 10,
            "note": "사후 결과값(A_realized) — 확정발행가·상장 후 가격 사용, 진입조건에 쓰지 않음. MAE/MFE 는 종가 기준"}


# A 3단계 — R(인수권 실측 시세)이 없을 때부터 'A 후보'로 랭킹하지 않는다.
#   사전감시: 인수권 상장 전(R 없음) — 감시 목록일 뿐 후보·랭킹 아님. 쿠션이 ATR 1배 남는 R 상한만 미리 본다
#   가격관찰: R 실측 + 아직 매매 가능 + 체결가능 쿠션 ≤ 0 (C_exec ≥ P)
#   조건충족: R 실측 + 아직 매매 가능 + 체결가능 쿠션 > 0 (C_exec < P — 종가 R+I 보다 보수적)
# 쿠션÷ATR 은 합격선 없이 연속형으로만 표시한다 (brief: H1 데이터 축적 전 임의 기준 금지).
# 인수권 매매종료일이 지났으면 A 단계 없음(None).
A_STAGES = {"prewatch": "A 사전감시", "price": "A 가격관찰", "met": "A 조건충족"}
A_ROW_ORDER = ("확정", "예상 최종", "1차")     # 적용 발행가 = 가장 늦은 단계 (사후 확정은 의사결정에 안 씀)


def a_applied_row(a: dict | None) -> dict | None:
    rows = [r for r in (a or {}).get("rows") or [] if r.get("issue") is not None]
    return next((r for k in A_ROW_ORDER for r in rows if r["kind"] == k), None)


def a_stage(a: dict, sch: dict, today: date) -> dict | None:
    last = (a.get("end_check") or {}).get("last") or sch.get("rights_end")
    if last and last < today.isoformat():
        return None
    row = a_applied_row(a)
    base = {"row_kind": row["kind"] if row else None}
    if not a.get("r"):
        start = sch.get("rights_start")
        when = f"인수권 상장 {start}" if start else "인수권 상장일 미정"
        hint = f" · 쿠션이 ATR 1배 남는 R 상한 {row['r_for_1atr']:,}원" if row and row.get("r_for_1atr") else ""
        return {**base, "code": "prewatch", "label": A_STAGES["prewatch"],
                "why": f"R 없음({when}) — 감시만, 랭킹 대상 아님{hint}"}
    # 판정은 체결가능 기준(C_exec = R_exec + I + 수수료·금융비용·매도비용)이 있으면 그것으로 — 종가 기준보다 보수적
    ex = a.get("exec")
    if ex and ex["cushion"] > 0:
        return {**base, "code": "met", "label": A_STAGES["met"], "basis": "C_exec",
                "why": f"C_exec {ex['cost']:,} < P {a['p']:,} — 체결가능 쿠션 {ex['cushion']:,}원 "
                       f"(할인율 {ex['cost_disc']:+.1f}%, 쿠션÷ATR {ex['cushion_atr'] if ex['cushion_atr'] is not None else '미확인'})"}
    if not ex and row and row.get("cushion") is not None and row["cushion"] > 0:
        return {**base, "code": "met", "label": A_STAGES["met"], "basis": "R+I",
                "why": f"R+I {row['cost']:,} < P {a['p']:,} — 원화 쿠션 {row['cushion']:,}원 "
                       f"(총원가 할인율 {row['cost_disc']:+.1f}%, 쿠션÷ATR {row['cushion_atr'] if row['cushion_atr'] is not None else '미확인'})"}
    if ex:
        return {**base, "code": "price", "label": A_STAGES["price"], "basis": "C_exec",
                "why": f"C_exec {ex['cost']:,} ≥ P {a['p']:,} — 체결가능 쿠션 {ex['cushion']:,}원 (종가 기준 R+I {row['cost']:,})"
                       + (f" · R ≤ {row['r_for_1atr']:,}원이면 종가 기준 쿠션 ATR 1배" if row.get("r_for_1atr") else "")}
    why = (f"R+I {row['cost']:,} ≥ P {a['p']:,} — 쿠션 {row['cushion']:,}원"
           + (f" · R ≤ {row['r_for_1atr']:,}원이면 쿠션 ATR 1배" if row.get("r_for_1atr") else "")
           if row and row.get("cost") else "적용 발행가 미확인")
    return {**base, "code": "price", "label": A_STAGES["price"], "why": why}


def supply(new_shares: int | None, dilution: float | None, p: int | None, daily: list[tuple[int, int]],
           listing_bar: dict | None = None, listing_price_type: str | None = None,
           listing_volume: int | None = None, baseline_complete: bool = False,
           baseline_start: str | None = None, baseline_end: str | None = None,
           post_volumes: list[int] | None = None) -> dict | None:
    """공급충격. D-1까지 자료가 실제로 채워졌을 때만 기준을 'D-20~D-1'로 확정한다.
    그 전에는 같은 계산값을 '현재 최근20(예비)'로 명시해 미래 구간을 이미 관측한 것처럼 보이지 않게 한다.
    listing_bar는 D0 실측(장중이면 명시)용."""
    if not new_shares:
        return None
    d = [(c, v) for c, v in daily[-AVG_VOLUME_DAYS:] if c and v]
    avg_vol = sum(v for _, v in d) / len(d) if d else None
    avg_val = sum(c * v for c, v in d) / len(d) if d else None
    lb = listing_bar or {}
    lv = lb.get("volume") or listing_volume
    lval = lb.get("value")
    lvwap = round(lval / lv) if lval and lv else None
    lclose, llow, lhigh = lb.get("close"), lb.get("low"), lb.get("high")
    volume_days = round(new_shares / avg_vol, 1) if avg_vol else None
    # 평균은 직전 급등 한두 번에 부풀어 공급부담을 작게 보이게 한다 → 20일 거래량 중앙값 기준도 같이
    vs = sorted(v for _, v in d)
    med_vol = (vs[len(vs) // 2] if len(vs) % 2 else (vs[len(vs) // 2 - 1] + vs[len(vs) // 2]) / 2) if vs else None
    # 신주대비 거래회전율(구 'D0 소화율') = 거래량 ÷ 신주 — 같은 주식이 여러 번 손바뀜해도 세므로 '소화'가 아니다.
    # 초과 회전율 = (거래량 − ADV20) ÷ 신주: 평소 거래분을 뺀, 신주 상장 때문에 늘었다고 볼 수 있는 거래
    pv = [v for v in (post_volumes or []) if v is not None][:6]
    excess_d0 = round((lv - avg_vol) / new_shares, 3) if lv and avg_vol else None
    excess_d5 = round(sum(v - avg_vol for v in pv) / new_shares, 3) if len(pv) == 6 and avg_vol else None
    return {
            "median_volume": round(med_vol) if med_vol else None,
            "volume_days_median": round(new_shares / med_vol, 1) if med_vol else None,
            "effective_shares": None,
            "effective_note": "보호예수·법적 매각제한 물량 미파싱 → 신주 전체로 계산 (말로 한 '장기보유'는 차감하지 않음)",
            "excess_turnover_d0": excess_d0, "excess_turnover_d0_d5": excess_d5,
            "excess_d5_days": len(pv),"new_shares": new_shares, "dilution": round(dilution * 100, 1) if dilution is not None else None,
            "float_ratio": None, "n": len(d),
            "baseline_complete": bool(baseline_complete),
            "baseline_label": "D-20~D-1" if baseline_complete else "현재 최근20(예비)",
            "baseline_start": baseline_start, "baseline_end": baseline_end,
            "value_days": round(new_shares * p / avg_val, 1) if p and avg_val else None,
            "volume_days": volume_days,
            "red": bool(volume_days is not None and volume_days >= OVERHANG_RED_DAYS),
            "red_threshold_days": OVERHANG_RED_DAYS,
            "avg_volume": round(avg_vol) if avg_vol else None,
            "listing_turnover": round(lv / new_shares, 3) if lv else None,
            "listing_volume_multiple": round(lv / avg_vol, 2) if lv and avg_vol else None,
            "listing_vwap": lvwap,
            "listing_close_vs_vwap": round((lclose / lvwap - 1) * 100, 1) if lclose and lvwap else None,
            "listing_close_location": round((lclose - llow) / (lhigh - llow) * 100, 1)
                                      if lclose and llow is not None and lhigh is not None and lhigh > llow else None,
            "listing_low_recovery": round((lclose / llow - 1) * 100, 1) if lclose and llow else None,
            "listing_price_type": listing_price_type}


def _next_quarter(op_period: str | None) -> str:
    m = re.search(r"(1분기|반기|3분기|4분기)", op_period or "")
    return NEXT_QUARTER[m.group(1)] if m else "다음 분기"


def recheck(verdict: str, g1: dict, gap: float | None, op_period: str | None, cheap: float, rich: float) -> str:
    if verdict.endswith("_q"):
        items = " · ".join(u["label"] for u in unconfirmed(g1))
        return f"{items} → GPT로 확인되면 {'🟢' if verdict == 'green_q' else '🟡'} 확정, 하나라도 탈락이면 ⚪"
    if verdict == "blue":
        return f"괴리율 +{rich:.0f}% 아래로 내려오면 청약 유지 검토"
    if verdict == "green":
        return f"괴리율 {cheap:.0f}% 위로 오르면(할인 축소) 🟡 재판정"
    if verdict == "yellow":
        return f"괴리율 {cheap:.0f}% 이하 + 신주원가 할인율 {DISC_FLOOR:.0f}% 초과(너무 깊지 않게) 시 🟢 인수권 매수+청약 검토"
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


def conclusion(verdict: str, g1: dict, gap: float | None, stg: str | None = None, disc: float | None = None) -> dict:
    if not g1["passed"]:
        fails = [c["text"].replace(" (100% 이상 즉시 탈락)", "") for c in g1["criteria"] if c["status"] == "fail"]
        reason = "관문1 탈락: " + " · ".join(fails[:3])
    else:
        reason = f"괴리율 {gap:+.1f}%" if gap is not None else "관문1 통과 · 괴리율 대기"
        if disc is not None:
            reason += f" · 신주원가 할인율 {disc:+.1f}%"
        if g1.get("n_unknown"):
            reason += f" (관문1 미확인 {g1['n_unknown']}개 — GPT 확인)"
    if verdict == "blue" and not g1["passed"]:
        reason = f"인수권 고평가 괴리율 {gap:+.1f}% · " + reason
    word = CONCLUSION[verdict]
    if base(verdict) in ("green", "blue") and stg in ("4", "5", "listed"):
        word = TRACKING       # 인수권 거래가 끝나 이제 들어갈 수 없다 — 판정은 가상 성과로 추적
    return {"word": word, "reason": reason}


def quick(verdict: str, g1: dict, gap: float | None, sch: dict, facts: dict, closes: list[tuple[str, int]],
          volumes: list[int], rights_close: int | None, new_shares: int | None, dilution: float | None,
          op_period: str | None, today: date, confirmed: bool, cheap: float = -20, rich: float = 20,
          card: dict | None = None, disc: float | None = None, bars: list[dict] | None = None) -> dict:
    stg = stage(sch, today)
    r = dilution or sch.get("alloc_ratio")    # 증자비율 우선 ([17]) — 없을 때만 배정비율
    issue = issue_estimate(sch, facts.get("discount"), r, closes, today, confirmed, bars)
    be = breakeven(stg, sch, issue, closes, rights_close)
    scen, note = scenarios_for(verdict, card)
    tracking = base(verdict) in ("green", "blue") and stg in ("4", "5", "listed")
    return {
        **conclusion(verdict, g1, gap, stg, disc),
        # 🟢 가격 조건 두 숫자 나란히 (카드 표시용)
        "green_check": {"gap": gap, "disc": disc, "cheap": cheap, "disc_floor": DISC_FLOOR,
                        "gap_ok": gap is not None and gap <= cheap, "disc_ok": disc is not None and disc > DISC_FLOOR,
                        "ok": green_price(gap, disc, cheap)},
        "recheck": ("신주 상장일 시가 · +5 · +20거래일 가상 성과로 판정 검증" if tracking
                    else recheck(verdict, g1, gap, op_period, cheap, rich)),
        "stage": stg, "stage_name": STAGES[stg],
        "issue": issue, "breakeven": be, "table": pnl_table(be, scen), "table_note": note,
        "overhang": overhang(new_shares, volumes),
    }


# ---- B⑥ 3분할: 공시 전 추세 / 공시 충격 / 이후 지속 (시장지수 대비 초과수익, 단순 차감) ----
# "원래 떨어지던 주식이 계속 떨어진 것"과 "유증 때문에 꺾인 것"을 가른다. 자동 관문이 아니라 판단 보조.
# t0 = 최초 공시일 이후 첫 거래일(공시 시각 미수집 — 장중 공시면 t0 당일, 장마감 후면 사실상 t0+1 반응).
# 권리락은 기계적 하락이라 이론 권리락가 비율로 보정(KRX 권리락 기준가 아님 — H3 와 같은 한계).
def _ret(a: float | None, b: float | None) -> float | None:
    return (b / a - 1) * 100 if a and b else None


def b6_decompose(stock: list[tuple[str, int]], index: list[tuple[str, float]], announce: str | None,
                 today: str, ex_date: str | None = None, ex_factor: float | None = None,
                 index_name: str = "지수") -> dict | None:
    if not announce or not stock or not index:
        return None
    idx = dict(index)
    days = [d for d, _ in stock if d in idx and d <= today]
    px = {d: c * (ex_factor if ex_date and ex_factor and d < ex_date else 1) for d, c in stock}
    t0 = next((k for k, d in enumerate(days) if d >= announce), None)
    if t0 is None or t0 < 1:
        return None

    def ar(i0: int, i1: int) -> dict | None:
        if i0 < 0 or i1 >= len(days) or i1 <= i0:
            return None
        a, b = days[i0], days[i1]
        rs, ri = _ret(px[a], px[b]), _ret(idx[a], idx[b])
        return {"from": a, "to": b, "stock": round(rs, 1), "index": round(ri, 1), "ar": round(rs - ri, 1)}

    last = len(days) - 1
    pre = ar(t0 - 21, t0 - 1) or ar(0, t0 - 1)
    out = {"t0": days[t0], "index_name": index_name,
           "pretrend": pre, "pretrend_full": bool(pre and t0 >= 21),
           "shock": ar(t0 - 1, t0 + 1), "shock3": ar(t0 - 1, t0 + 3),
           "persistence": ar(t0 + 1, last), "total": ar(t0 - 1, last),
           "ex_adjusted": bool(ex_date and ex_factor and ex_date <= days[last]),
           "note": "초과수익 = 종목 − 시장지수 단순 차감(업종지수 미수집). 권리락은 이론가 비율 보정"}
    p_, s_ = (out["pretrend"] or {}).get("ar"), (out["shock"] or {}).get("ar")
    if p_ is not None and s_ is not None:
        out["read"] = ("공시 충격 우세 — 유증으로 눌렸을 가능성" if s_ < 0 and abs(s_) > abs(min(p_, 0))
                       else "기존 하락 추세 우세 — 유증 때문이라 보기 어려움" if p_ < 0 and abs(p_) >= abs(min(s_, 0))
                       else "뚜렷한 유증 충격 없음")
    return out


def ex_rights_factor(p_pre: int | None, r: float | None, i: int | None) -> float | None:
    """권리락 이론가 비율 Px/P = (P + r·I)/((1+r)·P). 권리락 전 가격에 곱하면 권리락 후와 비교 가능."""
    if not p_pre or not r or not i:
        return None
    return (p_pre + r * i) / ((1 + r) * p_pre)
