const esc = (v) =>
  String(v ?? '').replace(
    /[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
  );

const enc = encodeURIComponent;

const date = (value, options = {}) =>
  value
    ? new Intl.DateTimeFormat('zh-CN', { month: 'short', day: 'numeric', ...options }).format(
        new Date(value),
      )
    : '未设置';

const datetime = (value) => date(value, { year: 'numeric', hour: '2-digit', minute: '2-digit' });

const bytes = (n) =>
  n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.ceil((n || 0) / 1024)} KB`;

const safeUrl = (value) => {
  try {
    const u = new URL(value, location.origin);
    return ['http:', 'https:'].includes(u.protocol) ? u.href : '';
  } catch {
    return '';
  }
};
export { esc, enc, date, datetime, bytes, safeUrl };
