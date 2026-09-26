"""자동 판정.

관문 1 (회사·조건) — brief 의 필터를 자동화 가능한 것부터:
  채무상환 < 50% · 희석 < 50% (100% 이상이면 즉시 탈락) · 최대주주 전량 이상 청약 ·
  직전 분기 영업흑자 · 52주 위치 ≤ 50% · 총액/잔액인수
  (업계 1~3위 · 대체 불가 사업은 자동화 불가 → 'GPT 확인 필요')
관문 2 (가격) — 인수권 괴리율

4단계 판정
  🟢 green  관문1 통과 + 인수권 저평가     → 인수권 매수 + 청약 (B+A)
  🟡 yellow 관문1 통과, 괴리 신호 없음      → 신주 상장일 매물 후 본주 매수 (B)
  🔵 blue   인수권 고평가                   → 인수권 마지막 날 매도 vs 청약 유지 비교 (A 매도)
  ⚪ white  관문1 탈락                      → 관찰 샘플 (인수권 매수+청약 가정으로 기록, 가설 검증용)
  🟢? green_q / 🟡? yellow_q  관문1 자동 6개 중 '미확인'이 하나라도 있으면 🟢/🟡 대신 "확인 필요" (v2~).
      업계 1~3위·대체 불가(수동 2개)는 늘 GPT 확인 대상이라 이 규칙에서 뺀다.
      가상 성과·백테스트는 따로 집계 → "미확인 포함 🟢가 실제로 얼마나 틀렸나" 비교용
"""
from __future__ import annotations

LOGIC_VERSION = 2   # 2: 관문1 자동 항목 미확인 → 🟢?/🟡? 확인 필요

# 순서 = 화면 정렬·집계 순서 (확인 필요는 🟢/🟡 바로 다음)
VERDICTS = {
    "green": ("🟢", "인수권 매수+청약"),
    "yellow": ("🟡", "상장일 후 본주 매수"),
    "green_q": ("🟢?", "확인 필요 · 인수권 매수+청약 후보"),
    "yellow_q": ("🟡?", "확인 필요 · 상장일 후 본주 매수 후보"),
    "blue": ("🔵", "인수권 매도 vs 청약"),
    "white": ("⚪", "관찰 샘플"),
}

# 미확인일 때 화면·프롬프트에 쓰는 항목명
UNKNOWN_LABEL = {"dilution": "희석률 미확인", "major": "최대주주 청약 여부 미확인", "op": "직전 분기 영업이익 미확인",
                 "pos52": "52주 위치 미확인", "uw": "인수 방식(총액·잔액인수) 미확인", "debt": "자금 목적(채무상환) 미확인"}


def base(verdict: str) -> str:
    """확인 필요(green_q/yellow_q) → 원래 판정. 진입 방식·측정 시점은 원래 판정을 따른다."""
    return verdict[:-2] if verdict.endswith("_q") else verdict


def unconfirmed(g1: dict) -> list[dict]:
    """관문1 자동 항목 중 미확인 (수동 2개 제외)."""
    return [{"key": c["key"], "label": UNKNOWN_LABEL.get(c["key"], c["label"] + " 미확인")}
            for c in g1["criteria"] if c["status"] == "unknown"]


def is_reit(corp_name: str) -> bool:
    return "리츠" in corp_name or "부동산투자회사" in corp_name


def _c(key, label, status, text):
    return {"key": key, "label": label, "status": status, "text": text}


