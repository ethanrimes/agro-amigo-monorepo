const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const ts = require("typescript");
const root = path.resolve(__dirname, "..");
const lib = path.join(root, "src/lib");
function load(file, cache = new Map()) {
  const full = path.resolve(lib, file);
  if (full.endsWith(".json")) return JSON.parse(fs.readFileSync(full, "utf8"));
  if (cache.has(full)) return cache.get(full);
  const exports = {};
  cache.set(full, exports);
  const code = ts.transpileModule(fs.readFileSync(full, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
      esModuleInterop: true, resolveJsonModule: true },
  }).outputText;
  new Function("exports", "require", code)(exports, (name) => {
    if (name.startsWith(".")) return load(path.relative(lib,
      path.resolve(path.dirname(full), name) + (path.extname(name) ? "" : ".ts")), cache);
    return require(name);
  });
  return exports;
}
const { wagePaymentBasis, wagePresentationDisplay, wageRateUnitDisplay, wageChartLabel, wageBasisNote } =
  load("wage-basis-display.ts");
const sourceFixture = JSON.parse(fs.readFileSync(
  path.join(__dirname, "fixtures/dane-wage-basis-source.json"), "utf8"));
const journalFixture = JSON.parse(fs.readFileSync(
  path.join(__dirname, "fixtures/dane-jornal-jun-2018-source.json"), "utf8"));

test("explicit DANE wage headings display month/week basis without changing source prices or selectors", () => {
  assert.equal(sourceFixture.source_witness_sha256,
    "aef5e1b3dde931a484d3091dc25dabf45db7e0e2f357b8ac517226ac7ebf1b5f");
  assert.equal(sourceFixture.source.document_id, "758e774879ddbf3b7242a4cf18e39ad31c128c055f73bdefe54387c668799ae6");
  assert.equal(sourceFixture.source.date, "2012-09-30");
  assert.equal(sourceFixture.source.page, 67);
  assert.equal(sourceFixture.source.raw_presentation, "Jornal");
  const monthly = sourceFixture.examples.find((row) => row.name === "Mensual agrícola sin alimentación");
  assert.ok(monthly);
  assert.equal(monthly.market, "Duitama");
  assert.equal(monthly.price_cop, "566700.0");
  assert.equal(wagePaymentBasis(monthly.name, sourceFixture.source.raw_presentation), "mes");
  assert.equal(wagePresentationDisplay(monthly.name, sourceFixture.source.raw_presentation), "Pago mensual · sin alimentación");
  assert.equal(wageRateUnitDisplay(monthly.name, sourceFixture.source.raw_presentation), "COP / mes · sin alimentación");
  assert.equal(wageChartLabel(monthly.name, sourceFixture.source.raw_presentation), "Pago mensual · sin alimentación");
  assert.equal(wageBasisNote(monthly.name, sourceFixture.source.raw_presentation),
    "Pago mensual según el encabezado de la fuente");
  const weeklyRows = sourceFixture.examples.filter((row) => row.name.startsWith("Semanal "));
  assert.deepEqual(weeklyRows.map((row) => row.price_cop), ["127500.0", "161000.0"]);
  for (const weekly of weeklyRows) {
    assert.equal(wagePaymentBasis(weekly.name, sourceFixture.source.raw_presentation), "semana");
    assert.equal(wagePresentationDisplay(weekly.name, sourceFixture.source.raw_presentation),
      weekly.name.endsWith("con alimentación") ? "Pago semanal · con alimentación"
        : weekly.name.endsWith("sin alimentación") ? "Pago semanal · sin alimentación" : "Pago semanal");
    assert.match(weekly.source_locator, /^PDF page 67,/);
  }
  assert.equal(sourceFixture.source.raw_presentation, "Jornal");
});

