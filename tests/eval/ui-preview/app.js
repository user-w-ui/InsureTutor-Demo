const $ = (id) => document.getElementById(id);
let fixture, currentCase, currentSource, locationIndex = 0;
let pdf, pdfLoading, pdfLib, renderTask, renderVersion = 0;
let pageNumber = 12, zoom = 1, sourceLanguage = 'zh-Hant';

function textElement(tag, text, className) {
  const node = document.createElement(tag);
  node.textContent = text;
  if (className) node.className = className;
  return node;
}

function caseHash(caseId, sourceId) {
  const params = new URLSearchParams({ case: caseId });
  if (sourceId) params.set('cite', sourceId);
  return `#${params}`;
}

function referenceLink(source, full = false) {
  const link = document.createElement('a');
  link.className = `ref-link${currentCase.conflict ? ' conflict-ref' : ''}`;
  link.href = caseHash(currentCase.id, source.id);
  link.dataset.sourceId = source.id;
  link.setAttribute('aria-label', `${source.title}，${source.language === 'en' ? '英文' : '中文'}原文，PDF 第 ${source.locations[0].page} 页`);
  link.title = link.getAttribute('aria-label');
  link.append(textElement('b', `[${source.number}]`));
  link.append(document.createTextNode(full ? source.title : source.title.replace(/^附注 (\d+) · .+$/, '附注 $1')));
  link.append(textElement('span', `p.${source.locations[0].page}${currentCase.conflict ? (source.language === 'en' ? ' · EN' : ' · 中文') : ''}`));
  link.addEventListener('click', (event) => {
    event.preventDefault();
    history.pushState(null, '', link.href);
    selectSource(source.id, true);
  });
  return link;
}

function renderClaims() {
  $('answer-claims').replaceChildren();
  for (const [index, claim] of currentCase.claims.entries()) {
    const block = textElement('div', '', `claim${index === 0 ? ' summary' : ''}`);
    const match = claim.text.match(/^(\d+\)\s*[^：:\n]{1,30}[：:])/);
    if (match) {
      block.append(textElement('strong', match[0]));
      block.append(document.createTextNode(claim.text.slice(match[0].length)));
    } else block.append(document.createTextNode(claim.text));
    const refs = textElement('div', '', 'reference-links');
    for (const uid of claim.unit_ids) {
      const sources = currentCase.sources.filter((s) => s.unit_id === uid &&
        (currentCase.conflict || s.language === sourceLanguage));
      for (const source of sources) refs.append(referenceLink(source));
    }
    block.append(refs);
    $('answer-claims').append(block);
  }
  $('source-list').replaceChildren();
  const sources = currentCase.sources.filter((s) => currentCase.conflict || s.language === sourceLanguage);
  for (const source of sources) $('source-list').append(referenceLink(source, true));
  $('source-count').textContent = `查看全部引用 · ${sources.length} 处`;
  markActiveLinks();
}

function markActiveLinks() {
  document.querySelectorAll('.ref-link').forEach((node) => {
    const active = node.dataset.sourceId === currentSource?.id;
    node.classList.toggle('active', active);
    if (active) node.setAttribute('aria-current', 'true');
    else node.removeAttribute('aria-current');
  });
}

function loadCase(id, sourceId) {
  currentCase = fixture.cases.find((c) => c.id === id) || fixture.cases[0];
  currentSource = undefined;
  document.querySelectorAll('.case-button').forEach((b) => {
    b.classList.toggle('active', b.dataset.caseId === currentCase.id);
    b.setAttribute('aria-pressed', String(b.dataset.caseId === currentCase.id));
  });
  $('question-text').textContent = currentCase.question;
  $('question').classList.remove('expanded');
  $('expand-question').hidden = currentCase.question.length < 85;
  $('expand-question').textContent = '展开完整问题';
  $('expand-question').setAttribute('aria-expanded', 'false');
  $('conflict-notice').hidden = !currentCase.conflict;
  $('conversation').scrollTop = 0;
  const chosen = currentCase.sources.find((s) => s.id === sourceId) ||
    currentCase.sources.find((s) => s.language === sourceLanguage) || currentCase.sources[0];
  sourceLanguage = chosen.language;
  renderClaims();
  selectSource(chosen.id, true);
}

function selectSource(id, scroll = true) {
  const source = currentCase.sources.find((s) => s.id === id);
  if (!source) return;
  currentSource = source;
  locationIndex = 0;
  if (sourceLanguage !== source.language) {
    sourceLanguage = source.language;
    renderClaims();
  }
  updateCitation();
  markActiveLinks();
  renderPage(source.locations[0].page, scroll);
}

