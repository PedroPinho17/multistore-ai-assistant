<script setup lang="ts">
import { nextTick, onMounted, watch } from 'vue'
import type { ChatMessage } from '@/api/types'
import { chartLabel } from '@/lib/chart-data'
import { colName } from '@/lib/format'
import { useAuthStore } from '@/stores/auth'
import { useChatStore } from '@/stores/chat'
import { useUiStore } from '@/stores/ui'
import UserAvatar from '@/components/UserAvatar.vue'

const props = defineProps<{ m: ChatMessage }>()
const auth = useAuthStore()
const chat = useChatStore()
const ui = useUiStore()

function maybeDraw() {
  if (props.m.chart && props.m.done) void nextTick(() => chat.drawChart(props.m))
}

onMounted(maybeDraw)
watch(() => props.m.done, maybeDraw)
</script>

<template>
  <div :class="['msg', m.from]">
    <div class="avatar" aria-hidden="true">
      <UserAvatar v-if="m.from === 'user'" :user="auth.user" :size="34" />
      <svg v-else class="logo-mark"><use href="#logo" /></svg>
    </div>

    <div v-if="m.from === 'user'" class="bubble">
      {{ m.text }}
      <div class="meta">{{ m.time }}</div>
    </div>

    <div v-else class="bubble" :class="{ err: m.error, wide: m.done && (m.columns || m.chart) }">
      <div>
        {{ m.shown }}<span v-if="!m.done" class="caret"></span>
      </div>

      <template v-if="m.done">
        <div v-if="m.chart" class="chart-box reveal">
          <canvas
            :id="'chart-' + m.id"
            height="140"
            role="img"
            :aria-label="
              chartLabel(m, ui.lang, ui.t.chart, v => chat.format(v))
            "
          ></canvas>
        </div>

        <div v-if="m.columns && m.rows.length > 1 && m.showTable" class="table-wrap reveal">
          <table>
            <thead>
              <tr>
                <th v-for="c in m.columns" :key="c">{{ colName(c, ui.lang) }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(r, ri) in m.rows.slice(0, 100)" :key="ri">
                <td
                  v-for="(v, j) in r"
                  :key="j"
                  :class="{ num: chat.isNum(v) }"
                >
                  {{ chat.format(v, chat.colDecimals(m, j as number)) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="actions reveal" v-if="!m.welcome && (!m.error || m.requestId)">
          <template v-if="!m.error">
            <button
              v-if="m.columns && m.rows.length > 1"
              type="button"
              @click="m.showTable = !m.showTable"
            >
              <svg class="i" aria-hidden="true"><use href="#i-table" /></svg>
              {{ m.showTable ? ui.t.hideTable : ui.t.showTable(m.rows.length) }}
            </button>
            <button
              v-if="m.columns && m.rows.length"
              type="button"
              @click="chat.downloadCsv(m)"
            >
              <svg class="i" aria-hidden="true"><use href="#i-download" /></svg> CSV
            </button>
            <button type="button" @click="chat.copy(m)">
              <svg class="i" aria-hidden="true">
                <use :href="m.copied ? '#i-check' : '#i-copy'" />
              </svg>
              {{ m.copied ? ui.t.copied : ui.t.copy }}
            </button>
            <button
              v-if="m.sql && auth.hasModule('teach') && !m.liked"
              type="button"
              @click="chat.like(m)"
            >
              <svg class="i" aria-hidden="true"><use href="#i-teach" /></svg> {{ ui.t.correct }}
            </button>
            <span v-if="m.liked" class="done">
              <svg class="i" aria-hidden="true"><use href="#i-check" /></svg> {{ ui.t.learned }}
            </span>
          </template>
          <span v-if="m.requestId" class="rate" role="group" :aria-label="ui.t.rate.label">
            <button
              type="button"
              :aria-pressed="m.rating === 1 ? 'true' : 'false'"
              :title="ui.t.rate.up"
              :aria-label="ui.t.rate.up"
              @click="chat.rate(m, 1)"
            >
              <svg class="i" aria-hidden="true"><use href="#i-up" /></svg>
            </button>
            <button
              type="button"
              :aria-pressed="m.rating === -1 ? 'true' : 'false'"
              :title="ui.t.rate.down"
              :aria-label="ui.t.rate.down"
              @click="chat.rate(m, -1)"
            >
              <svg class="i" aria-hidden="true"><use href="#i-down" /></svg>
            </button>
          </span>
        </div>

        <div
          class="source reveal"
          v-if="!m.error && (m.sql || m.kind === 'forecast' || m.kind === 'orders')"
        >
          <button
            type="button"
            class="source-toggle"
            :aria-expanded="m.showSql ? 'true' : 'false'"
            @click="m.showSql = !m.showSql"
          >
            <span :class="{ open: m.showSql }" aria-hidden="true">›</span>
            <svg class="i" aria-hidden="true"><use href="#i-code" /></svg> {{ ui.t.source }}
          </button>
          <div v-if="m.showSql" class="source-box">
            <template v-if="m.sql">
              <div class="source-head">
                <span
                  >SQL<template v-if="m.columns"> · {{ ui.t.rows(m.rows.length) }}</template
                  ><template v-if="m.cached"> · {{ ui.t.cached }}</template></span
                >
                <button type="button" @click="chat.copySql(m)">
                  <svg class="i" aria-hidden="true">
                    <use :href="m.sqlCopied ? '#i-check' : '#i-copy'" />
                  </svg>
                  {{ m.sqlCopied ? ui.t.copied : ui.t.copy }}
                </button>
              </div>
              <pre>{{ m.sql }}</pre>
              <div class="explain" v-if="m.requestId && auth.hasModule('sql')">
                <p v-if="m.explanation" class="explain-text">
                  <svg class="i" aria-hidden="true"><use href="#i-sparkles" /></svg>
                  {{ m.explanation }}
                </p>
                <button
                  v-else
                  type="button"
                  class="btn-ghost"
                  :disabled="m.explaining"
                  @click="chat.explain(m)"
                >
                  <svg class="i" aria-hidden="true"><use href="#i-sparkles" /></svg>
                  {{ m.explaining ? ui.t.explaining : ui.t.explain }}
                </button>
              </div>
            </template>
            <div v-else class="source-ml">
              <svg class="i" aria-hidden="true"><use href="#i-trend" /></svg> {{ ui.t.mlSource }}
            </div>
          </div>
        </div>
      </template>
      <div class="meta">{{ m.time }}</div>
    </div>
  </div>
</template>
