import { test, expect } from '@playwright/test';
const id='iniciador-chanchitos-40-kilogramos-solla-7487';
test('input history starts recent and reveals retained years only when explicitly requested',async({page,request})=>{
 test.setTimeout(90000);
 const endpoint='/api/explore/input?'+new URLSearchParams({id,department:'Antioquia',scope:'department'});
 const recentResponse=await request.get(endpoint),allResponse=await request.get(endpoint+'&history=all');
 expect(recentResponse.ok()).toBe(true);expect(allResponse.ok()).toBe(true);
 const recent=await recentResponse.json(),all=await allResponse.json();
 expect(all.history.length).toBeGreaterThan(recent.history.length);
 expect(all.history[0].date < recent.history[0].date).toBe(true);
 const requested:string[]=[];
 page.on('request',r=>{if(r.url().includes('/api/explore/input'))requested.push(r.url());});
 await page.setViewportSize({width:390,height:844});
 await page.goto(`/insumo/${id}?department=Antioquia`);
 await expect(page.locator('.price-chart')).toBeVisible();
 expect(requested.every(url=>new URL(url).searchParams.get('history')!=='all')).toBe(true);
 await expect(page.getByLabel('Historial de precios')).toHaveValue('recent');
 await expect(page.locator('.chart-data tbody tr')).toHaveCount(recent.history.length);
 await page.getByLabel('Historial de precios').selectOption('all');
 await expect(page.locator('.chart-data tbody tr')).toHaveCount(all.history.length);
 await expect(page.getByLabel('Filtros aplicados')).toContainText('Todo el historial');
 await page.getByText('Ver datos en tabla',{exact:true}).click();
 const values=await page.locator('.chart-data tbody tr td:nth-child(2)').allTextContents();
 const numbers=values.map(x=>Number(x.replace(/[^0-9]/g,'')));
 expect(numbers).toEqual([...numbers].sort((a,b)=>b-a));
 expect(numbers).toEqual(all.history.map((x:{price:number})=>Math.round(x.price)).sort((a:number,b:number)=>b-a));
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await expect(page.locator('.input-detail-summary h2')).toHaveText(new Intl.NumberFormat('es-CO',{style:'currency',currency:'COP',maximumFractionDigits:0}).format(all.input.price));
});

test('full municipal and departmental catalogs retain every returned identity and open historical-only detail',async({page,request})=>{
 test.setTimeout(120000);
 for(const scope of ['department','municipality']) {
  const response=await request.get(`/api/planning/inputs?grouped=true&department=&scope=${scope}&history=all`,{timeout:60000});
  expect(response.ok()).toBe(true);
  const rows=await response.json();
  expect(rows.length).toBeGreaterThan(4000);
  expect(new Set(rows.map((row:{id:string})=>row.id)).size).toBe(rows.length);
  const older=rows.find((row:{observed_on:string;name:string})=>row.observed_on<'2020-01-01'&&row.name==='Monitor') || rows.find((row:{observed_on:string})=>row.observed_on<'2020-01-01');
  expect(older).toBeTruthy();
  await page.goto(`/insumos?scope=${scope}&history=all&department=`);
  await expect(page.getByLabel('Historial de precios')).toHaveValue('all');
  await expect(page.locator('.results-label')).toContainText(`${rows.length} insumos y presentaciones`,{timeout:60000});
  await expect(page.getByLabel('Filtros aplicados')).toContainText('Todo el historial');
  await page.getByRole('combobox',{name:'Buscar insumo',exact:true}).fill(older.name);
  await page.getByRole('combobox',{name:'Buscar insumo',exact:true}).press('Escape');
  const card=page.locator(`a.input-catalog-card[href^="/insumo/${older.id}?"]`);
  await expect(card).toBeVisible();
  await expect(card).toContainText(older.observed_on.slice(0,4));
  expect(new URL((await card.getAttribute('href'))!,'http://localhost').searchParams.get('history')).toBe('all');
  await card.click();
  await expect(page.locator('.input-detail-summary h2')).toBeVisible();
  await expect(page.getByLabel('Historial de precios')).toHaveValue('all');
  await expect(page.locator('.input-detail-summary')).toContainText(older.observed_on.slice(0,4));
 }
});
