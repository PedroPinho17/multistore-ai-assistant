import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api } from '@/api/client'
import type { ProfileData } from '@/api/types'
import { ApiError } from '@/api/types'
import { AVATAR_MAX_BYTES, AVATAR_TYPES } from '@/lib/avatar'
import { KIND_ORDER, pwStrength as strengthOf } from '@/lib/format'
import { useAuthStore } from '@/stores/auth'
import { useChatStore } from '@/stores/chat'
import { useUiStore } from '@/stores/ui'

export const useProfileStore = defineStore('profile', () => {
  const profile = ref<ProfileData | null>(null)
  const avatarSaving = ref(false)
  const clock = ref(Date.now())
  const pw = ref({
    current: '',
    new: '',
    confirm: '',
    show: false,
    saving: false,
    error: '',
    ok: false,
  })
  const em = ref({ value: '', saving: false, error: '', ok: false })
  let clockTimer: ReturnType<typeof setInterval> | null = null

  const pwStrength = computed(() => strengthOf(pw.value.new))

  function startClock() {
    clock.value = Date.now()
    if (clockTimer) clearInterval(clockTimer)
    clockTimer = setInterval(() => {
      clock.value = Date.now()
    }, 30000)
  }

  function stopClock() {
    if (clockTimer) clearInterval(clockTimer)
    clockTimer = null
  }

  async function load() {
    try {
      profile.value = await api<ProfileData>('/profile')
      em.value = {
        value: profile.value.email || '',
        saving: false,
        error: '',
        ok: false,
      }
    } catch (e) {
      // Keeps what was shown; says why (a 401 already logged out and went to the login page)
      if (e instanceof ApiError && e.status !== 401) useUiStore().toast(e.message)
    }
  }

  function kindRows() {
    const ui = useUiStore()
    const counts = profile.value?.stats?.by_kind || {}
    const max = Math.max(1, ...Object.values(counts).map(Number))
    return KIND_ORDER.filter(k => counts[k]).map(k => ({
      key: k,
      label: (ui.t.p.kinds as Record<string, string>)[k] || k,
      n: counts[k]!,
      pct: Math.round((100 * counts[k]!) / max),
    }))
  }

  async function uploadAvatar(file: File | undefined) {
    const ui = useUiStore()
    const auth = useAuthStore()
    if (!file || avatarSaving.value) return
    if (!AVATAR_TYPES.includes(file.type) || file.size > AVATAR_MAX_BYTES) {
      ui.toast(ui.t.avatar.bad)
      return
    }
    avatarSaving.value = true
    try {
      const { avatar_url } = await api<{ avatar_url: string }>('/me/avatar', file)
      setMyAvatar(avatar_url)
      ui.toast(ui.t.avatar.saved, 'ok')
      void auth.refreshMe()
    } catch (e) {
      ui.toast(e instanceof ApiError ? e.message : String(e))
    } finally {
      avatarSaving.value = false
    }
  }

  async function removeAvatar() {
    const ui = useUiStore()
    try {
      await api('/me/avatar', null, 'DELETE')
      setMyAvatar(null)
      ui.toast(ui.t.avatar.removed, 'ok')
    } catch (e) {
      ui.toast(e instanceof ApiError ? e.message : String(e))
    }
  }

  function setMyAvatar(url: string | null) {
    const auth = useAuthStore()
    if (!auth.user) return
    auth.user = { ...auth.user, avatar_url: url }
    try {
      sessionStorage.setItem('user', JSON.stringify(auth.user))
    } catch {
      /* ignore */
    }
  }

  async function changePassword() {
    const ui = useUiStore()
    const auth = useAuthStore()
    const p = ui.t.p
    const state = pw.value
    state.error = ''
    state.ok = false
    const v = state.new
    if (v.length < 8) state.error = p.errShort
    else if (/^[0-9]+$/.test(v) || /^[\p{L}]+$/u.test(v)) state.error = p.errMix
    else if (v.toLowerCase().includes((auth.user?.username || '').toLowerCase()))
      state.error = p.errUser
    else if (v === state.current) state.error = p.errSame
    else if (v !== state.confirm) state.error = p.errMatch
    if (state.error) return
    state.saving = true
    try {
      const data = await api<{ token?: string }>('/profile/password', {
        current_password: state.current,
        new_password: v,
      })
      if (data.token) {
        auth.token = data.token
        try {
          sessionStorage.setItem('token', data.token)
        } catch {
          /* ignore */
        }
      }
      pw.value = {
        current: '',
        new: '',
        confirm: '',
        show: false,
        saving: false,
        error: '',
        ok: true,
      }
    } catch (e) {
      const err = e as ApiError
      state.error =
        err.status === 429
          ? ui.t.tooMany
          : err.code === 'pw_wrong_current'
            ? p.wrongCurrent
            : err.message
    } finally {
      state.saving = false
    }
  }

  async function saveEmail() {
    const state = em.value
    state.error = ''
    state.ok = false
    state.saving = true
    try {
      const r = await api<{ email: string | null }>(
        '/profile/email',
        { email: state.value.trim() || null },
        'PUT',
      )
      state.value = r.email || ''
      state.ok = true
      if (profile.value) profile.value.email = r.email
    } catch (e) {
      state.error = e instanceof ApiError ? e.message : String(e)
    } finally {
      state.saving = false
    }
  }

  /** An answer is streaming in the chat: deleting everything now would delete its conversation. */
  function chatBusy(): boolean {
    const chat = useChatStore()
    return chat.loading || chat.streaming
  }

  async function deleteAllConversations() {
    const ui = useUiStore()
    const n = profile.value?.stats?.conversations || 0
    if (!n) return
    if (chatBusy()) {
      ui.toast(ui.t.p.clearBusy)
      return
    }
    const ok = await ui.confirmDialog({
      title: ui.t.dlg.clearTitle,
      text: ui.t.p.confirmClear(n),
      confirm: ui.t.dlg.del,
      danger: true,
    })
    if (!ok) return
    if (chatBusy()) {
      ui.toast(ui.t.p.clearBusy)
      return
    }
    try {
      await api('/conversations', null, 'DELETE')
      // Not chat.reset(): that is the logout reset (cancels requests, clears everything)
      useChatStore().forgetConversations()
      await load()
      ui.toast(ui.t.dlg.cleared, 'ok')
    } catch (e) {
      ui.toast(e instanceof ApiError ? e.message : String(e))
    }
  }

  return {
    profile,
    avatarSaving,
    clock,
    pw,
    em,
    pwStrength,
    startClock,
    stopClock,
    load,
    kindRows,
    uploadAvatar,
    removeAvatar,
    setMyAvatar,
    changePassword,
    saveEmail,
    deleteAllConversations,
  }
})
