import { icon } from './icons.js';
import { link } from './ui.js';
import { enc, esc } from '../core/format.js';

function resourceLinks(items) {
  return items?.length
    ? `<div class="detail-list">${items.map((r) => link(`${icon('file')}<span>${esc(r.title)}</span>${icon('right')}`, 'resource/' + enc(r.id), 'list-link')).join('')}</div>`
    : '<p class="small">暂无关联资料</p>';
}
export { resourceLinks };
