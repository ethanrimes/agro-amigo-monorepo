const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const ts=require('typescript');
function load(file,mocks={}) {
 const exports={};
 const source=fs.readFileSync(path.join(__dirname,'../src/lib',file),'utf8');
 new Function('exports','require',ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText)
   (exports,name=>mocks[name]);
 return exports;
}
const labels=load('filter-labels.ts');
const locations=load('input-locations.ts',{'./filter-labels':labels});

test('NFC case-only municipality aliases keep exact product and accent boundaries',()=>{
 const rows=[
  {id:'wuxal',department:'Risaralda',municipality:'Belén De Umbría',observed_on:'2015-05-31',price:100},
  {id:'wuxal',department:'Risaralda',municipality:'Belén de Umbría',observed_on:'2026-08-31',price:120},
  {id:'wuxal',department:'Risaralda',municipality:'Santa Rosa De Cabal',observed_on:'2015-05-31',price:160},
  {id:'wuxal',department:'Risaralda',municipality:'Santa Rosa de Cabal',observed_on:'2023-04-30',price:180},
  {id:'other',department:'Risaralda',municipality:'Belén De Umbría',observed_on:'2026-08-31',price:900},
  {id:'wuxal',department:'Risaralda',municipality:'Belen de Umbría',observed_on:'2026-08-31',price:300},
 ];
 const winners=locations.latestInputLocations(rows);
 assert.equal(winners.length,4);
 assert.deepEqual(winners.filter(r=>r.id==='wuxal').map(r=>r.price).sort((a,b)=>a-b),[120,180,300]);
 assert.equal(locations.inputLocationId('Risaralda','Belén De Umbría',true),
   locations.inputLocationId('Risaralda','Belén de Umbría',true));
 assert.notEqual(locations.inputLocationId('Risaralda','Belen de Umbría',true),
   locations.inputLocationId('Risaralda','Belén de Umbría',true));
 assert.equal(locations.canonicalInputLocation('["Risaralda","Santa Rosa De Cabal"]',true),
   '["Risaralda","Santa Rosa de Cabal"]');
});
