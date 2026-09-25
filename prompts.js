// ===== GPT 분석지침 / 개별기업 분석 프롬프트 =====
// brief.md 의 확정 결론을 '전제'로 박아두고, 사이트 데이터(site.json)를 채워 넣는다.
// 수정할 땐 docs/brief.md 결론과 어긋나지 않게 할 것.

const P_NA = v => (v == null || v === '' ? '데이터없음' : v);
const P_N = v => (v == null ? '데이터없음' : Number(v).toLocaleString('ko-KR'));
const P_PCT = v => (v == null ? '데이터없음' : (v > 0 ? '+' : '') + Number(v).toFixed(1) + '%');

// 이미 결론 난 내용 — GPT 가 재논의하지 않도록 전제로 제시
const PREMISES = `[전제 — 이미 검증된 결론이다. 재논의하지 말고 이 위에서 분석해라]
1. 주주배정 유증의 "할인율 = 수익"은 틀렸다. 발행가 = 권리락 이론가 × (1 − 할인율)이라 권리락으로 이론상 제로섬이다.
   권리락 이론가 P_x = (P + r × I) / (1 + r)  (P: 권리락 전 주가, r: 배정비율, I: 발행가)
2. 인수권을 팔아 번 돈은 수익이 아니라 권리락으로 깎인 보유주 가치의 보상이다.
3. 초과청약은 배정주식수의 20% 한도이며, 실권주가 생겨야만 배정된다.
4. 진짜 수익원 후보는 네 가지다: (B) 유증 악재로 눌린 우량주의 회복, (수급) 인수권 기간 매도 압력·신주 상장일 매물 타이밍, (A) 인수권 괴리(인수권 가격 ≠ 본주 − 발행가), (레버리지) 권리락 전 보유자의 옵션성.
5. 전략 구조: B(눌린 우량주 줍기)가 본업이고 A(인수권 괴리 차익)가 보너스다. B로 진입 → 인수권 거래기간에 괴리 체크 → 비싸면 인수권 매도(A), 아니면 청약해서 B 유지 → 신주 상장일 매물 구간에서 추가 기회를 찾는다.
6. 인수권 괴리가 방치되는 이유: 청약 대금이 없는 주주의 강제 투매(5거래일 안에 안 팔면 권리 소멸), 신주 상장 물량의 선반영, 유증 공시 후 공매도한 자의 해당 유증 참여 금지 → "인수권 매수 + 본주 공매도" 차익거래가 막혀 있다.
7. 전형적인 주가 사이클: 유증 전 상승 → 권리락 조정 → 기준일 후 청약 전까지 서서히 하락(인수권 매도 압력) → 청약 후 반등 → 신주 입고일 매물로 하락 → 약 1달 뒤 회복. 단, 이는 가설(H2·H3)이며 검증 중이다.`;

const FILTERS = `[회사 필터 5개 — 전부 충족해야 B(본업) 후보]
① 업계 1~3위  ② 절대 안 망할 회사(지금은 힘들어도 성장성)  ③ 대체 불가 사업  ④ 직전 분기 영업흑자 + 다음 분기 흑자 예상  ⑤ 주가가 52주 고저 범위의 중간 이하`;

const CHART_RULE = `[차트 사용 규칙] MACD·볼린저밴드는 쓰지 마라. 타이밍은 일목균형표·RSI 50 게이트·ATR 로만 본다. 60·120일선과 일목 기준선은 지수·대형주 판단용, 켈트너 채널(26/2/ATR10/EMA)은 변동성·손절용으로만 허용.`;

const BLINDSPOTS = `[검증 지침 — 이 수집기의 알려진 맹점. 숫자를 그대로 믿지 말고 원문으로 확인해라]
- 일정(기준일·인수권 상장기간·청약·납입·상장일)은 공시 원문을 자동 파싱한 값이며 파서가 아직 실제 공시로 검증되지 않았다 → DART 원문에서 반드시 대조.
- 권리락일은 "기준일 전 1영업일"로 추정한 값이다(휴장일 목록 기반).
- 발행가는 공시 시점별로 예정 → 1차 → 2차(확정)로 바뀐다. 확정발행가 산식(기산일·가중평균 구간, "1차와 2차 중 낮은 가격" 여부, 할인율)은 회사별 증권신고서 '모집 또는 매출에 관한 일반사항'에서 직접 확인해라.
- 공매도 참여 제한 규정의 현행 세부 조건은 미확인 상태다.
- 괴리율 = 인수권 종가 ÷ (본주 종가 − 발행가) − 1. 음수 = 인수권이 이론가보다 싸다.`;

