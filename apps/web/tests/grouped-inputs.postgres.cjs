const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const { Client, types } = require('pg');

types.setTypeParser(1700, Number);
types.setTypeParser(1082, value => value);
const databaseURL = process.env.AGRO_INPUT_QUERY_TEST_DATABASE;
const enabled = Boolean(databaseURL);
const root = path.resolve(__dirname, '../../..');
const source = fs.readFileSync(path.join(__dirname, '../src/lib/server/planning.ts'), 'utf8');
const output = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const cityPartialReview = { exports: {} };
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,
  '../src/lib/server/city-partial-review.ts'), 'utf8'), { compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
} }).outputText, cityPartialReview);
const inputIdentityEquivalence = { exports: {} };
new Function('exports', 'require', ts.transpileModule(fs.readFileSync(path.join(__dirname,
  '../src/lib/input-identity-equivalence.ts'), 'utf8'), { compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
} }).outputText)(inputIdentityEquivalence.exports, name => name.endsWith('input-identity-equivalences.json')
  ? { default: JSON.parse(fs.readFileSync(path.join(root, 'shared/input-identity-equivalences.json'), 'utf8')) } : {});
const WINDOW = "observed_on > ((CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date - INTERVAL '12 months')::date AND observed_on <= (CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date";

function app(client) {
  const context = { exports: {}, Date, Map, Error, Promise, process,
    require: name => {
      if (name === 'server-only') return {};
      if (name === 'node:crypto' || name === 'node:timers') return require(name);
      if (name === './db') return { database: () => client, WINDOW };
      if (name === './official-evidence-sql') return {};
      if (name === './daily-date-note') return {};
      if (name === './city-partial-review') return cityPartialReview.exports;
      if (name === './source-document-sql' || name === './evidence-review-sql' ||
        name === './supply-summary-evidence') return {};
      if (name === './input-identities') return { reconcileInputCatalog: async rows => rows };
      if (name === '../input-identity-equivalence') return inputIdentityEquivalence.exports;
      if (name === '../planning-math') return { fold: s => s };
      if (name === '../label-normalization') return require('./helpers/load-label-normalization.cjs')();
      if (name === '../filter-labels') {
        const exports = {};
        new Function('exports', ts.transpileModule(fs.readFileSync(path.join(__dirname,
          '../src/lib/filter-labels.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS,
            target: ts.ScriptTarget.ES2022 } }).outputText)(exports);
        return exports;
      }
      if (name === '../weather-data') return {};
      throw new Error(`Unexpected import ${name}`);
    },
  };
  vm.runInNewContext(output, context);
  return context.exports;
}

function exploreApp(client) {
  const labelExports = {};
  new Function('exports', ts.transpileModule(fs.readFileSync(path.join(__dirname,
    '../src/lib/filter-labels.ts'), 'utf8'), { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
  } }).outputText)(labelExports);
  const locationExports = {};
  new Function('exports', 'require', ts.transpileModule(fs.readFileSync(path.join(__dirname,
    '../src/lib/input-locations.ts'), 'utf8'), { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
  } }).outputText)(locationExports, name => name === './filter-labels' ? labelExports : {});
  const source = fs.readFileSync(path.join(__dirname, '../src/lib/server/explore.ts'), 'utf8');
  const output = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
  } }).outputText;
  const context = { exports: {}, Map, Set, Error, Promise, JSON, Date,
    require: name => {
      if (name === 'server-only') return {};
      if (name === './db') return { database: () => client, WINDOW };
      if (name === './planning') return { inputs: async (_department, _scope, _historical, id) =>
        (await client.query(`SELECT id,name,category,presentation,brand,registration,product_line,
          department,municipality,observed_on,price,document_id,source_locator
          FROM published_input_municipal_price WHERE id=ANY($1::text[]) ORDER BY id`,
          [inputIdentityEquivalence.exports.resolveInputIdentity(id).memberIds])).rows };
      if (name === './price-quotes') return { PRICE_QUOTES: '', filteredProduct: async () => null };
      if (name === '../label-normalization') return require('./helpers/load-label-normalization.cjs')();
      if (name === '../filter-labels') return labelExports;
      if (name === '../input-locations') return locationExports;
      if (name === '../input-identity-equivalence') return inputIdentityEquivalence.exports;
      if (name === '../pdf-locator') return { pdfLocationPage: () => null };
      if (name === './supply-sql') return { supplyQueries: () => ({}), supplyMapQuery: () => '' };
      if (name === './market-sql') return { marketsQuery: () => '', marketDetailQuery: () => '', marketProductsQuery: () => '' };
      if (name === './market-alias') return { resolveMarketAlias: async (_db, id) => id };
      throw new Error(`Unexpected explore import ${name}`);
    },
  };
  vm.runInNewContext(output, context);
  return context.exports;
}

function month(date, offset, day = 1) {
  const d = new Date(date + 'T00:00:00Z');
  return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + offset, day)).toISOString().slice(0, 10);
}
function latest(a, b) {
  return b.observed_on.localeCompare(a.observed_on) || a.price - b.price ||
    a.department.localeCompare(b.department) || (a.municipality || '').localeCompare(b.municipality || '');
}

