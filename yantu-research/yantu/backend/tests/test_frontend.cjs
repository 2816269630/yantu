const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

const root = path.resolve(__dirname, '../..');
const html = fs.readFileSync(path.join(root, 'frontend/index.html'), 'utf8');
const script = fs.readFileSync(path.join(root, 'frontend/app.js'), 'utf8');

function until(predicate, timeout = 1500) {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    const poll = () => {
      if (predicate()) return resolve();
      if (Date.now() - start > timeout) return reject(new Error('Frontend did not settle'));
      setTimeout(poll, 10);
    };
    poll();
  });
}

async function main() {
  const dom = new JSDOM(html, {
    url: 'http://localhost:8000/#settings', runScripts: 'dangerously',
  });
  const { window } = dom;
  const requests = [];
  window.fetch = async (url, options = {}) => {
    requests.push({ url, options });
    const routes = {
      '/api/v1/auth/login': { accessToken: 'test-token', user: { id: 'u1', displayName: '甲' } },
      '/api/v1/me/teams': { items: [{ id: 't1', name: '科研实验室', role: 'owner' }], total: 1 },
      '/api/v1/teams/t1/members?pageSize=100': { items: [{ id: 'u1', name: '甲', role: 'owner' }], total: 1 },
      '/api/v1/teams/t1/routes': { id: 'r1' },
      '/api/v1/teams/t1/questions': { answer: '先读摘要 [1]', sources: [
        { resourceId: 'resource-1', title: '阅读指南', excerpt: '读论文时先读摘要。' },
      ] },
    };
    return { ok: !!routes[url], status: routes[url] ? 200 : 404,
      json: async () => routes[url] ? { data: routes[url] } : { message: 'Not Found' } };
  };
  window.eval(script);
  await until(() => window.document.querySelector('[data-form="setup"]'));
  const submit = (form) => {
    form.dispatchEvent(new window.SubmitEvent('submit', {
      bubbles: true, cancelable: true, submitter: form.querySelector('button:not([type="button"])'),
    }));
  };
  const login = window.document.querySelector('#loginForm');
  login.querySelector('[name=email]').value = 'owner@example.com';
  login.querySelector('[name=password]').value = 'a-test-password';
  submit(login);
  await until(() => window.document.querySelector('#teamId').value === 't1');
  assert.equal(window.document.querySelector('#myTeams tbody tr td').textContent, 't1');
  await until(() => window.document.querySelector('select[name=assigneeId]').options.length === 2);
  assert.equal(window.document.querySelector('select[name=assigneeId]').options[1].value, 'u1');

  window.document.querySelector('#addStage').click();
  const stages = [...window.document.querySelectorAll('.stage-editor')];
  assert.equal(stages.length, 2);
  stages[0].querySelector('[data-stage-title]').value = '入门';
  stages[0].querySelector('[data-task-title]').value = '精读论文';
  stages[1].querySelector('[data-stage-title]').value = '复现';
  stages[1].querySelector('[data-task-title]').value = '运行基线';
  const routeForm = window.document.querySelector('[data-route-form]');
  routeForm.querySelector('[name=title]').value = '差分隐私学习路线';
  submit(routeForm);
  await until(() => requests.some((r) => r.url === '/api/v1/teams/t1/routes'));
  const sent = JSON.parse(requests.find((r) => r.url === '/api/v1/teams/t1/routes').options.body);
  assert.equal(sent.stages.length, 2);
  assert.equal(sent.stages[0].tasks[0].title, '精读论文');
  assert.equal(sent.stages[1].title, '复现');
  const questionForm = window.document.querySelector('[data-api="/teams/{teamId}/questions"]');
  questionForm.querySelector('[name=question]').value = '读论文先看哪里？';
  submit(questionForm);
  await until(() => window.document.querySelector('#answer').textContent.includes('先读摘要'));
  assert.ok(window.document.querySelector('#answer').textContent.includes('阅读指南'));
  assert.equal(requests[0].options.headers.Authorization || '', '');
  assert.equal(requests.at(-1).options.headers.Authorization, 'Bearer test-token');
  assert.equal(window.document.querySelector('#status').textContent.includes('Not Found'), false);
  dom.window.close();
  console.log('Frontend login, team selection and route creation passed.');
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
