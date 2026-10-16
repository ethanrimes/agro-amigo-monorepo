const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

module.exports = function loadSourceScope() {
  const source = path.join(__dirname, '../../src/lib/server/source-document-scope.ts');
  const registry = JSON.parse(fs.readFileSync(path.join(__dirname,
    '../../../../shared/source-document-scope.json'), 'utf8'));
  const output = ts.transpileModule(fs.readFileSync(source, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const result = {};
  new Function('exports', 'require', output)(result, name => {
    if (name === '../../../../../shared/source-document-scope.json') return { default: registry };
    throw new Error('Unexpected source-scope dependency ' + name);
  });
  return result;
};
