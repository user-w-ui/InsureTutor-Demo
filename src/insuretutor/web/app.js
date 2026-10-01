import { PdfViewer } from './pdf-viewer.js';

const $ = (id) => document.getElementById(id);
const words = {
  subtitle: ['Understand the plan. Check the source.', '读懂保障，核对原文', '讀懂保障，核對原文'],
  heading: ['From questions to evidence.', '从问题，回到依据。', '從問題，回到依據。'],
  newChat: ['New chat', '新对话', '新對話'], welcome: ['What would you like to know?', '关于这份宣传册，你想了解什么？', '關於這份宣傳冊，你想了解甚麼？'],
  welcomeText: ['Explore benefits, withdrawal conditions and fees. Follow citations to the original text.', '了解保障、提款条件与费用，点击回答引用核对原文。', '了解保障、提款條件與費用，點擊回答引用核對原文。'],
  question: ['Your question', '你的问题', '你的問題'], placeholder: ['Ask a question about this brochure…', '问一个关于宣传册的问题…', '問一個關於宣傳冊的問題…'],
  language: ['Language', '语言', '語言'], send: ['Send ↗', '发送 ↗', '發送 ↗'],
  fineprint: ['Explains this brochure only; refer to policy documents for contractual terms.', '仅解释本册内容；具体条款以保单文件为准。', '僅解釋本冊內容；具體條款以保單文件為準。'],
  reference: ['Source reference', '原文参考', '原文參考'], openPdf: ['Open PDF ↗', '打开原件 ↗', '打開原件 ↗'], page: ['Page', '页', '頁'], fit: ['Fit width', '适合宽度', '適合寬度'],
  connecting: ['Connecting…', '正在连接…', '正在連接…'], agent: ['Ready to chat', '可以开始提问', '可以開始提問'], excerptsMode: ['Source excerpts mode', '原文摘录模式', '原文摘錄模式'], offline: ['Service unavailable', '服务暂不可用', '服務暫不可用'],
  loadingPdf: ['Opening the original PDF…', '正在打开原始 PDF…', '正在打開原始 PDF…'],
  pdfReady: ['Physical PDF pages. Green: text blocks; amber: whole tables.', 'PDF 物理页码；绿色为文本块，琥珀色为整表范围。', 'PDF 物理頁碼；綠色為文本塊，琥珀色為整表範圍。'],
  pdfError: ['PDF preview unavailable. Use “Open PDF”.', 'PDF 预览暂不可用，请使用“打开原件”。', 'PDF 預覽暫不可用，請使用「打開原件」。'],
  waiting: ['Preparing a source-checked answer', '正在准备并校验回答', '正在準備並校驗回答'],
  answered: ['Source-backed answer', '有来源的解释', '有來源的解釋'], clarification: ['Clarification needed', '需要澄清', '需要澄清'], refused: ['Outside the answer boundary', '回答边界', '回答邊界'], insufficient: ['Insufficient evidence', '证据不足', '證據不足'], source_conflict: ['Source discrepancy', '原文存在差异', '原文存在差異'], excerpts: ['Original excerpts', '原文摘录', '原文摘錄'],
  you: ['You', '你', '你'], allSources: ['All references', '查看全部引用', '查看全部引用'], position: ['Location', '位置', '位置'],
  table: ['Whole table', '整表范围', '整表範圍'], block: ['Text block', '原始文本块', '原始文本塊'], pageOnly: ['Page only', '仅定位到页', '僅定位到頁'],
  tableNote: ['Coordinates cover the whole table, not a specific row or cell.', '来源坐标覆盖整张表，并非某一行或单元格。', '來源坐標覆蓋整張表，並非某一行或單元格。'],
  blockNote: ['Highlights show source blocks, not individual words or sentences.', '高亮为原始文本块范围，非逐字或逐句标注。', '高亮為原始文本塊範圍，非逐字或逐句標註。'],
  pageNote: ['No reliable region coordinates; the citation opens the physical page.', '无可靠区域坐标，此引用定位到物理页。', '無可靠區域坐標，此引用定位到物理頁。'],
  conflictNote: ['Chinese and English differ. Both versions are retained; neither is selected as authoritative.', '中英文原文存在差异，保留双方，不选择任一版本为权威。', '中英文原文存在差異，保留雙方，不選擇任一版本為權威。'],
  invalid_input: ['Enter a nonblank question of at most 4,000 characters.', '请输入非空问题，最多 4,000 字。', '請輸入非空問題，最多 4,000 字。'],
  sessions_busy: ['Sessions are busy. Please try again shortly.', '当前会话繁忙，请稍后重试。', '目前會話繁忙，請稍後重試。'],
  internal_error: ['The request failed. Your question is retained; try again.', '请求失败，已保留问题，可以重新发送。', '請求失敗，已保留問題，可以重新發送。'],
  network: ['Connection failed. Your question is retained; try again.', '连接失败，已保留问题，可以重新发送。', '連接失敗，已保留問題，可以重新發送。'],
  clientTimeout: ['Response timed out. Your question is retained. The server may still finish this turn.', '等待超时，已保留问题；服务端可能仍在完成本轮。', '等待逾時，已保留問題；服務端可能仍在完成本輪。'],
  retry: ['Reconnect', '重新连接', '重新連接'], required: ['Related conditions and notes', '关联条件与脚注', '關聯條件與腳註'],
  noEvidence: ['No citation for this turn.', '本轮没有可展示的引用。', '本輪沒有可展示的引用。'],
  more: ['Read full question', '展开完整问题', '展開完整問題'], less: ['Collapse', '收起问题', '收起問題'],
  model_unconfigured: ['No model configured; showing original excerpts.', '未配置模型，展示原文摘录。', '未配置模型，展示原文摘錄。'],
  retrieval_failed: ['Source retrieval failed; no generated answer is available.', '来源检索失败，无法生成回答。', '來源檢索失敗，無法生成回答。'],
  no_evidence: ['No supporting evidence was found for this turn.', '本轮未找到支持问题的证据。', '本輪未找到支持問題的證據。'],
  model_or_tool_failed: ['The model or search call failed; showing available original evidence.', '模型或补查调用失败，展示已取得的原文证据。', '模型或補查呼叫失敗，展示已取得的原文證據。'],
  timeout: ['The answer timed out; showing available original evidence.', '回答超时，展示已取得的原文证据。', '回答逾時，展示已取得的原文證據。'],
  invalid_json: ['Format validation failed (JSON syntax or fields); showing original evidence.', '格式层校验未通过（JSON 语法或字段），展示原文证据。', '格式層校驗未通過（JSON 語法或欄位），展示原文證據。'],
  reference_rejected: ['Citation validation failed; showing original evidence.', '引用校验未通过，展示原文证据。', '引用校驗未通過，展示原文證據。'],
  turn_limit: ['The agent reached its turn limit; showing available original evidence.', 'Agent 达到回合上限，展示已取得的原文证据。', 'Agent 達到回合上限，展示已取得的原文證據。'],
  degraded: ['The answer fell back to original evidence; the failure layer is unknown.', '回答已降级为原文证据，未识别失败层级。', '回答已降級為原文證據，未識別失敗層級。'],
};
const referenceRejectionReasons = new Set([
  'unknown_or_missing_evidence', 'missing_source', 'invalid_source_id',
]);
function reasonMessageKey(reason) {
  if (referenceRejectionReasons.has(reason)) return 'reference_rejected';
  return Object.hasOwn(words, reason) ? reason : 'degraded';
}
let language = initialLanguage(), sessionId = null, pending = false, ready = false, mode = null;
let turnNumber = 0, active = null, pdfStatus = 'loadingPdf', pdfFailed = false;
const turns = new Map();
const viewer = new PdfViewer((key, error = false) => { pdfStatus = key; pdfFailed = error; updatePdfStatus(); });

