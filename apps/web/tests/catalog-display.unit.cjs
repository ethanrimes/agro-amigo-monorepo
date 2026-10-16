const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const ts=require('typescript');
function load(name){
 const exports={};
 new Function('exports','require',ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/lib',name+'.ts'),'utf8'),{
  compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}
 }).outputText)(exports,imported=>load(imported.replace(/^\.\//,'')));
 return exports;
}
const {catalogSuggestionDetail,catalogHref,catalogNameMatchesExactly}=load('catalog-display');
const weekly={id:'reference:weekly',name:'Acelga',category:'Productos agrícolas',image_key:'produce',price:433,
 previous_price:418,date:'2026-10-02',market_count:1,unit:'kg',source:'DANE',period:'weekly',
 basis:'Precio mayorista publicado',market:'Bogotá, D.C., Corabastos',href:'/references/weekly'};
test('same-name daily, weekly and historical prices are distinguishable before selection',()=>{
 const daily={...weekly,id:'reference:daily',price:489,period:'daily',href:'/references/daily'};
 const old={...weekly,id:'reference:2012',price:793,date:'2012-06-22',market:'Bogotá, D. C. Corabastos',href:'/references/2012'};
 const details=[daily,weekly,old].map(catalogSuggestionDetail);
 assert.equal(new Set(details).size,3);
 assert.match(details[0],/Diario/);assert.match(details[1],/Semanal/);
 assert.match(details[2],/2012/);
 details.forEach(detail=>{assert.match(detail,/Corabastos/);assert.match(detail,/COP \/ kg/)});
 assert.deepEqual([daily,weekly,old].map(p=>catalogHref(p)),['/references/daily','/references/weekly','/references/2012']);
});
test('packaging and source currency stay explicit for city and international search results',()=>{
 const city={...weekly,id:'mora',name:'Mora de castilla',series:'city',period:'daily',unit:'unit',
  basis:'Precio mayorista por empaque',presentation:'Caja de cartón',units:'12.5 Kilogramo',market:'Barranquilla, Barranquillita',href:undefined};
 const small={...city,units:'2.5 Kilogramo'};
 assert.notEqual(catalogSuggestionDetail(city),catalogSuggestionDetail(small));
 assert.match(catalogSuggestionDetail(city),/Caja de cartón.*12\.5 Kilogramo.*COP \/ unidad/);
 const flower={...weekly,currency:'USD',unit:'bunch',market:'Miami',period:'daily'};
 assert.match(catalogSuggestionDetail(flower),/Miami.*USD \/ bunch/);
 assert.doesNotMatch(catalogSuggestionDetail(flower),/COP/);
});
test('exact product names ignore case, accents and repeated whitespace without merging varieties',()=>{
 const maize={...weekly,name:'Maíz blanco trillado'};
 for(const query of ['MAIZ BLANCO TRILLADO','maíz blanco trillado','  MaIz  bLaNcO  TrIlLaDo  ']) {
  assert.equal(catalogNameMatchesExactly(maize,query),true);
  assert.equal(catalogNameMatchesExactly({...maize,name:'Maíz blanco retrillado'},query),false);
 }
 assert.equal(catalogNameMatchesExactly(maize,'maiz blanco'),false);
});
