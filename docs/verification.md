# 검증 상태

원칙: "검증 필요" 항목은 실제 API로 확인 후 사용 → `python -m yujeung verify` (또는 Actions → Run workflow → command=`verify`).

| 항목 | 상태 | 근거 / 남은 일 |
|---|---|---|
| DART `list.json` 공시검색 (corp_code 없으면 3개월 제한) | 문서 확인 | OpenDART 개발가이드 DS001/2019001 사본. **실호출 미확인** |
| DART `piicDecsn.json` 필드 (`ic_mthn`, `nstk_ostk_cnt`, `bfic_tisstk_ostk`, `fdpp_*`, `ssl_*`) — **corp_code 필수** | 문서 확인 | DS005/2020023 사본 + 오픈소스 테스트 픽스처(남양유업 2023). **실호출 미확인** |
| DART `estkRs.json` (청약기일·납입기일·배정기준일·모집가액) | 문서 확인 | DS006/2020054. **실호출 미확인** |
| DART `document.xml` 원문 → 일정 파서 | ⚠️ 미검증 | 합성 픽스처로만 테스트. 권리락일·인수권 상장기간·발행가 확정일은 구조화 API에 없어 원문 파싱 필수. **실제 공시 5~10건으로 정확도 확인 필요** |
| KRX Open API `sto/sr_bydd_trd` 신주인수권증서 일별매매정보 (2010-02-12~) | 문서 확인 | 필드: `ISU_PRC`(발행가), `TARSTK_ISU_SRT_CD`/`TARSTK_ISU_PRSNT_PRC`(대상 본주), `DELIST_DD`. 출처: KRX Open API 서비스 목록, seokhoonj/krx-openapi 카탈로그. **실호출 미확인** |
| KRX `sto/stk_bydd_trd`, `ksq_bydd_trd` 본주 일별 | 문서 확인 | 위와 동일 |
| KRX 인수권 `ISU_CD` 형식, `TARSTK_ISU_SRT_CD` 형식(A 접두 여부) | ⚠️ 미확인 | `short_code()`가 A접두·ISIN·6자리 모두 처리하도록 방어 |
| KRX Open API 데이터 갱신 시각 / 일일 호출 한도 | ⚠️ 미확인 | 최근 5영업일을 매번 재수집하므로 갱신 시각과 무관하게 동작. 한도는 백필 때 확인 |
| GitHub Actions(미국 IP) → KRX Open API 접근 | ⚠️ 미확인 | DART는 KR-hegemony Actions에서 동작 중. KRX는 첫 `verify` 실행으로 확인 |
| 권리락일 = 기준일 전 1영업일 | 추정 | `calendar_kr.KRX_HOLIDAYS` 2026 휴장일 목록 검증 필요 |
| 2차 발행가 산정식·공매도 참여제한 세부 | 미착수 | brief §7 그대로 |
