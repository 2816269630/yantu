'use strict';

const originalResourcePage = pages.resource;
let activeDocument = null;
const workspaceKinds = {'.ytdoc':'document','.ytsheet':'sheet','.ytslides':'slides','.txt':'text','.md':'text'};

pages.newdocument = async raw => {
  let request;
  try {request=JSON.parse(decodeURIComponent(raw||''));} catch {throw new Error('新建文档参数无效');}
  const titles={document:'未命名文档',sheet:'未命名表格',slides:'未命名幻灯片'};
  if(!Object.hasOwn(titles,request.kind))throw new Error('不支持的文档类型');
  const created=await api('/me/drive/documents','POST',{kind:request.kind,title:titles[request.kind],folderId:request.folderId||''});
  navigate('resource/'+enc(created.id));
  return loading();
};

function workspaceKind(fileName='') {return workspaceKinds['.'+fileName.split('.').pop().toLowerCase()] || '';}
function workspaceStatus(message, error=false) {const node=document.querySelector('#documentSaveStatus');if(node){node.textContent=message;node.classList.toggle('is-error',error);}}
function workspaceModifiedLabel(value) {
  if(!value)return '最近修改';
  const at=new Date(value),today=new Date();
  if(Number.isNaN(at.getTime()))return '最近修改';
  const dateKey=date=>`${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
  if(dateKey(at)===dateKey(today))return '今天修改';
  const yesterday=new Date(today);yesterday.setDate(today.getDate()-1);
  if(dateKey(at)===dateKey(yesterday))return '昨天修改';
  return `${at.getFullYear()===today.getFullYear()?'':at.getFullYear()+'年'}${at.getMonth()+1}月${at.getDate()}日修改`;
}
function workspaceOutlineItems(body) {
  const root={level:0,children:[]},stack=[root];
  String(body||'').replace(/\r/g,'').split('\n').forEach((raw,line)=>{
    const match=raw.match(/^\s{0,3}(#{1,6})\s+(.+?)\s*$/);
    if(!match||!match[2].trim()||stack[0].count>=200)return;
    const item={level:match[1].length,title:match[2].replace(/\s+#+\s*$/,'').trim(),line,children:[]};
    while(stack.length>1&&stack.at(-1).level>=item.level)stack.pop();
    stack.at(-1).children.push(item);stack.push(item);
    root.count=(root.count||0)+1;
  });
  return root.children;
}
function workspaceOutline(body,title) {
  const render=items=>items.length?`<ul>${items.map(item=>`<li class="document-outline-item" data-outline-level="${item.level}"><div class="document-outline-row">${item.children.length?`<button type="button" class="document-outline-toggle" data-outline-toggle aria-expanded="true" aria-label="收起${esc(item.title)}的子标题">▾</button>`:'<span class="document-outline-spacer"></span>'}<button type="button" class="document-outline-link" data-outline-line="${item.line}" title="${esc(item.title)}">${esc(item.title)}</button></div>${render(item.children)}</li>`).join('')}</ul>`:'';
  return `<li class="document-outline-root"><button type="button" class="document-outline-link active" data-outline-top title="返回文档开头">${esc(title)}</button>${render(workspaceOutlineItems(body))}</li>`;
}
function workspaceSheet(content) {
  const rows=content.length?content:[['','','']];
  const columns=Math.max(3,...rows.map(row=>row.length));
  return `<div class="document-sheet-scroll"><table class="document-sheet"><thead><tr><th></th>${Array.from({length:columns},(_,i)=>`<th>${String.fromCharCode(65+i)}</th>`).join('')}</tr></thead><tbody>${rows.map((row,r)=>`<tr><th>${r+1}</th>${Array.from({length:columns},(_,c)=>`<td><input data-sheet-row="${r}" data-sheet-column="${c}" value="${esc(row[c]||'')}" maxlength="5000" ${activeDocument.doc.canEdit?'':'readonly'} aria-label="${String.fromCharCode(65+c)}${r+1}"></td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}
function workspaceSlides(content) {
  const slides=content.length?content:[{title:'',body:''}];
  const index=Math.min(activeDocument.activeSlide||0,slides.length-1),slide=slides[index];
  return `<div class="document-slides"><aside class="document-slide-list" aria-label="幻灯片目录">${slides.map((item,i)=>`<button type="button" class="document-slide-thumb ${i===index?'active':''}" data-doc-slide="${i}"><span>${i+1}</span><strong>${esc(item.title||'未命名页面')}</strong></button>`).join('')}${activeDocument.doc.canEdit?'<button type="button" class="document-slide-add" data-doc-action="add-slide">＋ 新增页面</button>':''}</aside><div class="document-slide-stage"><input data-slide-field="title" value="${esc(slide.title)}" maxlength="200" placeholder="输入标题" ${activeDocument.doc.canEdit?'':'readonly'} aria-label="幻灯片标题"><textarea data-slide-field="body" maxlength="10000" placeholder="输入正文" ${activeDocument.doc.canEdit?'':'readonly'} aria-label="幻灯片正文">${esc(slide.body)}</textarea></div></div>`;
}
function workspaceMarkup(resource, doc) {
  const editable=doc.canEdit,kind=doc.kind;
  const label={document:'文档',text:'文本',sheet:'表格',slides:'幻灯片'}[kind];
  const back=state.driveReturn||'resources';
  const titleInput=`<input data-document-title value="${esc(resource.title)}" maxlength="200" aria-label="文档标题" title="点击修改标题" ${editable?'':'readonly'}>`;
  const owner=doc.owner||resource.owner||'未知作者';
  const byline=kind==='document'?`<div class="document-paper-byline"><span class="document-author-avatar" aria-hidden="true">${esc(Array.from(owner)[0]||'?')}</span><span class="document-author-name">${esc(owner)}</span><span class="document-byline-divider" aria-hidden="true"></span><time id="documentModifiedAt" datetime="${esc(doc.modifiedAt||'')}">${workspaceModifiedLabel(doc.modifiedAt)}</time></div>`:'';
  const rendered=kind==='document'?`<article class="document-rendered" data-document-preview ${activeDocument.preview?'':'hidden'} aria-label="文档预览">${renderDocumentPreview(doc.content)}</article>`:'';
  const content=kind==='sheet'?workspaceSheet(doc.content):kind==='slides'?workspaceSlides(doc.content):`<div class="document-paper"><h1 class="document-paper-title">${titleInput}</h1>${byline}<div class="document-editor" data-document-editor contenteditable="${editable?'plaintext-only':'false'}" role="textbox" aria-multiline="true" aria-label="文档正文" data-placeholder="从这里开始书写…" ${kind==='document'&&activeDocument.preview?'hidden':''}>${esc(doc.content)}</div>${rendered}</div>`;
  const outline=kind==='document'||kind==='text'?`<aside class="document-outline" id="documentOutlinePanel"><div class="document-outline-header"><h2>目录</h2><button type="button" class="document-outline-collapse" data-doc-action="toggle-outline" aria-expanded="true" aria-label="收起目录" title="收起目录">«</button></div><ul id="documentOutline">${workspaceOutline(doc.content,resource.title)}</ul></aside>`:'';
  const equationDialog=kind==='document'&&editable?`<dialog class="document-equation-dialog" id="documentEquationDialog" aria-label="插入公式"><div class="document-equation-head"><strong>插入公式</strong><button type="button" data-doc-action="cancel-equation" aria-label="关闭">×</button></div><div class="document-equation-kinds"><label><input type="radio" name="equationKind" value="inline">行内公式</label><label><input type="radio" name="equationKind" value="block" checked>独立公式</label></div><textarea id="documentEquationSource" aria-label="LaTeX 公式源码" placeholder="例如 \\frac{a}{b} + x^2" spellcheck="false"></textarea><div class="document-equation-templates"><button type="button" data-doc-equation-template="\\frac{a}{b}">分式</button><button type="button" data-doc-equation-template="x_{i+j}^{2}">上下标</button><button type="button" data-doc-equation-template="\\sqrt{x}">根式</button><button type="button" data-doc-equation-template="\\sum_{i=1}^{n} i">求和</button><button type="button" data-doc-equation-template="\\begin{bmatrix} a & b \\\\ c & d \\end{bmatrix}">矩阵</button></div><div class="document-equation-preview" id="documentEquationPreview" aria-label="公式预览"></div><div class="document-equation-actions"><button type="button" class="btn" data-doc-action="cancel-equation">取消</button><button type="button" class="btn primary" data-doc-action="insert-equation">插入公式</button></div></dialog>`:'';
  return `<div class="document-workspace"><header class="document-topbar"><div class="document-top-left"><a href="#${esc(back)}" class="document-home" aria-label="返回我的云盘">${icon('back')}</a><span class="document-mark">${icon(kind==='sheet'?'tasks':kind==='slides'?'layers':'file')}</span><div class="document-heading"><div class="document-title-top"><input id="documentTitle" data-document-title value="${esc(resource.title)}" maxlength="200" aria-label="文档标题" title="点击修改标题" ${editable?'':'readonly'}>${editable?'<button type="button" class="document-title-edit" data-doc-action="edit-title" aria-label="修改文档标题" title="修改文档标题">✎</button>':''}</div><span id="documentSaveStatus">${editable?'已保存到云端':'只读文档'}</span></div></div><div class="document-top-actions">${kind==='document'&&editable?`<button type="button" class="btn" data-doc-action="toggle-preview">${activeDocument.preview?'编辑正文':'预览'}</button><button type="button" class="btn" data-doc-action="open-equation">公式</button>`:''}${editable?'<button type="button" class="btn" data-doc-action="save">保存</button>'+btn('分享','cloud-shares',resource.id,'primary'):''}<button type="button" class="btn document-more" data-action="cloud-resource-more" data-id="${esc(resource.id)}" aria-haspopup="menu">···</button></div></header><div class="document-toolbar"><span>${label}</span>${kind==='sheet'&&editable?'<button type="button" data-doc-action="add-row">＋ 行</button><button type="button" data-doc-action="add-column">＋ 列</button>':''}${kind==='slides'&&editable?'<button type="button" data-doc-action="add-slide">＋ 页面</button>':''}<a href="/api/v1/resources/${enc(resource.id)}/download">下载原文件</a></div><div class="document-conflict" id="documentConflict" role="alert" hidden><strong>发现其他页面的更新</strong><span>自动保存已暂停，你的本地草稿没有覆盖云端内容。请先下载草稿，再重新加载云端版本。</span><button type="button" class="btn" data-doc-action="download-draft">下载本地草稿</button><button type="button" class="btn" data-doc-action="reload-cloud">重新加载云端</button></div><div class="document-body">${outline}<main class="document-stage">${content}</main></div>${equationDialog}</div>`;
}

pages.resource = async id => {
  const resource=await api(`/resources/${enc(id)}`);
  if(!workspaceKind(resource.fileName)) {activeDocument=null;return originalResourcePage(id);}
  let doc;
  try {doc=await api(`/resources/${enc(id)}/document`);}
  catch(error) {if(error.status===415){activeDocument=null;return originalResourcePage(id);}throw error;}
  activeDocument={doc,resource,dirty:false,saving:false,conflict:false,pendingSave:false,timer:null,titleDirty:false,titleSaving:false,pendingTitle:false,titleTimer:null,activeSlide:0,preview:doc.kind==='document'&&Boolean(String(doc.content).trim()),lastSaved:JSON.stringify(doc.content)};
  state.data.resource=resource;
  document.body.classList.add('document-mode');
  document.title=`${resource.title} · 研途`;
  return workspaceMarkup(resource,doc);
};

function workspaceContent() {
  if(!activeDocument)return null;
  const {doc}=activeDocument;
  if(doc.kind==='sheet'||doc.kind==='slides')return doc.content;
  const editor=document.querySelector('[data-document-editor]');
  return editor?(editor.innerText??editor.textContent).replace(/\r/g,''):doc.content;
}
function setWorkspacePreview(preview) {
  if(activeDocument?.doc.kind!=='document')return;
  const editor=document.querySelector('[data-document-editor]'),rendered=document.querySelector('[data-document-preview]');
  if(!editor||!rendered)return;
  const wasPreview=activeDocument.preview;
  activeDocument.preview=preview;
  if(preview)rendered.innerHTML=renderDocumentPreview(workspaceContent());
  editor.hidden=preview;rendered.hidden=!preview;
  const button=document.querySelector('[data-doc-action="toggle-preview"]');
  if(button)button.textContent=preview?'编辑正文':'预览';
  if(!preview){editor.focus();const selection=window.getSelection();if(wasPreview||!selection?.rangeCount||!editor.contains(selection.anchorNode)){const range=document.createRange();range.selectNodeContents(editor);range.collapse(false);selection?.removeAllRanges();selection?.addRange(range);}}
}
function workspaceEquationPreview() {
  const source=document.querySelector('#documentEquationSource')?.value||'',block=document.querySelector('[name="equationKind"]:checked')?.value==='block';
  const preview=document.querySelector('#documentEquationPreview');
  if(preview)preview.innerHTML=source.trim()?documentMath(source,block):'<span class="document-equation-placeholder">输入 LaTeX 后在此预览</span>';
}
function openWorkspaceEquation(initial='',block=true) {
  if(activeDocument?.doc.kind!=='document'||!activeDocument.doc.canEdit)return;
  if(activeDocument.preview)setWorkspacePreview(false);
  const editor=document.querySelector('[data-document-editor]'),selection=window.getSelection();
  activeDocument.equationRange=selection?.rangeCount&&editor.contains(selection.anchorNode)?selection.getRangeAt(0).cloneRange():null;
  const dialog=document.querySelector('#documentEquationDialog'),source=document.querySelector('#documentEquationSource');
  source.value=initial;document.querySelector(`[name="equationKind"][value="${block?'block':'inline'}"]`).checked=true;
  workspaceEquationPreview();dialog.showModal();source.focus();
}
function insertWorkspaceEquation() {
  const dialog=document.querySelector('#documentEquationDialog'),source=document.querySelector('#documentEquationSource')?.value.trim();
  if(!source){document.querySelector('#documentEquationSource')?.focus();return;}
  if(source.includes('$$')){workspaceStatus('公式源码不能包含连续的 $$',true);return;}
  const editor=document.querySelector('[data-document-editor]'),block=document.querySelector('[name="equationKind"]:checked')?.value==='block';
  editor.focus();
  const range=activeDocument.equationRange;
  let markup=`$${source}$`;
  if(block){
    const before=document.createRange();before.selectNodeContents(editor);
    if(range&&editor.contains(range.startContainer))before.setEnd(range.startContainer,range.startOffset);
    const prior=before.toString(),prefix=prior&&!prior.endsWith('\n')?'\n':'';
    markup=`${prefix}$$${source}$$\n`;
  }
  if(range&&editor.contains(range.commonAncestorContainer)){
    range.deleteContents();const node=document.createTextNode(markup);range.insertNode(node);range.setStartAfter(node);range.collapse(true);
    const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);
  } else {
    editor.appendChild(document.createTextNode(markup));const range=document.createRange();range.selectNodeContents(editor);range.collapse(false);
    const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);
  }
  activeDocument.equationRange=null;dialog.close();editor.dispatchEvent(new Event('input',{bubbles:true}));
}
function queueWorkspaceSave() {
  const workspace=activeDocument;
  if(!workspace?.doc.canEdit)return;
  workspace.dirty=true;workspaceStatus('未保存');
  clearTimeout(workspace.timer);
  if(workspace.conflict){workspaceStatus('保存冲突 · 本地草稿未覆盖云端',true);return;}
  if(workspace.saving){workspace.pendingSave=true;return;}
  workspace.timer=setTimeout(()=>{
    if(activeDocument===workspace)saveWorkspaceDocument().catch(error=>{if(!workspace.conflict)workspaceStatus(error.message,true);});
  },1200);
}
async function saveWorkspaceDocument() {
  const workspace=activeDocument;
  if(!workspace?.doc.canEdit)return;
  if(workspace.conflict){workspaceStatus('保存冲突 · 本地草稿未覆盖云端',true);return;}
  if(workspace.saving){workspace.pendingSave=true;return;}
  clearTimeout(workspace.timer);
  const content=workspaceContent(),serialized=JSON.stringify(content);
  if(serialized===workspace.lastSaved){workspace.dirty=false;workspaceStatus('已保存到云端');return;}
  workspace.saving=true;workspaceStatus('保存中…');
  let saved=false;
  try {
    const result=await api(`/resources/${enc(workspace.resource.id)}/document`,'PUT',{version:workspace.doc.version,content});
    saved=true;
    workspace.doc.version=result.version;workspace.lastSaved=serialized;
    if(result.modifiedAt){workspace.doc.modifiedAt=result.modifiedAt;const time=document.querySelector('#documentModifiedAt');if(time){time.dateTime=result.modifiedAt;time.textContent=workspaceModifiedLabel(result.modifiedAt);}}
    if(activeDocument===workspace&&serialized===JSON.stringify(workspaceContent())&&!workspace.pendingSave){workspace.dirty=false;workspaceStatus('已保存到云端');}
  } catch(error) {
    if(activeDocument===workspace){
      if(error.status===409){workspace.conflict=true;workspace.dirty=true;clearTimeout(workspace.timer);document.querySelector('#documentConflict')?.removeAttribute('hidden');document.querySelector('[data-doc-action="save"]')?.setAttribute('disabled','');workspaceStatus('保存冲突 · 本地草稿未覆盖云端',true);}
      else workspaceStatus(error.message,true);
    }
    throw error;
  } finally {
    workspace.saving=false;
    if(saved&&activeDocument===workspace&&!workspace.conflict&&workspace.lastSaved!==JSON.stringify(workspaceContent())){
      workspace.pendingSave=false;queueWorkspaceSave();
    } else workspace.pendingSave=false;
  }
}

