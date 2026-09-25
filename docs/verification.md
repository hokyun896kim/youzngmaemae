# 검증 상태

원칙: "검증 필요" 항목은 실제 API로 확인 후 사용 → `python -m yujeung verify` (또는 Actions → Run workflow → command=`verify`).

| 항목 | 상태 | 근거 / 남은 일 |
|---|---|---|
| DART `list.json` 공시검색 (corp_code 없으면 3개월 제한) | ✅ 실측 | 2026-09-25 Actions: 80일 1,963건, 유상증자결정 606건 |
| DART `piicDecsn.json` 필드 (`ic_mthn`, `nstk_ostk_cnt`, `bfic_tisstk_ostk`, `fdpp_*`, `ssl_*`) — **corp_code 필수** | ✅ 실측 | 6개사 필드 정상 (증자방식 값 예: 주주배정증자 / 제3자배정증자 / 일반공모증자) |
| DART `estkRs.json` (청약기일·납입기일·배정기준일·모집가액) | 문서 확인 | DS006/2020054. **실호출 미확인** |
| DART `document.xml` 원문 → 일정 파서 | 🟡 1건 실측 | 이렘(2026-09-23 기재정정): 수정 후 10개 항목 전부 추출(예정발행가 2,360 포함). 발행가 누락 버그(가격+날짜 한 행) 수정·회귀테스트 추가. 정정 공시 본문에 옛 날짜가 남는 사례 확인 → 청약일 이후 확정일 배제. **DART 원문과 값 대조 + 추가 5건 필요** |
| KRX Open API `sto/sr_bydd_trd` 신주인수권증서 일별매매정보 (2010-02-12~) | ✅ 실측 | 2026-09-25 서비스 승인 후 성공. **SK디앤디 12R 9/23 종가 636원 = 브리프 일치**, `ISU_PRC` 2,260, `DELIST_DD` 20260930. 2020-04-14 과거분도 조회됨 → H1 과거 백테스트 가능. 인수권 `ISU_CD` 형식 예: `2109801G` |
| KRX `TARSTK_ISU_PRSNT_PRC` (대상 본주 가격) | ⚠️ 종가 아님 의심 | SK디앤디 9/23: 3,335 vs 브리프 종가 3,395. 괴리율은 stk/ksq 종가 우선 계산(대체값으로만 사용). `verify`에서 두 값 비교 중 |
| KRX `sto/stk_bydd_trd`, `ksq_bydd_trd` 본주 일별 | ✅ 실측 | 유가 942 / 코스닥 1,821종목. `ISU_CD`는 6자리 단축코드, 필드명 카탈로그와 일치 |
| KRX 인수권 `ISU_CD` 형식, `TARSTK_ISU_SRT_CD` 형식(A 접두 여부) | ✅ 실측 | `TARSTK_ISU_SRT_CD` = `210980` (6자리, 접두 없음) |
| KRX Open API 데이터 갱신 시각 / 일일 호출 한도 | ⚠️ 미확인 | 최근 5영업일을 매번 재수집하므로 갱신 시각과 무관하게 동작. 한도는 백필 때 확인 |
| GitHub Actions(미국 IP) → KRX Open API 접근 | ✅ 실측 | stk/ksq 성공 — 해외 IP 차단 없음 |
| 권리락일 = 기준일 전 1영업일 | 추정 | `calendar_kr.KRX_HOLIDAYS` 2026 휴장일 목록 검증 필요 |
| 2차 발행가 산정식·공매도 참여제한 세부 | 미착수 | brief §7 그대로 |
