/* Parser de Server-Sent Events (o /ask/stream), sem dependências do Vue nem do browser:
 * o app.js usa-o e os testes correm-no com node (tests/js/sse.test.cjs).
 *
 *   const parser = createSseParser(onEvent, onBadEvent);
 *   parser.push(textoDecodificado);   // quantas vezes for preciso, aos bocados
 *   parser.end();                     // no fim do stream: processa o que sobrou
 *
 * - Os eventos separam-se por uma linha em branco: "\n\n" ou "\r\n\r\n" (a especificação aceita os dois).
 * - Um evento pode chegar partido entre leituras: fica no buffer até chegar o separador.
 * - O último evento pode vir sem a linha em branco final: o end() processa-o.
 * - Só os erros do JSON.parse são apanhados (vão para onBadEvent). Um erro dentro do onEvent
 *   sobe para quem chamou push()/end(): um bug no tratamento de um evento não se pode
 *   disfarçar de "evento inválido" (antes, um erro ao tratar o "done" virava "erro de rede").
 */
"use strict";

function createSseParser(onEvent, onBadEvent) {
  const separator = /\r?\n\r?\n/g;      // um por parser: o lastIndex é estado
  // O texto por tratar fica em pedaços (parts) e só se junta quando chega um separador: com um
  // buffer += texto e um regex sobre o buffer inteiro em cada push, um evento grande que chega
  // em muitos bocados pequenos custava O(n²) (400 KB em blocos de 16 caracteres: 1,6 s).
  let parts = [];
  let tail = "";                         // últimos 3 caracteres: um "\r\n\r\n" pode começar no bocado anterior
  let first = true;

  function dispatch(block) {
    if (first) { block = block.replace(/^﻿/, ""); first = false; }      // BOM no início do stream
    // Campo "data:" (pode haver várias linhas, juntam-se com \n); comentários (":") e outros campos ignoram-se
    const lines = block.split(/\r?\n/).filter(l => l.startsWith("data:"));
    if (!lines.length) return;
    const data = lines.map(l => l.slice(5).replace(/^ /, "")).join("\n");
    if (!data.trim()) return;
    let event;
    try {
      event = JSON.parse(data);
    } catch (err) {
      if (onBadEvent) onBadEvent(data, err);
      return;
    }
    onEvent(event);                       // fora do try: os erros do handler sobem
  }

  return {
    push(text) {
      if (!text) return;
      // Há algum separador no texto novo (ou a começar nos 3 caracteres antes dele)?
      separator.lastIndex = 0;
      if (!separator.test(tail + text)) {
        parts.push(text);
        tail = (tail + text).slice(-3);
        return;
      }
      let buffer = parts.join("") + text;  // junta-se uma vez por evento, não em cada bocado
      parts = [];
      separator.lastIndex = Math.max(0, buffer.length - text.length - tail.length);
      let match;
      while ((match = separator.exec(buffer)) !== null) {
        const block = buffer.slice(0, match.index);
        buffer = buffer.slice(match.index + match[0].length);   // o bloco já saiu do buffer: é tratado agora
        separator.lastIndex = 0;
        dispatch(block);
      }
      if (buffer) parts.push(buffer);
      tail = buffer.slice(-3);
    },
    end() {
      const rest = parts.join("");
      parts = []; tail = "";
      if (rest.trim()) dispatch(rest);
    },
  };
}

if (typeof module !== "undefined" && module.exports) module.exports = { createSseParser };
