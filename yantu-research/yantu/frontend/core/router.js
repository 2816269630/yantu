import { icon } from '../components/icons.js';
import { closeSidebar } from '../components/sidebar.js';
import { btn, empty, link, loading } from '../components/ui.js';
import { $, $$ } from './dom.js';
import { esc } from './format.js';
import { pages, state } from './state.js';
import { initReadingProgress } from '../pages/drive/reading.js';

function navigate(to) {
  if (location.hash.slice(1) === to) renderPage();
  else location.hash = to;
}

const titles = {
  home: '工作台',
  routes: '学习路线',
  route: '路线详情',
  plans: '我的学习',
  plan: '学习计划',
  experiences: '前辈经验',
  experience: '经验详情',
  meetings: '组会空间',
  meeting: '组会详情',
  resources: '我的云盘',
  resource: '资料详情',
  tasks: '任务与反馈',
  task: '任务详情',
  progress: '研究记录',
  assistant: '科研助手',
  settings: '空间与权限',
  notifications: '通知',
  search: '全站搜索',
};

async function renderPage() {
  if (!state.user) return;
  saveListView();
  closeSidebar();
  const parts = location.hash.slice(1).split('/');
  const page = titles[parts[0]] ? parts[0] : 'home';
  state.page = page;
  state.detailId = parts[1] || '';
  const seq = ++state.sequence;
  $('#crumb').textContent = titles[page];
  document.title = `${titles[page]} · 研途`;
  const active =
    {
      route: 'plans',
      routes: 'plans',
      plan: 'plans',
      experiences: 'plans',
      experience: 'plans',
      meeting: 'tasks',
      meetings: 'tasks',
      progress: 'tasks',
      resource: 'resources',
      task: 'tasks',
    }[page] || page;
  $$('#nav .navitem').forEach((a) => {
    a.classList.toggle('active', a.hash === '#' + active);
    a.setAttribute('aria-current', a.hash === '#' + active ? 'page' : 'false');
  });
  $('#content').innerHTML = loading();
  if (
    !state.team &&
    !['settings', 'notifications', 'resources', 'resource', 'assistant'].includes(page)
  ) {
    $('#content').innerHTML =
      `<div class="panel empty-onboard">${empty('从一个课题组开始', '创建你的科研空间，或接受负责人的邀请。', btn(icon('plus') + '创建课题组', 'create-team', '', 'primary'), 'people')}</div>`;
    return;
  }
  try {
    const html = await pages[page](state.detailId);
    if (seq !== state.sequence) return;
    $('#content').innerHTML =
      sectionTabs(page) +
      html +
      '<footer><span>研途 ResearchPath · 科研入门与经验传承</span><span>让研究过程可记录、可协作、可传承</span></footer>';
    state.renderedHash = location.hash;
    restoreListView();
    initReadingProgress();
  } catch (e) {
    if (seq === state.sequence)
      $('#content').innerHTML =
        `<div class="errorbox" role="alert">${esc(e.message)}<br>${btn('重试', 'refresh')}</div>`;
  }
}

function sectionTabs(page) {
  const learning = ['plans', 'plan', 'routes', 'route', 'experiences', 'experience'];
  const research = ['tasks', 'task', 'progress', 'meetings', 'meeting'];
  const items = learning.includes(page)
    ? [
        ['plans', '我的学习'],
        ['routes', '学习路线'],
        ['experiences', '前辈经验'],
      ]
    : research.includes(page)
      ? [
          ['tasks', '任务与反馈'],
          ['progress', '研究记录'],
          ['meetings', '组会'],
        ]
      : [];
  const active =
    {
      plan: 'plans',
      route: 'routes',
      experience: 'experiences',
      task: 'tasks',
      meeting: 'meetings',
    }[page] || page;
  return items.length
    ? `<nav class="section-tabs" aria-label="模块导航">${items.map(([id, label]) => link(label, id, 'btn ' + (id === active ? 'primary' : ''))).join('')}</nav>`
    : '';
}

function saveListView() {
  if (!state.renderedHash) return;
  state.uiViews ||= {};
  state.uiViews[state.renderedHash] = {
    scroll: window.scrollY,
    inputs: $$('#content .local-search').map((x) => ({ filter: x.dataset.filter, value: x.value })),
    actions: $$('#content .filter.active,#content .tab.active').map((x) => ({
      action: x.dataset.action,
      id: x.dataset.id,
    })),
  };
}

function restoreListView() {
  const v = state.uiViews?.[location.hash];
  if (v) {
    for (const a of v.actions) {
      const el = $$('#content [data-action]').find(
        (x) => x.dataset.action === a.action && x.dataset.id === a.id,
      );
      el?.click();
    }
    for (const x of v.inputs) {
      const el = $$('#content .local-search').find((e) => e.dataset.filter === x.filter);
      if (el) {
        el.value = x.value;
        el.dispatchEvent(new Event('input', { bubbles: true }));
      }
    }
  }
  requestAnimationFrame(() => window.scrollTo(0, v?.scroll || 0));
}
export { navigate, titles, renderPage, sectionTabs, saveListView, restoreListView };
