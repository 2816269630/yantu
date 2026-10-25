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
const workspaceTabId=(()=>{
  try {let id=sessionStorage.getItem('yantu:document-tab');if(!id){id=window.crypto?.randomUUID?.()||`tab-${Date.now()}-${Math.random().toString(36).slice(2)}`;sessionStorage.setItem('yantu:document-tab',id);}return id;}
  catch {return `tab-${Date.now()}-${Math.random().toString(36).slice(2)}`;}
})();
function workspaceDraftKey(id,tabId=workspaceTabId) {return `yantu:document-draft:${id}:${tabId}`;}
function readWorkspaceDraft(id) {
  try {
    const prefix=`yantu:document-draft:${id}`,keys=[...Array(localStorage.length)].map((_,i)=>localStorage.key(i)).filter(key=>key===prefix||key.startsWith(prefix+':'));
    return keys.map(key=>{try {const value=JSON.parse(localStorage.getItem(key));return value&&typeof value.content==='string'&&typeof value.title==='string'?{...value,_key:key}:null;}catch{return null;}}).filter(Boolean).sort((a,b)=>String(b.savedAt||'').localeCompare(String(a.savedAt||'')))[0]||null;
  }
  catch {return null;}
}
function clearWorkspaceDraft(id,key=workspaceDraftKey(id)) {try {localStorage.removeItem(key);}catch {}}
function persistWorkspaceDraft() {
  const workspace=activeDocument;
  if(!workspace?.doc.canEdit||workspace.doc.kind!=='document')return;
  try {localStorage.setItem(workspaceDraftKey(workspace.resource.id),JSON.stringify({title:document.querySelector('#documentTitle')?.value||workspace.resource.title,content:workspacePendingContent(),baseTitle:workspace.resource.title,version:workspace.doc.version,savedAt:new Date().toISOString()}));}
  catch {workspaceStatus('本机记录无法保存，请下载草稿',true);}
}
function clearWorkspaceDraftIfSaved() {
  if(activeDocument&&!activeDocument.dirty&&!activeDocument.titleDirty&&!activeDocument.conflict){
    clearWorkspaceDraft(activeDocument.resource.id);
    if(activeDocument.restoredDraftKey){clearWorkspaceDraft(activeDocument.resource.id,activeDocument.restoredDraftKey);activeDocument.restoredDraftKey=null;}
  }
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
  const localDialog=kind==='document'&&editable?`<dialog class="document-local-dialog" id="documentLocalDialog" aria-label="本地记录"><div class="document-local-head"><strong>本地记录</strong><button type="button" data-doc-action="close-local" aria-label="关闭">×</button></div><p>这份记录保存在当前浏览器。云端已有更新时，请先复制需要的内容，再重新读取云端版本。</p><label>本地标题<input id="documentLocalTitle" readonly></label><label>本地正文<textarea id="documentLocalContent" readonly></textarea></label><div class="document-local-actions"><button type="button" class="btn" data-doc-action="download-draft">下载记录</button><button type="button" class="btn primary" data-doc-action="close-local">完成</button></div></dialog>`:'';
  const conflictBanner=kind==='document'?`<div class="document-conflict" id="documentConflict" role="alert" hidden><strong>云端已有更新</strong><span>自动保存已暂停。本地记录已保留，可先查看并复制需要的内容。</span><button type="button" class="btn" data-doc-action="view-local">查看本地记录</button><button type="button" class="btn" data-doc-action="reload-cloud">重新读取云端</button></div>`:`<div class="document-conflict" id="documentConflict" role="alert" hidden><strong>发现其他页面的更新</strong><span>自动保存已暂停。请先下载本地草稿，再重新读取云端。</span><button type="button" class="btn" data-doc-action="download-draft">下载本地草稿</button><button type="button" class="btn" data-doc-action="reload-cloud">重新读取云端</button></div>`;
  const recovery=kind==='document'&&editable?`<div class="document-recovery" id="documentRecovery" role="status" hidden><strong>发现本地记录</strong><span id="documentRecoveryInfo"></span><button type="button" class="btn" data-doc-action="recover-draft">恢复内容</button><button type="button" class="btn" data-doc-action="view-local">查看记录</button><button type="button" class="btn" data-doc-action="discard-draft">舍弃记录</button></div>`:'';
  return `<div class="document-workspace"><header class="document-topbar"><div class="document-top-left"><a href="#${esc(back)}" class="document-home" aria-label="返回我的云盘">${icon('back')}</a><span class="document-mark">${icon(kind==='sheet'?'tasks':kind==='slides'?'layers':'file')}</span><div class="document-heading"><div class="document-title-top"><input id="documentTitle" data-document-title value="${esc(resource.title)}" maxlength="200" aria-label="文档标题" title="点击修改标题" ${editable?'':'readonly'}>${editable?'<button type="button" class="document-title-edit" data-doc-action="edit-title" aria-label="修改文档标题" title="修改文档标题">✎</button>':''}</div><span id="documentSaveStatus">${editable?'已保存到云端':'只读文档'}</span></div></div><div class="document-top-actions">${kind==='document'&&editable?`<button type="button" class="btn" data-doc-action="toggle-preview">${activeDocument.preview?'源码':'完成'}</button>`:''}${editable?'<button type="button" class="btn" data-doc-action="save">保存</button>'+btn('分享','cloud-shares',resource.id,'primary'):''}<button type="button" class="btn document-more" data-action="cloud-resource-more" data-id="${esc(resource.id)}" aria-haspopup="menu">···</button></div></header><div class="document-toolbar"><span>${label}</span>${kind==='sheet'&&editable?'<button type="button" data-doc-action="add-row">＋ 行</button><button type="button" data-doc-action="add-column">＋ 列</button>':''}${kind==='slides'&&editable?'<button type="button" data-doc-action="add-slide">＋ 页面</button>':''}<a href="/api/v1/resources/${enc(resource.id)}/download">下载原文件</a></div>${recovery}${conflictBanner}<div class="document-body">${outline}<main class="document-stage">${content}</main></div>${equationDialog}${localDialog}</div>`;
}

