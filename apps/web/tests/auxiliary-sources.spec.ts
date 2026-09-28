import { test, expect, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { createHash } from "node:crypto";
import type { FeatureCollection, Geometry } from "geojson";
import { departmentOutlines } from "../src/lib/map-boundaries";
import { imageLibrary, photoFor } from "../src/lib/images";
import manifest from "../src/lib/image-library.json";
import { EMPTY_PROFILE } from "../src/lib/farm-types";
const root = path.resolve(__dirname, "..");
const original = JSON.parse(fs.readFileSync(path.join(root, "public/maps/colombia-departments.json"), "utf8")) as FeatureCollection<Geometry>;
const evidence = process.env.AUX_EVIDENCE_DIR;

test("image files match their hashes and the crop selection is specific", () => {
  for (const entry of Object.values(manifest)) {
    expect(createHash("sha256").update(fs.readFileSync(path.join(root, "public", entry.src))).digest("hex")).toBe(entry.sha256);
    expect(entry.author && entry.license && entry.illustrative).toBeTruthy();
    if (!entry.source) expect(entry.license).toContain("no documentada");
  }
  for (const [name, key] of [["Café pergamino seco", "coffee-parchment"], ["Aguacate Hass", "avocado"], ["Tomate chonto", "tomato"], ["Papa superior", "potato"], ["Banano", "banana"], ["Plátano hartón", "plantain"], ["Cacao", "cacao-pods"], ["Caña de azúcar", "sugarcane-colombia"], ["Palma de aceite", "oil-palm-fruit"], ["Rosas", "rose-colombia"], ["Ganado bovino", "cattle-colombia"]]) {
    const photo = photoFor(name);
    expect(photo.key).toBe(key);
    expect(photo.src).toBe(imageLibrary[key].src);
  }
  for (const name of ["coffee", "avocado", "tomato", "potato", "banana", "plantain", "produce", "farm"]) {
    const original = fs.readFileSync(path.join(root, `public/images/${name}.jpg`));
    expect(original.subarray(0, 3).toString("hex")).toBe("ffd8ff");
  }
  expect(photoFor("Producto no identificado").key).toBe("produce-neutral");
  expect(photoFor("Café pergamino seco").alt).toContain("café pergamino");
  expect(photoFor("Sal").key).toBe("salt");
  expect(photoFor("Sal").alt).toContain("sal marina gruesa");
  expect(photoFor("Huevos frescos").key).toBe("eggs");
  expect(photoFor("Pimentón rojo").key).toBe("bell-pepper");
  expect(photoFor("Ají picante").key).toBe("produce-neutral");
  for (const name of ["Galería Alameda", "Almacafé", "Molino de arroz"]) {
    expect(photoFor(name, "", "market").key).toBe("market-neutral");
  }
  expect(photoFor("Producto cárnico desconocido", "Carnes").key).toBe("produce-neutral");
  expect(photoFor("Semilla certificada", "Semillas", "input").key).toBe("seeds-general");
  expect(photoFor("Plántula de cacao", "Material vegetal", "input").key).toBe("seedlings-general");
  expect(photoFor("Café tostado").key).toBe("coffee-roasted");
  expect(photoFor("Tomate de árbol").key).toBe("tamarillo");
  expect(photoFor("Manzana roja").key).toBe("apple");
  expect(photoFor("Cacao en polvo").key).toBe("cocoa-powder");
  expect(photoFor("Café molido").key).toBe("coffee-ground");
  expect(photoFor("Café instantáneo").key).toBe("coffee-instant");
  expect(photoFor("Atún en lata").key).toBe("tuna-canned");
  expect(photoFor("Chocolate de cacao").key).toBe("chocolate");
  expect(photoFor("Palma").key).toBe("oil-palm-fruit");
  expect(photoFor("Palmiste").key).toBe("oil-palm-fruit");
  expect(photoFor("Café · almendra sana").key).toBe("coffee-green-beans");
  expect(photoFor("Café colombiano excelso · ex-dock").key).toBe("coffee-green-beans");
  expect(photoFor("Rosa híbrida de té · RED VARIETIES 50 cm").key).toBe("rose-red-cut");
  expect(photoFor("Ganado flaco en pie · hembras").key).toBe("cattle-colombia");
  expect(photoFor("Ganado gordo en pie").key).toBe("cattle-colombia");
  expect(photoFor("Azúcar blanca").key).toBe("sugar");
  expect(photoFor("Aceite de palma").key).toBe("palm-oil-unbranded");
  expect(photoFor("Aceite vegetal").key).toBe("produce-neutral");
  expect(photoFor("Pimentón verde").key).toBe("bell-pepper-green");
  expect(photoFor("Pimentón rojo").key).toBe("bell-pepper");
  expect(photoFor("Café · incentivo a la calidad").key).toBe("produce-neutral");
  expect(photoFor("Fríjol rosado").key).toBe("beans");
});

test("actual outlines lose only the degenerate island; original and two valid islands remain exact", () => {
  const before = JSON.stringify(original);
  const result = departmentOutlines(original);
  expect(result.rejectedPolygons).toBe(1);
  expect(result.data.features).toHaveLength(33);
  for (const source of original.features) {
    const after = result.data.features.find(f => f.properties!.DPTO === source.properties!.DPTO)!;
    if (source.properties!.DPTO !== "88") expect(after).toEqual(source);
    else {
      const coordinates = (source.geometry as any).coordinates;
      expect(coordinates[1]).toEqual([[[-81.37, 13.386], [-81.37, 13.386]]]);
      expect((after.geometry as any).coordinates).toEqual([coordinates[0], coordinates[2]]);
    }
  }
  expect(JSON.stringify(original)).toBe(before);
});

test("invalid polygons are rejected rather than repaired; valid holes stay exact", () => {
  const outer = [[0, 0], [4, 0], [4, 4], [0, 0]];
  const hole = [[2, 1], [3, 1], [3, 2], [2, 1]];
  for (const invalid of [ [[1, 1], [1, 1]], [[0, 0], [1, 1], [2, 2], [0, 0]], [[0, 0], [4, 0], [4, 4], [1, 1]], [[0, 0], [NaN, 0], [4, 4], [0, 0]], [[0, 0], [181, 0], [4, 4], [0, 0]] ]) {
    const data: FeatureCollection<Geometry> = { type: "FeatureCollection", features: [{ type: "Feature", properties: {}, geometry: { type: "MultiPolygon", coordinates: [[outer, hole], [invalid]] } }] };
    const result = departmentOutlines(data);
    expect(result.rejectedPolygons).toBe(1);
    expect((result.data.features[0].geometry as any).coordinates).toEqual([[outer, hole]]);
  }
});

async function mockApi(page: Page) {
  await page.route("**/api/**", route => {
    const p = new URL(route.request().url()).pathname;
    const json = p === "/api/catalog" ? { products: [], categories: [], regions: [], total: 0, has_more: false } :
      p === "/api/explore/map" ? { points: [], unit: "", date: null, basis: "Synthetic empty data fixture", filters: {} } : [];
    return route.fulfill({ json });
  });
}
async function shot(page: Page, name: string) {
  if (evidence) {
    fs.mkdirSync(evidence, { recursive: true });
    await page.screenshot({ path: path.join(evidence, `${test.info().project.name}-${name}.png`), fullPage: true });
  }
}

test("browser: credited crop and Colombian context photos load with source details", async ({ page }) => {
  await mockApi(page);
  await page.goto("/credits");
  for (const key of ["apple", "blueberry", "farm-colombia", "produce-colombia", "coffee-parchment", "coffee-ground", "coffee-instant", "cocoa-powder", "peas-dried", "tuna-canned", "sardines-canned", "crackers-saltine", "cookies-sandwich", "parsley", "fava-green", "radish-red", "tangelo", "potato", "seeds-general", "seedlings-general", "cacao-pods", "sugarcane-colombia", "oil-palm-fruit", "palm-oil-unbranded", "rose-colombia", "rose-red-cut", "cattle-colombia", "coffee-green-beans", "bell-pepper-green"]) {
    const entry = imageLibrary[key];
    const article = page.locator(".credits-grid article").filter({ has: page.getByRole("heading", { name: entry.title, exact: true }) });
    await article.scrollIntoViewIfNeeded();
    await expect(article).toContainText(entry.author);
    await expect(article.getByRole("link", { name: "Ver origen de la imagen" })).toHaveAttribute("href", entry.source);
    if (entry.modifications) await expect(article).toContainText(entry.modifications);
    await expect.poll(() => article.locator("img").evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true);
  }
  await shot(page, "credits");
  await page.goto("/");
  await expect(page.locator(".home-hero img")).toHaveAttribute("src", imageLibrary["farm-colombia"].src);
  await expect(page.locator('.home-section[href="/products"] img')).toHaveAttribute("src", imageLibrary["produce-colombia"].src);
  await expect(page.locator('.home-section[href="/insumos"] img')).toHaveAttribute("src", imageLibrary["seeds-general"].src);
  await expect.poll(() => page.locator(".home-hero img").evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true);
  await shot(page, "home");
});

test("browser: map preserves valid island parts and discloses unverified outline provenance", async ({ page }) => {
  test.setTimeout(90_000);
  await mockApi(page);
  await page.goto("/markets");
  await page.getByRole("button", { name: "Ver mapa", exact: true }).click();
  await expect(page.locator(".colombia-map")).toHaveAttribute("data-outline-features", "33");
  await expect(page.locator(".colombia-map")).toHaveAttribute("data-outline-rejected", "1");
  await expect(page.locator(".colombia-map")).toHaveAttribute("data-ready", "true");
  const note = page.locator(".map-outline-note");
  await note.scrollIntoViewIfNeeded();
  await expect(note).toContainText("procedencia del archivo no está verificada");
  await expect(note).toContainText("no define linderos");
  expect(await note.evaluate(el => el.getBoundingClientRect().height)).toBeGreaterThan(20);
  await shot(page, "map");
});

for (const point of [
  { name: "Synthetic Pitalito", latitude: 1.912345, longitude: -76.123456, accuracy: 18.4 },
  { name: "Synthetic Medellín", latitude: 6.244212, longitude: -75.581245, accuracy: 250 },
]) test(`browser: disclosure, coordinate order and preserved synthetic state ${point.name}`, async ({ page }) => {
  await mockApi(page);
  const profile = { ...EMPTY_PROFILE, name: point.name, latitude: point.latitude.toFixed(6), longitude: point.longitude.toFixed(6), locationMethod: "gps", locationAccuracy: String(point.accuracy) };
  const state = JSON.stringify({ version: 2, activeId: "synthetic", farms: [{ id: "synthetic", profile, crops: [], selectedCropId: "" }, { id: "other", profile: { ...EMPTY_PROFILE, name: "Other preserved farm" }, crops: [], selectedCropId: "" }] });
  await page.addInitScript(state => { localStorage.setItem("agroamigo-farms-v2", state); localStorage.setItem("aux-test-unrelated", "preserve-me"); }, state);
  const requests: URL[] = [];
  page.on("request", request => { if (request.url().includes("/api/planning/weather?")) requests.push(new URL(request.url())); });
  await page.route("**/api/planning/weather?**", route => route.fulfill({ status: 503, json: { error: "Synthetic unavailable provider; no live request made" } }));
  await page.goto("/farm");
  const note = page.locator(".location-workspace > .privacy-note");
  await expect(note).toContainText("servidor de AgroAmigo y a Open-Meteo");
  await expect(page.locator(".location-place")).toContainText(`${point.latitude.toFixed(6)}, ${point.longitude.toFixed(6)}`);
  await expect(page.locator(".location-place")).toContainText(`±${Math.round(point.accuracy)} m`);
  await expect.poll(() => requests.some(r => r.searchParams.get("lat") === String(point.latitude) && r.searchParams.get("lon") === String(point.longitude))).toBe(true);
  expect(await page.evaluate(() => localStorage.getItem("agroamigo-farms-v2"))).toBe(state);
  expect(await page.evaluate(() => localStorage.getItem("aux-test-unrelated"))).toBe("preserve-me");
  await note.scrollIntoViewIfNeeded();
  await shot(page, point.name.replace(/\W/g, "-"));
});
