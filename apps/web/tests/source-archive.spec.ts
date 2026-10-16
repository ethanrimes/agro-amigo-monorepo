import { expect, test } from '@playwright/test';
import reviewedCityDates from '../../../pipelines/ingestion/reviewed_city_dates.json';

test('city product filter choices show distinct report dates and preserve source spelling identities', async ({ page }) => {
  const seen: URLSearchParams[] = [];
  await page.route('**/api/products/ajo-importado?*', async route => {
    const q = new URL(route.request().url()).searchParams;
    seen.push(q);
    const market = q.get('market') || '', presentation = q.get('presentation') || 'Caja de carton';
    await route.fulfill({ json: {
      product: {id:'ajo-importado',name:'Ajo importado',category:'Verduras',image_key:'ajo'},
      markets: [],history: [],current: null,classification:[['Verduras']],additional_references:[],
      filters: {series:'city',market,presentation,units:'10 Kilogramo',history:'all'},
      options: {series:['city'],presentations:['Caja de carton','Caja de cartón'],units:['10 Kilogramo'],markets:[
        {id:'sipsa-barranquilla-granabastos',name:'Barranquilla, Granabastos',literal_name:'Barranquilla, Granabastos',first_report_on:'2026-09-07',last_report_on:'2026-10-05'},
        {id:'dane-city-barranquilla-granabastos',name:'Barranquilla, Granabastos',literal_name:'BARRANQUILLA, GRANABASTOS',first_report_on:'2021-09-01',last_report_on:'2021-09-01'},
      ]},
    }});
  });
  await page.goto('/product/ajo-importado?series=city&history=all');
  await expect(page.getByRole('heading',{name:'Ajo importado',exact:true})).toBeVisible();
  const market = page.getByRole('group',{name:'Mercado',exact:true});
  await market.getByRole('combobox').fill('BARRANQUILLA');
  const historical = market.getByRole('option',{name:/Informe: 01\/09\/2021/});
  await expect(historical).toContainText('BARRANQUILLA, GRANABASTOS');
  await expect(market.getByRole('option',{name:/07\/09\/2026–05\/10\/2026/})).toBeVisible();
  await historical.click();
  await expect(market).toHaveAttribute('data-selected-value','dane-city-barranquilla-granabastos');
  await expect(market).toContainText('Informe: 01/09/2021');
  const presentation = page.getByRole('group',{name:'Presentación',exact:true});
  for (const term of ['CARTON','cartón','carto\u0301n']) {
    await presentation.getByRole('combobox').fill(term);
    await expect(presentation.getByRole('option')).toHaveCount(2);
  }
  await presentation.getByRole('option',{name:/Texto en la fuente: Caja de carton/}).click();
  await expect(presentation).toHaveAttribute('data-selected-value','Caja de carton');
  await expect(page.locator('.applied-filters').first()).toContainText('Caja de cartón');
  await expect.poll(()=>seen.some(q=>q.get('market')==='dane-city-barranquilla-granabastos')).toBe(true);
  expect(seen.at(-1)?.get('presentation')).toBe('Caja de carton');
});

const filename = 'anex-SIPSAabastecimiento-1raquinabril2024.xlsx';

test('reused city PDF suggestions show verified report dates and open the selected original', async ({ page }) => {
  const originals = [
    { id: 'a'.repeat(64), observed_first: '2026-09-07', observed_last: '2026-09-07' },
    { id: 'b'.repeat(64), observed_first: '2026-09-05', observed_last: '2026-09-05' },
  ].map(row => ({ ...row, title: 'DANE - Medellín, Plaza Minorista .pdf', publisher: 'DANE',
    reference_period: 'Serie histórica completa', kind: 'original', media_type: 'application/pdf',
    retrieved_at: '2026-09-07T22:54:00.123456Z' }));
  await page.route('**/api/planning/library', route => route.fulfill({ json: [] }));
  await page.route('**/api/source-archive?*', route => route.fulfill({ json: { rows: originals, hasMore: false } }));
  await page.route(`**/api/evidence/${originals[1].id}?*`, route => route.fulfill({ json: {
    ...originals[1], source_url: 'https://www.dane.gov.co/files/report.zip',
    metadata: {}, records: [], parents: [], bytes: 0,
  } }));
  await page.goto('/sources');
  const library = page.locator('.source-library');
  await library.getByRole('combobox', { name: 'Buscar en los documentos' }).fill('MEDELLI\u0301N 2026-09-05');
  const options = library.getByRole('option');
  await expect(options).toHaveCount(2);
  await expect(options.nth(0)).toContainText('7 de septiembre de 2026');
  await expect(options.nth(1)).toContainText('5 de septiembre de 2026');
  await expect(options.nth(1)).not.toContainText('Período indicado en el documento');
  await options.nth(1).click();
  await expect(page.getByRole('dialog', { name: 'Documento de la fuente' })
    .getByRole('link', { name: 'Descargar archivo', exact: true }))
    .toHaveAttribute('href', `/api/evidence/${originals[1].id}/content`);
});

