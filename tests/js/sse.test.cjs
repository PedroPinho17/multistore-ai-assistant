// Testes do parser de SSE (web/static/js/sse.js), com o test runner do node: node --test tests/js
// O pytest corre-os também (tests/unit/test_js.py), se houver node instalado.
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const { createSseParser } = require(path.join(__dirname, "..", "..", "web", "static", "js", "sse.js"));

const sse = event => `data: ${JSON.stringify(event)}\n\n`;

/** Lê o stream como o app.js: bytes aos bocados → TextDecoder(stream) → parser. */
function feed(text, sizes, { end = true } = {}) {
  const events = [], bad = [];
  const parser = createSseParser(ev => events.push(ev), raw => bad.push(raw));
  const bytes = new TextEncoder().encode(text);
  const decoder = new TextDecoder();
  let i = 0, k = 0;
  while (i < bytes.length) {
    const size = Array.isArray(sizes) ? sizes[k++ % sizes.length] : sizes;
    parser.push(decoder.decode(bytes.slice(i, i + size), { stream: true }));
    i += size;
  }
  parser.push(decoder.decode());
  if (end) parser.end();
  return { events, bad };
}

const ANSWER = [
  { type: "status", step: "classify" },
  { type: "data", kind: "sql", sql: "SELECT 1", columns: ["marca"], rows: [["BurgerLab"], ["Café Aroma"]] },
  { type: "token", text: "Duas " },
  { type: "token", text: "marcas → ≈ ok." },
  { type: "done", kind: "sql", answer: "Duas marcas → ≈ ok.", conversation_id: 7 },
];

test("eventos partidos entre leituras (até 1 byte de cada vez)", () => {
  const text = ANSWER.map(sse).join("");
  for (const sizes of [1, 2, 3, 7, [5, 1, 11, 2], 64, text.length]) {
    const { events, bad } = feed(text, sizes);
    assert.deepEqual(events, ANSWER, `blocos de ${sizes}`);
    assert.deepEqual(bad, []);
  }
});

test("o último evento sem linha em branco no fim chega no end()", () => {
  const text = ANSWER.map(sse).join("").replace(/\n\n$/, "");     // o "done" sem \n\n
  const partial = feed(text, 4, { end: false });
  assert.equal(partial.events.at(-1).type, "token");                 // antes do end(): ainda à espera
  assert.deepEqual(feed(text, 4).events, ANSWER);                     // com o end(): chega o done
  assert.deepEqual(feed(text.replace(/\n$/, ""), 4).events, ANSWER);  // nem sequer o \n final
});

test("CRLF: \\r\\n\\r\\n também separa eventos, mesmo partido entre leituras", () => {
  const crlf = ANSWER.map(e => `data: ${JSON.stringify(e)}\r\n\r\n`).join("");
  for (const sizes of [1, 2, 3, [1, 1, 2], 100]) {
    assert.deepEqual(feed(crlf, sizes).events, ANSWER, `CRLF em blocos de ${sizes}`);
  }
  const mixed = sse(ANSWER[0]) + `data: ${JSON.stringify(ANSWER[1])}\r\n\r\n` + `data: ${JSON.stringify(ANSWER[4])}\n\r\n`;
  assert.deepEqual(feed(mixed, 3).events, [ANSWER[0], ANSWER[1], ANSWER[4]]);
});

test("linhas grandes: 500 linhas com acentos e símbolos, partidas a meio dos caracteres", () => {
  const rows = Array.from({ length: 500 }, (_, i) =>
    [i, `Loja ${i} — Café Aroma São João`, i * 1.25, "→ ≈ €", null, "pão de hambúrguer".repeat(3)]);
  const big = { type: "data", kind: "sql", sql: "SELECT …", columns: ["id", "loja", "v", "s", "n", "txt"], rows };
  const text = sse(big) + sse({ type: "done", rows });
  assert.ok(text.length > 100_000);
  for (const sizes of [1, 7, 997, 16_384]) {               // 7 e 997 cortam caracteres multibyte a meio
    const { events, bad } = feed(text, sizes);
    assert.equal(events.length, 2, `blocos de ${sizes}`);
    assert.deepEqual(events[0], big);
    assert.deepEqual(events[1].rows, rows);
    assert.deepEqual(bad, []);
  }
});

test("caminho sem tokens (forecast/orders): status, data e done chegam todos", () => {
  const orders = [
    { type: "status", step: "classify" },
    { type: "status", step: "forecast" },
    { type: "data", kind: "orders", sql: null, columns: ["ingredient", "unit", "to_order"], rows: [["Pão", "un", 12]] },
    { type: "status", step: "answer" },
    { type: "done", kind: "orders", answer: "Encomenda 12 pães.", conversation_id: 99 },
  ];
  for (const sizes of [1, 9, 1000]) {
    const { events } = feed(orders.map(sse).join(""), sizes);
    assert.deepEqual(events, orders);
    assert.ok(!events.some(e => e.type === "token"));
    assert.equal(events.at(-1).answer, "Encomenda 12 pães.");          // o texto chega só no done
  }
  // e também se o done vier sem \n\n no fim
  assert.equal(feed(orders.map(sse).join("").trimEnd(), 5).events.at(-1).type, "done");
});

test("JSON inválido vai para onBadEvent e não estraga os eventos seguintes", () => {
  const text = sse(ANSWER[0]) + "data: {nao é json\n\n" + "data: [NaN]\n\n" + sse(ANSWER[4]);
  const { events, bad } = feed(text, 3);
  assert.deepEqual(events, [ANSWER[0], ANSWER[4]]);
  assert.deepEqual(bad, ["{nao é json", "[NaN]"]);     // o JSON.parse do browser recusa NaN
});

test("um erro dentro do handler sobe (não é tratado como evento inválido)", () => {
  const bad = [];
  const parser = createSseParser(ev => { if (ev.type === "done") throw new Error("bug no handler"); }, raw => bad.push(raw));
  assert.throws(() => parser.push(sse(ANSWER[4])), /bug no handler/);
  assert.deepEqual(bad, []);
  const atEnd = createSseParser(() => { throw new Error("bug no fim"); });
  atEnd.push(`data: ${JSON.stringify(ANSWER[4])}`);
  assert.throws(() => atEnd.end(), /bug no fim/);
});

test("comentários, keep-alives, BOM e data em várias linhas", () => {
  const text = "﻿: keep-alive\n\n" + "event: message\nid: 1\n" + sse(ANSWER[0]) +
               "data: {\"type\": \"done\",\ndata:  \"answer\": \"ok\"}\n\n" + "\n\n";
  const { events, bad } = feed(text, 2);
  assert.deepEqual(events, [ANSWER[0], { type: "done", answer: "ok" }]);
  assert.deepEqual(bad, []);
});

test("um evento grande em bocados pequenos não custa O(n²)", () => {
  // Antes: 400 KB em blocos de 16 caracteres demoravam 1,6 s (e 1,6 MB ~26 s). Agora ~30 ms.
  const event = { type: "data", s: "x".repeat(1_600_000) };
  const text = sse(event);
  let got = null;
  const parser = createSseParser(ev => { got = ev; });
  const start = performance.now();
  for (let i = 0; i < text.length; i += 16) parser.push(text.slice(i, i + 16));
  const ms = performance.now() - start;
  assert.equal(got.s.length, 1_600_000);
  assert.ok(ms < 2000, `demorou ${ms.toFixed(0)} ms`);
});