test("explicit wage name families require an exact supported presentation", () => {
  assert.equal(wagePaymentBasis("  MENSUAL   AGRICOLA sin alimentación ", " JORNAL "), "mes");
  assert.equal(wagePaymentBasis("Semanal pecuario", "jornal"), "semana");
  assert.equal(wagePaymentBasis("Jornal agrícola", "Jornal"), "jornal");
  for (const [name, presentation] of [
    ["Mensual agrícolaExtra", "Jornal"],
    ["Mensual agrícola", "Jornales"],
    ["Mensual agrícola", "Jornal por día"],
    ["Mensual comercial", "Jornal"],
    ["Mensual agrícola", "Kilogramo"],
  ]) assert.equal(wagePaymentBasis(name, presentation), null, `${name} / ${presentation}`);
});

test("ordinary chart headings, labels, and rate units retain their established wording", () => {
  assert.equal(wagePresentationDisplay("Calarca de insumos", "Bulto"), "Bulto");
  assert.equal(wageRateUnitDisplay("Calarca de insumos", "Bulto"), "COP / Bulto");
  assert.equal(wageChartLabel("Calarca de insumos", "Bulto"), "Precio por Bulto");
  assert.equal(wageBasisNote("Calarca de insumos", "Bulto"), null);
});

test("June 2018 source witness supports a jornal basis without inferring hours or daily conversion", () => {
  assert.equal(journalFixture.document_id,
    "f7c3eaed266bec96f8290e5aa0b81af45fca529c1d78468fe920527c302c899c");
  assert.equal(journalFixture.source_bytes_sha256, journalFixture.document_id);
  assert.equal(journalFixture.input_id, "jornal-agricola-sin-alimentacion");
  assert.equal(journalFixture.source_date, "2018-06-30");
  assert.equal(journalFixture.source_locator, "PDF page 153,col 2,y 436.0; inputs-pdf-v14");
  assert.equal(journalFixture.printed_table, "Cuadro 15. Precios de jornales");
  assert.equal(journalFixture.printed_period, "2018 (junio)");
  assert.equal(journalFixture.printed_section, "Jornal agrícola, sin alimentación (continuación)");
  assert.equal(journalFixture.printed_market, "Chinchiná (Caldas)");
  assert.equal(journalFixture.printed_mean_june, "35.000");
  assert.equal(journalFixture.price_cop, "35000");
  assert.equal(journalFixture.printed_variation_percent, "0,0");
  assert.equal(wagePaymentBasis(journalFixture.input_name, journalFixture.raw_presentation), "jornal");
  assert.equal(wagePresentationDisplay(journalFixture.input_name, journalFixture.raw_presentation),
    "Pago por jornal · sin alimentación");
  assert.equal(wageRateUnitDisplay(journalFixture.input_name, journalFixture.raw_presentation),
    "COP / jornal · sin alimentación");
  assert.equal(wageChartLabel(journalFixture.input_name, journalFixture.raw_presentation),
    "Pago por jornal · sin alimentación");
  assert.match(wageBasisNote(journalFixture.input_name, journalFixture.raw_presentation), /por jornal/u);
  assert.match(wageBasisNote(journalFixture.input_name, journalFixture.raw_presentation), /no especifica.*horas/u);
});

