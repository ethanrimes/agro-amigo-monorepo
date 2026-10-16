const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

module.exports = function loadCategoryPathSql() {
  const source = fs.readFileSync(path.join(__dirname,
    '../../src/lib/server/category-path-sql.ts'), 'utf8');
  const exports = {};
  const output = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
  } }).outputText;
  vm.runInNewContext(output, { exports });
  return exports;
};
