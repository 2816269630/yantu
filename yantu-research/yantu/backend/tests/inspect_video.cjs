const { chromium } = require('playwright');
const path = require('node:path');

(async () => {
  const browser = await chromium.launch({headless:true, executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
  const page = await browser.newPage({viewport:{width:1440,height:900}});
  const videoUrl = 'http://127.0.0.1:8765/issue-video.mp4';
  await page.setContent(`<style>body{margin:0;background:#111;display:grid;place-items:center;height:100vh}video{max-width:100%;max-height:100%}</style><video controls src="${videoUrl}"></video>`);
  const video=page.locator('video');
  await video.evaluate(el => new Promise((resolve,reject)=>{if(el.readyState>=1)return resolve();const timer=setTimeout(()=>reject(new Error(`video timeout ${el.error?.message||''}`)),10000);el.onloadedmetadata=()=>{clearTimeout(timer);resolve()};el.onerror=()=>reject(new Error(`video load failed ${el.error?.message||''}`));}));
  const duration=await video.evaluate(el=>el.duration);
  const points=[0,.2,.4,.6,.8,1].map(v=>Math.max(0,Math.min(duration-.05,duration*v)));
  for(let i=0;i<points.length;i++){
    await video.evaluate((el,t)=>new Promise(resolve=>{el.onseeked=resolve;el.currentTime=t;}),points[i]);
    await page.screenshot({path:`artifacts/video-${i}.png`});
  }
  console.log(JSON.stringify({duration,points}));
  await browser.close();
})().catch(error=>{console.error(error);process.exitCode=1;});
