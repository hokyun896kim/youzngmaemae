"""SQLite 저장소. 이 DB 자체가 Phase 1~2 백테스트 데이터가 된다."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

SCHEMA = """
-- API 응답 원본. 파싱 로직이 바뀌어도 여기서 재처리한다.
CREATE TABLE IF NOT EXISTS raw_responses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL,          -- dart.list / dart.piicDecsn / krx.rights ...
    request_key TEXT NOT NULL,          -- 요청 파라미터 요약
    fetched_at  TEXT NOT NULL,
    body        BLOB NOT NULL
);

-- 유증 케이스(한 회사의 한 번의 유증). 정정 공시는 같은 케이스로 묶인다.
CREATE TABLE IF NOT EXISTS cases (
    case_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    corp_code      TEXT NOT NULL,
    corp_name      TEXT NOT NULL,
    stock_code     TEXT,
    corp_cls       TEXT,
    first_rcept_no TEXT NOT NULL UNIQUE,
    first_rcept_dt TEXT NOT NULL,
    ic_mthn        TEXT,                -- 증자방식
    is_rights      INTEGER NOT NULL,    -- 주주배정 계열이면 1 (인수권증서 발행)
    status         TEXT NOT NULL DEFAULT 'open',   -- open / closed / withdrawn
    created_at     TEXT NOT NULL
);

-- 개별 공시 (원공시 + 정정)
CREATE TABLE IF NOT EXISTS disclosures (
    rcept_no    TEXT PRIMARY KEY,
    case_id     INTEGER REFERENCES cases(case_id),
    kind        TEXT NOT NULL,          -- piic(주요사항보고서) / estk(증권신고서)
    report_nm   TEXT NOT NULL,
    rcept_dt    TEXT NOT NULL,
    is_correction INTEGER NOT NULL,
    fields_json TEXT                    -- piicDecsn 응답 한 건 (정규화 전 원본 값)
);

-- 공시별 일정 파싱 결과. 정정될 때마다 행이 추가된다 → 일정 변경 이력.
CREATE TABLE IF NOT EXISTS schedule_versions (
    rcept_no      TEXT PRIMARY KEY REFERENCES disclosures(rcept_no),
    case_id       INTEGER NOT NULL REFERENCES cases(case_id),
    parsed_at     TEXT NOT NULL,
    record_date   TEXT,   -- 신주배정기준일
    ex_rights_date TEXT,  -- 권리락일 (기준일 전 1영업일, 추정)
    rights_start  TEXT,   -- 신주인수권증서 상장(매매) 시작일
    rights_end    TEXT,   -- 신주인수권증서 상장(매매) 종료일
    price_fix_date TEXT,  -- 확정발행가 산정/공고일
    subs_start    TEXT,   -- 구주주 청약 시작일
    subs_end      TEXT,   -- 구주주 청약 종료일
    payment_date  TEXT,   -- 납입일
    listing_date  TEXT,   -- 신주 상장 예정일
    issue_price   INTEGER,-- (예정/확정) 발행가
    alloc_ratio   REAL,   -- 1주당 신주배정주식수
    extras_json   TEXT,   -- 파싱에 쓴 원문 행/근거
    warnings_json TEXT    -- 못 찾은 필드 등
);

-- 시세: 본주(kind='stock')와 인수권(kind='rights')을 같은 테이블에
CREATE TABLE IF NOT EXISTS prices (
    trd_date   TEXT NOT NULL,
    kind       TEXT NOT NULL,
    code       TEXT NOT NULL,
    name       TEXT,
    case_id    INTEGER REFERENCES cases(case_id),
    open       INTEGER, high INTEGER, low INTEGER, close INTEGER,
    volume     INTEGER,
    source     TEXT NOT NULL,   -- krx / manual
    PRIMARY KEY (trd_date, kind, code)
);

-- 알림 발송 기록. id 가 곧 헤더의 #순번.
CREATE TABLE IF NOT EXISTS notifications (
    seq      INTEGER PRIMARY KEY AUTOINCREMENT,
    topic    TEXT NOT NULL,
    dedup_key TEXT UNIQUE,
    text     TEXT NOT NULL,
    sent_at  TEXT NOT NULL,
    delivered INTEGER NOT NULL
);
"""


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def connect(path: Path | str) -> sqlite3.Connection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def save_raw(conn: sqlite3.Connection, source: str, request_key: str, body: bytes | str) -> None:
    if isinstance(body, str):
        body = body.encode("utf-8")
    conn.execute(
        "INSERT INTO raw_responses (source, request_key, fetched_at, body) VALUES (?,?,?,?)",
        (source, request_key, now(), body),
    )
    conn.commit()


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)