// Deliberately independent row-by-row oracle, with no SQL/window implementation.
function expected(rows, assets, today, cutoff, department, scope, historical, id, grouped) {
  const municipal = scope === 'municipality';
  const geographicKey = value => {
    const literal = value.trim().toLocaleLowerCase('es');
    return ({quindio:'quindío',bolivar:'bolívar',cordoba:'córdoba',
      'bogotá d.c.':'bogotá, d.c.','bogotá, d. c.':'bogotá, d.c.'})[literal] || literal;
  };
  const published = rows.filter(p => p.observed_on <= today && (historical || p.observed_on > cutoff) &&
    (!department || geographicKey(p.department) === geographicKey(department)) && (!id || p.id === id) &&
    !assets.some(a => a.document_id === p.document_id && a.kind === 'inputs-pdf' &&
      a.processor_version === 'inputs-pdf-v4' && !p.source_locator.endsWith('; inputs-pdf-v4')) &&
    !(p.id === 'alias-legacy' && rows.some(replacement => replacement.id === 'alias-new' &&
      replacement.department === p.department && replacement.observed_on === p.observed_on &&
      replacement.name === p.name && replacement.presentation === p.presentation &&
      replacement.brand === p.brand && replacement.registration === p.registration &&
      replacement.product_line === p.product_line)));
  const groups = new Map();
  for (const p of published) {
    const key = JSON.stringify([p.id, ...(grouped ? [] : [p.department, ...(municipal ? [p.municipality] : [])])]);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(p);
  }
  return [...groups.values()].map(group => {
    const winner = [...group].sort(latest)[0];
    const priorMonth = month(winner.observed_on, -1).slice(0, 7);
    const previous = published.filter(p => p.id === winner.id && p.department === winner.department &&
      (!municipal || p.municipality === winner.municipality) && p.observed_on.startsWith(priorMonth)).sort(latest)[0];
    return { ...winner, municipality: municipal ? winner.municipality : '', scope,
      previous_price: previous?.price ?? null, previous_date: previous?.observed_on ?? null };
  }).sort((a, b) => a.id.localeCompare(b.id) || a.department.localeCompare(b.department) || a.municipality.localeCompare(b.municipality));
}

function normalized(rows) {
  return JSON.parse(JSON.stringify(rows)).sort((a, b) => a.id.localeCompare(b.id) ||
    a.department.localeCompare(b.department) || a.municipality.localeCompare(b.municipality));
}

test('full-history catalog queue bounds SQL concurrency and releases a failed reader', async () => {
  let active = 0, peak = 0, failMunicipal = true;
  const db = { query: async sql => {
    active++; peak = Math.max(peak, active);
    try {
      await new Promise(resolve => setTimeout(resolve, 12));
      if (failMunicipal && sql.includes('input_municipal_price')) {
        failMunicipal = false;
        throw new Error('fixture read failure');
      }
      return { rows: [] };
    } finally { active--; }
  } };
  const { inputs } = app(db);
  const requests = [
    inputs('', 'department', true, '', true),
    inputs('', 'municipality', true, '', true),
    inputs('Antioquia', 'department', true, '', true),
  ];
  const settled = await Promise.race([
    Promise.allSettled(requests),
    new Promise((_, reject) => setTimeout(() => reject(new Error('history queue stuck')), 1000)),
  ]);
  assert.deepEqual(settled.map(row => row.status), ['fulfilled', 'rejected', 'fulfilled']);
  assert.equal(peak, 2);
  assert.equal((await inputs('', 'municipality', true, '', true)).length, 0);
  assert.equal((await inputs('Boyacá', 'municipality', true, '', true)).length, 0);
  assert.equal(active, 0);
});

test('owned PostgreSQL rejects a poisoned Wuxal member row before history canonicalization and preserves source data', { skip: !enabled }, async () => {
  const client = new Client({ connectionString: databaseURL, statement_timeout: 12000 });
  await client.connect();
  try {
    await client.query('BEGIN');
    await client.query('SET LOCAL search_path=pg_temp');
    await client.query(`CREATE TEMP TABLE published_input_municipal_price(
      id text,name text,category text,presentation text,brand text,registration text,product_line text,
      observed_on date,price numeric,document_id text,source_locator text,department text,municipality text)`);
    const canonicalId = 'wuxal-tapa-negra-16-16-12-1-litro';
    const legacyId = 'wuxal-16-16-12-tapa-negra-1-litro';
    await client.query(`INSERT INTO published_input_municipal_price VALUES
      ($1,'Wuxal tapa negra 16-16-12','Fertilizantes y enmiendas','1 litro','','','',DATE '2014-04-30',29317,'valid-pdf','PDF page 13','Quindío','Armenia'),
      ($2,'Wuxal 15-15-15','Otra categoría','5 litros','Marca','ICA-77','Línea',DATE '2014-04-30',1,'poison-pdf','PDF page 99','Quindío','Armenia')`,
      [canonicalId, legacyId]);
    const selected = (await client.query(`SELECT id,name,category,presentation,brand,registration,product_line,
      observed_on AS date,price,document_id,source_locator,department,municipality
      FROM published_input_municipal_price WHERE id=ANY($1::text[])
      AND department=ANY($2::text[]) AND municipality=ANY($3::text[])
      AND observed_on<=CURRENT_DATE ORDER BY observed_on,price DESC,source_locator`,
      [[canonicalId, legacyId], ['Quindío'], ['Armenia']])).rows;
    assert.equal(selected.length, 2, 'fixture query includes both original member identities');
    assert.throws(() => inputIdentityEquivalence.exports.assertInputIdentityMembers(
      selected, [canonicalId, legacyId]), inputIdentityEquivalence.exports.InputIdentityGuardError);
    const retained = (await client.query(`SELECT id,name,category,presentation,brand,registration,product_line,price
      FROM published_input_municipal_price WHERE id=$1`, [legacyId])).rows[0];
    assert.deepEqual(retained, { id: legacyId, name: 'Wuxal 15-15-15', category: 'Otra categoría',
      presentation: '5 litros', brand: 'Marca', registration: 'ICA-77', product_line: 'Línea', price: 1 });
    await client.query('ROLLBACK');
  } finally {
    await client.end();
  }
});

