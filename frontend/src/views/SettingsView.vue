<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import AppShell from '@/components/AppShell.vue'
import LangPicker from '@/components/LangPicker.vue'
import { api } from '@/api/client'
import type { AppSettingsMeta } from '@/api/types'
import { ApiError } from '@/api/types'
import type { Lang } from '@/i18n/types'
import {
  ACCENTS,
  accentSwatchStyle,
  customPalette,
  isCustomAccent,
} from '@/lib/accent'
import { dateFmt } from '@/lib/format'
import { prefs } from '@/lib/storage'
import { LOCALES } from '@/i18n/types'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'

const auth = useAuthStore()
const ui = useUiStore()
const { user } = storeToRefs(auth)
const { t, themePref, lang, effectiveAccent, appConfig } = storeToRefs(ui)

const appForm = ref<AppSettingsMeta['values'] | null>(null)
const appMeta = ref<AppSettingsMeta | null>(null)
const appSaving = ref(false)

const accents = ACCENTS
const appDirty = computed(() => {
  const f = appForm.value
  const v = appMeta.value?.values
  return !!(f && v && Object.keys(f).some(k => f[k as keyof typeof f] !== v[k as keyof typeof v]))
})

function customHex(value: string) {
  return isCustomAccent(value) ? value : prefs.get('customAccent') || '#0f7a5a'
}
function customAdjusted(value: string) {
  return isCustomAccent(value) && customPalette(value).adjusted
}

function previewCustom(hex: string) {
  ui.setAccent(hex.toLowerCase(), false)
}
function saveCustom(hex: string) {
  const h = hex.toLowerCase()
  prefs.set('customAccent', h)
  ui.setAccent(h, true)
}

async function loadAppSettings() {
  if (user.value?.role !== 'admin') return
  try {
    appMeta.value = await api<AppSettingsMeta>('/settings/app')
    appForm.value = { ...appMeta.value.values }
  } catch (e) {
    ui.toast(e instanceof ApiError ? e.message : String(e))
  }
}

async function saveAppSettings() {
  if (!appForm.value || !appMeta.value) return
  const changes = Object.fromEntries(
    Object.entries(appForm.value).filter(
      ([k, v]) => v !== appMeta.value!.values[k as keyof typeof appForm.value],
    ),
  )
  if (!Object.keys(changes).length) return
  appSaving.value = true
  try {
    appMeta.value = await api<AppSettingsMeta>('/settings/app', changes, 'PUT')
    appForm.value = { ...appMeta.value.values }
    ui.appConfig = {
      ...ui.appConfig,
      default_accent: appForm.value.default_accent,
      default_lang: appForm.value.default_lang,
      show_demo_accounts: appForm.value.show_demo_accounts,
    }
    ui.toast(ui.t.st.appSaved, 'ok')
  } catch (e) {
    ui.toast(e instanceof ApiError ? e.message : String(e))
  } finally {
    appSaving.value = false
  }
}

function lastChangeText() {
  const m = appMeta.value
  if (!m || !m.updated_at) return t.value.st.never
  const when =
    dateFmt(m.updated_at, lang.value) +
    ' ' +
    new Date(m.updated_at).toLocaleTimeString(LOCALES[lang.value], {
      hour: '2-digit',
      minute: '2-digit',
    })
  return m.updated_by
    ? t.value.st.lastChange(m.updated_by, when)
    : t.value.st.lastChange(when, '').replace(/ · $/, '')
}

watch(
  () => ui.t.pageTitles.settings,
  title => {
    document.title = title
  },
  { immediate: true },
)
watch(
  () => [t.value.st.title, t.value.st.sub] as const,
  ([title, sub]) => ui.setPageMeta(title, sub, 'none'),
  { immediate: true },
)

onMounted(() => {
  void loadAppSettings()
})
</script>

