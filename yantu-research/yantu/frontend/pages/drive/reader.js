const params = new URLSearchParams(location.search),
  id = params.get('id'),
  viewer = document.querySelector('#viewer'),
  title = document.querySelector('#title'),
  status = document.querySelector('#status'),
  notes = document.querySelector('#notes'),
  noteText = document.querySelector('#noteText'),
  noteStatus = document.querySelector('#noteStatus');
async function api(path, method = 'GET', body) {
  const response = await fetch('/api/v1' + path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
    credentials: 'same-origin',
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.message || '无法打开论文');
  return result.data;
}
let lastPage = 0,
  saveTimer;
function save(values) {
  clearTimeout(saveTimer);
  noteStatus.textContent = '保存中…';
  saveTimer = setTimeout(async () => {
    try {
      await api(`/resources/${encodeURIComponent(id)}/reading-progress`, 'PATCH', values);
      noteStatus.textContent = '已自动保存';
    } catch {
      noteStatus.textContent = '保存失败';
    }
  }, 500);
}
async function boot() {
  if (!id) throw new Error('缺少资料编号');
  const [resource, progress] = await Promise.all([
    api(`/resources/${encodeURIComponent(id)}`),
    api(`/resources/${encodeURIComponent(id)}/reading-progress`),
  ]);
  if (resource.previewType !== 'application/pdf') throw new Error('全屏阅读器当前用于 PDF 论文');
  title.textContent = resource.title;
  document.title = `${resource.title} · 研途`;
  noteText.value = progress.notes || '';
  lastPage = Math.max(1, Number(progress.page) || 1);
  const file = encodeURIComponent(`/api/v1/resources/${encodeURIComponent(id)}/preview`);
  viewer.src = `/pdfjs/web/viewer.html?file=${file}#page=${lastPage}`;
  status.textContent = `上次读到第 ${lastPage} 页`;
  noteText.addEventListener('input', () => save({ notes: noteText.value, page: lastPage }));
  viewer.addEventListener('load', () =>
    setInterval(() => {
      try {
        const page = viewer.contentWindow.PDFViewerApplication?.pdfViewer?.currentPageNumber;
        if (page && page !== lastPage) {
          lastPage = page;
          status.textContent = `正在阅读第 ${page} 页`;
          save({ page, notes: noteText.value });
        }
      } catch {}
    }, 1000),
  );
}
document
  .querySelector('#toggleNotes')
  .addEventListener('click', () => notes.classList.toggle('hidden'));
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden' && id)
    fetch(`/api/v1/resources/${encodeURIComponent(id)}/reading-progress`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ page: lastPage, notes: noteText.value }),
      credentials: 'same-origin',
      keepalive: true,
    }).catch(() => {});
});
boot().catch((error) => {
  title.textContent = error.message;
  status.textContent = '打开失败';
});
