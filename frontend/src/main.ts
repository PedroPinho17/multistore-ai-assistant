import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from '@/App.vue'
import router from '@/router'
import { loadLang } from '@/i18n'
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
// mostrar, por isso monta depois. Se falhar, tenta o inglês (o fallback de t()).
void loadLang(ui.lang)
  .catch(() => loadLang('en'))
  .finally(() => {
    void ui.loadConfig()
    if (auth.token) void auth.refreshMe()
    app.mount('#app')
  })