test('archived April 2024 SIPSA workbook is searchable and opens its evidence viewer', async ({ page }) => {
  const id = 'a3c543fd44ec8c07699c2755b51bc64df400e647393a3cd6009ae6ce0ca46ca3';
  const workbook = {
    id, filename, title: `DANE - ${filename}`, publisher: 'DANE',
    reference_period: 'Serie histórica completa', kind: 'original',
    media_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  };
  await page.route('**/api/planning/library', route => route.fulfill({ json: [] }));
  await page.route('**/api/source-archive?*', route => route.fulfill({ json: { rows: [workbook], hasMore: false } }));
  await page.route(`**/api/evidence/${id}?*`, route => route.fulfill({ json: {
    ...workbook, source_url: 'https://www.dane.gov.co/', retrieved_at: '2024-04-30T00:00:00Z',
    metadata: { original_filename: filename }, records: [], parents: [], bytes: 100,
  } }));
  await page.route(`**/api/evidence/${id}/workbook?*`, route => route.fulfill({ json: {
    sheets: ['1.1'], sheet: '1.1', start: 1, totalRows: 1, totalColumns: 1,
    displayedColumns: 1, rows: [['Abastecimiento']], readOnly: true,
  } }));

  await page.goto('/sources');
  const library = page.locator('.source-library');
  await expect(library.getByText(filename, { exact: false })).toHaveCount(0);
  await library.getByRole('combobox', { name: 'Buscar en los documentos' }).fill('abril2024');
  const entry = library.getByRole('option', { name: new RegExp(filename) });
  await expect(entry).toBeVisible();
  await expect(entry).toContainText('Período indicado en el documento');
  await expect(entry).not.toContainText('Serie histórica completa');
  await expect(library.locator('.library-row')).toHaveCount(0);
  await library.getByRole('combobox', { name: 'Buscar en los documentos' }).fill('DANE abril2024');
  await expect(library.getByRole('option', { name: new RegExp(filename) })).toBeVisible();
  await entry.click();
  await expect(page.getByRole('dialog', { name: 'Documento de la fuente' })).toBeVisible();
  await expect(page.getByRole('dialog').getByRole('heading', { name: `DANE - ${filename}` })).toBeVisible();
  await expect(page.getByRole('dialog').locator('.evidence-heading')).toContainText('Período indicado en el documento');
  await expect(page.getByRole('dialog').locator('.evidence-heading')).not.toContainText('Serie histórica completa');
  await expect(page.getByRole('dialog').getByRole('region', { name: 'Visor de Excel de solo lectura' })).toBeVisible();
  await expect(page.getByRole('dialog').getByText('Abastecimiento')).toBeVisible();
});

