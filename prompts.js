// ===== GPT 분석지침 / 개별기업 분석 프롬프트 =====
// brief.md 의 확정 결론을 '전제'로 박아두고, 사이트 데이터(site.json)를 채워 넣는다.
// 수정할 땐 docs/brief.md 결론과 어긋나지 않게 할 것.

const P_NA = v => (v == null || v === '' ? '데이터없음' : v);
const P_N = v => (v == null ? '데이터없음' : Number(v).toLocaleString('ko-KR'));
const P_PCT = v => (v == null ? '데이터없음' : (v > 0 ? '+' : '') + Number(v).toFixed(1) + '%');
const P_REASON = x => String(x ?? '').replace(/괴리율|괴리/g, 'IV 프리미엄').replace(/(?:신주원가 할인율|원가할인)\s*([+-]?\d+(?:\.\d+)?)%/g, (_m, n) => {
  const v = -Number(n); return `총원가 쿠션율 ${v > 0 ? '+' : ''}${v.toFixed(1)}%`;
});

// 이미 결론 난 내용 — GPT 가 재논의하지 않도록 전제로 제시
const PREMISES = `[전제 — 이미 검증된 결론이다. 재논의하지 말고 이 위에서 분석해라]
1. 주주배정 유증의 "할인율 = 수익"은 틀렸다. 발행가 = 권리락 이론가 × (1 − 할인율)이라 권리락으로 이론상 제로섬이다.
   권리락 이론가 P_x = (P + r × I) / (1 + r)  (P: 권리락 전 주가, r: 배정비율, I: 발행가)
   ※ 사이트의 발행가·Px 추정은 r 로 증자비율(신주 ÷ 증자 전 발행주식총수)을 쓴다 — 자기주식 등으로 배정비율과 다를 수 있음
2. 인수권을 팔아 번 돈은 수익이 아니라 권리락으로 깎인 보유주 가치의 보상이다.
3. 초과청약은 배정주식수의 20% 한도이며, 실권주가 생겨야만 배정된다.
4. 진짜 수익원 후보는 네 가지다: (B) 유증 악재로 눌린 우량주의 회복, (수급) 인수권 기간 매도 압력·신주 상장일 매물 타이밍, (A) 인수권 할인 포착(인수권 가격 ≠ 본주 − 발행가), (레버리지) 권리락 전 보유자의 옵션성.
5. 전략 구조: B(눌린 우량주 줍기)가 본업이고 A(인수권 할인 포착)가 보너스다. B로 진입 → 인수권 거래기간에 괴리 체크 → 비싸면 인수권 매도(A), 아니면 청약해서 B 유지 → 신주 상장일 매물 구간에서 추가 기회를 찾는다.
6. 인수권 괴리가 방치되는 이유: 청약 대금이 없는 주주의 강제 투매(5거래일 안에 안 팔면 권리 소멸), 신주 상장 물량의 선반영, 유증 공시 후 공매도한 자의 해당 유증 참여 금지 → "인수권 매수 + 본주 공매도" 차익거래가 막혀 있다.
7. A 는 "인수권 괴리 차익"이 아니라 "인수권 할인 포착"이다. 본주를 동시에 공매도해 가격을 고정할 수 없으므로 무위험 차익거래가 아니다 — 인수권을 싸게 사도 청약 → 신주 상장까지 본주가 떨어지면 손실이 난다. 그래서 A 는 반드시 인수권 괴리 → 총원가 쿠션 → ATR 쿠션 → 신주 공급압력 순서로 본다. "−60% 괴리"가 실제로 몇 %의 경제적 안전마진이며, 그 안전마진이 상장일까지 버틸 만한지를 판단하는 것이 목적이다.
8. 전형적인 주가 사이클: 유증 전 상승 → 권리락 조정 → 기준일 후 청약 전까지 서서히 하락(인수권 매도 압력) → 청약 후 반등 → 신주 입고일 매물로 하락 → 약 1달 뒤 회복. 단, 이는 가설(H2·H3)이며 검증 중이다.`;

const FILTERS = `[회사 필터 5개 — 전부 충족해야 B(본업) 후보]
① 업계 1~3위  ② 절대 안 망할 회사(지금은 힘들어도 성장성)  ③ 대체 불가 사업  ④ 직전 분기 영업흑자 + 다음 분기 흑자 예상  ⑤ 주가가 52주 고저 범위의 중간 이하`;

// 형님 규칙 (09-28, 원문 그대로) — A 발행가 3층 분석
const FINAL_PRICE_RULE = `[A 전략 — 예상 최종발행가 3층 분석]

예상 최종발행가를 매일 계산해야 합니다.

기존에는:

현재 본주 - 1차 발행가

만 봤습니다.

이건 에코프로비엠처럼 1차·2차 중 낮은 가격을 최종 발행가로 쓰는 유증에서는 틀릴 수 있습니다.

따라서 A 분석을 앞으로 세 층으로 나눕니다.

① 1차가 기준

R/(P-I_1)-1

② 현재 시점 예상 최종가 기준

R/(P-\\hat I_{final})-1

③ 실제 확정가 기준

R/(P-I_{final})-1

그리고 ②를 만들기 위해 매일

* 산정기간 VWAP
* 기준일 종가
* 할인율
* 1차가
* 최저발행가 제한

을 업데이트해야 합니다.

이렇게 해야 “권리가 비싼 건지, 시장이 미래 발행가 인하를 먼저 반영한 건지” 구분할 수 있습니다.`;

