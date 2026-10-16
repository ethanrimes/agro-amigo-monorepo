const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const ts = require("typescript");

const helperSource = fs.readFileSync(path.join(__dirname, "../src/lib/client/fetch-json.ts"), "utf8");
const helperCompiled = ts.transpileModule(helperSource, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const hookSource = fs.readFileSync(path.join(__dirname, "../src/components/marketplace/useCatalogPage.ts"), "utf8");
const hookCompiled = ts.transpileModule(hookSource, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const loadHelperTypes = () => {
  const moduleRef = { exports: {} };
  new Function("exports", "fetch", helperCompiled)(moduleRef.exports, async () => { throw new Error("unused"); });
  return moduleRef.exports;
};
const helperTypes = loadHelperTypes();

function createHookHarness(fetchJson) {
  const states = [];
  const effects = [];
  let cursor = 0;
  let scheduled = [];
  const requests = [];
  const useState = (initial) => {
    const index = cursor++;
    if (!(index in states)) states[index] = initial;
    return [states[index], (update) => {
      states[index] = typeof update === "function" ? update(states[index]) : update;
    }];
  };
  const useEffect = (callback, deps) => {
    const index = cursor++;
    if (!effects[index] || deps.some((dep, i) => dep !== effects[index].deps[i]))
      scheduled.push({ index, callback, deps });
  };
  const helper = {
    fetchJson: (input, init) => {
      const promise = fetchJson(input, init);
      requests.push({ input, signal: init.signal, promise });
      return promise;
    },
    JsonFetchTimeoutError: helperTypes.JsonFetchTimeoutError,
    JsonResponseParseError: helperTypes.JsonResponseParseError,
  };
  const moduleRef = { exports: {} };
  new Function("exports", "require", hookCompiled)(moduleRef.exports, (name) => {
    if (name === "react") return { useState, useEffect };
    if (name === "@/lib/client/fetch-json") return helper;
    if (name === "@/lib/catalog-types") return {};
    return require(name);
  });
  return {
    requests,
    render(body) {
      cursor = 0;
      return moduleRef.exports.useCatalogPage(body);
    },
    commit() {
      for (const { index, callback, deps } of scheduled) {
        effects[index]?.cleanup?.();
        effects[index] = { deps, cleanup: callback() };
      }
      scheduled = [];
    },
  };
}
const flush = async () => {
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));
};

test("catalog timeout shows a localized retry error and a successful retry replaces it", async () => {
  let call = 0;
  const hook = createHookHarness(async () => {
    call++;
    if (call === 1) throw new helperTypes.JsonFetchTimeoutError();
    return { response: { ok: true }, data: { products: ["fresh"] } };
  });
  hook.render('{"offset":0}');
  hook.commit();
  await flush();
  let state = hook.render('{"offset":0}');
  assert.equal(state.error, "El catálogo tardó demasiado en responder. Revisa tu conexión e intenta de nuevo.");
  state.retry();
  hook.render('{"offset":0}');
  hook.commit();
  await flush();
  state = hook.render('{"offset":0}');
  assert.deepEqual(state.data, { products: ["fresh"] });
  assert.equal(state.error, "");
  assert.equal(call, 2);
});

test("old catalog responses cannot replace a newer filter, and HTTP errors keep server messages", async () => {
  const pending = [];
  const hook = createHookHarness((_input, init) => new Promise((resolve) => pending.push({ resolve, signal: init.signal })));
  hook.render('{"offset":0}');
  hook.commit();
  hook.render('{"offset":24}');
  hook.commit();
  assert.equal(pending[0].signal.aborted, true);
  pending[0].resolve({ response: { ok: true }, data: { products: ["old"] } });
  await flush();
  assert.equal(hook.render('{"offset":24}').data, null);

  pending[1].resolve({ response: { ok: false }, data: { error: "Catalog unavailable" } });
  await flush();
  assert.equal(hook.render('{"offset":24}').error, "Catalog unavailable");
});
