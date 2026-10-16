const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

// Execute the production matcher while keeping unrelated service fixtures isolated.
module.exports = function categoryHierarchy(normalizeLabel = value => value) {
  const exports = {};
  const source = fs.readFileSync(path.join(__dirname, '../../src/lib/category-hierarchy.ts'), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
  } }).outputText;
  vm.runInNewContext(code, { exports, require: key => {
    if (key === './label-normalization') return { normalizeLabel };
    if (key === './planning-math') return { fold: value => value.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase().trim() };
    throw new Error('Unexpected category dependency ' + key);
  } });
  return exports;
};
