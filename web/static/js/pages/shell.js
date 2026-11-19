/* Esqueleto das páginas privadas: barra lateral, menu da conta e topo */
"use strict";

const AppShell = {
  name: "app-shell",
  template: String.raw`
    <div class="shell">
      <aside class="rail" :class="{ open: sidebarOpen }" :aria-label="t.nav.main">
        <div class="rail-top">
          <a href="#/" class="rail-brand" :title="t.h.home"><svg class="logo-mark" aria-hidden="true"><use href="#logo"/></svg><span>Multistore AI</span></a>
          <button type="button" class="icon-only rail-close" @click="sidebarOpen = false" :aria-label="t.nav.close"><svg class="i" aria-hidden="true"><use href="#i-x"/></svg></button>
        </div>
        <nav class="rail-nav" :aria-label="t.nav.main">
          <a href="#/chat" class="nav-item" :class="{ active: view === 'chat' }" :aria-current="view === 'chat' ? 'page' : null">
            <svg class="i" aria-hidden="true"><use href="#i-chat"/></svg> <span>{{ t.nav.chat }}</span></a>
          <a href="#/users" class="nav-item" :class="{ active: view === 'users' }" :aria-current="view === 'users' ? 'page' : null" v-if="hasModule('users')">
            <svg class="i" aria-hidden="true"><use href="#i-users"/></svg> <span>{{ t.nav.users }}</span></a>
          <a href="#/review" class="nav-item" :class="{ active: view === 'review' }" :aria-current="view === 'review' ? 'page' : null" v-if="hasModule('teach')">
            <svg class="i" aria-hidden="true"><use href="#i-teach"/></svg> <span>{{ t.nav.review }}</span>
            <span v-if="rv.pending" class="nav-count" :aria-label="t.rv.pending(rv.pending)">{{ rv.pending > 99 ? '99+' : rv.pending }}</span></a>
          <a href="#/admin" class="nav-item" :class="{ active: view === 'admin' }" :aria-current="view === 'admin' ? 'page' : null" v-if="hasModule('observability')">
            <svg class="i" aria-hidden="true"><use href="#i-chart"/></svg> <span>{{ t.nav.admin }}</span></a>
          <a href="#/profile" class="nav-item" :class="{ active: view === 'profile' }" :aria-current="view === 'profile' ? 'page' : null">
            <svg class="i" aria-hidden="true"><use href="#i-user"/></svg> <span>{{ t.nav.profile }}</span></a>
          <a href="#/settings" class="nav-item" :class="{ active: view === 'settings' }" :aria-current="view === 'settings' ? 'page' : null">
            <svg class="i" aria-hidden="true"><use href="#i-settings"/></svg> <span>{{ t.nav.settings }}</span></a>
        </nav>

        <div v-if="view === 'chat'" class="rail-section">
          <div class="recents-title">{{ t.recents }}</div>
          <div class="conv-list">
            <div v-for="c in conversations" :key="c.id" class="conv"
                 :class="{ active: c.id === currentConv }" @click="openConversation(c.id)">
              <input v-if="editingId === c.id" class="conv-edit" :name="'title-' + c.id" :aria-label="t.rename"
                     v-model="editTitle" maxlength="80"
                     @click.stop @keydown.enter.prevent="saveTitle(c)" @keydown.esc="editingId = null"
                     @blur="saveTitle(c)" :ref="el => el && el.focus()" />
              <button v-else type="button" class="conv-title" :title="c.title"
                      :aria-current="c.id === currentConv ? 'page' : null"
                      @click.stop="openConversation(c.id)">{{ c.title }}</button>
              <button v-if="editingId !== c.id" class="conv-del" @click.stop="startRename(c)" :title="t.rename" :aria-label="t.rename + ': ' + c.title"><svg class="i" aria-hidden="true"><use href="#i-edit"/></svg></button>
              <button v-if="editingId !== c.id" class="conv-del" @click.stop="deleteConversation(c)" :title="t.delete" :aria-label="t.delete + ': ' + c.title"><svg class="i" aria-hidden="true"><use href="#i-trash"/></svg></button>
            </div>
            <div v-if="!conversations.length" class="conv-empty">{{ t.noChats }}</div>
          </div>
        </div>
        <div v-else class="rail-spacer"></div>

        <div class="rail-user">
          <div v-if="userMenu" class="user-menu" role="menu" @click.stop @keydown.esc="userMenu = false">
            <div class="menu-row">
              <span><svg class="i" aria-hidden="true"><use href="#i-globe"/></svg> {{ t.language }}</span>
              <lang-picker :model-value="lang" @update:model-value="setLang" :label="t.language" compact up></lang-picker>
            </div>
            <div class="menu-row">
              <span><svg v-if="theme === 'dark'" class="i" aria-hidden="true"><use href="#i-sun"/></svg><svg v-else class="i" aria-hidden="true"><use href="#i-moon"/></svg> {{ t.theme }}</span>
              <div class="segmented sm" role="group" :aria-label="t.theme">
                <button type="button" :aria-pressed="theme === 'light' ? 'true' : 'false'" @click="setTheme('light')" :aria-label="t.p.light" :title="t.p.light"><svg class="i" aria-hidden="true"><use href="#i-sun"/></svg></button>
                <button type="button" :aria-pressed="theme === 'dark' ? 'true' : 'false'" @click="setTheme('dark')" :aria-label="t.p.dark" :title="t.p.dark"><svg class="i" aria-hidden="true"><use href="#i-moon"/></svg></button>
              </div>
            </div>
            <a href="#/settings" role="menuitem" class="menu-item" @click="userMenu = false"><svg class="i" aria-hidden="true"><use href="#i-settings"/></svg> {{ t.nav.settings }}</a>
            <a href="#/profile" role="menuitem" class="menu-item" @click="userMenu = false"><svg class="i" aria-hidden="true"><use href="#i-user"/></svg> {{ t.nav.profile }}</a>
            <button type="button" role="menuitem" class="menu-item danger" @click="logout"><svg class="i" aria-hidden="true"><use href="#i-logout"/></svg> {{ t.logout }}</button>
          </div>
          <button type="button" class="user-btn" @click.stop="userMenu = !userMenu" aria-haspopup="menu"
                  :aria-expanded="userMenu ? 'true' : 'false'" :aria-label="t.nav.account + ': ' + user.username">
            <user-avatar :user="user" :size="32"></user-avatar>
            <span class="user-meta"><strong>{{ user.username }}</strong><small>{{ t.roles[user.role] }}</small></span>
            <svg class="i" aria-hidden="true"><use href="#i-updown"/></svg>
          </button>
        </div>
      </aside>
      <div class="backdrop" v-if="sidebarOpen" @click="sidebarOpen = false"></div>

      <div class="main">
        <header class="topbar">
          <button type="button" class="icon-only menu-btn" @click="sidebarOpen = true" :aria-label="t.menu"
                  :aria-expanded="sidebarOpen ? 'true' : 'false'"><svg class="i" aria-hidden="true"><use href="#i-menu"/></svg></button>
          <div class="topbar-title">
            <h1>{{ pageTitle }}</h1>
            <p v-if="pageSub">{{ pageSub }}</p>
          </div>
          <div class="topbar-actions">
            <template v-if="view === 'chat'">
              <span class="status" :class="{ busy: loading }">{{ loading ? t.typingShort : t.online }}</span>
              <button type="button" class="btn-soft sm" @click="newConversation"><svg class="i" aria-hidden="true"><use href="#i-plus"/></svg> <span class="hide-sm">{{ t.newChat }}</span></button>
            </template>
            <button v-else-if="view === 'users' && !um.form && !user.demo" type="button" class="btn btn-primary sm" @click="openNewUser" :disabled="!um.options"><svg class="i" aria-hidden="true"><use href="#i-plus"/></svg> {{ t.um.newBtn }}</button>
            <button v-else-if="view === 'review'" type="button" class="btn-soft sm icon-only" @click="reloadTeach()" :disabled="rv.loading || ex.loading"
                    :aria-label="t.rv.refresh" :title="t.rv.refresh">
              <span v-if="rv.loading" class="spinner" aria-hidden="true"></span><svg v-else class="i" aria-hidden="true"><use href="#i-refresh"/></svg></button>
            <template v-else-if="view === 'admin'">
              <div class="segmented sm" role="group" :aria-label="t.adm.period">
                <button v-for="d in dashDays" :key="d" type="button" :aria-pressed="adm.days === d ? 'true' : 'false'"
                        @click="loadMetrics(d)">{{ t.adm.days[d] }}</button>
              </div>
              <button type="button" class="btn-soft sm icon-only" @click="loadMetrics()" :disabled="adm.loading"
                      :aria-label="t.adm.refresh" :title="t.adm.refresh">
                <span v-if="adm.loading" class="spinner" aria-hidden="true"></span><svg v-else class="i" aria-hidden="true"><use href="#i-refresh"/></svg></button>
            </template>
          </div>
        </header>

        <chat-page v-if="view === 'chat'"></chat-page>

        <div v-else class="page-scroll" id="page-scroll">
          <profile-page v-if="view === 'profile'"></profile-page>

          <users-page v-else-if="view === 'users'"></users-page>

          <settings-page v-else-if="view === 'settings'"></settings-page>

          <admin-page v-else-if="view === 'admin'"></admin-page>

          <review-page v-else-if="view === 'review'"></review-page>
        </div>
      </div>
    </div>
  `,
};
