/* Run from repo root on an explicitly selected test emulator, after deploying the web app. */
const { _android, expect:baseExpect } = require('@playwright/test');
const expect=baseExpect.configure({timeout:30000});
const {mkdirSync,writeFileSync}=require('node:fs');
const {execFileSync}=require('node:child_process');
const shot=(name)=>writeFileSync('artifacts/'+name,execFileSync(process.env.ANDROID_HOME+'/platform-tools/adb',['-s',process.env.ANDROID_TEST_SERIAL,'exec-out','screencap','-p'],{timeout:15000}));
(async()=>{
 const serial=process.env.ANDROID_TEST_SERIAL;if(!serial)throw new Error('Set ANDROID_TEST_SERIAL explicitly.');
 const device=(await _android.devices()).find(d=>d.serial()===serial);if(!device)throw new Error('Selected emulator/device not connected.');
 device.setDefaultTimeout(30000);await device.shell('am start -n co.agroamigo.demo/.MainActivity');
 try{
  const page=await(await device.webView({pkg:'co.agroamigo.demo'})).page();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('https://agroamigo-demo-9a04.azurewebsites.net/');await expect(page.locator('.product-card')).toHaveCount(4);
  await expect(page.locator('.mobile-nav a')).toHaveText(['Inicio','Productos','Mercados','Insumos','Mi finca']);
  await page.locator('.mobile-nav a[href="/farm"]').click();
  await expect(page.locator('.farm-editor, .farm-card').first()).toBeVisible();
  if(await page.getByRole('button',{name:'Explorar ejemplo en Pitalito'}).isVisible())await page.getByRole('button',{name:'Explorar ejemplo en Pitalito'}).click();
  else await page.locator('.farm-card').first().click();
  await expect(page.locator('.farm-location-map')).toBeVisible();
  await page.getByRole('tab',{name:'Clima y labores',exact:true}).click();
  await expect(page.locator('.weather-day')).toHaveCount(7);await page.locator('.work-signals').scrollIntoViewIfNeeded();expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
  mkdirSync('artifacts',{recursive:true});shot('android-farm.png');
  await page.getByRole('tab',{name:'Mis cuentas',exact:true}).click();await page.getByRole('link',{name:'Comprobar el costo cafetero'}).click();
  await expect(page.locator('canvas[data-rendered=true]')).toBeVisible();await expect(page.getByLabel('Página del documento')).toHaveValue('6');await page.locator('.pdf-viewer').scrollIntoViewIfNeeded();shot('android-evidence.png');
  await page.getByRole('link',{name:'Descargar archivo',exact:true}).click();
  await expect.poll(async()=>String(await device.shell('ls /sdcard/Download')),{timeout:30000}).toMatch(/\.pdf/);
  await device.shell('input keyevent 4');await expect(page.locator('dialog')).toHaveCount(0);await expect(page).toHaveURL(/\/farm\/[a-f0-9-]+$/);
  // The test harness grants Android foreground location and sets an emulator fix before this step.
  await page.getByRole('button',{name:'Editar finca',exact:true}).click();await page.getByRole('button',{name:'Usar mi ubicación GPS',exact:true}).click();
  await expect(page.locator('.location-coordinate')).toContainText('1.85470');await page.getByRole('button',{name:'Guardar mi finca →',exact:true}).click();await expect(page.locator('dialog')).toHaveCount(0);
  await expect(page.locator('.farm-location-map')).toHaveAttribute('data-latitude','1.8547');await page.reload();await expect(page.locator('.farm-location-map')).toHaveAttribute('data-latitude','1.8547');await expect(page.locator('.farm-location-map')).toHaveAttribute('data-ready','true');await expect(page.locator('.maplibregl-marker')).toBeVisible();await page.locator('.farm-map-panel').scrollIntoViewIfNeeded();shot('android-farm-pin.png');
  await page.goto('https://agroamigo-demo-9a04.azurewebsites.net/products');await page.getByRole('button',{name:'Ver mapa',exact:true}).click();await expect.poll(async()=>Number(await page.locator('.colombia-map').getAttribute('data-features'))).toBeGreaterThan(0);shot('android-colombia-map.png');await device.shell('input keyevent 4');await expect(page.locator('dialog')).toHaveCount(0);
  await page.goto('https://agroamigo-demo-9a04.azurewebsites.net/offers');await page.getByLabel('Precio oferta 1',{exact:true}).fill('2000');await expect(page.locator('.offer-result strong').first()).toContainText('200.000');await page.reload();await expect(page.getByLabel('Precio oferta 1',{exact:true})).toHaveValue('2000');shot('android-offers.png');
  expect(errors).toEqual([]);console.log('Android: Spanish navigation, Azure data, farm/weather, GPS pin persistence, MapLibre polygons, popup PDF rendering/download/back, offer math and persistence passed.');
 }finally{await device.close();}
 process.exit(0);
})().catch(e=>{console.error(e);process.exitCode=1;});
