const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const ts = require('typescript');
const { Client, types } = require('pg');
const socket = process.env.AGRO_INPUT_QUERY_TEST_DATABASE;
const enabled = Boolean(socket?.includes('/tmp/agro-unified-catalog-pg-20260930'));
let db, GET;
const check = (name, fn) => test(name, { skip: !enabled && 'Requires private PostgreSQL fixture runner' }, fn);
before(async () => {
  if (!enabled) return;
  types.setTypeParser(1082, value => value);
  types.setTypeParser(1700, Number);
  db = new Client({ connectionString: socket }); await db.connect();
  await db.query(`SET search_path=pg_temp; SET statement_timeout='10s';
    CREATE TEMP TABLE historical_price(document_id text,source_locator text,observed_on date,product_name text,market_name text,unit text,price numeric,change_percent numeric,series text);
    CREATE TEMP TABLE historical_price_review(document_id text,source_locator text);
    CREATE TEMP TABLE ingestion_asset(document_id text,status text,observed_on date);
    CREATE TEMP TABLE source_document(id text,retrieved_at timestamptz);
    CREATE TEMP TABLE input_reference_row(document_id text,source_locator text,observed_on date,name text,category text,details jsonb,kind text);
    CREATE TEMP VIEW published_historical_price AS SELECT h.* FROM historical_price h WHERE NOT EXISTS(SELECT 1 FROM historical_price_review r WHERE r.document_id=h.document_id AND r.source_locator=h.source_locator);
    INSERT INTO source_document VALUES('retained-pdf','2015-03-01'),('review-only','2015-05-01');
    INSERT INTO historical_price VALUES
      ('retained-pdf','page23-v4','2015-02-28','Ahuyama','Barranquilla','kg',468,NULL,'dane-monthly-summary'),
      ('retained-pdf','page23-v5','2015-02-28','Ahuyama','Barranquilla','kg',468,6.61,'dane-monthly-summary'),
      ('retained-pdf','separate-unit','2015-02-28','Ahuyama','Barranquilla','bulto',9360,2,'dane-monthly-summary'),
      ('review-only','grid','2015-04-30','Unverified','Bogotá','kg',100,1,'dane-monthly-summary');
    INSERT INTO historical_price_review VALUES('retained-pdf','page23-v4');
    INSERT INTO ingestion_asset VALUES('review-only','review','2015-04-30');
    INSERT INTO source_document VALUES('electricity-original','2026-07-21');
    INSERT INTO input_reference_row
      SELECT 'electricity-original','3.5!row '||g,'2026-06-30',
        'Proveedor '||lpad(((g-1)/6+1)::text,2,'0'),'Energía eléctrica',
        jsonb_build_object('Estrato',(g-1)%6+1,'Tarifa mes',g*0.01,'Subsidio',-0.5952237758733023), 'electricity'
      FROM generate_series(1,126) g;`);
  const output = ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/app/api/data-references/route.ts'),'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const normalization = {};
  const normalizeSource = fs.readFileSync(path.join(__dirname, '../src/lib/label-normalization.ts'), 'utf8');
  const normalizeCode = ts.transpileModule(normalizeSource, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
    esModuleInterop: true, resolveJsonModule: true,
  } }).outputText;
  const labels = JSON.parse(fs.readFileSync(path.join(__dirname, '../../../shared/label-normalization.json'), 'utf8'));
  vm.runInNewContext(normalizeCode, { exports: normalization,
    require: name => {
      assert.equal(name, '../../../../shared/label-normalization.json');
      return labels;
    },
  });
  const display = {};
  const displayCode = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src/lib/data-reference-labels.ts'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  vm.runInNewContext(displayCode, { exports: display, require: name => {
    if (name === './label-normalization') return normalization;
    if (name === './category-hierarchy') return require('./helpers/category-hierarchy.cjs')(normalization.normalizeLabel);
    throw new Error('Unexpected display dependency ' + name);
  }});
  const context = { exports:{}, require: name => {
    if (name === 'next/server') return { NextResponse:{json:(body,init) => ({body,status:init?.status || 200})} };
    if (name === '@/lib/server/db') return {database:()=>db};
    if (name === '@/lib/label-normalization') return normalization;
    if (name === '@/lib/data-reference-labels') return display;
    if (name === '@/lib/server/sql-search-fold') {
      const folded = {};
      new Function('exports', ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/lib/server/sql-search-fold.ts'),'utf8'), {
        compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
      }).outputText)(folded);
      return folded;
    }
    if (name === '@/lib/planning-math') {
      const math = {};
      new Function('exports', ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/lib/planning-math.ts'),'utf8'), {
        compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
      }).outputText)(math);
      return math;
    }
    throw new Error(name);
  }};
  vm.runInNewContext(output,context); GET=context.exports.GET;
});

