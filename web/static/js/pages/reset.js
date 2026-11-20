/* Nova password a partir do link do email (/reset-password?token=…) */
"use strict";

const ResetPage = {
  name: "reset-page",
  template: String.raw`
    <main class="auth">
      <div class="auth-box">
        <a href="/" class="auth-brand"><svg class="logo-mark" aria-hidden="true"><use href="#logo"/></svg><strong>Multistore AI</strong></a>

        <div v-if="rp.done" class="auth-form">
          <h1>{{ t.l.rpDoneTitle }}</h1>
          <p class="ok-msg" role="status">✅ {{ t.l.rpDone }}</p>
          <a class="btn primary auth-cta" href="/login">{{ t.login }}</a>
        </div>

        <div v-else-if="!rp.token" class="auth-form">
          <h1>{{ t.l.rpTitle }}</h1>
          <p class="error" role="alert">{{ t.l.rpNoToken }}</p>
          <a class="link-btn auth-link" href="/login">← {{ t.l.fpBack }}</a>
        </div>

        <form v-else class="auth-form" @submit.prevent="submitReset" novalidate>
          <h1>{{ t.l.rpTitle }}</h1>
          <p class="sub">{{ t.l.rpSub }}</p>

          <label for="rp-new">{{ t.p.pwNew }}</label>
          <div class="field">
            <input id="rp-new" name="new-password" v-model="rp.pass" :type="rp.show ? 'text' : 'password'"
                   autocomplete="new-password" maxlength="128" aria-describedby="rp-rules" />
            <button type="button" class="eye" @click="rp.show = !rp.show" :aria-pressed="rp.show ? 'true' : 'false'"
                    :aria-label="rp.show ? t.l.hide : t.l.show" :title="rp.show ? t.l.hide : t.l.show" aria-controls="rp-new">
              <svg class="i" aria-hidden="true"><use :href="rp.show ? '#i-eyeoff' : '#i-eye'"/></svg>
            </button>
          </div>
          <p id="rp-rules" class="strength-label">{{ t.p.pwRules }}</p>

          <label for="rp-confirm">{{ t.p.pwConfirm }}</label>
          <div class="field">
            <input id="rp-confirm" name="confirm-password" v-model="rp.confirm" :type="rp.show ? 'text' : 'password'"
                   autocomplete="new-password" maxlength="128" />
          </div>

          <button class="primary" type="submit" :disabled="rp.saving || !rp.pass || !rp.confirm">
            <span v-if="rp.saving" class="spinner" aria-hidden="true"></span> {{ t.p.pwSave }}
          </button>
          <p class="error" v-if="rp.error" role="alert">{{ rp.error }}</p>
          <a class="link-btn auth-link" href="/login">← {{ t.l.fpBack }}</a>
        </form>

        <div class="auth-foot">
          <a href="/" class="back-link">← {{ t.h.back }}</a>
          <div class="auth-tools">
            <lang-picker :model-value="lang" @update:model-value="setLang" :label="t.language" up></lang-picker>
            <button type="button" class="icon-btn icon-only" @click="toggleTheme" :aria-label="t.theme" :title="t.theme"><svg v-if="theme === 'dark'" class="i" aria-hidden="true"><use href="#i-sun"/></svg><svg v-else class="i" aria-hidden="true"><use href="#i-moon"/></svg></button>
          </div>
        </div>
      </div>
    </main>
  `,
};
