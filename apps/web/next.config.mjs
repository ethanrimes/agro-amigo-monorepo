import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../..",
);
/** @type {import('next').NextConfig} */
export default {
  distDir: process.env.NEXT_DIST_DIR || ".next",
  devIndicators: false,
  output: "standalone",
  outputFileTracingRoot: root,
  poweredByHeader: false,
};
