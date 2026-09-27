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
const WINDOW = "observed_on > ((CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date - INTERVAL '12 months')::date AND observed_on <= (CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date";

function app(client) {
  const context = { exports: {}, Date, Map, Error, Promise, process,
    require: name => {
      if (name === 'server-only') return {};
      if (name === 'node:crypto') return require(name);
      if (name === './db') return { database: () => client, WINDOW };
      if (name === '../planning-math') return { fold: s => s };
      if (name === '../weather-data') return {};
      throw new Error(`Unexpected import ${name}`);
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
  const published = rows.filter(p => p.observed_on <= today && (historical || p.observed_on > cutoff) &&
    (!department || p.department === department) && (!id || p.id === id) &&
    !assets.some(a => a.document_id === p.document_id && a.kind === 'inputs-pdf' &&
      a.processor_version === 'inputs-pdf-v4' && !p.source_locator.endsWith('; inputs-pdf-v4')));
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

test('grouped department catalog agrees with independent exact-month and published-row oracle; other scopes retain parity', { skip: !enabled }, async () => {
  // This test accepts an explicit connection only. A local Unix-socket URL can
  // set sslmode=disable; Azure callers must configure their own TLS URL. It never
  // reads application secrets or assumes production TLS for a local cluster.
  const client = new Client({ connectionString: databaseURL, statement_timeout: 12000 });
  await client.connect();
  try {
    await client.query('BEGIN');
    await client.query('SET LOCAL search_path=pg_temp');
    const { rows: [clock] } = await client.query(`SELECT ((CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date)::text AS today,
      (((CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date - interval '12 months')::date)::text AS cutoff`);
    await client.query(`CREATE TEMP TABLE input_price(
      id text,department text,observed_on date,name text NOT NULL,category text NOT NULL,presentation text NOT NULL,
      price numeric NOT NULL,document_id text NOT NULL,source_locator text NOT NULL,
      brand text NOT NULL,registration text NOT NULL,product_line text NOT NULL,PRIMARY KEY(id,department,observed_on));
      CREATE TEMP TABLE input_municipal_price(LIKE input_price INCLUDING DEFAULTS);
      ALTER TABLE input_municipal_price ADD COLUMN municipality text NOT NULL;
      ALTER TABLE input_municipal_price ADD PRIMARY KEY(id,department,municipality,observed_on);
      CREATE TEMP TABLE ingestion_asset(url text PRIMARY KEY,document_id text,kind text,processor_version text,status text);`);
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
    const rows = [];
    const add = (id, offset, price, extras = {}) => rows.push({ id, department: 'Antioquia', observed_on: month(clock.today, offset),
      name: 'Same commercial product', category: 'Fertilizantes', presentation: id.endsWith('25kg') ? '25 kg' : '50 kg',
      price, document_id: 'ordinary', source_locator: 'Hoja1:R10', brand: 'Marca', registration: 'ICA123', product_line: 'Línea', ...extras });
    add('ordinary-50kg', -1, 120); add('ordinary-50kg', -2, 100);
    add('ordinary-25kg', -1, 65); add('ordinary-25kg', -2, 60);
    add('ordinary-50kg', -1, 90, { department: 'Boyacá' }); add('ordinary-50kg', -2, 80, { department: 'Boyacá' });
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
    add('historic-only', -14, 55); add('historic-only', -15, 50);
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
      ['Antioquia', 'department', false, '', false],
      ['', 'department', false, 'ordinary-50kg', false],
      ['Antioquia', 'municipality', false, '', true],
      ['Antioquia', 'municipality', false, '', false],
      ['', 'municipality', true, '', true],
    ];
    for (const args of cases) {
      const actual = normalized(await inputs(...args));
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
  } finally {
    await client.query('ROLLBACK');
    await client.end();
  }
});
