const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {JSDOM}=require('jsdom');
const root=path.resolve(__dirname,'../..');
const until=async fn=>{const start=Date.now();while(!fn()){if(Date.now()-start>4000)throw new Error('云盘页面未完成预期操作');await new Promise(r=>setTimeout(r,10));}};
async function main(){
  const dom=new JSDOM(fs.readFileSync(path.join(root,'frontend/index.html'),'utf8'),{url:'http://localhost/#drive',runScripts:'outside-only',pretendToBeVisual:true});
  const w=dom.window,doc=w.document,requests=[];
  w.scrollTo=()=>{};
  w.HTMLDialogElement.prototype.showModal=function(){assert.equal(this.open,false,'不能重复打开已打开的弹窗');this.open=true;};
  w.HTMLDialogElement.prototype.close=function(){this.open=false;};
  const user={id:'me',displayName:'本人',email:'me@example.test'};
  const project={id:'project',name:'课题一',role:'student',membershipStatus:'member',memberCount:2};
  const folder={id:'folder1',name:'文献目录',parentId:null,ownerId:user.id,kind:'folder'};
  const own={id:'own',title:'实验记录.txt',fileName:'实验记录.txt',ownerId:'me',owner:'本人',ownerName:'本人',canEdit:true,type:'note',visibility:'private',previewType:'text/plain',size:10,version:1,folderId:null};
  const shared={...own,id:'shared',title:'共享记录.txt',ownerId:'other',owner:'其他成员',canEdit:false};
  let shareActive=false,reference=false;
  w.fetch=async(url,options={})=>{
    const u=new URL(url,'http://localhost'),p=u.pathname.replace('/api/v1',''),method=options.method||'GET';
    const body=options.body&&typeof options.body==='string'?JSON.parse(options.body):{};
    requests.push({p,method,body});let result,status=200;
    if(p==='/me')result=user;
    else if(p==='/lab/projects')result={items:[project],total:1};
    else if(p==='/lab/next-meeting')result=null;
    else if(p==='/me/drive/folders/tree')result={items:[folder],files:[{...own,kind:'file'},{...shared,kind:'file'}]};
    else if(p==='/me/drive/children'){const current=u.searchParams.get('folderId');result={items:current?[{...own,kind:'file'}].filter(x=>x.folderId===current):[folder,...own.folderId?[]:[{...own,kind:'file'}],{...shared,kind:'file'}],total:current?Number(own.folderId===current):own.folderId?2:3,breadcrumbs:[{id:null,name:'我的文件'},...current?[folder]:[]]};}
    else if(p==='/me/drive/search')result={items:[{...own,kind:'file'}],total:1};
    else if(p==='/me/drive/available-resources')result={items:[own],total:1};
    else if(p==='/me/drive/folders'&&method==='POST')result={id:'created',name:body.name};
    else if(p==='/resources/own'&&method==='PATCH'){Object.assign(own,body);result=own;}
    else if(p==='/resources/own')result=own;
    else if(p==='/resources/own/versions')result={items:[{id:'v1',version:1,note:'首次上传',size:10}]};
    else if(p==='/resources/own/shares')result={direct:{items:shareActive?[{id:'share',userId:'other',displayName:'其他成员',teamId:'project',active:true}]:[]},legacyAccess:{active:false}};
    else if(p==='/resources/own/shares/other'){shareActive=method==='PUT';result={};}
    else if(p==='/teams/project/members')result={items:[{...user,name:user.displayName},{id:'other',displayName:'其他成员',name:'其他成员'}],total:2};
    else if(p==='/lab/projects/project/materials/references'){reference=true;result={...own,referenceId:'ref'};status=201;}
    else if(p==='/lab/projects/project/materials')result={items:reference?[own]:[],total:Number(reference)};
    else if(p==='/lab/projects/project/meetings')result={items:[],total:0};
    else if(p==='/lab/history')result={items:[],total:0};
    else status=404;
    return {ok:status>=200&&status<300,status,json:async()=>status<300?{data:result}:{message:'未预期的请求 '+p}};
  };
  const click=s=>{const e=doc.querySelector(s);assert.ok(e,s);e.click();};
  const submit=f=>f.dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));
  try{
    w.eval(['lab-app.js','lab-cloud.js','cloud-upload.js','lab-drive.js'].map(n=>fs.readFileSync(path.join(root,'frontend',n),'utf8')).join('\n'));
    await until(()=>doc.querySelector('.drive-layout'));
    assert.equal(doc.querySelectorAll('#nav .navitem').length,6);
    assert.equal(doc.querySelector('#nav .active').textContent,'我的资料');
    assert.ok(doc.querySelector('.drive-tree')&&doc.querySelector('.drive-inspector'));
    assert.ok(doc.querySelector('a[href="#materials"]')&&doc.querySelector('a[href="#drive"]'));
    click('[data-action=cloud-menu][data-id=shared]');
    await until(()=>doc.querySelector('#driveContextMenu'));
    assert.equal(doc.querySelector('#driveContextMenu [data-menu-action=cloud-rename]'),null,'共享文件不可重命名');
    assert.equal(doc.querySelector('#driveContextMenu [data-menu-action=cloud-shares]'),null,'共享文件不可再次共享');
    click('[data-action=cloud-menu][data-id=own]');
    await until(()=>doc.querySelector('[data-menu-action=cloud-rename]'));
    click('[data-menu-action=cloud-rename]');
    await until(()=>doc.querySelector('[data-form=cloud-rename]'));
    const rename=doc.querySelector('[data-form=cloud-rename]');rename.elements.name.value='实验参数100%.txt';submit(rename);
    await until(()=>own.title==='实验参数100%.txt'&&!doc.querySelector('#modal').open);
    await until(()=>doc.querySelector('.drive-layout'));
    assert.ok(requests.some(r=>r.p==='/resources/own'&&r.method==='PATCH'));
    click('[data-action=cloud-menu][data-id=own]');await until(()=>doc.querySelector('[data-menu-action=cloud-move]'));click('[data-menu-action=cloud-move]');
    await until(()=>doc.querySelector('[data-form=cloud-move]'));
    const move=doc.querySelector('[data-form=cloud-move]');move.elements.folderId.value=folder.id;submit(move);
    await until(()=>own.folderId===folder.id&&!doc.querySelector('#modal').open);
    await until(()=>doc.querySelector('.drive-layout'));
    click('[data-action=cloud-search-toggle]');
    const search=doc.querySelector('[data-form=cloud-search]');search.elements.q.value='100%';submit(search);
    await until(()=>doc.querySelector('.drive-query')?.textContent.includes('100%'));
    assert.ok(requests.some(r=>r.p==='/me/drive/search'));
    click('[data-action=cloud-menu][data-id=own]');await until(()=>doc.querySelector('[data-menu-action=cloud-shares]'));click('[data-menu-action=cloud-shares]');
    await until(()=>doc.querySelector('[data-form=cloud-share]'));
    submit(doc.querySelector('[data-form=cloud-share]'));
    await until(()=>shareActive&&doc.querySelector('[data-action=cloud-revoke]'));
    assert.equal(doc.querySelector('#modal').open,true);
    click('[data-action=cloud-revoke]');
    await until(()=>doc.querySelector('[data-form=cloud-revoke]'));
    submit(doc.querySelector('[data-form=cloud-revoke]'));
    await until(()=>!shareActive&&doc.querySelector('[data-form=cloud-share]'));
    click('#closeModal');
    w.location.hash='#materials';
    await until(()=>doc.querySelector('[data-action=reference-project-file]'));
    click('[data-action=reference-project-file]');
    await until(()=>doc.querySelector('[data-form=lab-reference]'));
    assert.match(doc.querySelector('#modalBody').textContent,/当前 2 位成员/);
    submit(doc.querySelector('[data-form=lab-reference]'));
    await until(()=>reference&&!doc.querySelector('#modal').open);
    assert.ok(requests.some(r=>r.p.endsWith('/materials/references')&&r.body.grantReadAccess===true));
    assert.equal(doc.querySelector('#nav .active').textContent,'我的资料');
    console.log('Cloud UI acceptance passed: original three-column layout, six-module integration, shared-file restrictions, rename, move, percent search, share/revoke and explicit project reference.');
  }finally{w.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
