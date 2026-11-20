<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import LangPicker from '@/components/LangPicker.vue'
import UserAvatar from '@/components/UserAvatar.vue'
import { useAuthStore } from '@/stores/auth'
import { useChatStore } from '@/stores/chat'
import { useDashboardStore } from '@/stores/dashboard'
import { useAdminStore } from '@/stores/admin'
import { useReviewStore } from '@/stores/review'
import { useUsersStore } from '@/stores/users'
import { useUiStore } from '@/stores/ui'
import type { Lang } from '@/i18n/types'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const chat = useChatStore()
const dash = useDashboardStore()
const adm = useAdminStore()
const review = useReviewStore()
const users = useUsersStore()
const ui = useUiStore()
const { user } = storeToRefs(auth)
const {
  conversations,
  currentConv,
  editingId,
  editTitle,
  loading,
  streaming,
  exportingPdf,
} = storeToRefs(chat)
const { t, theme, lang, sidebarOpen, userMenu, pageTitle, pageSub, topbarActions } =
  storeToRefs(ui)
const { pending } = storeToRefs(review)

const railEl = ref<HTMLElement | null>(null)
const menuBtn = ref<HTMLButtonElement | null>(null)
const isMobile = ref(false)
let mobileMq: MediaQueryList | null = null

const view = computed(() => String(route.name || ''))
const showRecents = computed(() => view.value === 'chat')
const brandTo = computed(() => (auth.token ? '/chat' : '/'))

function setLang(l: Lang) {
  auth.persistLangSetting(l)
  ui.userMenu = false
}

function syncMobile() {
  isMobile.value = !!mobileMq?.matches
}

function onDocClick() {
  ui.userMenu = false
}

function onEsc(e: KeyboardEvent) {
  if (e.key !== 'Escape') return
  if (ui.userMenu) {
    ui.userMenu = false
    return
  }
  if (ui.sidebarOpen) {
    ui.sidebarOpen = false
  }
}

