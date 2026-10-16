const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

function load(file, mocks = {}) {
  const exports = {};
  const js = ts.transpileModule(fs.readFileSync(file, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  vm.runInNewContext(js, { exports, require: (name) => {
    if (name in mocks) return mocks[name];
    throw new Error(`Unexpected dependency ${name}`);
  }, Set, Map });
  return exports;
}
const root = path.join(__dirname, "../src/lib");
const normalize = require("./helpers/load-label-normalization.cjs")();
const categoryPath = require("./helpers/load-category-path-sql.cjs")();
const packages = load(path.join(root, "server/city-package-equivalence.ts"), { "./category-path-sql": categoryPath });
const aliases = load(path.join(root, "server/city-market-alias.ts"), { "./category-path-sql": categoryPath });
const defaults = load(path.join(root, "product-filter-defaults.ts"));
const filters = load(path.join(root, "product-filter-dimensions.ts"), {
  "./label-normalization": normalize,
  "./product-filter-defaults": defaults,
  "./server/city-package-equivalence": packages,
  "./server/city-market-alias": aliases,
});
const plain = (value) => JSON.parse(JSON.stringify(value));
const requested = (overrides = {}) => ({
  series: "city", market: "", presentation: "Kilogramo",
  units: "1 Kilogramo", history: "all", ...overrides,
});
const dimensions = { product_id: "limon-tahiti", region: "", options: [
  { series: "city", market_id: "cucuta", market_name: "Cúcuta, Cenabastos",
    presentation: "Kilogramo", units: "1 Kilogramo",
    first_report_on: "2020-01-01", last_report_on: "2026-01-01" },
  { series: "city", market_id: "monteria", market_name: "MONTERIA, Mercado del Sur",
    presentation: "Bulto", units: "70 Kilogramo",
    first_report_on: "2020-03-25", last_report_on: "2026-08-01" },
  { series: "city", market_id: "other", market_name: "Medellín, Central Mayorista",
    presentation: "Bulto", units: "70 Kilogramo" },
  { series: "monthly", market_id: "monthly", market_name: "Cúcuta",
    presentation: "Por unidad de medida", units: "1 kg" },
] };

test("new package uses only its qualified markets and defaults while its price is pending", () => {
  const original = JSON.stringify(dimensions);
  const resolved = plain(filters.resolveProductFilterDimensions(dimensions,
    "limon-tahiti", "", requested({ presentation: "Bulto", units: "" })));
  assert.deepEqual(resolved.filters, {
    series: "city", presentation: "Bulto", units: "70 Kilogramo",
    market: "", history: "all",
  });
  assert.deepEqual(resolved.options.markets.map((market) => market.id), ["monteria", "other"]);
  assert.equal(resolved.options.markets[0].literal_name, "MONTERIA, Mercado del Sur");
  assert.equal(resolved.options.markets[0].name, "Montería, Mercado del Sur");
  assert.equal(resolved.options.markets[0].first_report_on, "2020-03-25");
  assert.equal(resolved.options.markets[0].last_report_on, "2026-08-01");
  assert.equal(JSON.stringify(dimensions), original);
});

test("an old market stays marked unavailable for the new package and can be cleared", () => {
  const resolved = plain(filters.resolveProductFilterDimensions(dimensions,
    "limon-tahiti", "", requested({ market: "cucuta", presentation: "Bulto", units: "" })));
  assert.equal(resolved.filters.units, "70 Kilogramo");
  assert.equal(resolved.filters.market, "cucuta");
  assert.match(resolved.options.markets.find((market) => market.id === "cucuta").name,
    /sin reportes para estos filtros/);
  assert.equal(filters.marketReportsForUnits(dimensions, "limon-tahiti", "", "city",
    "Bulto", "70 Kilogramo", "cucuta"), false);
  assert.equal(filters.marketReportsForUnits(dimensions, "limon-tahiti", "", "city",
    "Bulto", "70 Kilogramo", "monteria"), true);
});

test("a different product or department cannot borrow any previous choices", () => {
  assert.equal(filters.resolveProductFilterDimensions(dimensions,
    "different-product", "", requested()), null);
  assert.equal(filters.resolveProductFilterDimensions(dimensions,
    "limon-tahiti", "Córdoba", requested()), null);
  assert.equal(filters.marketReportsForUnits(dimensions, "limon-tahiti", "Córdoba", "city",
    "Bulto", "70 Kilogramo", "monteria"), false);
});

test("presentation matching keeps the server's case rule and exact units", () => {
  const result = plain(filters.resolveProductFilterDimensions(dimensions,
    "limon-tahiti", "", requested({ presentation: "bUlTo", units: "70 Kilogramo" })));
  assert.equal(result.filters.presentation, "Bulto");
  assert.equal(result.filters.units, "70 Kilogramo");
  assert.deepEqual(result.options.presentations, ["Kilogramo", "Bulto"]);
});

test("the guarded old arroz literal maps only to its exact available market package", () => {
  const rice = { product_id: "arroz-de-primera", region: "Valle del Cauca", options: [{
    series: "city", market_id: "cali", market_name: "Cali, Santa Elena",
    presentation: "Bolsa", units: "25 × 500 g",
  }] };
  const choice = requested({ market: "cali", presentation: "Bolsa", units: "25 unidades 500 gr" });
  assert.equal(filters.resolveProductFilterDimensions(rice, "arroz-de-primera",
    "Valle del Cauca", choice).filters.units, "25 × 500 g");
  assert.equal(filters.resolveProductFilterDimensions(rice, "arroz-de-primera",
    "Cauca", choice), null);
  assert.equal(filters.resolveProductFilterDimensions({ ...rice, options: [] },
    "arroz-de-primera", "Valle del Cauca", choice).filters.units, "25 unidades 500 gr");
});


test("missing package defaults use newest source date while explicit old package remains selectable", () => {
  const dated = { product_id: "limon-comun", region: "", options: [
    { series: "city", market_id: "old", market_name: "Old market",
      presentation: "Bulto", units: "69 Kilogramo",
      first_report_on: "2021-01-01", last_report_on: "2021-11-01" },
    { series: "city", market_id: "current", market_name: "Current market",
      presentation: "Bulto", units: "70 Kilogramo",
      first_report_on: "2026-10-06", last_report_on: "2026-10-06" },
  ] };
  const absent = plain(filters.resolveProductFilterDimensions(dated, "limon-comun", "",
    requested({ presentation: "", units: "", history: "recent" })));
  assert.equal(absent.filters.units, "70 Kilogramo");
  assert.deepEqual(absent.options.units, ["69 Kilogramo", "70 Kilogramo"]);
  const explicit = plain(filters.resolveProductFilterDimensions(dated, "limon-comun", "",
    requested({ presentation: "Bulto", units: "69 Kilogramo" })));
  assert.equal(explicit.filters.units, "69 Kilogramo");
  const oldMarket = plain(filters.resolveProductFilterDimensions(dated, "limon-comun", "",
    requested({ market: "old", presentation: "", units: "" })));
  assert.equal(oldMarket.filters.market, "old");
  assert.equal(oldMarket.filters.units, "69 Kilogramo");
  assert.deepEqual(oldMarket.options.markets.map(x => x.id), ["old"]);
});

test("missing presentation uses latest source report and an explicit older presentation remains", () => {
  const alternatives = { product_id: "limon-comun", region: "", options: [
    { series: "city", market_id: "a", market_name: "A", presentation: "Caja",
      units: "20 Kilogramo", last_report_on: "2021-01-01" },
    { series: "city", market_id: "a", market_name: "A", presentation: "Bulto",
      units: "70 Kilogramo", last_report_on: "2026-10-06" },
  ] };
  const omitted = plain(filters.resolveProductFilterDimensions(alternatives, "limon-comun", "",
    requested({ market: "a", presentation: "", units: "" })));
  assert.deepEqual([omitted.filters.presentation, omitted.filters.units], ["Bulto", "70 Kilogramo"]);
  const explicit = plain(filters.resolveProductFilterDimensions(alternatives, "limon-comun", "",
    requested({ market: "a", presentation: "Caja", units: "20 Kilogramo" })));
  assert.deepEqual([explicit.filters.presentation, explicit.filters.units], ["Caja", "20 Kilogramo"]);
  assert.deepEqual(explicit.options.presentations, ["Caja", "Bulto"]);
});