function caseStage(s, today = new Date()) {
  // 날짜 비교는 하루 단위 (오늘 = 해당일이면 그 구간에 포함)
  const t = k => (s[k] ? new Date(s[k] + 'T23:59:59+09:00') : null);
  const now = today;
  if (t('ex_rights_date') && now < new Date(s.ex_rights_date + 'T00:00:00+09:00')) return '① 공시 후 ~ 권리락 전 (권리 확보 구간)';
  if (t('rights_start') && now < new Date(s.rights_start + 'T00:00:00+09:00')) return '② 권리락 후 ~ 인수권 상장 전';
  if (t('rights_end') && now <= t('rights_end')) return '③ 인수권 거래 중 (A 괴리 체크 구간)';
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

// ---- 개별기업 분석 프롬프트 ----
function buildCasePrompt(c, siteData) {
  const s = c.schedule || {};
  const sm = c.summary || {};
  const purpose = Object.entries(sm.purpose_pct || {}).map(([k, v]) => `${k} ${v}%`).join(', ') || '데이터없음';
  const series = (c.rights_series || []).filter(p => p.gap != null);
  const gapLines = series.length
    ? series.slice(-10).map(p => `  ${p.d} ${p.name}: 인수권 ${P_N(p.rights)} / 본주 ${P_N(p.stock)} / 발행가 ${P_N(p.issue)} / 이론가 ${P_N(p.fair)} / 괴리율 ${P_PCT(p.gap)}`).join('\n')
    : '  (아직 인수권 시세 없음 — 인수권 상장 전이거나 수집 전)';
  const hist = (c.history || []).map(h => `  ${h.rcept_dt} ${h.report_nm}`).join('\n');
  const links = caseLinks(c).map(([, name, tier, url]) => `- ${name}(${tier}): ${url}`).join('\n');
  const stockLast = (c.stock_series || []).at(-1);

  return `너는 한국 주식 유상증자 이벤트 분석가다. 아래는 내 '유증 레이더'가 DART·KRX 에서 자동 수집한 ${c.corp_name}(${P_NA(c.stock_code)}) 유상증자 케이스다. 매수·매도를 단정하지 말고, 내가 판단할 재료를 깊고 균형 있게 정리해라.

${PREMISES}

${FILTERS}

${CHART_RULE}

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
- 자동 판정: ${c.verdict ? `${c.verdict.emoji} ${c.verdict.name}${c.verdict.provisional ? '(잠정)' : ''} — ${c.verdict.reason}` : '데이터없음'}
- 관문1 항목: ${c.gate1 ? c.gate1.criteria.map(x => `${x.label}=${{pass: '통과', fail: '탈락', unknown: '미확인', manual: 'GPT 확인 필요'}[x.status]}(${x.text})`).join(' / ') : '데이터없음'}${c.gate1 && c.gate1.reit_note ? `\n- 참고: ${c.gate1.reit_note}` : ''}
- 최근 본주 종가: ${stockLast ? `${stockLast.d} ${P_N(stockLast.close)}원` : '데이터없음'}

[사이트 자동 계산 — 30초 결론 · 어림 손익표 (검증 대상)]
${quickText(c.quick)}

[일정]
${scheduleText(s)}

[공시·정정 이력]
${hist || '  (없음)'}

[인수권 괴리율 추이 (최근 10거래일)]
${gapLines}

${BLINDSPOTS}

[★ 반드시 교차확인할 1차 자료]
${links}
- 링크에 접근할 수 있으면 직접 읽고, 어려우면 한국어 웹검색으로 보강해라. 출처를 명시하고, 확인하지 못한 부분은 "미확인"으로 표기해라.

[출력 순서 — 반드시 이 순서로 맨 앞에]
1) 30초 결론: 결론 한 단어(🟢 매수 검토 / 🟡 상장일 대기 / 🔵 인수권 매도 / ⚪ 패스) + 이유 한 줄
2) 어림 손익표: 본전선(현재 사이클 단계 기준: ① 권리락 전 본주+청약 = 권리락 이론가 Px / ③ 인수권 매수+청약 = 인수권 + 발행가 / ⑤ 상장 대기 본주 = 현재가)과 상장일 주가 시나리오 4개(본전선 대비 +15% / 0% / −15% / −30%)의 "상장일 주가 ○○원 → 수익률 ○%", 매물 소화일수(신주 수 ÷ 최근 20거래일 평균 거래량). 위 사이트 계산값을 원문으로 검증하고 틀리면 고쳐서 제시해라.
3) 다시 볼 조건 한 줄 (예: "3Q 영업흑자 전환 시", "괴리율 −20% 이하 시")
→ 그 다음에 아래 상세 분석을 써라. 30초 결론과 9번 결론이 다르면 이유를 밝혀라.
⚠ 발행가 구분: 공시 발행가가 '예정발행가'(이사회 당시)면 1차로 쓰지 말고 권리락 직전 종가로 1차를 다시 계산해라. '1차' 라벨이거나 1차 산정일(기준일 전 3거래일) 이후 공시값만 1차로 쓴다.
⚠ 발행가 추정: 1차 = 기준주가 × (1−할인율) ÷ (1 + 증자비율×할인율), 2차 = 청약 전 기준주가 × (1−할인율), 최종 = min(1차, 2차). 2차 발행가는 반드시 '권리락 후' 주가로 계산해라 — 권리락 전 주가를 넣으면 발행가가 부풀려진다. 확정발행가가 공시됐으면 추정 대신 확정값을 써라.

[분석 요청 — 깊게]
1. 자금 목적의 실체: 공시의 자금 목적 비중을 그대로 믿지 말고, 증권신고서 '자금의 사용목적' 세부 내역으로 성장 투자형인지 채무상환·연명형인지 판정해라. 채무상환이면 어떤 부채(만기·금리·사모사채 여부)인지 밝혀라.
2. 필터 5개 판정: ①~⑤를 하나씩 통과/탈락/미확인으로 판정하고 근거를 대라(⑤는 공시일 기준 52주 고저 위치를 계산). 하나라도 탈락이면 B(본업) 후보가 아니다. 위 '자동 판정'에서 "GPT 확인 필요"·"미확인"인 항목(업계 순위, 대체 불가, 최대주주 청약 등)을 특히 채워라.
3. 발행조건: 1차·2차(확정) 발행가 산식과 할인율, 확정발행가가 1차보다 내려갈 수 있는 본주 가격 수준(이 케이스의 "부분적 보험" 구간)을 계산해라.
4. 최대주주·특수관계인 청약 참여율과 실권주 처리 방식(일반공모 / 총액인수 / 모집주선 미발행)을 확인하고, 실권 시 수급에 미치는 영향을 판단해라.
5. A(인수권 괴리) 판정: 위 괴리율 추이로 인수권이 싼지 비싼지, "인수권 매수 + 청약" 시 신주 원가(인수권 + 발행가)가 상장일 예상 주가 대비 유리한지 계산해라. 괴리가 방치된 이유를 전제 6번 기준으로 설명해라.
6. 수급 사이클 위치: 현재 사이클 위치(${caseStage(s)})에서 다음 구간(권리락/인수권 매도/청약/신주 상장 매물)까지 예상되는 수급 압력과 크기(신주 물량 ÷ 일평균 거래량)를 추정해라.
7. 베어 케이스(steelman): 이 케이스에 들어가면 안 되는 가장 강력한 반대 논거를 일부러 세게 만들어라(추가 증자, 감사의견, 채무불이행, 정정신고서 요구, 최대주주 불참 등).
8. 반증 조건: 이 판단이 틀렸음을 보여줄 단 하나의 관찰값 또는 이벤트를 명시해라.
9. 결론: [B 본업 후보(청약·보유) / A만(인수권 매매) / 관찰(가설 검증 샘플) / 제외] 중 하나를 고르고, 이유 + 진입 전 체크리스트 + 다음에 확인할 일정 1~2개 + 확신도(상/중/하)를 제시해라.`;
}

function quickText(q) {
  if (!q) return '  (없음)';
  const be = q.breakeven, is = q.issue || {}, o = q.overhang;
  const lines = [
    `- 30초 결론(자동): ${q.word} — ${q.reason}`,
    `- 다시 볼 조건(자동): ${q.recheck}`,
    `- 사이클 단계: ${q.stage_name}`,
    `- 발행가: ${is.text || '데이터없음'}${is.d ? ` (할인율 ${(is.d * 100).toFixed(0)}%, 배정비율 ${is.r})` : ' (할인율 미확인 — 증권신고서에서 확인해라)'}`,
    `- 본전선: ${be ? `${P_N(be.value)}원 — ${be.how} (${be.text})` : (q.stage === 'listed' ? '상장 완료' : '계산 불가')}`,
    ...(q.table || []).map(t => `  · ${t.name} ${t.pct > 0 ? '+' : ''}${t.pct}%: 상장일 주가 ${P_N(t.price)}원 → 수익률 ${t.pct > 0 ? '+' : ''}${t.pct}%`),
    `- 매물 소화: ${o ? `평소 거래량 ${o.days}일치 (신주 ${P_N(o.new_shares)}주 ÷ 최근 ${o.n}일 평균 ${P_N(o.avg_volume)}주)${o.red ? ' ⚠ 60일 이상' : ''}` : '데이터없음'}`,
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
    return `- ${c.verdict ? c.verdict.emoji + ' ' : ''}${c.corp_name}(${P_NA(c.stock_code)}) | ${P_NA(c.ic_mthn)} | 자금목적 ${purpose} | 희석 ${sm.dilution_ratio != null ? (sm.dilution_ratio * 100).toFixed(0) + '%' : '-'} | 발행가 ${P_N(s.issue_price)} | ${caseStage(s)} | 권리락 ${P_NA(s.ex_rights_date)} · 인수권 ${P_NA(s.rights_start)}~${P_NA(s.rights_end)} · 상장 ${P_NA(s.listing_date)}${last ? ` | 괴리율 ${P_PCT(last.gap)}(${last.d})` : ''}`;
  }).join('\n') : '- (진행 중인 주주배정 케이스 없음)';
  const rights = (d.rights_today || []).length ? d.rights_today.map(r =>
    `- ${r.name}: 인수권 ${P_N(r.close)} / 본주 ${P_N(r.stock)} / 발행가 ${P_N(r.issue)} / 이론가 ${P_N(r.fair)} / 괴리율 ${P_PCT(r.gap)} / 인수권+청약 원가 ${P_N(r.cost)} / 거래량 ${P_N(r.volume)} / 상장폐지 ${P_NA(r.delist)}`
  ).join('\n') : '- (해당일 상장된 인수권 없음)';

  return `너는 한국 주식 유상증자 이벤트 매매 전략의 리서치 파트너다. 아래는 내 '유증 레이더'(DART + KRX 자동 수집)의 ${P_NA(d.last_rights_date)} 기준 스냅샷이다. 전체를 훑고 오늘 내가 집중할 곳을 골라줘라.

${PREMISES}

${FILTERS}

${CHART_RULE}

[진행 중인 주주배정 유증 케이스]
${caseLines}

[오늘 상장된 신주인수권증서 전체 (${P_NA(d.last_rights_date)} 종가)]
${rights}

${BLINDSPOTS}

[검증 중인 가설 — 판단할 때 이 틀로 정리해라]
- H1 인수권 괴리: 괴리율이 X% 이상일 때 "인수권 매수 + 청약"의 기대수익
- H2 상장일 매물 반등: 신주 상장일 급락 후 D+3~D+10 반등 여부
- H3 권리락 착시 급등: 권리락 첫날~D+3 단기 급등 반복 여부

[브리핑 요청]
1. 오늘의 우선순위: 위 케이스를 [B 본업 후보 / A 기회(인수권 괴리) / 관찰 샘플 / 제외]로 분류하고, 각각 한 줄 이유를 대라. 필터 5개로 걸러지는 종목은 명확히 탈락시켜라.
2. 인수권 괴리 랭킹: 괴리율이 가장 크게 벌어진 인수권 3개를 골라 괴리가 방치된 이유(강제 투매·상장 물량 선반영·공매도 차익 차단)와 남은 거래일을 함께 정리해라.
3. 이번 주 캘린더: 앞으로 5거래일 안에 권리락·인수권 시작/종료·청약·신주 상장이 있는 케이스를 날짜순으로 나열하고, 각 이벤트에서 확인할 것 1개씩 적어라.
4. 가설 샘플: H1·H2·H3 검증 샘플로 기록할 가치가 있는 케이스와, 기록할 때 추가로 수집해야 할 데이터를 제시해라.
5. 경고: 채무상환형·초대형 희석·정정신고서 요구 등 위험 신호가 있는 케이스를 짚어라.
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
