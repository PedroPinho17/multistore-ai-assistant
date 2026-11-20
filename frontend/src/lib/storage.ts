/** sessionStorage helper (token disappears when the tab closes). */
export const sessionStore = {
  get(k: string): string | null {
    try {
      return sessionStorage.getItem(k)
    } catch {
      return null
    }
  },
  set(k: string, v: string): void {
    try {
      sessionStorage.setItem(k, v)
    } catch {
      /* ignore quota / private mode */
    }
  },
  del(k: string): void {
    try {
      sessionStorage.removeItem(k)
    } catch {
      /* ignore */
    }
  },
}

/** localStorage for durable prefs (theme, lang). */
export const prefs = {
  get(k: string): string | null {
    try {
      return localStorage.getItem(k)
    } catch {
      return null
    }
  },
  set(k: string, v: string): void {
    try {
      localStorage.setItem(k, v)
    } catch {
      /* ignore */
    }
  },
  del(k: string): void {
    try {
      localStorage.removeItem(k)
    } catch {
      /* ignore */
    }
  },
}

// Drop tokens left in localStorage by older builds
try {
  localStorage.removeItem('token')
  localStorage.removeItem('user')
} catch {
  /* ignore */
}
