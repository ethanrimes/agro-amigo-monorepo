const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

module.exports = function loadLabelNormalization() {
  const source = fs.readFileSync(path.join(__dirname, '../../src/lib/label-normalization.ts'), 'utf8');
  const lexicon = JSON.parse(fs.readFileSync(path.join(__dirname, '../../../../shared/label-normalization.json'), 'utf8'));
  const output = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
  } }).outputText;
  const context = { exports: {}, require(name) {
    if (name === '../../../../shared/label-normalization.json') return { default: lexicon };
    throw new Error(`Unexpected label normalization import ${name}`);
  } };
  vm.runInNewContext(output, context);
  return context.exports;
};
