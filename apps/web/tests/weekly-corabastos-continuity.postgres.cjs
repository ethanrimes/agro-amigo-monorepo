/* Source-oracle fixtures and real publication SQL in isolated TEMP PostgreSQL. */
const { test, beforeEach, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const { Client, types } = require('pg');
types.setTypeParser(1700, Number);
types.setTypeParser(1082, value => value);
const oracle = require('./fixtures/weekly-corabastos-source-oracle.json');
const eggOracle = require('./fixtures/weekly-corabastos-eggs-source-oracle.json');
const source = fs.readFileSync(path.join(__dirname, '../src/lib/server/official-references.ts'), 'utf8');
const sql = source.split('export const OFFICIAL_REFERENCE_HISTORY_SQL = `')[1].split('`;')[0];
const helper = { exports: {}, require: name => require(name) };
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,
  '../src/lib/server/weekly-corabastos-continuity.ts'), 'utf8'), { compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
} }).outputText, helper);
const { weeklyCorabastosGroups, mergeWeeklyCorabastosHistory,
  WEEKLY_CORABASTOS_CANONICAL_MARKET: canonicalMarket } = helper.exports;
const socket = process.env.AGRO_REFERENCE_TEST_SOCKET;
const unified = Boolean(socket?.startsWith('/tmp/agro-unified-catalog-pg-'));
const enabled = Boolean(unified || socket?.startsWith('/tmp/agro-reference-pg-'));
const check = (name, fn) => test(name, { skip: !enabled && 'Requires isolated PostgreSQL' }, fn);
let db;
beforeEach(async () => {
  if (!enabled) return;
  db = new Client({ host: socket, port: unified ? 65443 : 65440, database: 'postgres' });
  await db.connect();
  await db.query("SET search_path=pg_temp; SET statement_timeout='12s'");
  for (const table of ['source_document','official_price_quote','official_source_review','ingestion_asset'])
    await db.query(`CREATE TEMP TABLE ${table} (LIKE public.${table} INCLUDING ALL)`);
  await db.query('CREATE INDEX quote_date ON official_price_quote(quote_key,observed_on DESC)');
});
afterEach(async () => { if (db) await db.end(); db = undefined; });

const cards = oracle.products.flatMap(product => product.keys.map(entry => ({
  quote_key: entry.key, market: entry.market, product_id: product.product_id,
  product_name: product.product_name, publisher: oracle.publisher,
  series: 'dane-weekly', basis: oracle.basis, currency: oracle.currency,
  unit: oracle.unit, observed_on: '2026-10-02', price: 1000,
  min_price: 900, max_price: 1100, previous_price: null,
  details: { identity_dimensions: { source_product: product.product_name } },
})));

async function insert(product, example, label = '') {
  const document = label ? require('node:crypto').createHash('sha256').update(label).digest('hex') : example.document_id;
  await db.query(`INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content,retrieved_at)
    VALUES($1,$2,'DANE',$3,$5,'original',$4,decode('00','hex'),'2026-10-02T12:00:00Z')
    ON CONFLICT DO NOTHING`,[document, product.product_name+label,
    'https://www.dane.gov.co/weekly/'+document+(product.unit==='unit'?'.xlsx':'.pdf'), example.date,
    product.unit==='unit'?'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':'application/pdf']);
  await db.query(`INSERT INTO official_price_quote(document_id,source_locator,parser_version,quote_key,
    product_id,product_name,category,publisher,series,basis,currency,unit,market,observed_on,
    price,min_price,max_price,source_page,parsed_at,details)
    VALUES($1,$2,'dane-weekly-v19',$3,$4,$5,'Verduras y hortalizas','DANE · SIPSA',
      'dane-weekly','Precio mayorista semanal','COP',$13,$6,$7,$8,$9,$10,$11,
      '2026-10-02T12:00:00Z',$12)`,[document,example.source_locator+label,example.key,
    product.product_id,product.product_name,example.market,example.date,
    example.price,example.min,example.max,example.source_page,
    { identity_dimensions: { source_product: product.product_name } },product.unit||'kg']);
  return { document, locator: example.source_locator+label };
}

async function selected(group) {
  await db.query('BEGIN READ ONLY ISOLATION LEVEL REPEATABLE READ');
  const rows=[];
  try {
    for (const key of group.keys) rows.push(...(await db.query(sql,[key])).rows);
    await db.query('COMMIT');
  } catch (error) { await db.query('ROLLBACK'); throw error; }
  return rows;
}

