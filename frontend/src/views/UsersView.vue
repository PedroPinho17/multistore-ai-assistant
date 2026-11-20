<script setup lang="ts">
import { onMounted, watch } from 'vue'
import { storeToRefs } from 'pinia'
import AppShell from '@/components/AppShell.vue'
import UserAvatar from '@/components/UserAvatar.vue'
import { ago } from '@/lib/format'
import { useAuthStore } from '@/stores/auth'
import { useUsersStore } from '@/stores/users'
import { useUiStore } from '@/stores/ui'
import type { Role } from '@/api/types'

const auth = useAuthStore()
const users = useUsersStore()
const ui = useUiStore()
const { user } = storeToRefs(auth)
const {
  form,
  options,
  loading,
  list,
  query,
  role,
  status,
  filteredUsers,
  formModules,
  formStores,
  editId,
  edit,
} = storeToRefs(users)
const { t } = storeToRefs(ui)
const clock = Date.now()

watch(
  () => ui.t.pageTitles.users,
  title => {
    document.title = title
  },
  { immediate: true },
)
watch(
  () => [t.value.um.title, t.value.um.sub] as const,
  ([title, sub]) => ui.setPageMeta(title, sub, 'users'),
  { immediate: true },
)

onMounted(() => {
  void users.load()
})
</script>

