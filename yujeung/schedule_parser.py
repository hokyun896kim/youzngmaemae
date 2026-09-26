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
PARSER_VERSION = 11  # 11: 옛 양식(2020) 인수권 기간 — 첫 후보가 무효여도 계속 탐색, '날짜~날짜 신주인수권증서 상장 거래기간'(증권신고서),
#                        '신주인수권증서의 상장여부 아니오' 기록
#                     10: 본문이 '-'로 비고 정정표에만 '추후결정' → 미정 기록(경남제약)
#                      9: 미정 항목은 앞 행 날짜도 지움(경남제약 청약일), 인수권 시작 ≤ 기준일 버림(클로봇)
#                      8: 행에 '추후결정/미정'이 있으면 그 항목은 미정(같은 행의 날짜 = 정정전) — 실측 경남제약 9/18,
#                        본문 후보 점수 = 항목 행을 찾은 칸(미정 포함)
#                      7: 본문 시작 후보 중 항목을 가장 많이 찾은 것(정정표가 본문 뒤에 붙는 경우 — 경남제약),
#                        인수권 문장 '추후결정' 뒤 날짜·기준일보다 이른 인수권 날짜 무시
#                      6: 본문(신주의 종류와 수 표) 앞 구간은 정정·표지로 보고 제외, 할인율 문장 확대
#                      5: 발행가 라벨 구분(예정/1차/확정). 4: 정정공시 '정정전/정정후' 표 제외, 할인율 추출

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


_D = r"20\d{2}\s*(?:년|[.\-/])\s*\d{1,2}\s*(?:월|[.\-/])\s*\d{1,2}\s*일?"
_SEP = r"\s*(?:\([^)]{1,6}\))?\s*[~∼\-]\s*"
# 라벨 → 기간: "신주인수권증서 상장예정기간 : 2020년 12월 02일 ~ 2020년 12월 08일" (옛 결정 공시 '기타 투자판단')
_RIGHTS_PERIOD_AFTER = re.compile(
    r"신주인수권증서[^.。]{0,30}?(?:상장|매매|거래)[^.。]{0,20}?기간[^0-9.。]{0,20}?(" + _D + ")" + _SEP + "(" + _D + ")")
# 기간 → 라벨: "2020년 06월 19일 ~ 2020년 06월 25일 신주인수권증서 상장 거래기간" (증권신고서 일정표)
_RIGHTS_PERIOD_BEFORE = re.compile(
    r"(" + _D + ")" + _SEP + "(" + _D + r")\s*신주인수권증서\s*(?:상장|매매|거래)")
_RIGHTS_LISTED_RE = re.compile(r"신주인수권증서의\s*상장\s*여부\s*(예|아니오|아니요)")


def extract_rights_period(text: str, record_date: str | None = None,
                          subs_start: str | None = None) -> tuple[str, str] | None:
    """인수권 상장(거래)기간 (시작, 끝). 기준일 이후·청약 전이어야 한다 — 아니면 다른 문장의 날짜."""
    t = text.replace("&cr;", " ")
    for rx in (_RIGHTS_PERIOD_AFTER, _RIGHTS_PERIOD_BEFORE):
        for m in rx.finditer(t):
            a, b = find_dates(m.group(1)), find_dates(m.group(2))
            if not (a and b) or a[0] > b[0]:
                continue
            if record_date and a[0] <= record_date:
                continue
            if subs_start and b[0] >= subs_start:
                continue
            return a[0], b[0]
    return None


def rights_listed(text: str) -> bool | None:
    """'신주인수권증서의 상장여부 예/아니오' — 아니오면 인수권 거래가 없는 주주배정(최대주주 단독 등)."""
    m = _RIGHTS_LISTED_RE.search(text)
    return None if not m else m.group(1) == "예"


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


