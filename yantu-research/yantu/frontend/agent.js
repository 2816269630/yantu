/* Research Agent: settings own connections; the workspace owns conversations. */
'use strict';
const agentState = { connections: [], history: [], conversation: null, currentId: '', attachments: [],
  selection: '', mode: 'agent', busy: false, reply: null, error: '', editing: '', codex: null, poll: null, abort: null };
const agentPreferenceKey = () => 'yantu:agent:model:' + state.user?.id;
const agentChoice = (connectionId, model) => JSON.stringify([connectionId, model]);
function agentModels() {
  return [{ id: '', name: '本地', models: ['local-search'] }, ...agentState.connections];
}
function agentEnsureSelection() {
  const choices = agentModels().flatMap(connection => connection.models.map(model => agentChoice(connection.id, model)));
  if (!agentState.selection) {
    try { agentState.selection = localStorage.getItem(agentPreferenceKey()) || ''; } catch (_) {}
  }
  if (!choices.includes(agentState.selection)) agentState.selection = choices.find(choice => JSON.parse(choice)[0]) || choices[0];
}
function agentMarkdown(value) {
  return String(value || '').split(/(```[^\n]*\n[\s\S]*?```)/g).map(part => {
    if (part.startsWith('```')) return `<pre class="agent-code"><code>${esc(part.replace(/^```[^\n]*\n/, '').replace(/```$/, ''))}</code></pre>`;
    return esc(part).replace(/^#{1,4} (.+)$/gm, '<strong class="agent-text-heading">$1</strong>')
      .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>').replace(/`([^`\n]+)`/g, '<code>$1</code>');
  }).join('');
}
function agentActionCard(action) {
  return `<article class="agent-action-card"><div class="between"><strong>${icon('file')}${esc(action.title)}</strong>${tag(({pending:'待你确认',approved:'已保存',rejected:'已取消'})[action.status] || '处理中', action.status === 'approved' ? 'green' : 'orange')}</div><details><summary>查看笔记草稿</summary><div class="agent-draft">${agentMarkdown(action.content)}</div></details>${action.status === 'pending' ? `<div class="section-actions">${btn('保存到我的云盘','agent-approve',action.id,'primary sm')}${btn('取消','agent-reject',action.id,'sm')}</div>` : action.resourceId ? link('打开已保存的笔记 '+icon('right'),'resource/'+enc(action.resourceId),'textbutton') : ''}</article>`;
}
function agentMessage(message, actions = []) {
  const assistant = message.role === 'assistant';
  const details = message.details || {};
  return `<article class="agent-message ${assistant ? 'agent-assistant' : 'agent-user'}"><div class="agent-message-label">${assistant ? icon('spark')+'研途' : '你'}${assistant && message.model ? `<span>${esc(message.model === 'local-search' ? '本地资料检索' : message.model)}</span>` : ''}</div>
    ${details.tools?.length ? `<details class="agent-tool-trace" ${message.status === 'running' ? 'open' : ''}><summary>${details.tools.some(tool => tool.status === 'running') ? '正在使用工具…' : `已使用 ${details.tools.length} 次工具`}</summary>${details.tools.map(tool => `<div><span class="agent-tool-dot ${esc(tool.status)}"></span><span>${esc(tool.label)}</span><small>${esc(tool.summary || '进行中')}</small></div>`).join('')}</details>` : ''}
    <div class="agent-message-text">${assistant ? agentMarkdown(message.content) : esc(message.content)}${message.status === 'running' && !message.content ? '<span class="agent-thinking">正在思考<span>…</span></span>' : ''}</div>
    ${details.error ? `<p class="agent-run-error" role="alert">${esc(details.error)}</p>` : ''}${message.status === 'stopped' ? '<p class="small">已停止生成</p>' : ''}
    ${details.sources?.length ? `<div class="agent-citations">${details.sources.map((source, index) => `<a href="#resource/${enc(source.resourceId)}" title="${esc(source.excerpt)}">${source.sourceIndex || index+1} · ${esc(source.title)}</a>`).join('')}</div>` : ''}
    ${actions.filter(action => details.actionIds?.includes(action.id)).map(agentActionCard).join('')}
    ${assistant && message.content && message.status !== 'running' ? btn('复制','agent-copy',message.id,'textbutton agent-copy') : ''}</article>`;
}
function agentEmpty() {
  return `<div class="agent-welcome"><div class="agent-welcome-icon">${icon('spark')}</div><h1>接下来，一起解决什么问题？</h1><p>读资料、理思路，把下一步研究变得更清楚。</p><div class="agent-starters">${[
    ['folder','梳理研究资料','检索我的资料，梳理核心研究问题和重要结论，并标注来源。'],
    ['tasks','规划下一步实验','查看我的科研任务，帮我整理优先级和下一步实验计划。'],
    ['calendar','准备下一次组会','查看近期组会和我的任务，整理一份会前准备清单。'],
    ['file','起草科研笔记','根据我的资料起草一份带引用的科研笔记，先给我确认草稿。']
  ].map(([glyph, label, prompt]) => `<button data-action="agent-starter" data-id="${esc(prompt)}">${icon(glyph)}<span>${label}</span>${icon('arrow')}</button>`).join('')}</div></div>`;
}
function agentHistory() {
  return `<div class="agent-history-head"><strong>对话</strong></div><div class="agent-history-list">${agentState.history.length ? agentState.history.map(item => `<button class="${item.id === agentState.currentId ? 'active' : ''}" data-action="agent-open" data-id="${esc(item.id)}"><span>${esc(item.title)}</span></button>`).join('') : '<p class="small">你的研究对话会保存在这里。</p>'}</div><div class="agent-history-foot">${icon('lock')}仅自己可见</div>`;
}
pages.assistant = async () => {
  const [connections, history] = await Promise.all([api('/agent/connections'), api('/agent/conversations')]);
  agentState.connections = connections.items;
  agentState.history = history.items;
  agentEnsureSelection();
  if (agentState.currentId && !agentState.busy) agentState.conversation = await api('/agent/conversations/' + enc(agentState.currentId));
  const messages = agentState.conversation?.messages || [];
  const actions = agentState.conversation?.actions || [];
  requestAnimationFrame(() => { const transcript = $('#agentTranscript'); if (transcript) transcript.scrollTop = transcript.scrollHeight; });
  return `<div class="agent-workbench"><aside class="agent-history" aria-label="历史会话">${agentHistory()}</aside><section class="agent-thread"><header class="agent-thread-head"><div>${icon('spark')}<strong>科研助手</strong><span class="agent-mode-badge">${agentState.mode === 'agent' ? 'Agent' : '对话'}</span></div><div class="section-actions">${btn('历史','agent-history','','textbutton agent-mobile-history')}${btn(icon('plus')+'新对话','agent-new','','textbutton')}${agentState.currentId ? btn('归档','agent-archive',agentState.currentId,'textbutton') : ''}</div></header>
    <div class="agent-transcript" id="agentTranscript" role="log" aria-label="科研对话">${messages.length ? messages.map(message => agentMessage(message, actions)).join('') : agentEmpty()}<div id="agentLive">${agentState.busy && agentState.reply ? agentMessage(agentState.reply, agentState.reply.actions || []) : ''}</div></div>
    <div class="agent-compose-area"><div class="agent-attachments">${agentState.attachments.map(item => `<span>${icon('file')}${esc(item.title)}<button data-action="agent-detach" data-id="${esc(item.id)}" aria-label="移除参考资料 ${esc(item.title)}">×</button></span>`).join('')}</div>
    <form class="agent-composer" data-form="agent-chat"><label class="sr-only" for="agentPrompt">向科研助手提问</label><textarea id="agentPrompt" name="message" placeholder="描述目标，或让 Agent 帮你处理一个研究任务…" rows="3" required maxlength="8000" ${agentState.busy ? 'disabled' : ''}></textarea><div class="agent-compose-toolbar"><div class="agent-compose-options"><label><span class="sr-only">工作模式</span><select id="agentMode" ${agentState.busy ? 'disabled' : ''}><option value="agent" ${agentState.mode === 'agent' ? 'selected' : ''}>✧ Agent</option><option value="chat" ${agentState.mode === 'chat' ? 'selected' : ''}>对话</option></select></label><label class="agent-model-picker"><span class="sr-only">切换模型</span><select id="agentModel" ${agentState.busy ? 'disabled' : ''}>${agentModels().map(connection => `<optgroup label="${esc(connection.name)}">${connection.models.map(model => `<option value="${esc(agentChoice(connection.id,model))}" ${agentState.selection === agentChoice(connection.id,model) ? 'selected' : ''}>${esc(model === 'local-search' ? '本地资料检索' : model)}</option>`).join('')}</optgroup>`).join('')}</select></label></div><div class="agent-compose-buttons"><button class="iconbtn" type="button" data-action="agent-attach" aria-label="添加参考资料" ${agentState.busy ? 'disabled' : ''}>${icon('plus')}</button>${agentState.busy ? '<button class="btn agent-stop" type="button" data-action="agent-stop">停止</button>' : `<button class="btn primary agent-send" type="submit" aria-label="发送消息">${icon('arrow')}</button>`}</div></div><div class="form-error" role="alert" hidden></div></form>
    <p class="agent-compose-note">${agentState.mode === 'agent' ? 'Agent 可检索资料和查看任务；笔记草稿由你确认后保存。' : '对话模式不自动调用工具。'} <span>Enter 发送 · Shift + Enter 换行</span></p></div></section></div>`;
};

const agentOriginalSettings = settingsContent;
settingsContent = async tab => tab === 'models' ? agentSettings() : agentOriginalSettings(tab);
async function agentSettings() {
  const value = await api('/agent/connections');
  agentState.connections = value.items;
  const editing = agentState.connections.find(item => item.id === agentState.editing && item.provider !== 'codex');
  if (value.codexAvailable && !agentState.codex) {
    try { agentState.codex = await api('/agent/codex/status'); } catch (error) { agentState.codex = { error: error.message }; }
  }
  const account = agentState.codex || {};
  const pending = account.login && !account.login.completed;
  return `<div class="agent-settings-intro"><h2>模型与连接</h2><p>连接你使用的模型服务，再到科研助手中自由切换。连接仅供当前账号使用。</p></div><div class="agent-settings-grid"><div class="stack"><section class="panel padded"><div class="between"><div><h3>API 模型连接</h3><p class="small">支持 OpenAI、兼容接口与本地 Ollama。</p></div>${btn(icon('plus')+'添加','agent-connection-new','','sm')}</div><div class="agent-connections">${agentState.connections.filter(item => item.provider !== 'codex').map(item => `<article><div><strong>${esc(item.name)}</strong><p>${esc(({openai:'OpenAI Responses',compatible:'Chat Completions',ollama:'Ollama'})[item.provider])} · ${item.models.length} 个模型${item.hasKey ? ' · 密钥已保存' : ''}</p></div><div class="section-actions">${btn('编辑','agent-connection-edit',item.id,'textbutton')}${btn('读取模型','agent-models',item.id,'textbutton')}${btn('移除','agent-connection-remove',item.id,'textbutton danger-text')}</div></article>`).join('') || '<div class="agent-settings-empty">还没有 API 连接。填写右侧表单，或在下方使用 ChatGPT 登录 Codex。</div>'}</div></section>
    <section class="panel padded"><div class="between"><div><h3>Codex · ChatGPT 账号</h3><p class="small">使用官方 Codex 连接，无需填写 API Key。</p></div>${tag(account.connected ? '已连接' : '未连接',account.connected ? 'green' : '')}</div>${account.connected ? `<div class="agent-account"><strong>${esc(account.email || 'ChatGPT 账号')}</strong><span>${esc(account.plan || '')}</span></div><div class="section-actions mt16">${btn('刷新模型','agent-codex-models')}${btn('退出 Codex','agent-codex-logout','','danger-text')}</div>` : `<p class="section-note mt16">点击登录后，打开官方验证页面并输入设备代码完成授权。研途不会接触你的账号密码。</p><div class="section-actions mt16"><button class="btn primary" data-action="agent-codex-login" ${value.codexAvailable ? '' : 'disabled'}>使用 ChatGPT 登录 Codex</button>${btn('检查连接状态','agent-codex-check')}</div>${!value.codexAvailable ? '<p class="helptext mt16">当前服务缺少 Codex 组件，请按部署说明更新镜像。</p>' : ''}`}
    ${pending ? `<div class="agent-device-login"><strong>完成账号授权</strong><p>设备代码：<code>${esc(account.login.userCode)}</code></p><a class="btn" href="${esc(safeUrl(account.login.verificationUrl))}" target="_blank" rel="noopener noreferrer">打开官方验证页面 ↗</a><p class="small">完成后自动检查连接，也可点击“检查连接状态”。</p></div>` : ''}${account.error || account.login?.error ? `<p class="agent-run-error" role="alert">${esc(account.error || account.login.error)}</p>` : ''}<p class="helptext mt16">模型和可用额度以你的账号为准。此连接与研途登录账号独立。</p></section></div>
    <section class="panel padded agent-connection-editor"><h3 class="mb16">${editing ? '编辑连接' : '添加 API 连接'}</h3><form data-form="agent-connection" class="form-stack"><input type="hidden" name="id" value="${esc(editing?.id || '')}">${field('连接名称','name',editing?.name || '',{required:true,max:100,placeholder:'例如：我的研究模型'})}${selectField('接口协议','provider',[{id:'openai',name:'OpenAI · Responses API'},{id:'compatible',name:'兼容接口 · Chat Completions'},{id:'ollama',name:'本地 Ollama'}],editing?.provider || 'openai')}${field('API 地址','baseUrl',editing?.baseUrl || 'https://api.openai.com/v1',{required:true,max:500,placeholder:'https://api.openai.com/v1'})}${field('API Key','apiKey','',{type:'password',max:4096,autocomplete:'off',placeholder:editing?.hasKey ? '已保存，留空保持原密钥' : '输入密钥；本地模型可留空',help:'密钥在本地服务端加密保存，不会返回浏览器。'})}${field('模型名称','models',(editing?.models || []).join('\n'),{textarea:true,rows:4,placeholder:'每行一个模型 ID，也可保存后读取模型列表',help:'填写服务商实际提供的模型 ID。'})}<div class="form-error" role="alert" hidden></div><button class="btn primary" type="submit">保存连接</button></form><p class="helptext mt16">本地 Ollama 地址通常为 http://host.docker.internal:11434。兼容接口一般使用以 /v1 结尾的 API 地址。</p></section></div>`;
}

function agentScheduleLive() {
  if (agentState.paintPending) return;
  agentState.paintPending = true;
  requestAnimationFrame(() => {
    agentState.paintPending = false;
    const live = $('#agentLive'), transcript = $('#agentTranscript');
    if (!live || !agentState.reply) return;
    const follow = transcript.scrollHeight - transcript.scrollTop - transcript.clientHeight < 140;
    live.innerHTML = agentMessage(agentState.reply, agentState.reply.actions || []);
    if (follow) transcript.scrollTop = transcript.scrollHeight;
  });
}
async function agentSend(formElement) {
  if (agentState.busy) return;
  const prompt = formElement.elements.message.value.trim();
  if (!prompt) return;
  if (!agentState.currentId) {
    const created = await api('/agent/conversations','POST',{});
    agentState.currentId = created.id;
    agentState.conversation = { ...created, messages: [], actions: [] };
  }
  const ident = agentState.currentId, ownerId = state.user.id;
  const [connectionId, model] = JSON.parse(agentState.selection);
  agentState.busy = true;
  agentState.reply = { id:'live', role:'assistant', content:'', model, status:'running', details:{ tools:[], sources:[], actionIds:[] }, actions:[] };
  agentState.conversation.messages.push({role:'user',content:prompt,status:'complete'});
  agentState.abort = new AbortController();
  await renderPage();
  let reachedServer = false;
  try {
    const response = await fetch(`/api/v1/agent/conversations/${enc(ident)}/messages`, {method:'POST', credentials:'same-origin',
      headers:{'Content-Type':'application/json'}, signal:agentState.abort.signal,
      body:JSON.stringify({message:prompt,connectionId,model,mode:agentState.mode,resourceIds:agentState.attachments.map(item=>item.id)})});
    if (!response.ok) {const error=await response.json();throw new Error(error.message || '消息发送失败');}
    reachedServer = true;
    const reader = response.body.getReader(), decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const {value,done} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value,{stream:true});
      let boundary;
      while ((boundary=buffer.indexOf('\n\n'))>=0) {
        const block=buffer.slice(0,boundary);buffer=buffer.slice(boundary+2);
        const event=block.match(/^event: (.+)$/m)?.[1], raw=block.match(/^data: (.+)$/m)?.[1];
        if (!raw || !agentState.reply) continue;
        const data=JSON.parse(raw), reply=agentState.reply;
        if(event==='delta')reply.content+=data.text;
        if(event==='tool'){const index=reply.details.tools.findIndex(item=>item.id===data.id);if(index<0)reply.details.tools.push(data);else reply.details.tools[index]=data;}
        if(event==='action'){reply.actions.push(data);reply.details.actionIds.push(data.id);}
        if(event==='error'){reply.details.error=data.message;reply.status='error';}
        if(event==='done')reply.status=data.status;
        agentScheduleLive();
      }
    }
  } catch(error) {
    if(state.user?.id===ownerId) {
      if(agentState.reply){agentState.reply.status='error';agentState.reply.details.error=error.name==='AbortError'?'已停止生成':error.message;}
      toast(error.message || '连接已中断',true);
    }
  } finally {
    if(state.user?.id===ownerId) {
      const failedPrompt = !reachedServer ? prompt : '';
      agentState.busy=false;agentState.abort=null;
      try {agentState.conversation=await api('/agent/conversations/'+enc(ident));} catch(_) {}
      if(state.page==='assistant') {await renderPage();if(failedPrompt && $('#agentPrompt'))$('#agentPrompt').value=failedPrompt;}
      agentState.reply=null;
    }
  }
}

