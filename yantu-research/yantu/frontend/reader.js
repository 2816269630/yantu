const params = new URLSearchParams(location.search);
const id = params.get('id');
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const elements = {
  body: document.body,
  viewer: $('#viewer'),
  title: $('#title'),
  summaryTitle: $('#summaryTitle'),
  summaryDescription: $('#summaryDescription'),
  owner: $('#owner'),
  fileMeta: $('#fileMeta'),
  progressText: $('#progressText'),
  noteStatus: $('#noteStatus'),
  navPanel: $('#navigationPanel'),
  notesPanel: $('#notesPanel'),
  navigationContent: $('#navigationContent'),
  pageInput: $('#pageInput'),
  pageCount: $('#pageCount'),
  zoomValue: $('#zoomValue'),
  noteText: $('#noteText'),
  noteCount: $('#noteCount'),
  notePageLabel: $('#notePageLabel'),
  readingProgressBar: $('#readingProgressBar'),
  viewerLoading: $('#viewerLoading'),
  mobileScrim: $('#mobileScrim'),
  toast: $('#readerToast'),
  errorState: $('#errorState'),
  errorMessage: $('#errorMessage'),
};

const reader = {
  resource: null,
  progress: null,
  app: null,
  page: 1,
  total: 0,
  navigation: 'outline',
  outline: [],
  thumbnailsRendered: false,
  documentReady: false,
  saveTimer: null,
  toastTimer: null,
};

