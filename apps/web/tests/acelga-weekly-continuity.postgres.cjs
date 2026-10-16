/* Run with the isolated PostgreSQL runner in the Acelga QA artifact. */
const { test, beforeEach, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const vm = require('node:vm');
const ts = require('typescript');
const { Client, types } = require('pg');
types.setTypeParser(1700, Number);
types.setTypeParser(1082, value => value);

const frontend = fs.readFileSync(path.join(__dirname, '../src/lib/server/official-references.ts'), 'utf8');
const ordinary = frontend.split('export const OFFICIAL_REFERENCE_HISTORY_SQL = `')[1].split('`;')[0];
assert.ok(ordinary.includes('FROM official_price_quote WHERE quote_key=$1'));
assert.ok(frontend.includes('for (const key of ACELGA_WEEKLY_KEYS)'),
  'The grouped route must use bounded one-key publication seeks');
assert.ok(frontend.includes('BEGIN READ ONLY ISOLATION LEVEL REPEATABLE READ'),
  'Five identities must be selected from one stable source snapshot');
const helper = fs.readFileSync(path.join(__dirname, '../src/lib/server/acelga-weekly-continuity.ts'), 'utf8');
const scope = { exports: {}, require: () => { throw Error('Unexpected helper runtime dependency'); } };
vm.runInNewContext(ts.transpileModule(helper, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
} }).outputText, scope);
const { ACELGA_WEEKLY_KEYS: keys, ACELGA_WEEKLY_MARKETS: markets,
  ACELGA_WEEKLY_CANONICAL_KEY: canonical, mergeAcelgaWeeklyHistory,
  collapseAcelgaWeeklyCatalog, isAcelgaWeeklyKey } = scope.exports;
const socket = process.env.AGRO_REFERENCE_TEST_SOCKET;
const unified = Boolean(socket?.startsWith('/tmp/agro-unified-catalog-pg-'));
const enabled = Boolean(unified || socket?.startsWith('/tmp/agro-reference-pg-'));
const check = (name, fn) => test(name, { skip: !enabled && 'Requires isolated PostgreSQL' }, fn);
let db;
const hash = label => crypto.createHash('sha256').update(label).digest('hex');

beforeEach(async () => {
  if (!enabled) return;
  db = new Client({ host: socket, port: unified ? 65443 : 65440, database: 'postgres' });
  await db.connect();
  await db.query("SET search_path=pg_temp; SET statement_timeout='12s'");
  for (const table of ['source_document', 'official_price_quote', 'official_source_review', 'ingestion_asset'])
    await db.query(`CREATE TEMP TABLE ${table} (LIKE public.${table} INCLUDING ALL)`);
  await db.query('CREATE INDEX quote_date ON official_price_quote(quote_key,observed_on DESC)');
  await db.query('CREATE INDEX review_doc ON official_source_review(document_id,source_locator)');
});
afterEach(async () => { if (db) await db.end(); db = undefined; });

async function insert(key, date, price, label, options = {}) {
  const document = hash(label);
  const locator = 'PDF page 4, Cuadro 1, ' + label;
  await db.query(`INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content,retrieved_at)
    VALUES($1,$2,'DANE',$3,'application/pdf','original',$4,decode('00','hex'),'2026-10-02T12:00:00Z')`,
  [document, label, 'https://www.dane.gov.co/' + label + '.pdf', date]);
  await db.query(`INSERT INTO official_price_quote(document_id,source_locator,parser_version,quote_key,
    product_id,product_name,category,publisher,series,basis,currency,unit,market,observed_on,
    price,min_price,max_price,source_page,parsed_at,details)
    VALUES($1,$2,'weekly-v19',$3,'acelga','Acelga','Verduras y hortalizas','DANE · SIPSA',
      'dane-weekly','Precio mayorista semanal','COP','kg',$4,$5,$6,$7,$8,4,'2026-10-02T12:00:00Z',$9)`,
  [document, locator, key, markets[key], date, price, options.min ?? price - 10,
    options.max ?? price + 10, { identity_dimensions: { source_product: 'Acelga' } }]);
  return { document, locator };
}
const history = async () => {
  const rows = [];
  historyKeys.length = 0;
  await db.query('BEGIN READ ONLY ISOLATION LEVEL REPEATABLE READ');
  try {
    for (const key of keys) {
      historyKeys.push(key);
      rows.push(...(await db.query(ordinary, [key])).rows);
    }
    await db.query('COMMIT');
  } catch (error) { await db.query('ROLLBACK'); throw error; }
  return rows;
};
const historyKeys = [];

