import { defineStore } from 'pinia'
import { computed, nextTick, ref } from 'vue'
import { api } from '@/api/client'
import type { ManagedUser, Role, UsersOptions } from '@/api/types'
import { ApiError } from '@/api/types'
import { DATA_MODULES, MODULE_ORDER } from '@/lib/format'
import { useUiStore } from '@/stores/ui'

export interface UserForm {
  username: string
  password: string
  show: boolean
  role: Role | ''
  brand_id: number | ''
  store_id: number | ''
  email: string
  modules: string[]
  error: string
  saving: boolean
}

function emptyForm(): UserForm {
  return {
    username: '',
    password: '',
    show: false,
    role: '',
    brand_id: '',
    store_id: '',
    email: '',
    modules: [],
    error: '',
    saving: false,
  }
}

function randomPassword(length = 14): string {
  const sets = [
    'abcdefghijkmnpqrstuvwxyz',
    'ABCDEFGHJKLMNPQRSTUVWXYZ',
    '23456789',
    '!#%+-=?@',
  ]
  const all = sets.join('')
  const pick = (s: string) => s[crypto.getRandomValues(new Uint32Array(1))[0]! % s.length]!
  const chars = sets.map(pick)
  while (chars.length < length) chars.push(pick(all))
  for (let i = chars.length - 1; i > 0; i--) {
    const j = crypto.getRandomValues(new Uint32Array(1))[0]! % (i + 1)
    ;[chars[i], chars[j]] = [chars[j]!, chars[i]!]
  }
  return chars.join('')
}

function apiError(e: unknown): string {
  const ui = useUiStore()
  const err = e as ApiError
  return (err.code && (ui.t.errors as Record<string, string>)[err.code]) || err.message || String(e)
}