pages.resource = async id => {
  const resource=await api(`/resources/${enc(id)}`);
  if(!workspaceKind(resource.fileName)) {activeDocument=null;return originalResourcePage(id);}
  let doc;
  try {doc=await api(`/resources/${enc(id)}/document`);}
  catch(error) {if(error.status===415){activeDocument=null;return originalResourcePage(id);}throw error;}
  if(doc.kind==='document'){
    activeDocument=null;
    state.data.resource=resource;
    return window.structuredDocumentPage(resource,doc);
  }
  activeDocument={doc,resource,dirty:false,saving:false,conflict:false,pendingSave:false,timer:null,titleDirty:false,titleSaving:false,pendingTitle:false,titleTimer:null,activeSlide:0,preview:doc.kind==='document',lastSaved:JSON.stringify(doc.content)};
  if(doc.kind==='document'&&doc.canEdit){
    activeDocument.recovery=readWorkspaceDraft(resource.id);
    if(activeDocument.recovery?.content===doc.content&&activeDocument.recovery.title===resource.title){clearWorkspaceDraft(resource.id,activeDocument.recovery._key);activeDocument.recovery=null;}
  }
  state.data.resource=resource;
  document.body.classList.add('document-mode');
  document.title=`${resource.title} · 研途`;
  const markup=workspaceMarkup(resource,doc);
  setTimeout(()=>{
    if(activeDocument?.resource.id!==id||!activeDocument.recovery)return;
    const banner=document.querySelector('#documentRecovery');if(!banner)return;
    document.querySelector('#documentRecoveryInfo').textContent=activeDocument.recovery.version===doc.version&&activeDocument.recovery.baseTitle===resource.title?'尚未同步到云端':'基于较早的云端版本';
    banner.hidden=false;
  },0);
  return markup;
};

