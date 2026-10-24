'use strict';

// Adapt the upstream drive UI to the laboratory's six-module shell.
const drivePages = {};
const typeNames = {paper:'论文',note:'笔记',slides:'组会材料',other:'其他',tutorial:'教程',experience:'经验',template:'模板'};
const btn = button, datetime = date, openModal = modal, renderPage = render, handleAction = action;
const $$ = (selector, root=document) => [...root.querySelectorAll(selector)];
const values = form => Object.fromEntries(new FormData(form));
const modalForm = (title,kind,fields,submit='保存',id='') => formModal(title,kind,fields,id,submit);
const form = (kind,fields,submit='保存',id='') => `<form data-form="${kind}" data-id="${esc(id)}">${fields}<div class="form-error" role="alert" hidden></div><div class="form-actions"><button class="btn primary" type="submit">${submit}</button></div></form>`;
function materialsTabs(active){return `<div class="tabs materials-tabs">${link('课题资料','materials','btn '+(active==='project'?'active':''))}${link('我的云盘','drive','btn '+(active==='drive'?'active':''))}</div>`;}
Object.assign(paths,{
  plus:'<path d="M12 5v14M5 12h14"/>', upload:'<path d="M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6"/>',
  download:'<path d="M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4"/>',search:'<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/>',
  cloud:'<path d="M6 18a5 5 0 0 1-1-10 7 7 0 0 1 13-1 5 5 0 0 1 0 11z"/>',right:'<path d="m9 5 7 7-7 7"/>',
  back:'<path d="m10 5-7 7 7 7M3 12h18"/>',people:'<circle cx="9" cy="7" r="4"/><path d="M2 21v-3a7 7 0 0 1 14 0v3M17 3a4 4 0 0 1 0 8M19 14a6 6 0 0 1 3 5v2"/>'
});