function firstFocusableInRail(): HTMLElement | null {
  return (
    railEl.value?.querySelector<HTMLElement>(
      'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ) ?? null
  )
}

watch(sidebarOpen, (open, wasOpen) => {
  if (!isMobile.value) return
  if (open) {
    void nextTick(() => firstFocusableInRail()?.focus())
  } else if (wasOpen) {
    void nextTick(() => menuBtn.value?.focus())
  }
})

onMounted(() => {
  mobileMq = window.matchMedia('(max-width: 900px)')
  syncMobile()
  mobileMq.addEventListener('change', syncMobile)
  document.addEventListener('click', onDocClick)
  document.addEventListener('keydown', onEsc)
  void review.loadCount()
})
onUnmounted(() => {
  mobileMq?.removeEventListener('change', syncMobile)
  document.removeEventListener('click', onDocClick)
  document.removeEventListener('keydown', onEsc)
})
</script>

<template>
  <div class="shell">
    <aside
      ref="railEl"
      class="rail"
      :class="{ open: sidebarOpen }"
      :aria-label="t.nav.main"
      :inert="isMobile && !sidebarOpen ? true : undefined"
      :aria-hidden="isMobile && !sidebarOpen ? 'true' : undefined"
    >
      <div class="rail-top">
        <RouterLink :to="brandTo" class="rail-brand" :title="t.h.home" @click="ui.sidebarOpen = false">
          <svg class="logo-mark" aria-hidden="true"><use href="#logo" /></svg>
          <span>Multistore AI</span>
        </RouterLink>
        <button
          type="button"
          class="icon-only rail-close"
          :aria-label="t.nav.close"
          @click="ui.sidebarOpen = false"
        >
          <svg class="i" aria-hidden="true"><use href="#i-x" /></svg>
        </button>
      </div>
      <nav class="rail-nav" :aria-label="t.nav.main">
        <RouterLink
          to="/chat"
          class="nav-item"
          active-class="active"
          :aria-current="view === 'chat' ? 'page' : undefined"
          @click="ui.sidebarOpen = false"
        >
          <svg class="i" aria-hidden="true"><use href="#i-chat" /></svg>
          <span>{{ t.nav.chat }}</span>
        </RouterLink>
        <RouterLink
          v-if="auth.hasModule('sql') || auth.hasModule('forecast')"
          to="/dashboard"
          class="nav-item"
          active-class="active"
          :aria-current="view === 'dashboard' ? 'page' : undefined"
          @click="ui.sidebarOpen = false"
        >
          <svg class="i" aria-hidden="true"><use href="#i-trend" /></svg>
          <span>{{ t.nav.dashboard }}</span>
        </RouterLink>
        <RouterLink
          v-if="auth.hasModule('users')"
          to="/users"
          class="nav-item"
          active-class="active"
          :aria-current="view === 'users' ? 'page' : undefined"
          @click="ui.sidebarOpen = false"
        >
          <svg class="i" aria-hidden="true"><use href="#i-users" /></svg>
          <span>{{ t.nav.users }}</span>
        </RouterLink>
        <RouterLink
          v-if="auth.hasModule('teach')"
          to="/review"
          class="nav-item"
          active-class="active"
          :aria-current="view === 'review' ? 'page' : undefined"
          @click="ui.sidebarOpen = false"
        >
          <svg class="i" aria-hidden="true"><use href="#i-teach" /></svg>
          <span>{{ t.nav.review }}</span>
          <span
            v-if="pending"
            class="nav-count"
            :aria-label="t.rv.pending(pending)"
            >{{ pending > 99 ? '99+' : pending }}</span
          >
        </RouterLink>
        <RouterLink
          v-if="auth.hasModule('observability')"
          to="/admin"
          class="nav-item"
          active-class="active"
          :aria-current="view === 'admin' ? 'page' : undefined"
          @click="ui.sidebarOpen = false"
        >
          <svg class="i" aria-hidden="true"><use href="#i-chart" /></svg>
          <span>{{ t.nav.admin }}</span>
        </RouterLink>
        <RouterLink
          to="/profile"
          class="nav-item"
          active-class="active"
          :aria-current="view === 'profile' ? 'page' : undefined"
          @click="ui.sidebarOpen = false"
        >
          <svg class="i" aria-hidden="true"><use href="#i-user" /></svg>
          <span>{{ t.nav.profile }}</span>
        </RouterLink>
        <RouterLink
          to="/settings"
          class="nav-item"
          active-class="active"
          :aria-current="view === 'settings' ? 'page' : undefined"
          @click="ui.sidebarOpen = false"
        >
          <svg class="i" aria-hidden="true"><use href="#i-settings" /></svg>
          <span>{{ t.nav.settings }}</span>
        </RouterLink>
      </nav>

      <div v-if="showRecents" class="rail-section">
        <div class="recents-title">{{ t.recents }}</div>
        <div class="conv-list">
          <div
            v-for="c in conversations"
            :key="c.id"
            class="conv"
            :class="{ active: c.id === currentConv }"
            @click="chat.openConversation(c.id)"
          >
            <input
              v-if="editingId === c.id"
              class="conv-edit"
              :name="'title-' + c.id"
              :aria-label="t.rename"
              v-model="editTitle"
              maxlength="80"
              @click.stop
              @keydown.enter.prevent="chat.saveTitle(c)"
              @keydown.esc="editingId = null"
              @blur="chat.saveTitle(c)"
              :ref="(el: unknown) => { (el as HTMLInputElement | null)?.focus?.() }"
            />
            <button
              v-else
              type="button"
              class="conv-title"
              :title="c.title"
              :aria-current="c.id === currentConv ? 'page' : undefined"
              @click.stop="chat.openConversation(c.id)"
            >
              {{ c.title }}
            </button>
            <button
              v-if="editingId !== c.id"
              type="button"
              class="conv-del"
              :title="t.rename"
              :aria-label="t.rename + ': ' + c.title"
              @click.stop="chat.startRename(c)"
            >
              <svg class="i" aria-hidden="true"><use href="#i-edit" /></svg>
            </button>
            <button
              v-if="editingId !== c.id"
              type="button"
              class="conv-del"
              :title="t.delete"
              :aria-label="t.delete + ': ' + c.title"
              :disabled="(loading || streaming) && c.id === currentConv"
              @click.stop="chat.deleteConversation(c)"
            >
              <svg class="i" aria-hidden="true"><use href="#i-trash" /></svg>
            </button>
          </div>
          <div v-if="!conversations.length" class="conv-empty">{{ t.noChats }}</div>
        </div>
      </div>
      <div v-else class="rail-spacer"></div>

      <div class="rail-user">
        <div
          v-if="userMenu"
          class="user-menu"
          role="menu"
          @click.stop
          @keydown.esc="ui.userMenu = false"
        >
          <div class="menu-row">
            <span
              ><svg class="i" aria-hidden="true"><use href="#i-globe" /></svg> {{ t.language }}</span
            >
            <LangPicker
              :model-value="lang"
              :label="t.language"
              compact
              up
              @update:model-value="setLang"
            />
          </div>
          <div class="menu-row">
            <span>
              <svg v-if="theme === 'dark'" class="i" aria-hidden="true"><use href="#i-sun" /></svg>
              <svg v-else class="i" aria-hidden="true"><use href="#i-moon" /></svg>
              {{ t.theme }}
            </span>
            <div class="segmented sm" role="group" :aria-label="t.theme">
              <button
                type="button"
                :aria-pressed="theme === 'light' ? 'true' : 'false'"
                :aria-label="t.p.light"
                :title="t.p.light"
                @click="ui.setTheme('light')"
              >
                <svg class="i" aria-hidden="true"><use href="#i-sun" /></svg>
              </button>
              <button
                type="button"
                :aria-pressed="theme === 'dark' ? 'true' : 'false'"
                :aria-label="t.p.dark"
                :title="t.p.dark"
                @click="ui.setTheme('dark')"
              >
                <svg class="i" aria-hidden="true"><use href="#i-moon" /></svg>
              </button>
            </div>
          </div>
          <RouterLink
            to="/settings"
            role="menuitem"
            class="menu-item"
            @click="ui.userMenu = false"
          >
            <svg class="i" aria-hidden="true"><use href="#i-settings" /></svg> {{ t.nav.settings }}
          </RouterLink>
          <RouterLink
            to="/profile"
            role="menuitem"
            class="menu-item"
            @click="ui.userMenu = false"
          >
            <svg class="i" aria-hidden="true"><use href="#i-user" /></svg> {{ t.nav.profile }}
          </RouterLink>
          <button
            type="button"
            role="menuitem"
            class="menu-item danger"
            @click="auth.logout(router, 'login')"
          >
            <svg class="i" aria-hidden="true"><use href="#i-logout" /></svg> {{ t.logout }}
          </button>
        </div>
        <button
          v-if="user"
          type="button"
          class="user-btn"
          aria-haspopup="menu"
          :aria-expanded="userMenu ? 'true' : 'false'"
          :aria-label="t.nav.account + ': ' + user.username"
          @click.stop="ui.userMenu = !ui.userMenu"
        >
          <UserAvatar :user="user" :size="32" />
          <span class="user-meta"
            ><strong>{{ user.username }}</strong
            ><small>{{ t.roles[user.role] || user.role }}</small></span
          >
          <svg class="i" aria-hidden="true"><use href="#i-updown" /></svg>
        </button>
      </div>
    </aside>
    <div v-if="sidebarOpen" class="backdrop" @click="ui.sidebarOpen = false"></div>

    <div class="main">
      <header class="topbar">
        <button
          ref="menuBtn"
          type="button"
          class="icon-only menu-btn"
          :aria-label="t.menu"
          :aria-expanded="sidebarOpen ? 'true' : 'false'"
          @click="ui.sidebarOpen = true"
        >
          <svg class="i" aria-hidden="true"><use href="#i-menu" /></svg>
        </button>
        <div class="topbar-title">
          <h1>{{ pageTitle }}</h1>
          <p v-if="pageSub">{{ pageSub }}</p>
        </div>
        <div class="topbar-actions">
          <template v-if="topbarActions === 'chat' || view === 'chat'">
            <span class="status" :class="{ busy: loading || streaming }">{{
              loading || streaming ? t.typingShort : t.online
            }}</span>
            <button
              v-if="currentConv"
              type="button"
              class="btn-soft sm"
              :disabled="exportingPdf"
              :aria-label="t.exportPdf"
              :title="t.exportPdf"
              @click="chat.exportPdf()"
            >
              <span v-if="exportingPdf" class="spinner" aria-hidden="true"></span>
              <svg v-else class="i" aria-hidden="true"><use href="#i-download" /></svg>
              <span class="hide-sm">{{ t.exportPdf }}</span>
            </button>
            <button
              type="button"
              class="btn-soft sm"
              :disabled="loading || streaming"
              @click="chat.newConversation()"
            >
              <svg class="i" aria-hidden="true"><use href="#i-plus" /></svg>
              <span class="hide-sm">{{ t.newChat }}</span>
            </button>
          </template>
          <template v-else-if="topbarActions === 'dashboard' || view === 'dashboard'">
            <button
              type="button"
              class="btn-soft sm icon-only"
              :disabled="dash.loading"
              :aria-label="t.dash.refresh"
              :title="t.dash.refresh"
              @click="dash.load()"
            >
              <span v-if="dash.loading" class="spinner" aria-hidden="true"></span>
              <svg v-else class="i" aria-hidden="true"><use href="#i-refresh" /></svg>
            </button>
          </template>
          <button
            v-else-if="
              (topbarActions === 'users' || view === 'users') && !users.form && !user?.demo
            "
            type="button"
            class="btn btn-primary sm"
            :disabled="!users.options"
            @click="users.openNewUser()"
          >
            <svg class="i" aria-hidden="true"><use href="#i-plus" /></svg> {{ t.um.newBtn }}
          </button>
          <button
            v-else-if="topbarActions === 'review' || view === 'review'"
            type="button"
            class="btn-soft sm icon-only"
            :disabled="review.loading || review.exLoading"
            :aria-label="t.rv.refresh"
            :title="t.rv.refresh"
            @click="review.reload()"
          >
            <span v-if="review.loading" class="spinner" aria-hidden="true"></span>
            <svg v-else class="i" aria-hidden="true"><use href="#i-refresh" /></svg>
          </button>
          <template v-else-if="topbarActions === 'admin' || view === 'admin'">
            <div class="segmented sm" role="group" :aria-label="t.adm.period">
              <button
                v-for="d in adm.dashDays"
                :key="d"
                type="button"
                :aria-pressed="adm.days === d ? 'true' : 'false'"
                :disabled="adm.loading"
                @click="adm.load(d)"
              >
                {{ t.adm.days[d] }}
              </button>
            </div>
            <button
              type="button"
              class="btn-soft sm icon-only"
              :disabled="adm.loading"
              :aria-label="t.adm.refresh"
              :title="t.adm.refresh"
              @click="adm.load()"
            >
              <span v-if="adm.loading" class="spinner" aria-hidden="true"></span>
              <svg v-else class="i" aria-hidden="true"><use href="#i-refresh" /></svg>
            </button>
          </template>
        </div>
      </header>

      <slot />
    </div>
  </div>
</template>
