import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useDashboardStore } from '@/stores/dashboard'
import { useUsersStore } from '@/stores/users'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'

vi.mock('@/lib/dash-charts', () => ({
  drawDashCharts: vi.fn().mockResolvedValue(undefined),
  destroyDashCharts: vi.fn(),
}))

describe('dashboard store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    const auth = useAuthStore()
    auth.token = 'tok'
    auth.wireApi()
    useUiStore().setLang('en', false)
  })

  it('loads dashboard data', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          revenue: {
            this_month_to_date: 10,
            last_month_same_days: 8,
            change_pct: 25,
            days: 5,
          },
        }),
      }),
    )
    const dash = useDashboardStore()
    await dash.load()
    expect(dash.data?.revenue?.this_month_to_date).toBe(10)
    expect(dash.error).toBe('')
  })

  it('sets error on failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        statusText: 'fail',
        json: async () => ({ detail: 'nope' }),
      }),
    )
    const dash = useDashboardStore()
    await dash.load()
    expect(dash.data).toBeNull()
    expect(dash.error).toBeTruthy()
  })
})

describe('users store filter', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    useAuthStore().wireApi()
  })

  it('filters by query and role', () => {
    const um = useUsersStore()
    um.list = [
      {
        id: 1,
        username: 'alice',
        role: 'loja',
        modules: ['sql'],
        active: true,
        brand_name: 'BurgerLab',
        store_name: 'Maia',
      },
      {
        id: 2,
        username: 'bob',
        role: 'marca',
        modules: ['sql'],
        active: false,
        brand_name: 'Café',
      },
    ]
    um.query = 'mai'
    expect(um.filteredUsers.map(u => u.username)).toEqual(['alice'])
    um.query = ''
    um.role = 'marca'
    expect(um.filteredUsers.map(u => u.username)).toEqual(['bob'])
    um.role = ''
    um.status = 'inactive'
    expect(um.filteredUsers.map(u => u.username)).toEqual(['bob'])
  })
})
