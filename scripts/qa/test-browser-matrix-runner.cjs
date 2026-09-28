#!/usr/bin/env node
// Exit-status regression using real Chromium and disposable local HTTP fixtures.
// node scripts/qa/test-browser-matrix-runner.cjs
// Optional QA_RUNNER_TEST_OUTPUT retains reports/screenshots at an explicit path.
const assert=require('node:assert/strict');
const http=require('node:http');
const fs=require('node:fs');
const path=require('node:path');
const os=require('node:os');
const crypto=require('node:crypto');
const {spawn}=require('node:child_process');
const repo=path.resolve(__dirname,'../..');
const runner=path.join(__dirname,'run-browser-matrix.cjs');
const retainOutput=Boolean(process.env.QA_RUNNER_TEST_OUTPUT);
const out=retainOutput?path.resolve(process.env.QA_RUNNER_TEST_OUTPUT):fs.mkdtempSync(path.join(os.tmpdir(),'agroamigo-qa-runner-'));
fs.mkdirSync(out,{recursive:true});
const requests=[];
const server=http.createServer((req,res)=>{
 requests.push(req.url);
 if(req.url==='/api/health'||req.url==='/release.json'){
  res.setHeader('Content-Type','application/json');res.end(JSON.stringify(req.url==='/api/health'?{status:'local-fixture'}:{id:'local-fixture-release'}));return;
 }
 res.setHeader('Content-Type','text/html');
 res.end('<!doctype html><html><body><div class="mobile-nav">Local fixture ready</div>'+(req.url==='/crash'?'<script>throw Error("Intentional fixture page error")</script>':'')+'</body></html>');
});
const fixture=(name,condition='true',ready='!!document.querySelector(".mobile-nav")',route='/')=>({name,route,ready,steps:[{checks:[{id:'fixture',condition,expected:'Local controlled check'}]}]});
const child=(env,manifest)=>new Promise((resolve,reject)=>{
 const p=spawn(process.execPath,[runner,manifest],{cwd:repo,env:{...process.env,...env},stdio:['ignore','pipe','pipe']});let output='';
 p.stdout.on('data',x=>output+=x);p.stderr.on('data',x=>output+=x);p.on('error',reject);
 const timer=setTimeout(()=>{p.kill('SIGTERM');reject(Error('Local QA fixture timed out'))},30000);
 p.on('close',code=>{clearTimeout(timer);resolve({code,output})});
});
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const base='http://127.0.0.1:'+server.address().port;
 const runs=[
  {name:'positive',cases:[fixture('positive','document.querySelector(".mobile-nav").innerText==="Local fixture ready"')],code:0},
  {name:'negative',cases:[fixture('negative','false')],code:1},
  {name:'blocked',cases:[fixture('blocked','true','false')],code:1},
  {name:'empty-selection',cases:[fixture('present')],filter:'^absent$',code:1},
  {name:'no-assertions',cases:[{name:'no-assertions',route:'/',steps:[{checks:[]}]}],code:1},
  {name:'page-error',cases:[fixture('page-error','true',undefined,'/crash')],code:1},
  {name:'negative-continues-to-positive',cases:[fixture('negative','false'),fixture('positive','true')],code:1},
 ];
 const results=[];
 for(const run of runs){
  const manifest=path.join(out,run.name+'.json');fs.writeFileSync(manifest,JSON.stringify(run.cases));
  const dest=path.join(out,run.name);const before=requests.length;
  const result=await child({QA_BASE_URL:base,QA_OUTPUT:dest,QA_READY_TIMEOUT:'75',QA_CASES:run.filter||''},manifest);
  fs.writeFileSync(path.join(dest,'process.log'),result.output);
  const report=JSON.parse(fs.readFileSync(path.join(dest,'report.json'),'utf8'));
  assert.equal(result.code,run.code,run.name);
  if(run.name==='positive')assert.equal(report.summary.failed,0);
  if(run.name==='negative')assert.equal(report.summary.failed,1);
  if(run.name==='blocked')assert.equal(report.summary.blocked,1);
  if(run.name==='empty-selection'){assert.match(report.fatal,/No QA scenarios selected/);assert.equal(requests.length,before)}
  if(run.name==='no-assertions')assert.equal(report.cases[0].outcome,'assertion_failed');
  if(run.name==='page-error')assert.equal(report.cases[0].page_errors.length,1);
  if(run.name==='negative-continues-to-positive')assert.deepEqual(report.cases.map(c=>c.outcome),['assertion_failed','assertions_passed']);
  results.push({fixture:run.name,expected_exit:run.code,actual_exit:result.code,passed:true,summary:report.summary||null,requests:requests.slice(before),browser:report.browser_version||null});
  console.log(run.name,'exit',result.code,'PASS');
 }
 const proof={success:true,runner_sha256:crypto.createHash('sha256').update(fs.readFileSync(runner)).digest('hex'),real_chromium:true,network:'Isolated127.0.0.1 HTTP fixtures only; no production requests',results};
 fs.writeFileSync(path.join(out,'proof.json'),JSON.stringify(proof,null,2)+'\n');
})().catch(e=>{console.error(e);console.error('Failure evidence:',out);process.exitCode=1}).finally(()=>{server.close();if(!retainOutput&&!process.exitCode)fs.rmSync(out,{recursive:true,force:true})});
