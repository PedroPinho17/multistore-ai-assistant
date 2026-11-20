/**
 * Server-Sent Events parser for /ask/stream (no Vue/browser deps).
 *
 *   const parser = createSseParser(onEvent, onBadEvent)
 *   parser.push(decodedText)
 *   parser.end()
 */
export type SseEventHandler = (event: unknown) => void
export type SseBadEventHandler = (raw: string, err: unknown) => void

export interface SseParser {
  push(text: string): void
  end(): void
}

export function createSseParser(
  onEvent: SseEventHandler,
  onBadEvent?: SseBadEventHandler,
): SseParser {
  const separator = /\r?\n\r?\n/g
  let parts: string[] = []
  let tail = ''
  let first = true

  function dispatch(block: string) {
    if (first) {
      block = block.replace(/^\uFEFF/, '')
      first = false
    }
    const lines = block.split(/\r?\n/).filter(l => l.startsWith('data:'))
    if (!lines.length) return
    const data = lines.map(l => l.slice(5).replace(/^ /, '')).join('\n')
    if (!data.trim()) return
    let event: unknown
    try {
      event = JSON.parse(data)
    } catch (err) {
      onBadEvent?.(data, err)
      return
    }
    onEvent(event)
  }

  return {
    push(text: string) {
      if (!text) return
      separator.lastIndex = 0
      if (!separator.test(tail + text)) {
        parts.push(text)
        tail = (tail + text).slice(-3)
        return
      }
      let buffer = parts.join('') + text
      parts = []
      separator.lastIndex = Math.max(0, buffer.length - text.length - tail.length)
      let match: RegExpExecArray | null
      while ((match = separator.exec(buffer)) !== null) {
        const block = buffer.slice(0, match.index)
        buffer = buffer.slice(match.index + match[0].length)
        separator.lastIndex = 0
        dispatch(block)
      }
      if (buffer) parts.push(buffer)
      tail = buffer.slice(-3)
    },
    end() {
      const rest = parts.join('')
      parts = []
      tail = ''
      if (rest.trim()) dispatch(rest)
    },
  }
}
