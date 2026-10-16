const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ts=require('typescript');
const normalization=require('./helpers/load-label-normalization.cjs')();
const file=path.join(__dirname,'../src/lib/quote-filter-options.ts');
const exportsForTest={};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(file,'utf8'),{
  compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022},
}).outputText,{exports:exportsForTest,require(name){
  if(name==='./label-normalization')return normalization;
  if(name==='./planning-math')return {fold:value=>value.normalize('NFD').replace(/\p{M}/gu,'').toLowerCase().trim()};
  throw new Error(name);
}});
const plain=value=>JSON.parse(JSON.stringify(value));

test('identical display markets retain separate IDs and show their own published report dates',()=>{
 const markets=[
  {id:'sipsa-barranquilla-granabastos',name:'Barranquilla, Granabastos',literal_name:'Barranquilla, Granabastos',first_report_on:'2026-09-07',last_report_on:'2026-10-05'},
  {id:'dane-city-barranquilla-granabastos',name:'Barranquilla, Granabastos',literal_name:'BARRANQUILLA, GRANABASTOS',first_report_on:'2021-09-01',last_report_on:'2021-09-01'},
 ];
 const before=JSON.stringify(markets),choices=plain(exportsForTest.quoteMarketOptions(markets));
 assert.deepEqual(choices.map(x=>x.id),markets.map(x=>x.id));
 assert.match(choices[0].detail,/07\/09\/2026–05\/10\/2026/);
 assert.match(choices[1].detail,/Informe: 01\/09\/2021/);
 assert.match(choices[1].detail,/BARRANQUILLA, GRANABASTOS/);
 assert.equal(JSON.stringify(markets),before);
});
test('case and decomposed accents do not hide duplicate market spellings',()=>{
 const choices=exportsForTest.quoteMarketOptions([
  {id:'a',name:'MEDELLÍN',literal_name:'MEDELLÍN'},
  {id:'b',name:'medellin'.normalize('NFD'),literal_name:'medellin'},
 ]);
 assert.ok(choices.every(x=>x.detail?.includes('Nombre en la fuente:')));
 assert.deepEqual(Array.from(choices,x=>x.id),['a','b']);
});
test('Manizales source spellings retain distinct market choices with their own coverage and package dimensions',()=>{
 const markets=[
  {id:'dane-city-manizales-centro-galerias',name:'Manizales, Centro Galerías',literal_name:'Manizales, Centro Galerias',series:'city',presentation:'Kilogramo',units:'1 Kilogramo',first_report_on:'2021-12-16',last_report_on:'2022-02-03'},
  {id:'sipsa-manizales-centro-galerias',name:'Manizales, Centro Galerías',literal_name:'Manizales, Centro Galerías',series:'city',presentation:'Kilogramo',units:'1 Kilogramo',first_report_on:'2020-03-26',last_report_on:'2026-10-01'},
 ];
 const before=JSON.stringify(markets),choices=plain(exportsForTest.quoteMarketOptions(markets));
 assert.deepEqual(choices.map(x=>x.id),['dane-city-manizales-centro-galerias','sipsa-manizales-centro-galerias']);
 assert.deepEqual(choices.map(x=>x.label),['Manizales, Centro Galerías','Manizales, Centro Galerías']);
 assert.match(choices[0].detail,/Informes: 16\/12\/2021–03\/02\/2022/);
 assert.match(choices[0].detail,/Nombre en la fuente: Manizales, Centro Galerias/);
 assert.match(choices[1].detail,/Informes: 26\/03\/2020–01\/10\/2026/);
 assert.match(choices[1].detail,/Nombre en la fuente: Manizales, Centro Galerías/);
 assert.deepEqual(markets.map(x=>[x.series,x.presentation,x.units]),[
  ['city','Kilogramo','1 Kilogramo'],['city','Kilogramo','1 Kilogramo'],
 ]);
 assert.equal(JSON.stringify(markets),before);
});
test('unknown report dates never fabricate date coverage or expose internal identifiers',()=>{
 const choices=plain(exportsForTest.quoteMarketOptions([{id:'private-source-key',name:'Otro mercado',first_report_on:null,last_report_on:'invalid'}]));
 assert.deepEqual(choices,[{id:'private-source-key',label:'Otro mercado'}]);
});
test('presentation spelling is corrected for display while exact source values remain selectable',()=>{
 const values=['Caja de carton','Caja de cartón','Caja de carto\u0301n','BULTO'];
 const choices=plain(exportsForTest.quotePresentationOptions(values));
 assert.deepEqual(choices.map(x=>x.id),values);
 assert.deepEqual(choices.map(x=>x.label),['Caja de cartón','Caja de cartón','Caja de cartón','Bulto']);
 assert.match(choices[0].detail,/Texto en la fuente: Caja de carton/);
 assert.equal(choices[1].detail,undefined);
 assert.deepEqual(values,['Caja de carton','Caja de cartón','Caja de carto\u0301n','BULTO']);
});
