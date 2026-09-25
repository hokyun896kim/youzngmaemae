# 유증 이벤트 매매 프로젝트
- 전체 배경·결론은 docs/brief.md 참고 (이미 결론 난 내용은 재논의 금지)
- 현재 단계: Phase 0 수집기 (DART 유증 감지 + 일정 파싱 + 인수권 시세 저장)
- 알림 메시지는 맨 앞에 [작업명 #순번] 소주제 헤더 필수
- "검증 필요" 표시 항목은 실제 API로 확인 후 사용

- 결정 로그: docs/decisions.md (brief 이후 확정 사항 — 실행은 GitHub Actions + Netlify 정적 웹)

## 코드 구조 (Phase 0)
- `yujeung/dart.py` — OpenDART (list / piicDecsn / estkRs / document). piicDecsn 은 corp_code 필수 → list.json 으로 먼저 감지
- `yujeung/detect.py` — 유상증자결정 감지 + 주주배정 필터 + 정정 공시를 케이스로 묶기
- `yujeung/schedule_parser.py` — 공시 원문에서 일정·발행가 추출 (정정마다 schedule_versions 에 버전 저장)
- `yujeung/krx.py`, `yujeung/prices.py` — KRX Open API 인수권(sr_bydd_trd)·본주 시세, 괴리율
- `yujeung/notify.py` — 텔레그램 (헤더 자동, 순번 = notifications.seq)
- `yujeung/pipeline.py` — daily 흐름, `yujeung/export.py` — data/site.json, `index.html` — 화면
- DB: 실행 시 `data/yujeung.sql`(커밋되는 텍스트 덤프) → SQLite 복원 → 갱신 → 다시 덤프. 바이너리는 커밋 금지
- 검증 상태는 docs/verification.md, 실측은 `python -m yujeung verify`
- 테스트: `python -m pytest -q` (네트워크 불필요). 테스트 픽스처는 합성 데이터
- 날짜는 항상 KST 기준 (`cli.today_kst`) — Actions 러너는 UTC
