import { icon } from '../../components/icons.js';
import { resourceLinks } from '../../components/resources.js';
import { btn, empty, head, link, para, tag } from '../../components/ui.js';
import { api, list } from '../../core/api.js';
import { date, datetime, enc, esc } from '../../core/format.js';
import { isManager, pages, state, teamUrl } from '../../core/state.js';

pages.meetings = async () => {
  const items = await list(teamUrl('/meetings'));
  state.data.meetings = items;
  const scheduled = items.filter((m) => (m.status || 'scheduled') === 'scheduled');
  const archived = items.filter((m) => m.status === 'archived');
  const next = scheduled
    .filter((m) => new Date(m.startsAt) >= Date.now())
    .sort((a, b) => a.startsAt.localeCompare(b.startsAt))[0];
  return (
    head(
      '组会空间',
      '把每次讨论留下来，让下一次行动有据可循。',
      isManager() ? btn(icon('plus') + '新建组会', 'create-meeting', '', 'primary') : '',
    ) +
    `<div class="statgrid"><div class="panel statbox">${icon('calendar')}<p>下一次组会</p><strong>${next ? date(next.startsAt) : '待安排'}</strong><small>${esc(next?.title || '等待新的讨论')}</small></div><div class="panel statbox">${icon('clock')}<p>待开展</p><strong>${scheduled.length} <span class="small">次</span></strong><small>提前准备问题与材料</small></div><div class="panel statbox">${icon('history')}<p>已归档</p><strong>${archived.length} <span class="small">次</span></strong><small>材料与反馈一起保留</small></div></div><div class="toolbar"><div class="filters">${[
      ['all', '全部'],
      ['scheduled', '待开展'],
      ['completed', '已完成'],
      ['archived', '已归档'],
    ]
      .map(
        ([v, l], i) =>
          `<button class="filter ${i ? '' : 'active'}" data-action="meeting-filter" data-id="${v}">${l}</button>`,
      )
      .join(
        '',
      )}</div><input class="input local-search" data-filter="meetings" aria-label="搜索组会" placeholder="查找组会主题…"></div><section class="panel" id="meetingCards">${meetingCards(items)}</section>`
  );
};

function meetingCards(items) {
  return items.length
    ? [...items]
        .sort((a, b) => b.startsAt.localeCompare(a.startsAt))
        .map(
          (m) =>
            `<article class="meeting-card"><div class="meeting-date"><div class="month">${date(m.startsAt, { month: 'short', day: undefined })}</div><div class="day">${new Date(m.startsAt).getDate()}</div></div><div class="middle"><div class="flex wrap mb8"><h3>${esc(m.title)}</h3>${tag({ scheduled: '待开展', completed: '已完成', archived: '已归档' }[m.status] || '待开展', m.status === 'archived' ? 'green' : 'blue')}</div><p>${datetime(m.startsAt)}</p><p>${esc(m.location)}</p>${m.agenda ? `<p class="text-clamp mt16">${esc(m.agenda)}</p>` : ''}</div>${link('查看详情 ' + icon('right'), 'meeting/' + enc(m.id), 'btn sm')}</article>`,
        )
        .join('')
    : empty(
        '暂时没有组会',
        '围绕研究问题组织一次讨论，材料与反馈会一起留下。',
        isManager() ? btn('安排第一次组会', 'create-meeting', '', 'primary') : '',
        'calendar',
      );
}

pages.meeting = async (id) => {
  const m = await api(`/meetings/${enc(id)}`);
  state.data.meeting = m;
  return (
    link(icon('back') + '返回组会空间', 'meetings', 'textbutton mb16') +
    head(
      m.title,
      `${datetime(m.startsAt)} · ${m.location}`,
      `${isManager() ? btn('编辑组会', 'edit-meeting', id) : ''}${btn('引用云盘资料', 'attach-meeting', id)}${btn(icon('upload') + '上传材料', 'meeting-upload', id, 'primary')}`,
    ) +
    `<div class="grid2"><div class="stack"><section class="panel padded"><h2>本次议程</h2><div class="rich-section">${para(m.agenda)}</div></section><section class="panel padded"><div class="between mb16"><h2>汇报材料</h2>${btn(icon('plus') + '添加材料', 'meeting-upload', id, 'sm')}</div>${m.resources.length ? resourceLinks(m.resources) : empty('汇报材料还未上传', '支持论文、汇报文稿和研究笔记。', '', 'file')}</section><section class="panel padded"><div class="between mb16"><h2>希望讨论的问题</h2>${btn(icon('plus') + '补充问题', 'meeting-question', id, 'sm')}</div>${(m.questions || []).length ? m.questions.map((q) => `<article class="submission"><div class="between mb8"><span class="small">${esc(q.author || q.authorName || '课题组成员')} · ${datetime(q.createdAt)}</span>${tag(q.status === 'resolved' ? '已回应' : '待讨论', q.status === 'resolved' ? 'green' : 'orange')}</div>${para(q.content)}${q.answer ? `<div class="feedback"><strong>讨论回应</strong>${para(q.answer)}</div>` : ''}${isManager() ? `<div class="form-actions">${btn(q.answer ? '编辑回应' : '记录回应', 'answer-meeting-question', q.id, 'sm')}</div>` : ''}</article>`).join('') : '<p class="small">写下一个具体问题，以及你目前的理解，让讨论更有针对性。</p>'}</section><section class="panel padded"><div class="between mb16"><h2>纪要与讨论结论</h2>${isManager() ? btn(m.minutes ? '编辑纪要' : '记录纪要', 'meeting-minutes', id, 'sm') : ''}</div>${m.minutes ? para(m.minutes.content) : empty('会后，把讨论变成下一步', '区分建议、已确认的决定与待验证假设。', '', 'message')}</section></div><aside class="stack"><section class="panel padded"><h2>后续行动项</h2><p class="section-note mt16 mb16">指定负责人、反馈人和完成标准，让下次组会能够追溯进展。</p>${(m.tasks || []).length ? m.tasks.map((t) => link(`${icon('tasks')}<span>${esc(t.title)}</span>${icon('right')}`, 'task/' + enc(t.id), 'list-link mb8')).join('') : '<p class="small mb16">尚无后续行动项</p>'}${isManager() ? btn(icon('plus') + '创建行动任务', 'meeting-task', id, 'wfull') : ''}</section><section class="panel padded"><h3>组会状态</h3><div class="mt16 mb16">${tag({ scheduled: '待开展', completed: '已完成', archived: '已归档' }[m.status] || '待开展', m.status === 'archived' ? 'green' : 'blue')}</div>${isManager() ? `<div class="section-actions">${m.status !== 'completed' && m.status !== 'archived' ? btn('标记已完成', 'meeting-complete', id, 'sm') : ''}${m.status !== 'archived' ? btn('归档组会', 'meeting-archive', id, 'sm') : ''}</div>` : ''}<p class="section-note mt16">组会材料按各自的可见范围保存。归档后仍可回看资料、纪要与任务。</p></section></aside></div>`
  );
};
export { meetingCards };
