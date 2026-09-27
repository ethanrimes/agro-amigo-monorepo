/* Product detail options/classifications: production-shaped TEMP PostgreSQL. */
const { test, beforeEach, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const { Client, types } = require('pg');
// Match production db.ts, including numeric JSON aggregation equivalence.
types.setTypeParser(1700, Number);
types.setTypeParser(20, Number);
types.setTypeParser(1082, value => value);
const root = path.join(__dirname, '../../..');
const server = path.join(__dirname, '../src/lib/server');
const WINDOW = fs.readFileSync(path.join(server, 'db.ts'), 'utf8').split('export const WINDOW =')[1].match(/"([^"]+)"/)[1];
function moduleSQL(filename, mocks, globals = {}) {
  const exports = {};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(server, filename), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, {
    exports, require: (name) => name === 'server-only' ? {} : mocks[name], ...globals,
  });
  return exports;
}
const classificationModule = moduleSQL('../price-classification.ts', {});
const quoteModule = moduleSQL('price-quotes.ts', { '../price-classification': classificationModule, './db': { WINDOW, database: () => db }, './summary-references': { summaryReferencesForProduct: async () => [] } });
const schema = fs.readFileSync(path.join(root, 'pipelines/ingestion/schema.sql'), 'utf8');
const view = schema.split('CREATE OR REPLACE VIEW published_price_observation AS')[1].split('GRANT SELECT ON published_price_observation')[0];
const socket = process.env.AGRO_CATALOG_SQL_SOCKET;
const enabled = socket?.startsWith('/tmp/agro-unified-catalog-pg-');
const tables = ['product','market','source_document','ingestion_asset','price_observation','regional_price','regional_classification'];
let db;
beforeEach(async () => {
  if (!enabled) return;
  db = new Client({ host: socket, port: 65443, database: 'postgres' }); await db.connect();
  await db.query("SET search_path=pg_temp; SET statement_timeout='10s'; SET TIME ZONE 'America/Bogota'");
  for (const table of tables) await db.query(`CREATE TEMP TABLE ${table} (LIKE public.${table} INCLUDING ALL)`);
  const reviewDefinition = schema.match(/CREATE TABLE IF NOT EXISTS price_observation_review \([\s\S]*?\n\);/)[0];
  await db.query(reviewDefinition.replace('CREATE TABLE IF NOT EXISTS', 'CREATE TEMP TABLE'));
  await db.query('CREATE TEMP VIEW published_price_observation AS ' + view);
  await db.query(fs.readFileSync(path.join(root, 'pipelines/ingestion/migrations/20260927_008_catalog_reads.sql'), 'utf8'));
  await db.query(fs.readFileSync(path.join(root, 'pipelines/ingestion/migrations/20260927_011_classification_reads.sql'), 'utf8'));
  await db.query(fs.readFileSync(path.join(root, 'pipelines/ingestion/migrations/20260927_012_product_options_reads.sql'), 'utf8'));
  await db.query('CREATE INDEX regional_price_lookup ON regional_price(product_id,market_name,observed_on DESC); CREATE INDEX regional_market_latest ON regional_price(market_name,observed_on DESC)');
  await db.query(`INSERT INTO product(id,name,category) VALUES('city','Ciudad','Frutas'),('monthly','Mensual','Verduras'),('milk','Leche','Lácteos'),('rice','Arroz','Cereales');
    INSERT INTO market(id,name,city,region) VALUES('a','A','Ciudad A','Uno'),('b','B','Ciudad B','Dos'),('empty','Empty','Ciudad E','Vacía');
    INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content,retrieved_at)
    VALUES('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','Old','DANE','https://example.invalid/old','application/pdf','original','',decode('00','hex'),'2026-09-01'),
    ('bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb','New','DANE','https://example.invalid/new','application/pdf','original','',decode('00','hex'),'2026-09-25')`);
});
afterEach(async () => { if (db) await db.end(); db = undefined; });
const check = (name, fn) => test(name, { skip: !enabled && 'Requires isolated PostgreSQL runner' }, fn);
let seq = 0;
async function regional({ product = 'city', name = 'Nombre literal', market = 'A', day = -1, price = 10, presentation = 'Bulto', quantity = 25, unit = 'Kilogramo', round = 1, doc = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' } = {}) {
  await db.query(`INSERT INTO regional_price(document_id,source_locator,observed_on,product_id,product_name,market_name,category,presentation,quantity,source_unit,round,round_label,min_price,max_price,unit,source_page)
    VALUES($1,$2,CURRENT_DATE+$3::integer,$4,$5,$6,'Frutas',$7,$8,$9,$10,'Ronda',$11::numeric,$11::numeric+2,'package',1)`,
    [doc, 'row-' + (++seq), day, product, name, market, presentation, quantity, unit, round, price]);
}
async function monthly({ product = 'monthly', market = 'a', month = 1, price = 100, source = 'dane-sipsa', unit = 'kg', doc = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' } = {}) {
  await db.query(`INSERT INTO price_observation(product_id,market_id,source_id,observed_on,period,unit,price,source_url,document_id)
    VALUES($1,$2,$3,(date_trunc('month',CURRENT_DATE)-($4||' months')::interval+interval '1 month - 1 day')::date,'monthly',$5,$6,'https://example.invalid/',$7)`, [product, market, source, month, unit, price, doc]);
}

const untilToday = "observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date";
const oldOptions = `WITH quotes AS (${quoteModule.PRICE_QUOTES}) SELECT DISTINCT series,market_id,market_name,presentation,units FROM quotes WHERE product_id=$1 AND ($2='' OR region=$2) AND ${untilToday} ORDER BY series,market_name,presentation,units`;
async function options(product, region='') {
  const raw = (await db.query(quoteModule.PRODUCT_FILTER_OPTIONS_SQL,[product,region])).rows;
  const actual = raw.some(row => row.requires_revision_resolution) ? (await db.query(oldOptions,[product,region])).rows : raw.map(({requires_revision_resolution,...row}) => row);
  assert.deepEqual(actual,(await db.query(oldOptions,[product,region])).rows);
  return {raw,actual};
}
async function classify() {
  await db.query(`INSERT INTO regional_classification(document_id,source_locator,category_path)
    SELECT document_id,source_locator,string_to_array(category,' > ') FROM regional_price ON CONFLICT DO NOTHING`);
}
check('all retained package, market, round, revision and source options match the price oracle',async()=>{
  await regional({day:-1200,presentation:'Caja',quantity:10});
  await regional({day:-2,presentation:'BULTO',quantity:25});
  await regional({day:-2,presentation:'bulto',quantity:25,round:2,price:25,doc:'b'.repeat(64)});
  await regional({day:-1,presentation:'Canastilla',quantity:12.5,market:'B'});
  await regional({day:100,presentation:'Future'});
  await regional({day:-1,presentation:'Unknown',market:'Not curated'});
  await monthly({product:'city',price:100});
  await monthly({product:'city',source:'dane-milk-farm',unit:'litre',price:110});
  await monthly({product:'city',source:'dane-rice-mill',unit:'unit',price:120});
  await monthly({product:'city',market:'b',price:500,doc:'b'.repeat(64)});
  await db.query("INSERT INTO ingestion_asset(url,kind,document_id,status) VALUES('https://example.invalid/review','monthly',repeat('b',64),'review')");
  for(const region of ['','Uno','Dos','absent']) await options('city',region);
  const result=await options('city'); assert.ok(result.actual.some(row=>row.presentation==='Caja'));
  assert.ok(!result.raw.some(row=>row.requires_revision_resolution));
});
check('ambiguous whitespace labels preserve only actual dated revision winners',async()=>{
  await regional({day:-2,presentation:' Bulto',unit:'Kilogramo',price:10});
  await regional({day:-2,presentation:'Bulto',unit:'Kilogramo',price:20,round:2,doc:'b'.repeat(64)});
  const {raw,actual}=await options('city');
  assert.ok(raw.some(row=>row.requires_revision_resolution));
  assert.deepEqual(actual.map(row=>row.presentation),['Bulto']);
  await classify();
  const result=await quoteModule.filteredProduct('city','',{series:'city',presentation:'Bulto',units:'25 Kilogramo'});
  assert.equal(result.options.presentations.length,1); assert.equal(result.options.presentations[0],'Bulto');
  assert.equal(Number(result.current.price),21);
});
check('package prefilter retains normalized-identity competitors before exact display filtering',async()=>{
  for(const [product,paddedPresentation,paddedUnit]of [
    ['pad-presentation',' Bulto ','Kilogramo'],
    ['pad-unit','Bulto',' Kilogramo '],
    ['pad-both',' Bulto ',' Kilogramo '],
  ]){
    await db.query("INSERT INTO product(id,name,category) VALUES($1,$1,'Frutas')",[product]);
    await regional({product,day:-2,price:10});
    await regional({product,day:-1,price:20}); // Requested display matches this old revision.
    await regional({product,day:-1,price:30,doc:'b'.repeat(64),presentation:paddedPresentation,unit:paddedUnit});
    const {actual:choices}=await options(product);
    for(const choice of choices){
      const result=await quoteModule.filteredProduct(product,'',{series:'city',presentation:choice.presentation,units:choice.units,history:'all'});
      const expected=(await db.query(`WITH quotes AS (${quoteModule.PRICE_QUOTES})
        SELECT observed_on AS date,avg(price) AS price,count(DISTINCT market_id) AS market_count
        FROM quotes WHERE product_id=$1 AND presentation=$2 AND units=$3 AND ${untilToday}
        GROUP BY observed_on ORDER BY observed_on`,[product,choice.presentation,choice.units])).rows;
      assert.deepEqual(result.history,expected,`${product}: ${JSON.stringify(choice)}`);
      // An older matching display must not resurrect a defeated dated revision.
      assert.ok(!result.history.some(row=>Number(row.price)===21));
      assert.deepEqual(result.current,expected.at(-1)||null);
    }
    const canonical=await quoteModule.filteredProduct(product,'',{series:'city',presentation:'Bulto',units:'25 Kilogramo',history:'all'});
    assert.equal(Number(canonical.current.price),11);
  }
});
check('classification preserves corrected stored paths and excludes missing classifications',async()=>{
  await regional({day:-1400}); await classify();
  await db.query("UPDATE regional_classification SET category_path=ARRAY['Frutas','Cítricos corregidos']");
  await regional({day:-1}); // Intentionally missing separately published classification.
  const previous=(await db.query(`SELECT DISTINCT c.category_path FROM regional_classification c JOIN regional_price r USING(document_id,source_locator) WHERE r.product_id=$1 ORDER BY c.category_path`,['city'])).rows;
  const actual=(await db.query(quoteModule.PRODUCT_CLASSIFICATIONS_SQL,['city'])).rows;
  assert.deepEqual(actual,previous); assert.deepEqual(actual,[{category_path:['Frutas','Cítricos corregidos']}]);
});

check('late classification preserves every dated round/revision winner and its literal evidence',async()=>{
  await regional({day:-500,price:10});
  await regional({day:-3,price:20});
  await regional({day:-3,price:30,doc:'b'.repeat(64)});
  await regional({day:-3,price:40,round:2}); // Higher round wins before newer retrieval.
  await regional({day:-1,price:50,round:2});
  await regional({day:-1,price:60,round:2,doc:'b'.repeat(64)});
  await regional({day:-1,price:70,round:2,doc:'b'.repeat(64)}); // Same document: lexical locator tie break.
  await regional({day:-1,price:100,market:'B'});
  await regional({day:-1,price:500,quantity:12.5}); // Distinct package cannot collapse.
  await regional({day:100,price:900});
  await regional({day:-1,market:'Unknown market',price:1000});
  await classify();
  await db.query("UPDATE regional_classification SET category_path=ARRAY['Frutas','Clasificación corregida'] WHERE document_id=repeat('b',64)");
  const oracle=(await db.query(`SELECT * FROM (${quoteModule.PRICE_QUOTES}) q WHERE product_id=$1 ORDER BY observed_on,market_id,units`,['city'])).rows;
  const values=(await db.query(`SELECT * FROM (${quoteModule.PRICE_QUOTE_VALUES}) q WHERE product_id=$1 ORDER BY observed_on,market_id,units`,['city'])).rows;
  const actual=await quoteModule.withQuoteClassifications(values);
  assert.deepEqual(JSON.parse(JSON.stringify(actual)),oracle);
  // Reconstruct the exact SQL winner rather than assuming insertion order equals
  // lexical locator order (row-9 sorts after row-10).
  const latest=oracle.filter(r=>r.market_id==='a'&&r.units==='25 Kilogramo'&&r.document_id==='b'.repeat(64)).at(-1);
  assert.ok(latest.source_locator); assert.ok([61,71].includes(latest.price));
  assert.ok(oracle.some(r=>r.price===41&&r.document_id==='a'.repeat(64)));
  assert.equal(oracle.filter(r=>r.market_name==='Unknown market').length,0);
});

check('filtered history/current/regions match classified SQL oracle while paths use exact current winner',async()=>{
  await regional({day:-500,price:10}); await classify();
  await db.query("UPDATE regional_classification SET category_path=ARRAY['Vieja','Solo histórica']");
  await regional({day:-3,price:20});
  await regional({day:-3,price:30,doc:'b'.repeat(64)});
  await regional({day:-3,price:40,round:2});
  await regional({day:-1,price:50,round:2});
  await regional({day:-1,price:60,round:2,doc:'b'.repeat(64)});
  await db.query(`INSERT INTO regional_classification(document_id,source_locator,category_path)
    SELECT document_id,source_locator,ARRAY['Frutas','Corrección del original'] FROM regional_price
    WHERE document_id=repeat('b',64) AND observed_on=CURRENT_DATE-1`);
  await regional({day:-1,price:100,market:'B'}); // Missing c row falls back to r.category.
  await regional({day:-1,price:500,quantity:12.5});
  await regional({day:100,price:900});
  for(const [region,market,history]of [['','','all'],['Uno','','all'],['','b','all'],['','','recent']]){
    const request={series:'city',presentation:'Bulto',units:'25 Kilogramo',market,history};
    const result=await quoteModule.filteredProduct('city',region,request);
    const filter=`product_id=$1 AND ($2='' OR region=$2) AND series='city' AND presentation='Bulto' AND units='25 Kilogramo' AND ($3='' OR market_id=$3) AND ${history==='all'?untilToday:WINDOW}`;
    const args=['city',region,market];
    const expectedHistory=(await db.query(`WITH q AS (${quoteModule.PRICE_QUOTES}) SELECT observed_on AS date,avg(price) AS price,count(DISTINCT market_id) AS market_count FROM q WHERE ${filter} GROUP BY observed_on ORDER BY observed_on`,args)).rows;
    const expectedMarkets=(await db.query(`WITH q AS (${quoteModule.PRICE_QUOTES}) SELECT DISTINCT ON(market_id) *,market_id AS id,market_name AS name,observed_on AS date FROM q WHERE ${filter} ORDER BY market_id,observed_on DESC`,args)).rows;
    assert.deepEqual(result.history,expectedHistory);
    assert.deepEqual(JSON.parse(JSON.stringify(result.markets)),expectedMarkets);
    assert.deepEqual(result.current,expectedHistory.at(-1));
    if(!region&&!market&&history==='all'){
      assert.deepEqual(result.history.map(r=>Number(r.price)),[11,41,81]);
      assert.deepEqual(JSON.parse(JSON.stringify(result.classification)),[['Frutas','Corrección del original'],['Frutas']]);
      assert.equal(result.markets.find(r=>r.id==='a').document_id,'b'.repeat(64));
    }
    if(history==='recent')assert.equal(result.history.length,2);
  }
});

check('late path lookup preserves stored corrections, missing-path fallback and non-city paths',async()=>{
  await regional({price:10}); await classify();
  await db.query("UPDATE regional_classification SET category_path=ARRAY['Frutas','Cítricos corregidos']");
  await regional({market:'B',price:20});
  await monthly({product:'city',price:100});
  const expected=(await db.query(`SELECT * FROM (${quoteModule.PRICE_QUOTES}) q WHERE product_id='city' ORDER BY series,market_id`)).rows;
  const raw=(await db.query(`SELECT * FROM (${quoteModule.PRICE_QUOTE_VALUES}) q WHERE product_id='city' ORDER BY series,market_id`)).rows;
  assert.notDeepEqual(raw,expected);
  const actual=await quoteModule.withQuoteClassifications(raw);
  assert.deepEqual(JSON.parse(JSON.stringify(actual)),expected);
  assert.deepEqual(actual.find(r=>r.series==='city'&&r.market_id==='a').category_path,['Frutas','Cítricos corregidos']);
  assert.deepEqual(actual.find(r=>r.series==='city'&&r.market_id==='b').category_path,['Frutas']);
  assert.deepEqual(actual.find(r=>r.series==='monthly').category_path,['Frutas']);
});

check('asset and locator reviews stay excluded from current prices, history and options',async()=>{
  await monthly({product:'milk',source:'dane-milk-farm',unit:'litre',price:1700});
  await monthly({product:'milk',market:'b',source:'dane-milk-farm',unit:'litre',price:3000,doc:'b'.repeat(64)});
  await monthly({product:'milk',market:'a',month:2,source:'dane-milk-farm',unit:'litre',price:9999});
  await db.query("UPDATE price_observation SET source_locator='reviewed-old-cell' WHERE price=9999");
  await db.query(`INSERT INTO price_observation_review(document_id,source_locator,product_id,market_id,source_id,observed_on,period,unit,reason)
    SELECT document_id,source_locator,product_id,market_id,source_id,observed_on,period,unit,'Exact original identity invalid' FROM price_observation WHERE price=9999`);
  await db.query("INSERT INTO ingestion_asset(url,kind,document_id,status) VALUES('https://example.invalid/milk-review','milk',repeat('b',64),'review')");
  const actual=await quoteModule.filteredProduct('milk','',{series:'farmgate',units:'1 litro',history:'all'});
  assert.equal(actual.history.length,1);assert.equal(actual.markets.length,1);assert.equal(Number(actual.current.price),1700);
  assert.deepEqual(JSON.parse(JSON.stringify(actual.options.markets.map(r=>r.id))),['a']);
  assert.deepEqual(JSON.parse(JSON.stringify(actual.classification)),[['Lácteos']]);
});
check('monthly litre/rice and city package detail prices and explicit filters remain exact',async()=>{
  await monthly({product:'milk',source:'dane-milk-farm',unit:'litre',price:1700});
  await monthly({product:'rice',source:'dane-rice-mill',unit:'kg',price:2200});
  await regional({price:100,day:-1}); await regional({price:200,day:-1,market:'B'}); await classify();
  for(const [id,series,units,price,count] of [['milk','farmgate','1 litro',1700,1],['rice','mill','1 kg',2200,1],['city','city','25 Kilogramo',151,2]]) {
    const result=await quoteModule.filteredProduct(id,'',{series,units,presentation:series==='city'?'Bulto':'Por unidad de medida'});
    assert.equal(Number(result.current.price),price); assert.equal(result.markets.length,count);
    assert.equal(result.filters.series,series); assert.equal(result.filters.units,units);
  }
  assert.equal(await quoteModule.filteredProduct('absent','',{}),null);
});