// 형님 판단 규칙 (09-28, 원문 그대로 — 고칠 때는 형님 확인)
const DECISION_RULES = `[최우선 판단 규칙 — 실전 후보 선별]

이 분석의 최종 목적은 단순히 유상증자 사례를 분류하는 것이 아니라, 현재 시점에서 B·A·H1·H2·H3 가운데 어느 이벤트에 연구·매매 관찰 자원을 집중할지 가려내는 것이다.

스냅샷 데이터 기준일과 실제 분석 실행일이 다르면 두 날짜를 반드시 구분한다.

* 스냅샷 기준 분석: 제공된 데이터가 당시 무엇을 의미했는지 평가
* 현재 판단: DART·KRX 및 최신 시세를 다시 확인해 변경된 일정·발행가·인수권 가격·본주 가격을 반영
* 둘이 다르면 반드시 「스냅샷 이후 변경」으로 별도 표시한다.
* “오늘”, “현재”, “남은 거래일”, “앞으로 5거래일”은 실제 분석 실행일 KST 기준으로 계산한다.

[B 전략 추가 필터]

기존 B 필터 ①~⑤는 모두 충족해야 한다.

① 업계 상위권 사업자
② 재무·사업 지속 가능성이 높은 회사
③ 경쟁우위·진입장벽·고객 전환비용·인허가·규모경제 등 대체하기 어려운 사업 구조
④ 직전 분기 영업흑자 + 다음 분기 영업흑자 컨센서스
⑤ 현재 수정주가 기준 52주 위치가 50% 이하

52주 위치는 아래 값도 함께 출력한다.

52W Position = (현재가 - 52주 저가) ÷ (52주 고가 - 52주 저가)

추가로 B-⑥을 반드시 평가한다.

⑥ 실제로 유증 때문에 눌렸는가

유증 최초 공시 직전 종가부터 현재까지의 종목 수익률을 같은 기간 벤치마크와 가능하면 업종지수 수익률과 비교한다.

단순히 가격이 낮거나 좋은 회사라는 이유만으로 B 후보로 분류하지 않는다.

“우량기업 + 유증 이후 상대적 가격 훼손”이 동시에 확인되어야 진짜 B 후보로 본다.

공시 이전부터 하락 추세였다면 유증 효과와 기존 하락 추세를 구분한다.

[A 전략 — 인수권 괴리 분석 수정]

기존 괴리율

인수권 괴리율 = R ÷ (P - I) - 1

은 시장 미스프라이싱을 관찰하는 연구지표로 유지한다.

그러나 실제 A 전략의 핵심 판단값으로 사용하지 않는다.

반드시 아래를 추가 계산한다.

총 취득원가 = 인수권 가격 R + 발행가 I

총원가 할인율 = 1 - (R + I) ÷ P

원화 쿠션 = P - (R + I)

A 전략에서는 인수권 괴리율보다 총원가 할인율과 원화 쿠션을 우선 해석한다.

예정가·1차 발행가·2차 발행가·확정발행가를 절대 혼용하지 않는다.

확정발행가 전이라면 최소한 아래를 별도로 표시한다.

* 1차 발행가 기준 총원가
* 현재 주가를 이용한 예상 2차 발행가 시나리오
* 확정발행가 미정 여부

확정되지 않은 가격으로 계산한 괴리를 “확정 차익”처럼 표현하지 않는다.

[A 전략 — 변동성 안전마진]

A 후보마다 반드시 아래를 출력한다.

* 본주 현재가 P
* 인수권 가격 R
* 적용 발행가 I와 발행가 단계
* P-I
* 기존 인수권 괴리율
* R+I 총 취득원가
* 총원가 할인율
* P-(R+I) 원화 쿠션
* ATR(10)
* 원화 쿠션 ÷ ATR(10)
* 인수권 거래 종료일까지 잔여 거래일
* 청약일까지 잔여 거래일
* 신주 상장일까지 잔여 거래일

쿠션÷ATR의 합격 기준은 임의로 만들지 않는다. H1 데이터가 충분히 축적될 때까지 연속형 데이터로 기록한다.

[공급충격 지표]

유상증자의 희석률 하나만 보지 말고 다음 값도 가능하면 계산한다.

* 신주 수 ÷ 증자 전 발행주식수
* 신주 수 ÷ 추정 유통주식수
* 신주 시가총액 ÷ 최근 20일 평균 거래대금
* 신주 수 ÷ 최근 20일 평균 거래량
* 신주 상장일 실제 거래량 ÷ 신규상장주식수

이를 이용해 “희석”과 “실제 시장이 소화해야 하는 물량”을 구분한다.

[복합 Corporate Action 경고]

유상증자와 동시에 또는 가까운 시기에 다음 이벤트가 있으면 단순 인수권 괴리 공식만으로 평가하지 않는다.

* 무상증자
* 액면분할·병합
* 합병·분할
* 거래정지
* 대규모 CB/BW 전환
* 보호예수 해제
* 최대주주 변경
* 공개매수

존재할 경우 「복합 이벤트」로 별도 표시하고 권리 가치에 미치는 영향을 추가 검증한다.

[권리락 H3 계산]

가능하면 자체 계산한 Px보다 KRX가 제시한 권리락 기준가격을 우선 사용한다.

자체 계산할 경우 증자비율 r과 실제 구주주 1주당 배정비율이 다른지 확인하고, 자기주식 등 배정 제외 주식의 영향을 검증한다.

H3는 반드시

권리락 전 종가 대비 표면수익률

과

KRX 권리락 기준가 또는 검증된 Px 대비 실질수익률

을 분리한다.

[최종 출력 — 승부 후보]

전체 분석 마지막에는 반드시 아래 네 줄을 출력한다.

1. 지금 가장 집중해서 볼 B 후보
2. 지금 가장 집중해서 볼 A 후보
3. 데이터 수집용 H1·H2·H3 후보
4. 겉보기에는 매력적이지만 피해야 할 함정 후보

단순히 괴리율이 가장 큰 종목을 A 후보로 선정하지 않는다.

B 품질, 총원가 쿠션, ATR 대비 쿠션, 공급충격, 발행가 확정 여부, 이벤트까지의 잔여기간을 종합해서 설명한다.

확인할 수 없는 데이터는 임의 추정하지 말고 「미확인」으로 표시한다.

[시점 일관성 · 룩어헤드 금지]

A/H1 계산의 P·R·ATR·VWAP·예상 최종발행가는 반드시 같은 as-of 시점의 데이터로 묶는다.
같은 날짜라도 사이트 갱신시각이 KRX 정규장 종료(15:30 KST) 전이면 "종가"가 아니라 "장중 스냅샷"이다.

과거 인수권 거래일을 평가할 때는 그날까지 공개된 발행가와 공시만 사용한다.
나중에 확정된 발행가를 과거 P·R에 소급해 진입신호를 만들지 않는다.

반드시 두 값을 구분한다.
- A_decision: 당시 실제로 알 수 있었던 발행가·시세로 계산한 의사결정값
- A_realized: 나중에 확정된 발행가와 상장 이후 결과를 붙인 사후 성과값

A_realized는 H1 결과 평가에는 쓰되 A_decision의 진입조건에는 절대 사용하지 않는다.

[최대주주 청약]

"최대주주 전량 이상 청약"은 최초 배정권리를 기준으로 판정한다.
가능하면 아래 두 값을 분리한다.
- 최초 배정권리 대비 실제/예정 청약률
- 청약시점 보유권리 대비 청약률(초과청약 포함)

잔여 권리를 120% 초과청약했다는 이유만으로 최초 배정권리 전량 참여로 판정하지 않는다.`;

// A 3단계 + 발행가 단계 배지 (사이트 계산 규칙 — DECISION_RULES 의 A 해석을 R 유무로 단계화)
const A_STAGE_RULE = `[A 3단계 · 발행가 단계 — 사이트 자동 분류]
- A 사전감시: 인수권 상장 전이라 R(인수권 실측 시세)이 없다. 감시 목록일 뿐이며 "A 후보"라고 부르지 말고 랭킹에 넣지 마라. 쿠션이 ATR 1배 남는 R 상한만 감시 가격으로 적어라.
- A 가격관찰: R 실측 + 아직 매매 가능 + 적용 발행가 기준 R+I ≥ P (원화 쿠션 ≤ 0).
- A 조건충족: R 실측 + 아직 매매 가능 + 적용 발행가 기준 R+I < P (원화 쿠션 > 0). 쿠션÷ATR 은 합격선 없이 값만 해석한다.
- 인수권 매매종료일이 지난 케이스는 A 대상이 아니다.
- A 랭킹·"지금 가장 집중해서 볼 A 후보"는 조건충족 → 가격관찰 순으로만 고른다. 둘 다 없으면 "A 후보 없음"이라고 쓰고 사전감시 종목은 감시 목록으로만 적어라.
- 발행가는 항상 단계와 함께 쓴다: 예정(이사회 예정가 — 1차 미산정) / 1차(1차 발행가 산정) / 예상최종(권리락 후 min(1차, 2차 추정), 매일 변동) / 확정. 1차·예상최종 가격을 "발행가"라고만 쓰거나 확정가처럼 표현하지 마라.`;

