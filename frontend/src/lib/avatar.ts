const AVATAR_COLORS = [
  '#B42318',
  '#B54708',
  '#027A48',
  '#0E7090',
  '#175CD3',
  '#5925DC',
  '#C11574',
  '#4E5BA6',
  '#475467',
  '#93370D',
]

export const AVATAR_TYPES = ['image/png', 'image/jpeg', 'image/webp']
export const AVATAR_MAX_BYTES = 2 * 1024 * 1024

export function avatarColor(name: string): string {
  let h = 0x811c9dc5
  for (const ch of name || '') {
    h ^= ch.codePointAt(0)!
    h = Math.imul(h, 0x01000193)
  }
  return AVATAR_COLORS[(h >>> 0) % AVATAR_COLORS.length]!
}

export function avatarInitials(name: string): string {
  return (
    (name || '')
      .split(/[.\s_-]+/)
      .filter(Boolean)
      .map(p => p[0])
      .join('')
      .slice(0, 2)
      .toUpperCase() || '?'
  )
}

const avatarCache = new Map<string, Promise<string>>()

/** Fetch avatar with Bearer and cache as data URL (CSP allows data: for img-src). */
export function loadAvatar(url: string, token: string): Promise<string> {
  if (!avatarCache.has(url)) {
    const p = fetch(url, { headers: { Authorization: 'Bearer ' + token } })
      .then(r => {
        if (!r.ok) throw new Error(String(r.status))
        return r.blob()
      })
      .then(
        blob =>
          new Promise<string>((resolve, reject) => {
            const reader = new FileReader()
            reader.onload = () => resolve(String(reader.result))
            reader.onerror = () => reject(reader.error)
            reader.readAsDataURL(blob)
          }),
      )
    p.catch(() => avatarCache.delete(url))
    avatarCache.set(url, p)
  }
  return avatarCache.get(url)!
}

export function clearAvatarCache(): void {
  avatarCache.clear()
}
