const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({headless:true, executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  const page = await browser.newPage({viewport:{width:1440,height:900}});
  const errors=[];
  page.on('pageerror', error => errors.push(String(error)));
  page.on('response', response => {if(response.status() >= 400 && !response.url().endsWith('/favicon.ico')) errors.push(`${response.status()} ${response.url()}`);});
  await page.goto('http://localhost:8088',{waitUntil:'networkidle'});
  await page.waitForTimeout(300);
  const visible = await page.locator('body').innerText();
  await page.screenshot({path:'artifacts/setup-desktop.png',fullPage:true});
  console.log(JSON.stringify({title:await page.title(),visible,errors},null,2));
  await browser.close();
  if(errors.length || !visible.includes('开启你的科研空间')) process.exitCode=1;
})().catch(error=>{console.error(error);process.exitCode=1;});