const CHART_RULE = `[차트 사용 규칙] MACD·볼린저밴드는 쓰지 마라. 타이밍은 일목균형표·RSI 50 게이트·ATR 로만 본다. 60·120일선과 일목 기준선은 지수·대형주 판단용, 켈트너 채널(26/2/ATR10/EMA)은 변동성·손절용으로만 허용.`;

const BLINDSPOTS = `[검증 지침 — 이 수집기의 알려진 맹점. 숫자를 그대로 믿지 말고 원문으로 확인해라]
- 일정(기준일·인수권 상장기간·청약·납입·상장일)은 공시 원문을 자동 파싱한 값이며 파서가 아직 실제 공시로 검증되지 않았다 → DART 원문에서 반드시 대조.
- 권리락일은 "기준일 전 1영업일"로 추정한 값이다(휴장일 목록 기반).
- 발행가는 공시 시점별로 예정 → 1차 → 2차(확정)로 바뀐다. 확정발행가 산식(기산일·가중평균 구간, "1차와 2차 중 낮은 가격" 여부, 할인율)은 회사별 증권신고서 '모집 또는 매출에 관한 일반사항'에서 직접 확인해라.
- 공매도 참여 제한 규정의 현행 세부 조건은 미확인 상태다.
- 내재가치 대비 프리미엄(IV 프리미엄, 구 괴리율) = 인수권 종가 ÷ max(본주 종가 − 발행가, 0) − 1. 본주 − 발행가는 내재가치일 뿐이고 인수권에는 남은 기간의 시간가치·발행가 하향 기대가 들어 있으므로 +값을 '오가격·고평가'로 단정하지 마라. 본주 ≤ 발행가면 비율 없음(내재가치 0 — 시간가치·발행가 재조정 기대만 존재). 음수 = 내재가치보다 싸다.
- 시장 암시 발행가 I_implied = 본주 − 인수권. 예상 최종가 Î 와의 차이 ΔI = I_implied − Î: ≈0 이면 인수권 가격이 합리적, ΔI ≪ 0 이면 권리가 비싸거나 시장이 추가 발행가 인하를 기대, ΔI ≫ 0 이면 인수권 할인 가능성.
- 신주인수권 ‘상장폐지일’과 ‘매매종료일’을 반드시 구분하며, 마지막 실제 매매가능일은 KRX 및 발행회사 공시에서 검증한다. 증권사 화면의 종료일을 매매종료일로 간주하지 않는다.
  (사이트 값: 매매종료일 = 발행회사 공시의 인수권 상장(매매)기간 종료일, KRX 상장폐지일은 보통 그 다음 영업일 — 둘을 대조한 결과를 함께 표시한다.)`;

function caseStage(s, today = new Date()) {
  // 날짜 비교는 하루 단위 (오늘 = 해당일이면 그 구간에 포함)
  const t = k => (s[k] ? new Date(s[k] + 'T23:59:59+09:00') : null);
  const now = today;
  if (!s.record_date && !s.listing_date) return '인수권 일정 미정 (기준일부터 추후결정 — 정정공시 대기)';
  if (t('ex_rights_date') && now < new Date(s.ex_rights_date + 'T00:00:00+09:00')) return '① 공시 후 ~ 권리락 전 (권리 확보 구간)';
  if (!s.rights_start && s.ex_rights_date && !(s.subs_start && now >= new Date(s.subs_start + 'T00:00:00+09:00')))
    return '인수권 일정 미정 (추후결정 — 정정공시 대기)';
  if (t('rights_start') && now < new Date(s.rights_start + 'T00:00:00+09:00')) return '② 권리락 후 ~ 인수권 상장 전';
  if (t('rights_end') && now <= t('rights_end')) return '③ 인수권 거래 중 (A 할인 체크 구간)';
  if (t('subs_end') && now <= t('subs_end')) return '④ 인수권 종료 ~ 청약';
  const ld = s.listing_date ? new Date(s.listing_date + 'T00:00:00+09:00') : null;
  if (ld && now < ld) return '⑤ 청약·납입 후 ~ 신주 상장 전';
  if (ld) {
    const days = Math.floor((now - ld) / 864e5);
    return days <= 30 ? `⑥ 신주 상장 후 D+${days} (매물 소화 구간)` : `⑦ 신주 상장 후 D+${days} (사이클 종료)`;
  }
  return '일정 정보 부족';
}

function caseLinks(c) {
  const q = encodeURIComponent(c.corp_name || '');
  const code = c.stock_code || '';
  return [
    ['📄', 'DART 유상증자결정 원문', '1차', `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${c.first_rcept_no}`, '최초 공시'],
    ['🗂️', 'DART 공시 목록', '1차', `https://dart.fss.or.kr/dsab007/main.do?option=corp&textCrpNm=${q}`, '정정·증권신고서·분기보고서'],
    ['🏢', '네이버 금융(종목)', '1차', `https://finance.naver.com/item/main.naver?code=${code}`, '시세·재무·투자자별 매매'],
    ['📑', '네이버 공시·뉴스', '2차', `https://finance.naver.com/item/news_notice.naver?code=${code}`, '종목 공시/뉴스'],
    ['📊', 'FnGuide', '2차', `http://comp.fnguide.com/SVO2/ASP/SVD_Main.asp?pGB=1&gicode=A${code}`, '재무·주주 구성'],
    ['🔍', '뉴스 검색', '2차', `https://search.naver.com/search.naver?query=${q}%20유상증자`, '유증 관련 기사'],
  ];
}

function scheduleText(s) {
  return [
    ['권리락일(추정)', s.ex_rights_date], ['신주배정기준일', s.record_date],
    ['인수권 상장 시작', s.rights_start], ['인수권 상장 종료', s.rights_end], ['확정발행가 산정일', s.price_fix_date],
    ['청약', s.subs_start ? `${s.subs_start} ~ ${P_NA(s.subs_end)}` : null], ['납입일', s.payment_date],
    ['신주 상장일', s.listing_date],
  ].map(([k, v]) => `- ${k}: ${P_NA(v)}`).join('\n');
}

