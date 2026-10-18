import { icon } from '../../components/icons.js';
import { resourceLinks } from '../../components/resources.js';
import { avatar, btn, empty, head, link, tag } from '../../components/ui.js';
import { api, list } from '../../core/api.js';
import { enc, esc } from '../../core/format.js';
import { isManager, pages, state, teamUrl } from '../../core/state.js';

pages.routes = async () => {
  const routes = await list(teamUrl('/routes'));
  state.data.routes = routes;
  return (
    head(
      '学习路线',
      '参考前辈走过的路，按照自己的基础调整节奏。',
      isManager() ? btn(icon('plus') + '贡献路线', 'create-route', '', 'primary') : '',
    ) +
    `<div class="callout">${icon('route')}<div>路线提供起点和参考。先确认前置知识，再与前辈约定适合你的阶段目标。</div></div><div class="toolbar"><div class="filters">${['全部路线', '我的路线'].map((v, i) => `<button class="filter ${!i ? 'active' : ''}" data-action="route-filter" data-id="${i ? 'mine' : 'all'}">${v}</button>`).join('')}</div><input class="input local-search" data-filter="routes" aria-label="搜索路线" placeholder="搜索路线名称、方向…"></div><div id="routeCards" class="grid3">${routeCards(routes)}</div>`
  );
};

function routeCards(items) {
  return items.length
    ? items
        .map(
          (r, i) =>
            `<article class="panel routecard"><div class="between"><div class="routeicon ${['', 'purple', 'green'][i % 3]}">${icon('route')}</div>${tag(r.difficulty || '学习路线', i % 2 ? 'purple' : 'blue')}</div><div><h2>${esc(r.title)}</h2><p class="small">${esc(r.direction || '跨方向通用')}</p></div><p class="text-clamp">${esc(r.description || '从阶段目标、参考资料到任务产出，循序展开学习。')}</p><div class="meta"><span>${r.stageCount || 0} 个阶段</span><span>版本 ${esc(r.version || 1)}</span></div><div class="divider" style="margin:0"></div><div class="flex">${avatar(r.author, 'mint')}<span class="small">${esc(r.author)} · 路线维护</span></div>${link('查看路线 ' + icon('arrow'), 'route/' + enc(r.id), 'btn')}</article>`,
        )
        .join('')
    : `<div class="panel" style="grid-column:1/-1">${empty('还没有学习路线', '由前辈或负责人创建阶段、资料与完成标准。', isManager() ? btn('创建第一条路线', 'create-route', '', 'primary') : '', 'route')}</div>`;
}

pages.route = async (id) => {
  const r = await api(`/routes/${enc(id)}`);
  state.data.route = r;
  return (
    link(icon('back') + '返回学习路线', 'routes', 'textbutton mb16') +
    head(
      r.title,
      r.description || '把每个阶段的目标、资料和产出联系起来。',
      `${isManager() ? btn('编辑路线', 'edit-route', id) + btn('版本记录', 'route-versions', id) : ''}${btn(icon('plus') + '加入我的计划', 'enroll', id, 'primary')}`,
    ) +
    `<div class="grid2"><div class="timeline">${r.stages.map((s, i) => `<section class="timeline-item"><span class="timeline-num">${String(i + 1).padStart(2, '0')}</span><div class="timeline-body"><h2>${esc(s.title)}</h2><p>${esc(s.description)}</p><div class="rich-section"><h3>阶段任务与完成标准</h3>${s.tasks.length ? s.tasks.map((t) => `<div class="timeline-foot mb8"><strong>${esc(t.title)}</strong><p>${esc(t.acceptanceCriteria || '由反馈人确认完成')}</p></div>`).join('') : '<p class="small">本阶段暂未设置任务</p>'}</div><h3 class="mb16">参考资料</h3>${resourceLinks(s.resources)}</div></section>`).join('')}</div><aside class="stack"><section class="panel padded"><div class="flex">${avatar(r.author, 'mint')}<div><h3>${esc(r.author)}</h3><p class="small">路线维护人</p></div></div><div class="divider"></div><div class="factlist"><div><span>研究方向</span><span>${esc(r.direction || '通用')}</span></div><div><span>建议基础</span><span>${esc(r.difficulty || '未指定')}</span></div><div><span>当前版本</span><span>${esc(r.version || 1)}</span></div><div><span>阶段数量</span><span>${r.stages.length}</span></div></div></section><section class="panel padded"><h3>适合自己的节奏</h3><p class="section-note mt16">加入后会建立独立的学习计划与个人任务。公共路线更新时，你已有的产出和反馈会保留。</p>${link('查看我的计划 ' + icon('arrow'), 'plans', 'textbutton mt16')}</section></aside></div>`
  );
};
export { routeCards };
