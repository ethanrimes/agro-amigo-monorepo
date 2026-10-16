const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript');
const code=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/lib/server/bug-reports.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const context={exports:{},URL,process:{env:{BUG_REPORT_RATE_SECRET:'private-test-secret-with-at-least-32-chars'}},require:name=>name==='server-only'?{}:name==='node:crypto'?require(name):{database:()=>({query:async(sql,values)=>{context.submission={sql,values};return{rows:[{id:'fixture-id'}]}}})}};
vm.runInNewContext(code,context);
const {validateBugReport,reportPagePath,submitBugReport}=context.exports;
test('valid report keeps filters, redacts coordinates and hashes rate address',async()=>{
 const report=validateBugReport({message:'  El precio de la papa no coincide  ',consent:true,page_path:'/product/papa?market=Bogota&lat=4.5&lon=-74.2&presentation=Bulto&token=private#anchor',reply_email:'reply@example.invalid'});
 assert.equal(report.page_path,'/product/papa?market=Bogota&presentation=Bulto');
 assert.equal(await submitBugReport(report,'192.0.2.5'),'fixture-id');
 assert.match(context.submission.values[4],/^[a-f0-9]{64}$/);
 assert.ok(!JSON.stringify(context.submission).includes('192.0.2.5'));
 assert.ok(!JSON.stringify(context.submission).includes('private#anchor'));
});
test('consent, bounded message, honeypot, source ID and reply headers are validated',()=>{
 const valid={message:'Un problema en el precio',consent:true};
 for(const value of [null,[],{...valid,consent:false},{...valid,message:'breve'},{...valid,message:'x'.repeat(5001)},{...valid,website:'spam'},{...valid,reply_email:'reply@example.invalid\r\nBcc:x@y.invalid'},{...valid,source_document_id:'wrong'}])assert.throws(()=>validateBugReport(value));
 for(const value of ['https://external.invalid','//external.invalid','/\\external.invalid','/products\nprivate'])assert.equal(reportPagePath(value),'');
});
