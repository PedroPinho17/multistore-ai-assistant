/* Perfil (/profile) */
"use strict";

const ProfilePage = {
  name: "profile-page",
  template: String.raw`
    <main class="page">
          <section class="card identity">
            <user-avatar :user="user" :size="72"></user-avatar>
            <div>
              <div class="identity-name">{{ user.username }} <span class="chip-role">{{ t.roles[user.role] }}</span></div>
              <p class="scope">{{ scopeText }}</p>
              <div class="avatar-tools" v-if="!user.demo">
                <label class="btn-soft sm" for="avatar-file" :aria-disabled="avatarSaving ? 'true' : null"><svg class="i" aria-hidden="true"><use href="#i-camera"/></svg> {{ avatarSaving ? t.avatar.saving : t.avatar.change }}</label>
                <input id="avatar-file" name="avatar" type="file" accept="image/png,image/jpeg,image/webp" class="sr-only" :disabled="avatarSaving" @change="uploadAvatar" />
                <button v-if="user.avatar_url" type="button" class="btn-soft sm" :disabled="avatarSaving" @click="removeAvatar"><svg class="i" aria-hidden="true"><use href="#i-trash"/></svg> {{ t.avatar.remove }}</button>
                <span class="help" aria-live="polite">{{ user.avatar_url ? t.avatar.hint : t.avatar.fallback }}</span>
              </div>
            </div>
          </section>

          <section class="stats" :aria-label="t.p.statsTitle">
            <div class="card stat">
              <div class="label">{{ t.p.conversations }}</div>
              <div class="value" v-if="profile">{{ profile.stats.conversations }}</div><div v-else class="skeleton"></div>
            </div>
            <div class="card stat">
              <div class="label">{{ t.p.questions }}</div>
              <div class="value" v-if="profile">{{ profile.stats.questions }}</div><div v-else class="skeleton"></div>
            </div>
            <div class="card stat">
              <div class="label">{{ t.p.lastActivity }}</div>
              <div class="value" style="font-size:18px" v-if="profile">{{ profile.stats.last_activity ? ago(profile.stats.last_activity) : '—' }}</div><div v-else class="skeleton"></div>
              <div class="hint2" v-if="profile && profile.stats.first_activity">{{ t.p.since }} {{ dateFmt(profile.stats.first_activity) }}</div>
            </div>
            <div class="card stat">
              <div class="label">{{ t.p.session }}</div>
              <div class="value" style="font-size:18px">{{ sessionLeft }}</div>
              <div class="hint2">{{ t.p.sessionHint }}</div>
            </div>
          </section>

          <div class="profile-cols">
            <section class="card">
              <h2>{{ t.p.permTitle }}</h2>
              <ul class="perm-list">
                <li v-for="pm in permissions" :key="pm.text" :class="pm.ok ? 'yes' : 'no'">
                  <span class="ico" aria-hidden="true">{{ pm.ok ? '✓' : '✕' }}</span>
                  <span><span class="sr-only">{{ pm.ok ? t.p.allowed : t.p.notAllowed }}: </span>{{ pm.text }}</span>
                </li>
              </ul>
            </section>

            <section class="card">
              <h2>{{ t.p.kindsTitle }}</h2>
              <template v-if="profile && kindRows.length">
                <div v-for="k in kindRows" :key="k.key" class="kind-row">
                  <span>{{ k.label }}</span>
                  <div class="kind-bar" role="img" :aria-label="k.label + ': ' + k.n"><span :style="{ width: k.pct + '%' }"></span></div>
                  <span class="n">{{ k.n }}</span>
                </div>
              </template>
              <p v-else-if="profile" class="muted">{{ t.p.noActivity }} <a href="/chat">{{ t.p.startChat }}</a></p>
              <div v-else class="skeleton"></div>
            </section>

            <section class="card">
              <h2>{{ t.p.pwTitle }}</h2>
              <p v-if="user.demo" class="demo-note" role="note"><svg class="i" aria-hidden="true"><use href="#i-lock"/></svg> {{ t.demoReadOnly }}</p>
              <form v-else class="form" @submit.prevent="changePassword" novalidate>
                <label for="pw-current">{{ t.p.pwCurrent }}</label>
                <div class="field">
                  <input id="pw-current" name="current-password" v-model="pw.current" :type="pw.show ? 'text' : 'password'"
                         autocomplete="current-password" maxlength="128" />
                </div>
                <label for="pw-new">{{ t.p.pwNew }}</label>
                <div class="field">
                  <input id="pw-new" name="new-password" v-model="pw.new" :type="pw.show ? 'text' : 'password'"
                         autocomplete="new-password" maxlength="128" aria-describedby="pw-strength" />
                  <button type="button" class="eye" @click="pw.show = !pw.show" :aria-pressed="pw.show ? 'true' : 'false'"
                          :aria-label="pw.show ? t.l.hide : t.l.show" :title="pw.show ? t.l.hide : t.l.show">
                    <svg v-if="!pw.show" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>
                    <svg v-else width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17.9 17.9A10.4 10.4 0 0 1 12 19c-6.4 0-10-7-10-7a18.6 18.6 0 0 1 5.1-5.9M9.9 5.2A9.6 9.6 0 0 1 12 5c6.4 0 10 7 10 7a18.7 18.7 0 0 1-2.2 3.2M14.1 14.1a3 3 0 1 1-4.2-4.2M2 2l20 20"/></svg>
                  </button>
                </div>
                <div class="strength" :class="'s' + pwStrength" aria-hidden="true"><i></i><i></i><i></i><i></i></div>
                <p id="pw-strength" class="strength-label">{{ pw.new ? t.p.strength[pwStrength] : t.p.pwRules }}</p>
                <label for="pw-confirm">{{ t.p.pwConfirm }}</label>
                <div class="field">
                  <input id="pw-confirm" name="confirm-password" v-model="pw.confirm" :type="pw.show ? 'text' : 'password'"
                         autocomplete="new-password" maxlength="128" />
                </div>
                <button class="primary" type="submit" :disabled="pw.saving || !pw.current || !pw.new || !pw.confirm">
                  <span v-if="pw.saving" class="spinner" aria-hidden="true"></span> {{ t.p.pwSave }}
                </button>
                <p class="error" v-if="pw.error" role="alert">{{ pw.error }}</p>
                <p class="ok-msg" v-if="pw.ok" role="status">✅ {{ t.p.pwDone }}</p>
              </form>
            </section>

            <section class="card">
              <h2>{{ t.p.emailTitle }}</h2>
              <p v-if="user.demo" class="demo-note" role="note"><svg class="i" aria-hidden="true"><use href="#i-lock"/></svg> {{ t.p.emailDemo }}</p>
              <form v-else class="form" @submit.prevent="saveEmail" novalidate>
                <p class="muted" style="margin-top:0">{{ t.p.emailHint }}</p>
                <label for="pf-email">Email</label>
                <div class="field">
                  <input id="pf-email" name="email" type="email" v-model="em.value" maxlength="254"
                         autocomplete="email" autocapitalize="none" spellcheck="false" />
                </div>
                <button class="primary" type="submit" :disabled="em.saving || em.value.trim() === (profile?.email || '')">
                  <span v-if="em.saving" class="spinner" aria-hidden="true"></span> {{ t.p.emailSave }}
                </button>
                <p class="error" v-if="em.error" role="alert">{{ em.error }}</p>
                <p class="ok-msg" v-if="em.ok" role="status">✅ {{ em.value ? t.p.emailSaved : t.p.emailRemoved }}</p>
              </form>
            </section>
          </div>

          <section class="card danger-zone">
            <h2 class="sec" style="margin:0 0 6px">{{ t.p.dangerTitle }}</h2>
            <div class="row2">
              <div><strong>{{ t.p.clearAll }}</strong><p>{{ t.p.clearAllHint }}</p></div>
              <button type="button" class="btn-danger" @click="deleteAllConversations"
                      :disabled="!profile || !profile.stats.conversations"><svg class="i" aria-hidden="true"><use href="#i-trash"/></svg> {{ t.p.clearAll }}</button>
            </div>
            <div class="row2">
              <div><strong>{{ t.logout }}</strong><p>{{ t.p.logoutHint }}</p></div>
              <button type="button" class="btn-danger" @click="logout"><svg class="i" aria-hidden="true"><use href="#i-logout"/></svg> {{ t.logout }}</button>
            </div>
          </section>
            </main>
  `,
};
