import { expect, test } from '@playwright/test';

test('help link keeps safe filters and queues a consented report', async ({ page }) => {
  const sent: Record<string, unknown>[] = [];
  await page.route('**/api/bug-reports', async route => {
    sent.push(route.request().postDataJSON());
    await route.fulfill({ status: 201, json: { id: 'report-123', status: 'queued' } });
  });
  await page.goto('/credits?q=cafe&market=Armenia&lat=1.912345&lng=-76.123456');
  await page.locator('header').getByRole('link', { name: 'Reportar un problema' }).click();
  await expect(page).toHaveURL(/\/reportar\?from=/);
  await expect(page.getByText('Pantalla relacionada:')).toContainText('Créditos de imágenes');
  await expect(page.getByText('Pantalla relacionada:')).not.toContainText('1.912345');
  await page.getByLabel('¿Qué pasó?').fill('El valor de esta fuente no abre el documento.');
  await page.getByLabel('Correo para responderte (opcional)').fill('campesino@example.com');
  await page.getByRole('checkbox').check();
  await page.getByRole('button', { name: 'Enviar reporte' }).click();
  await expect(page.getByRole('status')).toContainText('Reporte en cola');
  await expect(page.getByRole('status')).toContainText('no confirma que el correo ya haya llegado');
  expect(sent).toEqual([{
    message: 'El valor de esta fuente no abre el documento.',
    reply_email: 'campesino@example.com',
    page_path: '/credits?q=cafe&market=Armenia',
    consent: true,
  }]);
  await page.getByRole('button', { name: 'Escribir otro reporte' }).click();
  await expect(page.getByLabel('¿Qué pasó?')).toHaveValue('');
});

test('source context is exact and unavailable service keeps the draft for retry', async ({ page }) => {
  const id = 'a'.repeat(64);
  const sent: Record<string, unknown>[] = [];
  let attempts = 0;
  await page.route('**/api/bug-reports', async route => {
    sent.push(route.request().postDataJSON());
    attempts += 1;
    await route.fulfill(attempts === 1
      ? { status: 503, json: { error: 'unavailable' } }
      : { status: 201, json: { id: 'report-456', status: 'queued' } });
  });
  await page.goto(`/reportar?from=${encodeURIComponent(`/evidence/${id}?page=10&lat=1.912345`)}`);
  await expect(page.getByText('Pantalla relacionada:')).toContainText('Fuente consultada · página 10');
  await expect(page.getByText('Pantalla relacionada:')).not.toContainText(id);
  await page.getByLabel('¿Qué pasó?').fill('La página diez se muestra en blanco.');
  await page.getByRole('button', { name: 'Enviar reporte' }).click();
  await expect(page.locator('p[role="alert"]')).toContainText('Confirma que aceptas');
  expect(sent).toHaveLength(0);
  await page.getByRole('checkbox').check();
  await page.getByRole('button', { name: 'Enviar reporte' }).click();
  await expect(page.locator('p[role="alert"]')).toContainText('no está disponible');
  await expect(page.getByLabel('¿Qué pasó?')).toHaveValue('La página diez se muestra en blanco.');
  await page.getByRole('button', { name: 'Enviar reporte' }).click();
  await expect(page.getByRole('status')).toContainText('Reporte en cola');
  expect(sent).toHaveLength(2);
  expect(sent[0]).toEqual({
    message: 'La página diez se muestra en blanco.',
    page_path: `/evidence/${id}?page=10`,
    source_document_id: id,
    consent: true,
  });
});