check('two original-backed products remain separate, preserve 2012/2017/2018/2022 native cells and exact old keys', async () => {
  const groups=weeklyCorabastosGroups(cards);
  assert.equal(groups.groups.length,2);
  for (const product of oracle.products) for (const example of product.source_examples)
    await insert(product,example);
  for (const product of oracle.products) {
    const group=groups.byKey.get(product.keys[0].key);
    const raw=await selected(group);
    const merged=mergeWeeklyCorabastosHistory(group,raw);
    assert.equal(raw.length,4);
    assert.equal(merged.length,4);
    assert.ok(merged.every(row=>row.quote_key===group.canonicalKey && row.product_id===product.product_id));
    for (const example of product.source_examples) {
      const row=merged.find(item=>item.observed_on===example.date);
      assert.deepEqual([row.min_price,row.max_price,row.price], [example.min,example.max,example.price]);
      assert.equal(row.document_id,example.document_id);
      assert.equal(row.source_locator,example.source_locator);
    }
  }
  assert.equal((await db.query('SELECT count(*) FROM official_price_quote')).rows[0].count,'8');
});

check('exact same-date counterpart dedupes with both originals; review withdraws only the reviewed cell', async () => {
  const product=oracle.products[0], group=weeklyCorabastosGroups(cards).byKey.get(product.keys[0].key);
  const source=product.source_examples.find(item=>item.date==='2022-06-24');
  await insert(product,source);
  const canonical=product.keys.find(item=>item.market===canonicalMarket);
  const counterpart={...source,key:canonical.key,market:canonical.market,
    source_locator:'PDF page 9,table 1,column 1,line 21',source_page:9};
  const other=await insert(product,counterpart,'same-date-official-pdf');
  const merged=mergeWeeklyCorabastosHistory(group,await selected(group));
  assert.equal(merged.length,1);
  assert.equal(merged[0].details.alternate_originals.length,1);
  assert.equal(merged[0].details.alternate_originals[0].document_id,source.document_id);
  await db.query(`INSERT INTO official_source_review(document_id,source_locator,parser_version,record,reason,created_at)
    VALUES($1,$2,'dane-weekly-v19','{}','Contradictory original','2026-10-03T12:00:00Z')`,
  [other.document,other.locator]);
  const after=mergeWeeklyCorabastosHistory(group,await selected(group));
  assert.equal(after.length,1);
  assert.equal(after[0].document_id,source.document_id);
  assert.equal((await db.query('SELECT count(*) FROM official_price_quote')).rows[0].count,'2');
  assert.equal((await db.query('SELECT count(*) FROM source_document')).rows[0].count,'2');
});

check('cross-spelling same-date monetary conflict fails closed while raw originals remain intact', async () => {
  const product=oracle.products[1],group=weeklyCorabastosGroups(cards).byKey.get(product.keys[0].key);
  const source=product.source_examples.find(item=>item.date==='2022-06-24');
  await insert(product,source);
  const canonical=product.keys.find(item=>item.market===canonicalMarket);
  await insert(product,{...source,key:canonical.key,market:canonical.market,price:source.price+1,
    source_locator:'PDF page 9,table 1,column 2,line 20',source_page:9},'changed-price');
  const raw=await selected(group);
  assert.equal(raw.length,2);
  assert.throws(()=>mergeWeeklyCorabastosHistory(group,raw),/WEEKLY_CORABASTOS_PRICE_CONFLICT/);
  assert.equal((await db.query('SELECT count(*) FROM official_price_quote')).rows[0].count,'2');
});

check('four audited red-egg grades publish as separate COP/unit histories under their old and canonical keys', async () => {
  const eggCards=eggOracle.products.flatMap(product=>product.source_examples.map(example=>({
    quote_key:example.key,market:example.market,product_id:product.product_id,
    product_name:product.product_name,publisher:'DANE · SIPSA',series:'dane-weekly',
    basis:'Precio mayorista semanal',currency:'COP',unit:'unit',observed_on:example.date,
    price:example.price,min_price:example.min,max_price:example.max,previous_price:null,
    details:{identity_dimensions:{source_product:product.product_name}},
  })));
  const groups=weeklyCorabastosGroups(eggCards);
  assert.equal(groups.groups.length,4);
  for (const product of eggOracle.products) for (const example of product.source_examples)
    await insert(product,example);
  for (const product of eggOracle.products) {
    const group=groups.byKey.get(product.source_examples[0].key);
    const raw=await selected(group), merged=mergeWeeklyCorabastosHistory(group,raw);
    assert.equal(raw.length,2);
    assert.equal(merged.length,2);
    assert.ok(merged.every(row=>row.unit==='unit' && row.product_id===product.product_id));
    for (const example of product.source_examples) {
      const row=merged.find(item=>item.observed_on===example.date);
      assert.deepEqual([row.min_price,row.max_price,row.price],[example.min,example.max,example.price]);
      assert.equal(row.document_id,example.document_id);
    }
  }
  assert.equal((await db.query('SELECT count(*) FROM official_price_quote')).rows[0].count,'8');
});
