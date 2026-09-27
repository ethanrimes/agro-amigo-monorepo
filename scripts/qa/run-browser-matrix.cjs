#!/usr/bin/env node
// Real-browser transport for portable DOM/data QA manifests. No app/database writes.
const { chromium } = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const base = process.env.QA_BASE_URL || 'https://agroamigo-demo-9a04.azurewebsites.net';
const out = path.resolve(process.env.QA_OUTPUT || `artifacts/app-data-audit-2026-09-27/web/${new Date().toISOString().replace(/[:.]/g,'-')}`);
const files = process.argv.slice(2).length ? process.argv.slice(2) : ['apps/web/tests/qa/core-matrix-cases.json'];
const cases = files.flatMap(f=>JSON.parse(fs.readFileSync(f,'utf8')).map(c=>({...c,manifest:f})));
const selected = process.env.QA_CASES ? cases.filter(c=>new RegExp(process.env.QA_CASES,'i').test(c.name)) : cases;
fs.mkdirSync(out,{recursive:true});
const report={platform:'WEB',transport:'Playwright desktop Chromium (not native)',base,started_at:new Date().toISOString(),viewport:{width:Number(process.env.QA_WIDTH||1440),height:1000},cases:[],files,manifest_sha256:Object.fromEntries(files.map(f=>[f,crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex')]))};
const persist=()=>fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2));
(async()=>{
 const browser=await chromium.launch({headless:true}); report.browser_version=browser.version();
 const context=await browser.newContext({viewport:report.viewport,locale:'es-CO',timezoneId:'America/Bogota',acceptDownloads:true});
 const page=await context.newPage();
 try { const r=await context.request.get(`${base}/api/health`,{timeout:20000}); report.health={status:r.status(),body:await r.json()}; }catch(e){report.health={error:String(e)}}
 try{const r=await context.request.get(`${base}/release.json`,{timeout:15000});report.release=await r.json()}catch(e){report.release={error:String(e)}}
 const captured=[];page.on('response',r=>{if(r.url().includes('/api/'))captured.push({url:r.url(),status:r.status(),at:new Date().toISOString()})});
 let active=null;page.on('pageerror',e=>{active?.page_errors.push(String(e))});
 for(const c of selected){
  active={name:c.name,route:c.route,manifest:c.manifest,started_at:new Date().toISOString(),checks:[],page_errors:[],steps:[],requests:[]}; report.cases.push(active);let start=captured.length;
  const slug=c.name.replace(/[^a-z0-9-]+/gi,'-').toLowerCase();
  try{
   const res=await page.goto(base+c.route,{waitUntil:'domcontentloaded',timeout:60000});active.http_status=res?.status();
   await page.waitForFunction(c.ready||'document.readyState==="complete"',null,{timeout:Number(process.env.QA_READY_TIMEOUT||55000),polling:250});
   for(let i=0;i<c.steps.length;i++){
    const s=c.steps[i],step={index:i,checks:[]};active.steps.push(step);
    if(s.action)await page.evaluate(`(async()=>{${s.action}\n})()`);
    if(s.ready)await page.waitForFunction(s.ready,null,{timeout:55000,polling:250});
    for(const ch of s.checks||[]){
     let result={id:ch.id,expected:ch.expected,condition:ch.condition};
     try{result.passed=await page.evaluate(ch.condition)===true;result.observed=ch.observed?await page.evaluate(ch.observed):null}catch(e){result.passed=false;result.error=String(e)}
     step.checks.push(result);active.checks.push(result);
    }
    const shot=`${slug}-step${i+1}.png`;await page.screenshot({path:path.join(out,shot),fullPage:false});step.screenshot=shot;persist();
   }
   active.final_url=page.url();active.visible_text=(await page.locator('body').innerText()).slice(0,45000);
   active.storage=await page.evaluate(()=>Object.fromEntries(Object.entries(localStorage).filter(([k])=>k.startsWith('agroamigo-'))));
   active.outcome=active.checks.every(x=>x.passed)?'assertions_passed':'assertion_failed';
  }catch(e){active.outcome='blocked_or_failed';active.error=String(e);active.final_url=page.url();active.visible_text=(await page.locator('body').innerText().catch(()=>'' )).slice(0,45000);await page.screenshot({path:path.join(out,slug+'-error.png'),fullPage:false}).catch(()=>{});}
  active.requests=captured.slice(start);active.finished_at=new Date().toISOString();persist();
  console.log(`${active.outcome}: ${c.name} (${active.checks.filter(x=>x.passed).length}/${active.checks.length} assertions)`);
 }
 // Disposable browser profile is discarded; no user browser state was touched.
 await context.close();await browser.close();report.finished_at=new Date().toISOString();report.summary={scenarios:report.cases.length,assertions:report.cases.reduce((a,c)=>a+c.checks.length,0),failed:report.cases.flatMap(c=>c.checks).filter(c=>!c.passed).length,blocked:report.cases.filter(c=>c.outcome==='blocked_or_failed').length};persist();console.log(JSON.stringify({out,summary:report.summary}));
})().catch(e=>{report.fatal=String(e);persist();console.error(e);process.exitCode=1});
