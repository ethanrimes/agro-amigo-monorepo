import { test, expect } from '@playwright/test';
import { currentClassifications } from '../src/lib/price-classification';

test('classification follows revision-resolved filtered quotes and retains distinct full paths', () => {
  const current = [{ category_path:['Frutas','Cítricos'] }, { category_path:['Frutas','Cítricos'] }, { category_path:['Frutas','Otras frutas'] }];
  expect(currentClassifications(current, 'Clasificación antigua')).toEqual([['Frutas','Cítricos'],['Frutas','Otras frutas']]);
  expect(currentClassifications(current.slice(0,1), 'Clasificación de otro mercado')).toEqual([['Frutas','Cítricos']]);
  expect(currentClassifications([], 'Frutas')).toEqual([['Frutas']]);
  expect(currentClassifications([{date:'2026-09-25',category_path:['Frutas','Cítricos']},{date:'2026-09-24',category_path:['Otro grupo','Desactualizado']}], 'Frutas', '2026-09-25')).toEqual([['Frutas','Cítricos']]);
});

test('filtered package endpoints retain current source prices, categories and sorted history without full-history classification scan', async ({request}) => {
  test.skip(process.env.RUN_PRICE_AUDIT !== "1", "Opt-in Sep27 source-pinned current price audit");
  test.setTimeout(120_000);
  for (const [id,presentation,units,price,path] of [
    ['mora-de-castilla','Caja de cartón','2.5 Kilogramo',22500,['Frutas','Otras frutas']],
    ['mora-de-castilla','Caja de cartón','12.5 Kilogramo',79000,['Frutas','Otras frutas']],
    ['limon-tahiti','Bulto','24 Kilogramo',99000,['Frutas','Cítricos']],
  ] as const) {
    const params = new URLSearchParams({series:'city',history:'recent',region:'Atlántico',market:'sipsa-barranquilla-barranquillita',presentation,units});
    const response = await request.get(`/api/products/${id}?${params}`, {timeout:30_000});
    expect(response.ok(),await response.text()).toBeTruthy();
    const data = await response.json();
    expect(data.current.price).toBe(price);
    expect(data.current.date).toBe('2026-09-25');
    expect(data.markets).toHaveLength(1);
    expect(data.markets[0].units).toBe(units);
    expect(data.classification).toContainEqual(path);
    expect(data.history.map((row:{date:string})=>row.date)).toEqual(data.history.map((row:{date:string})=>row.date).sort());
  }
});
