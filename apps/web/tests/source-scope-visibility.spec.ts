import { expect, test } from '@playwright/test';
import scope from '../../../shared/source-document-scope.json';

const excluded = scope.documents[0];
const heldVilleta = '0252263a3e19f9425aba43095bb0f4ad2324ad84741a42a2749626c6467f4459';
const villetaTitle = 'DANE - Villeta, 20-10-2023.pdf';
const zipTitle = 'DANE - bol-SIPSADiario-regionales-31may2024.zip';

test('source library hides administrative PDF while held city PDF and its complete ZIP stay reachable', async ({ page, request }) => {
  test.skip(!process.env.AGRO_REAL_PDF_BROWSER, 'Requires retained source originals and read-only catalog');
  await page.goto('/sources');
  const library = page.locator('.source-library');
  const search = library.getByRole('combobox', { name: 'Buscar en los documentos' });

  async function find(query: string) {
    const response = page.waitForResponse(candidate => candidate.url().includes('/api/source-archive?') &&
      new URL(candidate.url()).searchParams.get('q') === query && candidate.status() === 200);
    await search.fill(query);
    await response;
    return library.getByRole('option');
  }

  for (const query of ['metas2023finalf', 'MÉTAS2023FINALF']) {
    await find(query);
    await expect(library.getByRole('option')).toHaveCount(0);
  }
  for (const query of ['Villeta, 20-10-2023.pdf', 'VÍLLETA, 20-10-2023.PDF']) {
    const options = await find(query);
    await expect(options).toHaveCount(1);
    await expect(options.first()).toContainText(villetaTitle);
  }
  await library.getByRole('option').first().click();
  const dialog = page.getByRole('dialog', { name: 'Documento de la fuente' });
  await expect(dialog.getByRole('heading', { name: villetaTitle })).toBeVisible();
  await expect(dialog.getByRole('link', { name: 'Descargar archivo', exact: true }))
    .toHaveAttribute('href', `/api/evidence/${heldVilleta}/content`);
  await dialog.getByRole('button', { name: 'Cerrar ventana' }).click();

  const zipOptions = await find('bol-SIPSADiario-regionales-31may2024.zip');
  await expect(zipOptions).toHaveCount(1);
  await expect(zipOptions.first()).toContainText(zipTitle);
  await zipOptions.first().click();
  await expect(page.getByRole('dialog', { name: 'Documento de la fuente' })
    .getByRole('link', { name: 'Descargar archivo', exact: true }))
    .toHaveAttribute('href', `/api/evidence/${excluded.archive_id}/content`);

  for (const suffix of ['content', 'workbook']) {
    const response = await request.get(`/api/evidence/${excluded.document_id}/${suffix}`);
    expect(response.status()).toBe(404);
  }
  const retainedZip = await request.get(`/api/evidence/${excluded.archive_id}/content`);
  expect(retainedZip.status()).toBe(200);
  expect(retainedZip.headers()['content-type']).toContain('application/zip');
});