<template>
  <AppShell>
    <div class="page-scroll">
      <main class="page wide">
        <section v-if="form" class="card" aria-labelledby="nu-title">
          <h2 id="nu-title" class="sec">{{ t.um.newTitle }}</h2>
          <form novalidate @submit.prevent="users.submitNewUser()">
            <div class="form-grid">
              <div>
                <label for="nu-username">{{ t.um.username }}</label>
                <input
                  id="nu-username"
                  v-model="form.username"
                  name="new-username"
                  class="input"
                  maxlength="32"
                  autocomplete="off"
                  autocapitalize="none"
                  spellcheck="false"
                  aria-describedby="nu-username-help"
                />
                <div id="nu-username-help" class="help">{{ t.um.usernameHint }}</div>
              </div>
              <div>
                <label for="nu-password">{{ t.um.password }}</label>
                <div class="pw-row">
                  <input
                    id="nu-password"
                    v-model="form.password"
                    name="new-user-password"
                    class="input"
                    :type="form.show ? 'text' : 'password'"
                    maxlength="72"
                    autocomplete="new-password"
                  />
                  <button
                    type="button"
                    class="btn-soft"
                    :aria-label="form.show ? t.l.hide : t.l.show"
                    @click="form.show = !form.show"
                  >
                    <svg class="i" aria-hidden="true"
                      ><use :href="form.show ? '#i-eyeoff' : '#i-eye'"
                    /></svg>
                  </button>
                  <button type="button" class="btn-soft" @click="users.genPassword()">
                    <svg class="i" aria-hidden="true"><use href="#i-dice" /></svg>
                    {{ t.um.generate }}
                  </button>
                </div>
                <div class="help">{{ t.p.pwRules }}</div>
              </div>
              <div>
                <label for="nu-email">{{ t.um.email }}</label>
                <input
                  id="nu-email"
                  v-model="form.email"
                  name="new-user-email"
                  class="input"
                  type="email"
                  maxlength="254"
                  autocomplete="off"
                />
                <div class="help">{{ t.um.emailHint }}</div>
              </div>
              <div>
                <label for="nu-role">{{ t.um.role }}</label>
                <select
                  id="nu-role"
                  name="new-role"
                  class="input"
                  :value="form.role"
                  @change="users.pickRole(($event.target as HTMLSelectElement).value as Role)"
                >
                  <option v-for="r in options?.roles || []" :key="r" :value="r">
                    {{ t.roles[r] }}
                  </option>
                </select>
              </div>
              <div v-if="form.role === 'marca'">
                <label for="nu-brand">{{ t.um.brand }}</label>
                <select id="nu-brand" v-model="form.brand_id" name="new-brand" class="input">
                  <option value="" disabled>{{ t.um.choose }}</option>
                  <option v-for="b in options?.brands || []" :key="b.id" :value="b.id">
                    {{ b.name }}
                  </option>
                </select>
              </div>
              <div v-else-if="form.role === 'loja'">
                <label for="nu-store">{{ t.um.store }}</label>
                <select id="nu-store" v-model="form.store_id" name="new-store" class="input">
                  <option value="" disabled>{{ t.um.choose }}</option>
                  <optgroup v-for="g in formStores" :key="g.brand" :label="g.brand">
                    <option v-for="s in g.stores" :key="s.id" :value="s.id">{{ s.name }}</option>
                  </optgroup>
                </select>
              </div>
              <div v-else></div>
              <fieldset class="full" style="border: 0; padding: 0; margin: 0">
                <legend class="lbl">{{ t.um.modules }}</legend>
                <div class="check-grid">
                  <label
                    v-for="mod in formModules"
                    :key="mod"
                    class="check"
                    :class="{ on: form.modules.includes(mod) }"
                  >
                    <input
                      type="checkbox"
                      :name="'nu-mod-' + mod"
                      :checked="form.modules.includes(mod)"
                      @change="users.toggleIn(form.modules, mod)"
                    />
                    <span
                      ><strong>{{ t.mods[mod as keyof typeof t.mods] }}</strong
                      ><small>{{ t.modsHint[mod as keyof typeof t.modsHint] }}</small></span
                    >
                  </label>
                </div>
              </fieldset>
            </div>
            <p v-if="form.error" class="error" role="alert">{{ form.error }}</p>
            <div class="form-actions">
              <button type="button" class="btn-soft" @click="users.form = null">
                {{ t.um.cancel }}
              </button>
              <button
                type="submit"
                class="btn btn-primary"
                :disabled="form.saving || !form.username || !form.password || !form.role"
              >
                <span v-if="form.saving" class="spinner" aria-hidden="true"></span>
                {{ t.um.create }}
              </button>
            </div>
          </form>
        </section>

        <p v-if="user?.demo" class="demo-note" role="note">
          <svg class="i" aria-hidden="true"><use href="#i-lock" /></svg> {{ t.demoReadOnly }}
        </p>
        <section class="card" :aria-label="t.um.title">
          <div class="filters">
            <input
              id="um-search"
              v-model="query"
              name="search"
              class="input with-icon"
              type="search"
              :placeholder="t.um.search"
              :aria-label="t.um.search"
            />
            <select id="um-role" v-model="role" name="role-filter" class="input" :aria-label="t.um.role">
              <option value="">{{ t.um.allRoles }}</option>
              <option v-for="r in ['admin', 'imperador', 'marca', 'loja']" :key="r" :value="r">
                {{ t.roles[r as Role] }}
              </option>
            </select>
            <select
              id="um-status"
              v-model="status"
              name="status-filter"
              class="input"
              :aria-label="t.um.allStatus"
            >
              <option value="">{{ t.um.allStatus }}</option>
              <option value="active">{{ t.um.active }}</option>
              <option value="inactive">{{ t.um.inactive }}</option>
            </select>
          </div>
          <p class="help" style="margin: 0 0 4px">{{ t.um.count(filteredUsers.length) }}</p>
          <div v-if="loading && !list.length" class="skeleton" style="height: 120px"></div>
          <div v-for="u in filteredUsers" :key="u.id" class="user-row">
            <UserAvatar :user="u" :size="40" :class="{ off: !u.active }" />
            <div>
              <div class="name">
                {{ u.username }}
                <span v-if="u.is_me" class="tag-sm me">{{ t.um.you }}</span>
                <span
                  v-if="u.protected && u.role !== 'admin'"
                  class="tag-sm"
                  :title="t.um.demoHint"
                >
                  <svg class="i" aria-hidden="true"><use href="#i-lock" /></svg> {{ t.um.demo }}
                </span>
                <span v-if="!u.active" class="tag-sm off">{{ t.um.inactive }}</span>
              </div>
              <div class="sub">
                {{
                  u.last_login
                    ? t.um.lastLogin + ': ' + ago(u.last_login, clock, t.p.ago)
                    : t.um.never
                }}
                <template v-if="u.created_by_name">
                  · {{ t.um.createdBy(u.created_by_name) }}
                </template>
              </div>
            </div>
            <div class="scope-col">
              <span class="chip-role">{{ t.roles[u.role] }}</span>
              <div class="sub">{{ users.scopeOf(u) }}</div>
            </div>
            <div class="chips mods-col" :aria-label="t.um.modules">
              <span v-for="mod in u.modules" :key="mod" class="mod-chip">{{
                t.mods[mod as keyof typeof t.mods]
              }}</span>
            </div>
            <div class="row-actions">
              <template v-if="u.can_manage">
                <button
                  type="button"
                  :aria-expanded="editId === u.id ? 'true' : 'false'"
                  @click="users.startEdit(u)"
                >
                  <svg class="i" aria-hidden="true"><use href="#i-edit" /></svg> {{ t.um.edit }}
                </button>
                <button type="button" @click="users.toggleActive(u)">
                  <svg class="i" aria-hidden="true"
                    ><use :href="u.active ? '#i-pause' : '#i-play'"
                  /></svg>
                  {{ u.active ? t.um.disable : t.um.enable }}
                </button>
                <button
                  type="button"
                  class="danger"
                  :aria-label="t.um.delete + ': ' + u.username"
                  :title="t.um.delete"
                  @click="users.removeUser(u)"
                >
                  <svg class="i" aria-hidden="true"><use href="#i-trash" /></svg>
                </button>
              </template>
              <span v-else class="tag-sm">{{ t.um.readOnly }}</span>
            </div>
            <div v-if="editId === u.id && edit" class="edit-box">
              <div class="check-grid">
                <label
                  v-for="mod in users.editableModules(u)"
                  :key="mod"
                  class="check"
                  :class="{ on: edit.modules.includes(mod) }"
                >
                  <input
                    type="checkbox"
                    :checked="edit.modules.includes(mod)"
                    @change="users.toggleIn(edit.modules, mod)"
                  />
                  <span
                    ><strong>{{ t.mods[mod as keyof typeof t.mods] }}</strong
                    ><small>{{ t.modsHint[mod as keyof typeof t.modsHint] }}</small></span
                  >
                </label>
              </div>
              <div>
                <label class="lbl" :for="'ed-pw-' + u.id">{{ t.um.newPassword }}</label>
                <div class="pw-row">
                  <input
                    :id="'ed-pw-' + u.id"
                    v-model="edit.password"
                    class="input"
                    :type="edit.show ? 'text' : 'password'"
                    maxlength="72"
                    autocomplete="new-password"
                  />
                  <button
                    type="button"
                    class="btn-soft"
                    :aria-label="edit.show ? t.l.hide : t.l.show"
                    @click="edit.show = !edit.show"
                  >
                    <svg class="i" aria-hidden="true"
                      ><use :href="edit.show ? '#i-eyeoff' : '#i-eye'"
                    /></svg>
                  </button>
                </div>
              </div>
              <div v-if="!u.protected || u.role === 'admin'">
                <label class="lbl" :for="'ed-email-' + u.id">{{ t.um.email }}</label>
                <input
                  :id="'ed-email-' + u.id"
                  v-model="edit.email"
                  class="input"
                  type="email"
                  maxlength="254"
                />
                <div class="help">{{ t.um.emailHint }}</div>
              </div>
              <p v-if="edit.error" class="error" role="alert" style="margin: 0">{{ edit.error }}</p>
              <div class="form-actions" style="margin: 0">
                <button type="button" class="btn-soft" @click="users.editId = null">
                  {{ t.um.cancel }}
                </button>
                <button
                  type="button"
                  class="btn btn-primary"
                  :disabled="edit.saving"
                  @click="users.saveEdit(u)"
                >
                  {{ t.um.save }}
                </button>
              </div>
            </div>
          </div>
          <p v-if="!loading && !filteredUsers.length" class="empty-state">{{ t.um.empty }}</p>
        </section>
      </main>
    </div>
  </AppShell>
</template>
