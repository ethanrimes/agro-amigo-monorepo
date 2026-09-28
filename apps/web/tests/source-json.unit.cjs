const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const ts = require("typescript");
const path = require("node:path");
function sourceWith(responses) {
  const exports = {};
  let calls = 0;
  const fetch = async () => {
    const r = responses[calls++];
    if (r instanceof Error) throw r;
    return r;
  };
  vm.runInNewContext(
    ts.transpileModule(
      fs.readFileSync(
        path.join(__dirname, "../src/lib/server/source-json.ts"),
        "utf8",
      ),
      {
        compilerOptions: {
          module: ts.ModuleKind.CommonJS,
          target: ts.ScriptTarget.ES2022,
        },
      },
    ).outputText,
    { exports, fetch, AbortSignal, Error, setTimeout: (fn) => fn() },
  );
  return {
    read: () => exports.sourceJson("https://official.example/query"),
    calls: () => calls,
  };
}
test("one network timeout retries the same source and preserves its literal response", async () => {
  const e = new Error("timeout");
  e.name = "TimeoutError";
  const a = sourceWith([
    e,
    Response.json({ features: [{ attributes: { price: 1234 } }] }),
  ]);
  assert.deepEqual(JSON.parse(JSON.stringify(await a.read())), {
    features: [{ attributes: { price: 1234 } }],
  });
  assert.equal(a.calls(), 2);
});
test("HTTP503 retries once; two failures remain an error", async () => {
  const a = sourceWith([
    new Response("unavailable", { status: 503 }),
    new Response("unavailable", { status: 503 }),
  ]);
  await assert.rejects(a.read(), /entidad/);
  assert.equal(a.calls(), 2);
});
test("missing source and long rate-limit wait are not retried", async () => {
  for (const r of [
    new Response("missing", { status: 404 }),
    new Response("limited", { status: 429, headers: { "Retry-After": "120" } }),
  ]) {
    const a = sourceWith([r]);
    await assert.rejects(a.read());
    assert.equal(a.calls(), 1);
  }
});
test("HTTP200 ArcGIS error and invalid JSON never become empty records", async () => {
  for (const r of [
    Response.json({ error: { code: 400 } }),
    new Response("not JSON"),
  ]) {
    const a = sourceWith([r]);
    await assert.rejects(a.read());
    assert.equal(a.calls(), 1);
  }
});
test("valid explicit empty features remains no coverage", async () => {
  const a = sourceWith([Response.json({ features: [] })]);
  assert.deepEqual(JSON.parse(JSON.stringify(await a.read())), {
    features: [],
  });
  assert.equal(a.calls(), 1);
});

test("malformed ArcGIS features never create a retained no-coverage snapshot", async () => {
  for (const payload of [
    {},
    { features: null },
    { features: [{}] },
    { features: [{ attributes: [] }] },
  ]) {
    const exports = {};
    const queries = [];
    const database = () => ({
      query: async (sql) => {
        queries.push(sql);
        return { rows: [] };
      },
    });
    const mockedRequire = (id) => {
      if (id === "server-only") return {};
      if (id === "./db") return { database };
      if (id === "./source-json") return { sourceJson: async () => payload };
      if (id === "../planning-math") return {};
      return require(id);
    };
    vm.runInNewContext(
      ts.transpileModule(
        fs.readFileSync(
          path.join(__dirname, "../src/lib/server/location.ts"),
          "utf8",
        ),
        {
          compilerOptions: {
            module: ts.ModuleKind.CommonJS,
            target: ts.ScriptTarget.ES2022,
          },
        },
      ).outputText,
      { exports, require: mockedRequire, URL, URLSearchParams, Buffer, Error },
    );
    await assert.rejects(
      exports.spatialPoint(
        { id: "soil", service: "https://official.example", layer: 0 },
        1.912345,
        -76.123456,
        1,
      ),
      /atributos verificables/,
    );
    assert.equal(queries.length, 1);
    assert.match(queries[0], /^SELECT/);
  }
});
