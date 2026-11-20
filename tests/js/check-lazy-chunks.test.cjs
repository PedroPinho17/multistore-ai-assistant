// Testes do frontend/scripts/check-lazy-chunks.mjs (o passo de CI que garante que o Chart.js
// fica fora do código de arranque), com builds falsos numa pasta temporária.
// O pytest corre-os (tests/unit/test_js.py), se houver node instalado.
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const SCRIPT = path.join(__dirname, "..", "..", "frontend", "scripts", "check-lazy-chunks.mjs");
const MARKER = 'throw new Error("Failed to create chart: Canvas is already in use.")';
const CHARTJS = `export const Chart=class{};${MARKER};`;

/** Writes a fake Vite build: index.html (entry index.js) plus assets/<name>: <code>. */
function build(assets, { html } = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "lazy-chunks-"));
  fs.mkdirSync(path.join(dir, "assets"));
  for (const [name, code] of Object.entries(assets)) fs.writeFileSync(path.join(dir, "assets", name), code);
  fs.writeFileSync(path.join(dir, "index.html"), html ??
    '<!doctype html><html><head><script src="/theme-boot.js"></script>' +
    '<script type="module" crossorigin src="/assets/index.js"></script></head><body><div id="app"></div></body></html>');
  return dir;
}

function check(dir) {
  const run = spawnSync(process.execPath, [SCRIPT, dir], { encoding: "utf8" });
  fs.rmSync(dir, { recursive: true, force: true });
  return { code: run.status, out: run.stdout + run.stderr };
}

// A build like Vite's: the shell loads Chart.js with import(); the entry imports a vendor chunk
const lazyBuild = extra => build({
  "index.js": 'import{a as e}from"./vendor.js";const s=()=>import("./AppShell.js");' + (extra || ""),
  "vendor.js": "export const a=1;",
  "AppShell.js": "function G(){return import(`./chartjs-D4x9.js`).then(e=>e.Chart)}export{G};",
  "chartjs-D4x9.js": CHARTJS,
});

test("passes when Chart.js is only loaded with import()", () => {
  const { code, out } = check(lazyBuild());
  assert.equal(code, 0, out);
  assert.match(out, /start-up = assets\/index\.js, assets\/vendor\.js;/);   // the static import was followed
  assert.match(out, /only in lazy chartjs-D4x9\.js/);
});

test("every static import form the bundler writes is followed", () => {
  const forms = [
    'import{Chart as Z}from"./chartjs-D4x9.js";',
    "import { Chart } from './chartjs-D4x9.js';",
    'import*as n from"./chartjs-D4x9.js";',
    'import Z from"./chartjs-D4x9.js";',
    'import"./chartjs-D4x9.js";',
    'export{Chart}from"./chartjs-D4x9.js";',
    'export*from"./chartjs-D4x9.js";',
    'const x=1;\nimport"./chartjs-D4x9.js";',
  ];
  for (const form of forms) {
    const { code, out } = check(build({ "index.js": form + "console.log(1);", "chartjs-D4x9.js": CHARTJS }));
    assert.equal(code, 1, `not caught: ${form}\n${out}`);
    assert.match(out, /imports the Chart\.js chunk \(chartjs-D4x9\.js\)/);
  }
});

test("dynamic imports and preload maps are not followed (that is the lazy loading)", () => {
  for (const lazy of [
    'const c=()=>import("./chartjs-D4x9.js");',
    "const c=()=>import(`./chartjs-D4x9.js`);",
    'const c=()=>import ( "./chartjs-D4x9.js" );',
    'const m=["assets/chartjs-D4x9.js"];',
  ]) {
    const { code, out } = check(build({ "index.js": lazy, "chartjs-D4x9.js": CHARTJS }));
    assert.equal(code, 0, `${lazy}\n${out}`);
  }
});

test("Chart.js reached through a chain of static imports is caught", () => {
  const { code, out } = check(build({
    "index.js": 'import"./a.js";',
    "a.js": 'export{b}from"./b.js";',
    "b.js": `export const b=1;${MARKER}`,          // Chart.js code bundled into another chunk
  }));
  assert.equal(code, 1, out);
  assert.match(out, /Chart\.js code is in a start-up chunk \(b\.js\)/);
});

test("a modulepreload link to the Chart.js chunk is caught", () => {
  const html = '<script type="module" src="/assets/index.js"></script>' +
    '<link rel="modulepreload" crossorigin href="/assets/chartjs-D4x9.js">';
  const { code, out } = check(build({ "index.js": "1;", "chartjs-D4x9.js": CHARTJS }, { html }));
  assert.equal(code, 1, out);
  assert.match(out, /chartjs-D4x9\.js/);
});

test("fails loudly instead of passing when the check cannot work", () => {
  const noMarker = check(build({ "index.js": 'const c=()=>import("./chart.js");', "chart.js": "export const Chart=1;" }));
  assert.equal(noMarker.code, 1);
  assert.match(noMarker.out, /update CHARTJS_MARKER/);           // Chart.js changed its texts

  const noEntry = check(build({ "index.js": "1;" }, { html: "<html><body>no scripts</body></html>" }));
  assert.equal(noEntry.code, 1);
  assert.match(noEntry.out, /no module entry script/);           // e.g. the Vite base changed

  const missing = check(build({ "index.js": 'import"./gone.js";', "chartjs-D4x9.js": CHARTJS }));
  assert.equal(missing.code, 1);
  assert.match(missing.out, /missing chunk assets\/gone\.js/);
});
