const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

const file = path.join(__dirname, '../src/components/planning/pdf-canvas-sizing.ts');
const api = {};
new Function('exports', ts.transpileModule(fs.readFileSync(file, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText)(api);

const android = 'Mozilla/5.0 (Linux; Android 17; wv) Chrome/152.0 AgroAmigoAndroid/1.0';
const desktop = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) Chrome/152.0';
const ios = 'Mozilla/5.0 (iPhone; CPU iPhone OS 26_1 like Mac OS X) AppleWebKit/605.1.15';

function dimensions(width, height, ratio) {
  return { width: Math.floor(width * ratio), height: Math.floor(height * ratio) };
}

test('native Android fit retains resolution; 150 and 200 percent remain visible at bounded backing sizes', () => {
  for (const item of [
    { width: 349.891, height: 452.8, zoom: 'fit', expectedRatio: 2 },
    { width: 524.836, height: 679.199, zoom: '150%' },
    { width: 699.781, height: 905.599, zoom: '200%' },
  ]) {
    const ratio = api.pdfCanvasBackingRatio({ ...item, devicePixelRatio: 2.625, userAgent: android });
    const size = dimensions(item.width, item.height, ratio);
    assert.ok(size.width > 0 && size.height > 0, item.zoom);
    assert.ok(size.width * size.height <= api.ANDROID_WEBVIEW_PDF_MAX_CANVAS_PIXELS, item.zoom);
    if (item.expectedRatio) assert.equal(ratio, item.expectedRatio);
    else assert.ok(ratio < 2 && ratio > 1, item.zoom);
  }
});

test('desktop, iOS, and ordinary Android Chrome retain original two-times raster resolution', () => {
  for (const userAgent of [desktop, ios, 'Mozilla/5.0 (Linux; Android 17) Chrome/152.0 Mobile']) {
    assert.equal(api.pdfCanvasBackingRatio({ width: 699.781, height: 905.599,
      devicePixelRatio: 2.625, userAgent }), 2);
  }
});

test('fractional device scales and exact pixel boundary do not inflate a page', () => {
  assert.equal(api.pdfCanvasBackingRatio({ width: 300, height: 400,
    devicePixelRatio: 1.25, userAgent: android }), 1.25);
  assert.equal(api.pdfCanvasBackingRatio({ width: 1000, height: 800,
    devicePixelRatio: 2.625, userAgent: android }), 1);
  const ratio = api.pdfCanvasBackingRatio({ width: 1000.25, height: 800.5,
    devicePixelRatio: 2.625, userAgent: android });
  const size = dimensions(1000.25, 800.5, ratio);
  assert.ok(ratio < 1);
  assert.ok(size.width * size.height <= api.ANDROID_WEBVIEW_PDF_MAX_CANVAS_PIXELS);
});

test('oversized original pages retain positive dimensions without exceeding the bound', () => {
  const width = 3500, height = 5000;
  const ratio = api.pdfCanvasBackingRatio({ width, height,
    devicePixelRatio: 3, userAgent: android });
  const size = dimensions(width, height, ratio);
  assert.ok(size.width > 0 && size.height > 0);
  assert.ok(size.width * size.height <= api.ANDROID_WEBVIEW_PDF_MAX_CANVAS_PIXELS);
});

test('invalid PDF viewports fail visibly rather than certifying a zero-size render', () => {
  for (const [width, height] of [[0, 100], [100, -1], [Infinity, 100], [100, NaN],
    [Number.MAX_VALUE, Number.MAX_VALUE], [1e12, 1], [0.1, 0.1]]) {
    assert.throws(() => api.pdfCanvasBackingRatio({ width, height,
      devicePixelRatio: 2.625, userAgent: android }), RangeError);
  }
});

test('an unavailable or invalid device pixel ratio uses a visible one-times bitmap', () => {
  for (const devicePixelRatio of [0, -1, NaN, Infinity]) {
    assert.equal(api.pdfCanvasBackingRatio({ width: 300, height: 400,
      devicePixelRatio, userAgent: android }), 1);
  }
});
