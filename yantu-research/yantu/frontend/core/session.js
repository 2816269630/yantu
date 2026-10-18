import { field } from '../components/forms.js';
import { icon } from '../components/icons.js';
import { renderShell } from '../components/sidebar.js';
import { btn, toast } from '../components/ui.js';
import { api, list } from './api.js';
import { $ } from './dom.js';
import { enc, esc } from './format.js';
import { renderPage } from './router.js';
import { state, teamUrl } from './state.js';
import { refreshNotifications } from '../pages/home/notifications.js';

async function refreshTeams(selected = state.team?.id) {
  state.teams = (await api('/me/teams')).items;
  state.team = state.teams.find((t) => t.id === selected) || state.teams[0] || null;
  $('#teamSelect').innerHTML = state.teams.length
    ? state.teams
        .map(
          (t) =>
            `<option value="${esc(t.id)}" ${t.id === state.team.id ? 'selected' : ''}>${esc(t.name)}</option>`,
        )
        .join('')
    : '<option value="">创建你的课题组</option>';
  state.members = state.team ? await list(teamUrl('/members')) : [];
  renderShell();
}

function showAuth(mode = 'login') {
  $('#appShell').hidden = true;
  $('#authRoot').hidden = false;
  const setup = mode === 'setup',
    register = mode === 'register';
  $('#authRoot').innerHTML =
    `<section class="auth-story"><div class="brand"><span class="brandmark">R</span><div><strong>研途</strong><span>RESEARCHPATH</span></div></div><h1>让每一步探索，<br>都有迹可循。</h1><p>从第一篇论文到第一次组会，把前辈的经验变成你自己的科研路径。</p><div class="auth-steps"><div class="auth-step"><span>01</span>沿着路线，找到清晰的起点</div><div class="auth-step"><span>02</span>记录实践，让问题得到反馈</div><div class="auth-step"><span>03</span>沉淀经验，与课题组一起成长</div></div></section><section class="auth-main"><div class="auth-card"><div class="brand login-logo"><span class="brandmark">R</span><strong>研途</strong></div><h2>${setup ? '开启你的科研空间' : register ? '加入研途' : '欢迎回到研途'}</h2><p>${setup ? '创建管理员账号与第一个课题组。' : register ? '使用受邀邮箱创建账号，加入课题组。' : '登录后，继续你的学习与研究。'}</p><form data-form="${setup ? 'setup' : register ? 'register' : 'login'}">${setup || register ? field('姓名', 'displayName', '', { required: true, max: 100, autocomplete: 'name' }) : ''}${field('邮箱', 'email', '', { type: 'email', required: true, autocomplete: 'username' })}${field('密码', 'password', '', { type: 'password', required: true, min: setup || register ? 12 : 1, autocomplete: setup || register ? 'new-password' : 'current-password', help: setup || register ? '请使用至少 12 位的密码。' : '' })}${setup ? field('课题组名称', 'teamName', '', { required: true, max: 100, placeholder: '例如：智能计算实验室' }) : ''}${register && !state.invite && !state.system.registrationOpen ? field('邀请令牌', 'invitationToken', '', { required: true, help: '由课题组负责人提供。' }) : ''}<div class="form-error" role="alert" hidden></div><button class="btn primary" type="submit">${setup ? '创建并进入工作台' : register ? '创建账号' : '登录'}${icon('arrow')}</button></form>${!setup ? `<div class="auth-links">${btn(register ? '已有账号，返回登录' : '使用邀请注册', register ? 'auth-login' : 'auth-register', '', 'textbutton')}</div>` : ''}<p class="auth-note">独立部署的科研协作空间<br>数据保存在你的本地环境</p></div></section>`;
}

async function enterApp() {
  state.user = await api('/me');
  await refreshTeams();
  if (state.invite) {
    try {
      const accepted = await api(`/invitations/${enc(state.invite)}/accept`, 'POST', {});
      await refreshTeams(accepted.teamId);
      toast('已加入受邀课题组');
    } catch (e) {
      toast(e.message, true);
    }
    state.invite = '';
    history.replaceState(null, '', location.pathname + location.hash);
  }
  await renderPage();
  refreshNotifications().catch(() => {});
}

async function boot() {
  try {
    state.system = await api('/system/status');
    if (!state.system.initialized) return showAuth('setup');
    try {
      await enterApp();
    } catch (e) {
      if (e.status === 401) showAuth(state.invite ? 'register' : 'login');
      else throw e;
    }
  } catch (e) {
    $('#appShell').hidden = false;
    $('#content').innerHTML =
      `<div class="errorbox">无法连接科研服务：${esc(e.message)}<br>${btn('重新连接', 'boot')}</div>`;
  }
}
export { refreshTeams, showAuth, enterApp, boot };
