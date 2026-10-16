/* Actual SQL parity against the published view; private local PostgreSQL only.
 * Run through artifacts/.../official-reference-date-seek/run_local_postgres.py.
 */
const { test, beforeEach, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { Client } = require('pg');
const source = fs.readFileSync(path.join(__dirname, '../../../pipelines/ingestion/official_catalog.py'), 'utf8');
const sql = source.split('LATEST_FOR_KEYS_SQL = \"\"\"')[1].split('\"\"\"')[0].replace('%s', '$1');
const schema = fs.readFileSync(path.join(__dirname, '../../../pipelines/ingestion/schema.sql'), 'utf8');
const view = schema.split('CREATE OR REPLACE VIEW published_official_price AS')[1].split('GRANT SELECT ON published_official_price')[0];
const frontend = fs.readFileSync(path.join(__dirname, '../src/lib/server/official-references.ts'), 'utf8');
const historySql = frontend.split('export const OFFICIAL_REFERENCE_HISTORY_SQL = `')[1].split('`;')[0];
const socket = process.env.AGRO_REFERENCE_TEST_SOCKET;
const unified = Boolean(socket?.startsWith('/tmp/agro-unified-catalog-pg-'));
const enabled = Boolean(unified || socket?.startsWith('/tmp/agro-reference-pg-'));
let db;
const hash = (label) => crypto.createHash('sha256').update(label).digest('hex');
const tables = ['source_document', 'official_price_quote', 'official_source_review', 'ingestion_asset'];
beforeEach(async () => {
  if (!enabled) return;
  db = new Client({ host: socket, port: unified ? 65443 : 65440, database: 'postgres' });
  await db.connect();
  await db.query("SET search_path=pg_temp; SET statement_timeout='12s'");
  for (const table of tables) {
    await db.query(`CREATE TEMP TABLE ${table} (LIKE public.${table} INCLUDING ALL)`);
    assert.equal((await db.query('SELECT relpersistence FROM pg_class WHERE oid=to_regclass($1)', [table])).rows[0].relpersistence, 't');
  }
  await db.query('CREATE INDEX official_quote_identity ON official_price_quote(quote_key,observed_on DESC)');
  await db.query('CREATE INDEX official_quote_history_cover ON official_price_quote(quote_key,observed_on DESC) INCLUDE(document_id,source_locator,parser_version,parsed_at,series)');
  await db.query('CREATE INDEX ingestion_asset_document ON ingestion_asset(document_id)');
  await db.query('CREATE TEMP VIEW published_official_price AS ' + view);
});
afterEach(async () => { if (db) await db.end(); db = undefined; });
const check = (name, fn) => test(name, { skip: !enabled && 'Requires isolated PostgreSQL runner' }, fn);
async function document(label, retrieved = '2026-09-20T12:00:00Z') {
  const id = hash(label);
  await db.query(`INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content,retrieved_at)
    VALUES($1,$2,'DANE',$3,'application/pdf','original','',decode('00','hex'),$4) ON CONFLICT DO NOTHING`,
  [id, label, 'https://example.invalid/' + label + '.pdf', retrieved]);
  return id;
}
async function quote(doc, key, day, price, extra = {}) {
  const { locator = key + ':' + day, parsed = '2026-09-23T12:00:00Z', version = 'v1' } = extra;
  await db.query(`INSERT INTO official_price_quote(document_id,source_locator,parser_version,quote_key,product_id,product_name,category,publisher,series,basis,currency,unit,market,observed_on,price,min_price,max_price,parsed_at,details)
    VALUES($1,$2,$3,$4,$5,$5,'Frutas','Official fixture','market-reference','Precio por caja','COP','caja','Mercado literal',$6,$7,$8,$9,$10,$11)`,
  [doc, locator, version, hash(key), key, day, price, price - 1, price + 1, parsed, { fixture: true, presentation: 'Caja 20 kg' }]);
}
async function review(doc, locator, created = '2026-09-24T12:00:00Z') {
  await db.query("INSERT INTO official_source_review VALUES($1,$2,'review-v1','{}','Unreadable label',$3)", [doc, locator, created]);
}
async function asset(doc, day) {
  await db.query("INSERT INTO ingestion_asset(url,kind,document_id,observed_on,status) VALUES($1,'colombia-pork-pdf',$2,$3,'review')", ['https://example.invalid/' + crypto.randomUUID(), doc, day]);
}
async function equivalent() {
  const keys = (await db.query('SELECT DISTINCT quote_key FROM official_price_quote')).rows.map((row) => row.quote_key);
  const actual = (await db.query(sql, [keys])).rows.sort((a, b) => a.quote_key.localeCompare(b.quote_key));
  const expected = (await db.query(`SELECT * FROM (
    SELECT p.*,d.source_url,lead(p.price) OVER(PARTITION BY p.quote_key ORDER BY p.observed_on DESC) AS previous_price,
      row_number() OVER(PARTITION BY p.quote_key ORDER BY p.observed_on DESC) AS rank
    FROM published_official_price p JOIN source_document d ON d.id=p.document_id
    WHERE p.observed_on <= (CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date
  ) ranked WHERE rank=1 ORDER BY quote_key`)).rows.map(({ rank, ...row }) => row);
  assert.deepEqual(actual, expected);
  for (const key of keys) {
    const history = (await db.query(historySql, [key])).rows;
    const old = (await db.query(`SELECT q.*,d.source_url FROM published_official_price q
      JOIN source_document d ON d.id=q.document_id WHERE quote_key=$1
        AND observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date ORDER BY observed_on`, [key])).rows;
    assert.deepEqual(history, old, 'All historical values, dimensions and provenance match the published view');
  }
  return actual;
}
check('history supersession sees a later parse even when its corrected quote identity changes', async () => {
  const doc = await document('identity-correction');
  await quote(doc, 'wrong-name', '2026-09-25', 100, {locator:'same printed cell'});
  await quote(doc, 'correct-name', '2026-09-25', 100, {locator:'same printed cell',version:'v2',parsed:'2026-09-24T12:00:00Z'});
  await equivalent();
  assert.deepEqual((await db.query(historySql,[hash('wrong-name')])).rows,[]);
  const corrected = (await db.query(historySql,[hash('correct-name')])).rows;
  assert.equal(corrected.length,1);assert.equal(corrected[0].parser_version,'v2');
  assert.equal((await db.query('SELECT count(*) FROM official_price_quote')).rows[0].count,'2');
});
check('history preserves milk bulletin precedence over a later download of an older bulletin', async () => {
  const newer = await document('June milk','2026-09-08T00:00:00Z');
  const older = await document('May milk','2026-09-10T00:00:00Z');
  await quote(newer,'milk','2026-05-31',2110);
  await quote(older,'milk','2026-05-31',2000);
  await db.query("UPDATE source_document SET reference_period=CASE WHEN id=$1 THEN '2026-06-30' ELSE '2026-05-31' END WHERE id=ANY($2::text[])",[newer,[newer,older]]);
  await db.query("UPDATE official_price_quote SET series='dane-milk-macroregion',unit='litro',basis='Promedio mensual publicado en finca por macrorregión',details=jsonb_build_object('bulletin_period',CASE WHEN document_id=$1 THEN '2026-06-30' ELSE '2026-05-31' END)",[newer]);
  await equivalent();
  const [row] = (await db.query(historySql,[hash('milk')])).rows;
  assert.equal(row.price,'2110');assert.equal(row.document_id,newer);assert.equal(row.unit,'litro');
});
check('date takes precedence over retrieval date; previous price uses a distinct observed date', async () => {
  const earlier = await document('earlier', '2026-09-20T12:00:00Z');
  const later = await document('later', '2026-09-26T12:00:00Z');
  await quote(earlier, 'cacao', '2026-09-25', 16000);
  await quote(later, 'cacao', '2026-09-25', 17000);
  await quote(later, 'cacao', '2026-09-24', 15000);
  await quote(later, 'cacao', '2026-09-10', 19000);
  const [row] = await equivalent();
  assert.equal(row.price, '17000'); assert.equal(row.previous_price, '15000');
  assert.equal(row.document_id, later);
});
check('same-date winners preserve original retrieval, parser timestamp and locator tie ordering', async () => {
  const old = await document('old', '2026-09-20T00:00:00Z');
  const recent = await document('recent', '2026-09-25T00:00:00Z');
  await quote(old, 'pork', '2026-09-24', 9000, { parsed: '2026-09-26T12:00:00Z' });
  await quote(recent, 'pork', '2026-09-24', 10000, { locator: 'a', parsed: '2026-09-24T12:00:00Z' });
  await quote(recent, 'pork', '2026-09-24', 11000, { locator: 'b', parsed: '2026-09-25T12:00:00Z' });
  await quote(recent, 'pork', '2026-09-24', 12000, { locator: 'a', version: 'v2', parsed: '2026-09-25T12:00:00Z' });
  const [row] = await equivalent();
  assert.equal(row.price, '12000'); assert.equal(row.source_locator, 'a'); assert.equal(row.previous_price, null);
});
check('whole-document and matching-date asset reviews fall back to eligible dates', async () => {
  const whole = await document('whole'); const dated = await document('dated'); const valid = await document('valid');
  await quote(whole, 'palm', '2026-09-25', 9000); await asset(whole, null);
  await quote(dated, 'palm', '2026-09-24', 8000); await quote(dated, 'palm', '2026-09-23', 7000); await asset(dated, '2026-09-24');
  await quote(valid, 'palm', '2026-09-22', 6000);
  const [row] = await equivalent(); assert.equal(row.price, '7000'); assert.equal(row.previous_price, '6000');
});
check('later or equal source review withdraws a parse; a corrected later parse is eligible', async () => {
  const doc = await document('reviewed');
  await quote(doc, 'coffee', '2026-09-25', 12000, { locator: 'current' });
  await review(doc, 'current');
  await quote(doc, 'coffee', '2026-09-24', 10000, { locator: 'equal', parsed: '2026-09-24T12:00:00Z' });
  await review(doc, 'equal');
  await quote(doc, 'coffee', '2026-09-23', 9000);
  assert.equal((await equivalent())[0].price, '9000');
  await quote(doc, 'coffee', '2026-09-25', 12500, { locator: 'current', version: 'corrected', parsed: '2026-09-26T12:00:00Z' });
  const [row] = await equivalent(); assert.equal(row.price, '12500'); assert.equal(row.previous_price, '9000');
});
check('future-only and fully reviewed identities disappear; future revisions cannot replace current quotes', async () => {
  const doc = await document('future');
  await quote(doc, 'only-future', '2999-12-31', 10);
  await quote(doc, 'current', '2999-12-31', 2); await quote(doc, 'current', '2026-09-25', 3);
  await quote(doc, 'all-reviewed', '2026-09-25', 4); await review(doc, 'all-reviewed:2026-09-25');
  const rows = await equivalent(); assert.equal(rows.length, 1); assert.equal(rows[0].price, '3'); assert.equal(rows[0].previous_price, null);
});
check('long histories and unrelated reviews keep identical values without a full-history revision sort', async () => {
  const old = await document('history-old', '2026-09-20T12:00:00Z');
  const recent = await document('history-recent', '2026-09-25T12:00:00Z');
  await db.query(`INSERT INTO official_price_quote(document_id,source_locator,parser_version,quote_key,product_id,product_name,category,publisher,series,basis,currency,unit,market,observed_on,price)
    SELECT CASE WHEN revision=1 THEN $1 ELSE $2 END, key::text||':'||day::text,'v1',lpad(key::text,64,'0'),key::text,key::text,'Frutas','fixture','daily','Precio kg','COP','kg','Bogotá',DATE '2020-01-01'+day,day+revision
    FROM generate_series(1,30) key CROSS JOIN generate_series(1,1000) day CROSS JOIN generate_series(1,2) revision`, [old, recent]);
  await db.query(`INSERT INTO official_source_review SELECT $1,'unrelated:'||n::text,'review-v1','{}','Test unrelated review',now() FROM generate_series(1,1000) n`, [old]);
  await db.query('ANALYZE official_price_quote; ANALYZE official_source_review; ANALYZE ingestion_asset');
  const rows = await equivalent(); assert.equal(rows.length, 30); assert.ok(rows.every((row) => row.price === '1002' && row.previous_price === '1001'));
  const keys = (await db.query('SELECT DISTINCT quote_key FROM official_price_quote')).rows.map((row) => row.quote_key);
  const plan = (await db.query('EXPLAIN (ANALYZE,FORMAT JSON) ' + sql, [keys])).rows[0]['QUERY PLAN'][0];
  function inspect(node) {
    if (node['Node Type'].includes('Sort')) {
      assert.ok(node['Actual Rows'] <= 2, 'Only same-date revisions should be sorted');
      // A bounded one/two-row revision sort may retain observed_on in its
      // keys. The row bound, not that harmless key, detects a history-wide sort.
    }
    for (const child of node.Plans || []) inspect(child);
  }
  inspect(plan.Plan);
  const oneKey = keys[0];
  const historyPlan = (await db.query('EXPLAIN (ANALYZE,FORMAT JSON) ' + historySql, [oneKey])).rows[0]['QUERY PLAN'][0];
  function inspectHistory(node) {
    if (node['Node Type'].includes('Sort'))
      assert.ok(node['Actual Rows'] <= 2000, 'History sorting stays within the selected identity, not all 60,000 source rows');
    if (node['Relation Name'] === 'official_source_review')
      assert.ok(node['Actual Rows'] <= 1, 'Review checks seek exact document/locator rather than scanning unrelated reviews');
    for (const child of node.Plans || []) inspectHistory(child);
  }
  inspectHistory(historyPlan.Plan);
});
check('frontend reads only clean current payloads, excluding tombstones and future dates', async () => {
  const frontend = fs.readFileSync(path.join(__dirname, '../src/lib/server/official-references.ts'), 'utf8');
  const readSql = frontend.split('export const LATEST_OFFICIAL_REFERENCES_SQL = `')[1].split('`;')[0];
  await db.query('CREATE TEMP TABLE official_catalog_current(quote_key text PRIMARY KEY,payload jsonb,dirty boolean,version text)');
  const valid = { quote_key: hash('read-model'), observed_on: '2026-09-25', price: 16000, previous_price: 15000 };
  for (const [key, payload, dirty, version] of [
    ['valid', valid, false, 'official-catalog-v1'],
    ['dirty', valid, true, 'official-catalog-v1'],
    ['withdrawn', null, false, 'official-catalog-v1'],
    ['old-version', valid, false, 'old-version'],
    ['future', { ...valid, observed_on: '2999-01-01' }, false, 'official-catalog-v1'],
  ]) await db.query('INSERT INTO official_catalog_current VALUES($1,$2,$3,$4)', [key, payload, dirty, version]);
  assert.deepEqual((await db.query(readSql)).rows, [{ payload: valid }]);
  assert.ok(!readSql.includes('official_price_quote'));
});

check('retained parser revisions resolve each printed cell before indexed supersession checks', async () => {
  const doc = await document('eight-worldbank-revisions');
  const key = hash('monthly-reference');
  await db.query(`INSERT INTO official_price_quote(document_id,source_locator,parser_version,quote_key,product_id,product_name,category,publisher,series,basis,currency,unit,market,observed_on,price,parsed_at)
    SELECT $1,'cell:'||month,'v'||revision,$2,'reference','Reference','Frutas','fixture','international-monthly','Monthly reference','USD','t','International',
      (DATE '1959-12-31'+month*INTERVAL '1 month')::date,month+revision,
      TIMESTAMPTZ '2026-09-01 12:00:00Z'+revision*INTERVAL '1 day'
    FROM generate_series(1,800) month CROSS JOIN generate_series(1,8) revision`, [doc,key]);
  await db.query('ANALYZE official_price_quote');
  const actual = (await db.query(historySql,[key])).rows;
  const expected = (await db.query(`SELECT q.*,d.source_url FROM published_official_price q
    JOIN source_document d ON d.id=q.document_id WHERE quote_key=$1
    AND observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date ORDER BY observed_on`,[key])).rows;
  assert.deepEqual(actual,expected);
  assert.equal(actual.length,800);
  assert.ok(actual.every(row=>row.parser_version==='v8'));
  const plan = (await db.query('EXPLAIN (ANALYZE,FORMAT JSON) '+historySql,[key])).rows[0]['QUERY PLAN'][0];
  const supersession=[];
  function inspect(node) {
    if(node['Relation Name']==='official_price_quote' && /parsed_at >/.test(node['Index Cond']||''))
      supersession.push(node);
    for(const child of node.Plans||[])inspect(child);
  }
  inspect(plan.Plan);
  assert.ok(supersession.length,'Supersession retains an indexed lookup');
  assert.ok(supersession.every(node=>node['Actual Loops']<=800),'Only the current800 printed cells need a newer-revision lookup');
  assert.equal((await db.query('SELECT count(*) FROM official_price_quote')).rows[0].count,'6400','All historical parser evidence remains retained');
});

check('overlapping retained originals check eligibility per date and fall back from a reviewed first choice', async () => {
  const key=hash('overlapping-agronet-history');
  const docs=[];
  for(let n=0;n<54;n++) docs.push(await document(`overlapping-${n}`,new Date(Date.UTC(2026,7,1+n)).toISOString()));
  await db.query(`INSERT INTO official_price_quote(document_id,source_locator,parser_version,quote_key,product_id,product_name,category,publisher,series,basis,currency,unit,market,observed_on,price,parsed_at)
    SELECT doc,'printed:'||day,'v'||revision,$2,'cacao','Cacao','Procesados','Agronet','colombia-agronet','Precio por kg','COP','kg','Colombia',
      DATE '2021-01-01'+day,ordinality*100+day+revision,TIMESTAMPTZ '2026-09-01 12:00:00Z'+revision*INTERVAL '1 day'
    FROM unnest($1::text[]) WITH ORDINALITY AS documents(doc,ordinality)
    CROSS JOIN generate_series(1,265) day CROSS JOIN generate_series(1,2) revision`,[docs,key]);
  await review(docs.at(-1),'printed:265');
  await db.query('ANALYZE official_price_quote; ANALYZE official_source_review');
  await equivalent();
  const rows=(await db.query(historySql,[key])).rows;
  assert.equal(rows.length,265);
  assert.equal(rows.at(-1).document_id,docs.at(-2),'A reviewed latest original falls back to its eligible predecessor');
  assert.ok(rows.slice(0,-1).every(row=>row.document_id===docs.at(-1)));
  const plan=(await db.query('EXPLAIN (ANALYZE,FORMAT JSON) '+historySql,[key])).rows[0]['QUERY PLAN'][0];
  const checks=[];
  function inspect(node){
    if(['official_price_quote','official_source_review','ingestion_asset'].includes(node['Relation Name']) &&
       node['Actual Loops']>1 && !/milk/.test(node.Alias||'')) checks.push(node);
    for(const child of node.Plans||[])inspect(child);
  }
  inspect(plan.Plan);
  assert.ok(checks.length);
  assert.ok(checks.every(node=>node['Actual Loops']<=266),'Only the winning source or its reviewed fallback needs an eligibility check per date');
  assert.equal((await db.query('SELECT count(*) FROM official_price_quote')).rows[0].count,'28620','All overlapping source revisions remain retained');
});