function formatBytes(value) {
  const size = Number(value) || 0;
  if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`;
  return `${Math.max(1, Math.ceil(size / 1024))} KB`;
}

function visibilityName(value) {
  return (
    {
      private: '仅自己及获授权成员',
      team: '课题组成员',
      project: '项目成员',
      public: '公开',
    }[value] || '按资料权限'
  );
}

function showToast(message) {
  clearTimeout(reader.toastTimer);
  elements.toast.textContent = message;
  elements.toast.classList.add('is-visible');
  reader.toastTimer = setTimeout(
    () => elements.toast.classList.remove('is-visible'),
    2200,
  );
}

function setSaveState(state, label) {
  elements.noteStatus.className = 'save-state';
  if (state === 'saving') elements.noteStatus.classList.add('is-saving');
  if (state === 'error') elements.noteStatus.classList.add('is-error');
  elements.noteStatus.textContent = label;
}

function showError(error) {
  console.error('Paper reader failed', error);
  elements.errorMessage.textContent = error?.message || '请稍后重试';
  elements.errorState.hidden = false;
  elements.progressText.textContent = '打开失败';
}

async function api(path, method = 'GET', body) {
  const response = await fetch('/api/v1' + path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
    credentials: 'same-origin',
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(result.message || `请求未完成（${response.status}）`);
  }
  return result.data;
}

function progressValues() {
  return {
    page: Math.max(1, Number(reader.page) || 1),
    notes: elements.noteText.value,
  };
}

async function saveProgress(delay = 600) {
  clearTimeout(reader.saveTimer);
  setSaveState('saving', '保存中…');
  reader.saveTimer = setTimeout(async () => {
    try {
      await api(
        `/resources/${encodeURIComponent(id)}/reading-progress`,
        'PATCH',
        progressValues(),
      );
      setSaveState('saved', '已自动保存');
    } catch {
      setSaveState('error', '保存失败');
    }
  }, delay);
}

function persistImmediately() {
  if (!id) return;
  fetch(`/api/v1/resources/${encodeURIComponent(id)}/reading-progress`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(progressValues()),
    credentials: 'same-origin',
    keepalive: true,
  }).catch(() => {});
}

function updateNoteMetrics() {
  const text = elements.noteText.value;
  elements.noteCount.textContent = `${text.replace(/\s/g, '').length} 字`;
}

function insertAtCursor(text) {
  const textarea = elements.noteText;
  const start = textarea.selectionStart ?? textarea.value.length;
  const end = textarea.selectionEnd ?? start;
  textarea.setRangeText(text, start, end, 'end');
  textarea.focus();
  updateNoteMetrics();
  saveProgress();
}

function toggleNavigation(force) {
  const shouldClose =
    typeof force === 'boolean'
      ? !force
      : !elements.body.classList.contains('nav-closed');
  if (shouldClose) {
    elements.body.classList.remove('nav-want-open');
    elements.body.classList.add('nav-want-closed', 'nav-closed');
  } else {
    elements.body.classList.remove('nav-want-closed', 'nav-closed');
    elements.body.classList.add('nav-want-open');
  }
  syncMobileScrim();
}

function toggleNotes(force) {
  const shouldClose =
    typeof force === 'boolean'
      ? !force
      : !elements.body.classList.contains('notes-closed');
  elements.body.classList.toggle('notes-closed', shouldClose);
  $('#toggleNotes').classList.toggle('is-active', !shouldClose);
  syncMobileScrim();
  if (!shouldClose && window.innerWidth <= 900) {
    toggleNavigation(false);
    elements.body.classList.add('nav-closed');
  }
}

function toggleFocus(force) {
  const next =
    typeof force === 'boolean'
      ? force
      : !elements.body.classList.contains('focus-mode');
  elements.body.classList.toggle('focus-mode', next);
  $('#focusButton').setAttribute('aria-pressed', String(next));
  if (next) {
    elements.body.classList.add('notes-closed', 'nav-closed');
  }
  syncMobileScrim();
}

function syncMobileScrim() {
  if (window.innerWidth > 900 || elements.body.classList.contains('focus-mode')) {
    elements.mobileScrim.style.display = 'none';
    return;
  }
  const visible =
    !elements.body.classList.contains('nav-closed') ||
    !elements.body.classList.contains('notes-closed');
  elements.mobileScrim.style.display = visible ? 'block' : 'none';
}

function updatePage(page, { fromPdf = false } = {}) {
  const next = Math.min(Math.max(1, Number(page) || 1), Math.max(1, reader.total));
  reader.page = next;
  elements.pageInput.value = String(next);
  elements.pageInput.max = String(Math.max(1, reader.total));
  elements.notePageLabel.textContent = `第 ${next} 页`;
  elements.progressText.textContent = reader.total
    ? `第 ${next} / ${reader.total} 页`
    : `第 ${next} 页`;
  elements.readingProgressBar.style.width = `${
    reader.total ? Math.max(2, (next / reader.total) * 100) : 0
  }%`;
  $$('.page-thumbnail').forEach((button) => {
    button.classList.toggle('is-active', Number(button.dataset.page) === next);
  });
  $$('.outline-item').forEach((button) => {
    button.classList.remove('is-active');
  });
  const activeOutline = [...$$('.outline-item')]
    .filter((button) => Number(button.dataset.page) <= next)
    .at(-1);
  activeOutline?.classList.add('is-active');
  if (!fromPdf && reader.app) {
    reader.app.page = next;
  }
}

function goToPage(page) {
  updatePage(page);
  reader.app?.pdfViewer?.currentPageNumber;
  if (reader.app) reader.app.page = reader.page;
}

function changeZoom(factor) {
  const app = reader.app;
  if (!app?.pdfViewer) return;
  const current = Number(app.pdfViewer.currentScale) || 1;
  app.pdfViewer.currentScale = Math.min(3.5, Math.max(0.35, current * factor));
}

function fitWidth() {
  if (!reader.app?.pdfViewer) return;
  reader.app.pdfViewer.currentScaleValue = 'page-width';
}

function injectViewerStyles() {
  const doc = elements.viewer.contentDocument;
  if (!doc || $('#paper-reader-overrides', doc)) return;
  const style = doc.createElement('style');
  style.id = 'paper-reader-overrides';
  style.textContent = `
    #outerContainer, #mainContainer { top: 0 !important; height: 100% !important; }
    #toolbarContainer, #secondaryToolbar, #sidebarContainer, #findbar,
    #loadingBar, #loadingBar .progress, .doorHanger, .dialogButton {
      display: none !important;
    }
    #viewerContainer {
      inset: 0 !important;
      padding-top: 0 !important;
      background: #edf0f3 !important;
    }
    #viewerContainer > #viewer.pdfViewer { padding-top: 12px !important; }
    .pdfViewer .page {
      margin: 14px auto !important;
      border: 0 !important;
      box-shadow: 0 8px 34px rgb(25 31 45 / 12%) !important;
    }
    .pdfViewer .page .loadingIcon {
      background-color: #f7f8fa !important;
    }
    #viewerContainer::-webkit-scrollbar { width: 10px; }
    #viewerContainer::-webkit-scrollbar-thumb {
      border: 3px solid #edf0f3;
      border-radius: 8px;
      background: #c8ccd4;
    }
  `;
  doc.head.append(style);
  const nativeChrome = [
    '#toolbarContainer',
    '#secondaryToolbar',
    '#sidebarContainer',
    '#findbar',
    '#loadingBar',
  ];
  for (const selector of nativeChrome) {
    const element = doc.querySelector(selector);
    if (element) element.style.setProperty('display', 'none', 'important');
  }
  for (const selector of ['#outerContainer', '#mainContainer']) {
    const element = doc.querySelector(selector);
    if (element) element.style.setProperty('top', '0', 'important');
  }
  const viewerContainer = doc.querySelector('#viewerContainer');
  if (viewerContainer) {
    viewerContainer.style.setProperty('inset', '0', 'important');
    viewerContainer.style.setProperty('padding-top', '0', 'important');
    viewerContainer.style.setProperty('background', '#edf0f3', 'important');
  }
  doc.documentElement.style.background = '#edf0f3';
  doc.body.style.background = '#edf0f3';
}

async function flattenOutline(items, depth = 0) {
  const rows = [];
  for (const item of items || []) {
    let page = 1;
    try {
      const destination =
        typeof item.dest === 'string'
          ? await reader.app.pdfDocument.getDestination(item.dest)
          : item.dest;
      if (destination?.[0]) {
        page = (await reader.app.pdfDocument.getPageIndex(destination[0])) + 1;
      }
    } catch {
      page = reader.page;
    }
    const title = Array.isArray(item.title) ? item.title.join('') : String(item.title || '');
    if (title.trim()) {
      rows.push({ title: title.trim(), page, depth, dest: item.dest });
    }
    if (item.items?.length) {
      rows.push(...(await flattenOutline(item.items, depth + 1)));
    }
  }
  return rows;
}

function renderOutline() {
  const container = elements.navigationContent;
  container.replaceChildren();
  if (!reader.outline.length) {
    const empty = document.createElement('div');
    empty.className = 'panel-empty';
    empty.innerHTML =
      '这份 PDF 没有可识别的目录。<br />切换到“页面”可按缩略图浏览。';
    container.append(empty);
    return;
  }
  const fragment = document.createDocumentFragment();
  for (const item of reader.outline.slice(0, 300)) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `outline-item outline-level-${Math.min(4, item.depth + 1)}`;
    button.dataset.page = String(item.page);
    button.title = `${item.title} · 第 ${item.page} 页`;
    const number = document.createElement('span');
    number.textContent = String(item.page);
    const label = document.createElement('span');
    label.textContent = item.title;
    button.append(number, label);
    button.addEventListener('click', () => {
      try {
        reader.app.pdfLinkService.goToDestination(item.dest);
      } catch {
        goToPage(item.page);
      }
      if (window.innerWidth <= 900) {
        elements.body.classList.add('nav-closed');
        syncMobileScrim();
      }
    });
    fragment.append(button);
  }
  container.append(fragment);
  updatePage(reader.page, { fromPdf: true });
}

async function renderThumbnails() {
  if (
    reader.thumbnailsRendered ||
    !reader.app?.pdfDocument ||
    reader.navigation !== 'pages'
  ) {
    return;
  }
  reader.thumbnailsRendered = true;
  const container = elements.navigationContent;
  container.replaceChildren();
  const grid = document.createElement('div');
  grid.className = 'page-grid';
  container.append(grid);
  const limit = Math.min(reader.total, 100);
  for (let pageNumber = 1; pageNumber <= limit; pageNumber += 1) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'page-thumbnail';
    button.dataset.page = String(pageNumber);
    const canvas = document.createElement('canvas');
    canvas.width = 110;
    canvas.height = 148;
    canvas.style.aspectRatio = '0.74';
    const label = document.createElement('span');
    label.textContent = String(pageNumber);
    button.append(canvas, label);
    button.addEventListener('click', () => {
      goToPage(pageNumber);
      if (window.innerWidth <= 900) {
        elements.body.classList.add('nav-closed');
        syncMobileScrim();
      }
    });
    grid.append(button);
  }
  updatePage(reader.page, { fromPdf: true });
  for (const button of $$('.page-thumbnail', grid)) {
    if (!elements.navigationContent.isConnected) return;
    try {
      const page = await reader.app.pdfDocument.getPage(Number(button.dataset.page));
      const viewport = page.getViewport({ scale: 0.2 });
      const canvas = $('canvas', button);
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.ceil(viewport.width * ratio);
      canvas.height = Math.ceil(viewport.height * ratio);
      canvas.style.aspectRatio = `${viewport.width} / ${viewport.height}`;
      const context = canvas.getContext('2d', { alpha: false });
      await page.render({
        canvasContext: context,
        viewport,
        transform: ratio !== 1 ? [ratio, 0, 0, ratio, 0, 0] : undefined,
      }).promise;
      page.cleanup();
    } catch {
      $('canvas', button).style.background = '#f1f2f4';
    }
  }
  if (reader.total > limit) {
    const note = document.createElement('p');
    note.className = 'panel-empty';
    note.textContent = `为保证流畅，仅显示前 ${limit} 页缩略图。`;
    container.append(note);
  }
}

function setNavigation(name) {
  reader.navigation = name;
  $$('.panel-tab').forEach((button) => {
    button.classList.toggle('is-active', button.dataset.navigation === name);
  });
  if (name === 'pages') renderThumbnails();
  else renderOutline();
}

async function onDocumentLoaded() {
  if (reader.documentReady) return;
  const app = reader.app;
  if (!app?.pdfDocument) return;
  reader.documentReady = true;
  reader.total = app.pagesCount || app.pdfDocument.numPages || 1;
  elements.pageCount.textContent = String(reader.total);
  $('#coverPageCount').textContent = String(reader.total);
  elements.viewerLoading.classList.add('is-hidden');
  elements.pageInput.max = String(reader.total);
  updatePage(app.pdfViewer?.currentPageNumber || reader.page, {
    fromPdf: true,
  });
  try {
    reader.outline = await flattenOutline(await app.pdfDocument.getOutline());
  } catch {
    reader.outline = [];
  }
  renderOutline();
  setSaveState('saved', '已自动保存');
}

function bindPdfViewer() {
  const app = elements.viewer.contentWindow?.PDFViewerApplication;
  if (!app) return;
  reader.app = app;
  injectViewerStyles();
  app.eventBus?.on?.('documentloaded', onDocumentLoaded);
  app.eventBus?.on?.('pagechanging', (event) => {
    updatePage(event.pageNumber || app.page || 1, { fromPdf: true });
    saveProgress(900);
  });
  app.eventBus?.on?.('scalechanging', (event) => {
    const scale = event.scale || app.pdfViewer?.currentScale || 1;
    elements.zoomValue.textContent = `${Math.round(scale * 100)}%`;
  });
  elements.viewer.contentDocument?.addEventListener('keydown', handleShortcut);
  if (app.pdfDocument) onDocumentLoaded();
}

function handleShortcut(event) {
  const target = event.target;
  const typing =
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLInputElement ||
    target?.isContentEditable;
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'n') {
    event.preventDefault();
    toggleNotes(false);
    elements.noteText.focus();
    return;
  }
  if (typing && !event.altKey) return;
  if (event.key === 'Escape') {
    if (elements.body.classList.contains('focus-mode')) {
      toggleFocus(false);
    } else if (window.innerWidth <= 900) {
      elements.body.classList.add('nav-closed', 'notes-closed');
      syncMobileScrim();
    }
    return;
  }
  if (event.key.toLowerCase() === 'f' && !event.ctrlKey && !event.metaKey) {
    event.preventDefault();
    toggleFocus();
    return;
  }
  if (['ArrowUp', 'PageUp'].includes(event.key)) {
    event.preventDefault();
    goToPage(reader.page - 1);
  } else if (['ArrowDown', 'PageDown', ' '].includes(event.key)) {
    event.preventDefault();
    goToPage(reader.page + 1);
  } else if (event.key === 'Home') {
    event.preventDefault();
    goToPage(1);
  } else if (event.key === 'End') {
    event.preventDefault();
    goToPage(reader.total);
  } else if (['+', '='].includes(event.key)) {
    changeZoom(1.12);
  } else if (event.key === '-') {
    changeZoom(0.89);
  }
}

function bindControls() {
  $('#backButton').addEventListener('click', () => {
    persistImmediately();
    if (history.length > 1) history.back();
    else window.close();
  });
  $('#toggleNav').addEventListener('click', () => toggleNavigation());
  $('#toggleNotes').addEventListener('click', () => toggleNotes());
  $('#closeNav').addEventListener('click', () => toggleNavigation(false));
  $('#closeNotes').addEventListener('click', () => toggleNotes(false));
  $('#focusButton').addEventListener('click', () => toggleFocus());
  elements.mobileScrim.addEventListener('click', () => {
    elements.body.classList.add('nav-closed', 'notes-closed');
    syncMobileScrim();
  });
  $('#previousPage').addEventListener('click', () => goToPage(reader.page - 1));
  $('#nextPage').addEventListener('click', () => goToPage(reader.page + 1));
  elements.pageInput.addEventListener('change', () => goToPage(elements.pageInput.value));
  elements.pageInput.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      goToPage(elements.pageInput.value);
      elements.pageInput.blur();
    }
  });
  $('#zoomIn').addEventListener('click', () => changeZoom(1.12));
  $('#zoomOut').addEventListener('click', () => changeZoom(0.89));
  $('#fitWidth').addEventListener('click', fitWidth);
  elements.zoomValue.addEventListener('click', fitWidth);
  elements.noteText.addEventListener('input', () => {
    updateNoteMetrics();
    saveProgress();
  });
  $('#insertPageHeading').addEventListener('click', () => {
    insertAtCursor(`\n\n## 第 ${reader.page} 页\n\n`);
  });
  $$('[data-note-prompt]').forEach((button) => {
    button.addEventListener('click', () => {
      const value = button.dataset.notePrompt || '';
      insertAtCursor(`${elements.noteText.value.trim() ? '\n\n' : ''}${value}`);
    });
  });
  $$('.panel-tab').forEach((button) => {
    button.addEventListener('click', () => setNavigation(button.dataset.navigation));
  });
  $('#retryButton').addEventListener('click', () => boot());
  document.addEventListener('keydown', handleShortcut);
  window.addEventListener('resize', syncMobileScrim);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') persistImmediately();
  });
  window.addEventListener('pagehide', persistImmediately);
}

