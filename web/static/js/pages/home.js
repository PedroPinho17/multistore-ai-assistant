/* Página inicial pública (/) */
"use strict";

const HomePage = {
  name: "home-page",
  template: String.raw`
      <div class="home">
        <header class="topnav">
          <a class="brand-link" href="/"><svg class="logo-mark" aria-hidden="true"><use href="#logo"/></svg><strong>Multistore AI</strong></a>
          <nav class="topnav-links" :aria-label="t.h.nav">
            <a href="#features" @click.prevent="scrollToId('features')">{{ t.h.navFeatures }}</a>
            <a href="#how" @click.prevent="scrollToId('how')">{{ t.h.navHow }}</a>
            <a v-if="showDemo" href="#roles" @click.prevent="scrollToId('roles')">{{ t.h.navRoles }}</a>
          </nav>
          <div class="head-right">
            <button class="icon-btn icon-only" @click="toggleTheme" :title="t.theme" :aria-label="t.theme"><svg v-if="theme === 'dark'" class="i" aria-hidden="true"><use href="#i-sun"/></svg><svg v-else class="i" aria-hidden="true"><use href="#i-moon"/></svg></button>
            <lang-picker :model-value="lang" @update:model-value="setLang" :label="t.language" compact></lang-picker>
            <a class="btn" :href="token ? '/chat' : '/login'">{{ token ? t.h.openChat : t.login }}</a>
          </div>
        </header>

        <main class="home-main">
          <section class="hero">
            <div>
              <p class="eyebrow">{{ t.h.eyebrow }}</p>
              <h1>{{ t.h.title }}</h1>
              <p class="lead">{{ t.h.lead }}</p>
              <div class="cta">
                <a class="btn btn-lg" :href="token ? '/chat' : '/login'">{{ token ? t.h.openChat : (showDemo ? t.h.tryDemo : t.login) }} <svg class="i" aria-hidden="true"><use href="#i-arrow"/></svg></a>
                <a class="btn-ghost btn-lg" href="https://github.com/PedroPinho17/multistore-ai-assistant" rel="noopener"><svg class="i" aria-hidden="true"><use href="#i-github"/></svg> {{ t.h.github }}</a>
              </div>
              <ul class="proof">
                <li v-for="pf in t.h.proof" :key="pf"><svg class="i" aria-hidden="true"><use href="#i-check"/></svg> {{ pf }}</li>
              </ul>
            </div>

            <!-- Conversa de demonstração (animada, decorativa) -->
            <div class="demo" aria-hidden="true">
              <div class="demo-head">
                <span class="dots3"><i></i><i></i><i></i></span>
                <strong>{{ t.title }}</strong>
                <span class="status" style="margin-left:auto">{{ t.online }}</span>
              </div>
              <div class="demo-body">
              <div v-for="m in demo.msgs" :key="m.id" :class="['msg', m.from]">
                <div class="avatar"><template v-if="m.from === 'user'">GM</template><svg v-else class="logo-mark" aria-hidden="true"><use href="#logo"/></svg></div>
                <div class="bubble">
                  <template v-if="m.from === 'user'">{{ m.text }}</template>
                  <template v-else>
                    {{ m.shown }}<span v-if="!m.done" class="caret"></span>
                    <template v-if="m.done && m.bars">
                      <div class="mini-bars"><span v-for="(b, i) in m.bars" :key="i" :style="{ height: b.v + '%', animationDelay: (i * 70) + 'ms' }"></span></div>
                      <div class="mini-legend"><span v-for="(b, i) in m.bars" :key="i">{{ b.l }}</span></div>
                    </template>
                    <span v-if="m.done && m.tag" class="tag">{{ m.tag }}</span>
                  </template>
                </div>
              </div>
              <div class="msg bot" v-if="demo.typing">
                <div class="avatar"><svg class="logo-mark" aria-hidden="true"><use href="#logo"/></svg></div>
                <div class="bubble typing"><span class="dots"><span></span><span></span><span></span></span></div>
              </div>
              </div>
            </div>
          </section>

          <section id="features" class="section">
            <div class="section-head"><h2>{{ t.h.tourTitle }}</h2><p>{{ t.h.tourSub }}</p></div>
            <div class="tour">
              <article v-for="row in t.h.tour" :key="row.img" class="tour-row">
                <div>
                  <p class="tour-kicker">{{ row.kicker }}</p>
                  <h3>{{ row.title }}</h3>
                  <p>{{ row.text }}</p>
                  <ul class="tour-points">
                    <li v-for="pt in row.points" :key="pt"><svg class="i" aria-hidden="true"><use href="#i-check"/></svg> <span>{{ pt }}</span></li>
                  </ul>
                </div>
                <figure class="tour-media">
                  <img :src="'/static/img/' + row.img + '.webp'" :width="row.w" :height="row.h" :alt="row.alt" loading="lazy" decoding="async" />
                </figure>
              </article>
            </div>
            <div class="also">
              <h4>{{ t.h.alsoTitle }}</h4>
              <div v-for="a in t.h.also" :key="a.title">
                <svg class="i" aria-hidden="true"><use :href="'#i-' + a.icon"/></svg>
                <strong>{{ a.title }}</strong>
                <p>{{ a.text }}</p>
              </div>
            </div>
          </section>

          <section id="how" class="section">
            <div class="section-head"><h2>{{ t.h.howTitle }}</h2><p>{{ t.h.howSub }}</p></div>
            <div class="how-grid">
              <ol class="steps-v">
                <li v-for="(st, i) in t.h.steps" :key="st.title">
                  <span class="flow-n">0{{ i + 1 }}</span>
                  <div><h3>{{ st.title }}</h3><p>{{ st.text }}</p></div>
                </li>
              </ol>
              <figure class="example" :aria-label="t.h.ex.title">
                <div class="example-head"><span class="dots3"><i></i><i></i><i></i></span> {{ t.h.ex.title }}</div>
                <dl>
                  <dt>{{ t.h.ex.question }}</dt><dd>“{{ t.h.ex.q }}”</dd>
                  <dt>{{ t.h.ex.intent }}</dt><dd>{{ t.h.ex.intentText }}</dd>
                  <dt>{{ t.h.ex.sql }}</dt><dd><pre><span class="k">SELECT</span> b.name <span class="k">AS</span> marca, <span class="k">ROUND</span>(<span class="k">SUM</span>(s.total), 2) <span class="k">AS</span> faturacao
    <span class="k">FROM</span> sales <span class="k">AS</span> s
    <span class="k">JOIN</span> stores <span class="k">AS</span> st <span class="k">ON</span> st.id = s.store_id
    <span class="k">JOIN</span> brands <span class="k">AS</span> b <span class="k">ON</span> b.id = st.brand_id
    <span class="k">WHERE</span> s.sold_at &gt;= <span class="k">CAST</span>(<span class="s">'2026-10-01'</span> <span class="k">AS</span> DATE)
      <span class="k">AND</span> s.sold_at &lt; <span class="k">CAST</span>(<span class="s">'2026-11-01'</span> <span class="k">AS</span> DATE)
    <span class="k">GROUP BY</span> b.name <span class="k">ORDER BY</span> faturacao <span class="k">DESC</span></pre></dd>
                  <dt>{{ t.h.ex.checks }}</dt><dd><span class="ok">✓</span> {{ t.h.ex.checksText }}</dd>
                  <dt>{{ t.h.ex.rls }}</dt><dd><span class="ok">✓</span> {{ t.h.ex.rlsText }}</dd>
                  <dt>{{ t.h.ex.answer }}</dt><dd>{{ t.h.ex.answerText }}</dd>
                </dl>
              </figure>
            </div>
          </section>

          <section v-if="showDemo" id="roles" class="section">
            <div class="section-head"><h2>{{ t.h.rolesTitle }}</h2><p>{{ t.h.rolesSub }}</p></div>
            <div class="tbl-wrap roles-table">
              <table class="tbl">
                <thead><tr><th>{{ t.h.cols.role }}</th><th>{{ t.h.cols.account }}</th><th>{{ t.h.cols.password }}</th>
                  <th class="wrap">{{ t.h.cols.sees }}</th><th><span class="sr-only">{{ t.h.use }}</span></th></tr></thead>
                <tbody>
                  <tr v-for="d in demoAccounts" :key="d.user">
                    <td><span class="role-cell"><svg class="i" aria-hidden="true"><use :href="'#i-' + d.icon"/></svg> {{ t.roles[d.role] }}</span></td>
                    <td><code>{{ d.user }}</code><span class="pw-m"> <code>{{ d.pass }}</code></span></td>
                    <td><code>{{ d.pass }}</code></td>
                    <td class="wrap">{{ t.h.roleText[d.role] }}</td>
                    <td class="num"><button type="button" class="btn-soft sm" @click="useDemo(d)"
                            :aria-label="t.h.use + ': ' + d.user">{{ t.h.use }}</button></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <section class="closing-card">
            <div>
              <h2>{{ showDemo ? t.h.closing : t.h.closingNoDemo }}</h2>
              <p v-if="showDemo">{{ t.h.closingSub }}</p>
            </div>
            <div class="cta">
              <a class="btn" :href="token ? '/chat' : '/login'">{{ token ? t.h.openChat : (showDemo ? t.h.tryDemo : t.login) }} <svg class="i" aria-hidden="true"><use href="#i-arrow"/></svg></a>
              <a class="btn-ghost" href="https://github.com/PedroPinho17/multistore-ai-assistant" rel="noopener"><svg class="i" aria-hidden="true"><use href="#i-github"/></svg> {{ t.h.github }}</a>
            </div>
          </section>
        </main>

        <footer class="site-footer">
          <span>© 2026 Multistore AI · {{ t.h.footer }}</span>
          <p class="stack"><span>{{ t.h.builtWith }}</span><code>FastAPI</code><code>PostgreSQL 17 · RLS</code><code>pgvector</code><code>Groq</code><code>XLM-RoBERTa</code><code>Vue 3</code></p>
          <a href="https://github.com/PedroPinho17/multistore-ai-assistant" rel="noopener"><svg class="i" aria-hidden="true"><use href="#i-github"/></svg> GitHub</a>
        </footer>
      </div>
  `,
};
