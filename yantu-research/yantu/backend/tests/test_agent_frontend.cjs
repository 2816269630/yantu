const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');
const root = path.resolve(__dirname, '../..');
const until = async predicate => { const start=Date.now();while(!predicate()){if(Date.now()-start>4000)throw new Error('Agent UI did not update');await new Promise(resolve=>setTimeout(resolve,10));} };

async function main() {
  const dom=new JSDOM(fs.readFileSync(path.join(root,'frontend/index.html'),'utf8'),{url:'http://localhost/#assistant',runScripts:'outside-only',pretendToBeVisual:true});
  const w=dom.window;w.scrollTo=()=>{};w.TextDecoder=TextDecoder;w.AbortController=AbortController;
  w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};w.HTMLDialogElement.prototype.close=function(){this.open=false;};
  let created=false, complete=false, approved=false, codexLogin=false;
  const calls=[], connection={id:'connection-1',name:'研究模型',provider:'compatible',baseUrl:'https://example.com/v1',hasKey:true,models:['model-a','model-b']};
  const action={id:'action-1',title:'实验笔记',content:'<script>unsafe</script>\n实验计划',status:'pending'};
  const stored={id:'conversation-1',title:'实验计划',messages:[],actions:[]};
  w.fetch=async(url,options={})=>{
    calls.push({url,options});let data;
    if(url==='/api/v1/system/status')data={initialized:true,registrationOpen:true,version:'0.4.0'};
    else if(url==='/api/v1/me')data={id:'test-user',displayName:'研究者',email:'test@example.com'};
    else if(url==='/api/v1/me/teams'||url==='/api/v1/me/notifications')data={items:[]};
    else if(url==='/api/v1/agent/connections'&&options.method==='POST'){Object.assign(connection,{name:JSON.parse(options.body).name});data=connection;}
    else if(url==='/api/v1/agent/connections')data={items:[connection],codexAvailable:true};
    else if(url==='/api/v1/agent/conversations'&&options.method==='POST'){created=true;data={id:stored.id,title:'新对话'};}
    else if(url==='/api/v1/agent/conversations')data={items:created?[{id:stored.id,title:stored.title}]:[]};
    else if(url==='/api/v1/agent/conversations/conversation-1')data={...stored,actions:complete?[{...action,status:approved?'approved':'pending',resourceId:approved?'file-1':null}]:[]};
    else if(url.endsWith('/messages')){
      const payload=JSON.parse(options.body);
      stored.messages=[{id:'u1',role:'user',content:payload.message,status:'complete'},
        {id:'a1',role:'assistant',content:'**已起草** <img src=x onerror=alert(1)>',model:payload.model,status:'complete',details:{tools:[{id:'t1',name:'draft_note',label:'起草笔记',status:'complete'}],actionIds:[action.id]}}];
      const encoded=new TextEncoder().encode([
        ['started',{messageId:'a1'}],['tool',{id:'t1',label:'起草笔记',status:'running'}],
        ['delta',{text:'**已起草** <img src=x onerror=alert(1)>'}],['action',action],['done',{status:'complete'}]
      ].map(([event,value])=>`event: ${event}\ndata: ${JSON.stringify(value)}\n\n`).join(''));
      let offset=0;
      return {ok:true,body:{getReader:()=>({read:async()=>{if(offset>=encoded.length){complete=true;return{done:true};}const value=encoded.slice(offset,offset+7);offset+=7;return{value,done:false};}})}};
    }
    else if(url==='/api/v1/agent/actions/action-1'){approved=true;data={...action,status:'approved',resourceId:'file-1'};}
    else if(url==='/api/v1/agent/codex/login'){codexLogin=true;data={verificationUrl:'https://auth.openai.com/codex/device',userCode:'ABCD-1234',completed:false};}
    else if(url==='/api/v1/agent/codex/status')data={connected:false};
    else throw new Error('Unexpected request: '+url);
    return {ok:true,status:200,json:async()=>({data})};
  };
  w.eval(fs.readFileSync(path.join(root,'frontend/app.js'),'utf8')+'\n'+fs.readFileSync(path.join(root,'frontend/agent.js'),'utf8')+'\nwindow.agentTest={state,agentState,navigate};');
  try {
    await until(()=>w.document.querySelector('.agent-workbench'));
    assert.equal(w.document.querySelector('[name="apiKey"]'),null,'Connection settings stay outside the assistant');
    const model=w.document.querySelector('#agentModel');model.value=JSON.stringify(['connection-1','model-b']);model.dispatchEvent(new w.Event('change',{bubbles:true}));
    w.document.querySelector('[data-action="agent-starter"]').click();
    assert.ok(w.document.querySelector('#agentPrompt').value.includes('检索我的资料'));
    w.document.querySelector('form[data-form="agent-chat"]').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));
    await until(()=>complete&&!w.agentTest.agentState.busy&&w.document.querySelector('.agent-action-card'));
    const sent=JSON.parse(calls.find(call=>call.url.endsWith('/messages')).options.body);
    assert.equal(sent.model,'model-b');assert.equal(sent.mode,'agent');
    assert.equal(approved,false,'Drafts must not save automatically');
    assert.equal(w.document.querySelector('.agent-message-text img'),null,'Assistant HTML is escaped');
    assert.equal(w.document.querySelector('.agent-draft script'),null,'Draft HTML is escaped');
    w.document.querySelector('[data-action="agent-approve"]').click();
    await until(()=>w.document.querySelector('.agent-action-card a[href="#resource/file-1"]'));
    const mode=w.document.querySelector('#agentMode');mode.value='chat';mode.dispatchEvent(new w.Event('change',{bubbles:true}));
    assert.match(w.document.querySelector('.agent-compose-note').textContent,/不自动调用工具/);
    w.agentTest.navigate('settings');await until(()=>w.document.querySelector('[data-action="settings-tab"][data-id="models"]'));
    w.document.querySelector('[data-action="settings-tab"][data-id="models"]').click();
    await until(()=>w.document.querySelector('[name="apiKey"]'));
    assert.equal(w.document.querySelector('.agent-workbench'),null);
    w.document.querySelector('[name="name"]').value='我的模型';w.document.querySelector('[name="apiKey"]').value='never-store-this-key';
    w.document.querySelector('form[data-form="agent-connection"]').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));
    await until(()=>connection.name==='我的模型'&&w.document.querySelector('[name="apiKey"]').value==='');
    for(let i=0;i<w.localStorage.length;i++)assert.ok(!w.localStorage.getItem(w.localStorage.key(i)).includes('never-store-this-key'));
    w.document.querySelector('[data-action="agent-codex-login"]').click();
    await until(()=>w.document.querySelector('.agent-device-login'));
    assert.equal(codexLogin,true);assert.match(w.document.querySelector('.agent-device-login').textContent,/ABCD-1234/);
    assert.equal(w.document.querySelector('.agent-device-login a').href,'https://auth.openai.com/codex/device');
    console.log('Agent UI passed: model switching, split UTF-8 streaming, tool cards, draft approval, safe rendering, private settings and Codex login.');
  } finally {clearInterval(w.agentTest?.agentState.poll);dom.window.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
