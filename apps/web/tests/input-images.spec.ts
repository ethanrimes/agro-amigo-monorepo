import { test, expect } from "@playwright/test";
import { photoFor } from "../src/lib/images";

test("nonmaterial input categories never inherit a fertilizer or liquid photograph", () => {
  for (const [name, category] of [
    ["Fumigadora plástica manual 20 litros", "Equipos y elementos agrícolas unidad"],
    ["Bovino Cebú macho 19-24 meses", "Animales vivos kilogramo"],
    ["Jornal agrícola sin alimentación", "Servicios agrícolas jornal"],
    ["Hectárea anual para papa", "Arrendamiento de tierras"],
    ["Calcio inyectable", "Medicamentos veterinarios 100 centímetros cúbicos"],
  ]) {
    const photo = photoFor(name, category, "input");
    expect(["input-neutral", "liquid-input"]).toContain(photo.key);
    expect(photo.src).toMatch(/\.svg$/);
  }
  expect(photoFor("Fumigadora 20 litros", "Equipos 20 litros", "input").key).toBe("input-neutral");
});

test("known material photos require a matching fertilizer or amendment category", () => {
  expect(photoFor("DAP 18-46-0", "Fertilizantes 50 kilogramos", "input").key).toBe("fertilizer");
  expect(photoFor("Cal dolomita", "Enmiendas 50 kilogramos", "input").key).toBe("limestone");
  expect(photoFor("Calcio inyectable", "Vitaminas 100 centímetros cúbicos", "input").key).toBe("input-neutral");
});

test("market photos identify only the photographed market", () => {
  expect(photoFor("Bogotá, Corabastos", "", "market").key).toBe("corabastos");
  expect(photoFor("Bogotá, Paloquemao", "", "market").key).toBe("paloquemao");
  expect(photoFor("Medellín, Plaza Minorista José María Villa", "", "market").key).toBe("minorista");
  expect(photoFor("Plaza Minorista de Tunja", "", "market").key).toBe("market-neutral");
  const unknown = photoFor("Cali, Galería Alameda", "", "market");
  expect(unknown.key).toBe("market-neutral");
  expect(unknown.alt).toContain("no representa Cali, Galería Alameda");
});

test("product photos distinguish seafood, green beans, and live animals", () => {
  expect(photoFor("Camarón", "Pescados").key).toBe("shrimp");
  expect(photoFor("Fríjol verde", "Verduras").key).toBe("beans-green");
  expect(photoFor("Res en pie", "Ganado").key).toBe("cattle-colombia");
  expect(photoFor("Cerdo en pie", "Carnes").key).toBe("produce-neutral");
  expect(photoFor("Pollo en pie", "Carnes").key).toBe("produce-neutral");
});

test("checked-in DANE food names use matching forms and species", () => {
  expect(photoFor("Jengibre").key).toBe("ginger");
  expect(photoFor("Acelga").key).toBe("chard");
  expect(photoFor("Papas negras otras").key).toBe("potato");
  expect(photoFor("Arveja seca importada").key).toBe("peas-dried");
  expect(photoFor("Arveja seca importada").alt).toContain("origen");
  expect(photoFor("Harinas").key).toBe("produce-neutral");
  expect(photoFor("Arveja verde").key).toBe("peas");
  expect(photoFor("Harina de trigo").key).toBe("flour");
});

test("additional catalog foods use credited family photos with form caveats", () => {
  for (const [name, key] of [
    ["Perejil", "parsley"],
    ["Haba verde", "fava-green"],
    ["Rábano rojo", "radish-red"],
    ["Tangelo", "tangelo"],
    ["Sardinas en lata", "sardines-canned"],
    ["Galletas saladas", "crackers-saltine"],
    ["Galletas dulces redondas con crema", "cookies-sandwich"],
  ]) {
    const photo = photoFor(name);
    expect(photo.key).toBe(key);
    expect(photo.alt).toContain("ilustrativa");
  }
  for (const name of ["Aceite vegetal mezcla", "Mariscos otros"]) {
    expect(photoFor(name).key).toBe("produce-neutral");
  }
});

test("generic photos disclose different cultivars, species, and commercial packs", () => {
  for (const [name, key, caveat] of [
    ["Aceite girasol", "sunflower-oil-unbranded", "refinado"],
    ["Aceite soya", "soybean-oil-unbranded", "laboratorio"],
    ["Ají topito dulce", "aji-dulce", "no acredita la variedad topito"],
    ["Ahuyamín (Sakata)", "squash-moschata", "no acredita el cultivar"],
    ["Calabaza", "squash-moschata", "no acredita el cultivar"],
    ["Cebollín chino", "chinese-chives", "especie"],
    ["Coles", "cabbage", "repollo como ejemplo"],
    ["Mayonesa doy pack", "mayonnaise-unbranded", "no representa la marca ni el empaque"],
    ["Mostaza doy pack", "mustard-unbranded", "no representa la marca ni el empaque"],
    ["Capaz Magdalena fresco", "capaz-fish", "no verifica la especie"],
    ["Cuchuco de cebada", "barley-groats", "molido"],
  ]) {
    const photo = photoFor(name);
    expect(photo.key).toBe(key);
    expect(photo.alt).toContain(caveat);
  }
  expect(photoFor("Aceite vegetal mezcla").key).toBe("produce-neutral");
});

test("named fish use credited subject photos with presentation caveats", () => {
  for (const [name, key] of [
    ["Bagre", "bagre"],
    ["Basa", "basa"],
    ["Bocachico", "bocachico"],
    ["Cachama", "cachama"],
    ["Tilapia", "tilapia"],
    ["Trucha", "trout"],
    ["Pescado seco", "dried-fish"],
  ]) {
    const photo = photoFor(name, "Pescados");
    expect(photo.key).toBe(key);
    expect(photo.alt).toContain("ilustrativa");
  }
  expect(photoFor("Mariscos otros", "Pescados").key).toBe("produce-neutral");
});