test('owned PostgreSQL input map refuses conflicting latest quotes and preserves equal-price evidence keys', { skip: !enabled }, async () => {
  const client = new Client({ connectionString: databaseURL, statement_timeout: 12000 });
  await client.connect();
  try {
    await client.query('BEGIN');
    await client.query('SET LOCAL search_path=pg_temp');
    await client.query(`CREATE TEMP TABLE published_input_municipal_price(
      id text,name text,category text,presentation text,brand text,registration text,product_line text,
      department text,municipality text,observed_on date,price numeric,document_id text,source_locator text);
      CREATE TEMP TABLE municipality(id text,name text,department_id text,department text,latitude numeric,longitude numeric);
      INSERT INTO municipality VALUES('armenia','Armenia','quindio','Quindío',4.53,-75.68)`);
    const canonicalId = 'wuxal-tapa-negra-16-16-12-1-litro';
    const legacyId = 'wuxal-16-16-12-tapa-negra-1-litro';
    await client.query(`INSERT INTO published_input_municipal_price VALUES
      ($1,'Wuxal tapa negra 16-16-12','Fertilizantes y enmiendas','1 litro','','','',
        'Quindío','Armenia',DATE '2014-04-30',29317,'new-pdf','PDF page 13'),
      ($2,'Wuxal 16-16-12 tapa negra','Fertilizantes y enmiendas','1 Litro','','','',
        'Quindío','Armenia',DATE '2014-04-30',30025,'old-pdf','PDF page 14')`, [canonicalId, legacyId]);
    const api = exploreApp(client);
    const filters = { scope: 'municipality', history: 'all', municipality: 'Armenia', region: 'Quindío' };
    await assert.rejects(api.mapData('input', canonicalId, 'price', filters),
      inputIdentityEquivalence.exports.InputIdentityConflictError,
      'different same-date prices must not be silently rendered as one map value');
    const retained = (await client.query(`SELECT id,price,source_locator FROM published_input_municipal_price
      WHERE id=ANY($1::text[]) ORDER BY id`, [[canonicalId, legacyId]])).rows;
    assert.deepEqual(retained.map(row => row.price).sort((a, b) => a - b), [29317, 30025]);

    await client.query(`UPDATE published_input_municipal_price SET price=29317 WHERE id=$1`, [legacyId]);
    const map = await api.mapData('input', canonicalId, 'price', filters);
    assert.equal(map.points.length, 2);
    assert.deepEqual(map.points.map(point => point.value), [29317, 29317]);
    assert.equal(new Set(map.points.map(point => point.quote_key)).size, 2,
      'equal-valued source quotes retain distinct evidence keys');
    assert.deepEqual(new Set(map.points.map(point => point.source_input_id)), new Set([canonicalId, legacyId]));
    assert.deepEqual(new Set(map.points.map(point => point.source_locator)), new Set(['PDF page 13', 'PDF page 14']));
    await client.query('ROLLBACK');
  } finally {
    await client.end();
  }
});

