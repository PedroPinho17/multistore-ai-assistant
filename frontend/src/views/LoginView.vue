<script setup lang="ts">
import { nextTick, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import LangPicker from '@/components/LangPicker.vue'
import { DEMO_ACCOUNTS } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import type { Lang } from '@/i18n/types'

const router = useRouter()
const auth = useAuthStore()
const ui = useUiStore()
const {
  username,
  password,
  loginError,
  loggingIn,
  shake,
  showPassword,
  capsLock,
  fp,
} = storeToRefs(auth)
const { t, theme, lang, showDemo } = storeToRefs(ui)

watch(
  () => ui.t.pageTitles.login,
  title => {
    document.title = title
  },
  { immediate: true },
)

onMounted(() => {
  void nextTick(() => document.getElementById('u')?.focus())
})

function setLang(l: Lang) {
  ui.setLang(l)
}
</script>

<template>
  <main class="auth">
    <div class="auth-box" :class="{ shake }">
      <a href="/" class="auth-brand"
        ><svg class="logo-mark" aria-hidden="true"><use href="#logo" /></svg
        ><strong>Multistore AI</strong></a
      >

      <form v-if="fp.open" class="auth-form" novalidate @submit.prevent="auth.sendForgot()">
        <h1>{{ t.l.fpTitle }}</h1>
        <template v-if="!fp.sent">
          <p class="sub">{{ t.l.fpSub }}</p>
          <label for="fp-login">{{ t.l.fpLabel }}</label>
          <div class="field">
            <span class="field-icon" aria-hidden="true">
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <rect x="3" y="5" width="18" height="14" rx="2" />
                <path d="m3 7 9 6 9-6" />
              </svg>
            </span>
            <input
              id="fp-login"
              v-model.trim="fp.login"
              name="email"
              type="text"
              inputmode="email"
              maxlength="254"
              autocomplete="email"
              autocapitalize="none"
              spellcheck="false"
              :placeholder="t.l.fpPh"
            />
          </div>
          <button class="primary" type="submit" :disabled="fp.sending || fp.login.length < 3">
            <span v-if="fp.sending" class="spinner" aria-hidden="true"></span> {{ t.l.fpSend }}
          </button>
          <p v-if="fp.error" class="error" role="alert">{{ fp.error }}</p>
          <p class="auth-note">{{ t.l.fpDemoNote }}</p>
        </template>
        <p v-else class="ok-msg" role="status">✅ {{ t.l.fpSent }}</p>
        <button type="button" class="link-btn auth-link" @click="auth.closeForgot()">
          ← {{ t.l.fpBack }}
        </button>
      </form>

      <form v-else class="auth-form" novalidate @submit.prevent="auth.login(router)">
        <h1>{{ t.l.welcome }}</h1>
        <p class="sub">{{ t.l.sub }}</p>

        <label for="u">{{ t.username }}</label>
        <div class="field">
          <span class="field-icon" aria-hidden="true">
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <circle cx="12" cy="8" r="4" />
              <path d="M4 21c0-4 4-6 8-6s8 2 8 6" />
            </svg>
          </span>
          <input
            id="u"
            v-model.trim="username"
            name="username"
            autocomplete="username"
            maxlength="64"
            :placeholder="t.l.userPh"
            autofocus
          />
        </div>

        <label for="p">{{ t.password }}</label>
        <div class="field">
          <span class="field-icon" aria-hidden="true">
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <rect x="4" y="11" width="16" height="10" rx="2" />
              <path d="M8 11V7a4 4 0 0 1 8 0v4" />
            </svg>
          </span>
          <input
            id="p"
            v-model="password"
            name="password"
            :type="showPassword ? 'text' : 'password'"
            autocomplete="current-password"
            maxlength="128"
            :placeholder="t.l.passPh"
            @keydown="auth.checkCaps"
            @keyup="auth.checkCaps"
          />
          <button
            type="button"
            class="eye"
            :aria-label="showPassword ? t.l.hide : t.l.show"
            :title="showPassword ? t.l.hide : t.l.show"
            :aria-pressed="showPassword ? 'true' : 'false'"
            aria-controls="p"
            @click="showPassword = !showPassword"
          >
            <svg
              v-if="!showPassword"
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              aria-hidden="true"
            >
              <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z" />
              <circle cx="12" cy="12" r="3" />
            </svg>
            <svg
              v-else
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              aria-hidden="true"
            >
              <path
                d="M17.9 17.9A10.4 10.4 0 0 1 12 19c-6.4 0-10-7-10-7a18.6 18.6 0 0 1 5.1-5.9M9.9 5.2A9.6 9.6 0 0 1 12 5c6.4 0 10 7 10 7a18.7 18.7 0 0 1-2.2 3.2M14.1 14.1a3 3 0 1 1-4.2-4.2M2 2l20 20"
              />
            </svg>
          </button>
        </div>
        <p v-if="capsLock" class="caps" role="status">⇪ {{ t.l.caps }}</p>

        <button class="primary" type="submit" :disabled="loggingIn || !username || !password">
          <span v-if="loggingIn" class="spinner" aria-hidden="true"></span>
          {{ loggingIn ? t.l.signingIn : t.login }}
        </button>
        <p v-if="loginError" class="error" role="alert">{{ loginError }}</p>
        <button type="button" class="link-btn auth-link" @click="auth.openForgot()">
          {{ t.l.forgot }}
        </button>
      </form>

      <div v-if="showDemo && !fp.open" class="demo-list">
        <div class="demo-list-head">
          <span>{{ t.l.demo }}</span><small>{{ t.l.demoHint }}</small>
        </div>
        <button
          v-for="d in DEMO_ACCOUNTS"
          :key="d.user"
          type="button"
          class="demo-row"
          :aria-label="t.l.useAccount + ': ' + t.roles[d.role] + ' (' + d.user + ')'"
          @click="auth.fillDemo(d)"
        >
          <svg class="i" aria-hidden="true"><use :href="'#i-' + d.icon" /></svg>
          <span>{{ t.roles[d.role] }}</span>
          <code>{{ d.user }}</code>
          <svg class="i dr-arrow" aria-hidden="true"><use href="#i-arrow" /></svg>
        </button>
      </div>

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