export const useUsersStore = defineStore('users', () => {
  const list = ref<ManagedUser[]>([])
  const options = ref<UsersOptions | null>(null)
  const loading = ref(false)
  const form = ref<UserForm | null>(null)
  const editId = ref<number | null>(null)
  const edit = ref<{
    modules: string[]
    password: string
    email: string
    show: boolean
    saving: boolean
    error: string
  } | null>(null)
  const query = ref('')
  const role = ref('')
  const status = ref('')

  const filteredUsers = computed(() => {
    const q = query.value.trim().toLowerCase()
    return list.value.filter(
      u =>
        (!q ||
          [u.username, u.brand_name, u.store_name].some(v =>
            (v || '').toLowerCase().includes(q),
          )) &&
        (!role.value || u.role === role.value) &&
        (!status.value || (status.value === 'active') === u.active),
    )
  })

  const formModules = computed(() => {
    const f = form.value
    const o = options.value
    return f && o && f.role ? o.modules[f.role] || [] : []
  })

  const formStores = computed(() => {
    const o = options.value
    if (!o) return [] as { brand: string; stores: UsersOptions['stores'] }[]
    const brands = Object.fromEntries((o.brands || []).map(b => [b.id, b.name]))
    const groups: Record<string, UsersOptions['stores']> = {}
    for (const s of o.stores) (groups[brands[s.brand_id] || '—'] ||= []).push(s)
    return Object.entries(groups).map(([brand, stores]) => ({ brand, stores }))
  })

  async function load() {
    const ui = useUiStore()
    loading.value = true
    try {
      const [users, opts] = await Promise.all([
        api<ManagedUser[]>('/users'),
        options.value ? Promise.resolve(null) : api<UsersOptions>('/users/options'),
      ])
      list.value = users
      if (opts) options.value = opts
    } catch (e) {
      ui.toast(apiError(e))
    } finally {
      loading.value = false
    }
  }

  function openNewUser() {
    const roles = options.value?.roles || []
    form.value = emptyForm()
    pickRole(roles[roles.length - 1] || '')
    void nextTick(() => document.getElementById('nu-username')?.focus())
  }

  function pickRole(r: Role | '') {
    const f = form.value
    if (!f) return
    f.role = r
    f.brand_id = ''
    f.store_id = ''
    f.modules = [...(options.value?.defaults?.[r] || [])]
    const o = options.value
    if (r === 'marca' && o?.brands.length === 1) f.brand_id = o.brands[0]!.id
    if (r === 'loja' && o?.stores.length === 1) f.store_id = o.stores[0]!.id
  }

  function toggleIn(arr: string[], m: string) {
    const i = arr.indexOf(m)
    if (i >= 0) arr.splice(i, 1)
    else arr.push(m)
  }

  function genPassword() {
    const ui = useUiStore()
    const f = form.value
    if (!f) return
    f.password = randomPassword()
    f.show = true
    ui.toast(ui.t.um.generated, 'ok')
  }

  async function submitNewUser() {
    const ui = useUiStore()
    const f = form.value
    if (!f) return
    f.error = ''
    if (!DATA_MODULES.some(m => f.modules.includes(m))) {
      f.error = ui.t.errors.no_modules
      return
    }
    f.saving = true
    try {
      const body = {
        username: f.username.trim().toLowerCase(),
        password: f.password,
        role: f.role,
        brand_id: f.role === 'marca' ? Number(f.brand_id) || null : null,
        store_id: f.role === 'loja' ? Number(f.store_id) || null : null,
        modules: MODULE_ORDER.filter(m => f.modules.includes(m)),
        email: f.email.trim() || null,
      }
      const created = await api<{ username: string }>('/users', body)
      ui.toast(ui.t.um.created(created.username), 'ok')
      form.value = null
      await load()
    } catch (e) {
      f.error = apiError(e)
    } finally {
      if (form.value) f.saving = false
    }
  }

  function startEdit(u: ManagedUser) {
    if (editId.value === u.id) {
      editId.value = null
      return
    }
    editId.value = u.id
    edit.value = {
      modules: [...u.modules],
      password: '',
      email: u.email || '',
      show: false,
      saving: false,
      error: '',
    }
  }

  function editableModules(u: ManagedUser) {
    return options.value?.modules?.[u.role] || []
  }

  async function saveEdit(u: ManagedUser) {
    const ui = useUiStore()
    const e = edit.value
    if (!e) return
    e.error = ''
    const body: Record<string, unknown> = {}
    const mods = MODULE_ORDER.filter(m => e.modules.includes(m))
    if (mods.join() !== u.modules.join()) body.modules = mods
    if (e.password) body.password = e.password
    if (e.email.trim() !== (u.email || '')) body.email = e.email.trim()
    if (!Object.keys(body).length) {
      editId.value = null
      return
    }
    e.saving = true
    try {
      await api(`/users/${u.id}`, body, 'PATCH')
      ui.toast(ui.t.um.saved, 'ok')
      editId.value = null
      await load()
    } catch (err) {
      e.error = apiError(err)
    } finally {
      e.saving = false
    }
  }

  async function toggleActive(u: ManagedUser) {
    const ui = useUiStore()
    if (u.active) {
      const ok = await ui.confirmDialog({
        title: ui.t.um.disableTitle,
        subject: u.username,
        text: ui.t.um.disableText,
        confirm: ui.t.um.disable,
        danger: true,
      })
      if (!ok) return
    }
    try {
      await api(`/users/${u.id}`, { active: !u.active }, 'PATCH')
      ui.toast(u.active ? ui.t.um.disabled : ui.t.um.enabled, 'ok')
      await load()
    } catch (e) {
      ui.toast(apiError(e))
    }
  }

  async function removeUser(u: ManagedUser) {
    const ui = useUiStore()
    const ok = await ui.confirmDialog({
      title: ui.t.um.deleteTitle,
      subject: u.username,
      text: ui.t.um.deleteText,
      confirm: ui.t.um.delete,
      danger: true,
    })
    if (!ok) return
    try {
      await api(`/users/${u.id}`, null, 'DELETE')
      ui.toast(ui.t.um.deleted, 'ok')
      await load()
    } catch (e) {
      ui.toast(apiError(e))
    }
  }

  function scopeOf(u: ManagedUser): string {
    const ui = useUiStore()
    if (u.role === 'admin' || u.role === 'imperador') return ui.t.um.scopeAll
    if (u.role === 'marca') return u.brand_name || '—'
    return [u.store_name, u.brand_name].filter(Boolean).join(' · ')
  }

  return {
    list,
    options,
    loading,
    form,
    editId,
    edit,
    query,
    role,
    status,
    filteredUsers,
    formModules,
    formStores,
    load,
    openNewUser,
    pickRole,
    toggleIn,
    genPassword,
    submitNewUser,
    startEdit,
    editableModules,
    saveEdit,
    toggleActive,
    removeUser,
    scopeOf,
  }
})
