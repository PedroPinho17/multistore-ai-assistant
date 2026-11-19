/* Definições (/settings) */
"use strict";

const SettingsPage = {
  name: "settings-page",
  template: String.raw`
    <main class="page">
              <section class="card" aria-labelledby="st-look">
                <h2 id="st-look" class="sec">{{ t.st.appearance }}</h2>
                <div class="set-row">
                  <div><strong id="st-theme">{{ t.theme }}</strong><p>{{ t.st.themeHint }}</p></div>
                  <div class="segmented" role="group" aria-labelledby="st-theme">
                  <button type="button" :aria-pressed="themePref === 'light' ? 'true' : 'false'" @click="setTheme('light')"><svg class="i" aria-hidden="true"><use href="#i-sun"/></svg> {{ t.st.light }}</button>
                  <button type="button" :aria-pressed="themePref === 'dark' ? 'true' : 'false'" @click="setTheme('dark')"><svg class="i" aria-hidden="true"><use href="#i-moon"/></svg> {{ t.st.dark }}</button>
                  <button type="button" :aria-pressed="themePref === 'system' ? 'true' : 'false'" @click="setTheme('system')"><svg class="i" aria-hidden="true"><use href="#i-monitor"/></svg> {{ t.st.system }}</button>
                  </div>
                </div>
                <div class="set-row column">
                  <div><strong id="st-accent">{{ t.st.accent }}</strong><p>{{ t.st.accentHint }}</p></div>
                  <div class="swatches" role="radiogroup" aria-labelledby="st-accent">
                    <button v-for="a in accents" :key="a" type="button" role="radio" class="swatch"
                            :aria-checked="effectiveAccent === a ? 'true' : 'false'" @click="setAccent(a)">
                      <span class="sw-dot" :style="accentSwatch(a)"></span> {{ t.st.accents[a] }}
                      <svg v-if="effectiveAccent === a" class="i" aria-hidden="true"><use href="#i-check"/></svg>
                      <span v-else-if="a === appConfig.default_accent" class="tag-def">{{ t.st.defaultTag }}</span>
                    </button>
                    <label class="swatch" :class="{ 'is-on': isCustom(effectiveAccent) }">
                      <input type="color" id="accent-custom" name="accent-custom" class="sw-color" :value="customHex(effectiveAccent)" :aria-label="t.st.pickColor"
                             @input="previewCustom($event.target.value)" @change="saveCustom($event.target.value)" />
                      <span>{{ t.st.custom }}</span>
                      <svg v-if="isCustom(effectiveAccent)" class="i" aria-hidden="true"><use href="#i-check"/></svg>
                      <svg v-else class="i sw-edit" aria-hidden="true"><use href="#i-edit"/></svg>
                    </label>
                  </div>
                  <p v-if="customAdjusted(effectiveAccent)" class="help adjusted"><svg class="i" aria-hidden="true"><use href="#i-alert"/></svg> {{ t.st.adjusted }}</p>
                  <div class="preview" :aria-label="t.st.preview">
                    <button type="button" class="btn sm" tabindex="-1">{{ t.st.previewBtn }}</button>
                    <span class="chip-role">{{ t.roles[user.role] }}</span>
                    <span class="bubble-demo">{{ t.st.previewMsg }}</span>
                    <a href="/settings" tabindex="-1" @click.prevent>{{ t.st.preview }}</a>
                  </div>
                </div>
                <div class="set-row">
                  <div><strong>{{ t.language }}</strong><p>{{ t.st.langHint }}</p></div>
                  <lang-picker :model-value="lang" @update:model-value="setLang" :label="t.language"></lang-picker>
                </div>
                <div class="set-foot">
                  <span class="help">{{ t.st.sub }}</span>
                  <button type="button" class="btn-soft sm" @click="resetSettings"><svg class="i" aria-hidden="true"><use href="#i-refresh"/></svg> {{ t.st.reset }}</button>
                </div>
              </section>

              <section v-if="user.role === 'admin' && appForm" class="card" aria-labelledby="st-app">
                <h2 id="st-app" class="sec">{{ t.st.appTitle }}</h2>
                <p class="sec-sub">{{ t.st.appSub }}</p>
                <div class="set-row column">
                  <div><strong id="st-def-accent">{{ t.st.defAccent }}</strong></div>
                  <div class="swatches" role="radiogroup" aria-labelledby="st-def-accent">
                    <button v-for="a in accents" :key="a" type="button" role="radio" class="swatch"
                            :aria-checked="appForm.default_accent === a ? 'true' : 'false'" @click="appForm.default_accent = a">
                      <span class="sw-dot" :style="accentSwatch(a)"></span> {{ t.st.accents[a] }}
                      <svg v-if="appForm.default_accent === a" class="i" aria-hidden="true"><use href="#i-check"/></svg>
                    </button>
                    <label class="swatch" :class="{ 'is-on': isCustom(appForm.default_accent) }">
                      <input type="color" id="default-accent-custom" name="default-accent-custom" class="sw-color" :value="customHex(appForm.default_accent)" :aria-label="t.st.pickColor"
                             @input="appForm.default_accent = $event.target.value.toLowerCase()" @change="appForm.default_accent = $event.target.value.toLowerCase()" />
                      <span>{{ t.st.custom }}</span>
                      <svg v-if="isCustom(appForm.default_accent)" class="i" aria-hidden="true"><use href="#i-check"/></svg>
                      <svg v-else class="i sw-edit" aria-hidden="true"><use href="#i-edit"/></svg>
                    </label>
                  </div>
                </div>
                <div class="set-row">
                  <div><strong>{{ t.st.defLang }}</strong><p>{{ t.st.defLangHint }}</p></div>
                  <lang-picker v-model="appForm.default_lang" :label="t.st.defLang"></lang-picker>
                </div>
                <div class="set-row">
                  <div><strong id="st-demo">{{ t.st.demo }}</strong><p>{{ t.st.demoHint }}</p></div>
                  <span class="switch-wrap">{{ appForm.show_demo_accounts ? t.st.on : t.st.off }}
                    <button type="button" role="switch" class="switch" aria-labelledby="st-demo" :aria-label="t.st.demo"
                            :aria-checked="appForm.show_demo_accounts ? 'true' : 'false'"
                            @click="appForm.show_demo_accounts = !appForm.show_demo_accounts"></button></span>
                </div>
                <div class="set-row">
                  <div><label class="lbl" for="st-session" style="margin:0">{{ t.st.session }}</label><p>{{ t.st.sessionHint }}</p></div>
                  <select id="st-session" name="session-hours" class="input" v-model.number="appForm.session_hours">
                    <option v-for="h in appMeta.options.session_hours" :key="h" :value="h">{{ t.st.hours(h) }}</option>
                  </select>
                </div>
                <div class="set-foot">
                  <span class="help">{{ lastChangeText() }}</span>
                  <button type="button" class="btn btn-primary sm" @click="saveAppSettings" :disabled="!appDirty || appSaving">
                    <span v-if="appSaving" class="spinner" aria-hidden="true"></span> {{ t.st.save }}</button>
                </div>
              </section>
            </main>
  `,
};
