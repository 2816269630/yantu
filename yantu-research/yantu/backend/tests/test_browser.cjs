/* Run only against a disposable, uninitialized local service. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

async function main() {
  const baseURL = process.env.YANTU_TEST_BASE_URL;
  assert.ok(baseURL, 'Set YANTU_TEST_BASE_URL to a disposable local test service.');
  const parsed = new URL(baseURL);
  assert.ok(['127.0.0.1', 'localhost'].includes(parsed.hostname), 'Only a local test server is allowed.');
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.YANTU_BROWSER_EXECUTABLE ? {executablePath: process.env.YANTU_BROWSER_EXECUTABLE} : {}),
  });
  try {
    const context = await browser.newContext({viewport:{width:1440,height:1000},timezoneId:'Asia/Shanghai'});
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('response', response => {
      if (response.status() >= 400 && !response.url().endsWith('/favicon.ico')) errors.push(`${response.status()} ${response.url()}`);
    });
    const status = await context.request.get(baseURL + '/api/v1/system/status');
    assert.equal((await status.json()).data.initialized, false, 'Refusing to modify an initialized service.');
    await page.goto(baseURL, {waitUntil:'networkidle'});
    const password = 'module-browser-test-password-2026';
    await page.locator('[name=displayName]').fill('模块验收负责人');
    await page.locator('[name=email]').fill('module-owner@example.test');
    await page.locator('[name=password]').fill(password);
    await page.locator('[name=teamName]').fill('模块验收课题组');
    await page.locator('form[data-form=setup] button[type=submit]').click();
    await page.waitForSelector('#appShell:not([hidden])');
    const fixtures = await page.evaluate(async ({password}) => {
      const api = async (url, method='GET', body) => {
        const response = await fetch('/api/v1'+url,{method,credentials:'same-origin',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});
        const value=await response.json();
        if(!response.ok)throw new Error(JSON.stringify(value));
        return value.data;
      };
      const owner=await api('/me');
      const team=(await api('/me/teams')).items[0];
      const invitation=await api(`/teams/${team.id}/invitations`,'POST',{email:'module-mentor@example.test',role:'mentor'});
      const mentor=await api('/auth/register','POST',{email:'module-mentor@example.test',password,displayName:'模块验收前辈',invitationToken:invitation.inviteToken});
      const task=await api(`/teams/${team.id}/tasks`,'POST',{title:'模块验收任务',description:'检查模块拆分后的页面与请求',acceptanceCriteria:'各页面正常加载',assigneeId:owner.id,reviewerId:mentor.id});
      const route=await api(`/teams/${team.id}/routes`,'POST',{title:'模块验收路线',description:'学习页面验收',stages:[{title:'阅读阶段',tasks:[{title:'阅读资料'}]}]});
      const experience=await api(`/teams/${team.id}/experiences`,'POST',{title:'模块验收经验',startingPoint:'首次使用系统',content:'模块验收记录'});
      const meeting=await api(`/teams/${team.id}/meetings`,'POST',{title:'模块验收组会',startsAt:'2026-11-01T08:00:00Z',location:'测试会议室',agenda:'核对重构结果'});
      await api(`/teams/${team.id}/progress`,'POST',{content:'模块验收研究记录',blockers:'',nextPlan:'继续测试',kind:'progress'});
      const form=new FormData();form.append('file',new File(['模块验收资料正文，用于科研助手检索。'],'模块验收.txt',{type:'text/plain'}));form.append('type','note');
      const upload=await fetch('/api/v1/me/drive/files',{method:'POST',body:form,credentials:'same-origin'});
      if(!upload.ok)throw new Error(await upload.text());
      return {task:task.id,route:route.id,experience:experience.id,meeting:meeting.id,resource:(await upload.json()).data.id};
    },{password});
    const pages=[['home','工作台'],['plans','我的学习'],['routes','学习路线'],['route/'+fixtures.route,'路线详情'],['experiences','前辈经验'],['experience/'+fixtures.experience,'经验详情'],['tasks','任务与反馈'],['task/'+fixtures.task,'任务详情'],['progress','研究记录'],['meetings','组会'],['meeting/'+fixtures.meeting,'组会详情'],['resources','我的云盘'],['resource/'+fixtures.resource,'资料详情'],['assistant','科研助手'],['settings','空间与权限'],['notifications','通知']];
    const screenshotDir=process.env.YANTU_TEST_SCREENSHOTS;
    if(screenshotDir)fs.mkdirSync(screenshotDir,{recursive:true});
    for(const [route,label] of pages){
      await page.evaluate(route=>{location.hash=route},route);
      await page.waitForFunction(()=>!document.querySelector('#content > .loading'));
      await page.waitForLoadState('networkidle');
      assert.equal(await page.locator('#content .errorbox').count(),0,label+' must not show an error');
      assert.ok((await page.locator('#content').innerText()).trim(),label+' must render content');
      if(screenshotDir)await page.screenshot({path:path.join(screenshotDir,route.split('/')[0]+'.png'),fullPage:true,animations:'disabled'});
    }
    await page.locator('a[aria-label="课题组设置"]').click();
    await page.locator('form[data-form=team]').waitFor();
    await page.waitForLoadState('networkidle');
    assert.ok((await page.locator('#content').innerText()).includes('课题组名称'));
    await page.setViewportSize({width:390,height:844});
    await page.evaluate(()=>{location.hash='resources'});
    await page.locator('.drive-layout').waitFor();
    await page.waitForLoadState('networkidle');
    assert.equal(await page.locator('#content .errorbox').count(),0);
    assert.equal(await page.locator('.drive-layout').evaluate(element=>getComputedStyle(element).gridTemplateColumns.split(' ').length),1,'Mobile drive must use one column.');
    if(screenshotDir)await page.screenshot({path:path.join(screenshotDir,'mobile-drive.png'),fullPage:true,animations:'disabled'});
    assert.deepEqual(errors,[]);
    console.log(`Browser regression passed: setup, ${pages.length} pages, settings shortcut and mobile drive.`);
  } finally {await browser.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