function updateCitation() {
  const source = currentSource;
  const location = source.locations[locationIndex];
  $('citation-number').textContent = source.number;
  $('citation-title').textContent = source.title;
  $('citation-page').textContent = `PDF 第 ${location.page} 页`;
  const table = location.precision === 'table';
  $('precision-label').textContent = table ? '整表范围' : '原始文本块';
  $('precision-note').textContent = table
    ? '当前来源坐标覆盖整张表；上方摘录对应本条内容，未伪造行或单元格位置。'
    : '高亮为原始文本块范围，非逐字标注；PDF 页码按文件物理页计算。';
  // Display extraction Markdown escapes as printed punctuation; raw quotes
  // and their anchors remain unchanged in the fixture.
  $('citation-quote').textContent = source.quote.replace(/\\([$%*])/g, '$1');
  $('citation-context').textContent = source.context.replace(/\\([$%*])/g, '$1');
  $('citation-context').hidden = !source.context;
  $('citation-detail').scrollTop = 0;
  for (const lang of ['zh-Hant', 'en']) {
    const button = $(lang === 'en' ? 'source-en' : 'source-zh');
    button.classList.toggle('active', source.language === lang);
    button.setAttribute('aria-pressed', String(source.language === lang));
    button.disabled = !currentCase.sources.some((s) => s.unit_id === source.unit_id && s.language === lang);
  }
  $('location-switches').replaceChildren();
  if (source.locations.length > 1) {
    source.locations.forEach((loc, index) => {
      const button = textElement('button', `位置 ${index + 1}`);
      button.classList.toggle('active', index === locationIndex);
      button.addEventListener('click', () => {
        locationIndex = index;
        updateCitation();
        renderPage(loc.page, true);
      });
      $('location-switches').append(button);
    });
  }
}

function drawHighlights(scroll) {
  $('highlights').replaceChildren();
  if (!currentSource) return;
  const locations = currentSource.locations.filter((l) => l.page === pageNumber);
  let selected;
  for (const location of locations) {
    const [x0, y0, x1, y1] = location.bbox;
    const box = textElement('div', '', `highlight flash${location.precision === 'table' ? ' table' : ''}`);
    box.style.left = `${x0 / 10}%`;
    box.style.top = `${y0 / 10}%`;
    box.style.width = `${(x1 - x0) / 10}%`;
    box.style.height = `${(y1 - y0) / 10}%`;
    box.append(textElement('span', `[${currentSource.number}] ${location.precision === 'table' ? '整表范围' : '引用位置'}`, 'highlight-label'));
    $('highlights').append(box);
    if (location === currentSource.locations[locationIndex]) selected = box;
  }
  if (scroll && selected) {
    const area = $('pdf-scroll');
    const target = selected.offsetTop + Math.min(selected.offsetHeight, area.clientHeight / 2) / 2;
    area.scrollTop = Math.max(0, $('pdf-page').offsetTop - area.offsetTop + target - area.clientHeight / 2);
  }
}

async function ensurePdf() {
  if (!pdfLoading) {
    pdfLoading = (async () => {
      pdfLib = await import('./vendor/pdf.min.mjs');
      pdfLib.GlobalWorkerOptions.workerSrc = new URL('./vendor/pdf.worker.min.mjs', import.meta.url).href;
      const loading = pdfLib.getDocument({ url: fixture.pdf_url, useSystemFonts: true, isEvalSupported: false });
      pdf = await loading.promise;
      $('page-total').textContent = `/ ${pdf.numPages} 页`;
      $('page-input').max = pdf.numPages;
      return pdf;
    })();
  }
  return pdfLoading;
}

