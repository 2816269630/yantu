import { icon } from '../../components/icons.js';
import { avatar, btn, empty, head, link, tag } from '../../components/ui.js';
import { api, list } from '../../core/api.js';
import { date, datetime, enc, esc } from '../../core/format.js';
import { isManager, pages, state, statusColors, statusNames, teamUrl } from '../../core/state.js';
import { taskRow } from '../collaboration/tasks.js';

pages.home = async () => {
  const [d, tasks, plans, meetings] = await Promise.all([
    api(`/me/dashboard?teamId=${enc(state.team.id)}`),
    list(`/me/tasks?teamId=${enc(state.team.id)}`),
    list(`/me/enrollments?teamId=${enc(state.team.id)}`),
    list(teamUrl('/meetings')),
  ]);
  state.data.tasks = tasks;
  const current = tasks.find((t) => t.id === d.currentTask?.id);
  const next =
    d.nextMeeting ||
    meetings
      .filter((m) => new Date(m.startsAt) > Date.now())
      .sort((a, b) => a.startsAt.localeCompare(b.startsAt))[0];
  const progress = plans.reduce(
    (total, p) => ({
      completed: total.completed + (p.progress?.completed || 0),
      total: total.total + (p.progress?.total || 0),
    }),
    { completed: 0, total: 0 },
  );
  const ratio = progress.total ? Math.round((progress.completed / progress.total) * 100) : 0;
  return (
    head(
      `你好，${state.user.displayName}`,
      '从一个具体问题开始，让每一步都有反馈。',
      `<span class="welcome-date">${date(new Date(), { year: 'numeric', weekday: 'long' })}</span>`,
    ) +
    `<div class="grid2"><div class="stack"><section class="panel padded focus">${current ? `<div class="between"><span class="flex blue small">${icon('target')}下一步，做这件事</span>${tag(statusNames[current.status], statusColors[current.status])}</div><h2>${esc(current.title)}</h2><p>${esc(current.description || '先确认完成标准，留下自己的判断与待讨论问题。')}</p><div class="deliverable">${icon('file')}<span>${esc(current.acceptanceCriteria || '进入任务查看产出要求与参考资料')}</span></div><div class="between">${link('继续当前任务 ' + icon('arrow'), 'task/' + enc(current.id), 'btn primary')}<span class="flex small">${avatar(current.reviewer, 'mint')}${esc(current.reviewer)}将为你反馈</span></div>` : empty('准备开始一段新的探索', '加入一条学习路线，或请前辈为你安排第一个任务。', link('浏览学习路线 ' + icon('arrow'), 'routes', 'btn primary'), 'target')}</section><section class="panel padded"><div class="between"><div><h2>我的学习进度</h2><p class="small">以反馈确认的阶段为准，按自己的节奏推进。</p></div>${link('我的计划 ' + icon('right'), 'plans')}</div><div class="home-progress"><strong>${progress.completed} <span class="small">/ ${progress.total} 个阶段</span></strong><div class="progress"><span style="width:${Math.max(0, Math.min(100, ratio))}%"></span></div></div>${plans
      .slice(0, 3)
      .map(
        (p) =>
          `<div class="row">${icon('route')}<div class="row-main">${link(esc(p.title), 'plan/' + enc(p.id))}<p>${p.status === 'paused' ? '已暂停' : '正在学习'} · 路线版本 ${esc(p.routeVersion || 1)}</p></div>${icon('right')}</div>`,
      )
      .join(
        '',
      )}${!plans.length ? '<p class="small">还没有学习计划。选择合适的路线后，任务会自动建立。</p>' : ''}</section><section class="panel"><div class="panelhead"><h2>我的待办 ${tag(tasks.filter((t) => t.status !== 'done').length)}</h2>${link('全部任务 ' + icon('right'), 'tasks')}</div>${
      tasks.some((t) => t.status !== 'done')
        ? tasks
            .filter((t) => t.status !== 'done')
            .slice(0, 5)
            .map(taskRow)
            .join('')
        : empty('暂时没有待办任务', '可以从一条路线开始。', '', 'tasks')
    }</section></div><aside class="stack"><section class="panel padded"><h2>待我反馈 ${tag(d.reviewCount || 0)}</h2><p class="small mt16">需要你审阅的任务会显示在科研协作中。</p>${link('查看待我反馈', 'tasks/review', 'btn mt16')}</section><section class="panel padded"><div class="between mb16"><h2>下一次组会</h2>${icon('calendar')}</div>${next ? `<div class="flex"><div class="meeting-date"><div class="month">${date(next.startsAt, { month: 'short', day: undefined })}</div><div class="day">${new Date(next.startsAt).getDate()}</div></div><div><h3>${esc(next.title)}</h3><p class="small">${datetime(next.startsAt)}</p><p class="small">${esc(next.location || '')}</p></div></div><div class="divider"></div><p class="section-note mb16">会前准备材料与讨论问题，会后把反馈转成下一步行动。</p>${link('进入组会空间 ' + icon('arrow'), 'meeting/' + enc(next.id), 'btn wfull')}` : empty('暂无近期组会', '组会创建后，将在这里显示。', isManager() ? btn('安排组会', 'create-meeting') : '', 'calendar')}</section><section class="panel padded"><div class="flex mb8">${icon('spark')}<h3>从组内经验里找线索</h3></div><p class="section-note">围绕论文、组会和实践记录检索资料，为每一条回答保留出处。</p>${link('问问科研助手 ' + icon('arrow'), 'assistant', 'textbutton mt16')}</section><section class="panel padded"><div class="flex mb8">${icon('people')}<h3>让经验持续传承</h3></div><p class="section-note">记录当时的条件、失败尝试与判断，给后来者一个更清楚的起点。</p>${link('阅读前辈经验 ' + icon('arrow'), 'experiences', 'textbutton mt16')}</section></aside></div>`
  );
};
