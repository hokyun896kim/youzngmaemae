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
INSERT INTO "cases" VALUES(1,'00125822','삼보산업','009620','K','20260917000373','20260918','제3자배정증자',0,'open','2026-09-25T13:32:24');
INSERT INTO "cases" VALUES(2,'01243161','인산가','277410','K','20260917000375','20260918','제3자배정증자',0,'open','2026-09-25T13:32:24');
INSERT INTO "cases" VALUES(5,'00615723','MSDI','123010','K','20260918000112','20260918','제3자배정증자',0,'open','2026-09-25T13:32:26');
INSERT INTO "cases" VALUES(6,'01075126','사토시홀딩스','223310','K','20260918000210','20260918','제3자배정증자',0,'open','2026-09-25T13:32:27');
INSERT INTO "cases" VALUES(8,'00479705','케스피온','079190','K','20260918000257','20260918','제3자배정증자',0,'open','2026-09-25T13:32:28');
INSERT INTO "cases" VALUES(9,'00537337','앤씨앤','092600','K','20260918000282','20260918','제3자배정증자',0,'open','2026-09-25T13:32:29');
INSERT INTO "cases" VALUES(10,'00307028','경남제약','053950','K','20260918000349','20260918','주주배정증자',1,'open','2026-09-25T13:32:30');
INSERT INTO "cases" VALUES(11,'00132868','우성머티리얼스','011300','Y','20260918000391','20260918','제3자배정증자',0,'open','2026-09-25T13:32:30');
INSERT INTO "cases" VALUES(13,'00530413','더코디','224060','K','20260918000453','20260918','제3자배정증자',0,'open','2026-09-25T13:32:32');
INSERT INTO "cases" VALUES(14,'01688896','삼성FN리츠','448730','Y','20260921000086','20260921','주주배정후 실권주 일반공모',1,'open','2026-09-25T13:32:34');
INSERT INTO "cases" VALUES(15,'00587925','모아라이프플러스','142760','K','20260921000097','20260921','제3자배정증자',0,'open','2026-09-25T13:32:34');
INSERT INTO "cases" VALUES(16,'00232007','상지건설','042940','K','20260921000184','20260921','주주우선공모증자',0,'open','2026-09-25T13:32:35');
INSERT INTO "cases" VALUES(17,'00145437','아센디오','012170','Y','20260921000240','20260921','제3자배정증자',0,'open','2026-09-25T13:32:35');
INSERT INTO "cases" VALUES(18,'01423837','모아데이타','288980','K','20260921000327','20260921','제3자배정증자',0,'open','2026-09-25T13:32:37');
INSERT INTO "cases" VALUES(20,'01160512','헝셩그룹','900270','K','20260921000369','20260921','제3자배정증자',0,'open','2026-09-25T13:32:38');
INSERT INTO "cases" VALUES(23,'01235296','셀리드','299660','K','20260921000434','20260922','제3자배정증자',0,'open','2026-09-25T13:32:40');
INSERT INTO "cases" VALUES(24,'01397903','엔젠바이오','354200','K','20260922000105','20260922','주주배정후 실권주 일반공모',1,'open','2026-09-25T13:32:41');
INSERT INTO "cases" VALUES(25,'00618410','KS인더스트리','101000','K','20260922000240','20260922','제3자배정증자',0,'open','2026-09-25T13:32:42');
INSERT INTO "cases" VALUES(26,'00122825','프리티','006490','Y','20260922000386','20260922','제3자배정증자',0,'open','2026-09-25T13:32:44');
INSERT INTO "cases" VALUES(27,'00550082','캔버스엔','210120','K','20260922000418','20260922','제3자배정증자',0,'open','2026-09-25T13:32:44');
INSERT INTO "cases" VALUES(29,'01235296','셀리드','299660','K','20260922000533','20260922','제3자배정증자',0,'open','2026-09-25T13:32:45');
INSERT INTO "cases" VALUES(32,'00406329','루멘스바이오스','038060','K','20260923000238','20260923','제3자배정증자',0,'open','2026-09-25T13:32:47');
INSERT INTO "cases" VALUES(35,'00110750','GMI벤처','019570','K','20260923000362','20260923','제3자배정증자',0,'open','2026-09-25T13:32:49');
INSERT INTO "cases" VALUES(36,'00101044','에이프로젠바이오로직스','003060','Y','20260923000418','20260923','제3자배정증자',0,'open','2026-09-25T13:32:51');
INSERT INTO "cases" VALUES(37,'00116426','이렘','009730','K','20260923000500','20260923','주주배정증자',1,'open','2026-09-25T13:32:51');
INSERT INTO "cases" VALUES(38,'00369569','비케이홀딩스','050090','K','20260923000531','20260923','제3자배정증자',0,'open','2026-09-25T13:32:52');
INSERT INTO "cases" VALUES(39,'00540429','휴림로봇','090710','K','20260923000576','20260923','일반공모증자',0,'open','2026-09-25T13:32:53');
INSERT INTO "cases" VALUES(40,'01689266','케이쓰리아이','431190','K','20260923000638','20260923','제3자배정증자',0,'open','2026-09-25T13:32:54');
CREATE TABLE disclosures (
    rcept_no    TEXT PRIMARY KEY,
    case_id     INTEGER REFERENCES cases(case_id),
    kind        TEXT NOT NULL,          -- piic(주요사항보고서) / estk(증권신고서)
    report_nm   TEXT NOT NULL,
    rcept_dt    TEXT NOT NULL,
    is_correction INTEGER NOT NULL,
    fields_json TEXT                    -- piicDecsn 응답 한 건 (정규화 전 원본 값)
);
INSERT INTO "disclosures" VALUES('20260917000373',1,'piic','[기재정정]주요사항보고서(유상증자결정)','20260918',1,'{"rcept_no": "20260917000373", "corp_cls": "K", "corp_code": "00125822", "corp_name": "삼보산업", "nstk_ostk_cnt": "860,000", "nstk_estk_cnt": "-", "fv_ps": "500", "bfic_tisstk_ostk": "3,494,609", "bfic_tisstk_estk": "-", "fdpp_fclt": "-", "fdpp_bsninh": "-", "fdpp_op": "-", "fdpp_dtrp": "-", "fdpp_ocsa": "2,786,407,624", "fdpp_etc": "-", "ic_mthn": "제3자배정증자", "ssl_at": "N", "ssl_bgd": "-", "ssl_edd": "-"}');
INSERT INTO "disclosures" VALUES('20260917000375',2,'piic','[기재정정]주요사항보고서(유상증자결정)','20260918',1,'{"rcept_no": "20260917000375", "corp_cls": "K", "corp_code": "01243161", "corp_name": "인산가", "nstk_ostk_cnt": "204,919", "nstk_estk_cnt": "-", "fv_ps": "1,000", "bfic_tisstk_ostk": "3,841,150", "bfic_tisstk_estk": "-", "fdpp_fclt": "-", "fdpp_bsninh": "-", "fdpp_op": "1,000,004,720", "fdpp_dtrp": "-", "fdpp_ocsa": "-", "fdpp_etc": "-", "ic_mthn": "제3자배정증자", "ssl_at": "N", "ssl_bgd": "-", "ssl_edd": "-"}');
INSERT INTO "disclosures" VALUES('20260918000112',5,'piic','[기재정정]주요사항보고서(유상증자결정)','20260918',1,'{"rcept_no": "20260918000112", "corp_cls": "K", "corp_code": "00615723", "corp_name": "MSDI", "nstk_ostk_cnt": "11,166,945", "nstk_estk_cnt": "-", "fv_ps": "1,000", "bfic_tisstk_ostk": "20,215,767", "bfic_tisstk_estk": "-", "fdpp_fclt": "-", "fdpp_bsninh": "-", "fdpp_op": "19,999,998,495", "fdpp_dtrp": "-", "fdpp_ocsa": "-", "fdpp_etc": "-", "ic_mthn": "제3자배정증자", "ssl_at": "N", "ssl_bgd": "-", "ssl_edd": "-"}');
INSERT INTO "disclosures" VALUES('20260918000210',6,'piic','[기재정정]주요사항보고서(유상증자결정)','20260918',1,'{"rcept_no": "20260918000210", "corp_cls": "K", "corp_code": "01075126", "corp_name": "사토시홀딩스", "nstk_ostk_cnt": "5,509,745", "nstk_estk_cnt": "-", "fv_ps": "500", "bfic_tisstk_ostk": "5,204,642", "bfic_tisstk_estk": "-", "fdpp_fclt": "-", "fdpp_bsninh": "-", "fdpp_op": "2,999,999,660", "fdpp_dtrp": "11,700,000,000", "fdpp_ocsa": "-", "fdpp_etc": "-", "ic_mthn": "제3자배정증자", "ssl_at": "N", "ssl_bgd": "-", "ssl_edd": "-"}');
INSERT INTO "disclosures" VALUES('20260918000257',8,'piic','[기재정정]주요사항보고서(유상증자결정)','20260918',1,'{"rcept_no": "20260918000257", "corp_cls": "K", "corp_code": "00479705", "corp_name": "케스피온", "nstk_ostk_cnt": "10,752,688", "nstk_estk_cnt": "-", "fv_ps": "1,000", "bfic_tisstk_ostk": "9,588,878", "bfic_tisstk_estk": "-", "fdpp_fclt": "-", "fdpp_bsninh": "-", "fdpp_op": "12,999,999,792", "fdpp_dtrp": "-", "fdpp_ocsa": "-", "fdpp_etc": "-", "ic_mthn": "제3자배정증자", "ssl_at": "N", "ssl_bgd": "-", "ssl_edd": "-"}');
INSERT INTO "disclosures" VALUES('20260918000282',9,'piic','[기재정정]주요사항보고서(유상증자결정)','20260918',1,'{"rcept_no": "20260918000282", "corp_cls": "K", "corp_code": "00537337", "corp_name": "앤씨앤", "nstk_ostk_cnt": "4,000,000", "nstk_estk_cnt": "-", "fv_ps": "2,500", "bfic_tisstk_ostk": "5,016,703", "bfic_tisstk_estk": "-", "fdpp_fclt": "-", "fdpp_bsninh": "-", "fdpp_op": "10,000,000,000", "fdpp_dtrp": "-", "fdpp_ocsa": "-", "fdpp_etc": "-", "ic_mthn": "제3자배정증자", "ssl_at": "N", "ssl_bgd": "-", "ssl_edd": "-"}');
INSERT INTO "disclosures" VALUES('20260918000349',10,'piic','[기재정정]주요사항보고서(유상증자결정)','20260918',1,'{"rcept_no": "20260918000349", "corp_cls": "K", "corp_code": "00307028", "corp_name": "경남제약", "nstk_ostk_cnt": "13,000,000", "nstk_estk_cnt": "-", "fv_ps": "500", "bfic_tisstk_ostk": "19,619,649", "bfic_tisstk_estk": "-", "fdpp_fclt": "-", "fdpp_bsninh": "-", "fdpp_op": "19,487,000,000", "fdpp_dtrp": "-", "fdpp_ocsa": "-", "fdpp_etc": "-", "ic_mthn": "주주배정증자", "ssl_at": "N", "ssl_bgd": "-", "ssl_edd": "-"}');
INSERT INTO "disclosures" VALUES('20260918000391',11,'piic','[기재정정]주요사항보고서(유상증자결정)','20260918',1,'{"rcept_no": "20260922000245", "corp_cls": "Y", "corp_code": "00132868", "corp_name": "우성머티리얼스", "nstk_ostk_cnt": "970,873", "nstk_estk_cnt": "-", "fv_ps": "1,000", "bfic_tisstk_ostk": "17,238,905", "bfic_tisstk_estk": "-", "fdpp_fclt": "-", "fdpp_bsninh": "-", "fdpp_op": "1,999,998,380", "fdpp_dtrp": "-", "fdpp_ocsa": "-", "fdpp_etc": "-", "ic_mthn": "제3자배정증자", "ssl_at": "N", "ssl_bgd": "-", "ssl_edd": "-"}');
INSERT INTO "disclosures" VALUES('20260918000407',11,'piic','[기재정정]주요사항보고서(유상증자결정)','20260918',1,'{"rcept_no": "20260922000245", "corp_cls": "Y", "corp_code": "00132868", "corp_name": "우성머티리얼스", "nstk_ostk_cnt": "970,873", "nstk_estk_cnt": "-", "fv_ps": "1,000", "bfic_tisstk_ostk": "17,238,905", "bfic_tisstk_estk": "-", "fdpp_fclt": "-", "fdpp_bsninh": "-", "fdpp_op": "1,999,998,380", "fdpp_dtrp": "-", "fdpp_ocsa": "-", "fdpp_etc": "-", "ic_mthn": "제3자배정증자", "ssl_at": "N", "ssl_bgd": "-", "ssl_edd": "-"}');
INSERT INTO "disclosures" VALUES('20260918000453',13,'piic','[기재정정]주요사항보고서(유상증자결정)','20260918',1,'{"rcept_no": "20260923000410", "corp_cls": "K", "corp_code": "00530413", "corp_name": "더코디", "nstk_ostk_cnt": "105,954", "nstk_estk_cnt": "-", "fv_ps": "500", "bfic_tisstk_ostk": "5,160,722", "bfic_tisstk_estk": "-", "fdpp_fclt": "-", "fdpp_bsninh": "-", "fdpp_op": "499,996,926", "fdpp_dtrp": "-", "fdpp_ocsa": "-", "fdpp_etc": "-", "ic_mthn": "제3자배정증자", "ssl_at": "N", "ssl_bgd": "-", "ssl_edd": "-"}');
INSERT INTO "disclosures" VALUES('20260918000455',13,'piic','[기재정정]주요사항보고서(유상증자결정)','20260918',1,'{"rcept_no": "20260923000410", "corp_cls": "K", "corp_code": "00530413", "corp_name": "더코디", "nstk_ostk_cnt": "105,954", "nstk_estk_cnt": "-", "fv_ps": "500", "bfic_tisstk_ostk": "5,160,722", "bfic_tisstk_estk": "-", "fdpp_fclt": "-", "fdpp_bsninh": "-", "fdpp_op": "499,996,926", "fdpp_dtrp": "-", "fdpp_ocsa": "-", "fdpp_etc": "-", "ic_mthn": "제3자배정증자", "ssl_at": "N", "ssl_bgd": "-", "ssl_edd": "-"}');
INSERT INTO "disclosures" VALUES('20260918000457',11,'piic','[기재정정]주요사항보고서(유상증자결정)','20260918',1,'{"rcept_no": "20260922000245", "corp_cls": "Y", "corp_code": "00132868", "corp_name": "우성머티리얼스", "nstk_ostk_cnt": "970,873", "nstk_estk_cnt": "-", "fv_ps": "1,000", "bfic_tisstk_ostk": "17,238,905", "bfic_tisstk_estk": "-", "fdpp_fclt": "-", "fdpp_bsninh": "-", "fdpp_op": "1,999,998,380", "fdpp_dtrp": "-", "fdpp_ocsa": "-", "fdpp_etc": "-", "ic_mthn": "제3자배정증자", "ssl_at": "N", "ssl_bgd": "-", "ssl_edd": "-"}');
INSERT INTO "disclosures" VALUES('20260921000086',14,'piic','[기재정정]주요사항보고서(유상증자결정)','20260921',1,'{"rcept_no": "20260921000086", "corp_cls": "Y", "corp_code": "01688896", "corp_name": "삼성FN리츠", "nstk_ostk_cnt": "19,000,000", "nstk_estk_cnt": "-", "fv_ps": "500", "bfic_tisstk_ostk": "91,050,000", "bfic_tisstk_estk": "-", "fdpp_fclt": "-", "fdpp_bsninh": "-", "fdpp_op": "17,660,000,000", "fdpp_dtrp": "80,000,000,000", "fdpp_ocsa": "-", "fdpp_etc": "-", "ic_mthn": "주주배정후 실권주 일반공모", "ssl_at": "Y", "ssl_bgd": "20260827", "ssl_edd": "20261029"}');
INSERT INTO "disclosures" VALUES('20260921000097',15,'piic','[기재정정]주요사항보고서(유상증자결정)','20260921',1,'{"rcept_no": "20260921000097", "corp_cls": "K", "corp_code": "00587925", "corp_name": "모아라이프플러스", "nstk_ostk_cnt": "2,000,000", "nstk_estk_cnt": "-", "fv_ps": "1,000", "bfic_tisstk_ostk": "21,083,490", "bfic_tisstk_estk": "-", "fdpp_fclt": "-", "fdpp_bsninh": "-", "fdpp_op": "2,000,000,000", "fdpp_dtrp": "-", "fdpp_ocsa": "-", "fdpp_etc": "-", "ic_mthn": "제3자배정증자", "ssl_at": "N", "ssl_bgd": "-", "ssl_edd": "-"}');
INSERT INTO "disclosures" VALUES('20260921000184',16,'piic','[기재정정]주요사항보고서(유상증자결정)','20260921',1,'{"rcept_no": "20260921000184", "corp_cls": "K", "corp_code": "00232007", "corp_name": "상지건설", "nstk_ostk_cnt": "2,200,000", "nstk_estk_cnt": "-", "fv_ps": "5,000", "bfic_tisstk_ostk": "6,828,712", "bfic_tisstk_estk": "-", "fdpp_fclt": "-", "fdpp_bsninh": "-", "fdpp_op": "11,000,000,000", "fdpp_dtrp": "-", "fdpp_ocsa": "-", "fdpp_etc": "-", "ic_mthn": "주주우선공모증자", "ssl_at": "Y", "ssl_bgd": "20260509", "ssl_edd": "20261028"}');
INSERT INTO "disclosures" VALUES('20260921000240',17,'piic','[기재정정]주요사항보고서(유상증자결정)','20260921',1,'{"rcept_no": "20260921000240", "corp_cls": "Y", "corp_code": "00145437", "corp_name": "아센디오", "nstk_ostk_cnt": "2,890,173", "nstk_estk_cnt": "-", "fv_ps": "2,500", "bfic_tisstk_ostk": "7,296,721", "bfic_tisstk_estk": "-", "fdpp_fclt": "-", "fdpp_bsninh": "-", "fdpp_op": "9,999,998,580", "fdpp_dtrp": "-", "fdpp_ocsa": "-", "fdpp_etc": "-", "ic_mthn": "제3자배정증자", "ssl_at": "N", "ssl_bgd": "-", "ssl_edd": "-"}');
INSERT INTO "disclosures" VALUES('20260921000303',11,'piic','[기재정정]주요사항보고서(유상증자결정)','20260921',1,'{"rcept_no": "20260922000245", "corp_cls": "Y", "corp_code": "00132868", "corp_name": "우성머티리얼스", "nstk_ostk_cnt": "970,873", "nstk_estk_cnt": "-", "fv_ps": "1,000", "bfic_tisstk_ostk": "17,238,905", "bfic_tisstk_estk": "-", "fdpp_fclt": "-", "fdpp_bsninh": "-", "fdpp_op": "1,999,998,380", "fdpp_dtrp": "-", "fdpp_ocsa": "-", "fdpp_etc": "-", "ic_mthn": "제3자배정증자", "ssl_at": "N", "ssl_bgd": "-", "ssl_edd": "-"}');
INSERT INTO "disclosures" VALUES('20260921000327',18,'piic','[기재정정]주요사항보고서(유상증자결정)','20260921',1,'{"rcept_no": "20260921000327", "corp_cls": "K", "corp_code": "01423837", "corp_name": "모아데이타", "nstk_ostk_cnt": "3,795,066", "nstk_estk_cnt": "-", "fv_ps": "500", "bfic_tisstk_ostk": "36,381,379", "bfic_tisstk_estk": "-", "fdpp_fclt": "-", "fdpp_bsninh": "-", "fdpp_op": "1,999,999,782", "fdpp_dtrp": "-", "fdpp_ocsa": "-", "fdpp_etc": "-", "ic_mthn": "제3자배정증자", "ssl_at": "N", "ssl_bgd": "-", "ssl_edd": "-"}');
INSERT INTO "disclosures" VALUES('20260921000369',20,'piic','[첨부정정]주요사항보고서(유상증자결정)','20260921',1,'{"rcept_no": "20260910000423", "corp_cls": "K", "corp_code": "01160512", "corp_name": "헝셩그룹", "nstk_ostk_cnt": "20,000,000", "nstk_estk_cnt": "-", "fv_ps": "-", "bfic_tisstk_ostk": "12,461,641", "bfic_tisstk_estk": "-", "fdpp_fclt": "-", "fdpp_bsninh": "-", "fdpp_op": "60,000,000,000", "fdpp_dtrp": "-", "fdpp_ocsa": "-", "fdpp_etc": "-", "ic_mthn": "제3자배정증자", "ssl_at": "N", "ssl_bgd": "-", "ssl_edd": "-"}');
INSERT INTO "disclosures" VALUES('20260921000434',23,'piic','주요사항보고서(유상증자결정)','20260922',0,'{"rcept_no": "20260922000533", "corp_cls": "K", "corp_code": "01235296", "corp_name": "셀리드", "nstk_ostk_cnt": "1,333,332", "nstk_estk_cnt": "-", "fv_ps": "500", "bfic_tisstk_ostk": "29,502,977", "bfic_tisstk_estk": "-", "fdpp_fclt": "-", "fdpp_bsninh": "-", "fdpp_op": "2,999,997,000", "fdpp_dtrp": "-", "fdpp_ocsa": "-", "fdpp_etc": "-", "ic_mthn": "제3자배정증자", "ssl_at": "N", "ssl_bgd": "-", "ssl_edd": "-"}');
INSERT INTO "disclosures" VALUES('20260922000105',24,'piic','[기재정정]주요사항보고서(유상증자결정)','20260922',1,'{"rcept_no": "20260922000105", "corp_cls": "K", "corp_code": "01397903", "corp_name": "엔젠바이오", "nstk_ostk_cnt": "7,150,000", "nstk_estk_cnt": "-", "fv_ps": "1,000", "bfic_tisstk_ostk": "8,936,583", "bfic_tisstk_estk": "-", "fdpp_fclt": "-", "fdpp_bsninh": "-", "fdpp_op": "3,679,100,000", "fdpp_dtrp": "4,000,000,000", "fdpp_ocsa": "-", "fdpp_etc": "-", "ic_mthn": "주주배정후 실권주 일반공모", "ssl_at": "Y", "ssl_bgd": "20260428", "ssl_edd": "20260904"}');
INSERT INTO "disclosures" VALUES('20260922000158',23,'piic','[기재정정]주요사항보고서(유상증자결정)','20260922',1,'{"rcept_no": "20260922000158", "corp_cls": "K", "corp_code": "01235296", "corp_name": "셀리드", "nstk_ostk_cnt": "4,796,163", "nstk_estk_cnt": "-", "fv_ps": "500", "bfic_tisstk_ostk": "29,502,977", "bfic_tisstk_estk": "-", "fdpp_fclt": "-", "fdpp_bsninh": "-", "fdpp_op": "9,999,999,855", "fdpp_dtrp": "-", "fdpp_ocsa": "-", "fdpp_etc": "-", "ic_mthn": "제3자배정증자", "ssl_at": "N", "ssl_bgd": "-", "ssl_edd": "-"}');
INSERT INTO "disclosures" VALUES('20260922000240',25,'piic','[기재정정]주요사항보고서(유상증자결정)','20260922',1,'{"rcept_no": "20260922000240", "corp_cls": "K", "corp_code": "00618410", "corp_name": "KS인더스트리", "nstk_ostk_cnt": "4,885,993", "nstk_estk_cnt": "-", "fv_ps": "500", "bfic_tisstk_ostk": "9,910,487", "bfic_tisstk_estk": "182,815", "fdpp_fclt": "-", "fdpp_bsninh": "-", "fdpp_op": "4,499,999,404", "fdpp_dtrp": "1,500,000,000", "fdpp_ocsa": "-", "fdpp_etc": "-", "ic_mthn": "제3자배정증자", "ssl_at": "N", "ssl_bgd": "-", "ssl_edd": "-"}');
INSERT INTO "disclosures" VALUES('20260922000245',11,'piic','[기재정정]주요사항보고서(유상증자결정)','20260922',1,'{"rcept_no": "20260922000245", "corp_cls": "Y", "corp_code": "00132868", "corp_name": "우성머티리얼스", "nstk_ostk_cnt": "970,873", "nstk_estk_cnt": "-", "fv_ps": "1,000", "bfic_tisstk_ostk": "17,238,905", "bfic_tisstk_estk": "-", "fdpp_fclt": "-", "fdpp_bsninh": "-", "fdpp_op": "1,999,998,380", "fdpp_dtrp": "-", "fdpp_ocsa": "-", "fdpp_etc": "-", "ic_mthn": "제3자배정증자", "ssl_at": "N", "ssl_bgd": "-", "ssl_edd": "-"}');
INSERT INTO "disclosures" VALUES('20260922000378',13,'piic','[기재정정]주요사항보고서(유상증자결정)','20260922',1,'{"rcept_no": "20260922000378", "corp_cls": "K", "corp_code": "00530413", "corp_name": "더코디", "nstk_ostk_cnt": "2,219,403", "nstk_estk_cnt": "-", "fv_ps": "500", "bfic_tisstk_ostk": "5,160,722", "bfic_tisstk_estk": "-", "fdpp_fclt": "-", "fdpp_bsninh": "-", "fdpp_op": "6,999,997,062", "fdpp_dtrp": "-", "fdpp_ocsa": "-", "fdpp_etc": "-", "ic_mthn": "제3자배정증자", "ssl_at": "N", "ssl_bgd": "-", "ssl_edd": "-"}');
INSERT INTO "disclosures" VALUES('20260922000386',26,'piic','[기재정정]주요사항보고서(유상증자결정)','20260922',1,'{"rcept_no": "20260922000386", "corp_cls": "Y", "corp_code": "00122825", "corp_name": "프리티", "nstk_ostk_cnt": "2,000,000", "nstk_estk_cnt": "-", "fv_ps": "2,500", "bfic_tisstk_ostk": "29,577,223", "bfic_tisstk_estk": "-", "fdpp_fclt": "-", "fdpp_bsninh": "-", "fdpp_op": "2,813,000,000", "fdpp_dtrp": "2,187,000,000", "fdpp_ocsa": "-", "fdpp_etc": "-", "ic_mthn": "제3자배정증자", "ssl_at": "N", "ssl_bgd": "-", "ssl_edd": "-"}');
INSERT INTO "disclosures" VALUES('20260922000418',27,'piic','[기재정정]주요사항보고서(유상증자결정)','20260922',1,'{"rcept_no": "20260922000418", "corp_cls": "K", "corp_code": "00550082", "corp_name": "캔버스엔", "nstk_ostk_cnt": "6,585,136", "nstk_estk_cnt": "-", "fv_ps": "500", "bfic_tisstk_ostk": "9,694,991", "bfic_tisstk_estk": "-", "fdpp_fclt": "-", "fdpp_bsninh": "-", "fdpp_op": "13,999,999,136", "fdpp_dtrp": "-", "fdpp_ocsa": "-", "fdpp_etc": "-", "ic_mthn": "제3자배정증자", "ssl_at": "N", "ssl_bgd": "-", "ssl_edd": "-"}');
INSERT INTO "disclosures" VALUES('20260922000533',29,'piic','주요사항보고서(유상증자결정)','20260922',0,'{"rcept_no": "20260922000533", "corp_cls": "K", "corp_code": "01235296", "corp_name": "셀리드", "nstk_ostk_cnt": "1,333,332", "nstk_estk_cnt": "-", "fv_ps": "500", "bfic_tisstk_ostk": "29,502,977", "bfic_tisstk_estk": "-", "fdpp_fclt": "-", "fdpp_bsninh": "-", "fdpp_op": "2,999,997,000", "fdpp_dtrp": "-", "fdpp_ocsa": "-", "fdpp_etc": "-", "ic_mthn": "제3자배정증자", "ssl_at": "N", "ssl_bgd": "-", "ssl_edd": "-"}');
INSERT INTO "disclosures" VALUES('20260923000238',32,'piic','[기재정정]주요사항보고서(유상증자결정)','20260923',1,'{"rcept_no": "20260923000238", "corp_cls": "K", "corp_code": "00406329", "corp_name": "루멘스바이오스", "nstk_ostk_cnt": "1,785,714", "nstk_estk_cnt": "-", "fv_ps": "1,000", "bfic_tisstk_ostk": "24,051,534", "bfic_tisstk_estk": "-", "fdpp_fclt": "1,499,999,600", "fdpp_bsninh": "-", "fdpp_op": "1,000,000,000", "fdpp_dtrp": "-", "fdpp_ocsa": "-", "fdpp_etc": "-", "ic_mthn": "제3자배정증자", "ssl_at": "N", "ssl_bgd": "-", "ssl_edd": "-"}');
INSERT INTO "disclosures" VALUES('20260923000362',35,'piic','[기재정정]주요사항보고서(유상증자결정)','20260923',1,'{"rcept_no": "20260923000362", "corp_cls": "K", "corp_code": "00110750", "corp_name": "GMI벤처", "nstk_ostk_cnt": "196,000", "nstk_estk_cnt": "0", "fv_ps": "2,500", "bfic_tisstk_ostk": "9,545,004", "bfic_tisstk_estk": "-", "fdpp_fclt": "-", "fdpp_bsninh": "-", "fdpp_op": "490,000,000", "fdpp_dtrp": "-", "fdpp_ocsa": "-", "fdpp_etc": "-", "ic_mthn": "제3자배정증자", "ssl_at": "N", "ssl_bgd": "-", "ssl_edd": "-"}');
INSERT INTO "disclosures" VALUES('20260923000390',13,'piic','[기재정정]주요사항보고서(유상증자결정)','20260923',1,'{"rcept_no": "20260923000390", "corp_cls": "K", "corp_code": "00530413", "corp_name": "더코디", "nstk_ostk_cnt": "317,863", "nstk_estk_cnt": "-", "fv_ps": "500", "bfic_tisstk_ostk": "5,160,722", "bfic_tisstk_estk": "-", "fdpp_fclt": "-", "fdpp_bsninh": "-", "fdpp_op": "1,499,995,497", "fdpp_dtrp": "-", "fdpp_ocsa": "-", "fdpp_etc": "-", "ic_mthn": "제3자배정증자", "ssl_at": "N", "ssl_bgd": "-", "ssl_edd": "-"}');
INSERT INTO "disclosures" VALUES('20260923000410',13,'piic','[기재정정]주요사항보고서(유상증자결정)','20260923',1,'{"rcept_no": "20260923000410", "corp_cls": "K", "corp_code": "00530413", "corp_name": "더코디", "nstk_ostk_cnt": "105,954", "nstk_estk_cnt": "-", "fv_ps": "500", "bfic_tisstk_ostk": "5,160,722", "bfic_tisstk_estk": "-", "fdpp_fclt": "-", "fdpp_bsninh": "-", "fdpp_op": "499,996,926", "fdpp_dtrp": "-", "fdpp_ocsa": "-", "fdpp_etc": "-", "ic_mthn": "제3자배정증자", "ssl_at": "N", "ssl_bgd": "-", "ssl_edd": "-"}');
INSERT INTO "disclosures" VALUES('20260923000418',36,'piic','[기재정정]주요사항보고서(유상증자결정)','20260923',1,'{"rcept_no": "20260923000418", "corp_cls": "Y", "corp_code": "00101044", "corp_name": "에이프로젠바이오로직스", "nstk_ostk_cnt": "12,706,481", "nstk_estk_cnt": "-", "fv_ps": "500", "bfic_tisstk_ostk": "16,261,203", "bfic_tisstk_estk": "-", "fdpp_fclt": "-", "fdpp_bsninh": "-", "fdpp_op": "-", "fdpp_dtrp": "-", "fdpp_ocsa": "-", "fdpp_etc": "20,000,001,094", "ic_mthn": "제3자배정증자", "ssl_at": "N", "ssl_bgd": "-", "ssl_edd": "-"}');
INSERT INTO "disclosures" VALUES('20260923000500',37,'piic','[기재정정]주요사항보고서(유상증자결정)','20260923',1,'{"rcept_no": "20260923000500", "corp_cls": "K", "corp_code": "00116426", "corp_name": "이렘", "nstk_ostk_cnt": "4,800,000", "nstk_estk_cnt": "-", "fv_ps": "500", "bfic_tisstk_ostk": "8,065,537", "bfic_tisstk_estk": "-", "fdpp_fclt": "1,460,000,000", "fdpp_bsninh": "-", "fdpp_op": "7,944,000,000", "fdpp_dtrp": "1,924,000,000", "fdpp_ocsa": "-", "fdpp_etc": "-", "ic_mthn": "주주배정증자", "ssl_at": "Y", "ssl_bgd": "20260425", "ssl_edd": "20261120"}');
INSERT INTO "disclosures" VALUES('20260923000531',38,'piic','[기재정정]주요사항보고서(유상증자결정)','20260923',1,'{"rcept_no": "20260923000531", "corp_cls": "K", "corp_code": "00369569", "corp_name": "비케이홀딩스", "nstk_ostk_cnt": "7,000,000", "nstk_estk_cnt": "-", "fv_ps": "500", "bfic_tisstk_ostk": "23,534,735", "bfic_tisstk_estk": "-", "fdpp_fclt": "-", "fdpp_bsninh": "-", "fdpp_op": "2,000,000,000", "fdpp_dtrp": "-", "fdpp_ocsa": "2,270,000,000", "fdpp_etc": "-", "ic_mthn": "제3자배정증자", "ssl_at": "N", "ssl_bgd": "-", "ssl_edd": "-"}');
INSERT INTO "disclosures" VALUES('20260923000543',38,'piic','[기재정정]주요사항보고서(유상증자결정)','20260923',1,'{"rcept_no": "20260923000543", "corp_cls": "K", "corp_code": "00369569", "corp_name": "비케이홀딩스", "nstk_ostk_cnt": "6,000,000", "nstk_estk_cnt": "-", "fv_ps": "500", "bfic_tisstk_ostk": "30,534,735", "bfic_tisstk_estk": "-", "fdpp_fclt": "-", "fdpp_bsninh": "-", "fdpp_op": "2,000,000,000", "fdpp_dtrp": "-", "fdpp_ocsa": "2,734,000,000", "fdpp_etc": "-", "ic_mthn": "제3자배정증자", "ssl_at": "N", "ssl_bgd": "-", "ssl_edd": "-"}');
INSERT INTO "disclosures" VALUES('20260923000576',39,'piic','주요사항보고서(유상증자결정)','20260923',0,'{"rcept_no": "20260923000576", "corp_cls": "K", "corp_code": "00540429", "corp_name": "휴림로봇", "nstk_ostk_cnt": "386,102", "nstk_estk_cnt": "-", "fv_ps": "500", "bfic_tisstk_ostk": "119,559,029", "bfic_tisstk_estk": "-", "fdpp_fclt": "-", "fdpp_bsninh": "-", "fdpp_op": "-", "fdpp_dtrp": "-", "fdpp_ocsa": "2,000,008,360", "fdpp_etc": "-", "ic_mthn": "일반공모증자", "ssl_at": "N", "ssl_bgd": "-", "ssl_edd": "-"}');
INSERT INTO "disclosures" VALUES('20260923000638',40,'piic','주요사항보고서(유상증자결정)','20260923',0,'{"rcept_no": "20260923000638", "corp_cls": "K", "corp_code": "01689266", "corp_name": "케이쓰리아이", "nstk_ostk_cnt": "874,342", "nstk_estk_cnt": "-", "fv_ps": "500", "bfic_tisstk_ostk": "7,486,442", "bfic_tisstk_estk": "-", "fdpp_fclt": "-", "fdpp_bsninh": "-", "fdpp_op": "2,998,993,060", "fdpp_dtrp": "-", "fdpp_ocsa": "-", "fdpp_etc": "-", "ic_mthn": "제3자배정증자", "ssl_at": "N", "ssl_bgd": "-", "ssl_edd": "-"}');
CREATE TABLE notifications (
    seq      INTEGER PRIMARY KEY AUTOINCREMENT,
    topic    TEXT NOT NULL,
    dedup_key TEXT UNIQUE,
    text     TEXT NOT NULL,
    sent_at  TEXT NOT NULL,
    delivered INTEGER NOT NULL
);
INSERT INTO "notifications" VALUES(10,'신규 유증 경남제약','new:20260918000349','[유증수집 #10] 신규 유증 경남제약
주주배정 ✅ 인수권 발생
증자방식: 주주배정증자
규모: 195억 / 신주÷기존주 66%
자금목적: 운영 100.0%
https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260918000349','2026-09-25T13:32:54',0);
INSERT INTO "notifications" VALUES(14,'신규 유증 삼성FN리츠','new:20260921000086','[유증수집 #14] 신규 유증 삼성FN리츠
주주배정 ✅ 인수권 발생
증자방식: 주주배정후 실권주 일반공모
규모: 977억 / 신주÷기존주 21%
자금목적: 운영 18.1%, 채무상환 81.9%
https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260921000086','2026-09-25T13:32:54',0);
INSERT INTO "notifications" VALUES(24,'신규 유증 엔젠바이오','new:20260922000105','[유증수집 #24] 신규 유증 엔젠바이오
주주배정 ✅ 인수권 발생
증자방식: 주주배정후 실권주 일반공모
규모: 77억 / 신주÷기존주 80%
자금목적: 운영 47.9%, 채무상환 52.1%
https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260922000105','2026-09-25T13:32:54',0);
INSERT INTO "notifications" VALUES(37,'신규 유증 이렘','new:20260923000500','[유증수집 #37] 신규 유증 이렘
주주배정 ✅ 인수권 발생
증자방식: 주주배정증자
규모: 113억 / 신주÷기존주 60%
자금목적: 시설 12.9%, 운영 70.1%, 채무상환 17.0%
https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260923000500','2026-09-25T13:32:54',0);
INSERT INTO "notifications" VALUES(41,'인수권 괴리 SK디앤디 12R','gap:SK디앤디 12R:2026-09-23','[유증수집 #41] 인수권 괴리 SK디앤디 12R
2026-09-23 종가 기준
인수권 636 / 이론가 1,075 (본주 3,335 − 발행가 2,260)
괴리율 -40.8% · 인수권 저평가 → 인수권 매수+청약 검토
인수권+청약 신주원가 2,896','2026-09-25T13:33:17',0);
INSERT INTO "notifications" VALUES(42,'인수권 괴리 엘앤씨바이오 12R','gap:엘앤씨바이오 12R:2026-09-23','[유증수집 #42] 인수권 괴리 엘앤씨바이오 12R
2026-09-23 종가 기준
인수권 10,430 / 이론가 8,100 (본주 47,200 − 발행가 39,100)
괴리율 +28.8% · 인수권 고평가 → 인수권 매도 검토
인수권+청약 신주원가 49,530','2026-09-25T13:33:17',0);
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
INSERT INTO "rights_daily" VALUES('2026-09-21','2109801G','SK디앤디 12R','KOSPI',606,645,652,462,2058784,1150502302,44676003,2260,'2026-09-30','210980','SK디앤디',3340,NULL,'krx');
INSERT INTO "rights_daily" VALUES('2026-09-22','2109801G','SK디앤디 12R','KOSPI',640,606,660,552,552988,348033556,44676003,2260,'2026-09-30','210980','SK디앤디',3385,NULL,'krx');
INSERT INTO "rights_daily" VALUES('2026-09-23','2109801G','SK디앤디 12R','KOSPI',636,635,651,606,400542,251293123,44676003,2260,'2026-09-30','210980','SK디앤디',3335,NULL,'krx');
INSERT INTO "rights_daily" VALUES('2026-09-23','2906501G','엘앤씨바이오 12R','KOSDAQ',10430,7690,10890,7690,363822,3476049240,3604466,39100,'2026-10-02','290650','엘앤씨바이오',47200,NULL,'krx');
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
INSERT INTO "schedule_versions" VALUES('20260918000349',10,'2026-09-25T13:44:16','2026-09-22','2026-09-21',NULL,NULL,'2026-10-28','2026-11-02','2026-11-03','2026-11-05','2026-11-17',1499,0.6628181743,'{"evidence": {"record_date": "8.신주배정기준일관계기관의''증권신고서에대한정정신고서제출요구''에따른정정추후결정", "subs_start": "11.청약예정일관계기관의''증권신고서에대한정정신고서제출요구''에따른정정구주주시작일", "subs_end": "11.청약예정일구주주종료일", "payment_date": "12.납입일관계기관의''증권신고서에대한정정신고서제출요구''에따른정정추후결정", "listing_date": "16.신주의상장예정일관계기관의''증권신고서에대한정정신고서제출요구''에따른정정추후결정", "alloc_ratio": "9.1주당신주배정주식수(주)", "issue_price": "6.신주발행가액예정발행가보통주식(원)확정예정일", "price_fix_date": "6.신주발행가액관계기관의''증권신고서에대한정정신고서제출요구''에따른정정확정예정일"}, "parser": 2, "file": "20260918000349.xml"}','["인수권 상장기간 추후결정 (정정 대기)", "⚠ 금감원 정정신고서 제출요구 이력", "권리락일은 기준일 전 1영업일로 추정 (휴장일 목록 기준)", "rights_start 못 찾음", "미검증 파서: 실제 공시 원문으로 정확도 확인 전"]');
INSERT INTO "schedule_versions" VALUES('20260921000086',14,'2026-09-25T13:44:17','2026-09-23','2026-09-22','2026-10-16','2026-10-22','2026-10-29','2026-11-03','2026-11-04','2026-11-11','2026-11-25',5110,0.2086765513,'{"evidence": {"record_date": "8.신주배정기준일", "alloc_ratio": "9.1주당신주배정주식수(주)", "subs_start": "11.청약예정일구주주시작일", "subs_end": "11.청약예정일구주주종료일", "payment_date": "12.납입일", "listing_date": "16.신주의상장예정일", "issue_price": "6.신주발행가액-예정발행가-보통주식(원)1차발행가액확정", "price_fix_date": "6.신주발행가액예정발행가보통주식(원)확정예정일", "rights_start": "신주인수권증서 상장기간 : 2026년 10월 16일 ~ 2026년 10월 22일 (5영업일)4) 금번 유상증자 시 신주인수권증서는 전자증권제도 시행일(2019년 "}, "parser": 2, "file": "20260921000086.xml"}','["권리락일은 기준일 전 1영업일로 추정 (휴장일 목록 기준)", "미검증 파서: 실제 공시 원문으로 정확도 확인 전"]');
INSERT INTO "schedule_versions" VALUES('20260922000105',24,'2026-09-25T13:44:18','2026-07-22','2026-07-21','2026-08-12','2026-08-19','2026-09-04','2026-09-09','2026-09-10','2026-09-17','2026-10-02',1074,0.800804792,'{"evidence": {"listing_date": "16.신주의상장예정일증자등기조기완료및유관기관협의에따른신주상장예정일변경", "record_date": "8.신주배정기준일", "alloc_ratio": "9.1주당신주배정주식수(주)", "subs_start": "11.청약예정일구주주시작일", "subs_end": "11.청약예정일구주주종료일", "payment_date": "12.납입일", "issue_price": "6.신주발행가액확정발행가보통주식(원)", "price_fix_date": "6.신주발행가액예정발행가보통주식(원)확정예정일", "rights_start": "신주인수권증서 상장예정기간 : 2026년 08월 12일 ~ 2026년 08월 19일4) 금번 유상증자시 신주인수권증서는 전자증권제도 시행일(2019년 9월 16일"}, "parser": 2, "file": "20260922000105.xml"}','["권리락일은 기준일 전 1영업일로 추정 (휴장일 목록 기준)", "미검증 파서: 실제 공시 원문으로 정확도 확인 전"]');
INSERT INTO "schedule_versions" VALUES('20260923000500',37,'2026-09-25T13:44:19','2026-10-01','2026-09-30','2026-10-22','2026-10-28','2026-11-04','2026-11-09','2026-11-10','2026-11-12','2026-11-25',2360,0.5955872198,'{"evidence": {"record_date": "8.신주배정기준일", "subs_start": "11.청약예정일구주주시작일", "subs_end": "11.청약예정일구주주종료일", "payment_date": "12.납입일", "listing_date": "16.신주의상장예정일", "rights_start": "라.신주인수권에관한사항-2)신주인수권증서상장예정기간", "alloc_ratio": "9.1주당신주배정주식수(주)", "issue_price": "6.신주발행가액예정발행가보통주식(원)확정예정일", "price_fix_date": "6.신주발행가액일정변경에따른정정확정예정일"}, "parser": 2, "file": "20260923000500.xml"}','["권리락일은 기준일 전 1영업일로 추정 (휴장일 목록 기준)", "미검증 파서: 실제 공시 원문으로 정확도 확인 전"]');
CREATE TABLE stock_daily (
    bas_dd  TEXT NOT NULL,
    code    TEXT NOT NULL,
    name    TEXT,
    close   INTEGER, open INTEGER, high INTEGER, low INTEGER,
    volume  INTEGER, mktcap INTEGER, list_shrs INTEGER,
    PRIMARY KEY (bas_dd, code)
);
INSERT INTO "stock_daily" VALUES('2026-09-17','019570','GMI벤처',2755,2825,2860,2755,12912,26296486020,9545004);
INSERT INTO "stock_daily" VALUES('2026-09-17','101000','KS인더스트리',1995,2090,2130,1883,260646,19771421565,9910487);
INSERT INTO "stock_daily" VALUES('2026-09-17','123010','MSDI',2925,3140,3140,2905,185961,59131118475,20215767);
INSERT INTO "stock_daily" VALUES('2026-09-17','053950','경남제약',2280,2300,2400,2270,311977,44732799720,19619649);
INSERT INTO "stock_daily" VALUES('2026-09-17','224060','더코디',7830,7140,7960,6920,315002,40408453260,5160722);
INSERT INTO "stock_daily" VALUES('2026-09-17','038060','루멘스바이오스',689,0,0,0,0,33143014541,48103069);
INSERT INTO "stock_daily" VALUES('2026-09-17','288980','모아데이타',270,295,295,263,1223100,9822972330,36381379);
INSERT INTO "stock_daily" VALUES('2026-09-17','142760','모아라이프플러스',490,496,498,470,146407,10330910100,21083490);
INSERT INTO "stock_daily" VALUES('2026-09-17','050090','비케이홀딩스',867,877,880,841,65246,20404615245,23534735);
INSERT INTO "stock_daily" VALUES('2026-09-17','223310','사토시홀딩스',3085,3135,3195,3010,23514,16056320570,5204642);
INSERT INTO "stock_daily" VALUES('2026-09-17','009620','삼보산업',4300,4475,4700,3925,22028,15026818700,3494609);
INSERT INTO "stock_daily" VALUES('2026-09-17','042940','상지건설',5740,5700,5800,5700,20343,39196806880,6828712);
INSERT INTO "stock_daily" VALUES('2026-09-17','299660','셀리드',2280,2220,2335,2165,469014,67266787560,29502977);
INSERT INTO "stock_daily" VALUES('2026-09-17','092600','앤씨앤',2825,2825,2825,2825,50256,14172185975,5016703);
INSERT INTO "stock_daily" VALUES('2026-09-17','354200','엔젠바이오',1457,1604,1687,1444,685944,13020601431,8936583);
INSERT INTO "stock_daily" VALUES('2026-09-17','009730','이렘',2100,1986,2130,1979,54387,16748556300,7975503);
INSERT INTO "stock_daily" VALUES('2026-09-17','277410','인산가',5680,5650,5980,5610,5114,21817732000,3841150);
INSERT INTO "stock_daily" VALUES('2026-09-17','210120','캔버스엔',1757,1797,1825,1656,74454,17034099187,9694991);
INSERT INTO "stock_daily" VALUES('2026-09-17','079190','케스피온',1365,1366,1490,1349,25800,13088818470,9588878);
INSERT INTO "stock_daily" VALUES('2026-09-17','431190','케이쓰리아이',3395,3435,3435,3320,34798,25416470590,7486442);
INSERT INTO "stock_daily" VALUES('2026-09-17','900270','헝셩그룹',2880,2905,3195,2750,248004,30851389440,10712288);
INSERT INTO "stock_daily" VALUES('2026-09-17','090710','휴림로봇',6130,6150,6220,6080,531514,732896847770,119559029);
INSERT INTO "stock_daily" VALUES('2026-09-17','448730','삼성FN리츠',5360,5300,5380,5230,65938,488028000000,91050000);
INSERT INTO "stock_daily" VALUES('2026-09-17','012170','아센디오',2940,2885,3050,2865,13788,21452359740,7296721);
INSERT INTO "stock_daily" VALUES('2026-09-17','003060','에이프로젠바이오로직스',1636,1631,1665,1620,63457,26603328108,16261203);
INSERT INTO "stock_daily" VALUES('2026-09-17','011300','우성머티리얼스',2310,2425,2425,2160,171609,39821870550,17238905);
INSERT INTO "stock_daily" VALUES('2026-09-17','006490','프리티',2190,2030,2210,1937,112056,38864469270,17746333);
INSERT INTO "stock_daily" VALUES('2026-09-18','019570','GMI벤처',2745,2765,2765,2730,16225,26201035980,9545004);
INSERT INTO "stock_daily" VALUES('2026-09-18','101000','KS인더스트리',2075,2040,2240,1990,272393,20564260525,9910487);
INSERT INTO "stock_daily" VALUES('2026-09-18','123010','MSDI',2830,2950,3085,2810,168560,57210620610,20215767);
INSERT INTO "stock_daily" VALUES('2026-09-18','053950','경남제약',2180,2335,2335,2145,231118,42770834820,19619649);
INSERT INTO "stock_daily" VALUES('2026-09-18','224060','더코디',5490,5780,5940,5490,706720,28332363780,5160722);
INSERT INTO "stock_daily" VALUES('2026-09-18','038060','루멘스바이오스',689,0,0,0,0,33143014541,48103069);
INSERT INTO "stock_daily" VALUES('2026-09-18','288980','모아데이타',270,271,286,263,2594154,9822972330,36381379);
INSERT INTO "stock_daily" VALUES('2026-09-18','142760','모아라이프플러스',478,482,496,464,173985,10077908220,21083490);
INSERT INTO "stock_daily" VALUES('2026-09-18','050090','비케이홀딩스',853,870,870,812,99212,20075128955,23534735);
INSERT INTO "stock_daily" VALUES('2026-09-18','223310','사토시홀딩스',3080,3085,3225,3065,25084,16030297360,5204642);
INSERT INTO "stock_daily" VALUES('2026-09-18','009620','삼보산업',4645,4390,5190,4175,57313,16232458805,3494609);
INSERT INTO "stock_daily" VALUES('2026-09-18','042940','상지건설',5780,5960,5960,5580,21437,39469955360,6828712);
INSERT INTO "stock_daily" VALUES('2026-09-18','299660','셀리드',2310,2250,2370,2250,292903,68151876870,29502977);
INSERT INTO "stock_daily" VALUES('2026-09-18','092600','앤씨앤',3670,3670,3670,3670,53180,18411300010,5016703);
INSERT INTO "stock_daily" VALUES('2026-09-18','354200','엔젠바이오',1345,1469,1469,1333,394239,12019704135,8936583);
INSERT INTO "stock_daily" VALUES('2026-09-18','009730','이렘',2165,2100,2200,1998,49653,17266963995,7975503);
INSERT INTO "stock_daily" VALUES('2026-09-18','277410','인산가',5700,5700,5890,5650,2564,21894555000,3841150);
INSERT INTO "stock_daily" VALUES('2026-09-18','210120','캔버스엔',1750,1766,1888,1703,61286,16966234250,9694991);
INSERT INTO "stock_daily" VALUES('2026-09-18','079190','케스피온',1281,1381,1385,1260,152336,12283352718,9588878);
INSERT INTO "stock_daily" VALUES('2026-09-18','431190','케이쓰리아이',3895,3500,4065,3480,401859,29159691590,7486442);
INSERT INTO "stock_daily" VALUES('2026-09-18','900270','헝셩그룹',3090,2985,3250,2810,391171,33100969920,10712288);
INSERT INTO "stock_daily" VALUES('2026-09-18','090710','휴림로봇',6450,6250,6540,6210,2106184,771155737050,119559029);
INSERT INTO "stock_daily" VALUES('2026-09-18','448730','삼성FN리츠',5340,5360,5700,5300,483052,486207000000,91050000);
INSERT INTO "stock_daily" VALUES('2026-09-18','012170','아센디오',3055,3075,3080,2715,15770,22291482655,7296721);
INSERT INTO "stock_daily" VALUES('2026-09-18','003060','에이프로젠바이오로직스',1631,1651,1665,1625,49969,26522022093,16261203);
INSERT INTO "stock_daily" VALUES('2026-09-18','011300','우성머티리얼스',2295,2300,2430,2210,51162,39563286975,17238905);
INSERT INTO "stock_daily" VALUES('2026-09-18','006490','프리티',1535,1825,1826,1535,1061637,27240621155,17746333);
INSERT INTO "stock_daily" VALUES('2026-09-21','019570','GMI벤처',2735,2715,2750,2710,12274,26105585940,9545004);
INSERT INTO "stock_daily" VALUES('2026-09-21','101000','KS인더스트리',1970,2040,2075,1890,276075,19523659390,9910487);
INSERT INTO "stock_daily" VALUES('2026-09-21','123010','MSDI',3020,2840,3090,2750,95541,61051616340,20215767);
INSERT INTO "stock_daily" VALUES('2026-09-21','053950','경남제약',2110,2160,2220,2110,180127,41397459390,19619649);
INSERT INTO "stock_daily" VALUES('2026-09-21','224060','더코디',5230,5450,6410,4650,1331124,26990576060,5160722);
INSERT INTO "stock_daily" VALUES('2026-09-21','038060','루멘스바이오스',689,0,0,0,0,33143014541,48103069);
INSERT INTO "stock_daily" VALUES('2026-09-21','288980','모아데이타',263,273,286,260,1346128,9568302677,36381379);
INSERT INTO "stock_daily" VALUES('2026-09-21','142760','모아라이프플러스',470,478,479,464,142167,9909240300,21083490);
INSERT INTO "stock_daily" VALUES('2026-09-21','050090','비케이홀딩스',856,854,860,818,91246,20145733160,23534735);
INSERT INTO "stock_daily" VALUES('2026-09-21','223310','사토시홀딩스',3030,3090,3180,2960,22542,15770065260,5204642);
INSERT INTO "stock_daily" VALUES('2026-09-21','009620','삼보산업',4790,4600,4950,4490,36090,16739177110,3494609);
INSERT INTO "stock_daily" VALUES('2026-09-21','042940','상지건설',5900,5780,6090,5700,54737,40289400800,6828712);
INSERT INTO "stock_daily" VALUES('2026-09-21','299660','셀리드',2220,2315,2320,2215,1919460,65496608940,29502977);
INSERT INTO "stock_daily" VALUES('2026-09-21','092600','앤씨앤',3200,4770,4770,3165,2568489,16053449600,5016703);
INSERT INTO "stock_daily" VALUES('2026-09-21','354200','엔젠바이오',1385,1372,1450,1302,704332,12377167455,8936583);
INSERT INTO "stock_daily" VALUES('2026-09-21','009730','이렘',1998,2165,2165,1996,38898,15935054994,7975503);
INSERT INTO "stock_daily" VALUES('2026-09-21','277410','인산가',5680,5820,5820,5600,1031,21817732000,3841150);
INSERT INTO "stock_daily" VALUES('2026-09-21','210120','캔버스엔',2275,1814,2275,1694,775474,22056104525,9694991);
INSERT INTO "stock_daily" VALUES('2026-09-21','079190','케스피온',1409,1370,1420,1290,60736,13510729102,9588878);
INSERT INTO "stock_daily" VALUES('2026-09-21','431190','케이쓰리아이',3775,3810,3945,3555,87356,28261318550,7486442);
INSERT INTO "stock_daily" VALUES('2026-09-21','900270','헝셩그룹',2905,3080,3080,2850,161912,31119196640,10712288);
INSERT INTO "stock_daily" VALUES('2026-09-21','090710','휴림로봇',6510,6520,6640,6320,1352723,778329278790,119559029);
INSERT INTO "stock_daily" VALUES('2026-09-21','210980','SK디앤디',3340,3645,3645,3340,260151,62182055880,18617382);
INSERT INTO "stock_daily" VALUES('2026-09-21','448730','삼성FN리츠',5000,5550,5550,4960,384083,455250000000,91050000);
INSERT INTO "stock_daily" VALUES('2026-09-21','012170','아센디오',3200,3055,3250,2975,22872,23349507200,7296721);
INSERT INTO "stock_daily" VALUES('2026-09-21','003060','에이프로젠바이오로직스',1602,1631,1659,1594,110867,26050447206,16261203);
INSERT INTO "stock_daily" VALUES('2026-09-21','011300','우성머티리얼스',2295,2300,2365,2250,113146,39563286975,17238905);
INSERT INTO "stock_daily" VALUES('2026-09-21','006490','프리티',1475,1501,1550,1409,302514,26175841175,17746333);
INSERT INTO "stock_daily" VALUES('2026-09-22','019570','GMI벤처',2710,2720,2780,2700,11178,25866960840,9545004);
INSERT INTO "stock_daily" VALUES('2026-09-22','101000','KS인더스트리',1379,1970,1990,1379,146976,13666561573,9910487);
INSERT INTO "stock_daily" VALUES('2026-09-22','123010','MSDI',3340,3065,3560,3055,704153,67520661780,20215767);
INSERT INTO "stock_daily" VALUES('2026-09-22','053950','경남제약',2030,2110,2150,2015,143169,39827887470,19619649);
INSERT INTO "stock_daily" VALUES('2026-09-22','224060','더코디',4180,5230,5230,4060,889648,21571817960,5160722);
INSERT INTO "stock_daily" VALUES('2026-09-22','038060','루멘스바이오스',689,0,0,0,0,33143014541,48103069);
INSERT INTO "stock_daily" VALUES('2026-09-22','288980','모아데이타',252,263,267,251,796141,9168107508,36381379);
INSERT INTO "stock_daily" VALUES('2026-09-22','142760','모아라이프플러스',470,470,500,464,114728,9909240300,21083490);
INSERT INTO "stock_daily" VALUES('2026-09-22','050090','비케이홀딩스',847,849,853,817,53334,19933920545,23534735);
INSERT INTO "stock_daily" VALUES('2026-09-22','223310','사토시홀딩스',3105,3135,3270,3010,28133,16160413410,5204642);
INSERT INTO "stock_daily" VALUES('2026-09-22','009620','삼보산업',5030,4780,5190,4780,26174,17577883270,3494609);
INSERT INTO "stock_daily" VALUES('2026-09-22','042940','상지건설',5670,5680,5940,5650,25174,38718797040,6828712);
INSERT INTO "stock_daily" VALUES('2026-09-22','299660','셀리드',2885,2410,2885,2410,1991482,85116088645,29502977);
INSERT INTO "stock_daily" VALUES('2026-09-22','092600','앤씨앤',2800,3005,3140,2550,1206902,14046768400,5016703);
INSERT INTO "stock_daily" VALUES('2026-09-22','354200','엔젠바이오',1309,1367,1373,1303,207399,11697987147,8936583);
INSERT INTO "stock_daily" VALUES('2026-09-22','009730','이렘',1998,2015,2025,1901,95300,15935054994,7975503);
INSERT INTO "stock_daily" VALUES('2026-09-22','277410','인산가',5600,5680,5960,5580,3770,21510440000,3841150);
INSERT INTO "stock_daily" VALUES('2026-09-22','210120','캔버스엔',1912,2135,2245,1855,732471,18536822792,9694991);
INSERT INTO "stock_daily" VALUES('2026-09-22','079190','케스피온',1382,1447,1448,1353,16412,13251829396,9588878);
INSERT INTO "stock_daily" VALUES('2026-09-22','431190','케이쓰리아이',3850,3805,4020,3740,117685,28822801700,7486442);
INSERT INTO "stock_daily" VALUES('2026-09-22','900270','헝셩그룹',2770,2925,2925,2740,160847,29673037760,10712288);
INSERT INTO "stock_daily" VALUES('2026-09-22','090710','휴림로봇',6400,6580,6700,6400,1218855,765177785600,119559029);
INSERT INTO "stock_daily" VALUES('2026-09-22','210980','SK디앤디',3385,3395,3475,3340,118546,63019838070,18617382);
INSERT INTO "stock_daily" VALUES('2026-09-22','448730','삼성FN리츠',4795,5000,5080,4795,314468,436584750000,91050000);
INSERT INTO "stock_daily" VALUES('2026-09-22','012170','아센디오',2820,3130,3140,2800,43679,20576753220,7296721);
INSERT INTO "stock_daily" VALUES('2026-09-22','003060','에이프로젠바이오로직스',1601,1625,1625,1591,135740,26034186003,16261203);
INSERT INTO "stock_daily" VALUES('2026-09-22','011300','우성머티리얼스',2720,2470,2960,2385,879371,46889821600,17238905);
INSERT INTO "stock_daily" VALUES('2026-09-22','006490','프리티',1381,1534,1554,1381,177256,24507685873,17746333);
INSERT INTO "stock_daily" VALUES('2026-09-23','019570','GMI벤처',2740,2680,2750,2680,14006,26153310960,9545004);
INSERT INTO "stock_daily" VALUES('2026-09-23','101000','KS인더스트리',1321,1280,1510,1100,506178,13091753327,9910487);
INSERT INTO "stock_daily" VALUES('2026-09-23','123010','MSDI',3360,3345,3395,3270,179193,67924977120,20215767);
INSERT INTO "stock_daily" VALUES('2026-09-23','053950','경남제약',1971,2050,2050,1970,83248,38670328179,19619649);
INSERT INTO "stock_daily" VALUES('2026-09-23','224060','더코디',4395,3890,4650,3850,737370,22681373190,5160722);
INSERT INTO "stock_daily" VALUES('2026-09-23','038060','루멘스바이오스',689,0,0,0,0,33143014541,48103069);
INSERT INTO "stock_daily" VALUES('2026-09-23','288980','모아데이타',246,253,262,240,1070945,8949819234,36381379);
INSERT INTO "stock_daily" VALUES('2026-09-23','142760','모아라이프플러스',467,471,509,464,100069,9845989830,21083490);
INSERT INTO "stock_daily" VALUES('2026-09-23','050090','비케이홀딩스',717,847,847,695,251358,16874404995,23534735);
INSERT INTO "stock_daily" VALUES('2026-09-23','223310','사토시홀딩스',3000,3105,3175,2955,20819,24385854000,8128618);
INSERT INTO "stock_daily" VALUES('2026-09-23','009620','삼보산업',5060,5030,5200,4930,20187,17682721540,3494609);
INSERT INTO "stock_daily" VALUES('2026-09-23','042940','상지건설',5600,5890,5890,5590,17785,38240787200,6828712);
INSERT INTO "stock_daily" VALUES('2026-09-23','299660','셀리드',2620,3000,3480,2575,7834941,77297799740,29502977);
INSERT INTO "stock_daily" VALUES('2026-09-23','092600','앤씨앤',2945,2765,2945,2680,207017,14774190335,5016703);
INSERT INTO "stock_daily" VALUES('2026-09-23','354200','엔젠바이오',1274,1309,1325,1273,127916,11385206742,8936583);
INSERT INTO "stock_daily" VALUES('2026-09-23','290650','엘앤씨바이오',47200,46450,47800,46400,60473,1272970028800,26969704);
INSERT INTO "stock_daily" VALUES('2026-09-23','009730','이렘',1962,2020,2020,1950,37470,15647936886,7975503);
INSERT INTO "stock_daily" VALUES('2026-09-23','277410','인산가',5610,5630,5700,5570,1262,21548851500,3841150);
INSERT INTO "stock_daily" VALUES('2026-09-23','210120','캔버스엔',1893,1848,1984,1815,150302,18352617963,9694991);
INSERT INTO "stock_daily" VALUES('2026-09-23','079190','케스피온',1329,1422,1422,1283,65274,12743618862,9588878);
INSERT INTO "stock_daily" VALUES('2026-09-23','431190','케이쓰리아이',4360,3850,4860,3850,1695384,32640887120,7486442);
INSERT INTO "stock_daily" VALUES('2026-09-23','900270','헝셩그룹',2765,2850,2870,2600,86089,34456437365,12461641);
INSERT INTO "stock_daily" VALUES('2026-09-23','090710','휴림로봇',6330,6520,7030,6280,2270654,756808653570,119559029);
INSERT INTO "stock_daily" VALUES('2026-09-23','210980','SK디앤디',3335,3385,3465,3265,88403,62088968970,18617382);
INSERT INTO "stock_daily" VALUES('2026-09-23','448730','삼성FN리츠',4855,4860,4995,4805,145793,442047750000,91050000);
INSERT INTO "stock_daily" VALUES('2026-09-23','012170','아센디오',2935,2820,3000,2795,22581,21415876135,7296721);
INSERT INTO "stock_daily" VALUES('2026-09-23','003060','에이프로젠바이오로직스',1639,1604,1680,1593,114406,26652111717,16261203);
INSERT INTO "stock_daily" VALUES('2026-09-23','011300','우성머티리얼스',2860,2635,2960,2635,145098,49303268300,17238905);
INSERT INTO "stock_daily" VALUES('2026-09-23','006490','프리티',1355,1434,1440,1313,88159,24046281215,17746333);
DELETE FROM "sqlite_sequence";
INSERT INTO "sqlite_sequence" VALUES('cases',40);
INSERT INTO "sqlite_sequence" VALUES('notifications',42);
COMMIT;
