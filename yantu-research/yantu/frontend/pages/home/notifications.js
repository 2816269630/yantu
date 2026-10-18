import { icon } from '../../components/icons.js';
import { btn, empty, head, tag } from '../../components/ui.js';
import { api, list } from '../../core/api.js';
import { $ } from '../../core/dom.js';
import { datetime, enc, esc } from '../../core/format.js';
import { pages, state } from '../../core/state.js';

pages.notifications = async () => {
  const items = await list(
    '/me/notifications' + (state.team ? `?teamId=${enc(state.team.id)}` : ''),
  );
  state.data.notifications = items;
  return (
    head('通知', '产出提交、反馈与课题组动态都在这里。', btn('全部标为已读', 'read-all')) +
    `<section class="panel">${items.length ? items.map((n) => `<div class="row">${icon(n.read ? 'check' : 'bell')}<div class="row-main"><h3>${esc(n.title)}</h3><p>${datetime(n.createdAt)}</p></div>${!n.read ? btn('标为已读', 'read-notification', n.id, 'sm') : tag('已读')}</div>`).join('') : empty('暂时没有新通知', '有任务提交、反馈或空间动态时，会在这里提醒你。', '', 'bell')}</section>`
  );
};

async function refreshNotifications() {
  if (!state.user) return;
  const items = await api(
    '/me/notifications?pageSize=100' + (state.team ? `&teamId=${enc(state.team.id)}` : ''),
  );
  const count = items.items.filter((n) => !n.read).length;
  $('#notificationsButton').innerHTML =
    icon('bell') + (count ? '<span class="unread-dot"></span>' : '');
  $('#notificationsButton').setAttribute('aria-label', `通知${count ? `，${count} 条未读` : ''}`);
}
export { refreshNotifications };
