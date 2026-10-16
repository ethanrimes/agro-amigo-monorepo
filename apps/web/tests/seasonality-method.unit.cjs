const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const ts=require('typescript'),React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const root=path.join(__dirname,'../src');
function load(file,mocks){const exports={};vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(root,file),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,{exports,require:n=>Object.hasOwn(mocks,n)?mocks[n]:{}});return exports;}
test('published method describes the actual median annual-normalized chart without projecting latest price',async()=>{
 const years=[2021,2022,2023].map((year,i)=>({reference_year:year,monthly_prices:Array.from({length:12},(_,m)=>(m+1)*(i+1)*100),source_rows:Array.from({length:12},(_,m)=>`native-${year}-${m+1}`),source_documents:Array.from({length:12},()=>[`source-${year}`])}));
 const planning=load('lib/server/planning.ts',{
  './db':{WINDOW:'true',database:()=>({query:async sql=>({rows:sql.includes('FROM seasonal_year')?years:[{price:99999,unit:'kg',date:'2026-08-31',market:'Quindio'}]})})},
  './city-partial-review':load('lib/server/city-partial-review.ts',{}),
  '../label-normalization':{normalizeLabel:(value,domain)=>domain==='place'&&value==='Quindio'?'Quindío':value},
 });
 const data=await planning.seasonality('tomate-chonto','source-market');
 assert.deepEqual(data.years,years);
 assert.equal(data.latest.market,'Quindío');
 assert.equal(data.latest.price,99999);
 assert.match(data.method,/promedio de sus 12 precios mensuales/);
 assert.match(data.method,/multiplica por 100/);
 assert.match(data.method,/mediana de esos índices/);
 assert.match(data.method,/al menos 3 años completos/);
 assert.match(data.method,/no calcula precios futuros/);
 assert.doesNotMatch(data.method,/percentiles 25|50 y 75|precio del mes de referencia/);
 const math=load('lib/planning-math.ts',{});
 const chart=load('components/planning/SeasonalChart.tsx',{
  'react/jsx-runtime':require('react/jsx-runtime'),'@/lib/planning-math':math,
  '@/lib/market-types':{money:v=>String(v),number:v=>String(v),dateLabel:v=>v},
  './EvidenceLink':{EvidenceLink:({children})=>React.createElement('a',null,children)},
 });
 const html=renderToStaticMarkup(React.createElement(chart.SeasonalChart,{data,month:1,onMonth(){}}));
 const actual=[...html.matchAll(/class="bar-value">([0-9]+)</g)].map(m=>Number(m[1]));
 assert.deepEqual(actual,Array.from({length:12},(_,m)=>Math.round((m+1)/6.5*100)));
 assert.ok(html.includes(data.method));
 assert.ok(html.includes('Sin ajuste por inflación.'));
 const changed=renderToStaticMarkup(React.createElement(chart.SeasonalChart,{data:{...data,latest:{...data.latest,price:1}},month:1,onMonth(){}}));
 assert.deepEqual([...changed.matchAll(/class="bar-value">([0-9]+)</g)].map(m=>Number(m[1])),actual);
});
