const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

const lib = path.join(__dirname, '../src/lib');
const lexicon = JSON.parse(fs.readFileSync(path.join(__dirname, '../../../shared/label-normalization.json'), 'utf8'));
function load(file, mocks) {
  const exports = {};
  const code = ts.transpileModule(fs.readFileSync(path.join(lib, file), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
      esModuleInterop: true, resolveJsonModule: true },
  }).outputText;
  new Function('exports','require',code)(exports,(name) =>
    name === 'server-only' ? {} : name.endsWith('shared/label-normalization.json')
      ? lexicon : mocks[name]);
  return exports;
}
const labels=load('label-normalization.ts',{});
const product=(id) => ({ id,name:'Limón Tahití',category:'Frutas',price:1800,
  date:'2021-11-16',market_count:1,unit:'kg',source:'DANE',period:'city',
  series:'city',presentation:'Kilogramo',units:'1 Kilogramo' });
const catalog=load('server/catalog.ts',{
  './city-catalog-names': { cityCatalogNames: async () => [] },
  './city-publication-epoch': { cityPublicationEpoch: async () => '0' },
  './queries': { catalog: async () => ({ products:[product('limon-thaiti'),product('limon-tahiti')],
    regions:[],cacheExpiresAt:Infinity }) },
  './summary-references': { latestSummaryReferences: async () => [] },
  './official-references': { latestOfficialReferenceSnapshot: async () => ({value:[],expires:Infinity}) },
  '../filter-labels': { departmentKey:x=>x,departmentLabels:x=>x },
  '../label-normalization': labels,
  '../catalog-frequency': load('catalog-frequency.ts', {}),
});

test('source typo displays canonical spelling while keeping both product IDs and raw search', async () => {
  assert.equal(labels.normalizeLabel('Limón thaití','product'),'Limón Tahití');
  const raw={product_id:'limon-thaiti',product_name:'Limón thaití',category:'Frutas',
    market:'Cali, Santa Helena',document_id:'35037d8b903aee4af4f0cb38538a9117a3f64e0585ae50e88e34dc33eff548e3',
    source_locator:'PDF page 1,table 1,row 12,round 1',min_price:1800,max_price:1900};
  const shown=labels.normalizeOfficialLabels(raw);
  assert.equal(shown.product_name,'Limón Tahití');
  assert.equal(raw.product_name,'Limón thaití');
  for(const field of ['product_id','document_id','source_locator','min_price','max_price'])
    assert.equal(shown[field],raw[field]);
  const output=await catalog.unifiedCatalog('',true);
  assert.equal(output.products.length,2);
  const typo=output.products.find(p=>p.id==='limon-thaiti');
  const canonical=output.products.find(p=>p.id==='limon-tahiti');
  assert.equal(typo.name,'Limón Tahití');
  assert.equal(canonical.name,'Limón Tahití');
  assert.notEqual(typo.href,canonical.href);
  assert.ok(typo.search_terms.includes('Limón thaití'));
  assert.ok(!canonical.search_terms.includes('Limón thaití'));
});
