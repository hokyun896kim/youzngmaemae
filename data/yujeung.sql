BEGIN TRANSACTION;
CREATE TABLE cases (
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
CREATE TABLE disclosures (
    rcept_no    TEXT PRIMARY KEY,
    case_id     INTEGER REFERENCES cases(case_id),
    kind        TEXT NOT NULL,          -- piic(주요사항보고서) / estk(증권신고서)
    report_nm   TEXT NOT NULL,
    rcept_dt    TEXT NOT NULL,
    is_correction INTEGER NOT NULL,
    fields_json TEXT                    -- piicDecsn 응답 한 건 (정규화 전 원본 값)
);
CREATE TABLE notifications (
    seq      INTEGER PRIMARY KEY AUTOINCREMENT,
    topic    TEXT NOT NULL,
    dedup_key TEXT UNIQUE,
    text     TEXT NOT NULL,
    sent_at  TEXT NOT NULL,
    delivered INTEGER NOT NULL
);
CREATE TABLE rights_daily (
    bas_dd      TEXT NOT NULL,      -- YYYY-MM-DD
    isu_cd      TEXT NOT NULL,      -- 인수권 종목코드
    isu_nm      TEXT,               -- 예: SK디앤디 12R
    mkt_nm      TEXT,
    close       INTEGER, open INTEGER, high INTEGER, low INTEGER,
    volume      INTEGER, value INTEGER,
    list_shrs   INTEGER,
    issue_price INTEGER,            -- ISU_PRC (신주 발행가)
    delist_dd   TEXT,               -- 인수권 상장폐지(거래 종료)일
    tar_code    TEXT,               -- 대상 본주 단축코드
    tar_name    TEXT,
    tar_price   INTEGER,            -- 대상 본주 가격 (TARSTK_ISU_PRSNT_PRC)
    case_id     INTEGER REFERENCES cases(case_id),
    source      TEXT NOT NULL DEFAULT 'krx',   -- krx / manual
    PRIMARY KEY (bas_dd, isu_cd)
);
CREATE TABLE schedule_versions (
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
CREATE TABLE stock_daily (
    bas_dd  TEXT NOT NULL,
    code    TEXT NOT NULL,
    name    TEXT,
    close   INTEGER, open INTEGER, high INTEGER, low INTEGER,
    volume  INTEGER, mktcap INTEGER, list_shrs INTEGER,
    PRIMARY KEY (bas_dd, code)
);
DELETE FROM "sqlite_sequence";
COMMIT;
