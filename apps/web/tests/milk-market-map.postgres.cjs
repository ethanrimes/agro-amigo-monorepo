'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const REPO = path.resolve(__dirname, '../../..');
const ts = require(path.join(REPO, 'apps/web/node_modules/typescript'));
const { Client } = require(path.join(REPO, 'apps/web/node_modules/pg'));
const source = path.join(REPO, 'apps/web/src/lib/server/explore.ts');

function loadMap(client, quoteRows, filters) {
  const exports = {};
  const mocks = {
    'server-only': {},
    '../label-normalization': { normalizeLabel: value => value },
    './db': { WINDOW: "observed_on >= CURRENT_DATE - INTERVAL '30 days'", database: () => client },
    './planning': {},
    './price-quotes': { filteredProduct: async () => ({
      product: { id: 'leche-cruda-en-finca', name: 'Leche cruda en finca' },
      filters, options: {}, markets: quoteRows,
    }) },
    '../filter-labels': {
      departmentKey: value => String(value || '').normalize('NFC').toLocaleLowerCase('es'),
      departmentVariants: value => [value],
    },
    '../input-locations': {
      municipalityKey: value => String(value || '').normalize('NFC').toLocaleLowerCase('es'),
      municipalityLabel: value => value,
    },
    '../input-identity-equivalence': {},
    '../pdf-locator': {},
    './supply-sql': {},
    './market-sql': {},
    './market-alias': {},
  };
  const js = ts.transpileModule(fs.readFileSync(source, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  vm.runInNewContext(js, {
    exports,
    require: name => {
      assert.ok(Object.hasOwn(mocks, name), `unexpected import ${name}`);
      return mocks[name];
    },
    Map, Set, JSON, Number, String, Array, Object, Math,
  }, { filename: source });
  return exports.mapData;
}

test('real PostgreSQL map resolves only unique municipality references and preserves quote provenance', async t => {
  const dsn = process.env.AGRO_MILK_MAP_LOCATION_PG_DSN;
  if (!dsn) return t.skip('requires explicitly owned local PostgreSQL fixture DSN');
  const client = new Client({ connectionString: dsn, connectionTimeoutMillis: 3000 });
  await client.connect();
  t.after(async () => client.end());
  await client.query(`
    CREATE TEMP TABLE municipality (
      id text PRIMARY KEY, name text NOT NULL, department text NOT NULL,
      department_id text NOT NULL, latitude double precision NOT NULL, longitude double precision NOT NULL
    );
    CREATE TEMP TABLE market (
      id text PRIMARY KEY, name text NOT NULL, city text NOT NULL, region text NOT NULL,
      municipality_id text
    );
  `);
  await client.query(`INSERT INTO municipality VALUES
    ('54172','Chinácota','Norte de Santander','54',7.61,-72.60),
    ('41551','Pitalito','Huila','41',1.85,-76.05),
    ('85010','Aguazul','Casanare','85',5.17,-72.55),
    ('85011','Santo Domingo','Casanare','85',5.10,-72.50),
    ('85012','Santo Domingo','Casanare','85',5.11,-72.51),
    ('41552','Palestina','Huila','41',1.74,-76.13),
    ('76001','Santiago de Cali','Valle del Cauca','76',3.45,-76.53),
    ('11001','Bogotá, D.C.','Bogotá, D.C.','11',4.65,-74.10)`);
  const markets = [
    ['finca-chinacota','Chinácota · leche en finca','Chinácota','Norte de Santander',null],
    ['finca-pitalito','Pitalito · leche en finca','Pitalito','Huila',null],
    ['finca-aguazul','Aguazul · leche en finca','Aguazul','Casanare',null],
    ['finca-wrong-dept','Pitalito · leche en finca','Pitalito','Cauca',null],
    ['finca-wrong-name','Fake Pitalito · leche en finca','Fake Pitalito','Huila',null],
    ['finca-ambiguous','Santo Domingo · leche en finca','Santo Domingo','Casanare',null],
    ['finca-conflict','Pitalito · leche en finca','Pitalito','Huila','41552'],
    ['ordinary-cali','Centro de abastos Cali','Cali','Valle del Cauca','76001'],
    ['ordinary-bogota-literal','Bogotá D.C. · Frigorífico Guadalupe','Bogotá D.C.','Bogotá D.C.','11001'],
    ['ordinary-null','Santiago de Cali','Santiago de Cali','Valle del Cauca',null],
  ];
  for (const row of markets) {
    await client.query(
      'INSERT INTO market(id,name,city,region,municipality_id) VALUES($1,$2,$3,$4,$5)',
      row,
    );
  }
  const quoteRows = markets.filter(([id]) => id.startsWith('finca-')).map(([id,name,_city,region]) => ({
    id, name, region, price: 2600, date: '2026-08-31', unit: 'litre',
    document_id: `doc-${id}`, source_locator: `sheet 1!row ${id}`,
    presentation: 'Por unidad de medida', units: '1 litro', series: 'farmgate',
  }));
  const filters = { series: 'farmgate', market: '', presentation: 'Por unidad de medida', units: '1 litro', region: '', history: 'all' };
  const beforeMarkets = await client.query('SELECT id,municipality_id,xmin::text FROM market ORDER BY id');
  const result = await loadMap(client, quoteRows, filters)('product','leche-cruda-en-finca','price',filters);
  assert.equal(JSON.stringify(result.points.map(p => p.id).sort()), JSON.stringify(['finca-aguazul','finca-chinacota','finca-pitalito']));
  assert.equal(JSON.stringify(result.points.map(p => p.document_id).sort()), JSON.stringify(['doc-finca-aguazul','doc-finca-chinacota','doc-finca-pitalito']));
  assert.ok(result.points.every(p => p.value === 2600 && p.date === '2026-08-31'));
  assert.ok(result.points.every(p => p.unit && p.source_locator && p.presentation === filters.presentation && p.units === filters.units && p.series === filters.series));
  assert.equal(JSON.stringify(result.filters), JSON.stringify(filters));
  assert.match(result.basis, /referencia municipal/i);
  assert.match(result.basis, /no indican la ubicación de una finca/i);
  const afterMarkets = await client.query('SELECT id,municipality_id,xmin::text FROM market ORDER BY id');
  assert.equal(JSON.stringify(afterMarkets.rows), JSON.stringify(beforeMarkets.rows));

  const ordinaryRows = [
    { id: 'ordinary-cali', name: 'Centro de abastos Cali', region: 'Valle del Cauca', price: 2000, date: '2026-08-31', unit: 'COP/kg', document_id: 'doc-cali', source_locator: 'PDF page 1,row 1', presentation: 'Kilogramo', units: '1 kilogramo', series: 'city' },
    { id: 'ordinary-bogota-literal', name: 'Bogotá D.C. · Frigorífico Guadalupe', region: 'Bogotá D.C.', price: 30000, date: '2026-08-31', unit: 'COP/kg', document_id: 'doc-bogota', source_locator: 'PDF page 1,row 2', presentation: 'Kilogramo', units: '1 kilogramo', series: 'city' },
    { id: 'ordinary-null', name: 'Santiago de Cali', region: 'Valle del Cauca', price: 2000, date: '2026-08-31', unit: 'COP/kg', document_id: 'doc-null', source_locator: 'PDF page 1,row 3', presentation: 'Kilogramo', units: '1 kilogramo', series: 'city' },
  ];
  const ordinaryFilters = { series: 'city', market: '', presentation: 'Kilogramo', units: '1 kilogramo', region: '', history: 'all' };
  const ordinary = await loadMap(client, ordinaryRows, ordinaryFilters)('product','ordinary-product','price',ordinaryFilters);
  assert.equal(JSON.stringify(ordinary.points.map(p => p.id).sort()), JSON.stringify(['ordinary-bogota-literal','ordinary-cali']));
  assert.equal(ordinary.points.find(p => p.id === 'ordinary-cali').latitude, 3.45);
  assert.equal(ordinary.points.find(p => p.id === 'ordinary-bogota-literal').longitude, -74.10);
  assert.equal(JSON.stringify(ordinary.points.map(p => p.name).sort()), JSON.stringify(['Bogotá D.C. · Frigorífico Guadalupe','Centro de abastos Cali']));
  assert.match(ordinary.basis, /puntos indican el municipio/i);
});
