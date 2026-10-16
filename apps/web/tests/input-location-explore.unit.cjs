const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const ts=require('typescript');
function load(file,mocks={}) {
 const exports={};
 const source=fs.readFileSync(path.join(__dirname,'../src/lib',file),'utf8');
 new Function('exports','require',ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText)
   (exports,name=>name==='server-only'?{}:mocks[name]);
 return exports;
}
const labels=load('filter-labels.ts');
const locations=load('input-locations.ts',{'./filter-labels':labels});
const identity=load('input-identity-equivalence.ts',{
 '../../../../shared/input-identity-equivalences.json':{default:JSON.parse(fs.readFileSync(path.join(__dirname,'../../../shared/input-identity-equivalences.json'),'utf8'))},
});
const sourceRows=[
 {id:'wuxal',name:'Wuxal',category:'Fertilizantes',presentation:'1 litro',department:'Risaralda',municipality:'Belén De Umbría',price:100,observed_on:'2015-05-31',document_id:'old',source_locator:'PDF page 1'},
 {id:'wuxal',name:'Wuxal',category:'Fertilizantes',presentation:'1 litro',department:'Risaralda',municipality:'Belén de Umbría',price:120,observed_on:'2026-08-31',document_id:'new',source_locator:'1.2!row 1'},
];
const calls=[];
const db={query:async(sql,args=[])=>{
 calls.push({sql,args});
 if(sql.includes('SELECT id,name,category,presentation')) return {rows:sourceRows
   .filter(row=>args[2].includes(row.municipality))
   .map(row=>({...row,date:row.observed_on}))};
 if(sql.includes('FROM municipality ORDER BY id')) return {rows:[
   {id:'belen',name:'Belén de Umbría',department_id:'risaralda',department:'Risaralda',latitude:5.2,longitude:-75.9},
   {id:'unaccented',name:'Belen de Umbría',department_id:'risaralda',department:'Risaralda',latitude:5.3,longitude:-75.8},
 ]};
 throw new Error('Unexpected SQL '+sql.slice(0,80));
}};
const explore=load('server/explore.ts',{
 './db':{database:()=>db,WINDOW:'observed_on<=CURRENT_DATE'},
 './planning':{inputs:async()=>sourceRows},
 './price-quotes':{PRICE_QUOTES:'',filteredProduct:async()=>null},
 '../filter-labels':labels,'../input-locations':locations,
 '../input-identity-equivalence':identity,
 '../pdf-locator':{pdfLocationPage:()=>null},
 './supply-sql':{supplyQueries:()=>({})},
 './market-sql':{marketsQuery:()=>'',marketDetailQuery:()=>'',marketProductsQuery:()=>''},
});

test('all-history input detail uses exact native municipality variants in indexed ANY predicate',async()=>{
 calls.length=0;
 const result=await explore.inputDetail('wuxal','Risaralda','municipality','Belén De Umbría',true);
 assert.equal(result.input.price,120);
 assert.equal(result.regions.length,1);
 assert.deepEqual(result.history.map(row=>row.price),[100,120]);
 const query=calls.find(call=>call.sql.includes('SELECT id,name,category,presentation'));
 assert.ok(query.sql.includes('municipality=ANY($3::text[])'));
 assert.deepEqual(query.args[2],['Belén De Umbría','Belén de Umbría']);
});

test('input map uses one case-only point and does not snap a different accent',async()=>{
 calls.length=0;
 const result=await explore.mapData('input','wuxal','price',{scope:'municipality',history:'all',municipality:'Belén De Umbría'});
 assert.equal(result.points.length,1);
 assert.equal(result.points[0].id,'belen');
 assert.equal(result.points[0].value,120);
 assert.equal(result.points[0].name,'Belén de Umbría, Risaralda');
});