function downloadWorkspaceDraft() {
  if(!activeDocument)return;
  const title=document.querySelector('#documentTitle')?.value.trim()||activeDocument.resource.title;
  const name=(title||'文档').replace(/[\\/:*?"<>|]/g,'_');
  const draft=JSON.stringify({kind:activeDocument.doc.kind,title,content:workspaceContent()},null,2);
  const url=URL.createObjectURL(new Blob([draft],{type:'application/json;charset=utf-8'}));
  const anchor=document.createElement('a');anchor.href=url;anchor.download=`${name}-本地草稿.json`;anchor.click();
  setTimeout(()=>URL.revokeObjectURL(url),3000);
}
function syncWorkspaceTitle(title,source=null) {
  document.querySelectorAll('[data-document-title]').forEach(input=>{if(input!==source)input.value=title;});
  const root=document.querySelector('[data-outline-top]');if(root)root.textContent=title;
}
function queueWorkspaceTitleSave() {
  const workspace=activeDocument;
  if(!workspace?.doc.canEdit)return;
  workspace.titleDirty=true;workspaceStatus('未保存');
  clearTimeout(workspace.titleTimer);
  if(workspace.conflict)return;
  if(workspace.titleSaving){workspace.pendingTitle=true;return;}
  workspace.titleTimer=setTimeout(()=>{
    if(activeDocument===workspace)saveWorkspaceTitle().catch(error=>{if(!workspace.conflict)workspaceStatus(error.message,true);});
  },800);
}
async function saveWorkspaceTitle() {
  const workspace=activeDocument,input=document.querySelector('#documentTitle');
  if(!workspace?.doc.canEdit||!input||workspace.conflict)return;
  if(workspace.titleSaving){workspace.pendingTitle=true;return;}
  clearTimeout(workspace.titleTimer);
  const title=input.value.trim();
  if(!title){syncWorkspaceTitle(workspace.resource.title);workspace.titleDirty=false;workspaceStatus('标题不能为空',true);return;}
  if(title===workspace.resource.title){workspace.titleDirty=false;if(!workspace.dirty)workspaceStatus('已保存到云端');return;}
  workspace.titleSaving=true;workspaceStatus('保存中…');
  try {
    const updated=await api(`/resources/${enc(workspace.resource.id)}`,'PATCH',{title,expectedTitle:workspace.resource.title});
    workspace.resource.title=updated.title;workspace.resource.fileName=updated.fileName;
    if(activeDocument===workspace){
      state.data.resource=workspace.resource;
      document.title=`${updated.title} · 研途`;
      if(input.value.trim()===title){syncWorkspaceTitle(updated.title);workspace.titleDirty=false;if(!workspace.dirty)workspaceStatus('已保存到云端');}
      else workspace.pendingTitle=true;
    }
  } catch(error) {
    if(activeDocument===workspace){
      if(error.status===409){workspace.conflict=true;workspace.titleDirty=true;document.querySelector('#documentConflict')?.removeAttribute('hidden');document.querySelector('[data-doc-action="save"]')?.setAttribute('disabled','');workspaceStatus('标题冲突 · 本地输入未覆盖云端',true);}
      else workspaceStatus(error.message,true);
    }
    throw error;
  } finally {
    workspace.titleSaving=false;
    if(activeDocument===workspace&&workspace.pendingTitle&&!workspace.conflict){workspace.pendingTitle=false;queueWorkspaceTitleSave();}
    else workspace.pendingTitle=false;
  }
}

function focusWorkspaceHeading(line,button) {
  if(activeDocument?.preview){
    const heading=document.querySelector(`[data-document-preview] [data-doc-line="${line}"]`);
    if(heading)heading.scrollIntoView({behavior:'smooth',block:'start'});
    document.querySelectorAll('#documentOutline .document-outline-link').forEach(link=>link.classList.toggle('active',link===button));
    return;
  }
  const editor=document.querySelector('[data-document-editor]');
  const raw=workspaceContent()?.split('\n')[line];
  if(!editor||!raw)return;
  const walker=document.createTreeWalker(editor,NodeFilter.SHOW_TEXT);
  let node,offset=-1,remaining=workspaceContent().split('\n').slice(0,line).reduce((total,text)=>total+text.length+1,0);
  if(editor.textContent===workspaceContent()){
    while((node=walker.nextNode())){if(remaining<=node.length){offset=remaining;break;}remaining-=node.length;}
  }
  if(offset<0){
    const search=document.createTreeWalker(editor,NodeFilter.SHOW_TEXT);
    while((node=search.nextNode())){offset=node.textContent.indexOf(raw.trim());if(offset>=0)break;}
  }
  if(!node||offset<0)return;
  const range=document.createRange();range.setStart(node,offset);range.collapse(true);
  editor.focus();const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);
  const rect=range.getBoundingClientRect();window.scrollBy({top:rect.top-180,behavior:'smooth'});
  document.querySelectorAll('#documentOutline .document-outline-link').forEach(link=>link.classList.toggle('active',link===button));
}
function refreshWorkspaceOutline() {
  const outline=document.querySelector('#documentOutline');if(!outline)return;
  const collapsed=new Set([...outline.querySelectorAll('[data-outline-toggle][aria-expanded="false"]')].map(button=>button.closest('li')?.querySelector('[data-outline-line]')?.dataset.outlineLine));
  outline.innerHTML=workspaceOutline(workspaceContent(),activeDocument.resource.title);
  outline.querySelectorAll('[data-outline-toggle]').forEach(button=>{
    if(collapsed.has(button.closest('li')?.querySelector('[data-outline-line]')?.dataset.outlineLine)){
      button.setAttribute('aria-expanded','false');button.textContent='▸';
      const children=button.closest('li')?.querySelector(':scope > ul');if(children)children.hidden=true;
    }
  });
}

document.addEventListener('input',event=>{
  if(!activeDocument||state.page!=='resource')return;
  if(event.target.matches('[data-document-title]')){syncWorkspaceTitle(event.target.value,event.target);queueWorkspaceTitleSave();return;}
  if(event.target.matches('[data-document-editor]')){
    activeDocument.doc.content=workspaceContent();
    const rendered=document.querySelector('[data-document-preview]');if(rendered)rendered.innerHTML=renderDocumentPreview(activeDocument.doc.content);
    refreshWorkspaceOutline();
    queueWorkspaceSave();
  }
  if(event.target.matches('[data-sheet-row]')){
    const row=Number(event.target.dataset.sheetRow),column=Number(event.target.dataset.sheetColumn);
    activeDocument.doc.content[row][column]=event.target.value;queueWorkspaceSave();
  }
  if(event.target.matches('[data-slide-field]')){
    activeDocument.doc.content[activeDocument.activeSlide][event.target.dataset.slideField]=event.target.value;
    if(event.target.dataset.slideField==='title')document.querySelector('.document-slide-thumb.active strong').textContent=event.target.value||'未命名页面';
    queueWorkspaceSave();
  }
});
document.addEventListener('click',event=>{
  if(!activeDocument||state.page!=='resource')return;
  if(event.target.closest('.document-home')&&(activeDocument.dirty||activeDocument.titleDirty)){
    event.preventDefault();
    if(window.confirm('当前修改尚未保存到云端。离开前请先保存或下载本地草稿。')){activeDocument.dirty=false;navigate(state.driveReturn||'resources');}
    return;
  }
  const outlineToggle=event.target.closest('[data-outline-toggle]');
  if(outlineToggle){const expanded=outlineToggle.getAttribute('aria-expanded')==='true';outlineToggle.setAttribute('aria-expanded',String(!expanded));outlineToggle.textContent=expanded?'▸':'▾';outlineToggle.setAttribute('aria-label',`${expanded?'展开':'收起'}${outlineToggle.closest('li')?.querySelector('[data-outline-line]')?.textContent||''}的子标题`);const children=outlineToggle.closest('li')?.querySelector(':scope > ul');if(children)children.hidden=expanded;return;}
  const outlineLink=event.target.closest('[data-outline-line]');
  if(outlineLink){focusWorkspaceHeading(Number(outlineLink.dataset.outlineLine),outlineLink);return;}
  if(event.target.closest('[data-outline-top]')){window.scrollTo({top:0,behavior:'smooth'});document.querySelectorAll('#documentOutline .document-outline-link').forEach(link=>link.classList.toggle('active',link.hasAttribute('data-outline-top')));return;}
  const slide=event.target.closest('[data-doc-slide]');
  if(slide){activeDocument.activeSlide=Number(slide.dataset.docSlide);document.querySelector('.document-stage').innerHTML=workspaceSlides(activeDocument.doc.content);return;}
  const action=event.target.closest('[data-doc-action]')?.dataset.docAction;
  if(action==='toggle-preview'){setWorkspacePreview(!activeDocument.preview);return;}
  if(action==='open-equation'){openWorkspaceEquation();return;}
  if(action==='cancel-equation'){activeDocument.equationRange=null;document.querySelector('#documentEquationDialog')?.close();return;}
  if(action==='insert-equation'){insertWorkspaceEquation();return;}
  if(action==='edit-title'){(document.querySelector('.document-paper-title [data-document-title]')||document.querySelector('#documentTitle'))?.focus();return;}
  if(action==='toggle-outline'){const panel=document.querySelector('#documentOutlinePanel'),button=event.target.closest('[data-doc-action]'),collapsed=panel.classList.toggle('is-collapsed');button.setAttribute('aria-expanded',String(!collapsed));button.setAttribute('aria-label',collapsed?'展开目录':'收起目录');button.title=collapsed?'展开目录':'收起目录';button.textContent=collapsed?'»':'«';return;}
  if(action==='save')saveWorkspaceDocument().catch(()=>{});
  if(action==='download-draft')downloadWorkspaceDraft();
  if(action==='reload-cloud'&&window.confirm('重新加载会清除当前页面尚未保存的修改。请先下载本地草稿。')){activeDocument.dirty=false;location.reload();}
  if(action==='add-row'){if(activeDocument.doc.content.length>=100)return toast('最多 100 行',true);const cols=Math.max(3,...activeDocument.doc.content.map(row=>row.length));activeDocument.doc.content.push(Array(cols).fill(''));document.querySelector('.document-stage').innerHTML=workspaceSheet(activeDocument.doc.content);queueWorkspaceSave();}
  if(action==='add-column'){if(Math.max(...activeDocument.doc.content.map(row=>row.length))>=26)return toast('最多 26 列',true);activeDocument.doc.content.forEach(row=>row.push(''));document.querySelector('.document-stage').innerHTML=workspaceSheet(activeDocument.doc.content);queueWorkspaceSave();}
  if(action==='add-slide'){if(activeDocument.doc.content.length>=50)return toast('最多 50 页',true);activeDocument.doc.content.push({title:'',body:''});activeDocument.activeSlide=activeDocument.doc.content.length-1;document.querySelector('.document-stage').innerHTML=workspaceSlides(activeDocument.doc.content);queueWorkspaceSave();}
});
document.addEventListener('click',event=>{
  const chip=event.target.closest('[data-doc-equation-template]');if(!chip)return;
  const source=document.querySelector('#documentEquationSource');if(!source)return;
  source.value=source.value?source.value+' '+chip.dataset.docEquationTemplate:chip.dataset.docEquationTemplate;
  workspaceEquationPreview();source.focus();
});
document.addEventListener('input',event=>{if(event.target?.id==='documentEquationSource')workspaceEquationPreview();});
document.addEventListener('change',event=>{if(event.target?.name==='equationKind')workspaceEquationPreview();});
document.addEventListener('focusout',event=>{if(event.target?.matches?.('[data-document-title]'))saveWorkspaceTitle().catch(()=>{});});
document.addEventListener('keydown',event=>{
  if(!activeDocument||state.page!=='resource')return;
  if(event.target?.matches?.('[data-document-editor]')&&activeDocument.doc.kind==='document'&&activeDocument.doc.canEdit){
    const selection=window.getSelection(),node=selection?.anchorNode,offset=selection?.anchorOffset;
    if(node?.nodeType===Node.TEXT_NODE&&selection.isCollapsed){
      const before=node.textContent.slice(0,offset),shortcut=event.key==='Enter'?before.match(/(?:^|\s)(\/(?:eq|gs))$/):event.key==='$'&&before.endsWith('$$$')?'$$$':null;
      if(shortcut){event.preventDefault();const length=typeof shortcut==='string'?3:shortcut[1].length;node.textContent=node.textContent.slice(0,offset-length)+node.textContent.slice(offset);const range=document.createRange();range.setStart(node,offset-length);range.collapse(true);selection.removeAllRanges();selection.addRange(range);event.target.dispatchEvent(new Event('input',{bubbles:true}));openWorkspaceEquation();return;}
    }
  }
  if(event.target?.matches?.('[data-document-title]')){
    if(event.key==='Enter'){event.preventDefault();saveWorkspaceTitle().catch(()=>{});event.target.blur();return;}
    if(event.key==='Escape'){event.preventDefault();clearTimeout(activeDocument.titleTimer);syncWorkspaceTitle(activeDocument.resource.title);activeDocument.titleDirty=false;event.target.blur();return;}
  }
  if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='s'){event.preventDefault();saveWorkspaceTitle().catch(()=>{});saveWorkspaceDocument().catch(()=>{});}
});
window.addEventListener('beforeunload',event=>{if(activeDocument?.dirty||activeDocument?.titleDirty){event.preventDefault();event.returnValue='';}});
window.addEventListener('hashchange',()=>{if(activeDocument?.titleDirty)saveWorkspaceTitle().catch(()=>{});if(activeDocument?.dirty)saveWorkspaceDocument().catch(()=>{});});
