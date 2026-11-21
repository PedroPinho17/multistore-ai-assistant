/**
 * Features come only from the API (`/me` and login). There are no defaults here: if the list is
 * missing (an old session), nothing extra is shown and the app reloads `/me`.
 */
export const FEATURES = [
  'chat',
  'forecast',
  'orders',
  'dashboard',
  'review',
  'users',
  'admin',
] as const
export type Feature = (typeof FEATURES)[number]

/** Any of these opens the chat page and the conversations; each question is checked again. */
export const CHAT_FEATURES: readonly Feature[] = ['chat', 'forecast', 'orders']

export function hasFeature(listed: string[] | null | undefined, feature: string): boolean {
  return !!listed?.includes(feature)
}

export function hasAnyFeature(
  listed: string[] | null | undefined,
  features: readonly string[],
): boolean {
  return features.some(f => hasFeature(listed, f))
}