function fillDocumentDetails(resource) {
  elements.title.textContent = resource.title || '未命名论文';
  document.title = `${resource.title || '论文阅读'} · 研途`;
  elements.summaryTitle.textContent = resource.title || '未命名论文';
  elements.summaryDescription.textContent = resource.description || '论文说明尚未填写';
  elements.owner.textContent = resource.owner || '资料维护人';
  elements.fileMeta.textContent = `${formatBytes(resource.size)} · v${resource.version || 1}`;
  $('#detailFileName').textContent = resource.fileName || resource.title || '—';
  $('#detailFileSize').textContent = formatBytes(resource.size);
  $('#detailVersion').textContent = `v${resource.version || 1}`;
  $('#detailVisibility').textContent = visibilityName(resource.visibility);
  $('#downloadLink').href = `/api/v1/resources/${encodeURIComponent(id)}/download`;
  $('#downloadLink').setAttribute('download', resource.fileName || '');
}

async function boot() {
  elements.errorState.hidden = true;
  if (!id) throw new Error('缺少资料编号');
  try {
    const [resource, progress] = await Promise.all([
      api(`/resources/${encodeURIComponent(id)}`),
      api(`/resources/${encodeURIComponent(id)}/reading-progress`),
    ]);
    if (resource.previewType !== 'application/pdf') {
      throw new Error('当前阅读工作台仅支持 PDF 论文');
    }
    reader.resource = resource;
    reader.progress = progress || {};
    fillDocumentDetails(resource);
    elements.noteText.value = reader.progress.notes || '';
    updateNoteMetrics();
    reader.page = Math.max(1, Number(reader.progress.page) || 1);
    updatePage(reader.page, { fromPdf: true });
    const file = encodeURIComponent(
      `/api/v1/resources/${encodeURIComponent(id)}/preview`,
    );
    elements.viewer.src = `/pdfjs/web/viewer.html?file=${file}#page=${reader.page}`;
  } catch (error) {
    showError(error);
  }
}

function initializeLayout() {
  if (window.innerWidth <= 900) {
    elements.body.classList.add('nav-closed', 'notes-closed');
  }
  syncMobileScrim();
}

bindControls();
initializeLayout();
elements.viewer.addEventListener('load', bindPdfViewer);
boot().catch(showError);