test("explicit wage names accept only Jornal or the two printed meal descriptors", () => {
  const cases = [
    ["Jornal agrícola", "Jornal", "jornal"],
    ["Jornal pecuario", "Jornal", "jornal"],
    ["Jornal agrícola", "con alimentación", "jornal"],
    ["Jornal agrícola", "sin alimentación", "jornal"],
    ["Jornal pecuario sin alimentación", "sin alimentación", "jornal"],
    ["Mensual agrícola sin alimentación", "Jornal", "mes"],
    ["Mensual pecuario", "Jornal", "mes"],
    ["Semanal agrícola con alimentación", "Jornal", "semana"],
    ["Semanal pecuario", "Jornal", "semana"],
  ];
  for (const [name, presentation, expected] of cases) {
    assert.equal(wagePaymentBasis(name, presentation), expected, `${name} / ${presentation}`);
  }
  assert.equal(wagePresentationDisplay("Jornal agrícola", "con alimentación"),
    "Pago por jornal · con alimentación");
  assert.equal(wagePresentationDisplay("Jornal agrícola", "Jornal"), "Pago por jornal");
  assert.equal(wageRateUnitDisplay("Jornal pecuario", "Jornal"), "COP / jornal");
  assert.equal(wagePresentationDisplay("Jornal agrícola", "sin alimentación"),
    "Pago por jornal · sin alimentación");
  assert.equal(wageRateUnitDisplay("Jornal pecuario", "con alimentación"),
    "COP / jornal · con alimentación");
  assert.equal(wagePresentationDisplay("Semanal agrícola con alimentación", "Jornal"),
    "Pago semanal · con alimentación");
  assert.equal(wageRateUnitDisplay("Mensual agrícola sin alimentación", "Jornal"),
    "COP / mes · sin alimentación");
  assert.equal(wagePaymentBasis("Mensual agrícola", "sin alimentación"), "mes");
  assert.equal(wagePaymentBasis("Semanal pecuario", "con alimentación"), "semana");
});

test("wage basis remains null for unrelated names, near-match presentations, and ordinary units", () => {
  for (const [name, presentation] of [
    ["Jornal agrícola", "Kilogramo"],
    ["Jornal comercial", "Jornal"],
    ["Jornal agrícola extra", "Jornal"],
    ["Mensual comercial", "Jornal"],
    ["Jornal agrícola", "Jornales"],
    ["Jornal agrícola", "Jornal por día"],
    ["Jornal pecuario", "con comida"],
    ["Jornal pecuario", "Sin alimento"],
    ["Jornal agrícola", "Unidad"],
  ]) assert.equal(wagePaymentBasis(name, presentation), null, `${name} / ${presentation}`);
  assert.equal(wagePresentationDisplay("Jornal agrícola", "Kilogramo"), "Kilogramo");
  assert.equal(wageRateUnitDisplay("Jornal agrícola", "Kilogramo"), "COP / Kilogramo");
  assert.equal(wageChartLabel("Jornal agrícola", "Kilogramo"), "Precio por Kilogramo");
});


test("source-backed comma punctuation in a complete Jornal label keeps the same guarded basis", () => {
  assert.equal(journalFixture.printed_section, "Jornal agrícola, sin alimentación (continuación)");
  const sourceTuples = [
    ["Jornal agrícola, sin alimentación", "Jornal"],
    ["Jornal agrícola", "Jornal agrícola, sin alimentación"],
    ["Jornal agrícola, sin alimentación", "Jornal agrícola, sin alimentación"],
  ];
  for (const [name, presentation] of sourceTuples) {
    assert.equal(wagePaymentBasis(name, presentation), "jornal", `${name} / ${presentation}`);
    assert.equal(wagePresentationDisplay(name, presentation), "Pago por jornal · sin alimentación");
    assert.equal(wageRateUnitDisplay(name, presentation), "COP / jornal · sin alimentación");
    assert.equal(wageChartLabel(name, presentation), "Pago por jornal · sin alimentación");
  }
  for (const [name, presentation] of [
    ["Jornal agrícola cosecha de café, sin alimentación", "Jornal"],
    ["Jornal agrícola, sin alimentación", "Kilogramo"],
    ["Jornal agrícola, sin alimentación", "con alimentación"],
    ["Jornal agrícola con alimentación", "sin alimentación"],
    ["Jornal agrícola, con alimentación extra", "Jornal"],
    ["Jornal agrícola, sin alimentación", "Jornal pecuario, sin alimentación"],
    ["Jornal agrícolasin alimentación", "Jornal"],
    ["Jornal agrícola, sin alimentación extra", "Jornal"],
    ["Jornal agrícola, sin alimentación, extra", "Jornal"],
  ]) {
    assert.equal(wagePaymentBasis(name, presentation), null, `${name} / ${presentation}`);
    assert.equal(wagePresentationDisplay(name, presentation), presentation);
    assert.equal(wageRateUnitDisplay(name, presentation), `COP / ${presentation}`);
    assert.equal(wageChartLabel(name, presentation), `Precio por ${presentation}`);
  }
});

