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

export interface ProfileStats {
  conversations: number
  questions: number
  last_activity?: string | null
  first_activity?: string | null
  by_kind?: Record<string, number>
}

export interface ProfileData {
  email?: string | null
  brand_name?: string | null
  store_name?: string | null
  visible_stores?: number
  stats: ProfileStats
}

export interface DashboardData {
  revenue?: {
    this_month_to_date: number
    last_month_same_days: number
    change_pct: number | null
    days: number
  }
  top_stores?: { store: string; revenue: number }[]
  margin_by_brand?: { brand: string; margin: number | null }[]
  margin_excluded_items?: number
  forecast_7d?: { rows: [string, number][] }
}

export interface ManagedUser {
  id: number
  username: string
  role: Role
  modules: string[]
  active: boolean
  email?: string | null
  brand_name?: string | null
  store_name?: string | null
  brand_id?: number | null
  store_id?: number | null
  last_login?: string | null
  created_by_name?: string | null
  is_me?: boolean
  protected?: boolean
  can_manage?: boolean
  avatar_url?: string | null
}

export interface UsersOptions {
  roles: Role[]
  brands: { id: number; name: string }[]
  stores: { id: number; name: string; brand_id: number }[]
  modules: Record<string, string[]>
  defaults: Record<string, string[]>
}

export interface AppSettingsMeta {
  values: {
    default_accent: string
    default_lang: Lang
    show_demo_accounts: boolean
    session_hours: number
  }
  options: { session_hours: number[] }
  updated_at?: string | null
  updated_by?: string | null
}

export interface AdminMetrics {
  summary: {
    requests: number
    users: number
    errors: number
    error_rate: number
    p50_ms: number | null
    p95_ms: number | null
    avg_tokens: number
    prompt_tokens: number
    completion_tokens: number
    satisfaction: number | null
    thumbs_up: number
    thumbs_down: number
    sql_fail_rate: number
    sql_recovered: number
    classifier_share: number
    cache_share: number
    cache_hits: number
  }
  daily: { day: string; requests: number; errors: number }[]
  by_intent: { intent: string; n: number }[]
  by_kind: {
    kind: string
    n: number
    avg_ms: number
    p95_ms: number
    avg_tokens: number
  }[]
  top_questions: { question: string; n: number; errors?: number; up?: number; down?: number }[]
  thumbs_down: {
    id: number
    question: string
    username: string
    created_at: string
    kind: string
  }[]
  recent_errors: {
    id: number
    question: string
    username: string
    created_at: string
    kind: string
    duration_ms?: number
    error?: string
  }[]
  by_user: {
    username: string
    role: string
    requests: number
    errors?: number
    tokens: number
    last_at: string
  }[]
  eval_history: {
    file: string
    date: string
    model: string
    level: string
    runs: number
    accuracy: number | null
    source?: string
  }[]
}

export interface ReviewItem {
  id: number
  question: string
  answer?: string | null
  error?: string | null
  sql?: string | null
  username: string
  role: string
  created_at: string
  can_teach: boolean
  follow_up?: boolean
  draftQuestion: string
  draftSql: string
  preview: { columns: string[]; rows: unknown[][]; row_count: number } | null
  testedSql: string | null
  busy: string
  err: string
}

export interface ExampleItem {
  id: number
  question: string
  sql: string
  source: string
  created_by?: string | null
  updated_by?: string | null
  updated_at?: string | null
  uses: number
  last_used_at?: string | null
  open: boolean
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