def _after_values(cells: list[str]) -> list[str] | None:
    """정정 행 → 라벨 + 정정후 값. 값이 짝수(2·4…)면 뒤쪽 절반(= 정정후: '전 | 후' 순서), 홀수면 마지막 하나.
    값이 하나뿐이면 정정전인지 후인지 알 수 없어 버린다."""
    values = [c for c in cells if _is_value(c)]
    labels = [c for c in cells if not _is_value(c)]
    if len(values) < 2 or not labels:
        return None
    return labels + (values[len(values) // 2:] if len(values) % 2 == 0 else values[-1:])


def body_starts(doc: str) -> list[int]:
    """본문 시작 후보: 원문 맨 앞(0) + '1. 신주의 종류와 수'가 든 표마다의 시작 위치.
    정정사항 표는 본문 앞(이렘 9/23)에도, 본문 뒤(경남제약 9/18)에도 붙고 그 안에 '신주의 종류와 수'
    행이 있을 수 있어, 한 위치로 정하지 않고 후보를 모두 파싱해 본다 (parse_document)."""
    out = [0]
    for m in _TABLE_RE.finditer(doc):
        if "신주의종류와수" in clean(m.group(0)).replace(" ", ""):
            out.append(m.start())
    return sorted(set(out))


def body_start(doc: str) -> int:
    """parse-doc 출력용: 실제로 고른 본문 시작 위치."""
    return _best_split(doc)[0]


def split_corrections(doc: str, start: int | None = None) -> tuple[str, list[list[str]]]:
    """정정 구간을 떼어낸다 → (본문, 정정후 행들).
    1) 본문 시작(start) 앞의 모든 표(정정사항·표지)  2) 그 뒤에 남은 '정정전 | 정정후'(또는 변경전/후) 표.
    본문 앞 구간은 통째로 뺀다 (표지·정정사항 문장 속 옛 날짜가 먼저 잡히지 않게). 정정신고서 제출요구·
    최대주주·할인율 같은 문장 검색은 parse_document 가 원문 전체로 한다."""
    if start is None:
        start = _best_split(doc)[0]
    corrected: list[list[str]] = []
    for cells in table_rows(doc[:start]):
        row = _after_values(cells)
        if row:
            corrected.append(row)

    def cut(m: re.Match) -> str:
        text = clean(m.group(0)).replace(" ", "")
        if not any(a in text and b in text for a, b in (("정정전", "정정후"), ("변경전", "변경후"), ("수정전", "수정후"))):
            return m.group(0)
        for cells in table_rows(m.group(0)):
            row = _after_values(cells)
            if row:
                corrected.append(row)
        return " "

    return _TABLE_RE.sub(cut, doc[start:]), corrected


def _found(s: "Schedule") -> int:
    return sum(v is not None for v in s.as_row().values())


def _rows_doc(rows: list[list[str]]) -> str:
    return "<TABLE>" + "".join("<TR>" + "".join(f"<TD>{html.escape(c)}</TD>" for c in cells) + "</TR>"
                               for cells in rows) + "</TABLE>"


def _best_split(doc: str) -> tuple[int, str, list[list[str]], "Schedule"]:
    """후보마다 '본문 + 떼어낸 정정후 값으로 채울 수 있는 칸'을 세어 가장 많은 것.
    같으면 뒤쪽(정정사항을 더 많이 떼어낸 쪽) — 앞머리 옛 값이 본문보다 먼저 잡히지 않게."""
    best, best_n = None, -1
    for start in body_starts(doc):
        body, corrected = split_corrections(doc, start)
        sch = _parse_body(body)
        fill = _parse_body(_rows_doc(corrected)) if corrected else None
        # 항목 행을 찾은 칸(값 또는 '추후결정') + 정정후로 채울 수 있는 칸. 미정도 '찾은 것'으로 센다 —
        # 안 그러면 정정전 옛 날짜가 남은 후보가 이긴다 (실측 경남제약 9/18)
        n = len(set(sch.extras.get("seen", [])) | {k for k in Schedule.FIELDS if getattr(sch, k) is not None}
                | ({k for k in Schedule.FIELDS if getattr(fill, k) is not None} if fill is not None else set()))
        if n >= best_n:
            best, best_n = (start, body, corrected, sch), n
    return best


# '할인율 25%', '할인율(25%)', '할인율은 35%를', '할인율: 30 %', '35%의 할인율'
_DISCOUNT_RE = re.compile(r"할인율[^0-9%\n]{0,12}?(\d{1,2}(?:\.\d+)?)\s*%|(\d{1,2}(?:\.\d+)?)\s*%\s*(?:의|를|을)?\s*할인율")


def price_label_kind(label: str) -> str | None:
    """발행가 라벨 → '확정' / '1차' / '예정' (라벨로 알 수 없으면 None — 공시일로 판단)."""
    lb = label.replace(" ", "")
    if "확정발행가" in lb:
        return "확정"
    if "1차" in lb:
        return "1차"
    if "예정발행가" in lb:
        return "예정"
    return None


def issue_kind(label_kind: str | None, rcept_dt: str | None, sch: dict) -> str:
    """발행가 구분. 확정 = 확정발행가 라벨 또는 확정 산정일 이후 공시 /
    1차 = '1차' 라벨 또는 1차 발행가 산정일(신주배정기준일 전 3거래일) 이후 공시 / 그 외 예정."""
    d = f"{rcept_dt[:4]}-{rcept_dt[4:6]}-{rcept_dt[6:8]}" if rcept_dt and len(rcept_dt) >= 8 else None
    fix = sch.get("price_fix_date")
    if not fix and sch.get("subs_start"):
        # 확정 산정일이 안 잡혔으면 청약 전 3거래일(2차 발행가 기준일)로 본다 — 실측 SG: 9/01 공시 911원이 '1차'로 분류됨
        fix = shift_business_days(date.fromisoformat(sch["subs_start"]), -3).isoformat()
    if label_kind == "확정" or (d and fix and d >= fix):
        return "확정"
    if label_kind == "1차" or (d and sch.get("record_date") and d >= first_price_date(sch["record_date"])):
        return "1차"
    return "예정"


def first_price_date(record_date: str) -> str:
    """1차 발행가 산정일 = 신주배정기준일 전 3거래일 (증권의 발행 및 공시 등에 관한 규정 — 회사별 원문 확인)."""
    return shift_business_days(date.fromisoformat(record_date), -3).isoformat()


def extract_discount(text: str) -> float | None:
    """1차·2차 발행가 산식의 할인율(예: '할인율 25%', '할인율(35%)'). 가장 많이 나온 값, 5~60% 만."""
    counts: dict[float, int] = {}
    for m in _DISCOUNT_RE.finditer(text):
        v = float(m.group(1) or m.group(2))
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
    _, body, corrected, s = _best_split(doc)
    text = clean(doc)
    # 본문엔 미정 칸이 '-'로만 남고 '추후결정'은 앞머리 정정표에만 있는 경우 (실측 경남제약 9/18 v9):
    # 본문이 비어 있고 원문 어디든 그 항목 행에 '추후결정/미정'이 있으면 미정으로 기록
    tbd = set(s.extras.get("tbd", []))
    for label, _values in labeled_rows(table_rows(doc)):
        fld = _date_field(label)
        if fld and fld not in tbd and any(k in label for k in TBD_WORDS) and getattr(s, fld) is None:
            tbd.add(fld)
            s.warnings.append(f"{FIELD_KO[fld]} 추후결정 (정정 대기)" if fld != "rights_start"
                              else "인수권 상장기간 추후결정 (정정 대기)")
    s.extras["tbd"] = sorted(tbd)
    if corrected:
        c = _parse_body(_rows_doc(corrected))
        filled, differ = [], []
        tbd_body = set(s.extras.get("tbd", []))
        for k in Schedule.FIELDS:
            new = getattr(c, k)
            if new is None or k in tbd_body or (k in ("subs_end", "rights_end", "ex_rights_date")
                                                and {"subs_end": "subs_start", "rights_end": "rights_start",
                                                     "ex_rights_date": "record_date"}[k] in tbd_body):
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
        if "issue_price" in filled:
            s.extras["issue_label_kind"] = c.extras.get("issue_label_kind")
    if "정정신고서제출요구" in text.replace(" ", "") and not any("정정신고서" in w for w in s.warnings):
        s.warnings.append("⚠ 금감원 정정신고서 제출요구 이력")
    s.extras["facts"] = {"major_holder": extract_major_holder(text),
                         "underwriting": extract_underwriting([], table_rows(doc), text),
                         "discount": extract_discount(text)}
    listed = rights_listed(text)
    if listed is not None:
        s.extras["facts"]["rights_listed"] = listed
    return s


TBD_WORDS = ("추후", "미정")
FIELD_KO = {"record_date": "신주배정기준일", "subs_start": "청약일", "payment_date": "납입일",
            "listing_date": "신주 상장일", "rights_start": "인수권 상장기간", "price_fix_date": "확정발행가 산정일"}


def _date_field(label: str) -> str | None:
    """행 라벨 → 일정 항목 (값이 없더라도 '이 항목 행을 봤다'를 세기 위해)."""
    if "발행가" in label:
        return "price_fix_date" if "확정" in label and "확정발행가" not in label.replace("확정예정일", "") else None
    if "신주배정기준일" in label:
        return "record_date"
    if "신주인수권증서" in label and "보유자" not in label and any(k in label for k in ("상장", "매매", "거래")):
        return "rights_start"
    if "청약" in label and "우리사주" not in label and not any(k in label for k in ("공고", "대상자", "결과", "보유자")):
        return "subs_start"
    if "납입일" in label:
        return "payment_date"
    if "상장예정일" in label and "인수권" not in label:
        return "listing_date"
    return None


def _parse_body(doc: str) -> Schedule:
    s = Schedule()
    seen: set[str] = set()
    tbd: set[str] = set()
    raw_rows = table_rows(doc)
    rows = labeled_rows(raw_rows)
    evidence: dict[str, str] = {}
    price_candidates: list[tuple[int, int, str]] = []   # (우선순위, 값, 라벨)
    fix_candidates: list[tuple[str, str]] = []           # (확정발행가 산정/확정 예정일, 라벨)

    for label, values in rows:
        fld = _date_field(label)
        if fld:
            seen.add(fld)
            if any(k in label for k in TBD_WORDS):
                # '8. 신주배정기준일 | 정정사유 | 2026-09-22 | 추후결정' — 같은 행의 날짜는 정정전 값 (실측 경남제약 9/18)
                if fld not in tbd:
                    tbd.add(fld)
                    s.warnings.append(f"{FIELD_KO[fld]} 추후결정 (정정 대기)" if fld != "rights_start"
                                      else "인수권 상장기간 추후결정 (정정 대기)")
                if fld != "price_fix_date":
                    continue
                values = [v for v in values if not find_dates(v)]
        if fld in tbd and fld != "price_fix_date":
            continue
        if not values:
            continue
        date = _first_date(values)
        if "발행가" in label:
            # 실측: '예정발행가 | 보통주식 | 2,360 | 확정예정일 | 날짜' 처럼 가격과 날짜가 한 행에 온다
            if "기타주식" not in label and "종류주식" not in label:
                n = _first_number(values, min_value=1)
                if n is not None:
                    prio = 0 if "확정발행가" in label else 1 if ("예정발행가" in label or "1차" in label) else 2
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

    issue_label_kind = None
    # 어느 행에서든 '추후결정'이 나온 항목은 미정 — 앞 행에서 먼저 잡힌 날짜(정정전)도 지운다
    # (실측 경남제약 9/18: 청약 '시작일 | 11/02' 다음 행에 '추후결정')
    for fld in tbd:
        for k in {"subs_start": ("subs_start", "subs_end"), "rights_start": ("rights_start", "rights_end")}.get(fld, (fld,)):
            if k != "price_fix_date":
                setattr(s, k, None)
                evidence.pop(k, None)

    if price_candidates:
        prio, value, label = min(price_candidates)
        s.issue_price, evidence["issue_price"] = value, label
        issue_label_kind = price_label_kind(label)

    # 확정발행가 날짜는 청약 전이어야 한다. 정정 공시 본문에 남은 옛 날짜(청약 이후)는 버린다.
    if fix_candidates:
        valid = [(d, lb) for d, lb in fix_candidates if not s.subs_start or d <= s.subs_start]
        if valid:
            s.price_fix_date, evidence["price_fix_date"] = max(valid)
        else:
            s.price_fix_date, evidence["price_fix_date"] = fix_candidates[0]
            s.warnings.append("확정발행가 날짜가 청약일 이후 — 원문 확인 필요")

    # 표에 없으면 본문(기타 투자판단 사항)에서 "신주인수권증서 상장/매매 … 날짜 ~ 날짜"
    if not s.rights_start and "rights_start" not in tbd and not any("추후결정" in w and "인수권" in w for w in s.warnings):
        text = clean(doc)
        period = extract_rights_period(text, s.record_date, s.subs_start)
        if period:   # "상장예정기간 : 날짜 ~ 날짜" (옛 양식 — 앞의 '상장여부 예 … 이사회결의일' 날짜에 걸리지 않게 먼저)
            s.rights_start, s.rights_end = period
            evidence["rights_start"] = "인수권 상장기간(본문)"
        for m in ([] if period else _RIGHTS_TEXT_RE.finditer(text)):
            chunk = m.group(0)
            ds = find_dates(chunk)
            if not ds:
                continue
            # '상장예정기간 : 추후결정 4) … 전자증권제도 시행일(2019년 9월 16일)' — 추후결정 뒤 날짜는 다른 얘기 (실측 경남제약)
            head = chunk[:chunk.find(ds[0][:4])]
            if any(k in head for k in ("추후", "미정")):
                s.warnings.append("인수권 상장기간 추후결정 (정정 대기)")
                break
            if s.record_date and ds[0] <= s.record_date:
                continue     # 기준일 이전 날짜(이사회결의일·전자증권 시행일 등) — 다음 후보를 본다 (실측 2020 유네코)
            s.rights_start = ds[0]
            s.rights_end = ds[1] if len(ds) > 1 else None
            evidence["rights_start"] = chunk[:120]
            break

    # 인수권은 신주배정기준일 이후에 상장된다. 그보다 이른 날짜는 다른 문장의 날짜를 잘못 집은 것
    if s.rights_start and s.record_date and s.rights_start <= s.record_date:   # 실측 클로봇: 기준일과 같은 날
        s.warnings.append(f"인수권 상장기간 {s.rights_start} 이 기준일({s.record_date}) 전이라 버림")
        s.rights_start = s.rights_end = None
        evidence.pop("rights_start", None)

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
    s.extras = {"evidence": evidence, "parser": PARSER_VERSION, "issue_label_kind": issue_label_kind,
                "seen": sorted(seen), "tbd": sorted(tbd)}
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