function agentStartPolling() {
  clearInterval(agentState.poll);
  agentState.poll=setInterval(async()=>{
    if(state.page!=='settings'||state.settingsTab!=='models'||!state.user){clearInterval(agentState.poll);return;}
    try {agentState.codex=await api('/agent/codex/status');if(agentState.codex.connected||agentState.codex.login?.completed){clearInterval(agentState.poll);await renderPage();}}catch(error){clearInterval(agentState.poll);toast(error.message,true);}
  },5000);
}
window.agentAction = async (action,id,source) => {
  if(action==='logout') {clearInterval(agentState.poll);if(agentState.busy&&agentState.currentId)await api(`/agent/conversations/${enc(agentState.currentId)}/stop`,'POST',{}).catch(()=>{});agentState.abort?.abort();Object.assign(agentState,{connections:[],history:[],conversation:null,currentId:'',attachments:[],selection:'',busy:false,reply:null,codex:null});return false;}
  if(!action.startsWith('agent-'))return false;
  if(action==='agent-history')openModal('历史对话',`<div class="agent-mobile-history-list">${agentHistory()}</div>`);
  if(['agent-new','agent-open','agent-archive'].includes(action)&&agentState.busy)throw new Error('请等待当前生成完成，或先点击停止。');
  if(['agent-new','agent-open'].includes(action)&&$('#modal').open)closeModal();
  if(action==='agent-new'){agentState.currentId='';agentState.conversation=null;agentState.attachments=[];await renderPage();}
  if(action==='agent-open'){agentState.currentId=id;agentState.attachments=[];await renderPage();}
  if(action==='agent-archive'){await api('/agent/conversations/'+enc(id),'PATCH',{archived:true});agentState.currentId='';agentState.conversation=null;await renderPage();}
  if(action==='agent-starter'){if($('#agentPrompt')){$('#agentPrompt').value=id;$('#agentPrompt').focus();}}
  if(action==='agent-stop'){source.disabled=true;source.textContent='正在停止…';await api(`/agent/conversations/${enc(agentState.currentId)}/stop`,'POST',{});}
  if(action==='agent-detach'){agentState.attachments=agentState.attachments.filter(item=>item.id!==id);source.closest('.agent-attachments>span')?.remove();}
  if(action==='agent-attach')await modalLoad('添加参考资料',async()=>{const items=await allDriveFiles('all');agentState.availableSources=items;return `<form data-form="agent-sources"><p class="small mb16">选择本次可用资料；不选时，Agent 按权限检索你的资料库。</p><div class="agent-source-picker">${items.map(item=>`<label class="source-check"><input type="checkbox" name="agentSource" value="${esc(item.id)}" ${agentState.attachments.some(selected=>selected.id===item.id)?'checked':''}><span>${esc(item.title)}</span></label>`).join('')||'<p class="small">暂无可选资料，请先在云盘上传。</p>'}</div><div class="form-error" role="alert" hidden></div><div class="form-actions">${btn('取消','close')}<button class="btn primary" type="submit">使用选中资料</button></div></form>`;});
  if(action==='agent-copy'){const message=agentState.conversation?.messages.find(item=>item.id===id);if(message){await navigator.clipboard.writeText(message.content);toast('已复制回答');}}
  if(action==='agent-approve'||action==='agent-reject'){source.disabled=true;try{await api('/agent/actions/'+enc(id),'POST',{approve:action==='agent-approve'});await renderPage();}finally{source.disabled=false;}}
  if(action==='agent-connection-new'){agentState.editing='';await renderPage();$('#f-name')?.focus();}
  if(action==='agent-connection-edit'){agentState.editing=id;await renderPage();$('#f-name')?.focus();}
  if(action==='agent-connection-remove'){await api('/agent/connections/'+enc(id),'DELETE');if(agentState.editing===id)agentState.editing='';await renderPage();toast('已移除连接');}
  if(action==='agent-models'){source.disabled=true;try{const value=await api('/agent/connections/'+enc(id)+'/models','POST',{});toast(`连接成功，已读取 ${value.models.length} 个模型`);await renderPage();}finally{source.disabled=false;}}
  if(action==='agent-codex-login'){source.disabled=true;try{const login=await api('/agent/codex/login','POST',{});agentState.codex={connected:false,login};await renderPage();agentStartPolling();}finally{source.disabled=false;}}
  if(action==='agent-codex-check'){agentState.codex=await api('/agent/codex/status');await renderPage();if(agentState.codex.login&&!agentState.codex.login.completed)agentStartPolling();}
  if(action==='agent-codex-models'){agentState.codex=await api('/agent/codex/status');if(agentState.codex.connection)await api('/agent/connections/'+enc(agentState.codex.connection.id)+'/models','POST',{});await renderPage();toast('已刷新可用模型');}
  if(action==='agent-codex-logout'){clearInterval(agentState.poll);await api('/agent/codex/logout','POST',{});agentState.codex={connected:false};await renderPage();}
  return true;
};
window.agentSubmit = async formElement => {
  const type=formElement.dataset.form;
  if(type==='agent-chat'){await agentSend(formElement);return true;}
  if(type==='agent-sources'){const ids=$$('input[name=agentSource]:checked',formElement).map(input=>input.value);if(ids.length>10)throw new Error('最多选择 10 份参考资料');const draft=$('#agentPrompt')?.value||'';agentState.attachments=agentState.availableSources.filter(item=>ids.includes(item.id));closeModal();await renderPage();if($('#agentPrompt'))$('#agentPrompt').value=draft;return true;}
  if(type==='agent-connection'){const data=values(formElement);data.models=data.models.split(/[\n,，]/).map(value=>value.trim()).filter(Boolean);const saved=await api('/agent/connections','POST',data);agentState.editing=saved.id;await renderPage();toast('连接已保存，可读取模型或到科研助手中使用');return true;}
  return false;
};
document.addEventListener('change',event=>{
  if(event.target.id==='agentModel'){agentState.selection=event.target.value;try{localStorage.setItem(agentPreferenceKey(),agentState.selection);}catch(_) {}}
  if(event.target.id==='agentMode'){agentState.mode=event.target.value;const badge=$('.agent-mode-badge');if(badge)badge.textContent=agentState.mode==='agent'?'Agent':'对话';const note=$('.agent-compose-note');if(note)note.innerHTML=(agentState.mode==='agent'?'Agent 可检索资料和查看任务；笔记草稿由你确认后保存。':'对话模式不自动调用工具。')+' <span>Enter 发送 · Shift + Enter 换行</span>';}
  if(event.target.matches('form[data-form="agent-connection"] [name="provider"]')){const input=$('[name="baseUrl"]',event.target.form);if(['https://api.openai.com/v1','http://host.docker.internal:11434',''].includes(input.value))input.value=event.target.value==='ollama'?'http://host.docker.internal:11434':'https://api.openai.com/v1';}
});
document.addEventListener('keydown',event=>{if(event.target.id==='agentPrompt'&&event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();if(!agentState.busy)event.target.form.requestSubmit();}});
if(state.user && state.page==='assistant')renderPage();