async function driveMembers(projectId){
  let items=[],page=1,result;
  do{result=await api(`/teams/${enc(projectId)}/members?pageSize=100&page=${page++}`);items.push(...result.items);}while(items.length<result.total);
  return items;
}
function resourceMedia(r){
  const preview=`/api/v1/resources/${enc(r.id)}/preview`;
  if(r.previewType==='application/pdf')return `<div class="reader-link"><span>PDF 文档</span><a class="btn" href="/reader.html?id=${enc(r.id)}" target="_blank" rel="noopener">新窗口阅读与笔记 ↗</a></div><div class="preview"><iframe title="PDF 文档预览" src="/pdfjs/web/viewer.html?file=${enc(preview)}"></iframe></div>`;
  if(r.previewType?.startsWith('image/'))return `<div class="preview"><img src="${preview}" alt="${esc(r.title)}"></div>`;
  if(r.previewType?.startsWith('text/'))return `<div class="preview"><iframe title="文本资料预览" src="${preview}"></iframe></div>`;
  return `<div class="panel">${empty('此格式请下载后查看',r.fileName)}</div>`;
}
async function driveResourcePage(id,resource=null){
  const [r,versions]=await Promise.all([resource||api('/resources/'+enc(id)),api(`/resources/${enc(id)}/versions?pageSize=100`)]);
  state.data.resource=r;remember('resource',id);
  const controls=(r.canEdit?button('编辑说明','edit-resource',id)+button('上传新版本','resource-version',id)+button('共享管理','cloud-shares',id):'')+button('下载','download-resource',id,'primary');
  return materialsTabs('drive')+link('← 返回文件列表',state.driveReturn||'drive','back')+head(r.title,`${r.fileName} · ${bytes(r.size)} · ${r.ownerName||r.owner}`,controls)+
    `<div class="stack">${resourceMedia(r)}<section class="panel padded"><h2>文件说明</h2><p class="body-text mt16">${esc(r.description||'暂无说明')}</p><div class="meta mt16">${tag(typeNames[r.type]||'文件')}<span>v${r.version}</span><span>${r.canEdit?'个人文件，默认私有；可明确授权给同课题成员。':'共享文件，只读访问。'}</span></div></section><section class="panel"><div class="panelhead"><h2>历史版本</h2></div>${[...versions.items].reverse().map(v=>`<div class="row"><div class="row-main"><h3>v${v.version} · ${esc(v.author||r.ownerName||r.owner)}</h3><p>${date(v.createdAt)} · ${bytes(v.size)} · ${esc(v.note||'首次上传')}</p></div>${button('下载此版本','download-version',v.id,'small')}</div>`).join('')||empty('暂无历史版本')}</section></div>`;
}
async function download(path,fallback='文件'){
  const response=await fetch('/api/v1'+path,{credentials:'same-origin'});
  if(!response.ok){const result=await response.json().catch(()=>({}));const error=new Error(result.message||'下载失败，请重试');error.status=response.status;throw error;}
  const disposition=response.headers.get('Content-Disposition')||'';
  let filename=fallback;
  const encoded=disposition.match(/filename\*=UTF-8''([^;]+)/i);
  if(encoded){try{filename=decodeURIComponent(encoded[1]);}catch{}}
  const url=URL.createObjectURL(await response.blob()),anchor=document.createElement('a');
  anchor.href=url;anchor.download=filename;document.body.append(anchor);anchor.click();anchor.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
async function openLabReference(projectId,meetingId=''){
  const [files,members]=await Promise.all([allDriveFiles('mine'),driveMembers(projectId)]);
  if(!files.length){modal('从云盘引用','<p>云盘中还没有文件，请先上传。</p><div class="form-actions">'+link('打开我的云盘','drive','btn primary')+'</div>');return;}
  state.cloudReference={projectId,meetingId};
  formModal('从云盘引用','lab-reference',selectField('我的文件','resourceId',files.map(x=>({id:x.id,name:x.title})))+
    `<div class="notice">确认后，将向本课题当前 ${members.length} 位成员授予所选文件的只读访问权限。文件保留在你的云盘中，后续版本会同步展示；你可以在共享管理中撤销授权。后续加入的成员需另行授权。</div><p class="small mt16">当前成员：${esc(members.map(x=>x.displayName).join('、'))}</p>`,'','确认授权并引用');
}
async function labCloudAction(name,id,element){
  if(name==='upload-resource'){await openCloudUpload();return true;}
  if(name==='edit-resource'||name==='resource-version'){
    const r=await api('/resources/'+enc(id));state.data.resource=r;
    if(name==='edit-resource')formModal('编辑文件说明','edit-resource',field('名称','title',r.title,{required:true,max:200})+field('说明','description',r.description,{area:true,max:50000})+field('标签（逗号分隔）','tags',(r.tags||[]).join(',')),id);
    else formModal('上传新版本','resource-version',field('版本说明','note','',{area:true,max:50000})+field('选择新文件','file','',{type:'file',required:true,accept:'.pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.txt,.md,.png,.jpg,.jpeg,.zip'})+'<p class="small">单个文件最多 20 MiB，旧版本将保留。</p>',id,'上传新版本');
    return true;
  }
  if(name==='download-resource'){await download(`/resources/${enc(id)}/download`);return true;}
  if(name==='download-version'){await download(`/resources/${enc(state.data.resource.id)}/download?versionId=${enc(id)}`);return true;}
  if(name==='reference-project-file'){await openLabReference(id);return true;}
  if(name==='reference-meeting-file'){const meeting=state.data.meeting;await openLabReference(meeting.projectId,meeting.id);return true;}
  return false;
}
async function labCloudSubmit(element){
  const kind=element.dataset.form,id=element.dataset.id,data=values(element);
  if(kind==='edit-resource'){data.tags=data.tags.split(',').map(x=>x.trim()).filter(Boolean);await api('/resources/'+enc(id),'PATCH',data);}
  else if(kind==='resource-version'){const file=element.elements.file.files[0];if(!file||file.size>20971520)throw new Error('请选择不超过 20 MiB 的文件');await api(`/resources/${enc(id)}/versions`,'POST',new FormData(element));}
  else if(kind==='lab-reference'){const target=state.cloudReference;await api(`/lab/projects/${enc(target.projectId)}/materials/references`,'POST',{resourceId:data.resourceId,meetingId:target.meetingId,grantReadAccess:true});}
  else return false;
  closeModal();toast('已保存');await render();return true;
}
document.addEventListener('change',event=>{if(event.target.name==='shareProject'){state.driveShareProject=event.target.value;openShares(state.activeShareResource).catch(e=>toast(e.message,true));}});
document.addEventListener('click',event=>{if(event.target.closest('#modal a[href^="#"]'))closeModal();});
