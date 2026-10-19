import { state } from './state.js';

const sessionCleanups = new Set();

// 各模块登记自己的清理函数，公共请求层无需依赖具体业务页面。
function registerSessionCleanup(cleanup) {
  sessionCleanups.add(cleanup);
  return () => sessionCleanups.delete(cleanup);
}

function resetSession() {
  Object.assign(state, {
    user: null,
    teams: [],
    team: null,
    members: [],
    data: {},
    uiViews: {},
    renderedHash: null,
    page: 'home',
    detailId: '',
    settingsTab: 'profile',
    filters: {},
    searchQuery: '',
  });
  for (const key of [
    'driveFolder',
    'driveView',
    'driveReturn',
    'referenceTarget',
    'uploadTarget',
    'returnFocus',
  ]) {
    delete state[key];
  }
  // 退出前发起的页面请求不能覆盖后续的登录界面。
  state.sequence++;
  for (const cleanup of sessionCleanups) cleanup();
}

export { registerSessionCleanup, resetSession };
