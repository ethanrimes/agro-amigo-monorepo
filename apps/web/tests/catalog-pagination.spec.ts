import { test, expect } from '@playwright/test';
import { readFileSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { paginateCatalog } from '../src/lib/catalog-page';
import { catalogMatches, catalogSavedKey } from '../src/lib/catalog-display';
import type { UnifiedCatalog } from '../src/lib/catalog-types';
const path = process.env.CATALOG_AUDIT_FIXTURE || resolve(__dirname, '../../../artifacts/app-data-audit-2026-09-27/prices/catalog.json');
const catalog: UnifiedCatalog = existsSync(path) ? JSON.parse(readFileSync(path, 'utf8')) : {products:[],regions:[],latestDate:null,filters:{region:'',reference_scope:'all',excluded_nonregional_count:0,excluded_nonregional_reason:null}};

test('all retained quote identities remain reachable in bounded pages with unchanged prices and sources', () => {
  test.skip(!existsSync(path), 'Opt-in independent 14,263-entry source snapshot is not present');
  const rows = [];
  for (let offset = 0; offset < catalog.products.length; offset += 100) {
    const page = paginateCatalog(catalog, { offset, limit: 100 });
    expect(page.total).toBe(catalog.products.length);
    expect(page.products.length).toBeLessThanOrEqual(100);
    rows.push(...page.products);
  }
  expect(rows).toEqual(catalog.products);
  const first = paginateCatalog(catalog, { limit: 24 });
  expect(Buffer.byteLength(JSON.stringify(first))).toBeLessThan(50_000);
  expect(first.categories).toEqual(expect.arrayContaining([...new Set(catalog.products.map(p => p.category))]));
  expect(first.currencies).toContain('USD');
});

test('filtering and saved identities happen across the full catalog before pagination', () => {
  test.skip(!existsSync(path), 'Opt-in independent source snapshot is not present');
  for (const query of ['Arabica', 'Rosas', 'Cacao', 'Mora de castilla']) {
    const expected = catalog.products.filter(p => catalogMatches(p, query));
    const first = paginateCatalog(catalog, { q: query, limit: 24 });
    expect(first.total).toBe(expected.length);
    expect(first.products).toEqual(expected.slice(0, 24));
  }
  const rows = [catalog.products[0], catalog.products.at(-1)!];
  expect(paginateCatalog(catalog, {saved: rows.map(catalogSavedKey)}).products).toEqual(rows);
  expect(paginateCatalog(catalog, {saved: []}).total).toBe(0);
  const roses = paginateCatalog(catalog, {q:'Rosas',category:'Flores',currency:'USD'});
  expect(roses.total).toBeGreaterThan(0);
  expect(roses.products.every(p => p.currency==='USD' && p.category==='Flores')).toBe(true);
  expect(roses.map_product).toBeNull();
});

test('live page API is bounded, validates parameters, and canonical view excludes references', async ({request}) => {
  test.setTimeout(90_000);
  const response = await request.post('/api/catalog', {data:{limit:24,offset:0}});
  expect(response.ok()).toBeTruthy();
  const text = await response.text(), first = JSON.parse(text);
  expect(first.products).toHaveLength(24);
  expect(first.total).toBeGreaterThan(1000);
  expect(Buffer.byteLength(text)).toBeLessThan(50_000);
  const next = await request.post('/api/catalog',{data:{limit:24,offset:24}});
  const second = await next.json();
  expect(second.products).toHaveLength(24);
  expect(second.products.some((p: {identity:string}) => first.products.some((x: {identity:string})=>x.identity===p.identity))).toBe(false);
  const bad = await request.post('/api/catalog',{data:{saved:[5]}});
  expect(bad.status()).toBe(400);
  const canonical = await request.get('/api/catalog?view=canonical');
  expect(canonical.ok()).toBeTruthy();
  const data = await canonical.json();
  expect(data.products.length).toBeGreaterThan(100);
  expect(data.products.every((p:{kind:string})=>p.kind==='product')).toBe(true);
});