test('reused city filenames remain distinct and reachable past both search page limits', async ({ page }) => {
  const originals = Array.from({ length: 48 }, (_, index) => ({
    id: index.toString(16).padStart(64, '0'), title: 'DANE - Medellín, Plaza Minorista .pdf',
    filename: 'Medellín, Plaza Minorista .pdf', publisher: 'DANE', kind: 'original',
    media_type: 'application/pdf', reference_period: 'Serie histórica completa',
    retrieved_at: '2026-09-07T22:54:00.123456Z',
  }));
  const selected = originals[47];
  const queries: string[] = [];
  await page.route('**/api/planning/library', route => route.fulfill({ json: [] }));
  await page.route('**/api/source-archive?*', route => {
    const url = new URL(route.request().url());
    queries.push(url.searchParams.get('q') || '');
    return route.fulfill({ json: url.searchParams.has('cursor')
      ? { rows: originals.slice(40), hasMore: false, nextCursor: null }
      : { rows: originals.slice(0, 40), hasMore: true, nextCursor: 'next-page' } });
  });
  await page.route(`**/api/evidence/${selected.id}?*`, route => route.fulfill({ json: {
    ...selected, source_url: 'https://www.dane.gov.co/files/report.zip',
    metadata: { original_filename: selected.filename }, records: [], parents: [], bytes: 0,
  } }));
  await page.goto('/sources');
  const library = page.locator('.source-library');
  await expect(library.locator('p[role="status"]')).toContainText('0 documentos');
  const input = library.getByRole('combobox', { name: 'Buscar en los documentos' });
  await input.fill('MEDELLIN plaza minorista');
  await expect(library.getByRole('option')).toHaveCount(8);
  await expect(library.getByRole('option').first()).toContainText('Copia 000000000000');
  // Different versions must remain distinguishable even when the filename and archive minute match.
  await expect(library.getByRole('option').first()).not.toHaveText(await library.getByRole('option').nth(1).innerText());
  await input.fill('MEDELLIN plaza minorista ');
  await expect(library.getByRole('option')).toHaveCount(8);
  for (let pageIndex = 0; pageIndex < 4; pageIndex++)
    await library.getByRole('button', { name: 'Siguientes', exact: true }).click();
  await expect(library.getByText('33–40 de 40', { exact: true })).toBeVisible();
  await library.getByRole('button', { name: 'Cargar más coincidencias' }).click();
  await expect(library.getByRole('button', { name: 'Siguientes', exact: true })).toBeVisible();
  await library.getByRole('button', { name: 'Siguientes', exact: true }).click();
  await expect(library.getByText('41–48 de 48', { exact: true })).toBeVisible();
  await library.getByRole('option').last().click();
  await expect(page.getByRole('dialog', { name: 'Documento de la fuente' })).toBeVisible();
  await expect(page.getByRole('dialog').getByRole('link', { name: 'Descargar archivo', exact: true }))
    .toHaveAttribute('href', `/api/evidence/${selected.id}/content`);
  await page.getByRole('dialog').getByRole('button', { name: 'Cerrar ventana' }).click();
  await input.fill('OTRO ARCHIVO');
  await expect(library.getByText('1–8 de 40', { exact: true })).toBeVisible();
  await input.fill('MEDELLI\u0301N plaza minorista');
  await expect(library.getByText('1–8 de 40', { exact: true })).toBeVisible();
  expect(queries).toContain('MEDELLIN plaza minorista');
  expect(queries).toContain('MEDELLI\u0301N plaza minorista');
});

test('a failed later archive page preserves originals and supports retry', async ({ page }) => {
  const originals = Array.from({ length: 41 }, (_, index) => ({
    id: index.toString(16).padStart(64, '0'), title: `DANE - Archivo ${index}.pdf`,
    publisher: 'DANE', kind: 'original', media_type: 'application/pdf', reference_period: '2026',
  }));
  let failed = false;
  await page.route('**/api/planning/library', route => route.fulfill({ json: [] }));
  await page.route('**/api/source-archive?*', route => {
    if (!new URL(route.request().url()).searchParams.has('cursor'))
      return route.fulfill({ json: { rows: originals.slice(0, 40), hasMore: true, nextCursor: 'next-page' } });
    if (!failed) {
      failed = true;
      return route.fulfill({ status: 503, json: { error: 'Fallo de página de prueba' } });
    }
    return route.fulfill({ json: { rows: originals.slice(40), hasMore: false, nextCursor: null } });
  });
  await page.goto('/sources');
  const library = page.locator('.source-library');
  await expect(library.locator('p[role="status"]')).toContainText('0 documentos');
  const input = library.getByRole('combobox', { name: 'Buscar en los documentos' });
  await input.fill('ARCHIVO');
  await expect(library.getByRole('option')).toHaveCount(8);
  for (let pageIndex = 0; pageIndex < 4; pageIndex++)
    await library.getByRole('button', { name: 'Siguientes', exact: true }).click();
  await library.getByRole('button', { name: 'Cargar más coincidencias' }).click();
  await expect(library.getByText('Fallo de página de prueba', { exact: true })).toBeVisible();
  await expect(library.getByRole('option')).toHaveCount(8);
  await expect(library.getByRole('option').first()).toContainText('Archivo 32.pdf');
  await library.getByRole('button', { name: 'Reintentar coincidencias' }).click();
  await expect(library.getByRole('button', { name: 'Siguientes', exact: true })).toBeVisible();
  await library.getByRole('button', { name: 'Siguientes', exact: true }).click();
  await expect(library.getByRole('option')).toHaveCount(1);
  await expect(library.getByRole('option')).toContainText('Archivo 40.pdf');
});

