# 검증 상태

원칙: "검증 필요" 항목은 실제 API로 확인 후 사용 → `python -m yujeung verify` (또는 Actions → Run workflow → command=`verify`).

| 항목 | 상태 | 근거 / 남은 일 |
|---|---|---|
| DART `list.json` 공시검색 (corp_code 없으면 3개월 제한) | ✅ 실측 | 2026-09-25 Actions: 80일 1,963건, 유상증자결정 606건 |
| DART `piicDecsn.json` 필드 (`ic_mthn`, `nstk_ostk_cnt`, `bfic_tisstk_ostk`, `fdpp_*`, `ssl_*`) — **corp_code 필수** | ✅ 실측 | 6개사 필드 정상 (증자방식 값 예: 주주배정증자 / 제3자배정증자 / 일반공모증자) |
| DART `estkRs.json` (청약기일·납입기일·배정기준일·모집가액) | 문서 확인 | DS006/2020054. **실호출 미확인** |
| DART `document.xml` 원문 → 일정 파서 | 🟡 1건 실측 | 이렘(2026-09-23 기재정정): 수정 후 10개 항목 전부 추출(예정발행가 2,360 포함). 발행가 누락 버그(가격+날짜 한 행) 수정·회귀테스트 추가. 정정 공시 본문에 옛 날짜가 남는 사례 확인 → 청약일 이후 확정일 배제. **DART 원문과 값 대조 + 추가 5건 필요** |
| KRX Open API `sto/sr_bydd_trd` 신주인수권증서 일별매매정보 (2010-02-12~) | ✅ 실측 | 2026-09-25 서비스 승인 후 성공. **SK디앤디 12R 9/23 종가 636원 = 브리프 일치**, `ISU_PRC` 2,260, `DELIST_DD` 20260930. 2020-04-14 과거분도 조회됨 → H1 과거 백테스트 가능. 인수권 `ISU_CD` 형식 예: `2109801G` |
| KRX `TARSTK_ISU_PRSNT_PRC` (대상 본주 가격) | ✅ 실측 = 종가 | SK디앤디 9/23: 3,335 = stk_bydd_trd 종가 3,335. **브리프 §3의 9/23 본주 3,395원은 오기** → 실제 이론가 1,075원, 괴리율 −40.8% (원가 2,896원은 동일) |
| KRX `sto/stk_bydd_trd`, `ksq_bydd_trd` 본주 일별 | ✅ 실측 | 유가 942 / 코스닥 1,821종목. `ISU_CD`는 6자리 단축코드, 필드명 카탈로그와 일치 |
| KRX 인수권 `ISU_CD` 형식, `TARSTK_ISU_SRT_CD` 형식(A 접두 여부) | ✅ 실측 | `TARSTK_ISU_SRT_CD` = `210980` (6자리, 접두 없음) |
| KRX Open API 데이터 갱신 시각 / 일일 호출 한도 | ⚠️ 미확인 | 최근 5영업일을 매번 재수집하므로 갱신 시각과 무관하게 동작. 한도는 백필 때 확인 |
| GitHub Actions(미국 IP) → KRX Open API 접근 | ✅ 실측 | stk/ksq 성공 — 해외 IP 차단 없음 |
| 권리락일 = 기준일 전 1영업일 | 추정 | `calendar_kr.KRX_HOLIDAYS` 2026 휴장일 목록 검증 필요 |
| 2차 발행가 산정식·공매도 참여제한 세부 | 미착수 | brief §7 그대로 |
| 네이버 금융 일봉 `fchart.stock.naver.com/sise.nhn` (본주·KOSPI·KOSDAQ) | ⚠️ 미확인 | 52주 위치·상장 후 수익률·지수 초과수익에 사용. pykrx OHLCV 와 같은 출처(KR-hegemony Actions 에서 동작). `verify` 에 점검 추가 |
| DART `fnlttSinglAcntAll.json` 직전 분기 영업이익 | ⚠️ 미확인 | KR-hegemony 와 같은 API·계정 식별. 분·반기 `thstrm_amount` = 3개월 금액이라는 가정 검증 필요. `verify` 에 점검 추가 |
| 원문 휴리스틱: 최대주주 청약 참여, 인수방식(총액/잔액/모집주선) | ⚠️ 미검증 | 문장 패턴 기반. 못 찾으면 '미확인'(GPT 확인 필요). 증권신고서 API 인수인정보(`udtmth`)가 있으면 그걸 우선 |
| 3자배정 공시 '청약일 | 날짜' 한 줄 | 🟡 합성 픽스처 | 청약일=납입일 제외 규칙용 |