function initialLanguage() {
  const lang = navigator.language.toLowerCase();
  return lang.startsWith('zh') ? (/tw|hk|hant/.test(lang) ? 'zh-Hant' : 'zh-Hans') : 'en';
}
function t(key) { return words[key]?.[['en', 'zh-Hans', 'zh-Hant'].indexOf(language)] || words.internal_error[['en', 'zh-Hans', 'zh-Hant'].indexOf(language)]; }
function element(tag, text = '', className = '') {
  const node = document.createElement(tag); node.textContent = text; node.className = className; return node;
}
function displayText(text) { return (text || '').replace(/\\([$%*])/g, '$1'); }
function updatePdfStatus() { $('viewer-status').textContent = t(pdfStatus); $('viewer-status').classList.toggle('error', pdfFailed); }
function translate() {
  document.documentElement.lang = language;
  document.querySelectorAll('[data-i18n]').forEach((node) => { node.textContent = t(node.dataset.i18n); });
  $('question-input').placeholder = t('placeholder');
  $('document-pages').textContent = `· ${viewer.count} ${language === 'en' ? 'pages' : language === 'zh-Hant' ? '頁' : '页'}`;
  $('service-status').textContent = t(ready ? (mode === 'agent' ? 'agent' : 'excerptsMode') : 'connecting');
  $('source-zh').textContent = language === 'zh-Hans' ? '中文原文' : language === 'zh-Hant' ? '中文原文' : 'Chinese';
  $('source-en').textContent = 'English';
  updatePdfStatus(); renderSuggestions(); if (active) updateCitation();
}
function renderSuggestions() {
  $('suggestions').replaceChildren();
  const questions = language === 'en' ? ['What are the withdrawal conditions?', 'How does insurability work?', 'Which returns are guaranteed?'] : language === 'zh-Hant' ? ['定期提款有哪些條件？', '保證可保權益是甚麼？', '哪些回報有保證？'] : ['定期提款有哪些条件？', '保证可保权益是什么？', '哪些回报有保证？'];
  questions.forEach((question) => {
    const button = element('button', question, 'case-button'); button.type = 'button'; button.disabled = pending;
    button.addEventListener('click', () => { $('question-input').value = question; updateCount(); $('question-input').focus(); });
    $('suggestions').append(button);
  });
}
function updateCount() { $('character-count').textContent = `${Array.from($('question-input').value).length} / 4000`; }
function setPending(value) {
  pending = value; $('send').disabled = value || !ready; $('question-input').readOnly = value;
  $('new-chat').disabled = value; $('response-language').disabled = value; renderSuggestions();
}
function groupVersion(group, lang) { return group.versions.find((v) => v.language === lang) || group.versions[0]; }
function refLink(turn, group, sourceLanguage) {
  const version = groupVersion(group, sourceLanguage);
  const number = turn.result.reference_groups.indexOf(group) + 1;
  const link = element('a', '', `ref-link${group.conflict ? ' conflict-ref' : ''}`);
  link.href = `#turn=${turn.id}&unit=${encodeURIComponent(group.unit_id)}&lang=${version.language}`;
  link.dataset.reference = `${turn.id}:${group.unit_id}:${version.language}`;
  const title = version.title.replace(/\s+/g, ' ');
  link.append(element('b', `[${number}]`), document.createTextNode(title.length > 36 ? title.slice(0, 36) + '…' : title), element('span', `p.${version.sources[0]?.pdf_page || '?'}${group.conflict ? ` · ${version.language === 'en' ? 'EN' : '中文'}` : ''}`));
  link.title = version.title;
  link.addEventListener('click', (event) => { event.preventDefault(); history.pushState(null, '', link.href); selectGroup(turn, group, version.language); });
  return link;
}
function addRefs(parent, turn, ids) {
  const refs = element('div', '', 'reference-links');
  for (const uid of [...new Set(ids)]) {
    const group = turn.result.reference_groups.find((g) => g.unit_id === uid); if (!group) continue;
    const langs = group.conflict ? ['zh-Hant', 'en'] : [turn.result.response_language === 'en' ? 'en' : 'zh-Hant'];
    langs.forEach((lang) => refs.append(refLink(turn, group, lang)));
  }
  parent.append(refs);
}
function renderAnswer(turn, container) {
  const result = turn.result;
  const heading = element('div', '', 'answer-heading'); heading.append(element('strong', 'InsureTutor'), element('span', t(result.status))); container.append(heading);
  if (result.reason) container.append(element('p', t(reasonMessageKey(result.reason)), 'mode-notice'));
  if (result.status === 'source_conflict') container.append(element('div', t('conflictNote'), 'conflict-notice'));
  if (result.claims.length) {
    result.claims.forEach((claim, index) => {
      const block = element('div', claim.text, `claim${index === 0 ? ' summary' : ''}`);
      if (claim.calculation) block.append(element('p', `${claim.calculation.steps}\n${claim.calculation.result}`, 'calculation'));
      addRefs(block, turn, claim.evidence_ids); container.append(block);
    });
  } else container.append(element('p', result.explanation, 'claim'));
  result.notices.forEach((notice) => container.append(element('p', notice, 'mode-notice')));
  if (result.clarification_question) container.append(element('p', result.clarification_question, 'clarification-question'));
  const groups = result.reference_groups;
  if (groups.length) {
    const details = element('details', '', 'all-sources'); details.append(element('summary', `${t('allSources')} · ${groups.length}`));
    addRefs(details, turn, groups.map((g) => g.unit_id)); container.append(details);
    // Excerpts have no generated claims; make the actual original text visible.
    if (!result.claims.length && result.status === 'excerpts') {
      groups.forEach((group) => {
        const excerpt = element('details', '', 'excerpt'); const version = groupVersion(group, result.response_language === 'en' ? 'en' : 'zh-Hant');
        excerpt.append(element('summary', version.title));
        excerpt.append(element('blockquote', displayText(version.sources.filter((s) => s.role === 'body').map((s) => s.quote).join('\n'))));
        addRefs(excerpt, turn, [group.unit_id]); container.append(excerpt);
      });
    }
  }
  container.append(element('p', t('fineprint'), 'answer-footer'));
}
function selectGroup(turn, group, lang, index = 0) {
  active = { turn, group, lang, index }; $('citation-detail').hidden = false;
  updateCitation(); markLinks(); viewer.select(active.locations, active.index);
}
function markLinks() {
  const key = active ? `${active.turn.id}:${active.group.unit_id}:${active.lang}` : '';
  document.querySelectorAll('.ref-link').forEach((node) => { node.classList.toggle('active', node.dataset.reference === key); });
}
function updateCitation() {
  const { turn, group, lang } = active;
  const version = groupVersion(group, lang);
  const locations = [];
  for (const source of version.sources) {
    if (!locations.some((s) => s.pdf_page === source.pdf_page && JSON.stringify(s.bbox_raw) === JSON.stringify(source.bbox_raw))) locations.push(source);
  }
  active.locations = locations; active.index = Math.min(active.index, locations.length - 1);
  const location = locations[active.index];
  $('citation-number').textContent = turn.result.reference_groups.indexOf(group) + 1;
  $('citation-title').textContent = version.title;
  $('citation-page').textContent = `PDF · ${t('page')} ${location.pdf_page}`;
  const box = location.bbox_raw;
  const valid = box?.length === 4 && box.every((v) => Number.isFinite(v) && v >= 0 && v <= 1000) && box[2] > box[0] && box[3] > box[1];
  const precision = valid ? (location.bbox_precision === 'whole_table' ? 'table' : 'block') : 'pageOnly';
  $('precision-label').textContent = t(precision); $('precision-note').textContent = t(precision === 'table' ? 'tableNote' : precision === 'block' ? 'blockNote' : 'pageNote');
  $('citation-quote').textContent = displayText(version.sources.filter((s) => s.role === 'body').map((s) => s.quote).join('\n'));
  $('citation-context').textContent = displayText(version.sources.filter((s) => s.role === 'context').map((s) => s.quote).join(' · '));
  $('citation-context').hidden = !$('citation-context').textContent;
  $('location-switches').replaceChildren();
  if (locations.length > 1) locations.forEach((source, index) => {
    const button = element('button', `${t('position')} ${index + 1}`); button.classList.toggle('active', index === active.index);
    button.title = `${source.role}: p.${source.pdf_page}`;
    button.addEventListener('click', () => selectGroup(turn, group, lang, index)); $('location-switches').append(button);
  });
  for (const sourceLanguage of ['zh-Hant', 'en']) {
    const button = $(sourceLanguage === 'en' ? 'source-en' : 'source-zh');
    button.classList.toggle('active', lang === sourceLanguage); button.setAttribute('aria-pressed', String(lang === sourceLanguage));
    button.disabled = !group.versions.some((v) => v.language === sourceLanguage);
  }
  $('required-references').replaceChildren();
  if (group.required_unit_ids.length) {
    $('required-references').append(element('span', t('required'), 'required-label'));
    group.required_unit_ids.forEach((uid) => { const related = turn.result.reference_groups.find((g) => g.unit_id === uid); if (related) $('required-references').append(refLink(turn, related, lang)); });
  }
  $('citation-detail').scrollTop = 0;
}