async function renderPage(number, scroll = false) {
  const version = ++renderVersion;
  const nextPage = Math.max(1, Math.min(fixture.page_count, Number(number) || 1));
  pageNumber = nextPage;
  $('page-input').value = nextPage;
  $('prev-page').disabled = nextPage === 1;
  $('next-page').disabled = nextPage === fixture.page_count;
  $('open-pdf').href = `${fixture.pdf_url}#page=${nextPage}`;
  $('viewer-status').classList.remove('error');
  $('viewer-status').textContent = `正在打开 PDF 第 ${nextPage} 页…`;
  try {
    if (renderTask) {
      renderTask.cancel();
      try { await renderTask.promise; } catch (_) { /* Cancelled for a new page. */ }
    }
    const doc = await ensurePdf();
    const page = await doc.getPage(nextPage);
    if (version !== renderVersion) return;
    const width = Math.max(240, $('pdf-scroll').clientWidth - (window.innerWidth < 960 ? 30 : 52));
    const base = page.getViewport({ scale: 1 });
    const viewport = page.getViewport({ scale: width / base.width * zoom });
    const pixelRatio = window.devicePixelRatio || 1;
    const canvas = $('pdf-canvas');
    canvas.width = Math.round(viewport.width * pixelRatio);
    canvas.height = Math.round(viewport.height * pixelRatio);
    canvas.style.width = `${viewport.width}px`;
    canvas.style.height = `${viewport.height}px`;
    $('pdf-page').style.width = `${viewport.width}px`;
    $('pdf-page').style.height = `${viewport.height}px`;
    $('highlights').replaceChildren();
    renderTask = page.render({ canvasContext: canvas.getContext('2d'), viewport,
      transform: pixelRatio === 1 ? null : [pixelRatio, 0, 0, pixelRatio, 0, 0] });
    await renderTask.promise;
    if (version !== renderVersion) return;
    const referenced = currentSource.locations.some((loc) => loc.page === nextPage);
    $('viewer-status').textContent = referenced ? '点击引用可跳页并定位；绿色为文本块，琥珀色为整表范围。' : '正在浏览原始 PDF；点击回答中的引用可回到对应位置。';
    drawHighlights(scroll);
    if (!scroll) $('pdf-scroll').scrollTop = 0;
  } catch (error) {
    if (version !== renderVersion || error?.name === 'RenderingCancelledException') return;
    $('viewer-status').classList.add('error');
    $('viewer-status').textContent = 'PDF 预览暂不可用，请使用“打开原件”。';
    $('highlights').replaceChildren();
  }
}

function readHash() {
  const params = new URLSearchParams(location.hash.slice(1));
  const id = params.get('case') || fixture.cases[0].id;
  const sourceId = params.get('cite');
  if (currentCase?.id === id && sourceId) selectSource(sourceId, true);
  else loadCase(id, sourceId);
}

async function initialize() {
  try {
    const response = await fetch('demo.json');
    if (!response.ok) throw new Error('fixture unavailable');
    fixture = await response.json();
    for (const example of fixture.cases) {
      const button = textElement('button', example.label, 'case-button');
      button.dataset.caseId = example.id;
      button.title = example.subtitle;
      button.addEventListener('click', () => {
        history.pushState(null, '', caseHash(example.id));
        loadCase(example.id);
      });
      $('case-switcher').append(button);
    }
    readHash();
    $('expand-question').addEventListener('click', () => {
      const expanded = $('question').classList.toggle('expanded');
      $('expand-question').setAttribute('aria-expanded', String(expanded));
      $('expand-question').textContent = expanded ? '收起问题' : '展开完整问题';
    });
    window.addEventListener('hashchange', readHash);
    window.addEventListener('popstate', readHash);
    $('reset-case').addEventListener('click', () => {
      history.pushState(null, '', caseHash(fixture.cases[0].id));
      loadCase(fixture.cases[0].id);
    });
    $('next-case').addEventListener('click', () => {
      const index = fixture.cases.indexOf(currentCase);
      const next = fixture.cases[(index + 1) % fixture.cases.length];
      history.pushState(null, '', caseHash(next.id));
      loadCase(next.id);
    });
    $('prev-page').addEventListener('click', () => renderPage(pageNumber - 1));
    $('next-page').addEventListener('click', () => renderPage(pageNumber + 1));
    $('page-input').addEventListener('change', () => renderPage($('page-input').value));
    $('zoom-out').addEventListener('click', () => { zoom = Math.max(.75, zoom - .25); renderPage(pageNumber, true); });
    $('zoom-in').addEventListener('click', () => { zoom = Math.min(2, zoom + .25); renderPage(pageNumber, true); });
    $('fit-page').addEventListener('click', () => { zoom = 1; renderPage(pageNumber, true); });
    for (const language of ['zh-Hant', 'en']) {
      $(language === 'en' ? 'source-en' : 'source-zh').addEventListener('click', () => {
        const source = currentCase.sources.find((s) => s.unit_id === currentSource.unit_id && s.language === language);
        if (source) {
          history.pushState(null, '', caseHash(currentCase.id, source.id));
          selectSource(source.id, true);
        }
      });
    }
    let resizeTimer;
    window.addEventListener('resize', () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => renderPage(pageNumber, true), 180);
    });
  } catch (_) {
    $('viewer-status').classList.add('error');
    $('viewer-status').textContent = '示例数据加载失败，请通过本地预览服务打开此页面。';
  }
}

initialize();
