<script setup lang="ts">
import { nextTick, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import LangPicker from '@/components/LangPicker.vue'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import type { Lang } from '@/i18n/types'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const ui = useUiStore()
const { rp } = storeToRefs(auth)
const { t, theme, lang } = storeToRefs(ui)

watch(
  () => ui.t.pageTitles.reset,
  title => {
    document.title = title
  },
  { immediate: true },
)

onMounted(() => {
  const hash = new URLSearchParams((route.hash || '').replace(/^#/, ''))
  const token =
    hash.get('token') ||
    (typeof route.query.token === 'string' ? route.query.token : '') ||
    ''
  auth.initResetToken(token)
  if (route.query.token || route.hash) {
    void router.replace({ name: 'reset' })
  }
  void nextTick(() => document.getElementById('rp-new')?.focus())
})

function setLang(l: Lang) {
  ui.setLang(l)
}
</script>

<template>
  <main class="auth">
    <div class="auth-box">
      <a href="/" class="auth-brand"
        ><svg class="logo-mark" aria-hidden="true"><use href="#logo" /></svg
        ><strong>Multistore AI</strong></a
      >

      <div v-if="rp.done" class="auth-form">
        <h1>{{ t.l.rpDoneTitle }}</h1>
        <p class="ok-msg" role="status">✅ {{ t.l.rpDone }}</p>
        <RouterLink class="btn primary auth-cta" to="/login">{{ t.login }}</RouterLink>
      </div>

      <div v-else-if="!rp.token" class="auth-form">
        <h1>{{ t.l.rpTitle }}</h1>
        <p class="error" role="alert">{{ t.l.rpNoToken }}</p>
        <RouterLink class="link-btn auth-link" to="/login">← {{ t.l.fpBack }}</RouterLink>
      </div>

      <form v-else class="auth-form" novalidate @submit.prevent="auth.submitReset()">
        <h1>{{ t.l.rpTitle }}</h1>
        <p class="sub">{{ t.l.rpSub }}</p>

        <label for="rp-new">{{ t.p.pwNew }}</label>
        <div class="field">
          <input
            id="rp-new"
            v-model="rp.pass"
            name="new-password"
            :type="rp.show ? 'text' : 'password'"
            autocomplete="new-password"
            maxlength="128"
            aria-describedby="rp-rules"
          />
          <button
            type="button"
            class="eye"
            :aria-pressed="rp.show ? 'true' : 'false'"
            :aria-label="rp.show ? t.l.hide : t.l.show"
            :title="rp.show ? t.l.hide : t.l.show"
            aria-controls="rp-new"
            @click="rp.show = !rp.show"
          >
            <svg class="i" aria-hidden="true">
              <use :href="rp.show ? '#i-eyeoff' : '#i-eye'" />
            </svg>
          </button>
        </div>
        <p id="rp-rules" class="strength-label">{{ t.p.pwRules }}</p>

        <label for="rp-confirm">{{ t.p.pwConfirm }}</label>
        <div class="field">
          <input
            id="rp-confirm"
            v-model="rp.confirm"
            name="confirm-password"
            :type="rp.show ? 'text' : 'password'"
            autocomplete="new-password"
            maxlength="128"
          />
        </div>

        <button class="primary" type="submit" :disabled="rp.saving || !rp.pass || !rp.confirm">
          <span v-if="rp.saving" class="spinner" aria-hidden="true"></span> {{ t.p.pwSave }}
        </button>
        <p v-if="rp.error" class="error" role="alert">{{ rp.error }}</p>
        <RouterLink class="link-btn auth-link" to="/login">← {{ t.l.fpBack }}</RouterLink>
      </form>

      <div class="auth-foot">
        <a href="/" class="back-link">← {{ t.h.back }}</a>
        <div class="auth-tools">
          <LangPicker :model-value="lang" :label="t.language" up @update:model-value="setLang" />
          <button
            type="button"
            class="icon-btn icon-only"
            :aria-label="t.theme"
            :title="t.theme"
            @click="ui.toggleTheme()"
          >
            <svg v-if="theme === 'dark'" class="i" aria-hidden="true"><use href="#i-sun" /></svg>
            <svg v-else class="i" aria-hidden="true"><use href="#i-moon" /></svg>
          </button>
        </div>
      </div>
    </div>
  </main>
</template>