// ---- 🟢?/🟡? 확인 필요: 미확인 항목만 묻는 짧은 프롬프트 ----
const CHECK_Q = {
  major: '최대주주(특수관계인 포함)의 청약을 두 기준으로 분리해 확인해라: ① 최초 배정권리 대비 실제/예정 청약률 ② 청약시점 보유권리 대비 청약률(초과청약 포함). 잔여 권리 120% 초과청약만으로 최초 배정 전량 참여로 보지 마라.',
  uw: '인수 방식이 총액인수 / 잔액인수 / 모집주선 중 무엇인가? 대표주관회사와 실권주 처리 방식을 증권신고서 "인수인에 관한 사항"에서 확인해라.',
  op: '직전 분기(가장 최근 제출된 분기·반기보고서, 연결 우선) 영업이익은 흑자인가 적자인가? 금액과 보고서 기간을 적어라.',
  pos52: '현재 주가는 최근 52주 최저가~최고가 범위에서 몇 % 위치인가? (최저=0%, 최고=100%) 최저·최고·현재가와 날짜를 적어라.',
  dilution: '신주 발행 주식수 ÷ 기존 발행주식총수(희석률)는 몇 %인가? 두 숫자를 공시에서 인용해라.',
  debt: '자금 사용 목적 중 채무상환자금 비중은 몇 %인가?',
};
function buildCheckPrompt(c) {
  const v = c.verdict || {}, items = v.unconfirmed || [];
  const links = caseLinks(c).filter(l => l[2] === '1차').map(([, n, , u]) => `- ${n}: ${u}`).join('\n');
  return `${c.corp_name}(${P_NA(c.stock_code)}) 주주배정 유상증자 — 자동 판정 "${v.emoji || ''} ${v.name || ''}"의 미확인 항목만 확인해줘.

[확인할 항목 — 이것만 답해라]
${items.map((it, i) => `${i + 1}) ${it.label}: ${CHECK_Q[it.key] || it.label}`).join('\n')}

[1차 자료]
${links}

[답 형식]
항목마다 "확인됨: 통과 / 확인됨: 탈락 / 확인 불가" 중 하나 + 근거(공시명·날짜·문구) 한 줄.
마지막 줄: 모두 통과면 "${v.code === 'green_q' ? '🟢' : '🟡'} 확정", 하나라도 탈락이면 "⚪ 관찰 샘플", 확인 불가가 남으면 "확인 필요 유지".
(기준: 관문1 = 채무상환 < 50% · 희석 < 50% · 최대주주 최초 배정권리 전량 이상 청약 · 직전 분기 영업흑자 · 52주 위치 ≤ 50% · 총액/잔액인수)`;
}

