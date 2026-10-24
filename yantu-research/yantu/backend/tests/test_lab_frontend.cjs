const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');
const root = path.resolve(__dirname, '../..');
const until = async (predicate) => {
  const start = Date.now();
  while (!predicate()) {
    if (Date.now() - start > 4000) throw new Error('页面未在预期时间内更新');
    await new Promise(resolve => setTimeout(resolve, 10));
  }
};

async function main() {
  const dom = new JSDOM(fs.readFileSync(path.join(root, 'frontend/index.html'), 'utf8'), {
    url: 'http://localhost/#home', runScripts: 'outside-only', pretendToBeVisual: true,
  });
  const w = dom.window;
  w.scrollTo = () => {};
  w.HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  w.HTMLDialogElement.prototype.close = function () { this.open = false; };
  const user = { id: 'member', displayName: '普通成员', email: 'member@example.test' };
  const joined = { id: 'joined', name: '已加入课题', role: 'student', membershipStatus: 'member', memberCount: 2 };
  const hidden = { id: 'hidden', name: '未加入课题', role: null, membershipStatus: 'none', memberCount: 1 };
  const message = { id: 'message1', title: '<img src=x onerror=alert(1)>', content: '<script>bad()</script>', authorId: user.id, authorName: user.displayName };
  const requests = [];
  let authenticated = false;
  let failMessages = false;
  w.fetch = async (url, options = {}) => {
    const parsed = new URL(url, 'http://localhost');
    const endpoint = parsed.pathname.replace('/api/v1', '');
    const method = options.method || 'GET';
    requests.push({ endpoint, method });
    let value;
    let status = 200;
    if (endpoint === '/auth/login') { authenticated = true; value = { user }; }
    else if (endpoint === '/auth/logout') { authenticated = false; value = null; }
    else if (!authenticated) status = 401;
    else if (endpoint === '/me') value = user;
    else if (endpoint === '/lab/projects') value = { items: parsed.searchParams.get('scope') === 'joined' ? [joined] : [joined, hidden] };
    else if (endpoint === '/lab/next-meeting') value = null;
    else if (endpoint === '/lab/projects/joined/materials' || endpoint === '/lab/projects/joined/meetings') value = { items: [] };
    else if (endpoint === '/lab/tasks') value = { items: [{ id: 'task1', projectId: joined.id, projectName: joined.name, title: '负责人分配的任务', status: 'todo' }] };
    else if (endpoint === '/lab/messages' && method === 'POST') value = message;
    else if (endpoint === '/lab/messages') { value = { items: [message], canPublish: true }; if (failMessages) status = 503; }
    else if (endpoint === '/lab/messages/message1') value = message;
    else if (endpoint === '/lab/comments/message/message1' || endpoint === '/lab/history') value = { items: [] };
    else status = 404;
    return { ok: status >= 200 && status < 300, status, json: async () => status >= 200 && status < 300 ? { data: value } : { message: status === 401 ? '请先登录' : '服务暂时不可用' } };
  };
  const click = selector => {
    const element = w.document.querySelector(selector);
    assert.ok(element, `找不到操作 ${selector}`);
    element.click();
  };
  try {
    w.eval(['lab-app.js','lab-cloud.js','cloud-upload.js','lab-drive.js'].map(name=>fs.readFileSync(path.join(root, 'frontend', name), 'utf8')).join('\n'));
    await until(() => w.document.querySelector('[data-form=login]'));
    assert.equal(w.document.querySelector('#appShell').hidden, true, '未登录时隐藏所有业务页面');
    const login = w.document.querySelector('[data-form=login]');
    login.elements.email.value = user.email;
    login.elements.password.value = 'test-laboratory-password';
    login.dispatchEvent(new w.Event('submit', { bubbles: true, cancelable: true }));
    await until(() => !w.document.querySelector('#appShell').hidden && w.document.querySelector('#content').classList.contains('home'));
    assert.deepEqual([...w.document.querySelectorAll('#nav .navitem')].map(a => a.textContent), ['首页', '课题管理', '我的资料', '我的任务', '历史记录', '学长留言']);
    assert.equal(w.document.querySelector('#content').textContent, '', '首页中心保持留白');
    assert.match(w.document.querySelector('#nextMeeting').textContent, /暂无安排/);

    click('a[href="#materials"]');
    await until(() => w.document.querySelector('#materialProject'));
    assert.deepEqual([...w.document.querySelector('#materialProject').options].map(o => o.textContent), [joined.name], '资料选择器只包含已加入课题');
    assert.equal(w.document.querySelector('[data-action=create-meeting]'), null, '普通成员不能安排组会');

    click('a[href="#tasks"]');
    await until(() => w.document.querySelector('.task-card'));
    assert.match(w.document.querySelector('#content').textContent, /负责人分配的任务/);
    assert.equal(w.document.querySelector('#content [data-action],#content form'), null, '我的任务不提供状态修改、提交或反馈操作');

    click('a[href="#messages"]');
    await until(() => w.document.querySelector('[data-action=create-message]'));
    assert.equal(w.document.querySelector('#content img,#content script'), null, '留言按文本展示');
    assert.match(w.document.querySelector('#content').textContent, /<script>bad/);
    click('[data-action=create-message]');
    await until(() => w.document.querySelector('dialog').open);
    assert.match(w.document.querySelector('#modalBody').textContent, /所有登录成员可见/);
    const form = w.document.querySelector('[data-form=create-message]');
    form.elements.title.value = '普通成员建议';
    form.elements.content.value = '保留原始实验数据。';
    form.dispatchEvent(new w.Event('submit', { bubbles: true, cancelable: true }));
    await until(() => w.location.hash === '#message/message1' && w.document.querySelector('[data-form=comment]'));
    assert.ok(requests.some(r => r.endpoint === '/lab/messages' && r.method === 'POST'));

    failMessages = true;
    click('a[href="#messages"]');
    await until(() => w.document.querySelector('#content .errorbox'));
    assert.match(w.document.querySelector('#content .errorbox').textContent, /服务暂时不可用/);
    failMessages = false;
    click('[data-action=retry]');
    await until(() => w.document.querySelector('[data-action=create-message]'));
    click('[data-action=logout]');
    await until(() => w.document.querySelector('#appShell').hidden);
    assert.ok(w.document.querySelector('[data-form=login]'));
    console.log('Frontend acceptance passed: login gate, six modules, blank home, joined-only materials, read-only tasks, member publishing, escaping, retry and logout.');
  } finally {
    w.close();
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
