// All rendering uses local PDF.js; bbox coordinates are normalized 0..1000.
export class PdfViewer {
  constructor(status) {
    this.status = status;
    this.pageNumber = 1;
    this.zoom = 1;
    this.version = 0;
    this.locations = [];
    this.index = 0;
    this.count = 20;
  }

  async open(url) {
    this.url = url;
    const lib = await import('./vendor/pdf.min.mjs');
    lib.GlobalWorkerOptions.workerSrc = new URL('./vendor/pdf.worker.min.mjs', import.meta.url).href;
    this.pdf = await lib.getDocument({ url, useSystemFonts: true, isEvalSupported: false }).promise;
    this.count = this.pdf.numPages;
    document.getElementById('page-total').textContent = `/ ${this.count}`;
    document.getElementById('page-input').max = this.count;
    await this.render(this.locations[this.index]?.pdf_page || 1, this.locations.length > 0);
  }

  select(locations, index = 0) {
    this.locations = locations;
    this.index = index;
    return this.render(locations[index]?.pdf_page || this.pageNumber, true);
  }

  async render(number, scroll = false) {
    if (!this.pdf) return;
    const $ = (id) => document.getElementById(id);
    const version = ++this.version;
    const pageNumber = Math.max(1, Math.min(this.count, Number(number) || 1));
    this.pageNumber = pageNumber;
    $('page-input').value = pageNumber;
    $('prev-page').disabled = pageNumber === 1;
    $('next-page').disabled = pageNumber === this.count;
    $('open-pdf').href = `${this.url}#page=${pageNumber}`;
    this.status('loadingPdf');
    try {
      if (this.task) {
        this.task.cancel();
        try { await this.task.promise; } catch (_) { /* A newer page superseded this render. */ }
      }
      const page = await this.pdf.getPage(pageNumber);
      if (version !== this.version) return;
      const width = Math.max(240, $('pdf-scroll').clientWidth - (window.innerWidth < 960 ? 30 : 52));
      const base = page.getViewport({ scale: 1 });
      const viewport = page.getViewport({ scale: width / base.width * this.zoom });
      const pixelRatio = window.devicePixelRatio || 1;
      const canvas = $('pdf-canvas');
      canvas.width = Math.round(viewport.width * pixelRatio);
      canvas.height = Math.round(viewport.height * pixelRatio);
      canvas.style.width = `${viewport.width}px`;
      canvas.style.height = `${viewport.height}px`;
      $('pdf-page').style.width = `${viewport.width}px`;
      $('pdf-page').style.height = `${viewport.height}px`;
      $('highlights').replaceChildren();
      this.task = page.render({ canvasContext: canvas.getContext('2d'), viewport,
        transform: pixelRatio === 1 ? null : [pixelRatio, 0, 0, pixelRatio, 0, 0] });
      await this.task.promise;
      if (version !== this.version) return;
      let selected;
      for (const location of this.locations.filter((s) => s.pdf_page === pageNumber)) {
        const box = location.bbox_raw;
        if (!Array.isArray(box) || box.length !== 4 || !box.every((n) => Number.isFinite(n) && n >= 0 && n <= 1000) || box[2] <= box[0] || box[3] <= box[1]) continue;
        const highlight = document.createElement('div');
        highlight.className = `highlight flash${location.bbox_precision === 'whole_table' ? ' table' : ''}`;
        highlight.style.left = `${box[0] / 10}%`;
        highlight.style.top = `${box[1] / 10}%`;
        highlight.style.width = `${(box[2] - box[0]) / 10}%`;
        highlight.style.height = `${(box[3] - box[1]) / 10}%`;
        $('highlights').append(highlight);
        if (location === this.locations[this.index]) selected = highlight;
      }
      this.status('pdfReady');
      if (scroll && selected) {
        const area = $('pdf-scroll');
        area.scrollTop = Math.max(0, $('pdf-page').offsetTop - area.offsetTop + selected.offsetTop - area.clientHeight / 3);
      } else $('pdf-scroll').scrollTop = 0;
    } catch (error) {
      if (version !== this.version || error?.name === 'RenderingCancelledException') return;
      this.status('pdfError', true);
      $('highlights').replaceChildren();
    }
  }
}
