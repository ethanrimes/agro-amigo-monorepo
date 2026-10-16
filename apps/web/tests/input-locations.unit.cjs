const { test } = require('node:test');
const assert = require('node:assert/strict');
const ts = require('typescript'), fs = require('node:fs'), path = require('node:path');
function load(name,mocks={}) { const api={};new Function('exports','require',
  ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/lib',name),'utf8'),
    {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText)
    (api,n=>mocks[n]);return api; }
const labels=load('filter-labels.ts'),api=load('input-locations.ts',{'./filter-labels':labels});
test('current geographic choices select one latest literal quote and keep input history untouched',()=>{
 const old={id:'wuxal',department:'Quindio',municipality:'Armenia',observed_on:'2014-09-30',price:30300,document_id:'pdf'};
 const current={...old,department:'Quindío',observed_on:'2023-04-30',price:55225,document_id:'excel'};
 const rows=[old,current];const copy=JSON.stringify(rows);
 assert.deepEqual(api.latestInputLocations(rows),[current]);
 assert.equal(JSON.stringify(rows),copy);assert.equal(old.department,'Quindio');
});
test('different inputs, exact municipalities and unknown geography remain separate',()=>{
 const base={id:'a',department:'Córdoba',municipality:'Montería',observed_on:'2026-01-01',price:100};
 const rows=[base,{...base,id:'b'},{...base,municipality:'Cereté'},
  {...base,department:'Córdoba Norte'},{...base,municipality:'Monteria'}];
 assert.equal(api.latestInputLocations(rows).length,5);
});
test('native case and verified department spellings keep canonical bookmark choices',()=>{
 assert.equal(api.canonicalInputLocation('["QUINDIO","Armenia"]',true),'["Quindío","Armenia"]');
 assert.equal(api.canonicalInputLocation('Cordoba',false),'Córdoba');
 assert.equal(api.canonicalInputLocation('__national__',true),'__national__');
 assert.equal(api.canonicalInputLocation('invalid',true),'invalid');
});
test('same-date current locations preserve deterministic single source selection',()=>{
 const row={id:'a',department:'Quindio',observed_on:'2026-01-01',price:120,document_id:'b'};
 const other={...row,department:'Quindío',price:100,document_id:'a'};
 assert.deepEqual(api.latestInputLocations([row,other]),[other]);
 assert.deepEqual(api.latestInputLocations([other,row]),[other]);
});
