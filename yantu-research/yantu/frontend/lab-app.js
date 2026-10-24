'use strict';

const $ = selector => document.querySelector(selector);
const state = {user:null, joined:[], seq:0, data:{}, next:null, projectScope:'all', projectTab:'members', taskProject:'', taskStatus:'', authMode:'login'};
const navItems = [['home','首页','home'],['projects','课题管理','projects'],['materials','我的资料','folder'],['tasks','我的任务','tasks'],['history','历史记录','history'],['messages','学长留言','message']];
const roleNames = {owner:'负责人',mentor:'学长',student:'成员'};
const taskNames = {todo:'待开始',doing:'进行中',done:'已完成',blocked:'遇到阻碍',review:'进行中'};
const meetingNames = {scheduled:'待开始',completed:'已结束',archived:'已归档'};
const paths = {
  home:'<path d="m3 10 9-7 9 7v10H3z"/><path d="M9 20v-7h6v7"/>',
  projects:'<rect x="3" y="5" width="18" height="15" rx="2"/><path d="M8 5V3h8v2M3 11h18M10 11v3h4v-3"/>',
  folder:'<path d="M3 7V5h6l2 2h10v13H3z"/>',
  tasks:'<rect x="5" y="4" width="15" height="17" rx="2"/><path d="M9 4V2h7v2M9 10h7M9 15h7"/>',
  history:'<path d="M3 11a9 9 0 1 1 2 7M3 4v7h7M12 7v6l4 2"/>',
  message:'<path d="M4 4h16v13H9l-5 4zM8 8h8M8 12h5"/>',
  file:'<path d="M5 3h9l5 5v13H5zM14 3v6h5M9 13h6M9 17h6"/>',
  meeting:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4M17 3v4M3 11h18M8 15h3"/>',
  video:'<rect x="3" y="5" width="18" height="15" rx="2"/><path d="m10 9 5 3-5 4z"/>',
  logout:'<path d="M9 4H4v16h5M12 12h9m-4-4 4 4-4 4"/>'
};
const icon = name => `<svg class="i" viewBox="0 0 24 24" aria-hidden="true">${paths[name] || paths.file}</svg>`;
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const enc = value => encodeURIComponent(String(value ?? ''));
const date = value => value ? new Date(value).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}) : '未设置';
const bytes = value => Number(value) >= 1073741824 ? (value/1073741824).toFixed(1)+' GiB' : Number(value) >= 1048576 ? (value/1048576).toFixed(1)+' MiB' : Math.ceil((Number(value)||0)/1024)+' KiB';
const localDate = value => {if(!value)return '';const d=new Date(value);return new Date(d-d.getTimezoneOffset()*60000).toISOString().slice(0,16);};
const tag = (text,cls='') => `<span class="tag ${cls}">${esc(text)}</span>`;
const button = (label,action,id='',cls='',extra='') => `<button type="button" class="btn ${cls}" data-action="${action}" data-id="${esc(id)}" ${extra}>${label}</button>`;
const link = (label,hash,cls='') => `<a class="${cls}" href="#${hash}">${label}</a>`;
const empty = (title,description='',actions='') => `<div class="empty"><h3>${esc(title)}</h3><p>${esc(description)}</p>${actions?`<div class="actions">${actions}</div>`:''}</div>`;
const head = (title,description='',actions='') => `<div class="pagehead"><div><h1>${esc(title)}</h1>${description?`<p>${esc(description)}</p>`:''}</div><div class="actions">${actions}</div></div>`;
let fieldSequence=0;
const field = (label,name,value='',options={}) => {
  const id=`f-${name}-${++fieldSequence}`;
  return `<div class="field"><label for="${id}">${esc(label)}</label>${options.area?`<textarea id="${id}" name="${name}" rows="${options.rows||4}" maxlength="${options.max||10000}" ${options.required?'required':''}>${esc(value)}</textarea>`:`<input id="${id}" name="${name}" type="${options.type||'text'}" value="${esc(value)}" ${options.required?'required':''} ${options.min?`minlength="${options.min}"`:''} ${options.max?`maxlength="${options.max}"`:''} ${options.accept?`accept="${options.accept}"`:''} ${options.auto?`autocomplete="${options.auto}"`:''}>`}${options.help?`<small>${esc(options.help)}</small>`:''}</div>`;
};
const selectField = (label,name,options,value='') => {
  const id=`f-${name}-${++fieldSequence}`;
  return `<div class="field"><label for="${id}">${esc(label)}</label><select id="${id}" name="${name}">${options.map(x=>`<option value="${esc(x.id)}" ${String(value)===String(x.id)?'selected':''}>${esc(x.name)}</option>`).join('')}</select></div>`;
};
function toast(message,error=false){const box=$('#toast');box.textContent=message;box.classList.toggle('error',error);box.hidden=false;clearTimeout(state.toastTimer);state.toastTimer=setTimeout(()=>box.hidden=true,4500);}
async function api(path,method='GET',body){
  const multipart=body instanceof FormData;
  const response=await fetch('/api/v1'+path,{method,credentials:'same-origin',headers:body===undefined||multipart?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:multipart?body:JSON.stringify(body)});
  const json=await response.json().catch(()=>({}));
  if(!response.ok){const error=new Error(json.message||json.detail||`请求失败（${response.status}）`);error.status=response.status;throw error;}
  return json.data;
}
async function refreshJoined(){state.joined=(await api('/lab/projects?scope=joined')).items;}
function navigate(hash){if(location.hash==='#'+hash)render();else location.hash=hash;}
function closeModal(){if(state.upload){state.upload.abort();state.upload=null;}if(typeof clearUploadQueue==='function')clearUploadQueue();$('#modal').close();$('#modalBody').innerHTML='';}
function modal(title,html){$('#modalTitle').textContent=title;$('#modalBody').innerHTML=html;if(!$('#modal').open)$('#modal').showModal();$('#modalBody input:not([type=hidden]),#modalBody textarea,#modalBody select')?.focus();}
function formModal(title,kind,fields,id='',submit='保存',extra=''){
  modal(title,`<form data-form="${kind}" data-id="${esc(id)}" ${extra}>${fields}<div class="form-error" role="alert" hidden></div><div class="form-actions">${button('取消','close','','quiet')}<button class="btn primary" type="submit">${submit}</button></div></form>`);
}
function showAuth(mode='login',error=''){
  state.authMode=mode;state.user=null;state.seq++;state.next=null;$('#appShell').hidden=true;$('#authRoot').hidden=false;$('#authRoot').className='auth-root';
  if($('#modal').open)closeModal();
  if(typeof clearUploadQueue==='function')clearUploadQueue();
  if(typeof closeDriveMenu==='function')closeDriveMenu();
  const register=mode==='register';
  $('#authRoot').innerHTML=`<section class="auth-card"><div class="brand"><span class="brandmark">研</span><span>研途<small>实验室空间</small></span></div><h1>${register?'创建账号':'登录研途'}</h1><p class="muted" style="margin:10px 0 26px">${register?'注册后，可创建课题或申请加入课题。':'继续你的课题与实验室生活。'}</p><form data-form="${mode}">${register?field('姓名','displayName','',{required:true,max:100,auto:'name'}):''}${field('邮箱','email','',{type:'email',required:true,max:254,auto:'username'})}${field('密码','password','',{type:'password',required:true,min:register?12:1,max:1024,auto:register?'new-password':'current-password',help:register?'至少 12 位。':''})}<div class="form-error" role="alert" ${error?'':'hidden'}>${esc(error)}</div><button class="btn primary" style="width:100%" type="submit">${register?'注册并登录':'登录'}</button></form><div class="auth-switch" style="text-align:center;margin-top:20px">${button(register?'已有账号，去登录':'创建新账号',register?'auth-login':'auth-register','','quiet')}</div></section>`;
}
function shell(){
  $('#authRoot').hidden=true;$('#appShell').hidden=false;
  $('#nav').innerHTML=navItems.map(([id,title,ic])=>link(icon(ic)+esc(title),id,'navitem')).join('');
  $('#profile').innerHTML=`<span class="avatar">${esc(state.user.displayName?.slice(0,1)||'研')}</span><div class="profile-info"><strong>${esc(state.user.displayName)}</strong><small>实验室成员</small></div><button type="button" class="iconbtn" data-action="logout" aria-label="退出登录" title="退出登录">${icon('logout')}</button>`;
}
async function loadNext(){if(!state.user)return;try{state.next=await api('/lab/next-meeting');updateCountdown();}catch(error){if(error.status===401)showAuth('login');}}
function updateCountdown(){
  if(!state.user)return;
  const box=$('#nextMeeting');box.hidden=false;
  if(!state.next){box.removeAttribute('href');box.innerHTML='<small>下次组会</small><strong>暂无安排</strong>';box.removeAttribute('title');return;}
  const seconds=Math.max(0,Math.floor((new Date(state.next.startsAt)-Date.now())/1000));
  const days=Math.floor(seconds/86400),h=String(Math.floor(seconds/3600)%24).padStart(2,'0'),m=String(Math.floor(seconds/60)%60).padStart(2,'0'),s=String(seconds%60).padStart(2,'0');
  box.href='#meeting/'+enc(state.next.id);box.title=`${state.next.projectName} · ${state.next.title} · ${date(state.next.startsAt)}`;
  box.innerHTML=`<small>距离下次组会</small><strong>${days?days+' 天 ':''}${h}:${m}:${s}</strong>`;
  if(seconds===0&&!state.countdownRefresh){state.countdownRefresh=true;loadNext().finally(()=>state.countdownRefresh=false);}
}
function remember(type,id){api('/lab/history','POST',{targetType:type,targetId:id}).catch(()=>{});}
function projectBadge(p){return p.role?tag(roleNames[p.role]||'成员','green'):p.membershipStatus==='pending'?tag('申请中','amber'):p.membershipStatus==='rejected'?tag('申请未通过'):tag('未加入');}
function applyButton(p){return p.membershipStatus==='member'?'':p.membershipStatus==='pending'?button('等待审批','noop',p.id,'','disabled'):button(p.membershipStatus==='rejected'?'重新申请':'申请加入','join',p.id);}
async function projectsPage(){
  const result=await api('/lab/projects?scope='+state.projectScope);state.data.projects=result.items;
  return head('课题管理','创建课题，或申请加入感兴趣的课题。',button('创建课题','create-project','','primary'))+
    `<div class="tabs">${button('全部课题','project-scope','all',state.projectScope==='all'?'active':'')}${button('已加入','project-scope','joined',state.projectScope==='joined'?'active':'')}</div>`+
    (result.items.length?`<div class="grid">${result.items.map(p=>`<article class="card"><div class="card-title"><h2>${link(esc(p.name),'project/'+enc(p.id))}</h2>${projectBadge(p)}</div><p>${esc(p.description||'暂无课题简介')}</p><div class="card-footer"><span class="small">${p.memberCount} 位成员${p.pendingCount?` · ${p.pendingCount} 条待审批申请`:''}</span><div class="actions">${applyButton(p)}${link('查看','project/'+enc(p.id),'btn small')}</div></div></article>`).join('')}</div>`:empty('还没有课题',state.projectScope==='joined'?'可以从全部课题中申请加入，也可以创建自己的课题。':'创建实验室的第一个课题。'));
}
async function projectPage(id){
  const p=await api('/lab/projects/'+enc(id));state.data.project=p;remember('project',id);
  let html=link('← 返回课题管理','projects','back')+head(p.name,p.description,`${projectBadge(p)}${p.role==='owner'?button('编辑课题','edit-project',id):applyButton(p)}`);
  if(!p.role)return html+`<section class="panel">${empty(p.membershipStatus==='pending'?'加入申请正在等待审批':'加入后参与课题',p.membershipStatus==='rejected'?'可以补充申请说明后再次申请。':'负责人批准后，该课题才会出现在“我的资料”中。',applyButton(p))}</section>`;
  const members=await api(`/teams/${enc(id)}/members?pageSize=100`);state.data.members=members.items;
  const tabs=[['members','成员'],...(p.role==='owner'?[['requests',`加入申请${p.pendingCount?' · '+p.pendingCount:''}`],['assignments','任务分配']]:[])];
  if(!tabs.some(t=>t[0]===state.projectTab))state.projectTab='members';
  html+=`<div class="tabs">${tabs.map(([key,label])=>button(label,'project-tab',key,state.projectTab===key?'active':'')).join('')}</div>`;
  if(state.projectTab==='members'){
    html+=`<section class="panel">${members.items.map(m=>`<div class="row"><span class="avatar">${esc(m.displayName.slice(0,1))}</span><div class="row-main"><h3>${esc(m.displayName)}${m.id===state.user.id?' · 我':''}</h3><p>${esc(m.email)}</p></div>${tag(roleNames[m.role]||m.role)}${p.role==='owner'&&m.role!=='owner'?`<div class="actions">${button('调整角色','member-role',m.id,'small')}${button('移出','remove-member',m.id,'small quiet')}</div>`:''}</div>`).join('')}</section>`;
  }else if(state.projectTab==='requests'){
    const requests=await api(`/lab/projects/${enc(id)}/join-requests`);state.data.requests=requests.items;
    html+=`<section class="panel">${requests.items.length?requests.items.map(r=>`<div class="row"><div class="row-main"><h3>${esc(r.displayName)}</h3><p>${esc(r.email)} · ${date(r.createdAt)}</p><p>${esc(r.message||'未填写申请说明')}</p></div>${r.status==='pending'?`<div class="actions">${button('通过','approve',r.id,'small primary')}${button('拒绝','reject',r.id,'small')}</div>`:tag(r.status==='approved'?'已通过':'已拒绝',r.status==='approved'?'green':'')}</div>`).join(''):empty('暂无加入申请')}</section>`;
  }else{
    const tasks=await api(`/lab/projects/${enc(id)}/tasks`);state.data.projectTasks=tasks.items;
    html+=`<div class="section-title"><h2>课题任务</h2>${button('创建并分配任务','create-task',id,'primary')}</div><section class="panel">${tasks.items.length?tasks.items.map(t=>taskCard(t,true)).join(''):empty('还没有分配任务','创建任务并选择已加入课题的成员。')}</section>`;
  }
  return html;
}
function taskCard(t,manage=false){return `<article class="task-card"><div class="task-top"><h3>${esc(t.title)}</h3><div class="actions">${tag(taskNames[t.status]||t.status,t.status==='done'?'green':'')}${manage?button('编辑','edit-task',t.id,'small'):''}</div></div><div class="meta"><span>${esc(t.projectName)}</span>${manage?`<span>执行人：${esc(t.assigneeName)}</span>`:''}<span>截止时间：${date(t.dueAt)}</span></div>${t.description?`<p class="task-description">${esc(t.description)}</p>`:''}</article>`;}
async function tasksPage(){
  const result=await api('/lab/tasks');state.data.tasks=result.items;
  const projects=[...new Map(result.items.map(t=>[t.projectId,{id:t.projectId,name:t.projectName}])).values()];
  if(state.taskProject&&!projects.some(p=>p.id===state.taskProject))state.taskProject='';
  const visible=result.items.filter(t=>(!state.taskProject||t.projectId===state.taskProject)&&(!state.taskStatus||t.status===state.taskStatus));
  return head('我的任务','查看负责人分配给你的任务。')+`<div class="toolbar"><label for="taskProject">课题</label><select id="taskProject"><option value="">全部课题</option>${projects.map(p=>`<option value="${esc(p.id)}" ${state.taskProject===p.id?'selected':''}>${esc(p.name)}</option>`).join('')}</select><label for="taskStatus">状态</label><select id="taskStatus"><option value="">全部状态</option>${['todo','doing','done'].map(x=>`<option value="${x}" ${state.taskStatus===x?'selected':''}>${taskNames[x]}</option>`).join('')}</select></div><section class="panel">${visible.length?visible.map(t=>taskCard(t)).join(''):empty('暂无任务','任务分配后会显示在这里。')}</section>`;
}
function resourceRows(items){return items.length?items.map(r=>`<div class="row"><span class="row-icon">${icon(r.type==='recording'?'video':'file')}</span><div class="row-main">${link(esc(r.title),'resource/'+enc(r.id),'row-title')}<p>${esc(r.fileName)} · ${bytes(r.size)} · ${esc(r.ownerName)}</p></div>${link(r.type==='recording'?'播放录像':'打开','resource/'+enc(r.id),'btn small')}</div>`).join(''):empty('暂无资料','上传后，已加入课题的成员可以查看和评论。');}
async function materialsPage(id){
  await refreshJoined();
  if(!state.joined.length)return materialsTabs('project')+head('课题资料')+`<section class="panel">${empty('还没有加入课题','审批通过后，该课题的资料和组会才会出现在这里。个人文件可先存入“我的云盘”。',link('查看课题','projects','btn primary'))}</section>`;
  const p=id?state.joined.find(x=>x.id===id):state.joined[0];
  if(!p)return head('我的资料')+`<section class="panel">${empty('当前无权访问此课题','可以回到已加入课题的资料列表。',link('查看我的资料','materials','btn'))}</section>`;
  const [files,meetings]=await Promise.all([api(`/lab/projects/${enc(p.id)}/materials`),api(`/lab/projects/${enc(p.id)}/meetings`)]);state.data.materialProject=p;
  return materialsTabs('project')+head('课题资料','按课题整理资料与每次组会的记录。')+`<div class="toolbar"><label for="materialProject">课题</label><select id="materialProject">${state.joined.map(x=>`<option value="${esc(x.id)}" ${x.id===p.id?'selected':''}>${esc(x.name)}</option>`).join('')}</select></div><div class="stack"><section><div class="section-title"><h2>课题资料</h2><div class="actions">${button('从云盘引用','reference-project-file',p.id)}${button('上传资料','upload-document',p.id)}</div></div><div class="panel">${resourceRows(files.items)}</div></section><section><div class="section-title"><h2>组会记录</h2>${['owner','mentor'].includes(p.role)?button('安排组会','create-meeting',p.id):''}</div><div class="panel">${meetings.items.length?meetings.items.map(m=>`<div class="row"><span class="row-icon">${icon('meeting')}</span><div class="row-main">${link(esc(m.title),'meeting/'+enc(m.id),'row-title')}<p>${date(m.startsAt)} · ${esc(m.location||'地点待定')}</p></div>${tag(meetingNames[m.status]||m.status)}${link('资料与讨论','meeting/'+enc(m.id),'btn small')}</div>`).join(''):empty('暂无组会记录','负责人或学长可以安排一次组会。')}</div></section></div>`;
}
function commentsPanel(kind,id,items){return `<section class="panel"><div class="panelhead"><h2>${kind==='meeting'?'组会讨论':'评论'} <span class="small">${items.length}</span></h2></div>${items.length?items.map(c=>`<article class="comment"><div class="comment-meta"><span class="avatar">${esc(c.authorName?.slice(0,1)||'研')}</span><strong>${esc(c.authorName)}</strong><time>${date(c.createdAt)}</time></div><p class="body-text">${esc(c.content)}</p></article>`).join(''):empty('还没有评论','留下问题、建议或补充内容。')}<form class="comment-form" data-form="comment" data-kind="${kind}" data-id="${esc(id)}">${field('写下评论','content','',{area:true,required:true,max:10000,rows:3})}<div class="form-error" role="alert" hidden></div><div class="form-actions"><button type="submit" class="btn primary">发布评论</button></div></form></section>`;}
async function meetingPage(id){
  const [m,comments]=await Promise.all([api('/lab/meetings/'+enc(id)),api('/lab/comments/meeting/'+enc(id)),refreshJoined()]);state.data.meeting=m;remember('meeting',id);
  const role=state.joined.find(p=>p.id===m.projectId)?.role;
  return link('← 返回我的资料','materials/'+enc(m.projectId),'back')+head(m.title,`${m.projectName} · ${date(m.startsAt)}`,`${tag(meetingNames[m.status]||m.status)}${['owner','mentor'].includes(role)?button('编辑组会','edit-meeting',id):''}`)+`<div class="stack"><section class="panel padded"><div class="meta"><span>地点：${esc(m.location||'待定')}</span></div><div class="divider"></div><div class="meeting-description"><div><h3>议程</h3><p class="body-text">${esc(m.agenda||'暂无议程')}</p></div><div><h3>组会纪要</h3><p class="body-text">${esc(m.minutes||'暂无纪要')}</p></div></div></section><section><div class="section-title"><h2>本次组会资料</h2><div class="actions">${button('从云盘引用','reference-meeting-file',id)}${button('上传资料','upload-meeting-document',id)}</div></div><div class="panel">${resourceRows(m.materials)}</div></section><section><div class="section-title"><h2>组会录像</h2>${button('上传录像','upload-recording',id)}</div><div class="panel">${m.recordings.length?resourceRows(m.recordings):empty('还没有录像','将录好的视频上传后，可在这里保留和播放。')}</div></section>${commentsPanel('meeting',id,comments.items)}</div>`;
}
async function resourcePage(id){
  const [r,comments]=await Promise.all([api('/lab/resources/'+enc(id)),api('/lab/comments/resource/'+enc(id))]);state.data.resource=r;remember('resource',id);
  if(r.visibility==='private')return driveResourcePage(id,r);
  const preview='/api/v1/resources/'+enc(id)+'/preview',download='/api/v1/resources/'+enc(id)+'/download';
  let media='';
  if(r.previewType?.startsWith('video/'))media=`<div class="preview"><video controls playsinline preload="metadata" src="${preview}">当前浏览器不支持视频播放。</video><p id="videoFallback" class="small" hidden>当前浏览器无法播放此视频编码，请下载后观看。</p></div>`;
  else if(r.previewType==='application/pdf')media=`<div class="reader-link"><span>PDF 文档</span><a class="btn" href="/reader.html?id=${enc(id)}" target="_blank" rel="noopener">新窗口阅读与笔记 ↗</a></div><div class="preview"><iframe title="PDF 文档预览" src="/pdfjs/web/viewer.html?file=${enc(preview)}"></iframe></div>`;
  else if(r.previewType?.startsWith('image/'))media=`<div class="preview"><img src="${preview}" alt="${esc(r.title)}"></div>`;
  else if(r.previewType?.startsWith('text/'))media=`<div class="preview"><iframe title="文本资料预览" src="${preview}"></iframe></div>`;
  else media=`<div class="panel">${empty('下载查看此文件',r.fileName,`<a class="btn" href="${download}">下载文件</a>`)}</div>`;
  return link('← 返回'+(r.meetingId?'组会':'我的资料'),r.meetingId?'meeting/'+enc(r.meetingId):'materials/'+enc(r.projectId),'back')+head(r.title,`${r.fileName} · ${bytes(r.size)} · ${r.ownerName}`,`<a class="btn" href="${download}">下载文件</a>`)+`<div class="stack">${media}${r.description?`<section class="panel padded"><h2 style="margin-bottom:12px">资料说明</h2><p class="body-text">${esc(r.description)}</p></section>`:''}${commentsPanel('resource',id,comments.items)}</div>`;
}
async function messagesPage(){
  const result=await api('/lab/messages');state.data.messages=result.items;
  return head('学长留言','所有登录成员都可以分享经验、建议与提醒。',result.canPublish?button('写留言','create-message','','primary'):'')+`<section class="panel">${result.items.length?result.items.map(m=>`<article class="row"><span class="avatar">${esc(m.authorName?.slice(0,1)||'研')}</span><div class="row-main">${link(esc(m.title),'message/'+enc(m.id),'row-title')}<p>${esc(m.content.slice(0,140))}${m.content.length>140?'…':''}</p><p>${esc(m.authorName)} · ${date(m.createdAt)}</p></div>${link('阅读','message/'+enc(m.id),'btn small')}</article>`).join(''):empty('还没有学长留言','写下第一条留言，登录后的实验室成员都可以阅读和评论。')}</section>`;
}
async function messagePage(id){
  const [m,comments]=await Promise.all([api('/lab/messages/'+enc(id)),api('/lab/comments/message/'+enc(id))]);state.data.message=m;remember('message',id);
  return link('← 返回学长留言','messages','back')+head(m.title,`${m.authorName} · ${date(m.createdAt)}`,m.authorId===state.user.id?button('编辑','edit-message',id)+button('删除','delete-message',id,'quiet'):'')+`<div class="stack"><article class="panel padded"><p class="body-text">${esc(m.content)}</p></article>${commentsPanel('message',id,comments.items)}</div>`;
}
async function historyPage(){
  const result=await api('/lab/history');const types={project:['课题','project','projects'],meeting:['组会','meeting','meeting'],resource:['资料','resource','file'],message:['留言','message','message']};
  return head('历史记录','你最近浏览过的内容。',result.items.length?button('清空记录','clear-history','','quiet'):'')+`<section class="panel">${result.items.length?result.items.map(h=>{const [type,route,ic]=types[h.targetType]||['内容','projects','file'];return `<div class="row"><span class="row-icon">${icon(ic)}</span><div class="row-main">${link(esc(h.title),route+'/'+enc(h.targetId),'row-title')}<p>${type}${h.projectName?' · '+esc(h.projectName):''}</p></div><span class="small">${date(h.visitedAt)}</span></div>`;}).join(''):empty('暂无浏览记录','打开课题、资料、组会或留言后，会自动记录在这里。')}</section>`;
}
async function render(){
  if(!state.user)return;
  const sequence=++state.seq;state.sequence=sequence;const parts=(location.hash.slice(1)||'home').split('/');const page=parts[0];const id=decodeURIComponent(parts[1]||'');state.page=page==='drive'?'resources':page;
  const module=({project:'projects',meeting:'materials',resource:'materials','drive-file':'materials',drive:'materials',message:'messages'})[page]||page;
  if(typeof closeDriveMenu==='function')closeDriveMenu();
  document.querySelectorAll('.navitem').forEach(a=>{const active=a.hash==='#'+module;a.classList.toggle('active',active);if(active)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
  $('#sidebar').classList.remove('open');$('#overlay').hidden=true;$('#menuToggle').setAttribute('aria-expanded','false');
  $('#content').className='content'+(page==='home'?' home':'');$('#pageLabel').textContent=page==='home'?'':navItems.find(x=>x[0]===module)?.[1]||'';document.title=(navItems.find(x=>x[0]===module)?.[1]||'首页')+' · 研途';
  if(page==='home'){$('#content').innerHTML='';loadNext();return;}
  $('#content').innerHTML='<div class="loading" role="status">加载中…</div>';
  try{
    const pages={projects:projectsPage,project:()=>projectPage(id),materials:()=>materialsPage(id),drive:()=>drivePages.resources(id),'drive-file':()=>driveResourcePage(id),meeting:()=>meetingPage(id),resource:()=>resourcePage(id),tasks:tasksPage,history:historyPage,messages:messagesPage,message:()=>messagePage(id)};
    if(!pages[page]){navigate('home');return;}
    const html=await pages[page]();if(sequence!==state.seq||!state.user)return;
    $('#content').innerHTML=html;window.scrollTo(0,0);
    $('#content video')?.addEventListener('error',()=>{const note=$('#videoFallback');if(note)note.hidden=false;});
  }catch(error){
    if(sequence!==state.seq)return;
    if(error.status===401){showAuth('login','登录已过期，请重新登录。');return;}
    $('#content').innerHTML=`<div class="errorbox" role="alert">${esc(error.message)} ${button('重试','retry')}</div>`;
  }
}

function taskForm(task=null){
  const p=state.data.project;
  formModal(task?'编辑任务':'创建并分配任务',task?'edit-task':'create-task',
    field('任务名称','title',task?.title||'',{required:true,max:200})+field('任务说明','description',task?.description||'',{area:true,max:20000})+
    selectField('分配给','assigneeId',state.data.members.map(m=>({id:m.id,name:m.displayName})),task?.assigneeId||state.data.members[0]?.id)+
    field('截止时间','dueAt',localDate(task?.dueAt),{type:'datetime-local'})+
    (task?selectField('状态','status',['todo','doing','done'].map(x=>({id:x,name:taskNames[x]})),['todo','doing','done'].includes(task.status)?task.status:'doing'):''),
    task?.id||p.id,task?'保存':'创建任务',`data-project="${esc(p.id)}"`);
}
function meetingForm(meeting=null){
  const projectId=meeting?.projectId||state.data.materialProject.id;
  formModal(meeting?'编辑组会':'安排组会',meeting?'edit-meeting':'create-meeting',
    field('组会主题','title',meeting?.title||'',{required:true,max:200})+
    field('开始时间','startsAt',localDate(meeting?.startsAt),{type:'datetime-local',required:true})+
    field('地点','location',meeting?.location||'',{max:200})+
    field('议程','agenda',meeting?.agenda||'',{area:true,max:20000})+
    (meeting?field('组会纪要','minutes',meeting.minutes||'',{area:true,max:50000})+selectField('状态','status',Object.entries(meetingNames).map(([id,name])=>({id,name})),meeting.status):''),
    meeting?.id||projectId,meeting?'保存':'安排组会',`data-project="${esc(projectId)}"`);
}
function uploadForm(recording=false,meeting=false){
  const projectId=meeting?state.data.meeting.projectId:state.data.materialProject.id;
  const meetingId=meeting?state.data.meeting.id:'';
  const accept=recording?'.mp4,.webm,.mov,.m4v,.avi,.mkv':'.pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.txt,.md,.csv,.png,.jpg,.jpeg,.gif,.webp,.zip';
  formModal(recording?'上传组会录像':'上传资料','upload',
    `<p class="small" style="margin-bottom:20px">仅已加入本课题的成员可查看。${recording?'单个录像最多 1 GiB。':'单个文件最多 20 MiB。'}</p>`+
    field(recording?'录像文件':'文件','file','',{type:'file',required:true,accept})+field('标题（可选）','title','',{max:200})+field('说明（可选）','description','',{area:true,max:10000})+
    '<div class="upload-progress" hidden><progress max="100" value="0"></progress><p>等待上传…</p></div>',projectId,'上传',`data-meeting="${esc(meetingId)}" data-recording="${recording?'1':'0'}"`);
}
async function action(name,id,element){
  if(typeof labCloudAction==='function'&&await labCloudAction(name,id,element))return;
  if(typeof cloudAction==='function'&&await cloudAction(name,id,element))return;
  if(name==='noop')return;
  if(name==='close'){closeModal();return;}
  if(name==='auth-login'||name==='auth-register'){showAuth(name==='auth-login'?'login':'register');return;}
  if(name==='retry'){await render();return;}
  if(name==='logout'){await api('/auth/logout','POST',{});state.data={};state.joined=[];showAuth('login');return;}
  if(name==='project-scope'){state.projectScope=id;await render();return;}
  if(name==='project-tab'){state.projectTab=id;await render();return;}
  if(name==='create-project'){formModal('创建课题','create-project',field('课题名称','name','',{required:true,max:100})+field('课题简介','description','',{area:true,max:10000}),'','创建课题');return;}
  if(name==='edit-project'){const p=state.data.project;formModal('编辑课题','edit-project',field('课题名称','name',p.name,{required:true,max:100})+field('课题简介','description',p.description,{area:true,max:10000}),id);return;}
  if(name==='join'){formModal('申请加入课题','join',field('申请说明','message','',{area:true,max:3000,help:'申请将交给课题负责人审批。'}),id,'提交申请');return;}
  if(name==='approve'||name==='reject'){await api(`/lab/projects/${enc(state.data.project.id)}/join-requests/${enc(id)}/decision`,'POST',{decision:name==='approve'?'approved':'rejected'});toast(name==='approve'?'已通过加入申请':'已拒绝加入申请');await render();return;}
  if(name==='member-role'){const m=state.data.members.find(x=>x.id===id);formModal('调整成员角色','member-role',`<p style="margin-bottom:18px">${esc(m.displayName)}</p>`+selectField('角色','role',[{id:'student',name:'成员'},{id:'mentor',name:'学长'}],m.role),id);return;}
  if(name==='remove-member'){const m=state.data.members.find(x=>x.id===id);formModal('移出课题','remove-member',`<p>将 ${esc(m.displayName)} 移出当前课题。移出后，该成员无法继续查看课题资料和组会。</p>`,id,'确认移出');return;}
  if(name==='create-task'){taskForm();return;}
  if(name==='edit-task'){taskForm(state.data.projectTasks.find(x=>x.id===id));return;}
  if(name==='create-meeting'){meetingForm();return;}
  if(name==='edit-meeting'){meetingForm(state.data.meeting);return;}
  if(name==='upload-document'){uploadForm();return;}
  if(name==='upload-meeting-document'){uploadForm(false,true);return;}
  if(name==='upload-recording'){uploadForm(true,true);return;}
  if(name==='create-message'||name==='edit-message'){
    const m=name==='edit-message'?state.data.message:null;
    formModal(m?'编辑留言':'写留言',name,field('标题','title',m?.title||'',{required:true,max:200})+field('留言内容','content',m?.content||'',{required:true,area:true,max:50000,rows:7,help:'所有登录成员可见。'}),m?.id||'',m?'保存':'发布留言');return;
  }
  if(name==='delete-message'){formModal('删除留言','delete-message','<p>确认删除这条留言及其评论？</p>',id,'删除');return;}
  if(name==='clear-history'){formModal('清空浏览记录','clear-history','<p>清空你自己的浏览记录，原始内容仍然保留。</p>','','清空');}
}
function uploadFile(form){
  const file=form.elements.file.files[0];if(!file)return Promise.reject(new Error('请选择文件。'));
  const limit=form.dataset.recording==='1'?1073741824:20971520;
  if(file.size>limit)return Promise.reject(new Error(`文件超过${form.dataset.recording==='1'?' 1 GiB':' 20 MiB'}的大小限制。`));
  const body=new FormData(form);body.delete('file');body.append('file',file);
  if(form.dataset.meeting)body.append('meetingId',form.dataset.meeting);
  const progress=form.querySelector('.upload-progress');progress.hidden=false;
  return new Promise((resolve,reject)=>{
    const xhr=new XMLHttpRequest();state.upload=xhr;xhr.open('POST',`/api/v1/lab/projects/${enc(form.dataset.id)}/materials`);xhr.withCredentials=true;
    xhr.upload.addEventListener('progress',event=>{if(event.lengthComputable){const amount=Math.round(event.loaded/event.total*100);progress.querySelector('progress').value=amount;progress.querySelector('p').textContent=amount===100?'上传完成，正在保存…':`正在上传 ${amount}%`;}});
    xhr.addEventListener('load',()=>{state.upload=null;let result;try{result=JSON.parse(xhr.responseText);}catch{reject(new Error('服务器响应异常，请稍后重试。'));return;}if(xhr.status>=200&&xhr.status<300)resolve(result.data);else reject(new Error(result.message||'上传失败，请重试。'));});
    xhr.addEventListener('error',()=>{state.upload=null;reject(new Error('网络连接中断，请重试。'));});
    xhr.addEventListener('abort',()=>{state.upload=null;reject(new Error('上传已取消。'));});xhr.send(body);
  });
}
async function submit(form){
  const kind=form.dataset.form,id=form.dataset.id,data=Object.fromEntries(new FormData(form));let result;
  if(typeof labCloudSubmit==='function'&&await labCloudSubmit(form))return;
  if(typeof cloudSubmit==='function'&&await cloudSubmit(form))return;
  if(kind==='login'||kind==='register'){
    if(kind==='register')await api('/auth/register','POST',data);
    result=await api('/auth/login','POST',{email:data.email,password:data.password});state.user=result.user;state.data={};await refreshJoined();shell();await loadNext();navigate('home');return;
  }
  if(kind==='create-project'){result=await api('/lab/projects','POST',data);await refreshJoined();closeModal();state.projectTab='members';navigate('project/'+enc(result.id));toast('课题已创建');return;}
  if(kind==='edit-project')await api('/lab/projects/'+enc(id),'PATCH',data);
  else if(kind==='join')await api(`/lab/projects/${enc(id)}/join-requests`,'POST',data);
  else if(kind==='member-role')await api(`/teams/${enc(state.data.project.id)}/members/${enc(id)}`,'PATCH',data);
  else if(kind==='remove-member')await api(`/teams/${enc(state.data.project.id)}/members/${enc(id)}`,'DELETE');
  else if(kind==='create-task'||kind==='edit-task'){
    data.dueAt=data.dueAt?new Date(data.dueAt).toISOString():null;
    await api(`/lab/projects/${enc(form.dataset.project)}/tasks${kind==='edit-task'?'/'+enc(id):''}`,kind==='edit-task'?'PATCH':'POST',data);
  }else if(kind==='create-meeting'||kind==='edit-meeting'){
    data.startsAt=new Date(data.startsAt).toISOString();
    result=await api(kind==='create-meeting'?`/lab/projects/${enc(form.dataset.project)}/meetings`:'/lab/meetings/'+enc(id),kind==='create-meeting'?'POST':'PATCH',data);
    closeModal();await loadNext();navigate('meeting/'+enc(result.id));toast('组会已保存');return;
  }else if(kind==='upload'){await uploadFile(form);}
  else if(kind==='comment'){await api(`/lab/comments/${enc(form.dataset.kind)}/${enc(id)}`,'POST',data);toast('评论已发布');await render();return;}
  else if(kind==='create-message'||kind==='edit-message'){
    result=await api('/lab/messages'+(kind==='edit-message'?'/'+enc(id):''),kind==='edit-message'?'PATCH':'POST',data);
    closeModal();navigate('message/'+enc(result.id));toast('留言已保存');return;
  }else if(kind==='delete-message'){await api('/lab/messages/'+enc(id),'DELETE');closeModal();navigate('messages');toast('留言已删除');return;}
  else if(kind==='clear-history')await api('/lab/history','DELETE');
  else throw new Error('未识别的操作。');
  closeModal();toast(kind==='join'?'加入申请已提交':'已保存');await render();
}
document.addEventListener('click',async event=>{
  const element=event.target.closest('[data-action]');if(!element||element.disabled)return;
  event.preventDefault();element.disabled=true;
  try{await action(element.dataset.action,element.dataset.id||'',element);}catch(error){if(error.status===401)showAuth('login','请重新登录。');else toast(error.message,true);}finally{if(element.isConnected)element.disabled=false;}
});
document.addEventListener('submit',async event=>{
  const form=event.target;if(!form.matches('form[data-form]'))return;event.preventDefault();if(form.dataset.busy)return;
  form.dataset.busy='1';const buttons=[...form.querySelectorAll('[type=submit]')];buttons.forEach(x=>x.disabled=true);const errorBox=form.querySelector('.form-error');if(errorBox)errorBox.hidden=true;
  try{await submit(form);}catch(error){if(form.isConnected&&errorBox){errorBox.textContent=error.message;errorBox.hidden=false;}else toast(error.message,true);}finally{delete form.dataset.busy;buttons.forEach(x=>x.disabled=false);}
});
document.addEventListener('change',event=>{
  if(event.target.id==='materialProject')navigate('materials/'+enc(event.target.value));
  if(event.target.id==='taskProject'){state.taskProject=event.target.value;render();}
  if(event.target.id==='taskStatus'){state.taskStatus=event.target.value;render();}
});
$('#closeModal').addEventListener('click',closeModal);
$('#modal').addEventListener('cancel',event=>{event.preventDefault();closeModal();});
$('#menuToggle').addEventListener('click',()=>{const open=$('#sidebar').classList.toggle('open');$('#overlay').hidden=!open;$('#menuToggle').setAttribute('aria-expanded',String(open));});
$('#overlay').addEventListener('click',()=>{$('#sidebar').classList.remove('open');$('#overlay').hidden=true;$('#menuToggle').setAttribute('aria-expanded','false');});
window.addEventListener('hashchange',render);
setInterval(updateCountdown,1000);setInterval(loadNext,60000);
async function boot(){
  try{state.user=await api('/me');await refreshJoined();shell();await loadNext();await render();}
  catch(error){showAuth('login',error.status===401?'':error.message);}
}
window.addEventListener('DOMContentLoaded',boot,{once:true});
