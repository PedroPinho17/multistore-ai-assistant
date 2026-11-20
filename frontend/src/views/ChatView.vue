<script setup lang="ts">
import { nextTick, onMounted, watch } from 'vue'
import { storeToRefs } from 'pinia'
import AppShell from '@/components/AppShell.vue'
import MessageBubble from '@/components/MessageBubble.vue'
import { useAuthStore } from '@/stores/auth'
import { useChatStore } from '@/stores/chat'
import { useUiStore } from '@/stores/ui'

const auth = useAuthStore()
const chat = useChatStore()
const ui = useUiStore()
const {
  messages,
  question,
  loading,
  streaming,
  stepIndex,
  welcomeDone,
  alerts,
  alertsOpen,
  starterSuggestions,
  last,
  announce,
} = storeToRefs(chat)
const { t } = storeToRefs(ui)

watch(
  () => ui.t.pageTitles.chat,
  title => {
    document.title = title
  },
  { immediate: true },
)

watch(
  () => [chat.pageTitle, ui.t.title] as const,
  ([title, sub]) => {
    ui.setPageMeta(title, sub, 'chat')
  },
  { immediate: true },
)

onMounted(async () => {
  if (auth.token) await auth.refreshMe()
  if (!messages.value.length) chat.welcome()
  void chat.loadConversations()
  void nextTick(() => document.getElementById('question')?.focus())
})
</script>

<template>
  <AppShell>
    <main id="chat-scroll" class="chat">
      <div class="chat-inner">
        <MessageBubble v-for="m in messages" :key="m.id" :m="m" />

        <div
          v-if="!loading && last && last.done && last.suggestions && last.suggestions.length"
          class="suggestions follow"
          role="group"
          :aria-label="t.followUp"
        >
          <button
            v-for="(s, i) in last.suggestions"
            :key="s"
            type="button"
            :style="{ animationDelay: i * 80 + 'ms' }"
            @click="chat.send(s)"
          >
            {{ s }}
          </button>
        </div>

        <section
          v-if="messages.length <= 1 && welcomeDone && alerts.length"
          class="alerts-card"
          :aria-label="t.alertsTitle"
        >
          <button
            type="button"
            class="alerts-head"
            :aria-expanded="alertsOpen ? 'true' : 'false'"
            @click="alertsOpen = !alertsOpen"
          >
            <svg class="i" aria-hidden="true"><use href="#i-alert" /></svg>
            {{ t.alertsTitle }} <span class="count">{{ alerts.length }}</span>
            <span class="chev" :class="{ open: alertsOpen }" aria-hidden="true">›</span>
          </button>
          <ul v-if="alertsOpen">
            <li v-for="(a, i) in alerts" :key="i" :class="a.severity">
              <span class="dot" aria-hidden="true"></span>
              <span>{{ a.message }}</span>
            </li>
          </ul>
        </section>

        <div
          v-if="messages.length <= 1 && !loading && welcomeDone && starterSuggestions.length"
          class="suggestions"
        >
          <button
            v-for="(s, i) in starterSuggestions"
            :key="s"
            type="button"
            :style="{ animationDelay: i * 80 + 'ms' }"
            @click="chat.send(s)"
          >
            {{ s }}
          </button>
        </div>

        <div v-if="loading" class="msg bot">
          <div class="avatar" aria-hidden="true">
            <svg class="logo-mark"><use href="#logo" /></svg>
          </div>
          <div class="bubble typing" role="status">
            <span class="dots" aria-hidden="true"><span></span><span></span><span></span></span>
            <span class="step" :key="stepIndex">{{ t.steps[stepIndex] }}</span>
          </div>
        </div>
      </div>
      <div class="sr-only" aria-live="polite">{{ announce }}</div>
    </main>

    <footer class="composer">
      <div class="composer-inner">
        <textarea
          id="question"
          v-model="question"
          name="question"
          :aria-label="t.questionLabel"
          rows="1"
          maxlength="500"
          :placeholder="t.placeholder"
          :disabled="loading || streaming"
          @keydown.enter.exact.prevent="chat.send()"
          @input="chat.autoGrow()"
        ></textarea>
        <button
          class="send"
          type="button"
          :disabled="loading || streaming || !question.trim()"
          :title="t.send"
          :aria-label="t.send"
          @click="chat.send()"
        >
          <svg class="i" aria-hidden="true"><use href="#i-send" /></svg>
        </button>
      </div>
      <div class="hint">{{ t.hint }}</div>
    </footer>
  </AppShell>
</template>
