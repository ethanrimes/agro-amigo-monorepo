const { test } = require('node:test');
const assert = require('node:assert/strict');
const ts = require('typescript'), fs = require('node:fs'), path = require('node:path');
const api = {};
new Function('exports', 'require', ts.transpileModule(fs.readFileSync(path.join(__dirname,
  '../src/lib/evidence-query-context.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText)(api, name => {
  if (name === './label-normalization') return require('./helpers/load-label-normalization.cjs')();
  if (name === './market-types') {
    const types = {};
    new Function('exports', ts.transpileModule(fs.readFileSync(path.join(__dirname,
      '../src/lib/market-types.ts'), 'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS,
      target:ts.ScriptTarget.ES2022}}).outputText)(types);
    return types;
  }
  if (name === './wage-basis-display') {
    const display = {};
    new Function('exports', ts.transpileModule(fs.readFileSync(path.join(__dirname,
      '../src/lib/wage-basis-display.ts'), 'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS,
      target:ts.ScriptTarget.ES2022}}).outputText)(display);
    return display;
  }
  throw new Error(name);
});
test('own monthly and weekly wage PDFs retain the card payment basis in consultation filters',()=>{
  const fixture=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/dane-wage-basis-source.json'),'utf8'));
  for(const [name,market,expected] of [
    ['Mensual agrícola sin alimentación','Duitama','Pago mensual · sin alimentación'],
    ['Semanal agrícola con alimentación','Manizales','Pago semanal · con alimentación'],
  ]) {
    assert.ok(fixture.examples.some(row=>row.name===name&&row.market===market));
    const original=[{label:'Presentación de la consulta',value:'Jornal'},
      {label:'Presentación en la fuente',value:'Jornal'}];
    const query=new URLSearchParams({productName:name,presentation:'Jornal',municipality:market,month:'2012-09-30'});
    const before=JSON.stringify({original,query:query.toString()});
    const shown=api.evidenceQueryContext(original,query);
    assert.equal(shown[0].value,expected);
    assert.equal(shown[1].value,'Jornal','literal source metadata stays unchanged');
    assert.equal(JSON.stringify({original,query:query.toString()}),before);
  }
});
test('verified consultation product context wins over an unrelated wage name in the URL',()=>{
  const original=[{label:'Producto de la consulta',value:'Wuxal'},{label:'Presentación de la consulta',value:'Jornal'}];
  assert.equal(api.evidenceQueryContext(original,new URLSearchParams({productName:'Mensual agrícola sin alimentación'}))[1].value,'Jornal');
});
test('wage source filters do not invent a payment basis from ambiguous names or conflicting meals',()=>{
  for(const [productName,presentation] of [['Mensual comercial','Jornal'],['Mensual agrícola sin alimentación','Con alimentación'],['Semanal agrícola','Kilogramo']]) {
    const shown=api.evidenceQueryContext(undefined,new URLSearchParams({productName,presentation}));
    assert.equal(shown.find(row=>row.label==='Presentación de la consulta').value,presentation);
  }
});
test('daily original retains inherited consultation department without claiming publisher geography',()=>{
  assert.deepEqual(api.evidenceQueryContext(undefined,new URLSearchParams('department=Quind%C3%ADo&locator=JSON+resultset%5B0%5D')),
    [{label:'Departamento de la consulta',value:'Quindío'}]);
});
test('verified source place context wins over raw numeric IDs and remains immutable',()=>{
  const original=[{label:'Municipio de referencia',value:'Medellín, Antioquia (05001)'},
    {label:'Departamento de referencia',value:'Antioquia (05)'}];
  const before=JSON.stringify(original);
  assert.deepEqual(api.evidenceQueryContext(original,new URLSearchParams('municipality=05001&department=05')),original);
  assert.equal(JSON.stringify(original),before);
  assert.deepEqual(api.evidenceQueryContext(undefined,new URLSearchParams('municipality=05001&department=05')),[]);
});
test('human municipal filters survive metadata replacement; unrelated parameters are not exposed as filters',()=>{
  const source=[null,{label:5,value:'bad'},{label:'Período',value:'2014-09'}];
  assert.deepEqual(api.evidenceQueryContext(source,new URLSearchParams('municipality=Armenia&department=Quind%C3%ADo&secret=not-a-filter')),
    [{label:'Período',value:'2014-09'},{label:'Departamento de la consulta',value:'Quindío'},{label:'Municipio de la consulta',value:'Armenia'}]);
  assert.equal(source.length,3);
});
test('a historical quote date stays distinct from its shared workbook reference period',()=>{
  const original=[{label:'Período del documento',value:'2026-08-31'}];
  assert.deepEqual(api.evidenceQueryContext(original,new URLSearchParams('month=2026-07-31&productName=Cacao&marketName=ICCO&presentation=Caja+de+cart%C3%B3n&units=2.5+Kilogramo')),
    [...original,{label:'Producto de la consulta',value:'Cacao'},{label:'Mercado de la consulta',value:'ICCO'},
      {label:'Presentación de la consulta',value:'Caja de cartón'},{label:'Unidades de la consulta',value:'2.5 Kilogramo'},
      {label:'Fecha del dato consultado',value:'2026-07-31'}]);
  assert.equal(original.length,1,'Original metadata is unchanged');
});
test('malformed historical dates and raw identities cannot invent readable source filters',()=>{
  for(const month of ['2026-99-31','2026-02-31','2026-08','not-a-date'])
    assert.deepEqual(api.evidenceQueryContext(undefined,new URLSearchParams({month,product:'raw-id',market:'raw-id'})),[]);
});
test('a quoted price keeps its currency and unit visible beside original document metadata',()=>{
  const original=[{label:'Período del documento',value:'2026-09-25'}];
  assert.deepEqual(api.evidenceQueryContext(original,new URLSearchParams('units=kg&currency=COP&month=2012-06-22')),
    [...original,{label:'Unidades de la consulta',value:'kg'},
      {label:'Moneda de la consulta',value:'COP'},
      {label:'Fecha del dato consultado',value:'2012-06-22'}]);
  assert.equal(original.length,1);
});
test('source consultation translates typed units while preserving literal source units and selectors',()=>{
  for (const [unit, expected] of [['unit','unidad'],['litre','litro'],['125kg','carga de 125 kg'],['kg','kg'],['24 Unidad 500 CC','24 Unidad 500 CC'],['__proto__','__proto__'],['constructor','constructor']]) {
    const original=[{label:'Unidades de la consulta',value:unit},{label:'Unidades en la fuente',value:unit}];
    const query=new URLSearchParams({units:unit});
    const before=JSON.stringify({original,query:query.toString()});
    const result=api.evidenceQueryContext(original,query);
    assert.equal(result[0].value,expected);
    assert.equal(result[1].value,unit);
    assert.equal(JSON.stringify({original,query:query.toString()}),before);
    assert.equal(api.evidenceQueryContext(undefined,query)[0].value,expected);
  }
});
test('electricity source consultation preserves provider and stratum without inventing product or units',()=>{
  const original=[{label:'Período del documento',value:'2021–2026'}];
  assert.deepEqual(api.evidenceQueryContext(original,new URLSearchParams({
    providerName:'Afinia Grupo-epm',stratum:'1',month:'2026-06-30',unrelated:'not a filter',
  })),[...original,{label:'Proveedor de la consulta',value:'Afinia Grupo-epm'},
    {label:'Estrato de la consulta',value:'1'},
    {label:'Fecha del dato consultado',value:'2026-06-30'}]);
  assert.equal(original.length,1);
});
test('consultation presentation spelling is clean while source metadata and selector stay literal',()=>{
  const original=[{label:'Presentación de la consulta',value:'Caja de cartÓn'},
    {label:'Presentación en la fuente',value:'Caja de cartÓn'}];
  const before=JSON.stringify(original), query=new URLSearchParams({presentation:'Caja de cartÓn',units:'24 Unidad 500 CC'});
  const shown=api.evidenceQueryContext(original,query);
  assert.equal(shown[0].value,'Caja de cartón');
  assert.equal(shown[1].value,'Caja de cartÓn');
  assert.equal(query.get('presentation'),'Caja de cartÓn');
  assert.equal(JSON.stringify(original),before);
});
test('a verified supply sum names the month independently of its first reporting day',()=>{
  const records=[{food_name:'Papa capira',quantity_kg:161000,reporting_days:24,
    period_start:'2026-08-01',first_reported_on:'2026-08-03',observed_on:'2026-08-31'}];
  const original=[{label:'Período del documento',value:'2026'}];
  const before=JSON.stringify({original,records});
  assert.deepEqual(api.evidenceQueryContext(original,new URLSearchParams('food=papa-capira&month=2026-08-01'),records),
    [...original,{label:'Mes del abastecimiento consultado',value:'agosto de 2026'}]);
  assert.equal(JSON.stringify({original,records}),before);
});
test('a supply-like URL or unrelated record cannot turn a quote date into a monthly quantity',()=>{
  const query=new URLSearchParams('food=papa-capira&month=2026-08-01');
  for(const records of [undefined,[{price:161000,period_start:'2026-08-01'}],
    [{food_name:'Papa capira',quantity_kg:161000,reporting_days:24,period_start:'2026-07-01'}]])
    assert.deepEqual(api.evidenceQueryContext(undefined,query,records),
      [{label:'Fecha del dato consultado',value:'2026-08-01'}]);
});
