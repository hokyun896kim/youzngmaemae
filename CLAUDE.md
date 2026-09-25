# 유증 이벤트 매매 프로젝트
- 전체 배경·결론은 docs/brief.md 참고 (이미 결론 난 내용은 재논의 금지)
- 현재 단계: Phase 0 수집기 (DART 유증 감지 + 일정 파싱 + 인수권 시세 저장)
- 알림 메시지는 맨 앞에 [작업명 #순번] 소주제 헤더 필수
- "검증 필요" 표시 항목은 실제 API로 확인 후 사용

## 코드 구조 (Phase 0)
- `yujeung/dart.py` — OpenDART 호출 (list / piicDecsn / estkRs / document)
- `yujeung/detect.py` — 유상증자결정 감지 + 주주배정 필터 + 케이스 묶기
- `yujeung/schedule_parser.py` — 공시 원문에서 일정·발행가 추출 (정정마다 버전 저장)
- `yujeung/krx.py`, `yujeung/prices.py` — 인수권·본주 시세 수집, 괴리율 계산
- `yujeung/notify.py` — 텔레그램 알림 (헤더 자동 부착, 순번은 DB에서 증가)
- `yujeung/cli.py` — `python -m yujeung <명령>` 진입점
- 원칙: API 응답 원본(raw)은 항상 `raw_responses`에 먼저 저장 → 파싱이 틀려도 재처리 가능
- 검증 상태는 `docs/verification.md`에 기록, 실측은 `python -m yujeung verify`
- 테스트: `python -m pytest -q` (네트워크 불필요)
