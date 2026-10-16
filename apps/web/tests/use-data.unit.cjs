// Offline hook-state regression for the sandbox where loopback servers are denied.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const ts = require("typescript");

const helperSource = fs.readFileSync(
  path.join(__dirname, "../src/lib/client/fetch-json.ts"), "utf8",
);
const helperCompiled = ts.transpileModule(helperSource, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const hookSource = fs.readFileSync(
  process.env.USE_DATA_SOURCE || path.join(__dirname, "../src/components/marketplace/useData.ts"), "utf8",
);
const hookCompiled = ts.transpileModule(hookSource, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;

function loadJsonHelper(fetchImpl) {
  const moduleRef = { exports: {} };
  new Function("exports", "fetch", helperCompiled)(moduleRef.exports, fetchImpl);
  return moduleRef.exports;
}

function createHookHarness({ fetchJsonImpl, fetchImpl } = {}) {
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
  const fetch = fetchImpl || ((requestUrl, options) => new Promise((resolve, reject) => {
    const request = { url: requestUrl, signal: options.signal, resolve, reject };
    requests.push(request);
    options.signal.addEventListener("abort", () => {
      const error = new Error("Aborted");
      error.name = "AbortError";
      reject(error);
    }, { once: true });
  }));
  const helper = fetchJsonImpl ? { ...fetchJsonImpl } : loadJsonHelper(fetch);
  const moduleRef = { exports: {} };
  new Function("exports", "require", hookCompiled)(moduleRef.exports, (name) => {
    if (name === "react") return { useState, useEffect };
    if (name === "@/lib/client/fetch-json") return helper;
    return require(name);
  });
  return {
    requests,
    render(url, timeoutMs) {
      cursor = 0;
      return moduleRef.exports.useData(url, timeoutMs);
    },
    commit() {
      for (const { index, callback, deps } of scheduled) {
        effects[index]?.cleanup?.();
        effects[index] = { deps, cleanup: callback() };
      }
      scheduled = [];
    },
    async settle(index, status, payload) {
      requests[index].resolve({ ok: status < 400, json: async () => payload });
      await new Promise((resolve) => setImmediate(resolve));
      await new Promise((resolve) => setImmediate(resolve));
    },
  };
}

test("catalog URL identity protects success, HTTP errors, retries, cancellation and disabled URLs", async () => {
  const hook = createHookHarness();
  assert.equal(hook.render("/a").loading, true);
  hook.commit();
  await hook.settle(0, 200, { value: "A" });
  assert.equal(hook.render("/a").data.value, "A");

  let state = hook.render("/b"); // before passive effect cleanup
  assert.equal(state.loading, true);
  assert.equal(state.data, null, "old successful response must not render for B");
  hook.commit();
  await hook.settle(1, 503, { error: "B failed" });
  state = hook.render("/b");
  assert.equal(state.error, "B failed");
  state.retry();
  state = hook.render("/b"); // identical URL, new request version
  assert.equal(state.loading, true);
  assert.equal(state.error, "", "old error must clear at retry render");
  hook.commit();
  await hook.settle(2, 200, { value: "B" });
  assert.equal(hook.render("/b").data.value, "B");

  hook.render("/c");
  hook.commit();
  assert.equal(hook.requests.length, 4);
  state = hook.render("/a");
  assert.equal(state.data, null, "old A data must not reappear on URL return");
  hook.commit();
  assert.equal(hook.requests[3].signal.aborted, true);
  await hook.settle(3, 200, { value: "late C" });
  assert.equal(hook.render("/a").data, null, "aborted response must not paint A");
  await hook.settle(4, 200, { value: "fresh A" });
  assert.equal(hook.render("/a").data.value, "fresh A");
  assert.equal(hook.render(null).loading, false);
  assert.equal(hook.render(null).data, null);
  hook.commit();
  assert.equal(hook.render("/a").loading, true, "re-enabled URL must fetch afresh");
});

test("a timed-out catalog request exposes a localized, retryable hook error", async () => {
  const helperTypes = loadJsonHelper(async () => { throw new Error("not used"); });
  const hook = createHookHarness({ fetchJsonImpl: {
    fetchJson: () => Promise.reject(new helperTypes.JsonFetchTimeoutError()),
    JsonFetchTimeoutError: helperTypes.JsonFetchTimeoutError,
    JsonResponseParseError: helperTypes.JsonResponseParseError,
  } });
  hook.render("/slow");
  hook.commit();
  await new Promise((resolve) => setImmediate(resolve));
  const state = hook.render("/slow");
  assert.equal(state.loading, false);
  assert.equal(state.error, "La consulta tardó demasiado. Revisa tu conexión e intenta de nuevo.");
  state.retry();
  assert.equal(hook.render("/slow").loading, true);
});

test("a source-preview deadline can change without exposing an earlier result or disabling cancellation", async () => {
  const hook = createHookHarness();
  hook.render("/workbook", 15);
  hook.commit();
  await new Promise((resolve) => setTimeout(resolve, 35));
  assert.equal(hook.render("/workbook", 15).loading, false);
  assert.match(hook.render("/workbook", 15).error, /tardó demasiado/);
  assert.equal(hook.requests[0].signal.aborted, true);

  const fresh = hook.render("/workbook", 60_000);
  assert.equal(fresh.loading, true);
  assert.equal(fresh.error, "");
  hook.commit();
  await hook.settle(1, 200, { row: 602025, kilograms: 5000 });
  assert.equal(hook.render("/workbook", 60_000).data.kilograms, 5000);

  hook.render("/next-sheet", 60_000);
  hook.commit();
  hook.render(null, 60_000);
  hook.commit();
  assert.equal(hook.requests[2].signal.aborted, true);
  assert.equal(hook.render(null, 60_000).data, null);
});
