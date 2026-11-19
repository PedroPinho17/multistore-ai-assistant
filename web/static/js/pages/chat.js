/* Chat (#/chat): mensagens, gráficos, tabelas, fonte e caixa de escrita */
"use strict";

const ChatPage = {
  name: "chat-page",
  template: String.raw`
    <main class="chat" id="chat-scroll">
      <div class="chat-inner">
        <div v-for="(m, i) in messages" :key="m.id" :class="['msg', m.from]">
          <div class="avatar" aria-hidden="true"><user-avatar v-if="m.from === 'user'" :user="user" :size="34"></user-avatar><svg v-else class="logo-mark"><use href="#logo"/></svg></div>

          <div v-if="m.from === 'user'" class="bubble">
            {{ m.text }}
            <div class="meta">{{ m.time }}</div>
          </div>

          <div v-else class="bubble" :class="{ err: m.error, wide: m.done && (m.columns || m.chart) }">
            <div>{{ m.shown }}<span v-if="!m.done" class="caret"></span></div>

            <template v-if="m.done">
              <div v-if="m.chart" class="chart-box reveal"><canvas :id="'chart-' + m.id" height="140" role="img" :aria-label="chartLabel(m)"></canvas></div>

              <div v-if="m.columns && m.rows.length > 1 && m.showTable" class="table-wrap reveal">
                <table>
                  <thead><tr><th v-for="c in m.columns">{{ colName(c) }}</th></tr></thead>
                  <tbody>
                    <tr v-for="r in m.rows.slice(0, 100)">
                      <td v-for="(v, j) in r" :class="{ num: isNum(v) }">{{ format(v, colDecimals(m, j)) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <div class="actions reveal" v-if="!m.welcome && (!m.error || m.requestId)">
                <template v-if="!m.error">
                  <button v-if="m.columns && m.rows.length > 1" @click="m.showTable = !m.showTable">
                    <svg class="i" aria-hidden="true"><use href="#i-table"/></svg> {{ m.showTable ? t.hideTable : t.showTable(m.rows.length) }}</button>
                  <button v-if="m.columns && m.rows.length" @click="downloadCsv(m)"><svg class="i" aria-hidden="true"><use href="#i-download"/></svg> CSV</button>
                  <button @click="copy(m)"><svg class="i" aria-hidden="true"><use :href="m.copied ? '#i-check' : '#i-copy'"/></svg> {{ m.copied ? t.copied : t.copy }}</button>
                  <button v-if="m.sql && hasModule('teach') && !m.liked" @click="like(m)"><svg class="i" aria-hidden="true"><use href="#i-teach"/></svg> {{ t.correct }}</button>
                  <span v-if="m.liked" class="done"><svg class="i" aria-hidden="true"><use href="#i-check"/></svg> {{ t.learned }}</span>
                </template>
                <span v-if="m.requestId" class="rate" role="group" :aria-label="t.rate.label">
                  <button type="button" @click="rate(m, 1)" :aria-pressed="m.rating === 1 ? 'true' : 'false'"
                          :title="t.rate.up" :aria-label="t.rate.up"><svg class="i" aria-hidden="true"><use href="#i-up"/></svg></button>
                  <button type="button" @click="rate(m, -1)" :aria-pressed="m.rating === -1 ? 'true' : 'false'"
                          :title="t.rate.down" :aria-label="t.rate.down"><svg class="i" aria-hidden="true"><use href="#i-down"/></svg></button>
                </span>
              </div>
              <div class="source reveal" v-if="!m.error && (m.sql || m.kind === 'forecast' || m.kind === 'orders')">
                <button type="button" class="source-toggle" @click="m.showSql = !m.showSql"
                        :aria-expanded="m.showSql ? 'true' : 'false'">
                  <span :class="{ open: m.showSql }" aria-hidden="true">›</span> <svg class="i" aria-hidden="true"><use href="#i-code"/></svg> {{ t.source }}
                </button>
                <div v-if="m.showSql" class="source-box">
                  <template v-if="m.sql">
                    <div class="source-head">
                      <span>SQL<template v-if="m.columns"> · {{ t.rows(m.rows.length) }}</template><template v-if="m.cached"> · {{ t.cached }}</template></span>
                      <button @click="copySql(m)"><svg class="i" aria-hidden="true"><use :href="m.sqlCopied ? '#i-check' : '#i-copy'"/></svg> {{ m.sqlCopied ? t.copied : t.copy }}</button>
                    </div>
                    <pre>{{ m.sql }}</pre>
                    <div class="explain" v-if="m.requestId && hasModule('sql')">
                      <p v-if="m.explanation" class="explain-text"><svg class="i" aria-hidden="true"><use href="#i-sparkles"/></svg> {{ m.explanation }}</p>
                      <button v-else type="button" class="btn-ghost" @click="explain(m)" :disabled="m.explaining">
                        <svg class="i" aria-hidden="true"><use href="#i-sparkles"/></svg> {{ m.explaining ? t.explaining : t.explain }}</button>
                    </div>
                  </template>
                  <div v-else class="source-ml"><svg class="i" aria-hidden="true"><use href="#i-trend"/></svg> {{ t.mlSource }}</div>
                </div>
              </div>
            </template>
            <div class="meta">{{ m.time }}</div>
          </div>
        </div>

        <!-- Perguntas de seguimento (só na última resposta) -->
        <div class="suggestions follow" v-if="!loading && last && last.done && last.suggestions && last.suggestions.length"
             role="group" :aria-label="t.followUp">
          <button v-for="(s, i) in last.suggestions" :key="s" :style="{ animationDelay: (i * 80) + 'ms' }" @click="send(s)">{{ s }}</button>
        </div>

        <!-- Alertas automáticos no início da conversa -->
        <section class="alerts-card" v-if="messages.length <= 1 && welcomeDone && alerts.length" :aria-label="t.alertsTitle">
          <button type="button" class="alerts-head" @click="alertsOpen = !alertsOpen" :aria-expanded="alertsOpen ? 'true' : 'false'">
            <svg class="i" aria-hidden="true"><use href="#i-alert"/></svg> {{ t.alertsTitle }} <span class="count">{{ alerts.length }}</span>
            <span class="chev" :class="{ open: alertsOpen }" aria-hidden="true">›</span>
          </button>
          <ul v-if="alertsOpen">
            <li v-for="(a, i) in alerts" :key="i" :class="a.severity">
              <span class="dot" aria-hidden="true"></span>
              <span>{{ a.message }}</span>
            </li>
          </ul>
        </section>

        <!-- Sugestões no início da conversa -->
        <div class="suggestions" v-if="messages.length <= 1 && !loading && welcomeDone && starterSuggestions.length">
          <button v-for="(s, i) in starterSuggestions" :key="s" :style="{ animationDelay: (i * 80) + 'ms' }"
                  @click="send(s)">{{ s }}</button>
        </div>

        <!-- Bot a escrever -->
        <div class="msg bot" v-if="loading">
          <div class="avatar" aria-hidden="true"><svg class="logo-mark"><use href="#logo"/></svg></div>
          <div class="bubble typing" role="status">
            <span class="dots" aria-hidden="true"><span></span><span></span><span></span></span>
            <span class="step" :key="stepIndex">{{ t.steps[stepIndex] }}</span>
          </div>
        </div>
      </div>
      <!-- Leitores de ecrã: anuncia cada resposta uma vez, já completa -->
      <div class="sr-only" aria-live="polite">{{ announce }}</div>
    </main>

    <footer class="composer">
      <div class="composer-inner">
        <textarea id="question" name="question" :aria-label="t.questionLabel" v-model="question" rows="1" maxlength="500" :placeholder="t.placeholder"
                  @keydown.enter.exact.prevent="send()" @input="autoGrow" :disabled="loading"></textarea>
        <button class="send" @click="send()" :disabled="loading || !question.trim()" :title="t.send" :aria-label="t.send"><svg class="i" aria-hidden="true"><use href="#i-send"/></svg></button>
      </div>
      <div class="hint">{{ t.hint }}</div>
    </footer>
  `,
};