check('five exact original identities publish one bookmark history with same-date alternate evidence', async () => {
  const [old2012, old2017, , old2018, old2022] = keys;
  await insert(old2012, '2012-06-22', 793, 'weekly-2012', { min: 767, max: 800 });
  await insert(old2017, '2017-05-19', 463, 'weekly-2017', { min: 400, max: 600 });
  await insert(canonical, '2017-09-01', 576, 'weekly-2017-later', { min: 400, max: 1000 });
  const alternate = await insert(old2018, '2018-03-09', 558, 'weekly-2018', { min: 400, max: 700 });
  await insert(canonical, '2018-03-09', 558, 'weekly-2018-annex', { min: 400, max: 700 });
  await insert(old2022, '2022-06-24', 1358, 'weekly-2022', { min: 867, max: 1667 });
  await insert(canonical, '2026-10-02', 433, 'weekly-current');
  const raw = await history();
  assert.deepEqual(Array.from(historyKeys), Array.from(keys),
    'Every original ID is supplied as an exact SQL parameter');
  assert.equal(raw.length, 7);
  const merged = mergeAcelgaWeeklyHistory(raw);
  assert.deepEqual(Array.from(merged, row => row.observed_on), [
    '2012-06-22', '2017-05-19', '2017-09-01', '2018-03-09', '2022-06-24', '2026-10-02']);
  assert.ok(merged.every(row => row.quote_key === canonical));
  assert.equal(merged[3].details.alternate_originals[0].document_id, alternate.document);
  assert.equal(merged[3].details.alternate_originals[0].source_locator, alternate.locator);
  assert.equal(merged[3].details.alternate_originals[0].source_page, 4);
  assert.equal((await db.query('SELECT count(*) FROM official_price_quote')).rows[0].count, '7');
  const cards = raw.map(row => ({ ...row, previous_price: null }));
  const collapsed = collapseAcelgaWeeklyCatalog(cards, raw);
  assert.equal(collapsed.length, 1);
  assert.equal(collapsed[0].quote_key, canonical);
  assert.equal(collapsed[0].previous_price, 1358);
  assert.ok(keys.every(isAcelgaWeeklyKey), 'Every original bookmark enters the grouped branch');
  assert.equal(new Set(keys.map(key => isAcelgaWeeklyKey(key) ? canonical : key)).size, 1,
    'All old IDs resolve to the canonical cache identity');
});

check('a reviewed latest original falls back; raw quote and document remain retained', async () => {
  const alias = keys[0];
  await insert(canonical, '2026-09-25', 500, 'prior');
  const reviewed = await insert(alias, '2026-10-02', 900, 'reviewed');
  await db.query(`INSERT INTO official_source_review(document_id,source_locator,parser_version,record,reason,created_at)
    VALUES($1,$2,'weekly-v19','{}','Source conflict','2026-10-03T12:00:00Z')`,
  [reviewed.document, reviewed.locator]);
  const rows = await history();
  assert.equal(rows.length, 1);
  assert.equal(rows[0].price, 500);
  assert.equal((await db.query('SELECT count(*) FROM official_price_quote')).rows[0].count, '2');
  assert.equal((await db.query('SELECT count(*) FROM source_document')).rows[0].count, '2');
});

check('conflicting published price fails closed while unrelated weekly identity stays separate', async () => {
  await insert(keys[0], '2026-09-25', 500, 'first');
  await insert(canonical, '2026-09-25', 501, 'conflict');
  const raw = await history();
  assert.equal(raw.length, 2);
  assert.throws(() => mergeAcelgaWeeklyHistory(raw), /ACELGA_WEEKLY_PRICE_CONFLICT/);
  assert.throws(() => collapseAcelgaWeeklyCatalog(raw.map(row => ({ ...row, previous_price: null })), raw),
    /ACELGA_WEEKLY_PRICE_CONFLICT/);
  const other = hash('other-weekly-acelga');
  const outside = (await db.query(ordinary, [other])).rows;
  assert.equal(outside.length, 0);
  assert.equal((await db.query('SELECT count(*) FROM official_price_quote')).rows[0].count, '2');
});