<template>
  <AppShell>
    <div class="page-scroll">
      <main v-if="user" class="page">
        <section class="card" aria-labelledby="st-look">
          <h2 id="st-look" class="sec">{{ t.st.appearance }}</h2>
          <div class="set-row">
            <div>
              <strong id="st-theme">{{ t.theme }}</strong>
              <p>{{ t.st.themeHint }}</p>
            </div>
            <div class="segmented" role="group" aria-labelledby="st-theme">
              <button
                type="button"
                :aria-pressed="themePref === 'light' ? 'true' : 'false'"
                @click="ui.setTheme('light')"
              >
                <svg class="i" aria-hidden="true"><use href="#i-sun" /></svg> {{ t.st.light }}
              </button>
              <button
                type="button"
                :aria-pressed="themePref === 'dark' ? 'true' : 'false'"
                @click="ui.setTheme('dark')"
              >
                <svg class="i" aria-hidden="true"><use href="#i-moon" /></svg> {{ t.st.dark }}
              </button>
              <button
                type="button"
                :aria-pressed="themePref === 'system' ? 'true' : 'false'"
                @click="ui.setTheme('system')"
              >
                <svg class="i" aria-hidden="true"><use href="#i-monitor" /></svg> {{ t.st.system }}
              </button>
            </div>
          </div>
          <div class="set-row column">
            <div>
              <strong id="st-accent">{{ t.st.accent }}</strong>
              <p>{{ t.st.accentHint }}</p>
            </div>
            <div class="swatches" role="radiogroup" aria-labelledby="st-accent">
              <button
                v-for="a in accents"
                :key="a"
                type="button"
                role="radio"
                class="swatch"
                :aria-checked="effectiveAccent === a ? 'true' : 'false'"
                @click="ui.setAccent(a)"
              >
                <span class="sw-dot" :style="accentSwatchStyle(a)"></span>
                {{ t.st.accents[a] }}
                <svg v-if="effectiveAccent === a" class="i" aria-hidden="true"
                  ><use href="#i-check"
                /></svg>
                <span v-else-if="a === appConfig.default_accent" class="tag-def">{{
                  t.st.defaultTag
                }}</span>
              </button>
              <label class="swatch" :class="{ 'is-on': isCustomAccent(String(effectiveAccent)) }">
                <input
                  id="accent-custom"
                  name="accent-custom"
                  type="color"
                  class="sw-color"
                  :value="customHex(String(effectiveAccent))"
                  :aria-label="t.st.pickColor"
                  @input="previewCustom(($event.target as HTMLInputElement).value)"
                  @change="saveCustom(($event.target as HTMLInputElement).value)"
                />
                <span>{{ t.st.custom }}</span>
                <svg
                  v-if="isCustomAccent(String(effectiveAccent))"
                  class="i"
                  aria-hidden="true"
                  ><use href="#i-check"
                /></svg>
                <svg v-else class="i sw-edit" aria-hidden="true"><use href="#i-edit" /></svg>
              </label>
            </div>
            <p v-if="customAdjusted(String(effectiveAccent))" class="help adjusted">
              <svg class="i" aria-hidden="true"><use href="#i-alert" /></svg> {{ t.st.adjusted }}
            </p>
            <div class="preview" :aria-label="t.st.preview">
              <button type="button" class="btn sm" tabindex="-1">{{ t.st.previewBtn }}</button>
              <span class="chip-role">{{ t.roles[user.role] }}</span>
              <span class="bubble-demo">{{ t.st.previewMsg }}</span>
              <a href="#" tabindex="-1" @click.prevent>{{ t.st.preview }}</a>
            </div>
          </div>
          <div class="set-row">
            <div>
              <strong>{{ t.language }}</strong>
              <p>{{ t.st.langHint }}</p>
            </div>
            <LangPicker
              :model-value="lang"
              :label="t.language"
              @update:model-value="(l: Lang) => auth.persistLangSetting(l)"
            />
          </div>
          <div class="set-foot">
            <span class="help">{{ t.st.sub }}</span>
            <button type="button" class="btn-soft sm" @click="ui.resetSettings(!!auth.token)">
              <svg class="i" aria-hidden="true"><use href="#i-refresh" /></svg> {{ t.st.reset }}
            </button>
          </div>
        </section>

        <section v-if="user.role === 'admin' && appForm" class="card" aria-labelledby="st-app">
          <h2 id="st-app" class="sec">{{ t.st.appTitle }}</h2>
          <p class="sec-sub">{{ t.st.appSub }}</p>
          <div class="set-row column">
            <div>
              <strong id="st-def-accent">{{ t.st.defAccent }}</strong>
            </div>
            <div class="swatches" role="radiogroup" aria-labelledby="st-def-accent">
              <button
                v-for="a in accents"
                :key="a"
                type="button"
                role="radio"
                class="swatch"
                :aria-checked="appForm.default_accent === a ? 'true' : 'false'"
                @click="appForm.default_accent = a"
              >
                <span class="sw-dot" :style="accentSwatchStyle(a)"></span>
                {{ t.st.accents[a] }}
                <svg v-if="appForm.default_accent === a" class="i" aria-hidden="true"
                  ><use href="#i-check"
                /></svg>
              </button>
              <label
                class="swatch"
                :class="{ 'is-on': isCustomAccent(appForm.default_accent) }"
              >
                <input
                  id="default-accent-custom"
                  type="color"
                  class="sw-color"
                  :value="customHex(appForm.default_accent)"
                  :aria-label="t.st.pickColor"
                  @input="
                    appForm.default_accent = (
                      $event.target as HTMLInputElement
                    ).value.toLowerCase()
                  "
                />
                <span>{{ t.st.custom }}</span>
                <svg
                  v-if="isCustomAccent(appForm.default_accent)"
                  class="i"
                  aria-hidden="true"
                  ><use href="#i-check"
                /></svg>
                <svg v-else class="i sw-edit" aria-hidden="true"><use href="#i-edit" /></svg>
              </label>
            </div>
          </div>
          <div class="set-row">
            <div>
              <strong>{{ t.st.defLang }}</strong>
              <p>{{ t.st.defLangHint }}</p>
            </div>
            <LangPicker v-model="appForm.default_lang" :label="t.st.defLang" />
          </div>
          <div class="set-row">
            <div>
              <strong id="st-demo">{{ t.st.demo }}</strong>
              <p>{{ t.st.demoHint }}</p>
            </div>
            <span class="switch-wrap"
              >{{ appForm.show_demo_accounts ? t.st.on : t.st.off }}
              <button
                type="button"
                role="switch"
                class="switch"
                aria-labelledby="st-demo"
                :aria-checked="appForm.show_demo_accounts ? 'true' : 'false'"
                @click="appForm.show_demo_accounts = !appForm.show_demo_accounts"
              ></button
            ></span>
          </div>
          <div class="set-row">
            <div>
              <label class="lbl" for="st-session" style="margin: 0">{{ t.st.session }}</label>
              <p>{{ t.st.sessionHint }}</p>
            </div>
            <select
              id="st-session"
              v-model.number="appForm.session_hours"
              name="session-hours"
              class="input"
            >
              <option
                v-for="h in appMeta?.options.session_hours || []"
                :key="h"
                :value="h"
              >
                {{ t.st.hours(h) }}
              </option>
            </select>
          </div>
          <div class="set-foot">
            <span class="help">{{ lastChangeText() }}</span>
            <button
              type="button"
              class="btn btn-primary sm"
              :disabled="!appDirty || appSaving"
              @click="saveAppSettings"
            >
              <span v-if="appSaving" class="spinner" aria-hidden="true"></span>
              {{ t.st.save }}
            </button>
          </div>
        </section>
      </main>
    </div>
  </AppShell>
</template>
