"""유상증자결정 주요사항보고서 원문(document.xml) → 일정·발행가 추출.

DART 원문은 <TABLE><TR><TD|TE|TH|TU> 구조의 XML. 표 행을 (라벨, 값들)로 펼친 뒤
라벨 키워드로 필드를 찾는다. 행 머리가 '시작일/종료일/보통주식…'처럼 하위 라벨이면
바로 위 행의 라벨을 앞에 붙인다 (rowspan 대응).

검증 필요: 실제 공시 원문 여러 건으로 추출 정확도 확인 전까지는
warnings 에 '미검증 파서' 를 남기고, 원문 행은 extras 에 그대로 보관한다.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

from datetime import date

from .calendar_kr import ex_rights_date, shift_business_days

# 파서 로직을 고치면 올린다 → 기존 공시가 다음 실행 때 재파싱된다 (pipeline.step_schedules)
PARSER_VERSION = 4   # 4: 정정공시의 '정정전/정정후' 표는 본문 파싱에서 빼고 정정후 값만 보조로 사용, 할인율 추출

_DATE_RE = re.compile(
    r"(20\d{2})\s*(?:년|[.\-/])\s*(\d{1,2})\s*(?:월|[.\-/])\s*(\d{1,2})\s*일?"
    r"|(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)"
)
_NUM_RE = re.compile(r"(?<![\d.])\d{1,3}(?:,\d{3})+(?:\.\d+)?(?![\d.])|(?<![\d.,])\d+(?:\.\d+)?(?![\d.,])")
_ROW_RE = re.compile(r"<TR\b[^>]*>(.*?)</TR>", re.S | re.I)
_TABLE_RE = re.compile(r"<TABLE\b[^>]*>.*?</TABLE>", re.S | re.I)
_CELL_RE = re.compile(r"<(TD|TH|TE|TU)\b[^>]*>(.*?)</\1>", re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")

# 행 머리가 이것들이면 상위 라벨에 딸린 하위 행이다 (rowspan 으로 상위 라벨 셀이 생략됨)
GROUP_LABELS = ("우리사주조합", "구주주", "일반모집", "일반공모", "보통주식", "기타주식", "종류주식")
LEAF_LABELS = ("시작일", "종료일", "확정", "예정")


def clean(text: str) -> str:
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def find_dates(text: str) -> list[str]:
    out = []
    for m in _DATE_RE.finditer(text):
        y, mo, d = (m.group(1), m.group(2), m.group(3)) if m.group(1) else (m.group(4), m.group(5), m.group(6))
        mo_i, d_i = int(mo), int(d)
        if 1 <= mo_i <= 12 and 1 <= d_i <= 31:
            out.append(f"{y}-{mo_i:02d}-{d_i:02d}")
    return out


def find_numbers(text: str) -> list[float]:
    stripped = _DATE_RE.sub(" ", text)
    return [float(m.group(0).replace(",", "")) for m in _NUM_RE.finditer(stripped)]


def table_rows(doc: str) -> list[list[str]]:
    rows = []
    for m in _ROW_RE.finditer(doc):
        cells = [clean(c.group(2)) for c in _CELL_RE.finditer(m.group(1))]
        cells = [c for c in cells if c]
        if cells:
            rows.append(cells)
    return rows


def split_corrections(doc: str) -> tuple[str, list[list[str]]]:
    """정정공시 앞머리의 '정정전 | 정정후' 표를 떼어낸다 → (본문, 정정후 행들).
    실측(이렘 2026-09-23 기재정정): 이 표가 본문보다 먼저 나와 첫 값(=정정전)이 일정으로 잡혔다.
    정정후 행 = 라벨 셀 + 마지막 값 셀 (값이 2개 이상인 행만 — 하나뿐이면 정정전인지 알 수 없다)."""
    corrected: list[list[str]] = []

    def cut(m: re.Match) -> str:
        text = clean(m.group(0)).replace(" ", "")
        if "정정전" not in text or "정정후" not in text:
            return m.group(0)
        for cells in table_rows(m.group(0)):
            values = [c for c in cells if _is_value(c)]
            labels = [c for c in cells if not _is_value(c)]
            if len(values) >= 2 and labels:
                corrected.append(labels + [values[-1]])
        return " "

    return _TABLE_RE.sub(cut, doc), corrected


_DISCOUNT_RE = re.compile(r"할인율\s*[(:：]?\s*(\d{1,2}(?:\.\d+)?)\s*%")


def extract_discount(text: str) -> float | None:
    """1차·2차 발행가 산식의 할인율(예: '할인율 25%', '할인율(35%)'). 가장 많이 나온 값, 5~60% 만."""
    counts: dict[float, int] = {}
    for m in _DISCOUNT_RE.finditer(text):
        v = float(m.group(1))
        if 5 <= v <= 60:
            counts[v] = counts.get(v, 0) + 1
    return max(counts, key=lambda v: (counts[v], v)) / 100 if counts else None


def _is_value(cell: str) -> bool:
    return bool(find_dates(cell)) or bool(re.fullmatch(r"[\d,.\s()%원주-]+", cell))


def labeled_rows(rows: list[list[str]]) -> list[tuple[str, list[str]]]:
    """[(정규화 라벨, 값 셀들)] — 라벨은 공백 제거. 하위 행이면 상위 라벨(+그룹)을 앞에 붙인다.
    예) '9.청약예정일 | 우리사주조합 | 시작일 | 날짜' 다음 '종료일 | 날짜' → '9.청약예정일우리사주조합종료일'"""
    out = []
    section, group = "", ""
    for cells in rows:
        labels = [c.replace(" ", "") for c in cells if not _is_value(c)]
        values = [c for c in cells if _is_value(c)]
        if not labels:
            out.append((section + group, values))
            continue
        first = labels[0]
        if first.startswith(LEAF_LABELS) and section:
            # 행 안에 자기 그룹(보통주식 등)이 있으면 위 행의 그룹을 끌어오지 않는다
            own = next((lb for lb in labels if lb.startswith(GROUP_LABELS)), None)
            label = section + ("" if own else group) + "".join(labels)
            group = own or group
        elif first.startswith(GROUP_LABELS) and section:
            group = first
            label = section + "".join(labels)
        else:
            section = first
            group = next((lb for lb in labels[1:] if lb.startswith(GROUP_LABELS)), "")
            label = "".join(labels)
        out.append((label, values))
    return out


@dataclass
class Schedule:
    record_date: str | None = None
    ex_rights_date: str | None = None
    rights_start: str | None = None
    rights_end: str | None = None
    price_fix_date: str | None = None
    subs_start: str | None = None
    subs_end: str | None = None
    payment_date: str | None = None
    listing_date: str | None = None
    issue_price: int | None = None
    alloc_ratio: float | None = None
    extras: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    FIELDS = ("record_date", "ex_rights_date", "rights_start", "rights_end", "price_fix_date",
              "subs_start", "subs_end", "payment_date", "listing_date", "issue_price", "alloc_ratio")

    def as_row(self) -> dict:
        return {k: getattr(self, k) for k in self.FIELDS}


def _first_date(values: list[str]) -> str | None:
    for v in values:
        ds = find_dates(v)
        if ds:
            return ds[0]
    return None


def _first_number(values: list[str], min_value: float = 0) -> float | None:
    for v in values:
        for n in find_numbers(v):
            if n > min_value:
                return n
    return None


# ---- 판정 재료: 최대주주 청약 참여, 인수 방식 (원문 휴리스틱 — 카드에 '원문 확인' 표시) ----
_PCT_RE = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")


def extract_major_holder(text: str) -> dict | None:
    """'최대주주 … 청약/참여 …' 문장에서 참여 수준. level: full(100%·전량 이상) / partial / none / unknown"""
    best = None
    rank = {"full": 3, "partial": 2, "none": 2, "unknown": 1}
    for m in re.finditer(r"최대주주", text):
        win = text[m.start(): m.start() + 220]
        if not re.search(r"청약|참여", win):
            continue
        if re.search(r"미정|결정되지|확정되지", win):
            cur = {"level": "unknown", "text": win[:140]}
        elif re.search(r"참여하지\s*않|불참|미참여|청약하지\s*않", win):
            cur = {"level": "none", "text": win[:140]}
        elif re.search(r"전량|전부|초과청약", win) or any(float(x) >= 100 for x in _PCT_RE.findall(win)):
            cur = {"level": "full", "text": win[:140]}
        elif _PCT_RE.search(win):
            pct = max(float(x) for x in _PCT_RE.findall(win))
            cur = {"level": "partial", "pct": pct, "text": win[:140]}
        else:
            continue
        if best is None or rank[cur["level"]] > rank[best["level"]]:
            best = cur
    return best


def extract_underwriting(rows: list[tuple[str, list[str]]], raw_rows: list[list[str]], text: str) -> str | None:
    """인수 방식: 총액인수 / 잔액인수 / 모집주선. 표의 '인수방법' 칸 우선, 없으면 본문 빈도."""
    kinds = ("잔액인수", "총액인수", "모집주선")
    for cells in raw_rows:
        joined = "".join(cells).replace(" ", "")
        if "인수방법" in joined or "인수형태" in joined:
            for k in kinds:
                if k in joined:
                    return k
    counts = {k: text.replace(" ", "").count(k) for k in kinds}
    k, n = max(counts.items(), key=lambda kv: kv[1])
    return k if n else None


def validate_schedule(s: dict) -> tuple[dict, list[str]]:
    """합쳐진 일정의 논리 검사. (고친 일정, 경고) — 원본은 건드리지 않는다.
    - 인수권 기간이 청약 기간과 똑같으면 '인수권 기간 파싱 실패' → 값 비움
    - 인수권 마지막 날이 청약 시작 5거래일 전보다 늦으면 경고"""
    s = dict(s)
    warns: list[str] = []
    if s.get("rights_start") and s.get("rights_start") == s.get("subs_start") and \
            (s.get("rights_end") or s.get("rights_start")) == (s.get("subs_end") or s.get("subs_start")):
        warns.append("인수권 기간 파싱 실패 (청약일과 동일) — 원문 확인")
        s["rights_start"] = s["rights_end"] = None
    if s.get("rights_end") and s.get("subs_start"):
        limit = shift_business_days(date.fromisoformat(s["subs_start"]), -5).isoformat()
        if s["rights_end"] > limit:
            warns.append(f"인수권 마지막 날 {s['rights_end']} 이 청약 5거래일 전({limit})보다 늦음 — 원문 확인")
    return s, warns


_RIGHTS_TEXT_RE = re.compile(r"신주인수권증서[^.。\n]{0,80}?(?:상장|매매|거래)[^.。\n]{0,80}")


def parse_document(doc: str) -> Schedule:
    """정정공시면 '정정전/정정후' 표를 빼고 본문(정정 반영된 전체 원문)으로 파싱하고,
    본문에서 못 찾은 필드만 정정후 값으로 채운다. 둘이 다르면 경고."""
    body, corrected = split_corrections(doc)
    s = _parse_body(body)
    text = clean(doc)
    if corrected:
        rows = "".join("<TR>" + "".join(f"<TD>{html.escape(c)}</TD>" for c in cells) + "</TR>" for cells in corrected)
        c = _parse_body(f"<TABLE>{rows}</TABLE>")
        filled, differ = [], []
        for k in Schedule.FIELDS:
            new = getattr(c, k)
            if new is None:
                continue
            if getattr(s, k) is None:
                setattr(s, k, new)
                filled.append(k)
            elif getattr(s, k) != new:
                differ.append(f"{k} 본문 {getattr(s, k)} / 정정후 {new}")
        if filled and s.record_date and "ex_rights_date" not in filled:
            s.ex_rights_date = ex_rights_date(s.record_date)
        s.warnings = [w for w in s.warnings if not any(w == f"{k} 못 찾음" for k in filled)]
        if differ:
            s.warnings.append("정정표와 본문 불일치 — 원문 확인: " + "; ".join(differ))
        s.extras["corrections"] = {"rows": len(corrected), "filled": filled}
    if "정정신고서제출요구" in text.replace(" ", "") and not any("정정신고서" in w for w in s.warnings):
        s.warnings.append("⚠ 금감원 정정신고서 제출요구 이력")
    s.extras["facts"] = {"major_holder": extract_major_holder(text),
                         "underwriting": extract_underwriting([], table_rows(doc), text),
                         "discount": extract_discount(text)}
    return s


def _parse_body(doc: str) -> Schedule:
    s = Schedule()
    raw_rows = table_rows(doc)
    rows = labeled_rows(raw_rows)
    evidence: dict[str, str] = {}
    price_candidates: list[tuple[int, int, str]] = []   # (우선순위, 값, 라벨)
    fix_candidates: list[tuple[str, str]] = []           # (확정발행가 산정/확정 예정일, 라벨)

    for label, values in rows:
        if not values:
            continue
        date = _first_date(values)
        if "발행가" in label:
            # 실측: '예정발행가 | 보통주식 | 2,360 | 확정예정일 | 날짜' 처럼 가격과 날짜가 한 행에 온다
            if "기타주식" not in label and "종류주식" not in label:
                n = _first_number(values, min_value=1)
                if n is not None:
                    prio = 0 if "확정발행가" in label else 1 if "예정발행가" in label else 2
                    price_candidates.append((prio, int(n), label))
            if "확정" in label and date:
                fix_candidates.append((date, label))
            continue
        if "신주배정기준일" in label and date and not s.record_date:
            s.record_date, evidence["record_date"] = date, label
        elif "1주당신주배정주식수" in label and s.alloc_ratio is None:
            n = _first_number(values)
            if n is not None:
                s.alloc_ratio, evidence["alloc_ratio"] = n, label
        elif ("신주인수권증서" in label and date and "보유자" not in label
              and any(k in label for k in ("상장", "매매", "거래"))):
            if any(k in label for k in ("추후", "미정")):
                s.warnings.append("인수권 상장기간 추후결정 (정정 대기)")
                continue
            if "종료" in label and not s.rights_end:
                s.rights_end, evidence["rights_end"] = date, label
            elif "시작" in label and not s.rights_start:
                s.rights_start, evidence["rights_start"] = date, label
            elif not s.rights_start:
                ds = [d for v in values for d in find_dates(v)]
                s.rights_start = ds[0]
                s.rights_end = ds[1] if len(ds) > 1 else s.rights_end
                evidence["rights_start"] = label
        elif ("청약" in label and "우리사주" not in label and date
              and not any(k in label for k in ("공고", "대상자", "결과", "보유자"))):
            if "종료" in label and not s.subs_end:
                s.subs_end, evidence["subs_end"] = date, label
            elif "시작" in label and not s.subs_start:
                s.subs_start, evidence["subs_start"] = date, label
            elif "시작" not in label and "종료" not in label and not s.subs_start:
                # 3자배정 공시: '청약일 | 날짜' 한 줄 (기간이면 '날짜 ~ 날짜')
                ds = [d for v in values for d in find_dates(v)]
                s.subs_start, s.subs_end = ds[0], ds[-1]
                evidence["subs_start"] = label
        elif "납입일" in label and date and not s.payment_date:
            s.payment_date, evidence["payment_date"] = date, label
        elif "상장예정일" in label and "인수권" not in label and date and not s.listing_date:
            s.listing_date, evidence["listing_date"] = date, label

    if price_candidates:
        prio, value, label = min(price_candidates)
        s.issue_price, evidence["issue_price"] = value, label

    # 확정발행가 날짜는 청약 전이어야 한다. 정정 공시 본문에 남은 옛 날짜(청약 이후)는 버린다.
    if fix_candidates:
        valid = [(d, lb) for d, lb in fix_candidates if not s.subs_start or d <= s.subs_start]
        if valid:
            s.price_fix_date, evidence["price_fix_date"] = max(valid)
        else:
            s.price_fix_date, evidence["price_fix_date"] = fix_candidates[0]
            s.warnings.append("확정발행가 날짜가 청약일 이후 — 원문 확인 필요")

    # 표에 없으면 본문(기타 투자판단 사항)에서 "신주인수권증서 상장/매매 … 날짜 ~ 날짜"
    if not s.rights_start and not any("추후결정" in w for w in s.warnings):
        text = clean(doc)
        for m in _RIGHTS_TEXT_RE.finditer(text):
            ds = find_dates(m.group(0))
            if ds:
                s.rights_start = ds[0]
                s.rights_end = ds[1] if len(ds) > 1 else None
                evidence["rights_start"] = m.group(0)[:120]
                break

    # 인수권 거래는 청약 전에 끝난다. 청약 시작일 이후로 잡힌 기간은 오파싱으로 보고 버린다.
    if s.rights_start and s.subs_start and (s.rights_end or s.rights_start) >= s.subs_start:
        s.warnings.append(f"인수권 상장기간 {s.rights_start}~{s.rights_end} 이 청약({s.subs_start}) 이후라 버림")
        s.rights_start = s.rights_end = None
        evidence.pop("rights_start", None)
        evidence.pop("rights_end", None)

    if s.record_date:
        s.ex_rights_date = ex_rights_date(s.record_date)
        s.warnings.append("권리락일은 기준일 전 1영업일로 추정 (휴장일 목록 기준)")

    for name in ("record_date", "issue_price", "subs_start", "payment_date", "listing_date", "rights_start"):
        if getattr(s, name) is None:
            s.warnings.append(f"{name} 못 찾음")
    s.warnings.append("미검증 파서: 실제 공시 원문으로 정확도 확인 전")
    s.extras = {"evidence": evidence, "parser": PARSER_VERSION}
    return s


def parse_documents(files: dict[str, str]) -> Schedule:
    """zip 안 여러 파일 중 유상증자결정 본문이 든 파일을 골라 파싱 (가장 많은 필드를 찾은 결과)."""
    best: Schedule | None = None
    for name, body in files.items():
        sch = parse_document(body)
        found = sum(v is not None for v in sch.as_row().values())
        if best is None or found > sum(v is not None for v in best.as_row().values()):
            best = sch
            best.extras["file"] = name
    return best or Schedule(warnings=["원문 파일 없음"])
