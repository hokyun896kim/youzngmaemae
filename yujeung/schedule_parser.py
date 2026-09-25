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

from .calendar_kr import ex_rights_date

_DATE_RE = re.compile(
    r"(20\d{2})\s*(?:년|[.\-/])\s*(\d{1,2})\s*(?:월|[.\-/])\s*(\d{1,2})\s*일?"
    r"|(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)"
)
_NUM_RE = re.compile(r"(?<![\d.])\d{1,3}(?:,\d{3})+(?:\.\d+)?(?![\d.])|(?<![\d.,])\d+(?:\.\d+)?(?![\d.,])")
_ROW_RE = re.compile(r"<TR\b[^>]*>(.*?)</TR>", re.S | re.I)
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


_RIGHTS_TEXT_RE = re.compile(r"신주인수권증서[^.。\n]{0,80}?(?:상장|매매|거래)[^.。\n]{0,80}")


def parse_document(doc: str) -> Schedule:
    s = Schedule()
    rows = labeled_rows(table_rows(doc))
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
        elif "신주인수권증서" in label and date:
            if "종료" in label and not s.rights_end:
                s.rights_end, evidence["rights_end"] = date, label
            elif "시작" in label and not s.rights_start:
                s.rights_start, evidence["rights_start"] = date, label
            elif not s.rights_start:
                ds = [d for v in values for d in find_dates(v)]
                s.rights_start = ds[0]
                s.rights_end = ds[1] if len(ds) > 1 else s.rights_end
                evidence["rights_start"] = label
        elif "청약" in label and "우리사주" not in label and date:
            if "종료" in label and not s.subs_end:
                s.subs_end, evidence["subs_end"] = date, label
            elif "시작" in label and not s.subs_start:
                s.subs_start, evidence["subs_start"] = date, label
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
    if not s.rights_start:
        text = clean(doc)
        for m in _RIGHTS_TEXT_RE.finditer(text):
            ds = find_dates(m.group(0))
            if ds:
                s.rights_start = ds[0]
                s.rights_end = ds[1] if len(ds) > 1 else None
                evidence["rights_start"] = m.group(0)[:120]
                break

    if s.record_date:
        s.ex_rights_date = ex_rights_date(s.record_date)
        s.warnings.append("권리락일은 기준일 전 1영업일로 추정 (휴장일 목록 기준)")

    for name in ("record_date", "issue_price", "subs_start", "payment_date", "listing_date", "rights_start"):
        if getattr(s, name) is None:
            s.warnings.append(f"{name} 못 찾음")
    s.warnings.append("미검증 파서: 실제 공시 원문으로 정확도 확인 전")
    s.extras = {"evidence": evidence}
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
