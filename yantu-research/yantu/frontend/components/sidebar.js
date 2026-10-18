import { icon } from './icons.js';
import { avatar } from './ui.js';
import { $ } from '../core/dom.js';
import { esc } from '../core/format.js';
import { roles, state } from '../core/state.js';

function closeSidebar() {
  $('#sidebar').classList.remove('open');
  $('#overlay').classList.remove('visible');
  $('#menuToggle').setAttribute('aria-expanded', 'false');
}

function renderShell() {
  const navs = [
    ['home', 'home', '工作台'],
    ['plans', 'route', '学习成长'],
    ['tasks', 'tasks', '科研协作'],
    ['resources', 'folder', '我的云盘'],
    ['assistant', 'spark', '科研助手'],
  ];
  $('#nav').innerHTML = navs
    .map(([id, ic, title]) => `<a class="navitem" href="#${id}">${icon(ic)}${title}</a>`)
    .join('');
  $('#profile').innerHTML =
    `${avatar(state.user?.displayName)}<div style="flex:1"><strong>${esc(state.user?.displayName)}</strong><small>${esc(roles[state.team?.role] || '科研成员')}</small></div><button class="iconbtn" data-action="logout" aria-label="退出登录">${icon('logout')}</button>`;
  $('#profileButton').textContent = state.user?.displayName?.slice(0, 1) || '?';
  $('#authRoot').hidden = true;
  $('#appShell').hidden = false;
}
export { closeSidebar, renderShell };
