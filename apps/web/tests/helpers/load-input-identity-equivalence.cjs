const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

module.exports = function loadInputIdentityEquivalence() {
  const source = fs.readFileSync(path.join(__dirname,
    '../../src/lib/input-identity-equivalence.ts'), 'utf8');
  const equivalences = JSON.parse(fs.readFileSync(path.join(__dirname,
    '../../../../shared/input-identity-equivalences.json'), 'utf8'));
  const exports = {};
  const output = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
  } }).outputText;
  vm.runInNewContext(output, { exports, require(name) {
    if (name === '../../../../shared/input-identity-equivalences.json') return { default: equivalences };
    throw new Error(`Unexpected input identity import ${name}`);
  } });
  return exports;
};
