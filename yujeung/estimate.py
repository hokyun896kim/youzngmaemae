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


def issue_estimate(sch: dict, d: float | None, r: float | None, closes: list[tuple[str, int]],
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
    return {"label": label, "kind": kind, "issue": i, "p_minus_i": p - i,
            "gap": round((r / (p - i) - 1) * 100, 1) if r and p > i else None,
            "cost": cost,
            "cost_disc": round((1 - cost / p) * 100, 1) if cost else None,      # 총원가 할인율 = 1 − (R+I)/P (양수 = 쿠션)
            "cushion": cushion,                                                 # 원화 쿠션 = P − (R+I)
            "cushion_atr": round(cushion / atr, 2) if cushion is not None and atr else None,
            "r_for_1atr": round(p - i - atr) if atr and p - i - atr > 0 else None}   # 쿠션이 ATR 1배 남는 인수권 가격 상한


def a_margin(sch: dict, issue: dict, p: int | None, p_date: str | None, r: int | None, r_date: str | None,
             atr_pct: float | None, today: date, end_check: dict | None = None) -> dict | None:
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
    g1 = next((x.get("gap") for x in rows if x["kind"] == "1차"), None)
    g2 = next((x.get("gap") for x in rows if x["kind"] == "예상 최종"), None)
    sp = issue.get("second") or {}
    final = None if confirmed else {
        "i1": i1, "i2": issue.get("i2"), "i_hat": next((x["issue"] for x in rows if x["kind"] == "예상 최종"), None),
        "d": issue.get("d"), "vwap": sp.get("vwap"), "vwap_src": sp.get("vwap_src"), "close_base": sp.get("close_base"),
        "base_date": sp.get("base_date"), "window": sp.get("window"), "fix_date": sch.get("price_fix_date"),
        "projected": sp.get("projected"), "floor": None, "rule": "min(1차, 2차) — 회사별 산식은 증권신고서 확인"}
    return {"p": p, "p_date": p_date, "r": r, "r_date": r_date, "atr": atr, "atr_n": A_ATR_N, "atr_pct": atr_pct,
            "confirmed": confirmed, "rows": rows, "end_check": end_check, "final": final,
            "gap_shift": round(g2 - g1, 1) if g1 is not None and g2 is not None else None,
            "days": [{"key": k, "label": lab, "date": sch.get(k), "left": trading_days_left(today, sch.get(k))}
                     for k, lab in A_DAY_KEYS]}


def supply(new_shares: int | None, dilution: float | None, p: int | None, daily: list[tuple[int, int]],
           listing_volume: int | None = None) -> dict | None:
    """공급충격: 희석(신주 ÷ 증자 전 주식)과 '시장이 실제로 소화해야 하는 물량'을 구분.
    daily = [(종가, 거래량)] 최근순 아님(오름차순). 거래대금은 종가×거래량 근사. 유통주식수는 수집하지 않음 → 미확인."""
    if not new_shares:
        return None
    d = [(c, v) for c, v in daily[-AVG_VOLUME_DAYS:] if c and v]
    avg_vol = sum(v for _, v in d) / len(d) if d else None
    avg_val = sum(c * v for c, v in d) / len(d) if d else None
    return {"new_shares": new_shares, "dilution": round(dilution * 100, 1) if dilution is not None else None,
            "float_ratio": None, "n": len(d),
            "value_days": round(new_shares * p / avg_val, 1) if p and avg_val else None,
            "volume_days": round(new_shares / avg_vol, 1) if avg_vol else None,
            "listing_turnover": round(listing_volume / new_shares, 2) if listing_volume else None}


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
