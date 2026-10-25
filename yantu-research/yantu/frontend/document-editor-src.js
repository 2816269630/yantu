import { Editor } from '@tiptap/core';
import { createDocumentExtensions, documentBlockTypes } from './document-schema.mjs';

// The editor state is the document. The DOM is only its view; no rendered block is
// made temporarily editable and no Markdown string is reconstructed after typing.
let pending = null;
let current = null;
const tabId = (() => {
  try {
    let value = sessionStorage.getItem('yantu:document-tab');
    if (!value) {
      value = crypto.randomUUID?.() || `tab-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      sessionStorage.setItem('yantu:document-tab', value);
    }
    return value;
  } catch { return `tab-${Date.now()}`; }
})();
const draftKey = id => `yantu:document-draft:${id}:${tabId}`;
const snapshot = value => JSON.stringify(value);
const blockTypes = new Set(documentBlockTypes);
const validBlockId = value => typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(value);
const randomBlockId = () => crypto.randomUUID?.() || 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, letter => {
  const value = Math.floor(Math.random() * 16);
  return (letter === 'x' ? value : (value & 3) | 8).toString(16);
});
const structured = value => value && typeof value === 'object' && value.type === 'doc' && [1, 2].includes(value.schemaVersion);
const status = (message, error = false) => {
  const node = document.querySelector('#documentSaveStatus');
  if (node) { node.textContent = message; node.classList.toggle('is-error', error); }
};
const content = (workspace = current) => workspace?.editor ? { schemaVersion: 2, ...workspace.editor.getJSON() } : null;
const untitledTitle = '未命名文档';
const title = () => {
  const input = document.querySelector('#documentTitle');
  return input ? input.value.trim() || untitledTitle : current?.resource.title?.trim() || untitledTitle;
};

function repairBlockIds(editor) {
  const seen = new Set();
  const transaction = editor.state.tr;
  editor.state.doc.descendants((node, pos) => {
    if (!blockTypes.has(node.type.name)) return;
    let id = node.attrs.id;
    if (!validBlockId(id) || seen.has(id)) {
      id = randomBlockId();
      transaction.setNodeMarkup(pos, undefined, { ...node.attrs, id }, node.marks);
    }
    seen.add(id);
  });
  if (!transaction.docChanged) return false;
  editor.view.dispatch(transaction);
  return true;
}

function readDraft(id) {
  try {
    const prefix = `yantu:document-draft:${id}`;
    return [...Array(localStorage.length)].map((_, i) => localStorage.key(i))
      .filter(key => key === prefix || key.startsWith(prefix + ':'))
      .map(key => { try { const value = JSON.parse(localStorage.getItem(key)); return value?.content && typeof value.title === 'string' ? { ...value, key } : null; } catch { return null; } })
      .filter(Boolean).sort((a, b) => String(b.savedAt).localeCompare(String(a.savedAt)))[0] || null;
  } catch { return null; }
}
function persistDraft() {
  if (!current?.doc.canEdit) return;
  try {
    localStorage.setItem(draftKey(current.resource.id), JSON.stringify({
      title: title(), content: content(), baseTitle: current.resource.title,
      version: current.doc.version, savedAt: new Date().toISOString(),
    }));
  } catch { status('本机记录保存失败', true); }
}
function clearDraft() {
  if (!current || current.dirty || current.titleDirty || current.conflict) return;
  try {
    localStorage.removeItem(draftKey(current.resource.id));
    if (current.restoredKey) localStorage.removeItem(current.restoredKey);
  } catch {}
}

function outlineRows() {
  if (!current?.editor) return;
  const root = document.querySelector('#documentOutline');
  if (!root) return;
  const headings = [];
  current.editor.state.doc.descendants((node, pos) => {
    if (node.type.name === 'heading' && node.textContent.trim()) {
      headings.push({ pos, level: node.attrs.level, text: node.textContent });
    }
  });
  const visibleTitle = document.querySelector('.document-paper-title input')?.value.trim();
  const rootRow = visibleTitle && visibleTitle !== untitledTitle
    ? `<li class="document-outline-root"><button type="button" class="document-outline-link" data-outline-top>${esc(visibleTitle)}</button></li>` : '';
  root.innerHTML = rootRow + headings.map(item => `<li class="document-outline-item" style="padding-left:${Math.min(item.level - 1, 5) * 13}px"><button type="button" class="document-outline-link" data-outline-pos="${item.pos}">${esc(item.text)}</button></li>`).join('');
}
function syncTitle(value, origin) {
  const effective = value.trim() || untitledTitle;
  document.querySelectorAll('[data-document-title]').forEach(input => {
    if (input === origin) return;
    input.value = input.id === 'documentTitle' ? effective : effective === untitledTitle ? '' : value;
  });
  outlineRows();
}
function queueTitle() {
  if (!current?.doc.canEdit) return;
  current.pendingTitle = title();
  current.titleDirty = true; status('未保存'); persistDraft();
  clearTimeout(current.titleTimer);
  if (current.conflict) return;
  if (current.titleSaving) { current.pendingTitle = title(); return; }
  current.titleTimer = setTimeout(() => saveTitle().catch(error => status(error.message, true)), 800);
}
async function saveTitle(workspace = current, queuedTitle = null) {
  if (!workspace?.titleDirty || workspace.conflict) return;
  const next = (queuedTitle ?? (current === workspace ? title() : workspace.pendingTitle))?.trim() || untitledTitle;
  if (workspace.titleSaving) {
    if (queuedTitle !== null || !workspace.pendingTitle) workspace.pendingTitle = next;
    return;
  }
  clearTimeout(workspace.titleTimer);
  if (next === workspace.resource.title) {
    workspace.titleDirty = false;
    workspace.pendingTitle = null;
    if (current === workspace) { syncTitle(next); clearDraft(); if (!workspace.dirty) status('已保存到云端'); }
    return;
  }
  workspace.titleSaving = true;
  if (current === workspace) status('保存中…');
  let saved = false;
  try {
    const updated = await api(`/resources/${enc(workspace.resource.id)}`, 'PATCH', { title: next, expectedTitle: workspace.resource.title });
    saved = true;
    workspace.resource.title = updated.title; workspace.resource.fileName = updated.fileName;
    if (current === workspace) {
      document.title = `${updated.title} · 研途`;
      if (title() === next) { syncTitle(next); workspace.titleDirty = false; workspace.pendingTitle = null; }
      else { workspace.titleDirty = true; workspace.pendingTitle = title(); persistDraft(); }
      if (!workspace.dirty && !workspace.titleDirty) status('已保存到云端');
      clearDraft();
    } else {
      workspace.titleDirty = typeof workspace.pendingTitle === 'string' && workspace.pendingTitle !== workspace.resource.title;
    }
  } catch (error) {
    if (current === workspace) {
      if (error.status === 409) conflict('标题已在其他页面修改');
      else status(error.message, true);
    }
    throw error;
  } finally {
    workspace.titleSaving = false;
    if (saved && workspace.titleDirty && !workspace.conflict) {
      const pendingTitle = workspace.pendingTitle;
      workspace.pendingTitle = null;
      if (typeof pendingTitle === 'string' && pendingTitle !== workspace.resource.title) {
        saveTitle(workspace, pendingTitle).catch(error => {
          if (current === workspace && !workspace.conflict) status(error.message, true);
        });
      }
    }
  }
}
function queueSave() {
  if (!current?.doc.canEdit) return;
  current.dirty = true; status('未保存'); persistDraft();
  clearTimeout(current.timer);
  if (current.conflict) return;
  if (current.saving) { current.pendingContent = content(current); return; }
  current.timer = setTimeout(() => save().catch(error => { if (!current?.conflict) status(error.message, true); }), 1200);
}
async function save(workspace = current, queuedContent = null) {
  if (!workspace?.doc.canEdit || workspace.conflict) return;
  const value = queuedContent || content(workspace);
  if (workspace.saving) {
    if (queuedContent || !workspace.pendingContent) workspace.pendingContent = value;
    return;
  }
  clearTimeout(workspace.timer);
  const serial = snapshot(value);
  if (serial === workspace.lastSaved) {
    workspace.dirty = false;
    if (current === workspace) {
      clearDraft();
      if (!workspace.titleDirty) status('已保存到云端');
    }
    return;
  }
  workspace.saving = true;
  if (current === workspace) status('保存中…');
  let saved = false;
  try {
    const result = await api(`/resources/${enc(workspace.resource.id)}/document`, 'PUT', { version: workspace.doc.version, content: value });
    saved = true;
    workspace.doc.version = result.version; workspace.lastSaved = serial;
    if (current === workspace) {
      const time = document.querySelector('#documentModifiedAt');
      if (time && result.modifiedAt) { time.dateTime = result.modifiedAt; time.textContent = workspaceModifiedLabel(result.modifiedAt); }
      workspace.dirty = snapshot(content(workspace)) !== serial;
      if (!workspace.dirty) {
        if (!workspace.titleDirty) status('已保存到云端');
        clearDraft();
      }
    }
  } catch (error) {
    if (current === workspace) {
      if (error.status === 409) conflict('云端已有更新');
      else status(error.message, true);
    }
    throw error;
  } finally {
    workspace.saving = false;
    if (saved && !workspace.conflict) {
      const next = workspace.pendingContent || (current === workspace && workspace.dirty ? content(workspace) : null);
      workspace.pendingContent = null;
      if (next && snapshot(next) !== workspace.lastSaved) {
        save(workspace, next).catch(error => {
          if (current === workspace && !workspace.conflict) status(error.message, true);
        });
      }
    }
  }
}
function conflict(message) {
  if (!current) return;
  current.conflict = true; current.dirty = true;
  clearTimeout(current.timer); clearTimeout(current.titleTimer);
  persistDraft();
  document.querySelector('#documentConflict')?.removeAttribute('hidden');
  status(`${message} · 本地记录已保留`, true);
}
function setContent(value) {
  if (typeof value === 'string') current.editor.commands.setContent(value, { contentType: 'markdown', emitUpdate: false });
  else current.editor.commands.setContent(value, { emitUpdate: false });
  outlineRows();
}
async function convertDocument() {
  const workspace = current;
  if (!workspace?.doc.canConvert || workspace.conflict) return;
  const button = document.querySelector('.document-compatibility [data-structured-action="convert-document"]');
  if (button) button.disabled = true;
  status('转换中…');
  try {
    repairBlockIds(workspace.editor);
    const value = content(workspace);
    const saved = await api(`/resources/${enc(workspace.resource.id)}/document`, 'PUT', {
      version: workspace.doc.version, content: value,
    });
    workspace.doc.version = saved.version;
    workspace.lastSaved = snapshot(value);
    workspace.doc.canEdit = true;
    workspace.doc.canConvert = false;
    workspace.doc.compatibilityIssue = '';
    if (current !== workspace) return;
    workspace.editor.setEditable(true);
    document.querySelectorAll('[data-document-title]').forEach(input => { input.readOnly = false; });
    syncTitle(workspace.resource.title);
    document.querySelector('.document-compatibility')?.remove();
    status('已转换并保存到云端');
  } catch (error) {
    if (current !== workspace) return;
    status(error.status === 409 ? '云端已有更新，请刷新后再转换' : `转换未完成，原文件未修改：${error.message}`, true);
    if (button) button.disabled = false;
  }
}
function formulaDialog(node = null, pos = null) {
  if (!current?.doc.canEdit) return;
  const dialog = document.querySelector('#structuredFormulaDialog');
  current.formula = node ? { pos, type: node.type.name } : null;
  dialog.querySelector('textarea').value = node?.attrs.latex || '';
  dialog.querySelector('[name="mathKind"][value="block"]').checked = node?.type.name === 'blockMath';
  dialog.querySelector('[name="mathKind"][value="inline"]').checked = node?.type.name !== 'blockMath';
  dialog.showModal(); dialog.querySelector('textarea').focus();
}
function saveFormula() {
  const dialog = document.querySelector('#structuredFormulaDialog');
  const latex = dialog.querySelector('textarea').value.trim();
  if (!latex || latex.length > 5000) { status('公式内容无效', true); return; }
  const block = dialog.querySelector('[name="mathKind"]:checked').value === 'block';
  const editor = current.editor;
  if (current.formula) {
    const { pos, type } = current.formula;
    if (type === (block ? 'blockMath' : 'inlineMath')) editor.commands[block ? 'updateBlockMath' : 'updateInlineMath']({ pos, latex });
    else editor.chain().focus().deleteRange({ from: pos, to: pos + editor.state.doc.nodeAt(pos).nodeSize }).insertContentAt(pos, { type: block ? 'blockMath' : 'inlineMath', attrs: { latex } }).run();
  } else editor.chain().focus().insertContent({ type: block ? 'blockMath' : 'inlineMath', attrs: { latex } }).run();
  dialog.close(); current.formula = null;
}
function linkDialog() {
  if (!current?.doc.canEdit) return;
  const dialog = document.querySelector('#structuredLinkDialog');
  current.linkSelection = { from: current.editor.state.selection.from, to: current.editor.state.selection.to };
  dialog.querySelector('input').value = current.editor.getAttributes('link').href || '';
  dialog.showModal(); dialog.querySelector('input').focus();
}
function saveLink() {
  const dialog = document.querySelector('#structuredLinkDialog');
  let href = dialog.querySelector('input').value.trim();
  if (href && !/^[a-z][a-z0-9+.-]*:/i.test(href)) href = `https://${href}`;
  if (href && !/^(https?:\/\/[^\s]+|mailto:[^\s]+)$/i.test(href)) { status('请输入有效的网页或邮箱链接', true); return; }
  const editor = current.editor;
  const selection = current.linkSelection;
  const chain = editor.chain().focus();
  if (selection) chain.setTextSelection(selection);
  if (href) chain.setLink({ href }).run();
  else chain.unsetLink().run();
  dialog.close(); current.linkSelection = null;
}
function hideMenus() {
  for (const id of ['structuredSelectionTools', 'structuredSlashMenu']) {
    const node = document.getElementById(id); if (node) node.hidden = true;
  }
}
function positionMenu(node, rect) {
  node.style.left = `${Math.max(12, Math.min(innerWidth - 240, rect?.left || 12))}px`;
  node.style.top = `${Math.max(12, Math.min(innerHeight - 250, (rect?.bottom || 20) + 8))}px`;
}
function updateMenus() {
  if (!current?.doc.canEdit || !current.editor?.isFocused) { hideMenus(); return; }
  const { from, to, $from } = current.editor.state.selection;
  const tools = document.querySelector('#structuredSelectionTools');
  const slash = document.querySelector('#structuredSlashMenu');
  const selection = window.getSelection();
  const range = selection?.rangeCount ? selection.getRangeAt(0) : null;
  const rect = typeof range?.getBoundingClientRect === 'function' ? range.getBoundingClientRect() : null;
  tools.hidden = from === to;
  if (!tools.hidden) positionMenu(tools, rect);
  const before = $from.parent.textBetween(0, $from.parentOffset, undefined, '\ufffc');
  const match = from === to ? before.match(/(?:^|\s)\/([\w]*)$/) : null;
  slash.hidden = !match;
  if (match) {
    current.slashRange = { from: from - match[0].trimStart().length, to: from };
    const query = match[1].toLowerCase();
    slash.querySelectorAll('[data-editor-command]').forEach(button => {
      button.hidden = Boolean(query && !button.dataset.alias.includes(query));
    });
    positionMenu(slash, rect);
  }
}
function runCommand(command, slash = false) {
  const editor = current?.editor; if (!editor) return;
  if (slash && current.slashRange) editor.chain().focus().deleteRange(current.slashRange).run();
  hideMenus();
  if (command === 'formula') { formulaDialog(); return; }
  if (command === 'link') { linkDialog(); return; }
  if (command === 'table') { editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run(); return; }
  const chain = editor.chain().focus();
  const actions = {
    paragraph: () => chain.setParagraph(), h1: () => chain.toggleHeading({ level: 1 }),
    h2: () => chain.toggleHeading({ level: 2 }), bold: () => chain.toggleBold(),
    bullet: () => chain.toggleBulletList(), number: () => chain.toggleOrderedList(),
    quote: () => chain.toggleBlockquote(),
  };
  actions[command]?.().run();
}
function mount() {
  if (current?.editor) {
    if (current.dirty && !current.saving && !current.conflict) save(current).catch(() => {});
    if (current.titleDirty && !current.titleSaving && !current.conflict) saveTitle(current, current.pendingTitle).catch(() => {});
    current.editor.destroy(); clearTimeout(current.timer); clearTimeout(current.titleTimer);
  }
  current = null;
  const host = document.querySelector('#structuredEditor');
  if (!host || !pending) return;
  const { resource, doc } = pending; pending = null;
  document.querySelector('#structuredSelectionTools').insertAdjacentHTML('beforeend', '<button type="button" data-editor-command="link" title="链接 Ctrl+K">链接</button>');
  document.querySelector('#structuredSlashMenu').insertAdjacentHTML('beforeend', '<button type="button" data-editor-command="table" data-alias="table bg"><span>▦</span>表格</button>');
  host.closest('.structured-workspace').insertAdjacentHTML('beforeend', '<dialog id="structuredLinkDialog" class="document-link-dialog"><strong>链接</strong><input type="url" aria-label="链接地址" placeholder="https://example.com"><div><button type="button" class="btn" data-structured-action="cancel-link">取消</button><button type="button" class="btn primary" data-structured-action="save-link">完成</button></div></dialog>');
  const workspace = current = { resource, doc, dirty: false, titleDirty: false, saving: false, titleSaving: false, conflict: false, lastSaved: null, initializing: true };
  let editor;
  editor = new Editor({
    element: host, editable: doc.canEdit,
    editorProps: {
      handleKeyDown(_view, event) {
        const menu = document.querySelector('#structuredSlashMenu');
        if (event.key === 'Enter' && menu && !menu.hidden) {
          const first = menu.querySelector('[data-editor-command]:not([hidden])');
          if (first) { event.preventDefault(); runCommand(first.dataset.editorCommand, true); return true; }
        }
        if (event.key === 'Escape' && menu && !menu.hidden) { hideMenus(); return true; }
        return false;
      },
    },
    extensions: createDocumentExtensions({ editable: doc.canEdit, onMathClick: (node, pos) => formulaDialog(node, pos) }),
    content: typeof doc.content === 'string' ? doc.content : doc.content,
    contentType: typeof doc.content === 'string' ? 'markdown' : 'json',
    onUpdate: () => { if (current !== workspace || workspace.initializing || !workspace.editor || repairBlockIds(editor)) return; outlineRows(); queueSave(); updateMenus(); },
    onSelectionUpdate: () => { if (current === workspace) updateMenus(); },
    onFocus: updateMenus, onBlur: hideMenus,
  });
  workspace.editor = editor;
  if (doc.canEdit) repairBlockIds(editor);
  workspace.lastSaved = snapshot(structured(doc.content) ? doc.content : { schemaVersion: 2, ...editor.getJSON() });
  workspace.recovery = doc.canEdit ? readDraft(resource.id) : null;
  if (workspace.recovery && snapshot(workspace.recovery.content) === snapshot(content()) && workspace.recovery.title === resource.title) {
    try { localStorage.removeItem(workspace.recovery.key); } catch {}
    workspace.recovery = null;
  }
  if (workspace.recovery) {
    document.querySelector('#structuredRecovery').hidden = false;
    document.querySelector('#structuredRecovery span').textContent = workspace.recovery.version === doc.version ? '发现尚未同步的本地记录' : '发现基于旧版本的本地记录';
  }
  workspace.initializing = false;
  outlineRows();
  host.addEventListener('keyup', updateMenus);
  host.addEventListener('mouseup', updateMenus);
}
function acceptSlashCommand(event) {
  const menu = document.querySelector('#structuredSlashMenu');
  if (!current || !menu || menu.hidden || event.target?.closest?.('input,textarea,button')) return;
  if (event.key === 'Escape') { event.preventDefault(); event.stopImmediatePropagation(); hideMenus(); return; }
  if (event.key !== 'Enter' && event.key !== 'Return' && event.inputType !== 'insertParagraph') return;
  const first = menu.querySelector('[data-editor-command]:not([hidden])');
  if (!first) return;
  event.preventDefault(); event.stopImmediatePropagation();
  runCommand(first.dataset.editorCommand, true);
}
document.addEventListener('keydown', acceptSlashCommand, true);
document.addEventListener('beforeinput', acceptSlashCommand, true);
function downloadDraft() {
  const record = current?.recovery || { title: title(), content: content() };
  const blob = new Blob([JSON.stringify({ kind: 'document', title: record.title, content: record.content }, null, 2)], { type: 'application/json;charset=utf-8' });
  const url = URL.createObjectURL(blob), anchor = document.createElement('a');
  anchor.href = url; anchor.download = `${(record.title || '文档').replace(/[\\/:*?"<>|]/g, '_')}-本地记录.json`; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 3000);
}
function page(resource, doc) {
  pending = { resource, doc };
  document.body.classList.add('document-mode');
  document.title = `${resource.title} · 研途`;
  const editable = doc.canEdit;
  const paperTitle = editable && resource.title === untitledTitle ? '' : resource.title;
  const owner = doc.owner || resource.owner || '未知作者';
  const back = state.driveReturn || 'resources';
  const compatibilityNotice = doc.compatibilityIssue
    ? `<div class="document-recovery document-compatibility"><strong>检查旧内容</strong><span>${esc(doc.compatibilityIssue)}${doc.canConvert ? '。原文件仍可下载查看。' : '。'}</span>${doc.canConvert ? '<button type="button" class="btn" data-structured-action="convert-document">确认转换并编辑</button>' : ''}</div>` : '';
  return `<div class="document-workspace structured-workspace"><header class="document-topbar"><div class="document-top-left"><a class="document-home" href="#${esc(back)}" aria-label="返回我的云盘">${icon('back')}</a><span class="document-mark">${icon('file')}</span><div class="document-heading"><div class="document-title-top"><input id="documentTitle" data-document-title value="${esc(resource.title)}" maxlength="200" aria-label="文档标题" ${editable ? '' : 'readonly'}></div><span id="documentSaveStatus">${editable ? '已保存到云端' : '只读文档'}</span></div></div><div class="document-top-actions">${editable ? btn('分享', 'cloud-shares', resource.id, 'primary') : ''}<button type="button" class="btn document-more" data-action="cloud-resource-more" data-id="${esc(resource.id)}" aria-haspopup="menu">···</button></div></header><div class="document-toolbar"><span>文档</span><a href="/api/v1/resources/${enc(resource.id)}/download">下载原文件</a></div><div class="document-recovery" id="structuredRecovery" hidden><strong>本地记录</strong><span></span><button type="button" class="btn" data-structured-action="view-draft">查看</button><button type="button" class="btn" data-structured-action="restore-draft">恢复</button><button type="button" class="btn" data-structured-action="discard-draft">舍弃</button></div><div class="document-conflict" id="documentConflict" hidden><strong>云端已有更新</strong><span>自动保存已暂停，本地记录已保留。</span><button type="button" class="btn" data-structured-action="download-draft">下载本地记录</button><button type="button" class="btn" data-structured-action="reload-cloud">重新读取云端</button></div>${compatibilityNotice}<div class="document-body"><aside class="document-outline" id="documentOutlinePanel"><div class="document-outline-header"><h2>目录</h2><button type="button" class="document-outline-collapse" data-structured-action="outline" aria-label="收起目录">«</button></div><ul id="documentOutline"></ul></aside><main class="document-stage"><div class="document-paper"><h1 class="document-paper-title"><input data-document-title value="${esc(paperTitle)}" placeholder="${editable ? '请输入标题' : ''}" maxlength="200" aria-label="文档标题" ${editable ? '' : 'readonly'}></h1><div class="document-paper-byline"><span class="document-author-avatar" aria-hidden="true">${esc(Array.from(owner)[0] || '?')}</span><span class="document-author-name">${esc(owner)}</span><span class="document-byline-divider"></span><time id="documentModifiedAt" datetime="${esc(doc.modifiedAt || '')}">${workspaceModifiedLabel(doc.modifiedAt)}</time></div><div id="structuredEditor" class="document-rendered" aria-label="文档正文"></div></div></main></div><div id="structuredSelectionTools" class="document-selection-tools" hidden><button type="button" data-editor-command="bold" title="加粗 Ctrl+B"><b>B</b></button><button type="button" data-editor-command="h1">H1</button><button type="button" data-editor-command="h2">H2</button></div><div id="structuredSlashMenu" class="document-slash-menu" hidden><div class="document-slash-heading">常用</div><button type="button" data-editor-command="formula" data-alias="gs eq formula"><span>𝑓𝑥</span>公式</button><button type="button" data-editor-command="h1" data-alias="h1 title"><span>H₁</span>一级标题</button><button type="button" data-editor-command="h2" data-alias="h2 subtitle"><span>H₂</span>二级标题</button><button type="button" data-editor-command="bullet" data-alias="list bullet"><span>≡</span>项目符号</button><button type="button" data-editor-command="quote" data-alias="quote"><span>❝</span>引用</button></div><dialog id="structuredFormulaDialog" class="document-equation-dialog"><div class="document-equation-head"><strong>公式</strong><button type="button" data-structured-action="cancel-formula" aria-label="关闭">×</button></div><div class="document-equation-kinds"><label><input type="radio" name="mathKind" value="inline" checked>行内公式</label><label><input type="radio" name="mathKind" value="block">独立公式</label></div><textarea aria-label="LaTeX 公式源码" placeholder="例如 \\frac{a}{b}+x^2" spellcheck="false"></textarea><div class="document-equation-actions"><button type="button" class="btn" data-structured-action="cancel-formula">取消</button><button type="button" class="btn primary" data-structured-action="save-formula">完成</button></div></dialog><dialog id="structuredDraftDialog" class="document-local-dialog"><div class="document-local-head"><strong>本地记录</strong><button type="button" data-structured-action="close-draft" aria-label="关闭">×</button></div><textarea readonly aria-label="本地记录内容"></textarea><div class="document-local-actions"><button type="button" class="btn" data-structured-action="download-draft">下载记录</button></div></dialog></div>`;
}

document.addEventListener('mousedown', event => {
  if (event.target.closest('#structuredSelectionTools button,#structuredSlashMenu button')) event.preventDefault();
});
document.addEventListener('input', event => {
  if (!current || !event.target.matches?.('.structured-workspace [data-document-title]')) return;
  syncTitle(event.target.value, event.target); queueTitle();
});
document.addEventListener('click', event => {
  if (!current || !document.querySelector('.structured-workspace')) return;
  const command = event.target.closest('[data-editor-command]');
  if (command) { runCommand(command.dataset.editorCommand, Boolean(command.closest('#structuredSlashMenu'))); return; }
  const link = event.target.closest('[data-outline-pos]');
  if (link) {
    const pos = Number(link.dataset.outlinePos);
    current.editor.commands.setTextSelection(pos + 1);
    current.editor.view.domAtPos(pos).node.parentElement?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    return;
  }
  if (event.target.closest('[data-outline-top]')) { scrollTo({ top: 0, behavior: 'smooth' }); return; }
  const action = event.target.closest('[data-structured-action]')?.dataset.structuredAction;
  if (action === 'convert-document') { convertDocument(); return; }
  if (action === 'outline') {
    const panel = document.querySelector('#documentOutlinePanel'); panel.classList.toggle('is-collapsed');
    event.target.textContent = panel.classList.contains('is-collapsed') ? '»' : '«'; return;
  }
  if (action === 'cancel-formula') document.querySelector('#structuredFormulaDialog').close();
  if (action === 'save-formula') saveFormula();
  if (action === 'cancel-link') document.querySelector('#structuredLinkDialog').close();
  if (action === 'save-link') saveLink();
  if (action === 'view-draft') {
    const dialog = document.querySelector('#structuredDraftDialog');
    dialog.querySelector('textarea').value = typeof current.recovery?.content === 'string' ? current.recovery.content : JSON.stringify(current.recovery?.content, null, 2);
    dialog.showModal();
  }
  if (action === 'close-draft') document.querySelector('#structuredDraftDialog').close();
  if (action === 'download-draft') downloadDraft();
  if (action === 'discard-draft') {
    try { localStorage.removeItem(current.recovery.key); } catch {}
    current.recovery = null; document.querySelector('#structuredRecovery').hidden = true;
  }
  if (action === 'restore-draft') {
    const record = current.recovery;
    if (!record) return;
    const stale = record.version !== current.doc.version || record.baseTitle !== current.resource.title;
    setContent(record.content); syncTitle(record.title); current.restoredKey = record.key;
    current.recovery = null; document.querySelector('#structuredRecovery').hidden = true;
    current.dirty = snapshot(content()) !== current.lastSaved; current.titleDirty = record.title !== current.resource.title;
    persistDraft();
    if (stale) conflict('本地记录基于旧版本');
    else { if (current.dirty) queueSave(); if (current.titleDirty) queueTitle(); }
  }
  if (action === 'reload-cloud' && confirm('重新读取云端会丢弃当前页面尚未保存的修改。请先下载本地记录。')) {
    current.dirty = false; location.reload();
  }
});
document.addEventListener('keydown', event => {
  if (!current || !document.querySelector('.structured-workspace')) return;
  if (event.target.matches?.('[data-document-title]')) {
    if (event.key === 'Enter') { event.preventDefault(); saveTitle().catch(() => {}); event.target.blur(); }
    if (event.key === 'Escape') { event.preventDefault(); syncTitle(current.resource.title); current.titleDirty = false; event.target.blur(); }
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
    event.preventDefault(); saveTitle().catch(() => {}); save().catch(() => {});
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k' && event.target.closest?.('#structuredEditor')) {
    event.preventDefault(); linkDialog();
  }
});
document.addEventListener('focusout', event => {
  if (current && event.target.matches?.('.structured-workspace [data-document-title]')) saveTitle().catch(() => {});
});
window.addEventListener('beforeunload', event => {
  if (current?.dirty || current?.titleDirty) { event.preventDefault(); event.returnValue = ''; }
});
window.addEventListener('hashchange', () => {
  if (current?.titleDirty) saveTitle(current, current.pendingTitle).catch(() => {});
  if (current?.dirty) save().catch(() => {});
});
window.structuredDocumentPage = page;
window.mountStructuredDocument = mount;
window.structuredDocumentEditor = () => current?.editor || null;
