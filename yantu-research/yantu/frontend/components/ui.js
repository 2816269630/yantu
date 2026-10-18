import { icon } from './icons.js';
import { $ } from '../core/dom.js';
import { esc } from '../core/format.js';
import { state } from '../core/state.js';

const tag = (v, color = '') => `<span class="tag ${esc(color)}">${esc(v)}</span>`;

const avatar = (v, color = '') =>
  `<span class="avatar ${esc(color)}">${esc(String(v || '?').slice(0, 1))}</span>`;

const btn = (label, action, id = '', kind = '') =>
  `<button type="button" class="btn ${kind}" data-action="${esc(action)}" data-id="${esc(id)}">${label}</button>`;

const link = (label, to, cls = 'textbutton') => `<a class="${cls}" href="#${esc(to)}">${label}</a>`;

const head = (title, desc, actions = '') =>
  `<div class="pagehead"><div><h1>${esc(title)}</h1><p>${esc(desc)}</p></div><div class="section-actions">${actions}</div></div>`;

const empty = (title, desc = '', action = '', name = 'folder') =>
  `<div class="empty"><div class="empty-icon">${icon(name)}</div><h3>${esc(title)}</h3><p>${esc(desc)}</p>${action}</div>`;

const loading = () => '<div class="loading" role="status">正在读取…</div>';

const para = (v) => `<div class="body-text">${esc(v || '暂无内容')}</div>`;

function toast(message, error = false) {
  clearTimeout(state.toastTimer);
  $('#toast').textContent = message;
  $('#toast').className = `toast visible${error ? ' error' : ''}`;
  state.toastTimer = setTimeout(() => $('#toast').classList.remove('visible'), 4500);
}
export { tag, avatar, btn, link, head, empty, loading, para, toast };
