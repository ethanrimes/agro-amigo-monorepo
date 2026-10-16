const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path');
const ts = require('typescript');
function load(relative, dependencies = {}, globals = {}) {
  const exports = {};
  const code = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src', relative), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  new Function('exports', 'require', ...Object.keys(globals), code)(exports, name => {
    if (!(name in dependencies)) throw new Error('Unexpected dependency '+name);
    return dependencies[name];
  }, ...Object.values(globals));
  return exports;
}
const math = load('lib/planning-math.ts');
const sqlFold = load('lib/server/sql-search-fold.ts');
test('the fixed SQL mark class matches every Unicode mark in the JavaScript runtime', () => {
  const sql = sqlFold.sqlSearchFold('name');
  const pattern = /NFD\), '([^']+)'/.exec(sql)?.[1];
  assert.ok(pattern);
  const sqlMarks = new RegExp(pattern, 'u');
  const jsMarks = /\p{M}/u;
  for (let codePoint = 0; codePoint <= 0x10ffff; codePoint++) {
    const character = String.fromCodePoint(codePoint);
    assert.equal(sqlMarks.test(character), jsMarks.test(character), `U+${codePoint.toString(16)}`);
  }
});
test('search normalization ignores case and combining accents while source labels stay literal', () => {
  for (const variants of [
    ['CÍTRICOS', 'citricos', 'ci\u0301tricos'],
    ['Bogotá Quindío', 'BOGOTA QUINDIO', 'BOGOTA\u0301 QUINDI\u0301O'],
    ['NIÑO PIÑATA', 'nino pinata', 'nin\u0303o pin\u0303ata'],
    ['ÜREA', 'urea', 'U\u0308REA'],
  ]) assert.equal(new Set(variants.map(math.fold)).size, 1);
  assert.equal(math.fold('  Limón   común '), 'limon   comun');
  const source = { id: 'source-owned-id', name: 'Limón común', price: 1234.567, presentation: 'Caja de cartón' };
  const before = structuredClone(source);
  math.fold(source.name);
  assert.deepEqual(source, before);
});
test('place searches normalize both remote query and cache identity without altering returned spelling or coordinates', async () => {
  const calls = [];
  const route = load('app/api/location/search/route.ts', {
    'next/server': { NextResponse: { json: (body, init) => ({ body, status: init?.status || 200 }) } },
    '@/lib/location-types': { inColombia: () => true },
    '@/lib/planning-math': math,
  }, { fetch: async url => {
    calls.push(new URL(url));
    return Response.json({ features: [{ geometry: { type: 'Point', coordinates: [-74.072, 4.711] },
      properties: { countrycode: 'CO', name: 'Bogotá, finca Niño', state: 'Cundinamarca', osm_type: 'node', osm_id: 123 } }] });
  } });
  for (const query of ['Bogotá Quindío', 'BOGOTA QUINDIO', 'BOGOTA\u0301 QUINDI\u0301O']) {
    const response = await route.GET({ nextUrl: new URL('http://localhost/api/location/search?q='+encodeURIComponent(query)) });
    assert.equal(response.status, 200);
    assert.equal(response.body.places[0].name, 'Bogotá, finca Niño');
    assert.equal(response.body.places[0].latitude, 4.711);
    assert.equal(response.body.places[0].longitude, -74.072);
  }
  assert.equal(calls.length, 1);
  assert.equal(calls[0].searchParams.get('q'), 'bogota quindio');
});
