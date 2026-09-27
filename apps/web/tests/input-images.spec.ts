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
