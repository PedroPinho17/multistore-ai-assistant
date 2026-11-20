import { describe, expect, it } from 'vitest'
import { createSseParser } from '@/lib/sse'

const sse = (event: unknown) => `data: ${JSON.stringify(event)}\n\n`

function feed(text: string, sizes: number | number[], { end = true } = {}) {
  const events: unknown[] = []
  const bad: string[] = []
  const parser = createSseParser(
    ev => events.push(ev),
    raw => bad.push(raw),
  )
  const bytes = new TextEncoder().encode(text)
  const decoder = new TextDecoder()
  let i = 0
  let k = 0
  while (i < bytes.length) {
    const size = Array.isArray(sizes) ? sizes[k++ % sizes.length]! : sizes
    parser.push(decoder.decode(bytes.slice(i, i + size), { stream: true }))
    i += size
  }
  parser.push(decoder.decode())
  if (end) parser.end()
  return { events, bad }
}

const ANSWER = [
  { type: 'status', step: 'classify' },
  {
    type: 'data',
    kind: 'sql',
    sql: 'SELECT 1',
    columns: ['marca'],
    rows: [['BurgerLab'], ['Café Aroma']],
  },
  { type: 'token', text: 'Duas ' },
  { type: 'token', text: 'marcas → ≈ ok.' },
  { type: 'done', kind: 'sql', answer: 'Duas marcas → ≈ ok.', conversation_id: 7 },
]

describe('createSseParser', () => {
  it('reassembles events split across reads (down to 1 byte)', () => {
    const text = ANSWER.map(sse).join('')
    for (const sizes of [1, 2, 3, 7, [5, 1, 11, 2], 64, text.length]) {
      const { events, bad } = feed(text, sizes)
      expect(events).toEqual(ANSWER)
      expect(bad).toEqual([])
    }
  })

  it('delivers a trailing event without blank line on end()', () => {
    const text = ANSWER.map(sse).join('').replace(/\n\n$/, '')
    const partial = feed(text, 4, { end: false })
    expect((partial.events.at(-1) as { type: string }).type).toBe('token')
    expect(feed(text, 4).events).toEqual(ANSWER)
    expect(feed(text.replace(/\n$/, ''), 4).events).toEqual(ANSWER)
  })

  it('accepts CRLF separators even when split', () => {
    const crlf = ANSWER.map(e => `data: ${JSON.stringify(e)}\r\n\r\n`).join('')
    for (const sizes of [1, 2, 3, [1, 1, 2], 100]) {
      expect(feed(crlf, sizes).events).toEqual(ANSWER)
    }
    const mixed =
      sse(ANSWER[0]) +
      `data: ${JSON.stringify(ANSWER[1])}\r\n\r\n` +
      `data: ${JSON.stringify(ANSWER[4])}\n\r\n`
    expect(feed(mixed, 3).events).toEqual([ANSWER[0], ANSWER[1], ANSWER[4]])
  })

  it('handles large multiline payloads with multibyte cuts', () => {
    const rows = Array.from({ length: 500 }, (_, i) => [
      i,
      `Loja ${i} — Café Aroma São João`,
      i * 1.25,
      '→ ≈ €',
      null,
      'pão de hambúrguer'.repeat(3),
    ])
    const big = {
      type: 'data',
      kind: 'sql',
      sql: 'SELECT …',
      columns: ['id', 'loja', 'v', 's', 'n', 'txt'],
      rows,
    }
    const text = sse(big) + sse({ type: 'done', rows })
    expect(text.length).toBeGreaterThan(100_000)
    for (const sizes of [1, 7, 997, 16_384]) {
      const { events, bad } = feed(text, sizes)
      expect(events.length).toBe(2)
      expect(events[0]).toEqual(big)
      expect((events[1] as { rows: unknown }).rows).toEqual(rows)
      expect(bad).toEqual([])
    }
  })

  it('supports no-token paths (forecast/orders)', () => {
    const orders = [
      { type: 'status', step: 'classify' },
      { type: 'status', step: 'forecast' },
      {
        type: 'data',
        kind: 'orders',
        sql: null,
        columns: ['ingredient', 'unit', 'to_order'],
        rows: [['Pão', 'un', 12]],
      },
      { type: 'status', step: 'answer' },
      {
        type: 'done',
        kind: 'orders',
        answer: 'Encomenda 12 pães.',
        conversation_id: 99,
      },
    ]
    for (const sizes of [1, 9, 1000]) {
      const { events } = feed(orders.map(sse).join(''), sizes)
      expect(events).toEqual(orders)
      expect(events.some(e => (e as { type: string }).type === 'token')).toBe(false)
      expect((events.at(-1) as { answer: string }).answer).toBe('Encomenda 12 pães.')
    }
    expect(
      (feed(orders.map(sse).join('').trimEnd(), 5).events.at(-1) as { type: string }).type,
    ).toBe('done')
  })

  it('routes invalid JSON to onBadEvent without breaking later events', () => {
    const text = sse(ANSWER[0]) + 'data: {nao é json\n\n' + 'data: [NaN]\n\n' + sse(ANSWER[4])
    const { events, bad } = feed(text, 3)
    expect(events).toEqual([ANSWER[0], ANSWER[4]])
    expect(bad).toEqual(['{nao é json', '[NaN]'])
  })

  it('lets handler errors propagate (not treated as bad events)', () => {
    const bad: string[] = []
    const parser = createSseParser(ev => {
      if ((ev as { type: string }).type === 'done') throw new Error('bug no handler')
    }, raw => bad.push(raw))
    expect(() => parser.push(sse(ANSWER[4]))).toThrow(/bug no handler/)
    expect(bad).toEqual([])
    const atEnd = createSseParser(() => {
      throw new Error('bug no fim')
    })
    atEnd.push(`data: ${JSON.stringify(ANSWER[4])}`)
    expect(() => atEnd.end()).toThrow(/bug no fim/)
  })

  it('ignores comments/keep-alives, strips BOM, joins multi-line data', () => {
    const text =
      '\uFEFF: keep-alive\n\n' +
      'event: message\nid: 1\n' +
      sse(ANSWER[0]) +
      'data: {"type": "done",\ndata:  "answer": "ok"}\n\n' +
      '\n\n'
    const { events, bad } = feed(text, 2)
    expect(events).toEqual([ANSWER[0], { type: 'done', answer: 'ok' }])
    expect(bad).toEqual([])
  })

  it('does not cost O(n²) on a large event in tiny chunks', () => {
    const event = { type: 'data', s: 'x'.repeat(1_600_000) }
    const text = sse(event)
    let got: { s: string } | null = null
    const parser = createSseParser(ev => {
      got = ev as { s: string }
    })
    const start = performance.now()
    for (let i = 0; i < text.length; i += 16) parser.push(text.slice(i, i + 16))
    const ms = performance.now() - start
    expect(got!.s.length).toBe(1_600_000)
    expect(ms).toBeLessThan(2000)
  })
})
