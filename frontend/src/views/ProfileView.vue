<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import AppShell from '@/components/AppShell.vue'
import UserAvatar from '@/components/UserAvatar.vue'
import { ago, dateFmt, decodeJwtExp } from '@/lib/format'
import { useAuthStore } from '@/stores/auth'
import { useChatStore } from '@/stores/chat'
import { useProfileStore } from '@/stores/profile'
import { useUiStore } from '@/stores/ui'

const router = useRouter()
const auth = useAuthStore()
const profileStore = useProfileStore()
const ui = useUiStore()
const { user } = storeToRefs(auth)
const { profile, avatarSaving, clock, pw, em, pwStrength } = storeToRefs(profileStore)
const { t, lang } = storeToRefs(ui)

const chat = useChatStore()
// An answer still streaming in the chat (the user came here mid-answer)
const chatBusy = computed(() => chat.loading || chat.streaming)

const tokenExp = computed(() => decodeJwtExp(auth.token))
const sessionLeft = computed(() => {
  if (!tokenExp.value) return '—'
  const msLeft = tokenExp.value - clock.value
  if (msLeft <= 0) return t.value.p.sessionExpired
  return t.value.p.left(Math.floor(msLeft / 3600000), Math.floor((msLeft % 3600000) / 60000))
})

const scopeText = computed(() => {
  const p = t.value.p
  const pr = profile.value
  if (!user.value) return ''
  if (user.value.role === 'imperador' || user.value.role === 'admin') return p.scopeAll
  if (user.value.role === 'marca') return p.scopeBrand(pr?.brand_name || '…')
  return p.scopeStore(pr?.store_name || '…', pr?.brand_name || '…')
})

const permissions = computed(() => {
  const p = t.value.p
  const u = user.value
  const pr = profile.value
  if (!u) return []
  const n = pr?.visible_stores ?? '…'
  const boss = u.role === 'imperador' || u.role === 'admin'
  const stores = boss
    ? p.storesAll(n)
    : u.role === 'marca'
      ? p.storesBrand(n, pr?.brand_name || '…')
      : p.storesOne(pr?.store_name || '…')
  const mods = t.value.mods
  const has = (m: string) => auth.hasModule(m)
  return [
    { ok: true, text: stores },
    { ok: has('sql'), text: mods.sql },
    { ok: has('forecast'), text: mods.forecast },
    { ok: has('orders'), text: mods.orders },
    { ok: boss, text: p.purchases },
    { ok: has('teach'), text: mods.teach },
    { ok: has('users'), text: mods.users },
    ...(has('observability') ? [{ ok: true, text: mods.observability }] : []),
    { ok: false, text: p.personal },
    { ok: false, text: p.write },
  ]
})

const kindRows = computed(() => profileStore.kindRows())

watch(
  () => ui.t.pageTitles.profile,
  title => {
    document.title = title
  },
  { immediate: true },
)

watch(
  [() => t.value.p.title, scopeText],
  ([title, sub]) => ui.setPageMeta(title, sub, 'none'),
  { immediate: true },
)

onMounted(() => {
  profileStore.startClock()
  void profileStore.load()
})
onUnmounted(() => profileStore.stopClock())

function onAvatarChange(e: Event) {
  const input = e.target as HTMLInputElement
  void profileStore.uploadAvatar(input.files?.[0])
  input.value = ''
}
</script>

