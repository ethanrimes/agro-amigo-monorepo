/* Portable data assertions in the actual Android app WebView, not emulation.
 * node apps/android/validate-matrix.cjs path/to/manifest.json [more manifests]
 * Requires ANDROID_TEST_SERIAL and ANDROID_TEST_ARTIFACTS. See QA matrix doc.
 */
const { _android } = require('@playwright/test');
const fs = require('node:fs');
const { execFileSync } = require('node:child_process');
const path = require('node:path');
const {createHash} = require('node:crypto');
const origin = 'https://agroamigo-demo-9a04.azurewebsites.net';
const out = process.env.ANDROID_TEST_ARTIFACTS;
const serial = process.env.ANDROID_TEST_SERIAL;
if (!out || !serial?.startsWith('emulator-') || process.argv.length < 3)
  throw Error('Explicit emulator, artifact directory and manifest are required');
const selection = process.env.ANDROID_TEST_CASES ? new RegExp(process.env.ANDROID_TEST_CASES) : null;
const manifests = process.argv.slice(2).map(p=>({path:p,sha256:createHash('sha256').update(fs.readFileSync(p)).digest('hex')}));
const cases = manifests.flatMap(p=>JSON.parse(fs.readFileSync(p.path,'utf8'))).filter(c=>!selection||selection.test(c.name));
if(!cases.length)throw Error('No selected native matrix scenarios');
fs.mkdirSync(out,{recursive:true});
const privateBackup = path.join(out,'.restore-settings.private.json');
if (fs.existsSync(privateBackup)) throw Error('Restore the pending private settings snapshot first');
const adb = `${process.env.ANDROID_HOME || '/Users/ethan/Library/Android/sdk'}/platform-tools/adb`;
let device, page, original;
const report = {platform:'ANDROID',started_at:new Date().toISOString(),serial,manifests,selection:selection?.source||null,results:[],errors:[],api_requests:[],settings_restored:false};
const write = ()=>fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2));
(async()=>{
  device=(await _android.devices()).find(d=>d.serial()===serial);
  if(!device)throw Error('Dedicated emulator is not connected');
  await device.shell('am start -n co.agroamigo.demo/.MainActivity');
  page=await(await device.webView({pkg:'co.agroamigo.demo'})).page();
  page.setDefaultTimeout(90000);page.setDefaultNavigationTimeout(90000);
  let active='setup';
  page.on('pageerror',e=>report.errors.push({scenario:active,message:e.message}));
  page.on('response',r=>{if(r.url().startsWith(origin+'/api/'))report.api_requests.push({scenario:active,path:r.url().slice(origin.length),status:r.status()})});
  await page.goto(origin,{waitUntil:'domcontentloaded'});
  await page.waitForSelector('.mobile-nav');
  report.user_agent=await page.evaluate(()=>navigator.userAgent);
  if(!report.user_agent.includes('AgroAmigoAndroid/1.0'))throw Error('Expected installed Android app WebView');
  original=await page.evaluate(()=>Object.fromEntries(Object.entries(localStorage)));
  fs.writeFileSync(privateBackup,JSON.stringify(original),{mode:0o600});
  report.release=await page.evaluate(async()=>{const r=await fetch('/release.json',{cache:'no-store'});if(!r.ok)throw Error(r.status);return r.json()});
  if(process.env.ANDROID_TEST_RELEASE && report.release.id!==process.env.ANDROID_TEST_RELEASE)throw Error('Unexpected deployed release');
  for(const scenario of cases){
    active=scenario.name;
    const result={name:active,route:scenario.route,checks:[]};report.results.push(result);
    try{
      await page.evaluate(old=>{localStorage.clear();for(const[k,v]of Object.entries(old))localStorage.setItem(k,v);const p=JSON.parse(localStorage.getItem('agroamigo-preferences-v2')||'{}');p.region='';localStorage.setItem('agroamigo-preferences-v2',JSON.stringify(p));},original);
      await page.goto(origin+scenario.route,{waitUntil:'domcontentloaded'});
      await page.waitForFunction(scenario.ready||'document.querySelector(".mobile-nav")');
      for(const step of scenario.steps){
        if(step.action)await page.evaluate(`(async()=>{${step.action}\n})()`);
        if(step.ready)await page.waitForFunction(step.ready);
        for(const check of step.checks||[]){
          const outcome={id:check.id,expected:check.expected};
          try{outcome.passed=await page.evaluate(`Boolean(${check.condition})`);outcome.observed=await page.evaluate(check.observed||check.condition)}
          catch(e){outcome.passed=false;outcome.error=e.message}
          result.checks.push(outcome);console.log('MATRIX_CHECK',JSON.stringify({scenario:active,...outcome}));
        }
      }
      result.passed=result.checks.length>0&&result.checks.every(c=>c.passed);
    }catch(e){result.passed=false;result.error=e.message;result.body=await page.locator('body').innerText().catch(()=>null)}
    result.screenshot=`android-matrix-${active.replace(/[^a-zA-Z0-9_-]/g,'-')}.png`;
    fs.writeFileSync(path.join(out,result.screenshot),execFileSync(adb,['-s',serial,'exec-out','screencap','-p'],{maxBuffer:16*1024*1024}));
    write();console.log('MATRIX_SCENARIO',JSON.stringify(result));
  }
  report.release_after=await page.evaluate(async()=>{const r=await fetch('/release.json',{cache:'no-store'});return r.json()});
  if(report.release_after.id!==report.release.id)throw Error('Release changed during validation');
  if(report.results.some(r=>!r.passed)||report.errors.length)process.exitCode=1;
})().catch(e=>{report.error=e.message;process.exitCode=1;console.error(e)}).finally(async()=>{
  try{
    if(page&&original){
      await page.evaluate(old=>{localStorage.clear();for(const[k,v]of Object.entries(old))localStorage.setItem(k,v);},original);
      const after=await page.evaluate(()=>Object.fromEntries(Object.entries(localStorage)));
      const stable=o=>JSON.stringify(Object.entries(o).sort(([a],[b])=>a.localeCompare(b)));
      if(stable(after)!==stable(original))throw Error('Settings restore mismatch');
      report.settings_restored=true;fs.unlinkSync(privateBackup);
    }
  }catch(e){report.restore_error=e.message;process.exitCode=1}
  report.finished_at=new Date().toISOString();write();await device?.close();
});
