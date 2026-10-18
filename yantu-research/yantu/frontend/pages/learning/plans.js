import { icon } from '../../components/icons.js';
import { resourceLinks } from '../../components/resources.js';
import { btn, empty, head, link, para, tag } from '../../components/ui.js';
import { api, list } from '../../core/api.js';
import { date, enc, esc } from '../../core/format.js';
import { pages, state } from '../../core/state.js';
import { taskRow } from '../collaboration/tasks.js';

pages.plans = async () => {
  const items = await list(`/me/enrollments?teamId=${enc(state.team.id)}`);
  return (
    head(
      '我的学习计划',
      '保留路线的起点，也记录你自己的调整。',
      link(icon('plus') + '选择路线', 'routes', 'btn primary'),
    ) +
    `<div class="grid3">${items.length ? items.map((p) => `<article class="panel routecard"><div class="between"><div class="routeicon">${icon('target')}</div>${tag(p.status === 'paused' ? '已暂停' : '学习中', p.status === 'paused' ? '' : 'blue')}</div><h2>${esc(p.title)}</h2><p>${esc(p.note || '从当前任务开始，持续记录产出与反馈。')}</p><div class="meta"><span>路线版本 ${esc(p.routeVersion || 1)}</span>${p.targetDate ? `<span>目标 ${date(p.targetDate)}</span>` : ''}</div>${p.progress ? `<div class="small">已完成 ${p.progress.completed} / ${p.progress.total} 个阶段</div>` : ''}${link('继续我的计划 ' + icon('arrow'), 'plan/' + enc(p.id), 'btn primary')}</article>`).join('') : `<section class="panel" style="grid-column:1/-1">${empty('你的探索，从这里开始', '先选择一条适合当前基础的路线，加入后即可开始任务。', link('选择学习路线', 'routes', 'btn primary'), 'target')}</section>`}</div>`
  );
};

pages.plan = async (id) => {
  const p = await api(`/enrollments/${enc(id)}`);
  state.data.plan = p;
  return (
    link(icon('back') + '返回我的计划', 'plans', 'textbutton mb16') +
    head(
      p.title,
      `基于路线版本 ${p.routeVersion} · ${p.status === 'paused' ? '已暂停' : '正在学习'}`,
      btn('调整计划', 'adjust-plan', id) + btn(icon('plus') + '补充学习任务', 'plan-task', id),
    ) +
    `<div class="grid2"><div class="timeline">${p.stages.map((s, i) => `<section class="timeline-item"><span class="timeline-num ${s.tasks.length && s.tasks.every((t) => t.status === 'done') ? 'done' : ''}">${i + 1}</span><div class="timeline-body"><h2>${esc(s.title)}</h2><p>${esc(s.description)}</p>${s.tasks.length ? s.tasks.map(taskRow).join('') : '<p class="small">本阶段暂无任务</p>'}<div class="rich-section">${resourceLinks(s.resources)}</div></div></section>`).join('')}</div><aside class="stack"><section class="panel padded"><h2>当前进度</h2><div class="home-progress mt16"><strong>${p.progress.completed} <span class="small">/ ${p.progress.total} 个阶段</span></strong><div class="progress"><span style="width:${p.progress.total ? Math.min(100, (p.progress.completed / p.progress.total) * 100) : 0}%"></span></div></div><div class="factlist"><div><span>计划完成</span><span>${p.targetDate ? date(p.targetDate, { year: 'numeric' }) : '按自己的节奏'}</span></div></div></section><section class="panel padded"><h3>个人调整说明</h3><div class="rich-section">${para(p.note || '还没有调整说明。你可以补充前置学习、目标日期与计划变更的原因。')}</div>${btn('修改说明', 'adjust-plan', id)}</section>${link('查看原始路线 ' + icon('right'), 'route/' + enc(p.routeId), 'btn')}</aside></div>`
  );
};
