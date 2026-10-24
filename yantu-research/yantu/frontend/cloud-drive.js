'use strict';
async function allDriveFiles(scope='all',extra='') {let page=1,items=[],data;do{data=await api(`/me/drive/available-resources?scope=${enc(scope)}&pageSize=100&page=${page++}${extra}`);items.push(...data.items);}while(items.length<data.total);return items;}
function driveFolderOptions(items){const byId=new Map(items.map(x=>[x.id,x]));return [{id:'',name:'我的文件 / 根目录'},...items.map(x=>{const names=[x.name];let p=byId.get(x.parentId),seen=new Set([x.id]);while(p&&!seen.has(p.id)){seen.add(p.id);names.unshift(p.name);p=byId.get(p.parentId);}return {id:x.id,name:'我的文件 / '+names.join(' / ')};}).sort((a,b)=>a.name.localeCompare(b.name,'zh-CN'))];}
function driveUrl(scope='mine',folder='',q='',page=1,file=''){return 'resources/'+enc(JSON.stringify({scope,folder,q,page,...(file?{file}:{})}));}
function driveFileUrl(file){return 'resource/'+enc(file.id);}
function driveFileLink(label,file,cls='filename'){return `<a class="${cls}" href="#${driveFileUrl(file)}" target="_blank" rel="noopener">${label}</a>`;}
function driveIsShared(item){return !!item?.ownerId&&item.ownerId!==state.user?.id;}
function driveSourceBadge(item){return driveIsShared(item)?`<span class="drive-source-badge" title="来自共享" aria-label="来自共享">${icon('cloud')}</span>`:'';}
function driveTreeIcon(item,kind){return `<span class="drive-tree-icon">${driveSourceBadge(item)}${icon(kind)}</span>`;}
function driveTreeMarkup(folders,files,view){
  const groups=new Map(),documents=new Map(),collapsed=state.driveTreeCollapsed ||= new Set();
  for(const folder of folders){const key=folder.parentId||'';if(!groups.has(key))groups.set(key,[]);groups.get(key).push(folder);}
  for(const file of files){const key=file.folderId||'';if(!documents.has(key))documents.set(key,[]);documents.get(key).push(file);}
  for(const items of groups.values())items.sort((a,b)=>a.name.localeCompare(b.name,'zh-CN'));
  for(const items of documents.values())items.sort((a,b)=>a.title.localeCompare(b.title,'zh-CN'));
  const renderChildren=(parent,ancestors)=>[
    ...(groups.get(parent)||[]).filter(folder=>!ancestors.has(folder.id)).map(folder=>{
      const hasChildren=!!(groups.get(folder.id)?.length||documents.get(folder.id)?.length),expanded=!collapsed.has(folder.id);
      const toggle=hasChildren?`<button type="button" class="drive-tree-toggle" data-action="cloud-tree-toggle" data-id="${esc(folder.id)}" aria-label="${expanded?'收起':'展开'}${esc(folder.name)}" aria-expanded="${expanded}"></button>`:'<span class="drive-tree-spacer" aria-hidden="true"></span>';
      const next=new Set(ancestors);next.add(folder.id);
      return `<div class="drive-tree-node" data-drive-id="${esc(folder.id)}"><div class="drive-tree-row">${toggle}${link(driveTreeIcon(folder,'folder')+'<span>'+esc(folder.name)+'</span>',driveUrl('mine',folder.id),'drive-tree-link '+(view.folder===folder.id?'active':''))}</div>${hasChildren?`<div class="drive-tree-children" ${expanded?'':'hidden'}>${renderChildren(folder.id,next)}</div>`:''}</div>`;
    }),
    ...(documents.get(parent)||[]).map(file=>`<div class="drive-tree-node drive-tree-file-node" data-drive-id="${esc(file.id)}"><div class="drive-tree-row"><span class="drive-tree-spacer" aria-hidden="true"></span>${driveFileLink(driveTreeIcon(file,'file')+'<span>'+esc(file.title)+'</span>',file,'drive-tree-link drive-tree-file')}</div></div>`)
  ].join('');
  const expanded=!collapsed.has('root');
  return `<div class="drive-tree-node drive-tree-root"><div class="drive-tree-row"><button type="button" class="drive-tree-toggle" data-action="cloud-tree-toggle" data-id="root" aria-label="${expanded?'收起':'展开'}我的文件" aria-expanded="${expanded}"></button>${link(driveTreeIcon(null,'folder')+'<span>我的文件</span>',driveUrl('mine'),'drive-tree-link '+(!view.folder&&!view.file?'active':''))}</div><div class="drive-tree-children" ${expanded?'':'hidden'}>${renderChildren('',new Set())}</div></div>`;
}
pages.resources = async raw => {
  let view = {scope:'mine',folder:'',q:'',page:1,file:''};
  try {Object.assign(view,JSON.parse(decodeURIComponent(raw||'')));} catch {}
  if(view.scope!=='mine'){view.scope='mine';view.folder='';}
  if(view.file){state.driveReturn=driveUrl(view.scope,view.folder,view.q,view.page);navigate(driveFileUrl({id:view.file}));return '';}
  const seq=state.sequence;
  const [tree,data]=await Promise.all([
    api('/me/drive/folders/tree?includeShared=true'),
    api(!view.q
      ? `/me/drive/children?folderId=${enc(view.folder)}&includeShared=true&page=${view.page}&pageSize=50`
      : `/me/drive/search?scope=all&q=${enc(view.q)}&page=${view.page}&pageSize=50`)
  ]);
  if(seq!==state.sequence)return '';
  closeDriveMenu();
  state.driveView=view;state.driveFolder=view.folder;state.driveReturn=driveUrl(view.scope,view.folder,view.q,view.page);
  state.data.driveItems=data.items;state.data.driveTree=tree.items;state.data.driveTreeFiles=tree.files||[];
  state.data.resource=null;
  state.driveTreeCollapsed ||= new Set();
  if(view.folder){const byId=new Map(tree.items.map(x=>[x.id,x])),seen=new Set();let current=view.folder;state.driveTreeCollapsed.delete('root');while(current&&!seen.has(current)){seen.add(current);state.driveTreeCollapsed.delete(current);current=byId.get(current)?.parentId;}}
  const folders=driveTreeMarkup(tree.items,tree.files||[],view);
  const path=data.breadcrumbs||[{id:null,name:'我的文件'}];
  const search=`<div class="drive-search-wrap"><button type="button" class="btn drive-search-trigger" data-action="cloud-search-toggle" aria-label="搜索文件（Ctrl+F）" aria-expanded="false" aria-controls="driveSearchPopover" title="搜索文件 · Ctrl+F">${icon('search')}</button><form id="driveSearchPopover" data-form="cloud-search" class="drive-search-popover" role="search" hidden><label for="driveSearchInput">搜索文件</label><div><input id="driveSearchInput" class="input" name="q" value="${esc(view.q)}" placeholder="输入文件名" autocomplete="off"><button class="btn primary" type="submit">搜索</button></div></form></div>`;
  const rows=data.items.length?data.items.map(x=>driveRow(x,view)).join(''):`<tr class="drive-empty-row"><td colspan="3">${empty(view.q?'没有搜索结果':'这个文件夹还是空的','',!view.q?btn(icon('plus')+'新建文件夹','cloud-new'):'','folder')}</td></tr>`;
  const breadcrumbs=`<nav class="drive-breadcrumb" aria-label="文件位置">${path.map((x,i)=>i===path.length-1?`<strong>${esc(x.name)}</strong>`:link(esc(x.name),driveUrl(view.scope,x.id||''))).join(icon('right'))}</nav>`;
  const pagination=data.total>50?`<div class="drive-list-foot"><span>第 ${view.page} 页 · 共 ${data.total} 项</span><div>${view.page>1?link('上一页',driveUrl(view.scope,view.folder,view.q,view.page-1),'btn sm'):''}${view.page*50<data.total?link('下一页',driveUrl(view.scope,view.folder,view.q,view.page+1),'btn sm'):''}</div></div>`:'';
  const folder=tree.items.find(x=>x.id===view.folder);
  const inspector=`<aside class="drive-inspector" aria-label="当前目录信息"><h2>${esc(folder?.name||'我的文件')}</h2><div class="drive-inspector-art">${icon('folder')}</div><div class="drive-inspector-facts"><div><span>类型</span><strong>文件夹</strong></div><div><span>所有者</span><strong>我</strong></div><div><span>内容</span><strong>${data.total} 项</strong></div>${folder?.createdAt?`<div><span>创建时间</span><strong>${date(folder.createdAt)}</strong></div>`:''}</div></aside>`;
  return `<div class="drive-page"><div class="drive-layout panel"><details class="drive-tree" open><summary>文件目录 <span>${tree.items.length+(tree.files||[]).length} 项</span></summary><nav id="driveTreeItems" aria-label="我的文件目录">${folders}</nav></details><section class="drive-workspace"><div class="drive-workspace-top">${breadcrumbs}${search}</div><div class="drive-actionbar">${btn(icon('plus')+'新建 '+icon('right'),'cloud-create-menu','','drive-action')}${btn(icon('upload')+'上传文件','upload-resource','','drive-action')}</div><div class="drive-main-grid"><section class="drive-content">${view.q?`<div class="drive-search-state"><strong>搜索结果</strong><span class="drive-query">${icon('search')}<span>${esc(view.q)}</span><a class="drive-query-clear" href="#${driveUrl(view.scope,view.folder)}" aria-label="清除搜索">×</a></span></div>`:''}<div class="drive-list-panel"><div class="tablewrap drive-table-wrap"><table class="drive-table"><thead><tr><th>名称</th><th>添加时间</th><th><span class="sr-only">操作</span></th></tr></thead><tbody>${rows}</tbody></table></div>${pagination}</div></section>${inspector}</div></section></div></div>`;
};
function drivePreview(r,versions,view){
  const canEdit=r.canEdit??r.ownerId===state.user.id;
  const back=driveUrl(view.scope,view.folder,view.q,view.page);
  const actions=`${canEdit?btn('编辑说明','edit-resource',r.id,'sm')+btn('上传新版本','resource-version',r.id,'sm')+btn('共享管理','cloud-shares',r.id,'sm'):''}${btn(icon('download')+'下载文件','download-resource',r.id,'sm')}`;
  return `<div class="drive-preview"><div class="drive-preview-head"><div>${link(icon('back')+'返回文件列表',back,'textbutton')}<h2>${driveSourceBadge(r)}${esc(r.title)}</h2></div><div class="drive-preview-actions">${actions}</div></div><div class="drive-preview-layout"><div class="drive-preview-main">${resourcePreview(r)}<section class="panel padded"><h3>阅读建议与使用说明</h3><div class="rich-section mt16">${para(r.description||'维护人还没有补充阅读建议。')}</div><div class="resource-detail-grid mt16"><div><p class="small">文件名称</p><p class="body-text">${esc(r.fileName||r.title)}</p></div><div><p class="small">版本</p><p>v${esc(r.version||1)}</p></div></div></section><section class="panel padded"><h3>版本记录</h3>${versions.length?[...versions].reverse().map(v=>`<div class="version-item"><div class="between"><strong>v${esc(v.version||v.number||1)} · ${esc(v.owner||v.author||r.owner)}</strong>${btn('下载','download-version',v.id,'sm')}</div><p class="small">${v.createdAt?datetime(v.createdAt):''} · ${bytes(v.size)}</p><p>${esc(v.note||'首次上传')}</p></div>`).join(''):'<p class="small mt16">当前文件为初始版本</p>'}</section></div><aside class="drive-preview-aside"><section class="panel padded"><h3>关联内容</h3><div class="detail-list mt16">${r.meetingId?link(icon('calendar')+'关联组会'+icon('right'),'meeting/'+enc(r.meetingId),'list-link'):''}${r.taskId?link(icon('tasks')+'关联任务'+icon('right'),'task/'+enc(r.taskId),'list-link'):''}${!r.meetingId&&!r.taskId?'<p class="small">未关联组会或任务</p>':''}</div></section><section class="panel padded"><h3>可见范围</h3><p class="section-note mt16">${r.visibility==='private'?'仅自己及明确授权的成员可访问。':'按原课题组共享范围访问。'}</p></section></aside></div></div>`;
}
function driveRow(x,view){
  const folder=x.kind==='folder';
  const title=folder?x.name:x.title;
  const to=folder?driveUrl('mine',x.id):driveFileUrl(x,view);
  const type=folder?'文件夹':typeNames[x.type]||x.type||'文件';
  return `<tr class="drive-row" data-drive-id="${esc(x.id)}" tabindex="0" aria-label="${esc(title)}，按 Shift+F10 打开操作菜单"><td><div class="drive-name"><span class="drive-file-icon ${folder?'is-folder':'is-file'}">${driveSourceBadge(x)}${icon(folder?'folder':'file')}</span><div class="drive-name-main">${folder?link(esc(title),to,'filename'):driveFileLink(esc(title),x)}<span class="drive-mobile-meta">${esc(type)}${folder?'':' · '+bytes(x.size)}</span></div></div></td><td class="drive-row-date">${x.createdAt?date(x.createdAt,{hour:'2-digit',minute:'2-digit'}):'—'}</td><td class="drive-row-actions"><button type="button" class="drive-more" data-action="cloud-menu" data-id="${esc(x.id)}" aria-label="${esc(title)}的更多操作" aria-haspopup="menu">···</button></td></tr>`;
}
function driveItem(id){return state.data.driveItems?.find(x=>x.id===id)||state.data.driveTree?.find(x=>x.id===id)||state.data.driveTreeFiles?.find(x=>x.id===id);}
function driveMenuEntries(item){
  if(!item)return [['cloud-new','新建文件夹','plus'],['upload-resource','上传文件','upload']];
  const folder=item.kind==='folder'||('name' in item && !('title' in item));
  const own=!driveIsShared(item);
  const entries=[['cloud-open',folder?'打开文件夹':'查看文件',folder?'folder':'file']];
  if(folder&&own)entries.push(['cloud-new','在此新建文件夹','plus'],['cloud-upload-here','上传到此文件夹','upload']);
  else entries.push(['download-resource','下载文件','download']);
  if(own)entries.push(['cloud-rename','重命名','file'],['cloud-move','移动到','folder']);
  if(own&&!folder)entries.push(['resource-version','上传新版本','upload'],['cloud-shares','共享管理','people']);
  if(folder&&own)entries.push(['cloud-delete','删除空文件夹','file']);
  return entries;
}
function closeDriveMenu(){const menu=document.querySelector('#driveContextMenu');if(menu){menu.remove();state.driveMenuReturnFocus?.focus?.();state.driveMenuReturnFocus=null;}}
function closeDriveSearch(restoreFocus=false){
  const popover=document.querySelector('#driveSearchPopover');
  if(!popover||popover.hidden)return;
  popover.hidden=true;
  const trigger=document.querySelector('.drive-search-trigger');
  trigger?.setAttribute('aria-expanded','false');
  if(restoreFocus)trigger?.focus();
}
function openDriveSearch(){
  const popover=document.querySelector('#driveSearchPopover');
  if(!popover)return;
  popover.hidden=false;
  document.querySelector('.drive-search-trigger')?.setAttribute('aria-expanded','true');
  const input=popover.querySelector('input[name="q"]');
  input?.focus();input?.select();
}
function showDriveMenu(item,point,returnFocus=null,entries=driveMenuEntries(item)){
  closeDriveMenu();state.driveMenuReturnFocus=returnFocus;
  const menu=document.createElement('div');menu.id='driveContextMenu';menu.className='drive-context-menu';menu.setAttribute('role','menu');menu.setAttribute('aria-label',item?`${item.name||item.title}的操作`:'新建与上传');
  menu.innerHTML=entries.map(([action,label,ic])=>`<button type="button" role="menuitem" data-menu-action="${action}" data-id="${esc(item?.id||'')}">${icon(ic)}<span>${label}</span></button>`).join('');
  document.body.append(menu);
  const x=Math.min(Math.max(8,point.x),window.innerWidth-menu.offsetWidth-8),y=Math.min(Math.max(8,point.y),window.innerHeight-menu.offsetHeight-8);
  menu.style.left=`${x}px`;menu.style.top=`${y}px`;
  menu.addEventListener('click',event=>{const target=event.target.closest('[data-menu-action]');if(!target)return;const action=target.dataset.menuAction,id=target.dataset.id;closeDriveMenu();handleAction(action,id,target).catch(e=>toast(e.message,true));});
  menu.querySelector('button')?.focus();
}
document.addEventListener('contextmenu',event=>{
  if(state.page!=='resources')return;
  const row=event.target.closest('[data-drive-id]');const surface=event.target.closest('.drive-list-panel');
  if(!row&&!surface)return;
  if(!row&&event.target.closest('input,button,a,select,textarea'))return;
  event.preventDefault();showDriveMenu(row?driveItem(row.dataset.driveId):null,{x:event.clientX,y:event.clientY});
});
document.addEventListener('click',event=>{if(!event.target.closest('#driveContextMenu,[data-action="cloud-menu"],[data-action="cloud-resource-more"],[data-action="cloud-create-menu"]'))closeDriveMenu();if(!event.target.closest('.drive-search-wrap'))closeDriveSearch();});
document.addEventListener('keydown',event=>{
  const menu=document.querySelector('#driveContextMenu');
  if(menu){if(event.key==='Escape'){event.preventDefault();closeDriveMenu();return;}if(['ArrowDown','ArrowUp'].includes(event.key)){event.preventDefault();const items=[...menu.querySelectorAll('button')],i=items.indexOf(document.activeElement);items[(i+(event.key==='ArrowDown'?1:-1)+items.length)%items.length]?.focus();return;}}
  if(state.page==='resources'&&event.key.toLowerCase()==='f'&&(event.ctrlKey||event.metaKey)&&!event.altKey&&!document.querySelector('#modal')?.open){event.preventDefault();openDriveSearch();return;}
  const searchPopover=document.querySelector('#driveSearchPopover');
  if(event.key==='Escape'&&searchPopover&&!searchPopover.hidden){event.preventDefault();closeDriveSearch(true);return;}
  if(state.page==='resources'&&(event.key==='ContextMenu'||event.shiftKey&&event.key==='F10')){const row=event.target.closest('[data-drive-id]');if(row){event.preventDefault();const rect=row.getBoundingClientRect();showDriveMenu(driveItem(row.dataset.driveId),{x:rect.right-20,y:rect.top+24},row);}}
});
window.addEventListener('hashchange',closeDriveMenu);
async function cloudAction(action,id,source){
  if(!action.startsWith('cloud-')&&action!=='attach-task'&&action!=='attach-meeting')return false;
  if(action==='cloud-resource-more'){
    const resource=state.data.resource;
    if(!resource)return true;
    const own=resource.canEdit??resource.ownerId===state.user.id;
    const entries=[...(own?[['edit-resource','编辑说明','file'],['resource-version','上传新版本','upload'],['cloud-shares','共享管理','people']]:[]),['download-resource','下载文件','download']];
    const rect=source.getBoundingClientRect();showDriveMenu(resource,{x:rect.right,y:rect.bottom+4},source,entries);
    return true;
  }
  if(action==='cloud-search-toggle'){
    if(document.querySelector('#driveSearchPopover')?.hidden)openDriveSearch();else closeDriveSearch(true);
    return true;
  }
  if(action==='cloud-tree-toggle'){
    const collapsed=state.driveTreeCollapsed ||= new Set(),node=source.closest('.drive-tree-node'),children=node?.querySelector(':scope > .drive-tree-children');
    if(!children)return true;
    if(collapsed.has(id))collapsed.delete(id);else collapsed.add(id);
    children.hidden=collapsed.has(id);source.setAttribute('aria-expanded',String(!children.hidden));source.setAttribute('aria-label',`${children.hidden?'展开':'收起'}${id==='root'?'我的文件':node.querySelector('.drive-tree-link')?.textContent||'文件夹'}`);
    return true;
  }
  const item=driveItem(id),folder=item&&(item.kind==='folder'||('name' in item&&!('title' in item)));
  if(action==='cloud-menu'){const rect=source.getBoundingClientRect();showDriveMenu(item,{x:rect.right,y:rect.bottom+4},source);return true;}
  if(action==='cloud-open'){if(folder)navigate(driveUrl('mine',id));else window.open('#'+driveFileUrl(item),'_blank','noopener');return true;}
  if(action==='cloud-create-menu'){
    const rect=source.getBoundingClientRect();
    showDriveMenu(null,{x:rect.left,y:rect.bottom+4},source,[['cloud-create-document','文档','file'],['cloud-create-sheet','表格','file'],['cloud-create-slides','幻灯片','file'],['cloud-new','文件夹','folder']]);
    return true;
  }
  if(['cloud-create-document','cloud-create-sheet','cloud-create-slides'].includes(action)){
    const kind=action.slice('cloud-create-'.length);
    window.open('#newdocument/'+enc(JSON.stringify({kind,folderId:state.driveFolder||''})),'_blank','noopener');
    return true;
  }
  if(action==='cloud-my-files'){navigate(driveUrl('mine'));return true;}
  if(action==='cloud-new'){state.driveCreationParent=id||state.driveFolder||'';modalForm('新建文件夹','cloud-folder',field('名称','name','',{required:true,max:200}),'创建');}
  if(action==='cloud-upload-here'){await openCloudUpload(null,id);return true;}
  if(action==='cloud-rename')modalForm(folder?'重命名文件夹':'重命名文件','cloud-rename',field('名称','name',folder?item.name:item.title,{required:true,max:200})+`<input type="hidden" name="kind" value="${folder?'folder':'file'}">`,'保存',id);
  if(action==='cloud-move'){const tree=await api('/me/drive/folders/tree');modalForm('选择目标目录','cloud-move',selectField('目标目录','folderId',driveFolderOptions(tree.items),folder?item.parentId:item.folderId)+`<input type="hidden" name="kind" value="${folder?'folder':'file'}">`,'移动',id);}
  if(action==='cloud-delete')modalForm('删除空文件夹','cloud-delete',`<p>确认删除“${esc(item.name)}”？非空目录会被拒绝。</p>`,'删除',id);
  if(action==='cloud-shares')await openShares(id);
  if(action==='cloud-revoke') {const [resource,user]=id.split(':');modalForm('撤销直接共享','cloud-revoke',`<p>撤销该文件对这个成员在所有课题组中的直接授权。若仍有原课题组共享，该成员可能继续可访问。</p>`,'撤销',resource+':'+user);}
  if(action==='cloud-retry'){for(const x of uploadQueue)if(x.status==='failed'){x.status='waiting';x.error='';}processUploadQueue();}
  if(action==='cloud-upload-done'){closeModal();await renderPage();}
  if(action==='attach-task'||action==='attach-meeting'){await openReferencePicker({kind:action==='attach-task'?'task':'meeting',id});}
  if(action==='cloud-link'){const item=uploadQueue.find(x=>x.result?.id===id);if(item?.target)await openReferencePicker(item.target,id);}
  return true;
}
async function openShares(id){const shares=await api(`/resources/${enc(id)}/shares`);const rows=shares.direct.items;openModal('文件共享与授权',`<p class="notice">仅授权此文件的查看、预览、下载和个人阅读状态。接收人不能修改或再次共享。${shares.legacyAccess.active?'本文件仍通过原课题组共享可访问，撤销直接授权不关闭这一来源。':''}</p>${rows.map(x=>`<div class="row"><div class="row-main"><strong>${esc(x.displayName)}</strong><p>课题组 ${esc(x.teamId)} · ${x.active?'有效只读授权':'已失效'}</p></div>${x.active?btn('撤销','cloud-revoke',id+':'+x.userId):''}</div>`).join('')}${state.team?form('cloud-share',selectField('授权成员','userId',state.members.filter(x=>x.id!==state.user.id).map(x=>({id:x.id,name:x.name})))+`<p class="small">授权上下文：${esc(state.team.name)}，离组后失效，重新加入需要重新授权。</p>`,'确认只读授权',id):'<p class="small mt16">加入课题组后可选择组内成员共享。</p>'}`);}
async function openReferencePicker(target,selected=''){state.referenceTarget=target;const files=await allDriveFiles('all',`&targetType=${target.kind}&targetId=${enc(target.id)}`);state.data.referenceFiles=files;openModal('从我的云盘引用材料',`<p class="notice">引用保持原文件 ID，不自动扩大权限。只对勾选的无权成员新增授权。授权成功但关联失败时，授权会保留，可到云盘撤销。</p>${form('cloud-reference',selectField('文件','resourceId',files.map(x=>({id:x.id,name:x.title+' · '+x.owner})),selected)+`<div id="referenceAudience"></div>`,'确认授权并引用')}${btn('先上传新文件','cloud-upload-for-target')}`);const sel=$('[name=resourceId]');sel?.addEventListener('change',renderAudience);renderAudience();}
function renderAudience(){const selected=$('[name=resourceId]')?.value,item=state.data.referenceFiles.find(x=>x.id===selected);const box=$('#referenceAudience');if(!box)return;box.innerHTML=item?(item.audience||[]).map(x=>`<div class="row"><span>${esc(x.displayName)}：${x.canRead?'已可访问':'当前无权访问'}</span>${!x.canRead&&item.ownerId===state.user.id?`<label><input name="grantUser" type="checkbox" value="${esc(x.userId)}"> 明确授予只读权限</label>`:''}</div>`).join('')+(item.ownerId!==state.user.id?'<p class="small">你不是所有者；无权成员需要联系所有者获取授权。</p>':''):'';}
async function cloudSubmit(f){const type=f.dataset.form;if(!type.startsWith('cloud-'))return false;const d=values(f),id=f.dataset.id;let refresh=true;
  if(type==='cloud-search'){navigate(driveUrl(state.driveView.scope,state.driveView.folder,d.q));return true;}
  if(type==='cloud-folder')await api('/me/drive/folders','POST',{name:d.name,parentId:state.driveCreationParent||null});
  if(type==='cloud-rename')await api(d.kind==='folder'?`/me/drive/folders/${enc(id)}`:`/resources/${enc(id)}`,'PATCH',d.kind==='folder'?{name:d.name}:{title:d.name});
  if(type==='cloud-move')await api(d.kind==='folder'?`/me/drive/folders/${enc(id)}`:`/resources/${enc(id)}`,'PATCH',d.kind==='folder'?{parentId:d.folderId||null}:{folderId:d.folderId||null});
  if(type==='cloud-delete')await api(`/me/drive/folders/${enc(id)}`,'DELETE');
  if(type==='cloud-share'){await api(`/resources/${enc(id)}/shares/${enc(d.userId)}`,'PUT',{permission:'read',teamId:state.team.id});toast('只读授权已保存');await openShares(id);return true;}
  if(type==='cloud-revoke'){const [r,u]=id.split(':');await api(`/resources/${enc(r)}/shares/${enc(u)}`,'DELETE');toast('直接授权已撤销；原课题组共享范围保持');await openShares(r);return true;}
  if(type==='cloud-reference') {const target=state.referenceTarget,item=state.data.referenceFiles.find(x=>x.id===d.resourceId);let granted=0;try{for(const box of $$('input[name=grantUser]:checked',f)){await api(`/resources/${enc(item.id)}/shares/${enc(box.value)}`,'PUT',{permission:'read',teamId:state.team.id});granted++;}await api(`/${target.kind==='task'?'tasks':'meetings'}/${enc(target.id)}/resources`,'POST',{resourceId:item.id});}catch(e){if(granted)e.message='授权已保存，关联未完成：'+e.message+'。可重试关联或到云盘撤销新增授权。';throw e;}}
  closeModal();toast('操作已保存');if(refresh)await renderPage();return true;
}
const originalCloudAction=cloudAction;
cloudAction=async(action,id,source)=>{if(action==='cloud-upload-for-target'){await openCloudUpload(state.referenceTarget);return true;}return originalCloudAction(action,id,source);};
