// Publish only the installed, lockfile-pinned PDF.js runtime assets locally.
import { copyFileSync, cpSync, mkdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
const packageRoot = new URL("../node_modules/pdfjs-dist/", import.meta.url);
const { version } = JSON.parse(readFileSync(new URL("package.json", packageRoot), "utf8"));
if (!/^\d+\.\d+\.\d+$/.test(version)) throw new Error("Invalid PDF.js version");
const destination = new URL(`../public/pdfjs/${version}/`, import.meta.url);
mkdirSync(destination, { recursive: true });
copyFileSync(new URL("LICENSE", packageRoot), new URL("LICENSE", destination));
copyFileSync(new URL("build/pdf.worker.min.mjs", packageRoot), new URL("pdf.worker.min.mjs", destination));
for (const name of ["cmaps", "standard_fonts", "wasm", "iccs"]) {
  cpSync(fileURLToPath(new URL(name, packageRoot)), fileURLToPath(new URL(name, destination)), { recursive: true });
}