// ---- 개별기업 분석 프롬프트 ----
function buildCasePrompt(c, siteData) {
  const s = c.schedule || {};
  const sm = c.summary || {};
  const purpose = Object.entries(sm.purpose_pct || {}).map(([k, v]) => `${k} ${v}%`).join(', ') || '데이터없음';
  const series = (c.rights_series || []).filter(p => p.gap != null);
  const gapLines = series.length
    ? series.slice(-10).map(p => `  ${p.d} ${p.name}: 인수권 ${P_N(p.rights)} / 본주 ${P_N(p.stock)} / 발행가 ${P_N(p.issue)} / 내재가치 ${P_N(p.fair)} / IV 프리미엄 ${P_PCT(p.gap)} / 시장 암시 발행가 ${P_N(p.i_implied)}`).join('\n')
    : '  (아직 인수권 시세 없음 — 인수권 상장 전이거나 수집 전)';
  const hist = (c.history || []).map(h => `  ${h.rcept_dt} ${h.report_nm}`).join('\n');
  const links = caseLinks(c).map(([, name, tier, url]) => `- ${name}(${tier}): ${url}`).join('\n');
  const stockLast = (c.stock_series || []).at(-1);

  return `너는 한국 주식 유상증자 이벤트 분석가다. 아래는 내 '유증 레이더'가 DART·KRX 에서 자동 수집한 ${c.corp_name}(${P_NA(c.stock_code)}) 유상증자 케이스다. 매수·매도를 단정하지 말고, 내가 판단할 재료를 깊고 균형 있게 정리해라.

${PREMISES}

${FILTERS}

${CHART_RULE}

${DECISION_RULES}

${FINAL_PRICE_RULE}
(개별기업 분석에서는 [최종 출력 — 승부 후보] 네 줄을 이 회사 기준으로 답해라 — 해당 없으면 "해당 없음".)

${snapshotText(siteData)}

[케이스 데이터 — 자동 수집]
- 회사: ${c.corp_name} (${P_NA(c.stock_code)}, ${P_NA(c.market)})
- 증자방식: ${P_NA(c.ic_mthn)} ${c.is_rights ? '(주주배정 계열 → 신주인수권증서 발생)' : '(주주배정 아님 → 인수권 없음, 관찰용)'}
- 최초 공시일: ${c.first_rcept_dt}
- 모집 규모: ${sm.total_amount ? Math.round(sm.total_amount / 1e8).toLocaleString() + '억원' : '데이터없음'}
- 신주 ÷ 기존 발행주식: ${sm.dilution_ratio != null ? (sm.dilution_ratio * 100).toFixed(0) + '%' : '데이터없음'}
- 1주당 배정비율: ${P_NA(s.alloc_ratio)}
- 자금 목적 비중: ${purpose}
- 발행가(최신 공시 기준): ${P_N(s.issue_price)}원${s.issue_kind ? ` [${s.issue_kind}${s.issue_kind === '예정' ? ' — 이사회 당시 예정발행가, 1차 아님' : ''}]` : ''}
- 현재 사이클 위치: ${caseStage(s)}
- 자동 판정: ${c.verdict ? `${c.verdict.emoji} ${c.verdict.name}${c.verdict.provisional ? '(잠정)' : ''} — ${P_REASON(c.verdict.reason)}` : '데이터없음'}
- 전략 배지(자동, 기출 백테스트 기반 행동 카드): ${strategyText(c, siteData)}
- 관문1 항목: ${c.gate1 ? c.gate1.criteria.map(x => `${x.label}=${{pass: '통과', fail: '탈락', unknown: '미확인', manual: 'GPT 확인 필요'}[x.status]}(${x.text})`).join(' / ') : '데이터없음'}${c.gate1 && c.gate1.reit_note ? `\n- 참고: ${c.gate1.reit_note}` : ''}
- 최근 본주 가격: ${stockLast ? `${stockLast.d} ${P_N(stockLast.close)}원 [${stockLast.price_type || '시점 미확인'}]` : '데이터없음'}

[사이트 자동 계산 — 30초 결론 · 어림 손익표 (검증 대상)]
${quickText(c.quick)}

[일정]
${scheduleText(s)}

[공시·정정 이력]
${hist || '  (없음)'}

[인수권 IV 프리미엄 추이 (최근 10거래일)]
${gapLines}

[A 인수권 할인 포착 — 사이트 자동 계산 (검증 대상): IV 프리미엄·시장 암시 발행가 → 총원가 쿠션(종가·체결가능) → ATR 쿠션 → 공급압력]
${aMarginText(c)}

${A_STAGE_RULE}

[B⑥ 유증으로 눌렸는가 — 3분할 (사이트 자동 계산, 검증 대상)]
${b6Text(c)}

[A_realized — 인수권 마지막 날 C_exec 로 샀다면 (사후값, H1 결과 평가용)]
${aRealizedText(c)}

${BLINDSPOTS}

[★ 반드시 교차확인할 1차 자료]
${links}
- 링크에 접근할 수 있으면 직접 읽고, 어려우면 한국어 웹검색으로 보강해라. 출처를 명시하고, 확인하지 못한 부분은 "미확인"으로 표기해라.

[출력 순서 — 반드시 이 순서로 맨 앞에]
1) 30초 결론: 결론 한 단어(🟢 매수 검토 / 🟡 상장일 대기 / 🟢?·🟡? 확인 필요 / 🔵 인수권 매도 / ⚪ 패스) + 이유 한 줄. 🟢?/🟡?는 관문1 자동 항목 중 미확인이 있다는 뜻 — 그 항목을 먼저 확인해 🟢/🟡 확정 또는 ⚪로 바꿔라. 가격 연구지표는 IV 프리미엄(구 괴리율 — 오가격 아님)과 함께 총원가 쿠션율 = 1 − (인수권+발행가)/본주를 사용한다. 기출상 총원가 쿠션이 20% 이상으로 지나치게 깊은 경우는 부실 신호였으므로 별도 위험필터로 본다. 가격은 KRX 정규장 종가 기준이며 장중이면 반드시 장중 스냅샷이라고 표시한다. '실권주 미발행'이고 잔액·총액인수가 없으면 인수방식 탈락
2) 어림 손익표: 본전선(현재 사이클 단계 기준: ① 권리락 전 본주+청약 = 권리락 이론가 Px / ③ 인수권 매수+청약 = 인수권 + 발행가 / ⑤ 상장 대기 본주 = 현재가)과 상장일 주가 시나리오 4개(본전선 대비 +15% / 0% / −15% / −30%)의 "상장일 주가 ○○원 → 수익률 ○%", 매물 소화일수(신주 수 ÷ 최근 20거래일 평균 거래량). 위 사이트 계산값을 원문으로 검증하고 틀리면 고쳐서 제시해라.
3) 다시 볼 조건 한 줄 (예: "3Q 영업흑자 전환 시", "IV 프리미엄 −20% 이하 시")
→ 그 다음에 아래 상세 분석을 써라. 30초 결론과 9번 결론이 다르면 이유를 밝혀라.
⚠ 발행가 구분: 공시 발행가가 '예정발행가'(이사회 당시)면 1차로 쓰지 말고 권리락 직전 종가로 1차를 다시 계산해라. '1차' 라벨이거나 1차 산정일(기준일 전 3거래일) 이후 공시값만 1차로 쓴다.
⚠ 발행가 추정: 1차 = 기준주가 × (1−할인율) ÷ (1 + 증자비율×할인율), 2차 = 청약 전 기준주가 × (1−할인율), 최종 = min(1차, 2차). 2차 발행가는 반드시 '권리락 후' 주가로 계산해라 — 권리락 전 주가를 넣으면 발행가가 부풀려진다. 확정발행가가 공시됐으면 추정 대신 확정값을 써라.

[분석 요청 — 깊게]
1. 자금 목적의 실체: 공시의 자금 목적 비중을 그대로 믿지 말고, 증권신고서 '자금의 사용목적' 세부 내역으로 성장 투자형인지 채무상환·연명형인지 판정해라. 채무상환이면 어떤 부채(만기·금리·사모사채 여부)인지 밝혀라.
2. 필터 판정: ①~⑤와 B-⑥(실제로 유증 때문에 눌렸는가 — 위 3분할: 공시 전 추세가 이미 하락이었는지 / 공시 충격이 컸는지 / 이후 악재가 지속됐는지로 판단)을 하나씩 통과/탈락/미확인으로 판정하고 근거를 대라(⑤는 공시일 기준 52주 고저 위치를 계산). 하나라도 탈락이면 B(본업) 후보가 아니다. 위 '자동 판정'에서 "GPT 확인 필요"·"미확인"인 항목(업계 순위, 대체 불가, 최대주주 청약 등)을 특히 채워라.
3. 발행조건: 1차·2차(확정) 발행가 산식과 할인율, 확정발행가가 1차보다 내려갈 수 있는 본주 가격 수준(이 케이스의 "부분적 보험" 구간)을 계산해라.
4. 최대주주·특수관계인 청약은 "최초 배정권리 대비 청약률"과 "청약시점 보유권리 대비 청약률(초과청약 포함)"을 분리해 확인하고, 실권주 처리 방식(일반공모 / 총액인수 / 모집주선 미발행)과 수급 영향을 판단해라.
5. A(인수권 할인 포착) 판정: 먼저 A 단계(사전감시/가격관찰/조건충족)를 확인하고 — 사전감시면 A 판정 대신 감시 가격만 제시 — IV 프리미엄은 연구지표로만 쓰고 시장 암시 발행가(P−R)와 예상 최종가의 차이 ΔI 로 '시장이 최종 발행가를 얼마로 보는가'를 먼저 해석하고, 총원가는 종가 기준과 체결가능 기준(C_exec)을 구분하고, 위 [A 인수권 할인 포착] 값(총원가 할인율·원화 쿠션·쿠션÷ATR(10)·잔여 거래일·공급충격)을 원문·최신 시세로 검증해 그 순서로 판단해라. 발행가 단계(1차·2차 시나리오·확정)를 섞지 말고, 괴리가 방치된 이유를 전제 6번 기준으로 설명해라.
6. 수급 사이클 위치: 현재 사이클 위치(${caseStage(s)})에서 다음 구간(권리락/인수권 매도/청약/신주 상장 매물)까지 예상되는 수급 압력과 크기(신주 물량 ÷ 일평균 거래량)를 추정해라.
7. 베어 케이스(steelman): 이 케이스에 들어가면 안 되는 가장 강력한 반대 논거를 일부러 세게 만들어라(추가 증자, 감사의견, 채무불이행, 정정신고서 요구, 최대주주 불참 등).
8. 반증 조건: 이 판단이 틀렸음을 보여줄 단 하나의 관찰값 또는 이벤트를 명시해라.
9. 결론: [B 본업 후보(청약·보유) / A만(인수권 매매) / 관찰(가설 검증 샘플) / 제외] 중 하나를 고르고, 이유 + 진입 전 체크리스트 + 다음에 확인할 일정 1~2개 + 확신도(상/중/하)를 제시해라.`;
}

