const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');
const root = path.resolve(__dirname, '../..');
const until = async (predicate) => { const start=Date.now(); while(!predicate()){if(Date.now()-start>3000)throw new Error('页面未在预期时间内更新');await new Promise(r=>setTimeout(r,10));} };
async function main(){
 const dom=new JSDOM(fs.readFileSync(path.join(root,'frontend/index.html'),'utf8'),{url:'http://localhost/#resources',runScripts:'outside-only',pretendToBeVisual:true});
 const w=dom.window;w.scrollTo=()=>{};w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};w.HTMLDialogElement.prototype.close=function(){this.open=false;};
 let team=false,fail=false,folderCalls=0;const requests=[];
 const file={id:'file1',title:'科研笔记.txt',fileName:'科研笔记.txt',type:'note',ownerId:'me',owner:'本人',version:1,size:10,visibility:'private',canEdit:true,permissions:{canShare:true},kind:'file'};
 w.fetch=async (url,options={})=>{requests.push({url,options});const u=new URL(url,'http://localhost');const p=u.pathname.replace('/api/v1','');let value;let status=200;
  if(p==='/system/status')value={initialized:true};
  else if(p==='/me')value={id:'me',displayName:'测试成员',email:'test@example.com'};
  else if(p==='/me/teams')value={items:team?[{id:'t1',name:'测试组',role:'student'}]:[]};
  else if(p==='/me/notifications')value={items:[]};
  else if(p==='/teams/t1/members')value={items:[{id:'me',name:'测试成员',role:'student'}]};
  else if(p==='/me/drive/folders/tree')value={items:[]};
  else if(p==='/me/drive/children'){if(fail){status=503;}value={items:[file],total:1,breadcrumbs:[{id:null,name:'我的文件'}]};}
  else if(p==='/me/drive/folders'&&options.method==='POST'){folderCalls++;await new Promise(r=>setTimeout(r,30));value={id:'folder1'};}
  else if(p==='/me/drive/available-resources')value={items:[file],total:1};
  else if(p==='/me/tasks')value={items:[],total:0};
  else if(p==='/resources/file1')value={...file,canEdit:false,ownerId:'other'};
  else if(p==='/resources/file1/versions')value={items:[]};
  else if(p==='/resources/file1/reading-progress')value={};
  else {status=404;}
  return {ok:status===200,status,json:async()=>status===200?{data:value}:{message:'测试服务暂时不可用'}};
 };
 const source=['app.js','cloud-upload.js','cloud-drive.js'].map(f=>fs.readFileSync(path.join(root,'frontend',f),'utf8')).join('\n');
 w.eval(source+'\nwindow.testApp={state,navigate,refreshTeams};');
 await until(()=>w.document.querySelector('.drive-layout'));
 assert.equal(w.document.querySelectorAll('#nav .navitem').length,5);
 assert.equal(w.document.querySelector('#nav .active').textContent.trim(),'我的云盘');
 assert.ok(w.document.querySelector('[data-action=upload-resource]'),'无课题组用户仍可上传');
 w.document.querySelector('[data-action=cloud-new]').click();
 await until(()=>w.document.querySelector('[data-form=cloud-folder]'));
 const form=w.document.querySelector('[data-form=cloud-folder]');form.querySelector('[name=name]').value='测试目录';
 form.dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));form.dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));
 await until(()=>folderCalls===1&&!w.document.querySelector('#modal').open);assert.equal(folderCalls,1,'重复提交只写入一次');
 w.testApp.navigate('resource/file1');await until(()=>w.document.querySelector('.pagehead h1')?.textContent==='科研笔记.txt');
 assert.equal(w.document.querySelector('[data-action=edit-resource]'),null,'接收人不能编辑共享文件');
 assert.equal(w.document.querySelector('[data-action=cloud-shares]'),null,'接收人不能再次共享');
 team=true;await w.testApp.refreshTeams();w.testApp.navigate('tasks');await until(()=>w.document.querySelector('#taskBoard'));
 assert.equal(w.document.querySelectorAll('.section-tabs a').length,3);
 assert.equal(requests.some(x=>x.url.includes('/me/review-queue')),false,'学生查看任务时不能被反馈权限错误阻断');
 w.testApp.navigate('assistant');await until(()=>w.document.querySelector('#assistantSourceSearch'));
 const checkbox=w.document.querySelector('input[name=source]');checkbox.checked=true;checkbox.dispatchEvent(new w.Event('change',{bubbles:true}));
 assert.ok(w.document.querySelector('#assistantSelected').textContent.includes('1 份'));
 const search=w.document.querySelector('#assistantSourceSearch');search.value='无匹配';search.dispatchEvent(new w.Event('input',{bubbles:true}));assert.ok(w.document.querySelector('.source-check').hidden);
 fail=true;w.testApp.navigate('resources');await until(()=>w.document.querySelector('#content .errorbox'));assert.equal(w.document.querySelector('#content .empty'),null,'加载错误不能伪装为空列表');
 fail=false;w.document.querySelector('#content [data-action=refresh]').click();await until(()=>w.document.querySelector('.drive-layout'));
 dom.window.close();console.log('前端回归通过：导航、无课题组云盘、重复提交、只读共享、学生任务、资料选择及错误重试。');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
