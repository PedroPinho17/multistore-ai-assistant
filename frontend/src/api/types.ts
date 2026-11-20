export type Role = 'imperador' | 'marca' | 'loja' | 'admin'
export type ThemePref = 'light' | 'dark' | 'system'
export type Theme = 'light' | 'dark'
export type Lang = 'pt' | 'en' | 'es' | 'fr'
export type ToastType = 'ok' | 'error'

export interface User {
  username: string
  role: Role
  modules?: string[]
  avatar_url?: string | null
  demo?: boolean
  brand_name?: string | null
  store_name?: string | null
  settings?: UserSettings | null
}

export interface UserSettings {
  lang?: Lang | null
  theme?: ThemePref | null
  accent?: string | null
}

export interface LoginResponse {
  token: string
  user: User
}

export interface Conversation {
  id: number
  title: string
  updated_at?: string
}

export interface StoredMessage {
  role: 'user' | 'assistant'
  content: string
  created_at: string
  sql?: string | null
  kind?: string | null
  request_id?: string | null
  rating?: number | null
}

export interface AskResult {
  answer?: string
  error?: string
  sql?: string | null
  kind?: string | null
  request_id?: string | null
  conversation_id?: number
  cached?: boolean
  suggestions?: string[]
  columns?: string[]
  rows?: unknown[][]
}

export interface ChatMessage {
  id: number
  from: 'user' | 'bot'
  text: string
  shown: string
  done: boolean
  time: string
  welcome?: boolean
  error?: boolean
  question?: string
  sql?: string | null
  kind?: string | null
  requestId?: string | null
  rating?: number | null
  cached?: boolean
  suggestions?: string[]
  columns?: string[]
  rows: unknown[][]
  chart?: boolean
  showTable: boolean
  showSql: boolean
  liked: boolean
  copied: boolean
  sqlCopied: boolean
  explanation: string
  explaining: boolean
  _dec?: Record<number, number>
}

export interface AlertItem {
  severity: string
  message: string
}

export interface AppConfig {
  default_accent: string
  default_lang: Lang
  show_demo_accounts: boolean
}

export interface DemoAccount {
  user: string
  pass: string
  role: Role
  icon: string
}

export const DEMO_ACCOUNTS: DemoAccount[] = [
  { user: 'pedro', pass: 'imperador123', role: 'imperador', icon: 'crown' },
  { user: 'gestor.burgerlab', pass: 'marca123', role: 'marca', icon: 'tag' },
  { user: 'gerente.maia', pass: 'loja123', role: 'loja', icon: 'store' },
]

export const COLUMN_LABELS: Record<Lang, Record<string, string>> = {
  pt: {
    day: 'Dia',
    forecast_revenue_eur: 'Faturação prevista (€)',
    ingredient: 'Ingrediente',
    unit: 'Unidade',
    needed_7_days: 'Necessário (7 dias)',
    stock: 'Stock',
    to_order: 'A encomendar',
  },
  en: {
    day: 'Day',
    forecast_revenue_eur: 'Forecast revenue (€)',
    ingredient: 'Ingredient',
    unit: 'Unit',
    needed_7_days: 'Needed (7 days)',
    stock: 'Stock',
    to_order: 'To order',
  },
  es: {
    day: 'Día',
    forecast_revenue_eur: 'Facturación prevista (€)',
    ingredient: 'Ingrediente',
    unit: 'Unidad',
    needed_7_days: 'Necesario (7 días)',
    stock: 'Stock',
    to_order: 'A pedir',
  },
  fr: {
    day: 'Jour',
    forecast_revenue_eur: "Chiffre d'affaires prévu (€)",
    ingredient: 'Ingrédient',
    unit: 'Unité',
    needed_7_days: 'Nécessaire (7 jours)',
    stock: 'Stock',
    to_order: 'À commander',
  },
}

export class ApiError extends Error {
  status: number
  code?: string

  constructor(message: string, status: number, code?: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}