<template>
  <AppShell>
    <div class="page-scroll">
      <main v-if="user" class="page">
        <section class="card identity">
          <UserAvatar :user="user" :size="72" />
          <div>
            <div class="identity-name">
              {{ user.username }}
              <span class="chip-role">{{ t.roles[user.role] }}</span>
            </div>
            <p class="scope">{{ scopeText }}</p>
            <div v-if="!user.demo" class="avatar-tools">
              <label
                class="btn-soft sm"
                for="avatar-file"
                :aria-disabled="avatarSaving ? 'true' : undefined"
              >
                <svg class="i" aria-hidden="true"><use href="#i-camera" /></svg>
                {{ avatarSaving ? t.avatar.saving : t.avatar.change }}
              </label>
              <input
                id="avatar-file"
                name="avatar"
                type="file"
                accept="image/png,image/jpeg,image/webp"
                class="sr-only"
                :disabled="avatarSaving"
                @change="onAvatarChange"
              />
              <button
                v-if="user.avatar_url"
                type="button"
                class="btn-soft sm"
                :disabled="avatarSaving"
                @click="profileStore.removeAvatar()"
              >
                <svg class="i" aria-hidden="true"><use href="#i-trash" /></svg>
                {{ t.avatar.remove }}
              </button>
              <span class="help" aria-live="polite">{{
                user.avatar_url ? t.avatar.hint : t.avatar.fallback
              }}</span>
            </div>
          </div>
        </section>

        <section class="stats" :aria-label="t.p.statsTitle">
          <div class="card stat">
            <div class="label">{{ t.p.conversations }}</div>
            <div v-if="profile" class="value">{{ profile.stats.conversations }}</div>
            <div v-else class="skeleton"></div>
          </div>
          <div class="card stat">
            <div class="label">{{ t.p.questions }}</div>
            <div v-if="profile" class="value">{{ profile.stats.questions }}</div>
            <div v-else class="skeleton"></div>
          </div>
          <div class="card stat">
            <div class="label">{{ t.p.lastActivity }}</div>
            <div v-if="profile" class="value" style="font-size: 18px">
              {{
                profile.stats.last_activity
                  ? ago(profile.stats.last_activity, clock, t.p.ago)
                  : '—'
              }}
            </div>
            <div v-else class="skeleton"></div>
            <div v-if="profile?.stats.first_activity" class="hint2">
              {{ t.p.since }} {{ dateFmt(profile.stats.first_activity, lang) }}
            </div>
          </div>
          <div class="card stat">
            <div class="label">{{ t.p.session }}</div>
            <div class="value" style="font-size: 18px">{{ sessionLeft }}</div>
            <div class="hint2">{{ t.p.sessionHint }}</div>
          </div>
        </section>

        <div class="profile-cols">
          <section class="card">
            <h2>{{ t.p.permTitle }}</h2>
            <ul class="perm-list">
              <li v-for="pm in permissions" :key="pm.text" :class="pm.ok ? 'yes' : 'no'">
                <span class="ico" aria-hidden="true">{{ pm.ok ? '✓' : '✕' }}</span>
                <span
                  ><span class="sr-only"
                    >{{ pm.ok ? t.p.allowed : t.p.notAllowed }}:
                  </span>
                  {{ pm.text }}</span
                >
              </li>
            </ul>
          </section>

          <section class="card">
            <h2>{{ t.p.kindsTitle }}</h2>
            <template v-if="profile && kindRows.length">
              <div v-for="k in kindRows" :key="k.key" class="kind-row">
                <span>{{ k.label }}</span>
                <div class="kind-bar" role="img" :aria-label="k.label + ': ' + k.n">
                  <span :style="{ width: k.pct + '%' }"></span>
                </div>
                <span class="n">{{ k.n }}</span>
              </div>
            </template>
            <p v-else-if="profile" class="muted">
              {{ t.p.noActivity }} <RouterLink to="/chat">{{ t.p.startChat }}</RouterLink>
            </p>
            <div v-else class="skeleton"></div>
          </section>

          <section class="card">
            <h2>{{ t.p.pwTitle }}</h2>
            <p v-if="user.demo" class="demo-note" role="note">
              <svg class="i" aria-hidden="true"><use href="#i-lock" /></svg> {{ t.demoReadOnly }}
            </p>
            <form v-else class="form" novalidate @submit.prevent="profileStore.changePassword()">
              <label for="pw-current">{{ t.p.pwCurrent }}</label>
              <div class="field">
                <input
                  id="pw-current"
                  v-model="pw.current"
                  name="current-password"
                  :type="pw.show ? 'text' : 'password'"
                  autocomplete="current-password"
                  maxlength="128"
                />
              </div>
              <label for="pw-new">{{ t.p.pwNew }}</label>
              <div class="field">
                <input
                  id="pw-new"
                  v-model="pw.new"
                  name="new-password"
                  :type="pw.show ? 'text' : 'password'"
                  autocomplete="new-password"
                  maxlength="128"
                  aria-describedby="pw-strength"
                />
                <button
                  type="button"
                  class="eye"
                  :aria-pressed="pw.show ? 'true' : 'false'"
                  :aria-label="pw.show ? t.l.hide : t.l.show"
                  @click="pw.show = !pw.show"
                >
                  <svg v-if="!pw.show" class="i" aria-hidden="true"><use href="#i-eye" /></svg>
                  <svg v-else class="i" aria-hidden="true"><use href="#i-eyeoff" /></svg>
                </button>
              </div>
              <div class="strength" :class="'s' + pwStrength" aria-hidden="true">
                <i></i><i></i><i></i><i></i>
              </div>
              <p id="pw-strength" class="strength-label">
                {{ pw.new ? t.p.strength[pwStrength] : t.p.pwRules }}
              </p>
              <label for="pw-confirm">{{ t.p.pwConfirm }}</label>
              <div class="field">
                <input
                  id="pw-confirm"
                  v-model="pw.confirm"
                  name="confirm-password"
                  :type="pw.show ? 'text' : 'password'"
                  autocomplete="new-password"
                  maxlength="128"
                />
              </div>
              <button
                class="primary"
                type="submit"
                :disabled="pw.saving || !pw.current || !pw.new || !pw.confirm"
              >
                <span v-if="pw.saving" class="spinner" aria-hidden="true"></span>
                {{ t.p.pwSave }}
              </button>
              <p v-if="pw.error" class="error" role="alert">{{ pw.error }}</p>
              <p v-if="pw.ok" class="ok-msg" role="status">✅ {{ t.p.pwDone }}</p>
            </form>
          </section>

          <section class="card">
            <h2>{{ t.p.emailTitle }}</h2>
            <p v-if="user.demo" class="demo-note" role="note">
              <svg class="i" aria-hidden="true"><use href="#i-lock" /></svg> {{ t.p.emailDemo }}
            </p>
            <form v-else class="form" novalidate @submit.prevent="profileStore.saveEmail()">
              <p class="muted" style="margin-top: 0">{{ t.p.emailHint }}</p>
              <label for="pf-email">Email</label>
              <div class="field">
                <input
                  id="pf-email"
                  v-model="em.value"
                  name="email"
                  type="email"
                  maxlength="254"
                  autocomplete="email"
                  autocapitalize="none"
                  spellcheck="false"
                />
              </div>
              <button
                class="primary"
                type="submit"
                :disabled="em.saving || em.value.trim() === (profile?.email || '')"
              >
                <span v-if="em.saving" class="spinner" aria-hidden="true"></span>
                {{ t.p.emailSave }}
              </button>
              <p v-if="em.error" class="error" role="alert">{{ em.error }}</p>
              <p v-if="em.ok" class="ok-msg" role="status">
                ✅ {{ em.value ? t.p.emailSaved : t.p.emailRemoved }}
              </p>
            </form>
          </section>
        </div>

        <section class="card danger-zone">
          <h2 class="sec" style="margin: 0 0 6px">{{ t.p.dangerTitle }}</h2>
          <div class="row2">
            <div>
              <strong>{{ t.p.clearAll }}</strong>
              <p>{{ t.p.clearAllHint }}</p>
              <p v-if="chatBusy" class="help" role="status">{{ t.p.clearBusy }}</p>
            </div>
            <button
              type="button"
              class="btn-danger"
              :disabled="!profile || !profile.stats.conversations || chatBusy"
              @click="profileStore.deleteAllConversations()"
            >
              <svg class="i" aria-hidden="true"><use href="#i-trash" /></svg> {{ t.p.clearAll }}
            </button>
          </div>
          <div class="row2">
            <div>
              <strong>{{ t.logout }}</strong>
              <p>{{ t.p.logoutHint }}</p>
            </div>
            <button type="button" class="btn-danger" @click="auth.logout(router, 'login')">
              <svg class="i" aria-hidden="true"><use href="#i-logout" /></svg> {{ t.logout }}
            </button>
          </div>
        </section>
      </main>
    </div>
  </AppShell>
</template>
