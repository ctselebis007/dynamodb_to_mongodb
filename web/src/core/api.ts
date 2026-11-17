import type { components } from './api-types'

export type Schemas = components['schemas']

export class ApiError extends Error {
  readonly code: string
  readonly hint: string
  readonly status: number

  constructor(code: string, message: string, hint: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.hint = hint
    this.status = status
  }
}

interface ErrorEnvelope {
  error?: { code?: string; message?: string; hint?: string }
}

export async function apiFetch<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = init
  const res = await fetch(path, {
    ...rest,
    headers: { Accept: 'application/json', ...(json !== undefined && { 'Content-Type': 'application/json' }), ...headers },
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  })
  const text = await res.text()
  let body: unknown
  try {
    body = text ? JSON.parse(text) : undefined
  } catch {
    body = undefined
  }
  if (!res.ok) {
    const err = (body as ErrorEnvelope | undefined)?.error
    if (err?.code) throw new ApiError(err.code, err.message ?? err.code, err.hint ?? '', res.status)
    throw new ApiError(
      `HTTP_${res.status}`,
      res.statusText || `Request failed (${res.status})`,
      'Is the API running? Check the terminal where `npm run dev` is running.',
      res.status,
    )
  }
  return body as T
}

export const api = {
  get: <T>(path: string) => apiFetch<T>(path),
  post: <T>(path: string, json: unknown = {}) => apiFetch<T>(path, { method: 'POST', json }),
  put: <T>(path: string, json: unknown) => apiFetch<T>(path, { method: 'PUT', json }),
}
