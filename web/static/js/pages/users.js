/* Contas (#/users) */
"use strict";

const UsersPage = {
  name: "users-page",
  template: String.raw`
    <main class="page wide">
          <section v-if="um.form" class="card" aria-labelledby="nu-title">
            <h2 id="nu-title" class="sec">{{ t.um.newTitle }}</h2>
            <form @submit.prevent="submitNewUser" novalidate>
              <div class="form-grid">
                <div>
                  <label for="nu-username">{{ t.um.username }}</label>
                  <input id="nu-username" name="new-username" class="input" v-model="um.form.username" maxlength="32" autocomplete="off"
                         autocapitalize="none" spellcheck="false" aria-describedby="nu-username-help" />
                  <div id="nu-username-help" class="help">{{ t.um.usernameHint }}</div>
                </div>
                <div>
                  <label for="nu-password">{{ t.um.password }}</label>
                  <div class="pw-row">
                    <input id="nu-password" name="new-user-password" class="input" v-model="um.form.password" :type="um.form.show ? 'text' : 'password'"
                           maxlength="72" autocomplete="new-password" />
                    <button type="button" class="btn-soft" @click="um.form.show = !um.form.show"
                            :aria-label="um.form.show ? t.l.hide : t.l.show" :title="um.form.show ? t.l.hide : t.l.show"><svg class="i" aria-hidden="true"><use :href="um.form.show ? '#i-eyeoff' : '#i-eye'"/></svg></button>
                    <button type="button" class="btn-soft" @click="genPassword"><svg class="i" aria-hidden="true"><use href="#i-dice"/></svg> {{ t.um.generate }}</button>
                  </div>
                  <div class="help">{{ t.p.pwRules }}</div>
                </div>
                <div>
                  <label for="nu-role">{{ t.um.role }}</label>
                  <select id="nu-role" name="new-role" class="input" :value="um.form.role" @change="pickRole($event.target.value)">
                    <option v-for="r in um.options.roles" :key="r" :value="r">{{ t.roles[r] }}</option>
                  </select>
                </div>
                <div v-if="um.form.role === 'marca'">
                  <label for="nu-brand">{{ t.um.brand }}</label>
                  <select id="nu-brand" name="new-brand" class="input" v-model="um.form.brand_id">
                    <option value="" disabled>{{ t.um.choose }}</option>
                    <option v-for="b in um.options.brands" :key="b.id" :value="b.id">{{ b.name }}</option>
                  </select>
                </div>
                <div v-else-if="um.form.role === 'loja'">
                  <label for="nu-store">{{ t.um.store }}</label>
                  <select id="nu-store" name="new-store" class="input" v-model="um.form.store_id">
                    <option value="" disabled>{{ t.um.choose }}</option>
                    <optgroup v-for="g in formStores" :key="g.brand" :label="g.brand">
                      <option v-for="s in g.stores" :key="s.id" :value="s.id">{{ s.name }}</option>
                    </optgroup>
                  </select>
                </div>
                <div v-else></div>
                <fieldset class="full" style="border:0;padding:0;margin:0">
                  <legend class="lbl">{{ t.um.modules }}</legend>
                  <div class="check-grid">
                    <label v-for="mod in formModules" :key="mod" class="check" :class="{ on: um.form.modules.includes(mod) }">
                      <input type="checkbox" :name="'nu-mod-' + mod" :checked="um.form.modules.includes(mod)" @change="toggleIn(um.form.modules, mod)" />
                      <span><strong>{{ t.mods[mod] }}</strong><small>{{ t.modsHint[mod] }}</small></span>
                    </label>
                  </div>
                </fieldset>
              </div>
              <p class="error" v-if="um.form.error" role="alert">{{ um.form.error }}</p>
              <div class="form-actions">
                <button type="button" class="btn-soft" @click="um.form = null">{{ t.um.cancel }}</button>
                <button type="submit" class="btn btn-primary"
                        :disabled="um.form.saving || !um.form.username || !um.form.password || !um.form.role">
                  <span v-if="um.form.saving" class="spinner" aria-hidden="true"></span> {{ t.um.create }}</button>
              </div>
            </form>
          </section>

          <p v-if="user.demo" class="demo-note" role="note"><svg class="i" aria-hidden="true"><use href="#i-lock"/></svg> {{ t.demoReadOnly }}</p>
          <section class="card" :aria-label="t.um.title">
            <div class="filters">
              <input id="um-search" name="search" class="input with-icon" type="search" v-model="um.query" :placeholder="t.um.search" :aria-label="t.um.search" />
              <select id="um-role" name="role-filter" class="input" v-model="um.role" :aria-label="t.um.role">
                <option value="">{{ t.um.allRoles }}</option>
                <option v-for="r in ['admin', 'imperador', 'marca', 'loja']" :key="r" :value="r">{{ t.roles[r] }}</option>
              </select>
              <select id="um-status" name="status-filter" class="input" v-model="um.status" :aria-label="t.um.allStatus">
                <option value="">{{ t.um.allStatus }}</option>
                <option value="active">{{ t.um.active }}</option>
                <option value="inactive">{{ t.um.inactive }}</option>
              </select>
            </div>
            <p class="help" style="margin:0 0 4px">{{ t.um.count(filteredUsers.length) }}</p>
            <div v-if="um.loading && !um.list.length" class="skeleton" style="height:120px"></div>
            <div v-for="u in filteredUsers" :key="u.id" class="user-row">
              <user-avatar :user="u" :size="40" :class="{ off: !u.active }"></user-avatar>
              <div>
                <div class="name">
                  {{ u.username }}
                  <span v-if="u.is_me" class="tag-sm me">{{ t.um.you }}</span>
                  <span v-if="u.protected && u.role !== 'admin'" class="tag-sm" :title="t.um.demoHint"><svg class="i" aria-hidden="true"><use href="#i-lock"/></svg> {{ t.um.demo }}</span>
                  <span v-if="!u.active" class="tag-sm off">{{ t.um.inactive }}</span>
                </div>
                <div class="sub">{{ u.last_login ? t.um.lastLogin + ': ' + ago(u.last_login) : t.um.never }}<template v-if="u.created_by_name"> · {{ t.um.createdBy(u.created_by_name) }}</template></div>
              </div>
              <div class="scope-col">
                <span class="chip-role">{{ t.roles[u.role] }}</span>
                <div class="sub">{{ scopeOf(u) }}</div>
              </div>
              <div class="chips mods-col" :aria-label="t.um.modules">
                <span v-for="mod in u.modules" :key="mod" class="mod-chip">{{ t.mods[mod] }}</span>
              </div>
              <div class="row-actions">
                <template v-if="u.can_manage">
                  <button type="button" @click="startEdit(u)" :aria-expanded="um.editId === u.id ? 'true' : 'false'"><svg class="i" aria-hidden="true"><use href="#i-edit"/></svg> {{ t.um.edit }}</button>
                  <button type="button" @click="toggleActive(u)"><svg class="i" aria-hidden="true"><use :href="u.active ? '#i-pause' : '#i-play'"/></svg> {{ u.active ? t.um.disable : t.um.enable }}</button>
                  <button type="button" class="danger" @click="removeUser(u)" :aria-label="t.um.delete + ': ' + u.username" :title="t.um.delete"><svg class="i" aria-hidden="true"><use href="#i-trash"/></svg></button>
                </template>
                <span v-else class="tag-sm">{{ t.um.readOnly }}</span>
              </div>
              <div v-if="um.editId === u.id" class="edit-box">
                <div class="check-grid">
                  <label v-for="mod in editableModules(u)" :key="mod" class="check" :class="{ on: um.edit.modules.includes(mod) }">
                    <input type="checkbox" :name="'ed-mod-' + mod" :checked="um.edit.modules.includes(mod)" @change="toggleIn(um.edit.modules, mod)" />
                    <span><strong>{{ t.mods[mod] }}</strong><small>{{ t.modsHint[mod] }}</small></span>
                  </label>
                </div>
                <div>
                  <label class="lbl" :for="'ed-pw-' + u.id">{{ t.um.newPassword }}</label>
                  <div class="pw-row">
                    <input :id="'ed-pw-' + u.id" class="input" v-model="um.edit.password" :type="um.edit.show ? 'text' : 'password'"
                           maxlength="72" autocomplete="new-password" />
                    <button type="button" class="btn-soft" @click="um.edit.show = !um.edit.show"
                            :aria-label="um.edit.show ? t.l.hide : t.l.show"><svg class="i" aria-hidden="true"><use :href="um.edit.show ? '#i-eyeoff' : '#i-eye'"/></svg></button>
                  </div>
                </div>
                <p class="error" v-if="um.edit.error" role="alert" style="margin:0">{{ um.edit.error }}</p>
                <div class="form-actions" style="margin:0">
                  <button type="button" class="btn-soft" @click="um.editId = null">{{ t.um.cancel }}</button>
                  <button type="button" class="btn btn-primary" @click="saveEdit(u)" :disabled="um.edit.saving">{{ t.um.save }}</button>
                </div>
              </div>
            </div>
            <p v-if="!um.loading && !filteredUsers.length" class="empty-state">{{ t.um.empty }}</p>
          </section>
            </main>
  `,
};
