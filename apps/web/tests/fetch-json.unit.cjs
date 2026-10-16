const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const ts = require("typescript");

const source = fs.readFileSync(path.join(__dirname, "../src/lib/client/fetch-json.ts"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;

function load(fetchImpl) {
  const moduleRef = { exports: {} };
  new Function("exports", "fetch", compiled)(moduleRef.exports, fetchImpl);
  return moduleRef.exports;
}

function aborted(signal) {
  return new Promise((_resolve, reject) => {
    const fail = () => {
      const error = new Error("Aborted");
      error.name = "AbortError";
      reject(error);
    };
    if (signal.aborted) fail();
    else signal.addEventListener("abort", fail, { once: true });
  });
}

test("fetch JSON enforces the 30-second default and times out a hanging response body", async () => {
  let requestSignal;
  let bodySawAbort = false;
  const { fetchJson, JSON_FETCH_TIMEOUT_MS, JsonFetchTimeoutError } = load(async (_input, init) => {
    requestSignal = init.signal;
    return {
      ok: true,
      json: () => new Promise(() => {
        requestSignal.addEventListener("abort", () => { bodySawAbort = true; }, { once: true });
      }),
    };
  });
  assert.equal(JSON_FETCH_TIMEOUT_MS, 30_000);
  await assert.rejects(fetchJson("/slow", {}, 15), JsonFetchTimeoutError);
  assert.equal(bodySawAbort, true, "timeout must abort body consumption too");
  assert.equal(requestSignal.aborted, true);
});

test("fetch timeout also releases a request that never returns headers", async () => {
  let requestSignal;
  const { fetchJson, JsonFetchTimeoutError } = load((_input, init) => {
    requestSignal = init.signal;
    return aborted(requestSignal);
  });
  await assert.rejects(fetchJson("/no-headers", {}, 15), JsonFetchTimeoutError);
  assert.equal(requestSignal.aborted, true);
});

test("caller cancellation remains AbortError and clears the pending timeout", async () => {
  const caller = new AbortController();
  let requestSignal;
  const { fetchJson, JsonFetchTimeoutError } = load((_input, init) => {
    requestSignal = init.signal;
    return aborted(requestSignal);
  });
  const pending = fetchJson("/old-filter", { signal: caller.signal }, 25);
  caller.abort();
  await assert.rejects(pending, (error) => error.name === "AbortError" && !(error instanceof JsonFetchTimeoutError));
  await new Promise((resolve) => setTimeout(resolve, 40));
  assert.equal(requestSignal.aborted, true);
});

test("success clears timeout and caller listener; HTTP JSON remains available to the caller", async () => {
  const caller = new AbortController();
  const originalAdd = caller.signal.addEventListener.bind(caller.signal);
  const originalRemove = caller.signal.removeEventListener.bind(caller.signal);
  let adds = 0;
  let removes = 0;
  caller.signal.addEventListener = (...args) => { adds++; return originalAdd(...args); };
  caller.signal.removeEventListener = (...args) => { removes++; return originalRemove(...args); };
  let requestSignal;
  const { fetchJson } = load(async (_input, init) => {
    requestSignal = init.signal;
    return { ok: false, status: 503, json: async () => ({ error: "Server busy" }) };
  });
  const result = await fetchJson("/http-error", { signal: caller.signal }, 15);
  await new Promise((resolve) => setTimeout(resolve, 25));
  assert.equal(result.response.status, 503);
  assert.deepEqual(result.data, { error: "Server busy" });
  assert.equal(requestSignal.aborted, false, "completed success must clear its timer");
  assert.equal(adds, 1);
  assert.equal(removes, 1);
});

test("malformed JSON is distinguishable while preserving its parse cause", async () => {
  const { fetchJson, JsonResponseParseError } = load(async () => ({
    ok: true,
    json: async () => { throw new SyntaxError("bad json"); },
  }));
  await assert.rejects(fetchJson("/bad-json", {}, 100), (error) =>
    error instanceof JsonResponseParseError && error.cause instanceof SyntaxError && error.cause.message === "bad json");
});