async function submit(event) {
  event.preventDefault(); if (pending || !ready) return;
  const question = $('question-input').value;
  if (!question.trim() || Array.from(question).length > 4000) { showError('invalid_input'); return; }
  $('question-input').value = ''; updateCount();
  $('chat-error').hidden = true; document.querySelector('.welcome')?.remove();
  const questionRow = element('div', '', 'question-row'); const bubble = element('div', '', 'question-bubble expanded');
  bubble.append(element('p', question));
  if (question.length > 85) {
    bubble.classList.remove('expanded'); const toggle = element('button', t('more')); toggle.type = 'button'; toggle.setAttribute('aria-expanded', 'false');
    toggle.addEventListener('click', () => { const expanded = bubble.classList.toggle('expanded'); toggle.textContent = t(expanded ? 'less' : 'more'); toggle.setAttribute('aria-expanded', String(expanded)); }); bubble.append(toggle);
  }
  questionRow.append(element('span', t('you'), 'speaker user-speaker'), bubble);
  const answerRow = element('article', '', 'answer-row'); const content = element('div', '', 'answer-content');
  answerRow.append(element('span', 'i', 'speaker tutor-speaker'), content);
  $('conversation').append(questionRow, answerRow);
  setPending(true); const started = Date.now();
  const updateWaiting = () => { content.textContent = `${t('waiting')} · ${Math.floor((Date.now() - started) / 1000)}s`; $('conversation').scrollTop = $('conversation').scrollHeight; };
  updateWaiting(); const timer = setInterval(updateWaiting, 1000);
  const controller = new AbortController(); const timeout = setTimeout(() => controller.abort(), 75000);
  try {
    const response = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: controller.signal,
      body: JSON.stringify({ question, session_id: sessionId, response_language: $('response-language').value }) });
    const data = await response.json();
    if (!response.ok) { const error = new Error(data.error?.code || 'internal_error'); error.requestId = data.error?.request_id; throw error; }
    sessionId = data.session_id;
    if ($('response-language').value === 'auto') { language = data.response_language; translate(); }
    clearInterval(timer); content.replaceChildren();
    const turn = { id: ++turnNumber, result: data }; turns.set(turn.id, turn); renderAnswer(turn, content);
    if (data.reference_groups.length) selectGroup(turn, data.reference_groups[0], data.response_language === 'en' ? 'en' : 'zh-Hant');
    $('conversation').scrollTop = Math.max(0, answerRow.offsetTop - $('conversation').offsetTop - 14);
  } catch (error) {
    answerRow.remove(); questionRow.remove();
    $('question-input').value = question; updateCount();
    showError(error.name === 'AbortError' ? 'clientTimeout' : words[error.message] ? error.message : 'network', error.requestId);
  } finally { clearInterval(timer); clearTimeout(timeout); setPending(false); $('question-input').focus(); }
}
function showError(code, requestId) {
  $('chat-error').hidden = false; $('chat-error').textContent = t(code) + (requestId ? ` · ${requestId.slice(0, 8)}` : '');
}
async function connect() {
  $('service-status').textContent = t('connecting');
  try {
    const response = await fetch('/api/health'); if (!response.ok) throw new Error();
    const health = await response.json(); ready = health.ready; mode = health.mode; translate(); $('send').disabled = !ready;
    $('open-pdf').href = `${health.pdf_url}#page=1`;
    if (!viewer.pdf) try { await viewer.open(health.pdf_url); } catch (_) { pdfStatus = 'pdfError'; pdfFailed = true; updatePdfStatus(); }
  } catch (_) {
    ready = false; $('send').disabled = true; $('service-status').textContent = t('offline');
    $('chat-error').hidden = false; $('chat-error').replaceChildren(element('span', t('network')));
    const retry = element('button', t('retry'), 'case-button'); retry.addEventListener('click', () => { $('chat-error').hidden = true; connect(); }); $('chat-error').append(retry);
  }
}
function readReferenceHash() {
  const params = new URLSearchParams(location.hash.slice(1)); const turn = turns.get(Number(params.get('turn')));
  const group = turn?.result.reference_groups.find((g) => g.unit_id === params.get('unit'));
  if (group) selectGroup(turn, group, params.get('lang') === 'en' ? 'en' : 'zh-Hant');
}
$('composer').addEventListener('submit', submit);
$('question-input').addEventListener('input', updateCount);
$('question-input').addEventListener('keydown', (event) => { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); $('composer').requestSubmit(); } });
$('response-language').addEventListener('change', () => { language = $('response-language').value === 'auto' ? initialLanguage() : $('response-language').value; translate(); });
$('new-chat').addEventListener('click', () => {
  if (pending) return; sessionId = null; turns.clear(); active = null; $('conversation').replaceChildren(); $('citation-detail').hidden = true;
  viewer.locations = []; viewer.render(1); history.replaceState(null, '', location.pathname); $('chat-error').hidden = true; $('question-input').value = ''; updateCount(); $('question-input').focus();
});
for (const lang of ['zh-Hant', 'en']) $(lang === 'en' ? 'source-en' : 'source-zh').addEventListener('click', () => { if (active) selectGroup(active.turn, active.group, lang); });
$('prev-page').addEventListener('click', () => viewer.render(viewer.pageNumber - 1));
$('next-page').addEventListener('click', () => viewer.render(viewer.pageNumber + 1));
$('page-input').addEventListener('change', () => viewer.render($('page-input').value));
$('zoom-out').addEventListener('click', () => { viewer.zoom = Math.max(.75, viewer.zoom - .25); viewer.render(viewer.pageNumber, true); });
$('zoom-in').addEventListener('click', () => { viewer.zoom = Math.min(2, viewer.zoom + .25); viewer.render(viewer.pageNumber, true); });
$('fit-page').addEventListener('click', () => { viewer.zoom = 1; viewer.render(viewer.pageNumber, true); });
window.addEventListener('popstate', readReferenceHash); window.addEventListener('hashchange', readReferenceHash);
let resizeTimer; window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => viewer.render(viewer.pageNumber, true), 180); });
translate(); connect();
