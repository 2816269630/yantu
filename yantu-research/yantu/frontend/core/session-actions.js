import { api } from './api.js';
import { renderPage } from './router.js';
import { enterApp, refreshTeams, showAuth } from './session.js';
import { resetSession } from './session-state.js';
import { state } from './state.js';

async function handleSessionAction(action, id, source) {
  if (action === 'auth-login') return showAuth('login');
  if (action === 'auth-register') return showAuth('register');
  if (action === 'logout') {
    await api('/auth/logout', 'POST', {});
    resetSession();
    showAuth('login');
    return;
  }
}

async function submitSessionForm(type, data, id, formElement) {
  let result;
  if (type === 'setup') {
    result = await api('/auth/setup', 'POST', data);
    state.user = result.user;
    await refreshTeams(result.teamId);
    await renderPage();
  }
  if (type === 'login') {
    result = await api('/auth/login', 'POST', data);
    state.user = result.user;
    await enterApp();
  }
  if (type === 'register') {
    data.invitationToken = data.invitationToken || state.invite;
    await api('/auth/register', 'POST', data);
    const login = await api('/auth/login', 'POST', { email: data.email, password: data.password });
    state.user = login.user;
    await enterApp();
  }
}
export { handleSessionAction, submitSessionForm };
