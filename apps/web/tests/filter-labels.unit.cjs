const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const cache = new Map();
function load(name) {
  name = path.resolve(name);
  if (cache.has(name)) return cache.get(name);
  if (name.endsWith('.json')) {
    const data = JSON.parse(fs.readFileSync(name, 'utf8'));
    cache.set(name, data);
    return data;
  }
  const exports = {};
  cache.set(name, exports);
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(name,'utf8'),{
    compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,
      esModuleInterop:true,resolveJsonModule:true},
  }).outputText,{exports,URL,URLSearchParams,Intl,Date,console,
    require:relative=>load(path.resolve(path.dirname(name),relative.endsWith('.json') ? relative : relative+'.ts'))});
  return exports;
}
const labels=load(path.join(__dirname,'../src/lib/filter-labels.ts'));
const {paginateCatalog}=load(path.join(__dirname,'../src/lib/catalog-page.ts'));

test('department options group case spellings without dropping the native accents',()=>{
  assert.deepEqual([...labels.departmentLabels(['ATLÁNTICO','Atlántico','BOGOTÁ, D.C.','Bogotá, D.C.','VALLE DEL CAUCA','Valle del Cauca'])],
    ['Atlántico','Bogotá, D.C.','Valle del Cauca']);
});

test('verified DANE department aliases share one filter and retain unknown locations',()=>{
  const originals=['Quindio','Quindío','Cordoba','Córdoba','Bolivar','Bolívar',
    'Bogotá D.C.','Bogotá, D. C.','BOGOTÁ, D.C.'];
  assert.deepEqual([...labels.departmentLabels(originals)],
    ['Bogotá, D.C.','Bolívar','Córdoba','Quindío']);
  for (const [selection, native] of [['QUINDÍO','Quindio'],['Córdoba','Cordoba'],
    ['bolivar','Bolívar'],['Bogotá, D.C.','Bogotá, D. C.']]) {
    assert.ok(labels.departmentVariants(selection).includes(native), `${selection} must reach ${native}`);
    assert.equal(labels.departmentKey(selection),labels.departmentKey(native));
  }
  assert.equal(labels.departmentKey('Córdoba del Sur'),'córdoba del sur',
    'Unrecognized geography is not assigned to a department by substring');
  assert.equal(originals[0],'Quindio','The literal source spelling stays unchanged');
});

test('one category filter reaches all source case and accent variants before pagination',()=>{
  const products=['FRUTAS','Frutas','frutas','Verduras','Tuberculos, raices y platanos','Tubérculos, raíces y plátanos']
    .map((category,i)=>({id:String(i),identity:String(i),category,name:'Producto '+i,unit:'kg',price:100+i,source:'DANE',date:'2026-10-02'}));
  const catalog={products,regions:['ATLÁNTICO','Atlántico'],latestDate:'2026-10-02',filters:{region:'',reference_scope:'all'}};
  const result=paginateCatalog(catalog,{category:'Frutas',limit:2});
  assert.equal(result.total,3);
  assert.deepEqual([...result.products].map(p=>p.identity),['0','1']);
  assert.deepEqual([...result.regions],['Atlántico']);
  assert.equal(result.categories.filter(c=>labels.categoryKey(c)==='frutas').length,1);
  const roots=paginateCatalog(catalog,{category:'Tubérculos, raíces y plátanos'});
  assert.deepEqual([...roots.products].map(p=>p.identity),['4','5']);
  assert.equal(products[0].category,'FRUTAS','The literal source heading is unchanged');
});

test('category options retain accented spelling and readable headings regardless of source order',()=>{
  assert.deepEqual([...labels.categoryLabels(['FRUTAS','Frutas','Tuberculos, raices y platanos','TUBÉRCULOS, RAÍCES Y PLÁTANOS'])],
    ['Frutas','Tubérculos, raíces y plátanos']);
});
