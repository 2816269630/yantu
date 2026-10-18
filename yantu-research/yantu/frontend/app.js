import { showFormError } from './components/forms.js';
import { icon } from './components/icons.js';
import { closeModal } from './components/modal.js';
import { closeSidebar } from './components/sidebar.js';
import { loading, toast } from './components/ui.js';
import { handleAction, handleSubmit } from './core/actions.js';
import { $, $$ } from './core/dom.js';
import { navigate, renderPage } from './core/router.js';
import { boot, refreshTeams } from './core/session.js';
import { state } from './core/state.js';
import { meetingCards } from './pages/collaboration/meetings.js';
import { cloudSubmit } from './pages/drive/browser.js';
import { resourceRows } from './pages/drive/detail.js';
import { experienceCards } from './pages/learning/experiences.js';
import { routeCards } from './pages/learning/routes.js';
import './pages/assistant/index.js';
import './pages/collaboration/meetings.js';
import './pages/collaboration/progress.js';
import './pages/collaboration/tasks.js';
import './pages/drive/browser.js';
import './pages/drive/detail.js';
import './pages/home/index.js';
import './pages/home/notifications.js';
import './pages/home/search.js';
import './pages/learning/experiences.js';
import './pages/learning/plans.js';
import './pages/learning/routes.js';
import './pages/settings/index.js';

document.addEventListener('submit', async (event) => {
  if (!event.target.matches('form[data-form]')) return;
  event.preventDefault();
  const f = event.target;
  if (f.dataset.busy) return;
  f.dataset.busy = '1';
  const buttons = $$('button[type=submit]', f);
  buttons.forEach((b) => (b.disabled = true));
  try {
    if (typeof cloudSubmit === 'function' && (await cloudSubmit(f))) return;
    await handleSubmit(f);
  } catch (e) {
    showFormError(f, e);
  } finally {
    delete f.dataset.busy;
    buttons.forEach((b) => (b.disabled = false));
  }
});
document.addEventListener('click', (event) => {
  const target = event.target.closest('[data-action]');
  if (target?.matches('.filter')) {
    target.parentElement
      .querySelectorAll('.filter')
      .forEach((b) => b.classList.toggle('active', b === target));
  }
  if (target)
    handleAction(target.dataset.action, target.dataset.id || '', target).catch((e) =>
      toast(e.message, true),
    );
});
document.addEventListener('input', (event) => {
  if (!event.target.matches('.local-search')) return;
  const query = event.target.value.toLowerCase(),
    filter = event.target.dataset.filter;
  const items = (state.data[filter] || []).filter((item) =>
    JSON.stringify(item).toLowerCase().includes(query),
  );
  if (filter === 'routes') $('#routeCards').innerHTML = routeCards(items);
  if (filter === 'experiences') $('#experienceCards').innerHTML = experienceCards(items);
  if (filter === 'resources') $('#resourceRows').innerHTML = resourceRows(items);
  if (filter === 'meetings') $('#meetingCards').innerHTML = meetingCards(items);
});
window.addEventListener('hashchange', renderPage);
$('#closeModal').addEventListener('click', closeModal);
$('#overlay').addEventListener('click', closeSidebar);
$('#menuToggle').innerHTML = icon('menu');
$('#searchIcon').innerHTML = icon('search');
$('#spaceIcon').innerHTML = icon('layers');
$('#menuToggle').addEventListener('click', () => {
  const open = $('#sidebar').classList.toggle('open');
  $('#overlay').classList.toggle('visible', open);
  $('#menuToggle').setAttribute('aria-expanded', String(open));
});
$('#teamSelect').addEventListener('change', async (event) => {
  state.sequence++;
  state.data = {};
  state.uiViews = {};
  state.renderedHash = null;
  $('#content').innerHTML = loading();
  await refreshTeams(event.target.value);
  await renderPage();
});
$('#notificationsButton').addEventListener('click', () => navigate('notifications'));
$('#profileButton').addEventListener('click', () => {
  state.settingsTab = 'profile';
  navigate('settings');
});
$('#globalSearch').addEventListener('submit', (event) => {
  event.preventDefault();
  state.searchQuery = $('#searchInput').value.trim();
  if (state.searchQuery) navigate('search');
});
document.addEventListener('keydown', (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault();
    $('#searchInput').focus();
  }
});
document.addEventListener('input', (e) => {
  if (e.target.id === 'assistantSourceSearch') {
    const q = e.target.value.toLocaleLowerCase();
    $$('.source-check').forEach((x) => (x.hidden = !x.textContent.toLocaleLowerCase().includes(q)));
  }
});
document.addEventListener('change', (e) => {
  if (e.target.matches('input[name=source]')) {
    $('#assistantSelected').textContent =
      `已选择 ${$$('input[name=source]:checked').length} 份；本次仅检索勾选资料，空选择检索全部当前有权且可解析的文件`;
  }
});
document.addEventListener('dragover', (e) => {
  if (e.dataTransfer?.types.includes('Files')) e.preventDefault();
});
document.addEventListener('drop', (e) => {
  if (e.dataTransfer?.types.includes('Files')) e.preventDefault();
});
boot();
