const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const output = {};
new Function('exports', ts.transpileModule(
  fs.readFileSync(path.join(__dirname, '../src/lib/archive-copy-label.ts'), 'utf8'),
  { compilerOptions: { module: ts.ModuleKind.CommonJS } },
).outputText)(output);
test('retained copy labels use Colombia time and distinguish in-place revisions', () => {
  const current = output.archiveCopyLabel('2026-09-27T06:52:59.610524Z');
  const old = output.archiveCopyLabel('2026-09-07T23:42:16.319237Z');
  assert.match(current, /27.*2026.*01:52.*Colombia/);
  assert.match(old, /7.*2026.*06:42.*Colombia/);
  assert.notEqual(current, old);
  assert.equal(output.archiveCopyLabel(undefined), null);
  assert.equal(output.archiveCopyLabel('invalid'), null);
});
test('same-title versions remain distinguishable when archive minutes or short identity fragments collide', () => {
  const first = 'a'.repeat(48) + '1111' + 'c'.repeat(12);
  const second = 'b'.repeat(48) + '2222' + 'c'.repeat(12);
  assert.equal(output.archiveVersionLabel(first, [first]), null);
  assert.equal(output.archiveVersionLabel(first, [first, second]), 'Copia 1111' + 'c'.repeat(12));
  assert.notEqual(output.archiveVersionLabel(first, [first, second]), output.archiveVersionLabel(second, [first, second]));
  const zero = '0'.repeat(64), one = '0'.repeat(63) + '1';
  assert.notEqual(output.archiveVersionLabel(zero, [zero, one]), output.archiveVersionLabel(one, [zero, one]));
});
