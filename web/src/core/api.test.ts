import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, api } from './api'

function mockFetch(status: number, body: string, statusText = '') {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(body, { status, statusText })))
}

afterEach(() => vi.unstubAllGlobals())

describe('apiFetch', () => {
  it('parses the error envelope into ApiError', async () => {
    mockFetch(409, JSON.stringify({ error: { code: 'NOT_SEEDED', message: 'Not seeded', hint: 'Run Seed' } }))
    const err = await api.get('/api/x').catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err).toMatchObject({ code: 'NOT_SEEDED', message: 'Not seeded', hint: 'Run Seed', status: 409 })
  })

  it('handles a non-JSON 500', async () => {
    mockFetch(500, '<html>Internal Server Error</html>', 'Internal Server Error')
    const err = await api.get('/api/x').catch((e: unknown) => e)
    expect(err).toMatchObject({ code: 'HTTP_500', status: 500 })
    expect((err as ApiError).hint).toMatch(/API running/)
  })

  it('returns parsed JSON and sends JSON bodies', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ ok: true })))
    vi.stubGlobal('fetch', fetchMock)
    expect(await api.post('/api/y', { a: 1 })).toEqual({ ok: true })
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(init.body).toBe('{"a":1}')
    expect(init.method).toBe('POST')
  })
})