// [18] 전략 배지 한 줄 (site.json strategy_rules 문구 그대로)
function strategyText(c, d) {
  const S = c.strategy, R = d && d.strategy_rules;
  if (!S || !R) return '데이터없음';
  if (S.ban) return S.ban.map(b => `⛔ ${R.bans[b].label} — ${R.bans[b].effect}`).join(' / ');
  const locked=(S.locks||[]).includes('unconfirmed_gate');
  if (!S.items.length) return locked?'실전 게이트 잠김 — 관문 미확인 항목 확인 필요':'해당 전략 없음';
  const st = {live: '지금 해당', wait: '대기', past: '기간 종료'};
  return S.items.map(it => {
    const D = R.strategies[it.key];
    let x = `${D.medal} ${D.title} [${st[it.state]}] (조건: ${D.cond})`;
    if (it.key === 's2') x += ` 청산일 ${P_NA(it.exit_on)} · 손절 ${P_N(it.stop)}원(${it.stop_basis || '-'}) · RSI ${it.rsi ?? '-'} · ${it.confirmed?'종가 확정':'장중/미리보기 — 종가 미확정'}`;
    return x;
  }).join(' / ') + (locked?' · 🔒 관문 미확인으로 전략2·3 실전 게이트 잠김':'') + (S.bans.length ? ` · 참고: ${S.bans.map(b => R.bans[b].label).join(', ')}` : '');
}

// A = 인수권 할인 포착 — 사이트 자동 계산값 (DECISION_RULES 의 출력 항목 순서)
function aMarginText(c) {
  const a = c.a_margin, s = c.supply;
  if (!a || !(a.rows || []).length) return '  (인수권 없음 또는 본주 시세 없음)';
  const out = [
    `- A_decision 기준시점: ${P_NA(a.decision_asof || a.p_date)} / 본주 P: ${P_N(a.p)}원 (${P_NA(a.p_date)} ${P_NA(a.price_type || '시점 미확인')}) / 인수권 R: ${a.r == null ? '미확인(아직 인수권 시세 없음)' : `${P_N(a.r)}원 (${a.r_date})`}`,
    `- ATR(${a.atr_n}): ${a.atr == null ? '미확인' : `${P_N(a.atr)}원 (${a.atr_pct}%)`} · 확정발행가: ${a.confirmed ? '확정' : '미정'} · 적용 발행가 단계: ${a.issue_stage ? a.issue_stage.label : '미확인'}`,
    `- A 단계: ${a.stage ? `${a.stage.label} — ${a.stage.why}` : '해당 없음(인수권 매매 종료 또는 일정 미확인)'}`,
    ...a.rows.map(r => r.issue == null ? `- [${r.label}] ${r.note || '데이터없음'}` : `- [${r.label}] I ${P_N(r.issue)} / P-I ${P_N(r.p_minus_i)} / IV 프리미엄 ${P_PCT(r.gap)} / R+I ${P_N(r.cost)} / 총원가 할인율 ${r.cost_disc == null ? '데이터없음' : r.cost_disc.toFixed(1) + '%'} / 원화 쿠션 ${P_N(r.cushion)} / 쿠션÷ATR ${r.cushion_atr ?? '데이터없음'}${a.r == null && r.r_for_1atr ? ` / 쿠션이 ATR 1배 남는 R 상한 ${P_N(r.r_for_1atr)}` : ''}${r.note ? ` (${r.note})` : ''}`),
    `- 잔여 거래일(오늘 포함, 사이트 갱신일 기준): ${a.days.map(d => `${d.label} ${d.left == null ? '지남/미정' : d.left + '일'}(${P_NA(d.date)})`).join(' · ')}`,
  ];
  const im = a.implied;
  if (im) out.push(`- 시장 암시 발행가 I_implied = P − R = ${P_N(im.i_implied)} vs 적용 발행가[${im.row_kind}] ${P_N(im.i_hat)} → ΔI ${im.d_i > 0 ? '+' : ''}${P_N(im.d_i)}원 (${P_PCT(im.d_i_pct)}) — ΔI<0: 권리가 비싸거나 추가 발행가 인하 기대 / ΔI>0: 인수권 할인 가능성`);
  const ex = a.exec;
  if (ex) out.push(`- 체결가능 기준 A_exec: R_exec ${P_N(ex.r_exec)}(${ex.r_basis} · 종가 ${P_N(ex.r_close)} · VWAP ${P_N(ex.r_vwap)} · 거래량 ${P_N(ex.r_volume)} · 일중범위 ${ex.r_range_pct ?? '데이터없음'}%) + I ${P_N(ex.issue)} + 수수료 ${P_N(ex.fee)} + 금융비용 ${P_N(ex.carry)} + 매도비용 ${P_N(ex.sell_cost)} = C_exec ${P_N(ex.cost)} / 체결가능 총원가 할인율 ${ex.cost_disc}% / 쿠션 ${P_N(ex.cushion)} / 쿠션÷ATR ${ex.cushion_atr ?? '데이터없음'} — ${ex.assumptions} · ${ex.missing}`);
  const xp = a.exposure;
  if (xp) out.push(`- 노출기간: 매수일→신주 상장 ${xp.t_listing}거래일 · 기간보정 쿠션 (쿠션÷ATR)/√T = ${xp.time_adj_cushion ?? '데이터없음'} (H1 연구변수 — 매수 기준 아님)`);
  const fb = a.funding;
  if (fb) out.push(`- 청약자금 부담률 = q × I / P_pre = ${Number(fb.q).toFixed(4)} × ${P_N(fb.issue)} / ${P_N(fb.p_pre)}(${fb.basis}) = ${fb.pct}% (높을수록 강제 투매 압력 가설)`);
  if (a.gap_shift != null) out.push(`- ① → ② IV 프리미엄 차이: ${a.gap_shift > 0 ? '+' : ''}${a.gap_shift}%p`);
  const f = a.final;
  if (f && f.i2 == null) out.push('- 예상 최종가(②): 권리락 전 — 2차 발행가 미산정이라 ② = 1차가. 권리락 후부터 매일 갱신');
  else if (f) out.push(`- 예상 최종가(②) 입력: 1차가 ${P_N(f.i1)} / 2차 추정 ${P_N(f.i2)} = min(산정기간 1주 VWAP ${P_N(f.vwap)}, ${f.projected ? '최근' : '기준일'} 종가 ${P_N(f.close_base)}${f.base_date ? ` [${f.base_date}]` : ''}) × (1 − 할인율 ${f.d != null ? Math.round(f.d * 100) + '%' : '미확인'}) / 산정기간 ${(f.window || []).join(', ') || '데이터없음'} / VWAP 출처 ${P_NA(f.vwap_src)} / 최저발행가 제한 미확인(증권신고서 확인) / 확정발행가 산정일 ${P_NA(f.fix_date)}${f.projected ? ' — 산정일 전이라 오늘을 기준일로 본 예상' : ''} / 규칙 ${f.rule}`);
  const hs = (c.rights_series || []).filter(x => x.gap != null).slice(-10);
  if (hs.length) out.push(`- 일별 ①·② IV 프리미엄 · 시장 암시 발행가 추이: ${hs.map(x => `${x.d.slice(5)} ①${P_PCT(x.gap)}${x.gap_hat != null ? ` ②${P_PCT(x.gap_hat)}(Î ${P_N(x.i_hat)})` : ''}`).join(' · ')}`);
  const e = a.end_check;
  if (e) out.push(`- 인수권 마지막 매매일 검증: 공시 매매종료일 ${P_NA(e.disclosed)} / KRX 상장폐지일 ${P_NA(e.delist)} → 그 전 영업일 ${P_NA(e.krx_last)} — ${e.text}`);
  if (s) out.push(`- 공급충격: 신주 ÷ 증자 전 주식 ${s.dilution == null ? '데이터없음' : s.dilution + '%'} / 신주 ÷ 유통주식 미확인 / 신주 시가총액 ÷ 상장 전 최근 ${s.n}일 평균 거래대금 ${s.value_days ?? '데이터없음'}일 / 신주 ÷ 상장 전 최근 ${s.n}일 평균 거래량 ${s.volume_days ?? '데이터없음'}일 · 중앙값 거래량 기준 ${s.volume_days_median ?? '데이터없음'}일 / 실효 공급(보호예수 차감) ${s.effective_note || '미확인'} / D0 신주대비 거래회전율(소화율 아님) ${s.listing_turnover == null ? '상장 전 또는 데이터없음' : (s.listing_turnover*100).toFixed(1)+'%'} / D0 초과회전율 (거래량−ADV20)/신주 ${s.excess_turnover_d0 == null ? '데이터없음' : (s.excess_turnover_d0*100).toFixed(1)+'%'} / D0~D5 누적 초과회전율 ${s.excess_turnover_d0_d5 == null ? '데이터없음(D+5 전)' : (s.excess_turnover_d0_d5*100).toFixed(1)+'%'}${s.listing_price_type?' ['+s.listing_price_type+']':''}${s.listing_volume_multiple!=null?' / D0 거래량 = 평소 '+s.listing_volume_multiple+'배':''}${s.listing_vwap?' / D0 VWAP '+P_N(s.listing_vwap):''}${s.listing_close_vs_vwap!=null?' / 종가-VWAP '+P_PCT(s.listing_close_vs_vwap):''}`);
  return out.join('\n');
}