def gate1(summary: dict, facts: dict, op_income: int | None, op_period: str | None,
          pos52: float | None, corp_name: str = "") -> dict:
    """관문 1. status: pass / fail / unknown(자료 없음) / manual(GPT 확인 필요)."""
    crit = []
    debt = (summary.get("purpose_pct") or {}).get("채무상환", 0.0)
    crit.append(_c("debt", "채무상환 < 50%", "pass" if debt < 50 else "fail", f"채무상환 {debt:.0f}%"))

    dil = summary.get("dilution_ratio")
    if dil is None:
        crit.append(_c("dilution", "희석 < 50%", "unknown", "희석 미확인"))
    else:
        txt = f"희석 {dil * 100:.0f}%" + (" (100% 이상 즉시 탈락)" if dil >= 1 else "")
        crit.append(_c("dilution", "희석 < 50%", "pass" if dil < 0.5 else "fail", txt))

    mh = (facts or {}).get("major_holder") or {}
    level = mh.get("level")
    if level == "full":
        crit.append(_c("major", "최대주주 전량 이상 청약", "pass", "최대주주 전량 청약(원문)"))
    elif level in ("partial", "none"):
        pct = f" {mh.get('pct'):.0f}%" if mh.get("pct") is not None else ""
        crit.append(_c("major", "최대주주 전량 이상 청약", "fail",
                       "최대주주 불참" if level == "none" else f"최대주주 일부 청약{pct}"))
    else:
        crit.append(_c("major", "최대주주 전량 이상 청약", "unknown", "최대주주 청약 GPT 확인 필요"))

    if op_income is None:
        crit.append(_c("op", "직전 분기 영업흑자", "unknown", "영업이익 미확인"))
    else:
        crit.append(_c("op", "직전 분기 영업흑자", "pass" if op_income > 0 else "fail",
                       f"영업{'이익' if op_income > 0 else '손실'} {op_income / 1e8:,.0f}억 ({op_period})"))

    if pos52 is None:
        crit.append(_c("pos52", "52주 위치 ≤ 50%", "unknown", "52주 위치 미확인"))
    else:
        crit.append(_c("pos52", "52주 위치 ≤ 50%", "pass" if pos52 <= 0.5 else "fail", f"52주 위치 {pos52 * 100:.0f}%"))

    uw = (facts or {}).get("underwriting")
    if uw in ("총액인수", "잔액인수"):
        crit.append(_c("uw", "총액인수", "pass", uw))
    elif uw == "모집주선":
        crit.append(_c("uw", "총액인수", "fail", "모집주선(인수단 책임 없음)"))
    else:
        crit.append(_c("uw", "총액인수", "unknown", "인수방식 미확인"))

    manual = [_c("rank", "업계 1~3위", "manual", "GPT 확인 필요"),
              _c("irreplaceable", "대체 불가 사업", "manual", "GPT 확인 필요")]

    hard_fail = dil is not None and dil >= 1
    failed = [c for c in crit if c["status"] == "fail"]
    return {
        "criteria": crit + manual,
        "passed": not hard_fail and not failed,
        "hard_fail": hard_fail,
        "n_pass": sum(c["status"] == "pass" for c in crit),
        "n_auto": len(crit),
        "n_unknown": sum(c["status"] == "unknown" for c in crit),
        "reit": is_reit(corp_name),
        "reit_note": ("리츠는 차환 유증이 일상 — 채무상환 기준 완화 검토 대상 (현재 미적용)"
                      if is_reit(corp_name) else None),
    }


def decide(g1: dict, gap: float | None, cheap: float = -20.0, rich: float = 20.0) -> str:
    if gap is not None and gap >= rich:
        return "blue"
    if g1["passed"]:
        v = "green" if gap is not None and gap <= cheap else "yellow"
        return v + "_q" if g1.get("n_unknown") else v
    return "white"


def reason_line(g1: dict, gap: float | None, verdict: str) -> str:
    """예: '채무상환 100% · 희석 240% → 패스 · 괴리 -40.8% → ⚪ 관찰 샘플'"""
    crit = {c["key"]: c for c in g1["criteria"]}
    items = [crit["debt"]["text"], crit["dilution"]["text"].replace(" (100% 이상 즉시 탈락)", "")]
    items += [c["text"] for c in g1["criteria"] if c["status"] == "fail" and c["key"] not in ("debt", "dilution")]
    head = " · ".join(items) + (" → 관문1 통과" if g1["passed"] else " → 패스")
    if g1["passed"] and g1["n_unknown"]:
        head += f"(미확인 {g1['n_unknown']})"
    tail = f" · 괴리 {gap:+.1f}%" if gap is not None else " · 괴리 대기"
    emoji, name = VERDICTS[verdict]
    return f"{head}{tail} → {emoji} {name}"
