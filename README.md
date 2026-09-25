# 유증 레이더 (Phase 0 수집기)

주주배정 유상증자를 DART에서 감지하고, 일정을 추적하고, KRX 신주인수권증서 일별 시세로 **인수권 괴리율**을 매일 기록하는 정적 웹.
배경·결론은 [`docs/brief.md`](docs/brief.md), 이후 결정은 [`docs/decisions.md`](docs/decisions.md), 검증 상태는 [`docs/verification.md`](docs/verification.md).

## 구조 (KR헤게모니와 동일)
```
GitHub Actions (평일 08:40 / 18:40 KST)
  └ python -m yujeung daily
      DART list.json → 유상증자결정 감지 → piicDecsn 상세 → 원문(document.xml) 일정 파싱 → estkRs 보강
      KRX sr_bydd_trd(인수권 전체) + stk/ksq_bydd_trd(추적 본주) → 괴리율
      텔레그램 알림 ([유증수집 #순번] 소주제)
      → data/site.json + data/yujeung.sql 커밋
Netlify (레포 연결, 빌드 없음) → index.html 이 data/site.json 을 읽어 표시
```

## 준비 (한 번)
1. 레포 **Settings → Secrets and variables → Actions**: `DART_API_KEY`, `KRX_API_KEY` (선택: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`)
2. KRX Open API(openapi.krx.co.kr)에서 **신주인수권증서 일별매매정보 / 유가증권 일별매매정보 / 코스닥 일별매매정보** 이용신청
3. Actions → **유증 수집기 → Run workflow → command = `verify`** 로 실제 API 응답 확인
4. Netlify → Add new project → 이 레포 연결 (Base directory 비움, 빌드 명령 없음)

## 로컬
```bash
pip install -r requirements.txt
cp .env.example .env            # 키 입력
python -m yujeung verify        # 실제 API 점검
python -m yujeung daily         # 하루치 수집
python -m http.server 8899      # http://localhost:8899
python -m pytest -q             # 오프라인 테스트
```

## 명령
| 명령 | 설명 |
|---|---|
| `daily [--today YYYYMMDD]` | 감지 → 일정 → 시세 → 알림 → site.json/덤프 |
| `backfill-rights --start 20100212 --end 20101231` | KRX 인수권 과거 시세 적재 (연 단위로 끊어서) |
| `import-rights file.csv` | HTS에서 옮긴 인수권 종가 (`date,isu_nm,close,stock_code,stock_close,issue_price`) |
| `export` | site.json 재생성 |
| `verify` | 실제 API 필드 점검 |
