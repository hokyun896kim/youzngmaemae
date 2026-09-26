# 유증 이벤트 매매 프로젝트
- 전체 배경·결론은 docs/brief.md 참고 (이미 결론 난 내용은 재논의 금지)
- 현재 단계: Phase 0 수집기 (DART 유증 감지 + 일정 파싱 + 인수권 시세 저장)
- 알림 메시지는 맨 앞에 [작업명 #순번] 소주제 헤더 필수
- "검증 필요" 표시 항목은 실제 API로 확인 후 사용

- 결정 로그: docs/decisions.md (brief 이후 확정 사항 — 실행은 GitHub Actions + Netlify 정적 웹)

## 코드 구조 (Phase 0)
- `yujeung/dart.py` — OpenDART (list / piicDecsn / estkRs / document). piicDecsn 은 corp_code 필수 → list.json 으로 먼저 감지
- `yujeung/detect.py` — 유상증자결정 감지 + 주주배정 필터 + 정정 공시를 케이스로 묶기
- `yujeung/schedule_parser.py` — 공시 원문에서 일정·발행가·할인율 추출 (정정마다 schedule_versions 에 버전 저장). 정정공시의 '정정전/정정후' 표는 본문 파싱에서 제외. 케이스 일정 = 최신 유상증자결정 원문 기준(`pipeline.latest_schedule`)
- `yujeung/krx.py`, `yujeung/prices.py` — KRX Open API 인수권(sr_bydd_trd)·본주 시세, 괴리율
- `yujeung/notify.py` — 알림 문구 생성·기록만 (발송 없음, 헤더 자동, 순번 = notifications.seq). 알림 역할은 사이트 '오늘 볼 것'
- `yujeung/verdict.py` — 관문1(채무상환·희석·최대주주·영업흑자·52주·총액인수)+관문2(괴리) → 🟢🟡🔵⚪. 관문1 자동 항목 미확인이 있으면 🟢?/🟡?(green_q/yellow_q) 확인 필요 — 진입·측정은 `verdict.base()` 로 원래 판정을 따르고 집계는 따로
- `yujeung/strategy.py` — [18] 전략 배지(🥇 비싼 인수권 팔기 · 🥈 상장일 매수 10거래일 · 🥉 적당히 싼 인수권+청약) + 금지 규칙(⛔). 조건 상수는 여기 한 곳, 근거 숫자는 data/backtest.json `strategies`(하드코딩 금지). 전략별 가상 성과 = strategy_trades. 전략 로직을 바꾸면 `STRATEGY_VERSION` 을 올린다 (🥈 는 판정 🟡/🟡? 일 때만 — B안)
- `yujeung/estimate.py` — 카드 '30초 결론' + 발행가 추정(할인율 d) + 단계별 본전선 + 어림 손익표 + 매물 소화일수
- `yujeung/paper.py` — 가상 성과: 인수권 마지막 날 판정 스냅샷(불변) + 상장 후 수익률·지수 초과
- `yujeung/backtest.py` — 과거 유증 백테스트(기출문제). 연도별 임시 DB, 미래 정보 금지(`dart.op_income_asof`), 결과 data/backtest/*.json + data/backtest.json. 설명·한계는 docs/backtest.md
- `yujeung/naver.py` — 네이버 일봉(본주·지수), `dart.latest_op_income` — 직전 분기 영업이익
- `yujeung/pipeline.py` — daily 흐름, `yujeung/export.py` — data/site.json, `index.html` — 화면
- `prompts.js` — GPT 분석지침(전체 브리핑) + 개별기업 분석 프롬프트. brief 확정 결론을 "전제"로, 수집기 맹점을 "검증 지침"으로 포함 — brief 와 어긋나게 고치지 말 것
- DB: 실행 시 `data/yujeung.sql`(커밋되는 텍스트 덤프) → SQLite 복원 → 갱신 → 다시 덤프. 바이너리는 커밋 금지
- 검증 상태는 docs/verification.md, 실측은 `python -m yujeung verify`
- 테스트: `python -m pytest -q` (네트워크 불필요). 테스트 픽스처는 합성 데이터
- 날짜는 항상 KST 기준 (`cli.today_kst`, `db.now()`) — Actions 러너는 UTC
- 파서 로직을 바꾸면 `schedule_parser.PARSER_VERSION` 을 올린다 (기존 공시 재파싱). 판정 로직을 바꾸면 `verdict.LOGIC_VERSION` 을 올린다 (과거 스냅샷은 불변)
- 진행 상황: docs/progress.md