check('database record search treats case and composed/decomposed accents equally without changing source values', async () => {
  const originals = [
    ['search-a', 'Café Niño', 1234.567],
    ['search-b', 'CAFE\u0301 NIN\u0303O', 4567],
    ['search-c', 'Fertilizante 20%_', 8901],
  ];
  for (const [id, name, price] of originals) {
    await db.query("INSERT INTO source_document VALUES($1,'2026-07-01')", [id]);
    await db.query(`INSERT INTO input_reference_row VALUES($1,'A1','2026-06-30',$2,'Fertilizantes',jsonb_build_object('Precio (COP)',$3::numeric),'summary')`, [id, name, price]);
  }
  try {
    for (const query of ['cafe nino', 'CAFÉ NIÑO', 'CaFe\u0301 NiN\u0303o']) {
      const response = await GET({ nextUrl: new URL('http://localhost/api/data-references?kind=summary&date=2026-06-30&q='+encodeURIComponent(query)) });
      assert.equal(response.status, 200);
      assert.equal(response.body.total, 2);
      assert.deepEqual(Array.from(response.body.rows, row => [row.document_id, row.source_locator, row.details['Precio (COP)']]).sort((a,b) => a[0].localeCompare(b[0])),
        [['search-a','A1',1234.567],['search-b','A1',4567]]);
    }
    const literal = await GET({ nextUrl: new URL('http://localhost/api/data-references?kind=summary&date=2026-06-30&q='+encodeURIComponent('20%_')) });
    assert.equal(literal.body.total, 1);
    assert.equal(literal.body.rows[0].document_id, 'search-c');
    const stored = (await db.query("SELECT document_id,name,details->>'Precio (COP)' AS price FROM input_reference_row WHERE document_id LIKE 'search-%' ORDER BY document_id")).rows;
    assert.deepEqual(stored.map(row => [row.document_id,row.name,Number(row.price)]), originals);
  } finally {
    await db.query("DELETE FROM input_reference_row WHERE document_id LIKE 'search-%'; DELETE FROM source_document WHERE id LIKE 'search-%'");
  }
});
check('database record search removes extended and astral marks while preserving exact record IDs', async () => {
  const names = [
    ['mark-1ab0', 'Ar\u1ab0bol 20%_'],
    ['mark-astral', 'Ar\u{1d185}bol 20%_'],
    ['mark-other', 'Arbol 20xx'],
  ];
  for (const [id, name] of names) {
    await db.query("INSERT INTO source_document VALUES($1,'2026-07-01')", [id]);
    await db.query(`INSERT INTO input_reference_row VALUES($1,'A1','2026-06-30',$2,
      'Fertilizantes','{}','summary')`, [id, name]);
  }
  try {
    for (const query of ['arbol 20%_', 'ÁRBOL 20%_', 'ar\u0301bol 20%_']) {
      const response = await GET({ nextUrl: new URL('http://localhost/api/data-references?kind=summary&date=2026-06-30&q='+encodeURIComponent(query)) });
      assert.equal(response.status, 200);
      assert.deepEqual(response.body.rows.map((row) => row.document_id).sort(), ['mark-1ab0', 'mark-astral']);
    }
    assert.deepEqual((await db.query("SELECT document_id,name FROM input_reference_row WHERE document_id LIKE 'mark-%' ORDER BY document_id")).rows.map((row) => [row.document_id, row.name]), names.sort((a,b) => a[0].localeCompare(b[0])));
  } finally {
    await db.query("DELETE FROM input_reference_row WHERE document_id LIKE 'mark-%'; DELETE FROM source_document WHERE id LIKE 'mark-%'");
  }
});
after(async () => { if (db) await db.end(); });
async function result(query) { return GET({nextUrl:new URL('http://localhost/api/data-references?kind=wholesale&'+query)}); }
check('monthly summary uses corrected published percentage without deleting legacy raw rows', async () => {
  const res = await result('date=2015-02-28&q=Ahuyama');
  assert.equal(res.status,200); const kg=res.body.rows.find(row=>row.details.Unidad==='kg');
  assert.equal(kg.details['Precio (COP)'],468); assert.equal(kg.details['Variación (%)'],6.61);
  assert.equal(kg.source_locator,'page23-v5');
  assert.equal((await db.query('SELECT count(*)::int n FROM historical_price')).rows[0].n,4);
});
check('monthly summary keeps distinct reported units for the same product and city', async () => {
  const res=await result('date=2015-02-28&q=Ahuyama');
  assert.equal(res.body.total,2); assert.equal(res.body.rows.length,2);
  assert.deepEqual(res.body.rows.map(row=>row.details.Unidad).sort(),['bulto','kg']);
});
check('a withheld source cannot become the latest monthly date or a visible summary', async () => {
  const res=await result(''); assert.equal(res.status,200);
  assert.deepEqual(Array.from(res.body.dates),['2015-02-28']); assert.equal(res.body.date,'2015-02-28');
  assert.equal(res.body.rows.some(row=>row.document_id==='review-only'),false);
});
check('tariff pagination retains every exact provider and stratum once with stable source identities and decimals', async () => {
  const request = page => GET({nextUrl:new URL('http://localhost/api/data-references?kind=electricity&date=2026-06-30&page='+page)});
  const pages = [];
  for (const page of [0,1,2]) {
    const response = await request(page);
    assert.equal(response.status,200); assert.equal(response.body.total,126);
    assert.equal(response.body.rows.length,page===2?6:60);
    assert.deepEqual(response.body.rows,(await request(page)).body.rows);
    pages.push(...response.body.rows);
  }
  assert.equal(new Set(pages.map(row=>row.document_id+':'+row.source_locator)).size,126);
  for (let i=0;i<126;i++) {
    const row=pages[i];
    assert.equal(row.name,'Proveedor '+String(Math.floor(i/6)+1).padStart(2,'0'));
    assert.equal(row.details.Estrato,i%6+1);
    assert.equal(row.details['Tarifa mes'],(i+1)/100);
    assert.equal(row.details.Subsidio,-0.5952237758733023);
    assert.equal(row.source_locator,'3.5!row '+(i+1));
  }
  assert.equal((await db.query('SELECT count(*)::int n FROM input_reference_row')).rows[0].n,126);
});
check('canonical category selection includes every exact raw spelling without crossing categories', async () => {
  await db.query(`INSERT INTO source_document VALUES('spell-a','2026-07-01'),('spell-b','2026-07-01'),('spell-c','2026-07-01');
    INSERT INTO input_reference_row VALUES
      ('spell-a','A1','2026-06-30','A','Lacteos y huevos',
        '{"Grupo":"Lacteos y huevos","Ciudad":"Quindio","Precio (COP)":1234.567}'::jsonb,'summary'),
      ('spell-b','A2','2026-06-30','B','Lácteos y huevos',
        '{"Grupo":"Lácteos y huevos","Ciudad":"Quindío","Precio (COP)":4567}'::jsonb,'summary'),
      ('spell-c','A3','2026-06-30','C','Frutas frescas',
        '{"Grupo":"Frutas frescas","Ciudad":"NariNo","Precio (COP)":999}'::jsonb,'summary');`);
  try {
    for (const selected of ['Lácteos y huevos', 'Lacteos y huevos']) {
      const response = await GET({ nextUrl: new URL('http://localhost/api/data-references?kind=summary&date=2026-06-30&category='+encodeURIComponent(selected)) });
      assert.equal(response.status, 200);
      assert.equal(response.body.total, 2);
      assert.deepEqual(Array.from(response.body.rows, row => row.document_id).sort(), ['spell-a','spell-b']);
      assert.equal(response.body.categories.filter(value => value === 'Lácteos y huevos').length, 1);
      assert.equal(response.body.rows[0].category, 'Lácteos y huevos');
      assert.equal(response.body.rows[0].details.Grupo, 'Lácteos y huevos');
      assert.equal(response.body.rows[0].details.Ciudad, 'Quindío');
      assert.equal(response.body.rows[0].details['Precio (COP)'], 1234.567);
      assert.equal(response.body.rows[0].source_locator, 'A1');
    }
    const different = await GET({ nextUrl: new URL('http://localhost/api/data-references?kind=summary&date=2026-06-30&category=Frutas%20frescas') });
    assert.equal(different.body.total, 1);
    assert.equal(different.body.rows[0].document_id, 'spell-c');
    assert.equal(different.body.rows[0].details.Ciudad, 'NariNo');
  } finally {
    await db.query("DELETE FROM input_reference_row WHERE document_id LIKE 'spell-%'; DELETE FROM source_document WHERE id LIKE 'spell-%'");
  }
});