// This opt-in scenario uses the retained DANE PDFs and the real archive API.
// Run against a compiled app with AGRO_REAL_PDF_BROWSER=1 and a read-only
// catalog connection; it never starts from a document-ID route.
test.describe('retained February 2022 city PDFs through the visible library', () => {
  test.skip(!process.env.AGRO_REAL_PDF_BROWSER, 'Requires retained DANE PDFs and read-only catalog');
  const members = reviewedCityDates.archives.find((archive) => archive.archive_id.startsWith('2ca39'))!.members;
  const source = (market: string) => members.find((member) => member.market_name === market)!;

  async function search(page: import('@playwright/test').Page, query: string) {
    const input = page.locator('.source-library').getByRole('combobox', { name: 'Buscar en los documentos' });
    await Promise.all([
      page.waitForResponse((response) => response.url().includes('/api/source-archive?') &&
        new URL(response.url()).searchParams.get('q') === query && response.status() === 200),
      input.fill(query),
    ]);
    return page.locator('.source-library').getByRole('option');
  }

  async function openOwnPdf(page: import('@playwright/test').Page, market: string, query: string) {
    const member = source(market), filename = member.entry_name.split('/').at(-1)!;
    const options = await search(page, query);
    await expect(options).toHaveCount(1);
    await expect(options.first()).toContainText(`DANE - ${filename}`);
    await expect(options.first()).toContainText(`Mercado impreso: ${member.market_name}`);
    await options.first().click();
    const dialog = page.getByRole('dialog', { name: 'Documento de la fuente' });
    await expect(dialog.getByRole('heading', { name: `DANE - ${filename}`, exact: true })).toBeVisible();
    await expect(dialog.getByRole('link', { name: 'Descargar archivo', exact: true }))
      .toHaveAttribute('href', `/api/evidence/${member.document_id}/content`);
    const viewer = dialog.getByRole('region', { name: 'Visor del documento original' });
    await expect(viewer.locator('canvas[data-rendered="true"]')).toBeVisible();
    await expect(viewer.getByText('Leer el texto de esta página')).toBeVisible();
    await dialog.getByRole('button', { name: 'Cerrar ventana' }).click();
    return member.document_id;
  }

  test('printed market, filename spelling, NFD/case and date find the same own Neiva and Manizales PDFs', async ({ page }) => {
    await page.goto('/sources');
    const neiva = await openOwnPdf(page, 'Neiva, Surabastos', 'Neiva Surabastos 10-2-2022');
    expect(await openOwnPdf(page, 'Neiva, Surabastos', 'NEIVA SUARBASTOS 10/2/2022')).toBe(neiva);
    const manizales = await openOwnPdf(page, 'Manizales, Centro Galerías',
      'MANIZALES CENTRO GALERI\u0301AS 10/2/2022');
    expect(await openOwnPdf(page, 'Manizales, Centro Galerías',
      'manizales centro galerias 10-2-2022')).toBe(manizales);
    const options = await search(page, 'Neiva Surabastos 11-2-2022');
    await expect(options.filter({ hasText: 'DANE - Neiva, Suarbastos 10-2-2022.pdf' })).toHaveCount(0);
  });

  test('the two Pereira markets open separate original PDFs through their own visible suggestions', async ({ page }) => {
    await page.goto('/sources');
    const la41 = await openOwnPdf(page, 'Pereira, La 41', 'Pereira La 41 10-2-2022');
    const mercasa = await openOwnPdf(page, 'Pereira, Mercasa', 'Pereira Mercasa 10-2-2022');
    expect(la41).not.toBe(mercasa);
  });
});
