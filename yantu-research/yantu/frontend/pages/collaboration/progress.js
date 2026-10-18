import { icon } from '../../components/icons.js';
import { avatar, btn, empty, head, para, tag } from '../../components/ui.js';
import { list } from '../../core/api.js';
import { datetime, esc } from '../../core/format.js';
import { isOwner, pages, state, teamUrl } from '../../core/state.js';

pages.progress = async () => {
  const items = await list(teamUrl('/progress'));
  state.data.progress = items;
  return (
    head(
      '研究记录与求助',
      '记录目标、观察与尝试，把卡点变成可以讨论的问题。',
      btn(icon('plus') + '记录进展', 'create-progress', '', 'primary') +
        btn('向课题组求助', 'create-help'),
    ) +
    `<div class="stack">${items.length ? items.map((p) => `<article class="panel padded"><div class="between mb16"><div class="flex">${avatar(p.author || p.authorName, 'mint')}<div><strong>${esc(p.author || p.authorName || '课题组成员')}</strong><p class="small">${datetime(p.createdAt)}</p></div></div><div class="flex">${tag(p.kind === 'help' ? '求助' : '进展', p.kind === 'help' ? 'orange' : 'blue')}${tag(p.status === 'resolved' ? '已解决' : '讨论中', p.status === 'resolved' ? 'green' : '')}</div></div>${para(p.content)}${p.blockers ? `<div class="notice mt16"><strong>遇到的困难</strong>${para(p.blockers)}</div>` : ''}${p.nextPlan ? `<div class="rich-section"><h3>下一步计划</h3>${para(p.nextPlan)}</div>` : ''}${(p.comments || []).map((c) => `<div class="feedback"><strong>${esc(c.author || c.authorName || '课题组成员')}</strong> <span class="small">${datetime(c.createdAt)}</span>${para(c.content)}</div>`).join('')}<div class="form-actions">${btn('回复讨论', 'comment-progress', p.id)}${(p.authorId === state.user.id || isOwner()) && p.status !== 'resolved' ? btn('标记已解决', 'resolve-progress', p.id, 'soft') : ''}</div></article>`).join('') : `<section class="panel">${empty('把今天的探索留下来', '一次观察、一段失败尝试，或一个需要帮助的问题，都值得记录。', btn('写下第一条记录', 'create-progress', '', 'primary'), 'message')}</section>`}</div>`
  );
};
