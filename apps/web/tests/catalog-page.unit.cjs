const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const ts=require('typescript');
function load(name,parent=path.join(__dirname,'../src/lib/entry.ts')){
 const filename=path.resolve(path.dirname(parent),name.endsWith('.json')?name:name+'.ts');
 if(filename.endsWith('.json')) return JSON.parse(fs.readFileSync(filename,'utf8'));
 const exports={};
 new Function('exports','require',ts.transpileModule(fs.readFileSync(filename,'utf8'),{
  compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true}
 }).outputText)(exports,imported=>load(imported,filename));
 return exports;
}
const {paginateCatalog}=load('catalog-page');
const product=(id,name,extra={})=>({id,identity:id,saved_key:id,name,category:'Granos y cereales',
 image_key:'produce',price:100,date:'2026-08-31',market_count:1,unit:'kg',source:'DANE',
 period:'monthly',kind:'product',currency:'COP',map_supported:true,...extra});
const catalog={products:[
 product('retrillado','Maíz blanco retrillado'),
 product('trillado','Maíz blanco trillado'),
 product('reference:trillado','Maíz blanco trillado',{kind:'official-reference',map_supported:false}),
],regions:[],latestDate:'2026-08-31',filters:{region:''}};
test('exact maize searches select the correct variety first and paginate every retained identity',()=>{
 for(const q of ['MAIZ BLANCO TRILLADO','maíz blanco trillado']){
  const first=paginateCatalog(catalog,{q,limit:1});
  assert.equal(first.products[0].id,'trillado');
  assert.equal(first.total,3);
  const rest=paginateCatalog(catalog,{q,offset:1,limit:2});
  assert.deepEqual(rest.products.map(p=>p.id),['reference:trillado','retrillado']);
  assert.equal(rest.pagination.has_more,false);
 }
 assert.deepEqual(catalog.products.map(p=>p.id),['retrillado','trillado','reference:trillado']);
});
test('blank and partial searches preserve ordering, while saved filters keep distinct varieties',()=>{
 for(const q of ['','maiz blanco']){
  assert.deepEqual(paginateCatalog(catalog,{q}).products.map(p=>p.id),['retrillado','trillado','reference:trillado']);
 }
 const saved=paginateCatalog(catalog,{q:'MAIZ BLANCO TRILLADO',saved:['retrillado']});
 assert.deepEqual(saved.products.map(p=>p.id),['retrillado']);
 assert.equal(saved.total,1);
});
