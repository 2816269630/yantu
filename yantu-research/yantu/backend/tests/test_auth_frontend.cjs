const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

const root = path.resolve(__dirname, '../..');
const until = async predicate => {
  const started = Date.now();
  while (!predicate()) {
    if (Date.now() - started > 3000) throw new Error('Authentication view did not update');
    await new Promise(resolve => setTimeout(resolve, 10));
  }
};

async function openSite({ registrationOpen = true, invite = '' } = {}) {
  const dom = new JSDOM(fs.readFileSync(path.join(root, 'frontend/index.html'), 'utf8'), {
    url: `http://localhost/${invite ? '?invite=' + invite : ''}#home`, runScripts: 'outside-only',
  });
  const w = dom.window;
  w.scrollTo = () => {};
  let authenticated = false, duplicate = false;
  const requests = [];
  w.fetch = async (url, options = {}) => {
    requests.push({ url, options });
    let status = 200, data;
    if (url === '/api/v1/system/status') data = { initialized: true, registrationOpen, version: '0.4.0' };
    else if (url === '/api/v1/auth/register') {
      status = duplicate ? 409 : 200;
      data = { id: 'new-user' };
    } else if (url === '/api/v1/auth/login') {
      authenticated = true;
      data = { user: { id: 'new-user', displayName: '新成员' } };
    } else if (url === '/api/v1/me') {
      status = authenticated ? 200 : 401;
      data = { id: 'new-user', displayName: '新成员' };
    } else if (url === '/api/v1/me/teams' || url === '/api/v1/me/notifications') data = { items: [] };
    else throw new Error(`Unexpected request: ${url}`);
    return { ok: status === 200, status, json: async () => status === 200 ? { data } : { message: status === 409 ? '邮箱已注册，请直接登录。' : '请先登录' } };
  };
  w.eval(fs.readFileSync(path.join(root, 'frontend/app.js'), 'utf8'));
  await until(() => w.document.querySelector('form[data-form]'));
  return { dom, w, requests, setDuplicate: value => { duplicate = value; } };
}

function fill(w, values) {
  for (const [name, value] of Object.entries(values)) w.document.querySelector(`[name="${name}"]`).value = value;
}
function submit(w) {
  w.document.querySelector('form[data-form]').dispatchEvent(new w.Event('submit', { bubbles: true, cancelable: true }));
}

async function main() {
  const site = await openSite();
  try {
    const { w, requests } = site;
    assert.equal(w.document.querySelector('h1').textContent, '登录研途');
    w.document.querySelector('[data-action="auth-register"]').click();
    assert.equal(w.document.querySelector('h1').textContent, '创建研途账号');
    assert.equal(w.document.querySelector('[name="invitationToken"]').required, false);
    assert.ok(w.document.querySelector('[name="invitationToken"]').closest('details'));
    fill(w, { displayName: '新成员', email: 'new@example.com', password: 'strong-password-123', confirmPassword: 'different-password-123' });
    submit(w);
    await until(() => !w.document.querySelector('.form-error').hidden);
    assert.match(w.document.querySelector('.form-error').textContent, /两次输入的密码不一致/);
    assert.equal(requests.some(request => request.url.endsWith('/auth/register')), false);
    fill(w, { confirmPassword: 'strong-password-123' });
    site.setDuplicate(true);
    submit(w);
    await until(() => /邮箱已注册/.test(w.document.querySelector('.form-error').textContent));
    assert.equal(w.document.querySelector('[type="submit"]').disabled, false);
    site.setDuplicate(false);
    submit(w);
    await until(() => w.document.querySelector('#authRoot').hidden);
    assert.equal(w.document.querySelector('#appShell').hidden, false);
    const payload = JSON.parse(requests.find(request => request.url.endsWith('/auth/register')).options.body);
    assert.equal(payload.confirmPassword, undefined, 'Confirmation password stays in the browser');
    assert.equal(payload.invitationToken, '', 'Personal signup needs no invitation');
    assert.ok(requests.some(request => request.url.endsWith('/auth/login')), 'Signup logs the new account in');
  } finally { site.dom.window.close(); }

  const invited = await openSite({ invite: 'invitation-token' });
  try {
    const { w, requests } = invited;
    assert.ok(w.document.querySelector('.auth-invite-note'));
    fill(w, { displayName: '受邀成员', email: 'invited@example.com', password: 'strong-password-123', confirmPassword: 'strong-password-123' });
    submit(w);
    await until(() => w.document.querySelector('#authRoot').hidden);
    assert.equal(new URL(w.location.href).searchParams.has('invite'), false);
    const payload = JSON.parse(requests.find(request => request.url.endsWith('/auth/register')).options.body);
    assert.equal(payload.invitationToken, 'invitation-token');
    assert.equal(requests.some(request => request.url.includes('/invitations/')), false, 'A signup invitation is not accepted twice');
  } finally { invited.dom.window.close(); }

  const closed = await openSite({ registrationOpen: false });
  try {
    closed.w.document.querySelector('[data-action="auth-register"]').click();
    assert.equal(closed.w.document.querySelector('[name="invitationToken"]').required, true);
  } finally { closed.dom.window.close(); }
  console.log('Authentication UI: personal signup, confirmation, duplicate retry, auto-login and invitation flow passed.');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
