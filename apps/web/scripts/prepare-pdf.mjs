import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { mkdir, copyFile, cp } from "node:fs/promises";
const require = createRequire(import.meta.url),
  root = dirname(require.resolve("pdfjs-dist/package.json"));
const target = new URL("../public/pdfjs/", import.meta.url);
await mkdir(target, { recursive: true });
await copyFile(
  join(root, "legacy/build/pdf.worker.min.mjs"),
  new URL("pdf.worker.min.mjs", target),
);
for (const folder of ["standard_fonts", "wasm", "cmaps"])
  await cp(join(root, folder), new URL(folder + "/", target), {
    recursive: true,
  });
// MapLibre 6 requires an explicit worker URL in Next.js and its shared sibling.
const mapRoot = dirname(require.resolve("maplibre-gl/package.json"));
const mapTarget = new URL("../public/maplibre/", import.meta.url);
await mkdir(mapTarget, { recursive: true });
for (const file of ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"])
  await copyFile(join(mapRoot, "dist", file), new URL(file, mapTarget));
