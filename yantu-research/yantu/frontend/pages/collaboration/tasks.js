import { icon } from '../../components/icons.js';
import { resourceLinks } from '../../components/resources.js';
import { avatar, btn, empty, head, link, para, tag } from '../../components/ui.js';
import { api, list } from '../../core/api.js';
import { datetime, enc, esc, safeUrl } from '../../core/format.js';
import { isManager, isOwner, pages, state, statusColors, statusNames } from '../../core/state.js';

function taskRow(t) {
  return `<div class="row"><span class="checkcircle ${t.status === 'done' ? 'done' : t.status === 'blocked' ? 'orange' : t.status === 'doing' ? 'blue' : ''}">${t.status === 'done' ? '✓' : ''}</span><div class="row-main">${link(esc(t.title), 'task/' + enc(t.id), 'rowbutton')}<p>${esc(t.reviewer || '未指定反馈人')}${t.assignee ? ` · ${esc(t.assignee)}` : ''}</p></div>${tag(statusNames[t.status] || t.status, statusColors[t.status])}</div>`;
}

pages.tasks = async (view) => {
  const [mine, reviews] = await Promise.all([
    list(`/me/tasks?teamId=${enc(state.team.id)}`),
    isManager() ? list(`/me/review-queue?teamId=${enc(state.team.id)}`) : Promise.resolve([]),
  ]);
  state.data.tasks = mine;
  state.data.reviews = reviews;
  return (
    head(
      '任务与反馈',
      '用具体产出记录进展；让每个问题都有后续。',
      isManager() ? btn(icon('plus') + '创建任务', 'create-task', '', 'primary') : '',
    ) +
    `<div class="tabs"><button class="tab ${view === 'review' ? '' : 'active'}" data-action="task-tab" data-id="mine">我的任务 ${tag(mine.length)}</button><button class="tab ${view === 'review' ? 'active' : ''}" data-action="task-tab" data-id="review">待我反馈 ${tag(reviews.length)}</button></div><div id="taskBoard">${taskBoard(view === 'review' ? reviews : mine)}</div>`
  );
};

function taskBoard(items) {
  return `<div class="kanban">${Object.entries(statusNames)
    .map(
      ([status, title]) =>
        `<section class="kanban-col"><div class="kanban-head"><span>${title}</span>${tag(items.filter((t) => t.status === status).length)}</div>${
          items
            .filter((t) => t.status === status)
            .map(
              (t) =>
                `<a href="#task/${enc(t.id)}" class="taskcard">${tag(t.routeStageTitle || (t.meetingId ? '组会行动' : '科研任务'), statusColors[status])}<h3>${esc(t.title)}</h3><p>${esc(t.acceptanceCriteria || t.description || '查看任务要求与资料')}</p><div class="bottom"><span>反馈 · ${esc(t.reviewer)}</span>${avatar(t.reviewer, 'mint')}</div>${t.planeSync === 'failed' ? '<p class="task-owner danger-text">后台任务同步待重试</p>' : ''}</a>`,
            )
            .join('') || '<div class="empty-col">暂无任务</div>'
        }</section>`,
    )
    .join('')}</div>`;
}

pages.task = async (id) => {
  const t = await api(`/tasks/${enc(id)}`);
  state.data.task = t;
  const mine = t.assigneeId === state.user.id;
  const reviewable = t.status === 'review' && (t.reviewerId === state.user.id || isOwner());
  return (
    link(icon('back') + '返回任务与反馈', 'tasks', 'textbutton mb16') +
    head(
      t.title,
      `负责人：${t.assignee || state.user.displayName} · 反馈人：${t.reviewer}`,
      `${tag(statusNames[t.status], statusColors[t.status])}${mine && t.status !== 'done' ? btn('更新进度', 'task-progress', id) + btn(icon('upload') + '提交产出', 'submit-task', id, 'primary') : ''}`,
    ) +
    `<div class="grid2"><div class="stack"><section class="panel padded"><h2>这一步要解决什么？</h2><div class="rich-section">${para(t.description)}</div><h3>完成标准</h3><div class="deliverable rich-section">${para(t.acceptanceCriteria || '提交后由反馈人确认完成。')}</div>${t.blocker ? `<div class="notice"><strong>当前卡点</strong>${para(t.blocker)}</div>` : ''}<div class="between mb16"><h3>参考资料</h3>${btn('引用云盘资料', 'attach-task', id, 'sm')}</div>${resourceLinks(t.resources)}</section><section class="panel padded"><div class="between"><h2>产出与反馈</h2>${tag((t.submissions || []).length + ' 次提交')}</div>${
      (t.submissions || []).length
        ? [...t.submissions]
            .reverse()
            .map(
              (s, index) =>
                `<article class="submission"><div class="between mb16"><strong>第 ${t.submissions.length - index} 次产出</strong><span class="small">${datetime(s.createdAt)}</span></div>${para(s.summary)}${safeUrl(s.url) ? `<a class="textbutton mt16" href="${esc(safeUrl(s.url))}" target="_blank" rel="noopener noreferrer">打开成果链接 ↗</a>` : ''}${(s.reviews || []).map((r) => `<div class="feedback"><div class="between mb8"><strong>${r.decision === 'approved' ? '已确认完成' : '继续完善'}</strong><span>${datetime(r.createdAt)}</span></div>${para(r.comment)}</div>`).join('')}${reviewable && index === 0 && !s.reviews.length ? `<div class="form-actions">${btn('提交反馈', 'review-submission', s.id, 'primary')}</div>` : ''}</article>`,
            )
            .join('')
        : empty(
            '还没有提交产出',
            '整理已有进展，说明你最希望得到反馈的问题。',
            mine ? btn('提交第一次产出', 'submit-task', id, 'primary') : '',
            'file',
          )
    }</section></div><aside class="stack"><section class="panel padded"><h3>任务信息</h3><div class="factlist"><div><span>负责人</span><span>${esc(t.assignee || '本人')}</span></div><div><span>反馈人</span><span>${esc(t.reviewer)}</span></div><div><span>任务同步</span><span>${esc({ synced: '已同步', linked: '已同步', local: '本地保存', unlinked: '本地保存', not_configured: '本地保存', pending: '等待同步', retry_needed: '同步需重试', failed: '同步需重试' }[t.planeSync] || '本地保存')}</span></div></div>${t.planeSync === 'failed' && isManager() ? btn('重试同步', 'sync-task', id, 'mt16') : ''}</section><section class="panel padded"><h3>留下你的实践记录</h3><p class="section-note mt16">遇到困难时，记录现象、环境、已尝试的方法。它们同样是有价值的科研产出。</p>${mine ? btn('记录进展 / 卡点', 'task-progress', id, 'mt16') : ''}</section>${t.meetingId ? link(icon('calendar') + '查看关联组会', 'meeting/' + enc(t.meetingId), 'btn') : ''}</aside></div>`
  );
};
export { taskRow, taskBoard };
