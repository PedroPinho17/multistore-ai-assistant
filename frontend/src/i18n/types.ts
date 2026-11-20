export type Lang = 'pt' | 'en' | 'es' | 'fr'
export type Scope = 'group' | 'brand' | 'store'

export const LOCALES: Record<Lang, string> = {
  pt: 'pt-PT',
  en: 'en-GB',
  es: 'es-ES',
  fr: 'fr-FR',
}

export const LANG_NAMES: Record<Lang, string> = {
  pt: 'Português',
  en: 'English',
  es: 'Español',
  fr: 'Français',
}

export const LANGS = [
  { code: 'pt' as const, name: 'Português', flag: 'pt' },
  { code: 'en' as const, name: 'English', flag: 'gb' },
  { code: 'fr' as const, name: 'Français', flag: 'fr' },
  { code: 'es' as const, name: 'Español', flag: 'es' },
]

/** Typed message tree for Login / Reset / Chat / Shell (Phase 2 part 1). */
export interface MessageTree {
  title: string
  loginSub: string
  username: string
  password: string
  login: string
  logout: string
  send: string
  online: string
  typingShort: string
  theme: string
  clear: string
  placeholder: string
  hint: string
  showSql: string
  hideSql: string
  showTable: (n: number) => string
  hideTable: string
  source: string
  rows: (n: number) => string
  mlSource: string
  newChat: string
  recents: string
  noChats: string
  delete: string
  exportPdf: string
  exportingPdf: string
  pdfDone: string
  rename: string
  language: string
  menu: string
  questionLabel: string
  chart: string
  dlg: {
    cancel: string
    del: string
    close: string
    delTitle: string
    delText: string
    clearTitle: string
    deleted: string
    cleared: string
  }
  explain: string
  explaining: string
  cached: string
  followUp: string
  alertsTitle: string
  demoReadOnly: string
  copy: string
  copied: string
  copyFailed: string
  correct: string
  learned: string
  roles: { imperador: string; marca: string; loja: string; admin?: string }
  loginError: string
  tooMany: string
  network: string
  steps: string[]
  welcome: (name: string, scope: Scope, forecast: boolean, orders: boolean) => string
  starters: Record<Scope, [string, string][]>
  errors: {
    notFound: string
    forbidden: string
    badSql: string
    [code: string]: string
  }
  pageTitles: {
    login: string
    chat: string
    reset: string
  }
  h: { home: string; back: string }
  l: {
    welcome: string
    sub: string
    userPh: string
    passPh: string
    show: string
    hide: string
    caps: string
    signingIn: string
    demo: string
    demoHint: string
    useAccount: string
    forgot: string
    fpTitle: string
    fpSub: string
    fpLabel: string
    fpPh: string
    fpSend: string
    fpBack: string
    fpSent: string
    fpDemoNote: string
    rpTitle: string
    rpSub: string
    rpDoneTitle: string
    rpDone: string
    rpNoToken: string
  }
  p: {
    light: string
    dark: string
    pwNew: string
    pwConfirm: string
    pwRules: string
    pwSave: string
    errShort: string
    errMix: string
    errMatch: string
  }
  nav: {
    chat: string
    users: string
    admin: string
    profile: string
    settings: string
    review: string
    dashboard: string
    main: string
    close: string
    account: string
  }
  rate: {
    label: string
    up: string
    down: string
    thanks: string
  }
}