function workspaceContent() {
  if(!activeDocument)return null;
  const {doc}=activeDocument;
  if(doc.kind==='sheet'||doc.kind==='slides')return doc.content;
  const editor=document.querySelector('[data-document-editor]');
  return editor?(editor.innerText??editor.textContent).replace(/\r/g,''):doc.content;
}
function workspaceInlineMarkdown(node) {
  if(node.nodeType===Node.TEXT_NODE)return node.textContent;
  if(node.nodeType!==Node.ELEMENT_NODE)return '';
  if(node.matches('.document-formula-target'))return `$${node.dataset.docMathSource||''}$`;
  if(node.tagName==='BR')return '\n';
  const body=[...node.childNodes].map(workspaceInlineMarkdown).join('');
  if(node.matches('strong,b'))return `**${body}**`;
  if(node.matches('em,i'))return `*${body}*`;
  if(node.matches('code'))return `\`${body}\``;
  return node.matches('div,p')?`${body}\n`:body;
}
function workspaceBlockContent(edit) {
  if(edit.element.tagName==='PRE'){
    const lines=edit.originalSource.split('\n'),opening=lines[0],closing=lines.at(-1)?.trim().startsWith('```')?lines.at(-1):'```';
    return `${opening}\n${edit.element.textContent}\n${closing}`;
  }
  return [...edit.element.childNodes].map(workspaceInlineMarkdown).join('').replace(/\n+$/,'');
}
function workspacePendingContent() {
  const body=workspaceContent(),edit=activeDocument?.inlineEdit;
  if(!edit?.changed)return body;
  const lines=body.split('\n'),value=workspaceBlockContent(edit);
  lines.splice(edit.start,edit.end-edit.start+1,...value.split('\n').map((line,index)=>index===0||edit.prefixEachLine?edit.prefix+line:line));
  return lines.join('\n');
}
function setWorkspacePreview(preview) {
  if(activeDocument?.doc.kind!=='document')return;
  if(activeDocument.inlineEdit)commitWorkspaceBlock();
  const editor=document.querySelector('[data-document-editor]'),rendered=document.querySelector('[data-document-preview]');
  if(!editor||!rendered)return;
  const wasPreview=activeDocument.preview;
  activeDocument.preview=preview;
  if(preview)rendered.innerHTML=renderDocumentPreview(workspaceContent());
  editor.hidden=preview;rendered.hidden=!preview;
  const button=document.querySelector('[data-doc-action="toggle-preview"]');
  if(button)button.textContent=preview?'源码':'完成';
  if(!preview){editor.focus();const selection=window.getSelection();if(wasPreview||!selection?.rangeCount||!editor.contains(selection.anchorNode)){const range=document.createRange();range.selectNodeContents(editor);range.collapse(false);selection?.removeAllRanges();selection?.addRange(range);}}
}
function openWorkspaceBlock(target) {
  if(activeDocument?.doc.kind!=='document'||!activeDocument.doc.canEdit||!activeDocument.preview)return;
  if(activeDocument.inlineEdit?.element===target)return;
  if(activeDocument.inlineEdit)commitWorkspaceBlock();
  const start=Number(target.dataset.docLine),end=Number(target.dataset.docEndLine),lines=workspaceContent().split('\n');
  if(!Number.isInteger(start)||!Number.isInteger(end)||start<0||end<start)return;
  const raw=lines.slice(start,end+1).join('\n');
  const prefix=target.matches('h1,h2,h3,h4,h5,h6,li,blockquote')?(raw.match(/^\s*(?:#{1,6}\s+|[-*+]\s+|\d+\.\s+|>\s*)/)||[''])[0]:'';
  if(target.matches('.document-preview-empty'))target.textContent='';
  target.contentEditable='true';target.spellcheck=false;target.classList.add('is-editing');
  activeDocument.inlineEdit={start,end,element:target,originalSource:raw,prefix,originalPrefix:prefix,prefixEachLine:target.matches('blockquote'),changed:false};
  target.focus();
  const selection=window.getSelection();
  if(selection&&!target.contains(selection.anchorNode)){const range=document.createRange();range.selectNodeContents(target);range.collapse(false);selection.removeAllRanges();selection.addRange(range);}
}
function commitWorkspaceBlock(cancel=false) {
  const edit=activeDocument?.inlineEdit;if(!edit)return;
  hideWorkspacePopovers();
  activeDocument.inlineEdit=null;
  const content=workspaceBlockContent(edit);
  const next=content.split('\n').map((line,index)=>index===0||edit.prefixEachLine?edit.prefix+line:line).join('\n');
  if(!cancel&&edit.changed&&(next!==edit.originalSource)){
    const lines=workspaceContent().split('\n');lines.splice(edit.start,edit.end-edit.start+1,...next.split('\n'));
    const editor=document.querySelector('[data-document-editor]');editor.textContent=lines.join('\n');
    editor.dispatchEvent(new Event('input',{bubbles:true}));
  } else document.querySelector('[data-document-preview]').innerHTML=renderDocumentPreview(workspaceContent());
}
function formatWorkspaceBlock(kind) {
  const edit=activeDocument?.inlineEdit;if(!edit)return;
  const selection=window.getSelection();
  if(kind==='bold'){
    if(!selection?.rangeCount||selection.isCollapsed||!edit.element.contains(selection.anchorNode))return;
    const range=selection.getRangeAt(0),strong=document.createElement('strong');
    try {range.surroundContents(strong);} catch {strong.appendChild(range.extractContents());range.insertNode(strong);}
    selection.removeAllRanges();edit.element.dispatchEvent(new Event('input',{bubbles:true}));
  } else {
    const prefix={h1:'# ',h2:'## ',bullet:'- ',number:'1. ',quote:'> '}[kind];if(!prefix)return;
    edit.prefix=prefix;edit.element.dataset.pendingFormat=kind;edit.element.dispatchEvent(new Event('input',{bubbles:true}));
  }
  hideWorkspacePopovers();edit.element.focus();
}
function workspacePopover(kind) {
  let node=document.querySelector(`#document${kind}Popover`);
  if(node)return node;
  node=document.createElement('div');node.id=`document${kind}Popover`;node.className=kind==='Slash'?'document-slash-menu':'document-selection-tools';node.hidden=true;
  node.innerHTML=kind==='Slash'?'<div class="document-slash-heading">常用</div><button type="button" data-slash-command="formula"><span>𝑓𝑥</span>公式</button><button type="button" data-slash-command="h1"><span>H₁</span>一级标题</button><button type="button" data-slash-command="h2"><span>H₂</span>二级标题</button><button type="button" data-slash-command="bullet"><span>≡</span>项目符号</button><button type="button" data-slash-command="quote"><span>❝</span>引用</button>':'<button type="button" data-block-format="bold" title="加粗 Ctrl+B"><b>B</b></button><button type="button" data-block-format="h1">H1</button><button type="button" data-block-format="h2">H2</button>';
  document.body.appendChild(node);return node;
}
function hideWorkspacePopovers() {for(const kind of ['Slash','Selection']){const node=document.querySelector(`#document${kind}Popover`);if(node)node.hidden=true;}}
function positionWorkspacePopover(node,rect) {node.style.left=`${Math.max(12,Math.min(window.innerWidth-230,rect?.left||12))}px`;node.style.top=`${Math.max(12,Math.min(window.innerHeight-50,(rect?.bottom||12)+8))}px`;}
function updateWorkspaceSelection() {
  const edit=activeDocument?.inlineEdit;if(!edit)return;
  const selection=window.getSelection(),node=workspacePopover('Selection');
  if(!selection?.rangeCount||selection.isCollapsed||!edit.element.contains(selection.anchorNode)){node.hidden=true;return;}
  const range=selection.getRangeAt(0);positionWorkspacePopover(node,range.getBoundingClientRect?.()||edit.element.getBoundingClientRect?.());node.hidden=false;
}
function updateWorkspaceSlash() {
  const edit=activeDocument?.inlineEdit;if(!edit)return;
  const selection=window.getSelection(),node=workspacePopover('Slash');
  if(!selection?.rangeCount||!selection.isCollapsed||!edit.element.contains(selection.anchorNode)){node.hidden=true;return;}
  const range=selection.getRangeAt(0),before=range.cloneRange();before.selectNodeContents(edit.element);before.setEnd(range.startContainer,range.startOffset);
  const match=before.toString().match(/(?:^|\s)\/(\w*)$/);
  if(!match){node.hidden=true;return;}
  const query=match[1].toLowerCase(),buttons=[...node.querySelectorAll('[data-slash-command]')];
  for(const button of buttons)button.hidden=Boolean(query&&!button.textContent.toLowerCase().includes(query)&&!(button.dataset.slashCommand==='formula'&&['gs','eq'].includes(query)));
  positionWorkspacePopover(node,range.getBoundingClientRect?.()||edit.element.getBoundingClientRect?.());node.hidden=false;
}
function removeWorkspaceSlash() {
  const selection=window.getSelection(),edit=activeDocument?.inlineEdit;
  if(!edit||!selection?.rangeCount)return;
  const range=selection.getRangeAt(0),node=range.startContainer;
  if(node.nodeType!==Node.TEXT_NODE)return;
  const before=node.textContent.slice(0,range.startOffset),match=before.match(/\/(\w*)$/);if(!match)return;
  node.textContent=before.slice(0,-match[0].length)+node.textContent.slice(range.startOffset);
  const caret=document.createRange();caret.setStart(node,before.length-match[0].length);caret.collapse(true);selection.removeAllRanges();selection.addRange(caret);
}
function insertWorkspaceSlashFormula() {
  const edit=activeDocument?.inlineEdit,selection=window.getSelection();if(!edit||!selection?.rangeCount)return;
  const range=selection.getRangeAt(0);range.deleteContents();const node=document.createTextNode('$x$');range.insertNode(node);
  edit.element.dispatchEvent(new Event('input',{bubbles:true}));commitWorkspaceBlock();
  const formula=[...document.querySelectorAll('[data-document-preview] [data-doc-math-source="x"]')].at(-1);
  if(formula){const found=workspaceFormulaAt(formula);if(found)openWorkspaceFormulaPopover({...found,pendingNew:true},formula);}
}
function openWorkspaceFormulaPopover(found,target) {
  let popover=document.querySelector('#documentFormulaPopover');
  if(!popover){popover=document.createElement('div');popover.id='documentFormulaPopover';popover.className='document-formula-popover';popover.innerHTML='<textarea aria-label="编辑 LaTeX 公式" spellcheck="false"></textarea><div class="document-formula-popover-preview"></div><div class="document-formula-popover-actions"><span>Esc 保存并关闭</span><button type="button" data-formula-action="cancel">取消</button><button type="button" data-formula-action="save">保存</button></div>';document.body.appendChild(popover);}
  activeDocument.formulaEdit={...found};
  const source=popover.querySelector('textarea');source.value=found.source;
  popover.querySelector('.document-formula-popover-preview').innerHTML=documentMath(found.source,found.block);
  const rect=target.getBoundingClientRect();popover.style.left=`${Math.max(12,Math.min(window.innerWidth-400,rect.left))}px`;popover.style.top=`${Math.max(12,Math.min(window.innerHeight-220,rect.bottom+8))}px`;
  popover.hidden=false;source.focus();
}
function closeWorkspaceFormulaPopover(save=false) {
  const popover=document.querySelector('#documentFormulaPopover'),edit=activeDocument?.formulaEdit;if(!popover||!edit)return;
  if(save){
    const value=popover.querySelector('textarea').value.trim();if(!value||value.includes('$$')){workspaceStatus('请输入有效的公式源码',true);return;}
    const editor=document.querySelector('[data-document-editor]'),body=workspaceContent();
    editor.textContent=body.slice(0,edit.start)+(edit.block?`$$${value}$$`:`$${value}$`)+body.slice(edit.end);
    editor.dispatchEvent(new Event('input',{bubbles:true}));
  } else if(edit.pendingNew){
    const editor=document.querySelector('[data-document-editor]'),body=workspaceContent();editor.textContent=body.slice(0,edit.start)+body.slice(edit.end);editor.dispatchEvent(new Event('input',{bubbles:true}));
  }
  activeDocument.formulaEdit=null;popover.hidden=true;
}
function workspaceEquationPreview() {
  const source=document.querySelector('#documentEquationSource')?.value||'',block=document.querySelector('[name="equationKind"]:checked')?.value==='block';
  const preview=document.querySelector('#documentEquationPreview');
  if(preview)preview.innerHTML=source.trim()?documentMath(source,block):'<span class="document-equation-placeholder">输入 LaTeX 后在此预览</span>';
}
function workspaceFormulaAt(target) {
  const body=workspaceContent(),lines=body.split('\n'),line=Number(target.dataset.docMathBlock??target.dataset.docMathLine);
  if(!Number.isInteger(line)||line<0||line>=lines.length)return null;
  const offset=lines.slice(0,line).reduce((sum,text)=>sum+text.length+1,0),raw=lines[line];
  if(target.hasAttribute('data-doc-math-block')){
    const opening=raw.trimStart().startsWith('$$')?'$$':'\\[',closing=opening==='$$'?'$$':'\\]';
    const start=offset+raw.indexOf(opening),end=body.indexOf(closing,start+opening.length);
    return end<0?null:{start,end:end+closing.length,source:body.slice(start+opening.length,end),block:true};
  }
  const matches=[...raw.matchAll(/\\\((.+?)\\\)|(?<!\\)\$([^$\n]+?)\$(?!\$)/g)],match=matches[Number(target.dataset.docMathIndex)];
  return match?{start:offset+match.index,end:offset+match.index+match[0].length,source:match[1]??match[2],block:false}:null;
}
function openWorkspaceEquation(initial='',block=true,replacement=null) {
  if(activeDocument?.doc.kind!=='document'||!activeDocument.doc.canEdit)return;
  if(activeDocument.preview&&!replacement)setWorkspacePreview(false);
  const editor=document.querySelector('[data-document-editor]'),selection=window.getSelection();
  activeDocument.equationRange=replacement?null:selection?.rangeCount&&editor.contains(selection.anchorNode)?selection.getRangeAt(0).cloneRange():null;
  activeDocument.equationReplacement=replacement;
  const dialog=document.querySelector('#documentEquationDialog'),source=document.querySelector('#documentEquationSource');
  dialog.setAttribute('aria-label',replacement?'编辑公式':'插入公式');
  dialog.querySelector('.document-equation-head strong').textContent=replacement?'编辑公式':'插入公式';
  dialog.querySelector('[data-doc-action="insert-equation"]').textContent=replacement?'保存公式':'插入公式';
  source.value=initial;document.querySelector(`[name="equationKind"][value="${block?'block':'inline'}"]`).checked=true;
  workspaceEquationPreview();dialog.showModal();source.focus();
}
function insertWorkspaceEquation() {
  const dialog=document.querySelector('#documentEquationDialog'),source=document.querySelector('#documentEquationSource')?.value.trim();
  if(!source){document.querySelector('#documentEquationSource')?.focus();return;}
  if(source.includes('$$')){workspaceStatus('公式源码不能包含连续的 $$',true);return;}
  const editor=document.querySelector('[data-document-editor]'),block=document.querySelector('[name="equationKind"]:checked')?.value==='block';
  const replacement=activeDocument.equationReplacement;
  if(replacement){
    const body=workspaceContent(),before=body.slice(0,replacement.start),after=body.slice(replacement.end);
    const markup=block?`${before&&!before.endsWith('\n')?'\n':''}$$${source}$$${after&&!after.startsWith('\n')?'\n':''}`:`$${source}$`;
    editor.textContent=before+markup+after;
    activeDocument.equationReplacement=null;activeDocument.equationRange=null;dialog.close();
    editor.dispatchEvent(new Event('input',{bubbles:true}));return;
  }
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
  persistWorkspaceDraft();
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
  if(workspace.formulaEdit?.pendingNew)return;
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
    if(activeDocument===workspace&&serialized===JSON.stringify(workspaceContent())&&!workspace.pendingSave){workspace.dirty=false;workspaceStatus('已保存到云端');clearWorkspaceDraftIfSaved();}
  } catch(error) {
    if(activeDocument===workspace){
      if(error.status===409)markWorkspaceConflict();
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
  const record=!activeDocument.conflict&&activeDocument.recovery||{title:document.querySelector('#documentTitle')?.value.trim()||activeDocument.resource.title,content:workspaceContent()};
  const title=record.title;
  const name=(title||'文档').replace(/[\\/:*?"<>|]/g,'_');
  const draft=JSON.stringify({kind:activeDocument.doc.kind,title,content:record.content},null,2);
  const url=URL.createObjectURL(new Blob([draft],{type:'application/json;charset=utf-8'}));
  const anchor=document.createElement('a');anchor.href=url;anchor.download=`${name}-本地草稿.json`;anchor.click();
  setTimeout(()=>URL.revokeObjectURL(url),3000);
}
function markWorkspaceConflict(message='保存冲突 · 本地记录已保留') {
  if(!activeDocument)return;
  activeDocument.conflict=true;activeDocument.dirty=true;
  clearTimeout(activeDocument.timer);clearTimeout(activeDocument.titleTimer);
  persistWorkspaceDraft();
  document.querySelector('#documentConflict')?.removeAttribute('hidden');
  document.querySelector('[data-doc-action="save"]')?.setAttribute('disabled','');
  workspaceStatus(message,true);
}
function viewWorkspaceLocalRecord() {
  const dialog=document.querySelector('#documentLocalDialog');if(!dialog)return;
  const record=!activeDocument.conflict&&activeDocument.recovery||{title:document.querySelector('#documentTitle')?.value||activeDocument.resource.title,content:workspaceContent()};
  dialog.querySelector('#documentLocalTitle').value=record.title;
  dialog.querySelector('#documentLocalContent').value=record.content;
  dialog.showModal();
}
function recoverWorkspaceDraft() {
  const workspace=activeDocument,record=workspace?.recovery;if(!record)return;
  const editor=document.querySelector('[data-document-editor]');editor.textContent=record.content;
  syncWorkspaceTitle(record.title);workspace.doc.content=record.content;
  document.querySelector('#documentRecovery').hidden=true;workspace.restoredDraftKey=record._key;workspace.recovery=null;
  const stale=record.version!==workspace.doc.version||record.baseTitle!==workspace.resource.title;
  if(workspace.doc.kind==='document')setWorkspacePreview(true);
  workspace.dirty=record.content!==JSON.parse(workspace.lastSaved);
  workspace.titleDirty=record.title!==workspace.resource.title;
  persistWorkspaceDraft();refreshWorkspaceOutline();
  if(stale)markWorkspaceConflict('本地记录基于旧版本 · 请复制需要的内容');
  else {if(workspace.dirty)queueWorkspaceSave();if(workspace.titleDirty)queueWorkspaceTitleSave();}
}
function syncWorkspaceTitle(title,source=null) {
  document.querySelectorAll('[data-document-title]').forEach(input=>{if(input!==source)input.value=title;});
  const root=document.querySelector('[data-outline-top]');if(root)root.textContent=title;
}
function queueWorkspaceTitleSave() {
  const workspace=activeDocument;
  if(!workspace?.doc.canEdit)return;
  workspace.titleDirty=true;workspaceStatus('未保存');
  persistWorkspaceDraft();
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
  if(title===workspace.resource.title){workspace.titleDirty=false;if(!workspace.dirty)workspaceStatus('已保存到云端');clearWorkspaceDraftIfSaved();return;}
  workspace.titleSaving=true;workspaceStatus('保存中…');
  try {
    const updated=await api(`/resources/${enc(workspace.resource.id)}`,'PATCH',{title,expectedTitle:workspace.resource.title});
    workspace.resource.title=updated.title;workspace.resource.fileName=updated.fileName;
    if(activeDocument===workspace){
      state.data.resource=workspace.resource;
      document.title=`${updated.title} · 研途`;
      if(input.value.trim()===title){syncWorkspaceTitle(updated.title);workspace.titleDirty=false;if(!workspace.dirty)workspaceStatus('已保存到云端');clearWorkspaceDraftIfSaved();}
      else workspace.pendingTitle=true;
    }
  } catch(error) {
    if(activeDocument===workspace){
      if(error.status===409){workspace.titleDirty=true;markWorkspaceConflict('标题冲突 · 本地记录已保留');}
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
  if(event.target===activeDocument.inlineEdit?.element){
    activeDocument.inlineEdit.changed=true;
    activeDocument.dirty=true;workspaceStatus('未保存');persistWorkspaceDraft();
    updateWorkspaceSlash();updateWorkspaceSelection();return;
  }
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
  const formula=event.target.closest('.document-formula-target');
  if(formula){
    if(activeDocument.doc.canEdit){
      const block=Boolean(formula.closest('[data-doc-editable]'));
      const line=formula.dataset.docMathLine,index=formula.dataset.docMathIndex;
      if(block&&activeDocument.inlineEdit)commitWorkspaceBlock();
      const current=block?document.querySelector(`[data-doc-math-line="${line}"][data-doc-math-index="${index}"]`):formula;
      const found=current&&workspaceFormulaAt(current);if(found)openWorkspaceFormulaPopover(found,current);
    }
    return;
  }
  const slashCommand=event.target.closest('[data-slash-command]');
  if(slashCommand){const kind=slashCommand.dataset.slashCommand;removeWorkspaceSlash();hideWorkspacePopovers();if(kind==='formula')insertWorkspaceSlashFormula();else formatWorkspaceBlock(kind);return;}
  const formulaAction=event.target.closest('[data-formula-action]');
  if(formulaAction){closeWorkspaceFormulaPopover(formulaAction.dataset.formulaAction==='save');return;}
  const blockFormat=event.target.closest('[data-block-format]');
  if(blockFormat){formatWorkspaceBlock(blockFormat.dataset.blockFormat);return;}
  const block=event.target.closest('[data-doc-editable]');
  if(block&&activeDocument.preview){openWorkspaceBlock(block);return;}
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
  if(action==='cancel-equation'){activeDocument.equationRange=null;activeDocument.equationReplacement=null;document.querySelector('#documentEquationDialog')?.close();return;}
  if(action==='insert-equation'){insertWorkspaceEquation();return;}
  if(action==='edit-title'){(document.querySelector('.document-paper-title [data-document-title]')||document.querySelector('#documentTitle'))?.focus();return;}
  if(action==='toggle-outline'){const panel=document.querySelector('#documentOutlinePanel'),button=event.target.closest('[data-doc-action]'),collapsed=panel.classList.toggle('is-collapsed');button.setAttribute('aria-expanded',String(!collapsed));button.setAttribute('aria-label',collapsed?'展开目录':'收起目录');button.title=collapsed?'展开目录':'收起目录';button.textContent=collapsed?'»':'«';return;}
  if(action==='save')saveWorkspaceDocument().catch(()=>{});
  if(action==='download-draft')downloadWorkspaceDraft();
  if(action==='view-local'){viewWorkspaceLocalRecord();return;}
  if(action==='close-local'){document.querySelector('#documentLocalDialog')?.close();return;}
  if(action==='recover-draft'){recoverWorkspaceDraft();return;}
  if(action==='discard-draft'){clearWorkspaceDraft(activeDocument.resource.id,activeDocument.recovery?._key);activeDocument.recovery=null;document.querySelector('#documentRecovery').hidden=true;return;}
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
document.addEventListener('input',event=>{if(event.target?.matches?.('#documentFormulaPopover textarea'))document.querySelector('#documentFormulaPopover .document-formula-popover-preview').innerHTML=documentMath(event.target.value,activeDocument?.formulaEdit?.block);});
document.addEventListener('change',event=>{if(event.target?.name==='equationKind')workspaceEquationPreview();});
document.addEventListener('mousedown',event=>{if(event.target.closest('[data-block-format],[data-slash-command]'))event.preventDefault();});
document.addEventListener('selectionchange',()=>{updateWorkspaceSelection();updateWorkspaceSlash();});
document.addEventListener('focusout',event=>{
  if(event.target?.matches?.('[data-document-title]'))saveWorkspaceTitle().catch(()=>{});
  if(event.target===activeDocument?.inlineEdit?.element)setTimeout(()=>{if(activeDocument?.inlineEdit?.element===event.target&&!document.querySelector('#documentSlashPopover')?.contains(document.activeElement))commitWorkspaceBlock();},0);
});
document.addEventListener('keydown',event=>{
  if(!activeDocument||state.page!=='resource')return;
  if(event.target?.matches?.('#documentFormulaPopover textarea')&&event.key==='Escape'){event.preventDefault();closeWorkspaceFormulaPopover(true);return;}
  if(event.target?.matches?.('.document-formula-target')&&(event.key==='Enter'||event.key===' ')){event.preventDefault();event.target.click();return;}
  if(event.target===activeDocument.inlineEdit?.element){
    if(event.key==='Escape'){event.preventDefault();commitWorkspaceBlock(true);return;}
    if(event.key==='Enter'&&(event.ctrlKey||event.metaKey)){event.preventDefault();commitWorkspaceBlock();return;}
    if(event.key.toLowerCase()==='b'&&(event.ctrlKey||event.metaKey)){event.preventDefault();formatWorkspaceBlock('bold');return;}
    if(event.key==='Enter'&&!document.querySelector('#documentSlashPopover')?.hidden){
      const first=document.querySelector('#documentSlashPopover [data-slash-command]:not([hidden])');if(first){event.preventDefault();first.click();return;}
    }
    if(event.key==='/'||event.key==='Backspace'||event.key==='Escape')setTimeout(updateWorkspaceSlash,0);
  }
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