// B⑥ 3분할 (사이트 자동 계산 — 판단 보조, 자동 관문 아님)
function b6Text(c) {
  const b = c.b6; if (!b) return '  (데이터없음 — 지수·본주 일봉 부족)';
  const f = (x, lab) => x ? `${lab} ${x.from}~${x.to}: 종목 ${P_PCT(x.stock)} − ${b.index_name} ${P_PCT(x.index)} = 초과 ${P_PCT(x.ar)}` : `${lab}: 데이터없음`;
  return [`- t0(공시 후 첫 거래일) ${b.t0}${b.ex_adjusted ? ' · 권리락 이론가 비율 보정' : ''}`,
    `- ${f(b.pretrend, 'B⑥-a 공시 전 추세 AR[-20,-1]')}${b.pretrend_full ? '' : ' (20거래일 미만)'}`,
    `- ${f(b.shock, 'B⑥-b 공시 충격 AR[0,+1]')} / ${f(b.shock3, 'CAR[0,+3]')}`,
    `- ${f(b.persistence, 'B⑥-c 악재 지속 AR[+2,오늘]')}`,
    `- 자동 해석: ${b.read || '데이터없음'} (${b.note})`].join('\n');
}

// A_realized — 사후 결과값, 진입조건에 쓰지 말 것
function aRealizedText(c) {
  const r = c.a_realized; if (!r) return '  (신주 상장 전 또는 인수권 시세 없음)';
  return `- C_exec ${P_N(r.cost)} (${r.buy_date} 인수권 마지막 시세 · ${r.issue_basis} ${P_N(r.issue)}) → ${r.points.map(p => `${p.label} ${p.ret == null ? '대기' : P_PCT(p.ret)}`).join(' · ')} / MAE ${P_PCT(r.mae)} · MFE ${P_PCT(r.mfe)} (종가, ~${r.path_end}) — ${r.note}`;
}

// 스냅샷 기준일 vs 분석 실행일 구분 (DECISION_RULES)
function snapshotText(d) {
  const now = new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 16).replace('T', ' ');
  const gen=P_NA(d && (d.generated_at || '').slice(0, 16).replace('T', ' '));
  const gd=(d&&d.generated_at||'').slice(0,10), gt=(d&&d.generated_at||'').slice(11,16);
  const rightsType=d&&d.last_rights_date?(d.last_rights_date<gd||(d.last_rights_date===gd&&gt>='15:30')?'종가':'장중 스냅샷'):'시점 미확인';
  return `[날짜] 인수권 시세 기준일 ${P_NA(d && d.last_rights_date)} [${rightsType}] · 사이트 갱신 ${gen} KST · 이 프롬프트 복사 ${now} KST`;
}

function quickText(q) {
  if (!q) return '  (없음)';
  const be = q.breakeven, is = q.issue || {}, o = q.overhang;
  const lines = [
    `- 30초 결론(자동): ${q.word} — ${P_REASON(q.reason)}`,
    `- 다시 볼 조건(자동): ${q.recheck}`,
    `- 사이클 단계: ${q.stage_name}`,
    `- 발행가 [${is.stage ? is.stage.label : '예정'}]: ${is.text || '데이터없음'}${is.d ? ` (할인율 ${(is.d * 100).toFixed(0)}%, 증자비율 ${(is.r * 100).toFixed(1)}%)` : ' (할인율 미확인 — 증권신고서에서 확인해라)'}`,
    `- 본전선: ${be ? `${P_N(be.value)}원 — ${be.how} (${be.text})` : (q.stage === 'listed' ? '상장 완료' : '계산 불가')}`,
    ...(q.table || []).map(t => `  · ${t.name} ${t.pct > 0 ? '+' : ''}${t.pct}%: 상장일 주가 ${P_N(t.price)}원 → 수익률 ${t.pct > 0 ? '+' : ''}${t.pct}%`),
    `- 매물 소화: ${o ? `상장 전 평소 거래량 ${o.days}일치 (신주 ${P_N(o.new_shares)}주 ÷ D-20~D-1 평균 ${P_N(o.avg_volume)}주)${o.red ? ' ⚠ 60일 이상' : ''}` : '데이터없음'}`,
  ];
  if ((q.table || []).length) lines.push(`- ${q.table_note}`);
  return lines.join('\n');
}