test('grouped department catalog agrees with independent exact-month and published-row oracle; other scopes retain parity', { skip: !enabled }, async () => {
  // This test accepts an explicit connection only. A local Unix-socket URL can
  // set sslmode=disable; Azure callers must configure their own TLS URL. It never
  // reads application secrets or assumes production TLS for a local cluster.
  const client = new Client({ connectionString: databaseURL, statement_timeout: 12000 });
  await client.connect();
  try {
    await client.query('BEGIN');
    await client.query('SET LOCAL search_path=pg_temp');
    await client.query("SET LOCAL timezone='America/Bogota'");
    const { rows: [clock] } = await client.query(`SELECT ((CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date)::text AS today,
      (((CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date - interval '12 months')::date)::text AS cutoff`);
    await client.query(`CREATE TEMP TABLE input_price(
      id text,department text,observed_on date,name text NOT NULL,category text NOT NULL,presentation text NOT NULL,
      price numeric NOT NULL,document_id text NOT NULL,source_locator text NOT NULL,
      brand text NOT NULL,registration text NOT NULL,product_line text NOT NULL,PRIMARY KEY(id,department,observed_on));
      CREATE TEMP TABLE input_municipal_price(LIKE input_price INCLUDING DEFAULTS);
      ALTER TABLE input_municipal_price ADD COLUMN municipality text NOT NULL;
      ALTER TABLE input_municipal_price ADD PRIMARY KEY(id,department,municipality,observed_on);
      CREATE TEMP TABLE ingestion_asset(url text PRIMARY KEY,document_id text,kind text,processor_version text,status text);
      CREATE TEMP TABLE ingestion_checkpoint(document_id text,processor_version text,step text);
      CREATE TEMP TABLE input_identity_alias(legacy_id text,id text,PRIMARY KEY(legacy_id,id));
      CREATE TEMP TABLE input_latest_projection_state(scope text,source_epoch bigint,projection_epoch bigint,asof_bogota date,delta_complete boolean NOT NULL DEFAULT false);
      INSERT INTO input_latest_projection_state VALUES ('department',0,-1,CURRENT_DATE,false),('municipality',0,-1,CURRENT_DATE,false);
      CREATE TEMP TABLE input_latest_projection_delta(scope text,id text,changed_epoch bigint,PRIMARY KEY(scope,id));
      CREATE TEMP TABLE input_department_latest_raw(id text,department text,observed_on date,price numeric,
        name text,category text,presentation text,document_id text,source_locator text,
        brand text,registration text,product_line text);
      CREATE TEMP TABLE input_municipal_latest_raw(id text,department text,municipality text,observed_on date,price numeric,
        name text,category text,presentation text,document_id text,source_locator text,
        brand text,registration text,product_line text);
      CREATE TEMP TABLE source_document(id text PRIMARY KEY,source_url text,retrieved_at timestamptz);`);
    const ledgerSchema = fs.readFileSync(path.join(root, 'pipelines/ingestion/schema.sql'), 'utf8').match(/CREATE TABLE IF NOT EXISTS input_projection_supersession \([\s\S]*?\n\);/);
    assert.ok(ledgerSchema, 'exact native supersession ledger schema');
    await client.query(ledgerSchema[0].replace('CREATE TABLE IF NOT EXISTS', 'CREATE TEMP TABLE'));
    // Use the real published views, not a simplified fixture eligibility rule.
    const schema = fs.readFileSync(path.join(root, 'pipelines/ingestion/schema.sql'), 'utf8');
    for (const name of ['published_input_price', 'published_input_municipal_price']) {
      const definition = schema.match(new RegExp(`CREATE OR REPLACE VIEW ${name} AS[\\s\\S]*?\\n\\);`));
      assert.ok(definition, name);
      await client.query(definition[0].replace('CREATE OR REPLACE VIEW', 'CREATE TEMP VIEW'));
    }
    const assets = [
      { url: 'upgrade', document_id: 'pdf-upgraded', kind: 'inputs-pdf', processor_version: 'inputs-pdf-v4', status: 'complete' },
      { url: 'unrelated', document_id: 'ordinary', kind: 'inputs-annex', processor_version: 'inputs-v3', status: 'review' },
      { url: 'earlier-parser', document_id: 'pdf-old', kind: 'inputs-pdf', processor_version: 'inputs-pdf-v3', status: 'complete' },
    ];
    for (const a of assets) await client.query('INSERT INTO ingestion_asset VALUES($1,$2,$3,$4,$5)', Object.values(a));
    for (const id of ['ordinary','pdf-upgraded','pdf-old'])
      await client.query('INSERT INTO source_document VALUES($1,$2,$3)', [id,'https://example.test/'+id,'2026-09-30T00:00:00Z']);
    await client.query("INSERT INTO input_identity_alias VALUES('alias-legacy','alias-new')");
    await client.query("INSERT INTO ingestion_checkpoint VALUES('pdf-upgraded','inputs-pdf-v4','inputs-pdf:published')");
    const rows = [];
    const add = (id, offset, price, extras = {}) => rows.push({ id, department: 'Antioquia', observed_on: month(clock.today, offset),
      name: 'Same commercial product', category: 'Fertilizantes', presentation: id.endsWith('25kg') ? '25 kg' : '50 kg',
      price, document_id: 'ordinary', source_locator: 'Hoja1:R10', brand: 'Marca', registration: 'ICA123', product_line: 'Línea', ...extras });
    add('ordinary-50kg', -1, 120); add('ordinary-50kg', -2, 100);
    add('ordinary-25kg', -1, 65); add('ordinary-25kg', -2, 60);
    add('ordinary-50kg', -1, 90, { department: 'Boyacá' }); add('ordinary-50kg', -2, 80, { department: 'Boyacá' });
    add('regional-older', -1, 130, { department: 'Boyacá' });
    add('regional-older', -3, 110); add('regional-older', -4, 100);
    add('foreign-only', -1, 80, { department: 'Valle del Cauca' });
    add('native-unaccented', -1, 73, { department:'Quindio' });
    add('native-accented', -1, 81, { department:'Quindío' });
    add('native-bogota-spaced', -1, 97, { department:'Bogotá, D. C.' });
    add('native-bogota-compact', -1, 99, { department:'Bogotá D.C.' });
    add('gap', -1, 140); add('gap', -3, 100);
    add('multiple-dates', -1, 180, { observed_on: month(clock.today, -1, 3) });
    add('multiple-dates', -1, 200, { observed_on: month(clock.today, -1, 20) });
    add('multiple-dates', -2, 130, { observed_on: month(clock.today, -2, 4) });
    add('multiple-dates', -2, 150, { observed_on: month(clock.today, -2, 21) });
    add('withdrawn-latest', -1, 999, { document_id: 'pdf-upgraded' });
    add('withdrawn-latest', -2, 110); add('withdrawn-latest', -3, 100);
    add('withdrawn-previous', -1, 150); add('withdrawn-previous', -2, 999, { document_id: 'pdf-upgraded' }); add('withdrawn-previous', -3, 100);
    add('fully-withdrawn', -1, 999, { document_id: 'pdf-upgraded' });
    add('corrected-pdf', -1, 123, { document_id: 'pdf-upgraded', source_locator: 'page3; inputs-pdf-v4' });
    add('old-parser-still-valid', -1, 125, { document_id: 'pdf-old' });
    add('alias-legacy', -1, 70); add('alias-new', -1, 71);
    add('alias-legacy', -2, 60); add('alias-new', -2, 61);
    add('historic-only', -14, 55); add('historic-only', -15, 50);
    // More than500 keys force actual national batching in both recent/all
    // modes. Historical/future-only keys must not leak into recent results.
    for (let n=0;n<505;n++) add('batch-'+String(n).padStart(3,'0'),-1,200+n);
    // Catalog identities on lexical boundaries and outside ASCII retain the
    // same winners in raw, projected, and department/municipality reads.
    for (const [index, id] of ['0-input', 'c', 'e', 'g', 'j', 'm', 'p', 's', 'v', 'z-input', 'ñ-input'].entries())
      add(id, -1, 300 + index);
    add('boundary', -12, 40, { observed_on: clock.cutoff });
    const tomorrow = new Date(clock.today + 'T00:00:00Z'); tomorrow.setUTCDate(tomorrow.getUTCDate() + 1);
    add('future', 0, 999, { observed_on: tomorrow.toISOString().slice(0, 10) });
    for (const r of rows) await client.query(`INSERT INTO input_price(${Object.keys(r).join(',')}) VALUES(${Object.keys(r).map((_, i) => '$' + (i + 1)).join(',')})`, Object.values(r));
    const municipalRows = rows.flatMap(r => [
      { ...r, municipality: 'Municipio A' },
      { ...r, municipality: 'Municipio B', price: r.price + 10 },
    ]);
    for (const r of municipalRows) await client.query(`INSERT INTO input_municipal_price(${Object.keys(r).join(',')}) VALUES(${Object.keys(r).map((_, i) => '$' + (i + 1)).join(',')})`, Object.values(r));
    const { inputs } = app(client);
    const cases = [
      ['Antioquia', 'department', false, '', true],
      ['Boyacá', 'department', false, '', true],
      ['Antioquia', 'department', false, 'multiple-dates', true],
      ['Antioquia', 'department', false, 'unknown', true],
      ['Unknown department', 'department', false, '', true],
      ['', 'department', false, '', true],
      ['Antioquia', 'department', true, '', true],
      ['Boyacá', 'department', true, '', true],
      ['Antioquia', 'department', false, '', false],
      ['', 'department', false, 'ordinary-50kg', false],
      ['', 'department', true, 'ordinary-50kg', false],
      ['Antioquia', 'department', true, 'withdrawn-latest', false],
      ['Antioquia', 'department', true, 'withdrawn-previous', false],
      ['Antioquia', 'department', true, 'corrected-pdf', false],
      ['Antioquia', 'department', true, 'alias-legacy', false],
      ['Antioquia', 'department', true, 'alias-new', false],
      ['Antioquia', 'department', true, 'fully-withdrawn', false],
      ['Antioquia', 'municipality', false, '', true],
      ['Antioquia', 'municipality', false, '', false],
      ['Antioquia', 'municipality', true, '', true],
      ['', 'municipality', false, '', true],
      ['', 'municipality', true, '', true],
      ['', 'municipality', true, 'ordinary-50kg', false],
      ['Antioquia', 'municipality', true, 'withdrawn-latest', false],
      ['Antioquia', 'municipality', true, 'withdrawn-previous', false],
      ['Antioquia', 'municipality', true, 'alias-legacy', false],
    ];
    cases.push(...cases.filter(args => args[0] === 'Antioquia').flatMap(args =>
      ['ANTIOQUIA', 'antioquia'].map(department => [department, ...args.slice(1)])));
    for (const department of ['Quindio','QUINDÍO','Bogotá, D.C.'])
      for (const scope of ['department','municipality'])
        for (const grouped of [true,false])
          cases.push([department,scope,true,'',grouped]);
    for (const args of cases) {
      const actual = normalized(await app(client).inputs(...args));
      const wanted = expected(args[1] === 'municipality' ? municipalRows : rows, assets, clock.today, clock.cutoff, ...args);
      assert.deepEqual(actual, wanted, JSON.stringify(args));
    }
    const catalog = await inputs('Antioquia', 'department', false, '', true);
    assert.equal(catalog.find(r => r.id === 'multiple-dates').previous_price, 150);
    assert.equal(catalog.find(r => r.id === 'gap').previous_price, null);
    assert.equal(catalog.find(r => r.id === 'withdrawn-latest').price, 110);
    assert.equal(catalog.find(r => r.id === 'withdrawn-previous').previous_price, null);
    assert.ok(!catalog.some(r => ['fully-withdrawn', 'historic-only', 'future', 'boundary'].includes(r.id)));
    assert.ok(catalog.some(r => r.id === 'ordinary-25kg') && catalog.some(r => r.id === 'ordinary-50kg'));
    const full = await inputs('', 'department', true, '', true);
    assert.ok(!full.some(r => r.id === 'alias-legacy'));
    assert.ok(full.some(r => r.id === 'alias-new'));
    assert.equal((await client.query("SELECT count(*) AS n FROM input_price WHERE id='alias-legacy'")).rows[0].n, '2');
    await client.query(`INSERT INTO ingestion_checkpoint
      SELECT 'ordinary','native-resume-'||n,'unrelated:checkpoint'
      FROM generate_series(1,5000) n`);
    const publishedBefore = {};
    for (const scope of ['published_input_price', 'published_input_municipal_price'])
      publishedBefore[scope] = (await client.query(`SELECT * FROM ${scope} ORDER BY id,department,observed_on`)).rows;
    // CONCURRENTLY is for durable production indexes outside a transaction.
    // The actual index definition is exercised here on isolated TEMP tables.
    const checkpointIndex = fs.readFileSync(path.join(root,
      'pipelines/ingestion/migrations/20261003_051_input_publication_checkpoint_index.sql'), 'utf8');
    await client.query(checkpointIndex.replace('CREATE INDEX CONCURRENTLY', 'CREATE INDEX'));
    for (const scope of Object.keys(publishedBefore))
      assert.deepEqual((await client.query(`SELECT * FROM ${scope} ORDER BY id,department,observed_on`)).rows,
        publishedBefore[scope], `${scope} eligibility is unchanged by the checkpoint index`);
    await client.query(`INSERT INTO input_department_latest_raw
      SELECT DISTINCT ON(id,department) id,department,observed_on,price,
        name,category,presentation,document_id,source_locator,brand,registration,product_line
      FROM input_price WHERE observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date
      ORDER BY id,department,observed_on DESC,price;
      INSERT INTO input_municipal_latest_raw
      SELECT DISTINCT ON(id,department,municipality) id,department,municipality,observed_on,price,
        name,category,presentation,document_id,source_locator,brand,registration,product_line
      FROM input_municipal_price WHERE observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date
      ORDER BY id,department,municipality,observed_on DESC,price;
      UPDATE input_latest_projection_state SET projection_epoch=source_epoch,delta_complete=true,
        asof_bogota=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date;`);
    let projectionReads = 0;
    const projectionQueries = [];
    const projected = app({ query: (sql, values) => {
      if (sql.includes('FROM input_department_latest_raw') ||
        sql.includes('FROM input_municipal_latest_raw')) {
        projectionReads++;
        projectionQueries.push(sql);
      }
      return client.query(sql, values);
    } }).inputs;
    for (const args of cases.filter(row => row[4] && !row[3])) {
      const actual = normalized(await projected(...args));
      const wanted = expected(args[1] === 'municipality' ? municipalRows : rows,
        assets, clock.today, clock.cutoff, ...args);
      assert.deepEqual(actual, wanted, `projection ${JSON.stringify(args)}`);
    }
    assert.ok(projectionReads >= 5, 'ready projection must serve grouped scopes');
    assert.ok(projectionQueries.some(sql => sql.includes('AND l.department=ANY($2::text[])')),
      'named recent department must use the projection instead of a full published-view scan');
    assert.ok(projectionQueries.every(sql =>
      /JOIN input_(?:municipal_|department_)latest_raw p/.test(sql) &&
      !/JOIN input_(?:municipal_)?price p/.test(sql)),
    'ready projected national catalog must resolve payload from the small projection, not the raw history');
    assert.ok(projectionQueries.every(sql =>
      sql.includes('withdrawn AS MATERIALIZED') && sql.includes('aliased AS MATERIALIZED') &&
      !sql.includes('EXISTS (SELECT 1 FROM ingestion_checkpoint')),
    'publication flags must be computed once per statement, not probed once per winner');
    const projectedAntioquia = await projected('Antioquia', 'department', true, '', true);
    assert.equal(projectedAntioquia.find(row => row.id === 'ordinary-25kg').price, 65,
      'no checkpoint leaves the raw winner eligible');
    assert.equal(projectedAntioquia.find(row => row.id === 'corrected-pdf').price, 123,
      'equal PDF processor version leaves the corrected winner eligible');
    assert.equal(projectedAntioquia.find(row => row.id === 'withdrawn-latest').price, 110,
      'newer PDF processor version resolves the older published winner');
    await client.query("UPDATE input_latest_projection_state SET asof_bogota=asof_bogota-1 WHERE scope='municipality'");
    let rawReads = 0;
    const stale = app({ query: (sql, values) => {
      if (sql.includes('WITH RECURSIVE keys')) rawReads++;
      return client.query(sql, values);
    } }).inputs;
    assert.deepEqual(normalized(await stale('', 'municipality', true, '', true)),
      expected(municipalRows, assets, clock.today, clock.cutoff,
        '', 'municipality', true, '', true));
    assert.ok(rawReads > 0, 'Bogotá date rollover must use current raw rows');
    await client.query("UPDATE input_latest_projection_state SET asof_bogota=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date,projection_epoch=source_epoch WHERE scope='municipality'");
    let interleaved = false, interleavedRawReads = 0;
    const raced = app({ query: async (sql, values) => {
      if (!interleaved && sql.includes('WITH state AS MATERIALIZED')) {
        interleaved = true;
        await client.query("UPDATE input_latest_projection_state SET source_epoch=source_epoch+1,delta_complete=false WHERE scope='municipality'");
      }
      if (sql.includes('WITH RECURSIVE keys')) interleavedRawReads++;
      return client.query(sql, values);
    } }).inputs;
    assert.deepEqual(normalized(await raced('', 'municipality', true, '', true)),
      expected(municipalRows, assets, clock.today, clock.cutoff,
        '', 'municipality', true, '', true));
    assert.ok(interleaved && interleavedRawReads > 0,
      'epoch change before pointer statement must fall back to raw rows');
    // A live input writer advances the epoch while the materialized projection
    // still carries the last completed publication. Overlay only changed IDs
    // in the same SQL snapshot, including a new ID and a new current winner.
    await client.query(`UPDATE input_latest_projection_state SET
      projection_epoch=source_epoch,delta_complete=true,
      asof_bogota=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date`);
    const deltaRows = [
      { ...rows.find(row => row.id === 'ordinary-50kg' && row.department === 'Antioquia'),
        observed_on: clock.today,price:250,source_locator:'delta-current' },
      { id:'delta-new',department:'Antioquia',observed_on:clock.today,
        name:'New during writer',category:'Fertilizantes',presentation:'1 litro',
        price:777,document_id:'ordinary',source_locator:'delta-new',
        brand:'Marca',registration:'ICA123',product_line:'Línea' },
    ];
    rows.push(...deltaRows);
    for (const row of deltaRows) {
      await client.query(`INSERT INTO input_price(${Object.keys(row).join(',')})
        VALUES(${Object.keys(row).map((_,i)=>'$'+(i+1)).join(',')})`,Object.values(row));
      const municipal={...row,municipality:'Municipio A',price:row.price+10};
      municipalRows.push(municipal);
      await client.query(`INSERT INTO input_municipal_price(${Object.keys(municipal).join(',')})
        VALUES(${Object.keys(municipal).map((_,i)=>'$'+(i+1)).join(',')})`,Object.values(municipal));
    }
    await client.query(`UPDATE input_latest_projection_state SET source_epoch=source_epoch+1;
      INSERT INTO input_latest_projection_delta(scope,id,changed_epoch)
      SELECT scope,affected.id,source_epoch FROM input_latest_projection_state
      CROSS JOIN (VALUES('ordinary-50kg'),('delta-new')) affected(id);`);
    let deltaProjectionReads=0,deltaRawRanges=0;
    const overlaid=app({query:(sql,values)=>{
      if(sql.includes('FROM input_latest_projection_delta d')) deltaProjectionReads++;
      if(sql.includes('WITH RECURSIVE keys')) deltaRawRanges++;
      return client.query(sql,values);
    }}).inputs;
    for(const args of [
      ['', 'department', true, '', true],
      ['Antioquia', 'department', false, '', true],
      ['', 'municipality', true, '', true],
      ['Antioquia', 'municipality', false, '', true],
    ]){
      assert.deepEqual(normalized(await overlaid(...args)),
        expected(args[1]==='municipality'?municipalRows:rows,
          assets,clock.today,clock.cutoff,...args),
        `writer delta ${JSON.stringify(args)}`);
    }
    assert.ok(deltaProjectionReads>=4,'stale projection must read exact delta IDs');
    assert.equal(deltaRawRanges,0,'complete delta must avoid national historical scans');
    await client.query(`DELETE FROM input_price WHERE id='gap';
      DELETE FROM input_municipal_price WHERE id='gap';
      UPDATE input_latest_projection_state SET source_epoch=source_epoch+1;
      INSERT INTO input_latest_projection_delta(scope,id,changed_epoch)
      SELECT scope,'gap',source_epoch FROM input_latest_projection_state WHERE true
      ON CONFLICT(scope,id) DO UPDATE SET changed_epoch=excluded.changed_epoch;`);
    for(const sourceRows of [rows,municipalRows])
      for(let i=sourceRows.length-1;i>=0;i--) if(sourceRows[i].id==='gap') sourceRows.splice(i,1);
    const afterDelete=app(client).inputs;
    for(const scope of ['department','municipality']) {
      const actual=normalized(await afterDelete('',scope,true,'',true));
      assert.ok(!actual.some(row=>row.id==='gap'),'deleted projected ID must disappear');
      assert.deepEqual(actual,expected(scope==='municipality'?municipalRows:rows,
        assets,clock.today,clock.cutoff,'',scope,true,'',true));
    }
    // Removing just one location must suppress its stale pointer while the
    // same identity remains visible at another location. A delta prefilter
    // that drops identities absent in the named department would resurrect it.
    await client.query(`DELETE FROM input_price WHERE id='ordinary-50kg' AND department='Antioquia';
      DELETE FROM input_municipal_price WHERE id='ordinary-50kg' AND department='Antioquia';
      UPDATE input_latest_projection_state SET source_epoch=source_epoch+1;
      INSERT INTO input_latest_projection_delta(scope,id,changed_epoch)
      SELECT scope,'ordinary-50kg',source_epoch FROM input_latest_projection_state WHERE true
      ON CONFLICT(scope,id) DO UPDATE SET changed_epoch=excluded.changed_epoch;`);
    for(const sourceRows of [rows,municipalRows])
      for(let i=sourceRows.length-1;i>=0;i--)
        if(sourceRows[i].id==='ordinary-50kg' && sourceRows[i].department==='Antioquia')
          sourceRows.splice(i,1);
    for(const department of ['', 'Antioquia'])
      for(const scope of ['department','municipality']) {
        const actual=normalized(await app(client).inputs(department,scope,true,'',true));
        assert.equal(actual.some(row=>row.id==='ordinary-50kg'), department==='');
        assert.deepEqual(actual,expected(scope==='municipality'?municipalRows:rows,
          assets,clock.today,clock.cutoff,department,scope,true,'',true));
      }
    // Exercise several complete 40-ID exception batches against the actual
    // published views. Half the aliases replace the newest legacy row; half
    // have a different product line and must leave that row in place.
    await client.query(`INSERT INTO source_document VALUES
      ('stress-old','https://example.test/stress-old','2026-09-29T00:00:00Z'),
      ('stress-new','https://example.test/stress-new','2026-09-30T00:00:00Z');
      INSERT INTO input_identity_alias
      SELECT 'stress-legacy-'||n,'stress-new-'||n FROM generate_series(0,119) n;
      INSERT INTO input_price(id,department,observed_on,name,category,presentation,price,
        document_id,source_locator,brand,registration,product_line)
      SELECT 'stress-legacy-'||n,'Antioquia',
        (CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date-1,
        'Stress product','Fertilizantes','50 kg',100+n,'stress-old','row:latest',
        'Marca','ICA123','Línea' FROM generate_series(0,119) n;
      INSERT INTO input_price(id,department,observed_on,name,category,presentation,price,
        document_id,source_locator,brand,registration,product_line)
      SELECT 'stress-legacy-'||n,'Antioquia',
        (CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date-35,
        'Stress product','Fertilizantes','50 kg',90+n,'stress-old','row:older',
        'Marca','ICA123','Línea' FROM generate_series(0,119) n;
      INSERT INTO input_price(id,department,observed_on,name,category,presentation,price,
        document_id,source_locator,brand,registration,product_line)
      SELECT 'stress-new-'||n,'Antioquia',
        (CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date-1,
        'Stress product','Fertilizantes','50 kg',200+n,'stress-new','row:replacement',
        'Marca','ICA123',CASE WHEN n%2=0 THEN 'Línea' ELSE 'Different' END
      FROM generate_series(0,119) n;
      INSERT INTO input_municipal_price
      SELECT p.*, 'Municipio A' FROM input_price p WHERE p.id LIKE 'stress-%';
      INSERT INTO input_department_latest_raw
      SELECT DISTINCT ON(id,department) id,department,observed_on,price,
        name,category,presentation,document_id,source_locator,brand,registration,product_line
      FROM input_price WHERE id LIKE 'stress-%'
      ORDER BY id,department,observed_on DESC,price;
      INSERT INTO input_municipal_latest_raw
      SELECT DISTINCT ON(id,department,municipality) id,department,municipality,
        observed_on,price,name,category,presentation,document_id,source_locator,
        brand,registration,product_line
      FROM input_municipal_price WHERE id LIKE 'stress-%'
      ORDER BY id,department,municipality,observed_on DESC,price;
      UPDATE input_latest_projection_state SET projection_epoch=source_epoch,delta_complete=true,
        asof_bogota=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date;`);
    for (const scope of ['department', 'municipality']) {
      let exceptionBatches = 0;
      const stressInputs = app({ query: (sql, values) => {
        if (sql.includes('FROM unnest($1::text[]) AS keys(id)') &&
          sql.includes(`FROM published_input_${scope === 'municipality' ? 'municipal_' : ''}price p`)) exceptionBatches++;
        return client.query(sql, values);
      } }).inputs;
      const actual = (await stressInputs('', scope, true, '', true))
        .filter(row => row.id.startsWith('stress-legacy-'))
        .map(row => [row.id,row.observed_on,row.price,row.document_id,row.source_locator]);
      const view = scope === 'department' ? 'published_input_price' : 'published_input_municipal_price';
      const { rows: wantedRows } = await client.query(`SELECT DISTINCT ON(id)
        id,observed_on,price,document_id,source_locator FROM ${view}
        WHERE id LIKE 'stress-legacy-%'
          AND observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date
        ORDER BY id,observed_on DESC,price,department${scope === 'municipality' ? ',municipality' : ''}`);
      const wanted = wantedRows.map(row => [row.id,row.observed_on,row.price,row.document_id,row.source_locator]);
      actual.sort((a,b) => a[0].localeCompare(b[0]));
      wanted.sort((a,b) => a[0].localeCompare(b[0]));
      assert.equal(JSON.stringify(actual), JSON.stringify(wanted),
        `${scope} exception parity with published view`);
      assert.equal(actual.length, 120);
      assert.ok(exceptionBatches >= 3, `${scope} must exercise multiple exception batches`);
    }

    // Strict two-ID read uses the real PostgreSQL published view and retains
    // each original member ID/name/locator while returning the canonical ID.
    await client.query(`INSERT INTO input_municipal_price
      (id,department,observed_on,name,category,presentation,price,document_id,source_locator,
       brand,registration,product_line,municipality)
      VALUES
      ('wuxal-16-16-12-tapa-negra-1-litro','Quindío','2013-03-31',
       'Wuxal 16-16-12 tapa negra','Fertilizantes y enmiendas','1 litro',29175,
       'wuxal-old','old-name!PDF page 13','','','','Armenia'),
      ('wuxal-tapa-negra-16-16-12-1-litro','Quindío','2014-04-30',
       'Wuxal tapa negra 16-16-12','Fertilizantes y enmiendas','1 Litro',29317,
       'wuxal-new','new-name!PDF page 13','','','','Armenia'),
      ('wuxal-16-16-12-tapa-negra-1-litro','Quindío','2014-04-30',
       'Wuxal 16-16-12 tapa negra','Fertilizantes y enmiendas','1 litro',30025,
       'wuxal-conflict','old-name!PDF page 14','','','','Armenia')`);
    const legacyInputId = 'wuxal-16-16-12-tapa-negra-1-litro';
    const canonicalInputId = 'wuxal-tapa-negra-16-16-12-1-litro';
    const strictInputs = app(client).inputs;
    const strictRows = await strictInputs('', 'municipality', true, legacyInputId, false);
    assert.equal(strictRows.length, 2, 'the selected detail returns both latest conflicting source quotes');
    assert.ok(strictRows.every(row => row.id === canonicalInputId));
    assert.deepEqual(strictRows.map(row => row.price).sort((a,b) => a-b), [29317,30025]);
    assert.deepEqual(strictRows.map(row => row.source_input_id).sort(), [canonicalInputId,legacyInputId].sort());
    assert.deepEqual(strictRows.map(row => row.source_name).sort(),
      ['Wuxal 16-16-12 tapa negra','Wuxal tapa negra 16-16-12'].sort());
    assert.ok(strictRows.some(row => row.source_locator === 'old-name!PDF page 14'));
    const canonicalRows = await strictInputs('', 'municipality', true, canonicalInputId, false);
    assert.deepEqual(canonicalRows.map(row => [row.id,row.price,row.source_input_id]).sort(),
      strictRows.map(row => [row.id,row.price,row.source_input_id]).sort());
  } finally {
    await client.query('ROLLBACK');
    await client.end();
  }
});
