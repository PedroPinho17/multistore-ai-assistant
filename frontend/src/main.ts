import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from '@/App.vue'
import router from '@/router'
import { loadLang } from '@/i18n'
import { startApp } from '@/boot'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import '@/styles/main.css'

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
app.use(router)

const auth = useAuthStore()
const ui = useUiStore()
auth.wireApi(router)

// Só a língua ativa vem no arranque (cada língua é um chunk); sem ela não há textos para
// mostrar, por isso monta depois. Se falhar, tenta o inglês (o fallback de t()); se nem
// esse vier, mostra uma mensagem simples em vez de uma página em branco (boot.ts, testado).
void startApp({
  lang: ui.lang,
  load: loadLang,
  root: () => document.getElementById('app'),
  start: () => {
    void ui.loadConfig()
    if (auth.token) void auth.refreshMe()
    app.mount('#app')
  },
})