// ---- GPT 분석지침: 전체 브리핑 ----
function buildBriefingPrompt(d) {
  const open = (d.cases || []).filter(c => c.status === 'open' && c.is_rights);
  const caseLines = open.length ? open.map(c => {
    const s = c.schedule || {}, sm = c.summary || {};
    const last = (c.rights_series || []).filter(p => p.gap != null).at(-1);
    const purpose = Object.entries(sm.purpose_pct || {}).map(([k, v]) => `${k}${v}%`).join('/') || '-';
    return `- ${c.verdict ? c.verdict.emoji + ' ' : ''}${c.corp_name}(${P_NA(c.stock_code)}) | ${P_NA(c.ic_mthn)} | 자금목적 ${purpose} | 희석 ${sm.dilution_ratio != null ? (sm.dilution_ratio * 100).toFixed(0) + '%' : '-'} | 공시 발행가 ${P_N(s.issue_price)}[${s.issue_kind === '확정' || s.issue_kind === '1차' ? s.issue_kind : '예정'}] | ${caseStage(s)} | 권리락 ${P_NA(s.ex_rights_date)} · 인수권 ${P_NA(s.rights_start)}~${P_NA(s.rights_end)} · 상장 ${P_NA(s.listing_date)}${last ? ` | IV 프리미엄 ${P_PCT(last.gap)}(${last.d})` : ''}${c.b6 ? ` | B⑥ 전추세 ${P_PCT((c.b6.pretrend || {}).ar)} · 충격 ${P_PCT((c.b6.shock || {}).ar)} · 지속 ${P_PCT((c.b6.persistence || {}).ar)}` : ''}${c.a_margin && c.a_margin.stage ? ` | ${c.a_margin.stage.label}` : ''}`;
  }).join('\n') : '- (진행 중인 주주배정 케이스 없음)';
  const rights = (d.rights_today || []).length ? d.rights_today.map(r =>
    `- ${r.name}: 인수권 ${P_N(r.close)} / 본주 ${P_N(r.stock)} / 발행가 ${P_N(r.issue)} / 내재가치 ${P_N(r.fair)} / IV 프리미엄 ${P_PCT(r.gap)} / 시장 암시 발행가 ${r.stock && r.close ? P_N(r.stock - r.close) : "데이터없음"} / 인수권+청약 원가 ${P_N(r.cost)} / 거래량 ${P_N(r.volume)} / KRX 상장폐지일 ${P_NA(r.delist)} → 마지막 매매일 ${P_NA(r.last_trade)}(상장폐지일 전 영업일 — 공시와 대조)`
  ).join('\n') : '- (해당일 상장된 인수권 없음)';

  const aBy = k => open.filter(c => c.a_margin && c.a_margin.stage && c.a_margin.stage.code === k);
  const aGroup = (k, title) => { const xs = aBy(k); return `■ ${title} ${xs.length}건\n` + (xs.length ? xs.map(c => `▶ ${c.corp_name}\n${aMarginText(c)}`).join('\n') : '- (없음)'); };
  const aPre = aBy('prewatch');
  const aLines = [aGroup('met', 'A 조건충족 (랭킹 1순위 풀)'), aGroup('price', 'A 가격관찰 (랭킹 2순위 풀)'),
    `■ A 사전감시 ${aPre.length}건 — R 없음, 후보·랭킹 금지 (감시 가격만)\n` + (aPre.length ? aPre.map(c => {
      const a = c.a_margin, r = (a.rows || []).find(x => x.kind === a.stage.row_kind);
      return `- ${c.corp_name}: ${a.stage.why} · 적용 발행가 [${a.issue_stage ? a.issue_stage.label : '예정'}] ${P_N(r && r.issue)} · 인수권 상장 ${P_NA((c.schedule || {}).rights_start)}`;
    }).join('\n') : '- (없음)')].join('\n\n');

  return `너는 한국 주식 유상증자 이벤트 매매 전략의 리서치 파트너다. 아래는 내 '유증 레이더'(DART + KRX 자동 수집)의 ${P_NA(d.last_rights_date)} 기준 스냅샷이다. 전체를 훑고 오늘 내가 집중할 곳을 골라줘라.

${PREMISES}

${FILTERS}

${CHART_RULE}

${DECISION_RULES}

${FINAL_PRICE_RULE}

${snapshotText(d)}

[진행 중인 주주배정 유증 케이스]
${caseLines}

${A_STAGE_RULE}

[A 인수권 할인 포착 — A 3단계별 케이스 (사이트 자동 계산, 검증 대상)]
${aLines}

[오늘 상장된 신주인수권증서 전체 (${P_NA(d.last_rights_date)} · ${(()=>{const gd=(d.generated_at||'').slice(0,10),gt=(d.generated_at||'').slice(11,16);return d.last_rights_date<gd||(d.last_rights_date===gd&&gt>='15:30')?'종가':'장중 스냅샷';})()})]
${rights}

${BLINDSPOTS}

[검증 중인 가설 — 판단할 때 이 틀로 정리해라]
- H1 인수권 할인: IV 프리미엄·총원가 쿠션(체결가능 기준)이 X 일 때 "인수권 매수 + 청약"의 기대수익
- H2 상장일 매물 반등: 신주 상장일 급락 후 D+3~D+10 반등 여부
- H3 권리락 착시 급등: 권리락 첫날~D+3 단기 급등 반복 여부

[브리핑 요청]
1. 오늘의 우선순위: 위 케이스를 [B 본업 후보 / A 기회(인수권 할인 포착) / 관찰 샘플 / 제외]로 분류하고, 각각 한 줄 이유를 대라. 필터 5개로 걸러지는 종목은 명확히 탈락시켜라.
2. 인수권 할인 포착 랭킹: A 조건충족 → A 가격관찰 풀에서만 고른다(사전감시는 R이 없으니 제외 — 풀이 비면 "A 후보 없음"). IV 프리미엄 순이 아니라 시장 암시 발행가 ΔI · 체결가능 총원가 쿠션율·원화 쿠션÷ATR(10)·상장까지 노출기간·공급충격(평균·중앙값)·청약자금 부담률·발행가 확정 여부·잔여 거래일로 최대 3개를 골라, 각 항목 값과 괴리가 방치된 이유(강제 투매·상장 물량 선반영·공매도 차익 차단)를 함께 정리해라.
3. 이번 주 캘린더: 앞으로 5거래일 안에 권리락·인수권 시작/종료·청약·신주 상장이 있는 케이스를 날짜순으로 나열하고, 각 이벤트에서 확인할 것 1개씩 적어라.
4. 가설 샘플: H1·H2·H3 검증 샘플로 기록할 가치가 있는 케이스와, 기록할 때 추가로 수집해야 할 데이터를 제시해라.
5. 경고: 채무상환형·초대형 희석·정정신고서 요구·복합 Corporate Action 등 위험 신호가 있는 케이스를 짚어라.
6. 마지막에 [최종 출력 — 승부 후보] 네 줄을 반드시 출력해라.
각 케이스를 깊게 파야 하면 "개별기업 분석 프롬프트"로 따로 물어보라고 안내해라. 매수·매도는 단정하지 말고, 확인하지 못한 부분은 "미확인"으로 표기해라.`;
}

function copyText(txt, btn, previewEl, label) {
  if (previewEl) { previewEl.textContent = txt; previewEl.classList.add('show'); }
  const done = () => {
    btn.textContent = '✅ 복사됨! GPT·Claude에 붙여넣으세요'; btn.classList.add('done');
    setTimeout(() => { btn.textContent = label; btn.classList.remove('done'); }, 2500);
  };
  const fallback = () => {
    const ta = document.createElement('textarea'); ta.value = txt; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select(); try { document.execCommand('copy'); } catch (e) { } document.body.removeChild(ta);
  };
  if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(txt).then(done).catch(() => { fallback(); done(); });
  else { fallback(); done(); }
}

if (typeof module !== 'undefined') module.exports = { buildCasePrompt, buildBriefingPrompt, caseStage, caseLinks };
