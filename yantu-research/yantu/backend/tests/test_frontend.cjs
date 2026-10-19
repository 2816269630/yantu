const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { JSDOM } = require('jsdom');
const root = path.resolve(__dirname, '../..');
const until = async (predicate) => {
  const start = Date.now();
  while (!predicate()) {
    if (Date.now() - start > 3000) throw new Error('页面未在预期时间内更新');
    await new Promise((r) => setTimeout(r, 10));
  }
};
async function main() {
  const dom = new JSDOM(fs.readFileSync(path.join(root, 'frontend/index.html'), 'utf8'), {
    url: 'http://localhost/#resources',
    runScripts: 'outside-only',
    pretendToBeVisual: true,
  });
  const w = dom.window;
  w.scrollTo = () => {};
  w.HTMLDialogElement.prototype.showModal = function () {
    this.open = true;
  };
  w.HTMLDialogElement.prototype.close = function () {
    this.open = false;
  };
  let team = false,
    fail = false,
    unauthorized = false,
    folderCalls = 0,
    resolveAnswer,
    createdHandover;
  const requests = [];
  const file = {
    id: 'file1',
    title: '科研笔记.txt',
    fileName: '科研笔记.txt',
    type: 'note',
    ownerId: 'me',
    owner: '本人',
    version: 1,
    size: 10,
    visibility: 'private',
    canEdit: true,
    permissions: { canShare: true },
    kind: 'file',
  };
  w.fetch = async (url, options = {}) => {
    requests.push({ url, options });
    const u = new URL(url, 'http://localhost');
    const p = u.pathname.replace('/api/v1', '');
    let value;
    let status = 200;
    if (p === '/system/status') value = { initialized: true };
    else if (p === '/me') value = { id: 'me', displayName: '测试成员', email: 'test@example.com' };
    else if (p === '/me/teams')
      value = { items: team ? [{ id: 't1', name: '测试组', role: 'student' }] : [] };
    else if (p === '/me/notifications') value = { items: [] };
    else if (p === '/teams/t1/members')
      value = {
        items: [
          { id: 'me', name: '测试成员', role: 'student' },
          { id: 'peer', name: '接收成员', role: 'student' },
        ],
      };
    else if (p === '/teams/t1/tasks')
      value = {
        items: [
          { id: 'handover-task1', title: '复现实验' },
          { id: 'handover-task2', title: '整理结果' },
        ],
        total: 2,
      };
    else if (p === '/teams/t1/handovers') {
      if (options.method === 'POST') {
        createdHandover = {
          ...JSON.parse(options.body),
          id: 'handover1',
          fromUserName: '测试成员',
          toUserName: '接收成员',
          status: 'pending',
          createdAt: '2026-10-19T00:00:00Z',
        };
        value = { id: 'handover1' };
      } else
        value = { items: createdHandover ? [createdHandover] : [], total: createdHandover ? 1 : 0 };
    } else if (p === '/me/drive/folders/tree') value = { items: [] };
    else if (p === '/me/drive/children') {
      if (unauthorized) {
        status = 401;
      } else if (fail) {
        status = 503;
      }
      value = { items: [file], total: 1, breadcrumbs: [{ id: null, name: '我的文件' }] };
    } else if (p === '/me/drive/folders' && options.method === 'POST') {
      folderCalls++;
      await new Promise((r) => setTimeout(r, 30));
      value = { id: 'folder1' };
    } else if (p === '/me/drive/available-resources') value = { items: [file], total: 1 };
    else if (p === '/me/drive/questions')
      value = await new Promise((resolve) => {
        resolveAnswer = resolve;
      });
    else if (p === '/auth/logout') value = {};
    else if (p === '/me/tasks') value = { items: [], total: 0 };
    else if (p === '/resources/file1') value = { ...file, canEdit: false, ownerId: 'other' };
    else if (p === '/resources/file1/versions') value = { items: [] };
    else if (p === '/resources/file1/reading-progress') value = {};
    else {
      status = 404;
    }
    return {
      ok: status === 200,
      status,
      json: async () => (status === 200 ? { data: value } : { message: '测试服务暂时不可用' }),
    };
  };
  const modules = new Map();
  const context = dom.getInternalVMContext();
  const loadModule = (filename) => {
    if (!modules.has(filename))
      modules.set(
        filename,
        new vm.SourceTextModule(fs.readFileSync(filename, 'utf8'), {
          context,
          identifier: filename,
        }),
      );
    return modules.get(filename);
  };
  const entry = new vm.SourceTextModule(
    `
  import './frontend/app.js';
  import {state} from './frontend/core/state.js';
  import {navigate} from './frontend/core/router.js';
  import {refreshTeams} from './frontend/core/session.js';
  import {api} from './frontend/core/api.js';
  import {handleSessionAction} from './frontend/core/session-actions.js';
  import {saveReadingProgress} from './frontend/pages/drive/reading.js';
  import {uploadQueue} from './frontend/pages/drive/upload.js';
  window.testApp={state,navigate,refreshTeams,api,handleSessionAction,saveReadingProgress,getUploadQueue:()=>uploadQueue};
 `,
    { context, identifier: path.join(root, 'test-entry.js') },
  );
  await entry.link((specifier, referencing) =>
    loadModule(path.resolve(path.dirname(referencing.identifier), specifier)),
  );
  await entry.evaluate();
  await until(() => w.document.querySelector('.drive-layout'));
  assert.equal(w.document.querySelectorAll('#nav .navitem').length, 5);
  assert.equal(w.document.querySelector('#nav .active').textContent.trim(), '我的云盘');
  assert.ok(w.document.querySelector('[data-action=upload-resource]'), '无课题组用户仍可上传');
  w.document.querySelector('[data-action=cloud-new]').click();
  await until(() => w.document.querySelector('[data-form=cloud-folder]'));
  const form = w.document.querySelector('[data-form=cloud-folder]');
  form.querySelector('[name=name]').value = '测试目录';
  form.dispatchEvent(new w.Event('submit', { bubbles: true, cancelable: true }));
  form.dispatchEvent(new w.Event('submit', { bubbles: true, cancelable: true }));
  await until(() => folderCalls === 1 && !w.document.querySelector('#modal').open);
  assert.equal(folderCalls, 1, '重复提交只写入一次');
  w.testApp.navigate('resource/file1');
  await until(() => w.document.querySelector('.pagehead h1')?.textContent === '科研笔记.txt');
  assert.equal(
    w.document.querySelector('[data-action=edit-resource]'),
    null,
    '接收人不能编辑共享文件',
  );
  assert.equal(w.document.querySelector('[data-action=cloud-shares]'), null, '接收人不能再次共享');
  team = true;
  await w.testApp.refreshTeams();
  w.testApp.navigate('tasks');
  await until(() => w.document.querySelector('#taskBoard'));
  assert.equal(w.document.querySelectorAll('.section-tabs a').length, 3);
  assert.equal(
    requests.some((x) => x.url.includes('/me/review-queue')),
    false,
    '学生查看任务时不能被反馈权限错误阻断',
  );
  w.testApp.navigate('assistant');
  await until(() => w.document.querySelector('#assistantSourceSearch'));
  const checkbox = w.document.querySelector('input[name=source]');
  checkbox.checked = true;
  checkbox.dispatchEvent(new w.Event('change', { bubbles: true }));
  assert.ok(w.document.querySelector('#assistantSelected').textContent.includes('1 份'));
  const search = w.document.querySelector('#assistantSourceSearch');
  search.value = '无匹配';
  search.dispatchEvent(new w.Event('input', { bubbles: true }));
  assert.ok(w.document.querySelector('.source-check').hidden);
  const questionForm = w.document.querySelector('[data-form=assistant]');
  questionForm.querySelector('[name=question]').value = '测试异步回答';
  questionForm.dispatchEvent(new w.Event('submit', { bubbles: true, cancelable: true }));
  await until(() => resolveAnswer);
  w.testApp.navigate('resources');
  await until(() => w.document.querySelector('.drive-layout'));
  resolveAnswer({ mode: 'retrieval', answer: '已经离开的页面回答', sources: [] });
  await until(() => !questionForm.dataset.busy);
  assert.equal(
    questionForm.querySelector('.form-error').hidden,
    true,
    '离开助手后返回的回答不应造成报错',
  );
  assert.equal(w.document.querySelector('.assistant-response'), null, '旧回答不能出现在新页面');
  fail = true;
  w.testApp.navigate('resources');
  await until(() => w.document.querySelector('#content .errorbox'));
  assert.equal(w.document.querySelector('#content .empty'), null, '加载错误不能伪装为空列表');
  fail = false;
  w.document.querySelector('#content [data-action=refresh]').click();
  await until(() => w.document.querySelector('.drive-layout'));
  w.testApp.state.settingsTab = 'handover';
  w.testApp.navigate('settings');
  await until(() => w.document.querySelector('[data-action=create-handover]'));
  w.document.querySelector('[data-action=create-handover]').click();
  await until(() => w.document.querySelector('[data-form=handover]'));
  const handoverForm = w.document.querySelector('[data-form=handover]');
  handoverForm.querySelector('[name=title]').value = '实验资料交接';
  handoverForm.querySelector('[name=content]').value = '保留实验过程和待办';
  handoverForm.querySelectorAll('[name=taskIds]').forEach((input) => (input.checked = true));
  handoverForm.querySelector('[name=resourceIds]').checked = true;
  handoverForm.dispatchEvent(new w.Event('submit', { bubbles: true, cancelable: true }));
  await until(() => createdHandover && !w.document.querySelector('#modal').open);
  assert.deepEqual(
    createdHandover.taskIds,
    ['handover-task1', 'handover-task2'],
    '交接保留所有勾选任务',
  );
  assert.deepEqual(createdHandover.resourceIds, ['file1'], '交接保留勾选资料');
  assert.equal(createdHandover.toUserId, 'peer', '只选择其他有效成员作为接收人');
  await until(() => w.document.querySelector('.handover-record'));
  assert.ok(w.document.querySelector('.handover-record').textContent.includes('2 项关联任务'));
  w.document.querySelector('[data-action=create-handover]').click();
  await until(() => w.document.querySelector('[data-form=handover]'));
  const staleForm = w.document.querySelector('[data-form=handover]');
  const originalTeam = w.testApp.state.team;
  w.testApp.state.team = { ...originalTeam, id: 'another-team' };
  staleForm.dispatchEvent(new w.Event('submit', { bubbles: true, cancelable: true }));
  await until(() => staleForm.querySelector('.form-error').textContent.includes('课题组已切换'));
  assert.equal(
    requests.filter(
      (request) => request.url.includes('/handovers') && request.options.method === 'POST',
    ).length,
    1,
    '旧表单不能提交到新课题组',
  );
  w.testApp.state.team = originalTeam;
  w.document.querySelector('#closeModal').click();
  for (const mode of ['logout', 'expired']) {
    const app = w.testApp;
    app.state.user = { id: 'me', displayName: '测试成员' };
    await app.refreshTeams();
    app.navigate('resources');
    await until(() => w.document.querySelector('.drive-layout'));
    w.document.querySelector('[data-action=cloud-new]').click();
    await until(() => w.document.querySelector('#modal').open);
    Object.assign(app.state, {
      driveFolder: 'previous-folder',
      driveReturn: 'resources/old',
      referenceTarget: { id: 'previous-task' },
      uploadTarget: { id: 'previous-task' },
      searchQuery: 'previous-query',
    });
    app.state.data.privateContent = 'previous-user';
    w.document.querySelector('#searchInput').value = 'previous-query';
    let aborted = 0;
    app.getUploadQueue().push({ xhr: { abort: () => aborted++ } });
    app.saveReadingProgress('file1', { ratio: 0.5 });
    const savesBefore = requests.filter(
      (x) => x.url.includes('/reading-progress') && x.options.method === 'PATCH',
    ).length;
    const sequence = app.state.sequence;
    if (mode === 'logout') await app.handleSessionAction('logout');
    else {
      unauthorized = true;
      await assert.rejects(app.api('/me/drive/children'), (error) => error.status === 401);
      unauthorized = false;
    }
    assert.equal(app.state.user, null, mode + ' clears user');
    assert.equal(app.state.team, null, mode + ' clears team');
    assert.equal(app.state.teams.length, 0, mode + ' clears teams');
    assert.equal(app.state.members.length, 0, mode + ' clears members');
    assert.equal(Object.keys(app.state.data).length, 0, mode + ' clears page cache');
    assert.equal(app.state.renderedHash, null, mode + ' clears last rendered page');
    assert.equal(app.state.driveFolder, undefined, mode + ' clears old cloud folder');
    assert.equal(app.state.referenceTarget, undefined, mode + ' clears old reference target');
    assert.equal(app.state.uploadTarget, undefined, mode + ' clears old upload target');
    assert.equal(app.state.sequence, sequence + 1, mode + ' invalidates pending renders');
    assert.equal(aborted, 1, mode + ' aborts active uploads');
    assert.equal(app.getUploadQueue().length, 0, mode + ' clears upload queue');
    assert.equal(w.document.querySelector('#modal').open, false, mode + ' closes dialogs');
    assert.equal(
      w.document.querySelector('#modalBody').childElementCount,
      0,
      mode + ' clears dialog content',
    );
    assert.equal(
      w.document.querySelector('#content').childElementCount,
      0,
      mode + ' clears previous page',
    );
    assert.equal(w.document.querySelector('#searchInput').value, '', mode + ' clears search input');
    assert.ok(w.document.querySelector('[data-form=login]'), mode + ' displays login');
    app.saveReadingProgress('file1', { ratio: 0.9 });
    await new Promise((resolve) => setTimeout(resolve, 600));
    assert.equal(
      requests.filter((x) => x.url.includes('/reading-progress') && x.options.method === 'PATCH')
        .length,
      savesBefore,
      mode + ' cancels delayed reading saves and ignores signed-out events',
    );
  }
  dom.window.close();
  console.log(
    '前端回归通过：导航、云盘、只读共享、助手、交接多选提交、切组保护、退出及登录失效清理。',
  );
}
main().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
