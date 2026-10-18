import { icon } from '../../components/icons.js';
import { empty, head, link, tag } from '../../components/ui.js';
import { api } from '../../core/api.js';
import { $ } from '../../core/dom.js';
import { enc, esc } from '../../core/format.js';
import { pages, state, teamUrl } from '../../core/state.js';

pages.search = async () => {
  const q = state.searchQuery || $('#searchInput').value.trim();
  if (!q)
    return (
      head('全站搜索', '输入关键词，查找有权访问的资料、任务、路线和组会。') +
      empty('你想找什么？', '使用右上方的搜索框开始查找。', '', 'search')
    );
  const r = await api(teamUrl('/search') + '?q=' + enc(q));
  const types = {
    resource: ['资料', 'resource'],
    task: ['任务', 'task'],
    route: ['路线', 'route'],
    meeting: ['组会', 'meeting'],
    experience: ['经验', 'experience'],
  };
  return (
    head('搜索结果', `“${q}” · 共 ${r.total} 条结果`) +
    `<section class="panel">${
      r.items.length
        ? r.items
            .map((i) => {
              const t = types[i.type] || ['内容', i.type];
              return `<div class="row">${icon(i.type === 'resource' ? 'file' : i.type === 'task' ? 'tasks' : i.type === 'meeting' ? 'calendar' : 'book')}<div class="row-main">${link(esc(i.title), t[1] + '/' + enc(i.id))}<p class="text-clamp">${esc(i.summary)}</p></div>${tag(t[0])}</div>`;
            })
            .join('')
        : empty(
            '没有找到相关内容',
            '试试更短的关键词，或确认内容是否属于当前课题组。',
            '',
            'search',
          )
    }</section>`
  );
};
