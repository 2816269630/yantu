import { showAuth } from './session.js';
import { resetSession } from './session-state.js';
import { state } from './state.js';

async function api(path, method = 'GET', body, binary = false) {
  const headers =
    body instanceof FormData
      ? {}
      : body === undefined
        ? {}
        : { 'Content-Type': 'application/json' };
  const response = await fetch('/api/v1' + path, {
    method,
    credentials: 'same-origin',
    headers,
    body: body === undefined ? undefined : body instanceof FormData ? body : JSON.stringify(body),
  });
  if (response.ok && binary) return response;
  const result = await response.json().catch(() => null);
  if (!response.ok) {
    const err = new Error(result?.message || `请求未完成（${response.status}）`);
    err.status = response.status;
    if (response.status === 401 && state.user) {
      resetSession();
      showAuth('login');
    }
    throw err;
  }
  if (!result || !Object.hasOwn(result, 'data'))
    throw new Error('服务返回了无法读取的数据，请刷新后重试。');
  return result.data;
}

async function list(path) {
  const items = [];
  let page = 1,
    total = 0;
  do {
    const r = await api(`${path}${path.includes('?') ? '&' : '?'}page=${page}&pageSize=100`);
    items.push(...(r.items || []));
    total = r.total ?? items.length;
    if (!(r.items || []).length) break;
    page++;
  } while (items.length < total && page <= 100);
  return items;
}

async function download(path, fallback = '研途导出') {
  const r = await api(path, 'GET', undefined, true);
  const b = await r.blob();
  const u = URL.createObjectURL(b);
  const a = document.createElement('a');
  a.href = u;
  const name = r.headers.get('Content-Disposition')?.match(/filename\*=UTF-8''([^;]+)/i);
  const asciiName = r.headers.get('Content-Disposition')?.match(/filename="?([^";]+)"?/i);
  a.download = name ? decodeURIComponent(name[1]) : asciiName ? asciiName[1] : fallback;
  a.click();
  setTimeout(() => URL.revokeObjectURL(u), 3000);
}
export { api, list, download };