test("source-backed monthly and weekly tuples retain their cadence when meal is stored in presentation", () => {
  const monthly = sourceFixture.examples.find((row) => row.name === "Mensual agrícola sin alimentación");
  const weekly = sourceFixture.examples.find((row) => row.name === "Semanal agrícola sin alimentación");
  assert.ok(monthly && weekly);
  const tuples = [
    [monthly.name, "Jornal", "mes", "Pago mensual · sin alimentación"],
    [monthly.name, "sin alimentación", "mes", "Pago mensual · sin alimentación"],
    ["Mensual agrícola", "sin alimentación", "mes", "Pago mensual · sin alimentación"],
    ["Mensual agrícola", "Mensual agrícola, sin alimentación", "mes", "Pago mensual · sin alimentación"],
    [weekly.name, "Jornal", "semana", "Pago semanal · sin alimentación"],
    [weekly.name, "sin alimentación", "semana", "Pago semanal · sin alimentación"],
    ["Semanal agrícola", "Semanal agrícola, sin alimentación", "semana", "Pago semanal · sin alimentación"],
  ];
  for (const [name, presentation, basis, display] of tuples) {
    assert.equal(wagePaymentBasis(name, presentation), basis, `${name} / ${presentation}`);
    assert.equal(wagePresentationDisplay(name, presentation), display);
    assert.equal(wageRateUnitDisplay(name, presentation), `COP / ${basis} · sin alimentación`);
    assert.equal(wageChartLabel(name, presentation), display);
  }
  assert.equal(monthly.price_cop, "566700.0");
  assert.equal(weekly.price_cop, "161000.0");
  assert.equal(monthly.source_locator, "PDF page 67,col 2,y 468.8; inputs-pdf-v14");
  assert.equal(weekly.source_locator, "PDF page 67,col 2,y 561.8; inputs-pdf-v14");
  assert.equal(wageBasisNote("Mensual agrícola", "sin alimentación"),
    "Pago mensual según el encabezado de la fuente");
  assert.equal(wageBasisNote("Semanal agrícola", "sin alimentación"),
    "Pago semanal según el encabezado de la fuente");
});

test("cadence, family, meal, and exact word boundaries must agree", () => {
  const invalid = [
    ["Mensual agrícola sin alimentación", "con alimentación"],
    ["Semanal pecuario con alimentación", "sin alimentación"],
    ["Mensual agrícola", "Semanal agrícola, sin alimentación"],
    ["Semanal agrícola", "Semanal pecuario, sin alimentación"],
    ["Mensual agrícola", "Mensual agrícola"],
    ["Mensual agrícola sinalimentación", "Jornal"],
    ["Mensual agrícolasin alimentación", "Jornal"],
    ["Mensual agrícola, sin alimentación extra", "Jornal"],
    ["Jornal agrícola cosecha de café, sin alimentación", "Jornal"],
    ["Cosecha de café, sin alimentación", "Jornal"],
    ["Mensual agrícola sin alimentación", "Kilogramo"],
  ];
  for (const [name, presentation] of invalid) {
    assert.equal(wagePaymentBasis(name, presentation), null, `${name} / ${presentation}`);
    assert.equal(wagePresentationDisplay(name, presentation), presentation);
    assert.equal(wageRateUnitDisplay(name, presentation), `COP / ${presentation}`);
    assert.equal(wageChartLabel(name, presentation), `Precio por ${presentation}`);
  }
});
