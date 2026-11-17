import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { QueryCard, percentile, type QueryResult, type QuerySpec } from './QueryCard'

const spec: QuerySpec = {
  id: 'T1',
  group: 'talent',
  title: 'All direct children of one business',
  pattern: 'Point read',
  dynamo_today: '1 Query',
  defaults: { subject: 'business:REALGAR_SHOAL' },
  ideal: [],
}

const result = (over: Partial<QueryResult> = {}): QueryResult => ({
  results: [{ count: 18 }],
  pipeline: [{ $match: { subject: 'business:REALGAR_SHOAL' } }],
  timings: { server_ms: 4.2, embed_ms: null, rerank_ms: null },
  explain: null,
  scale: 1,
  match: true,
  checks: [{ path: 'count', mode: 'eq', expected: 18, actual: 18, ok: true }],
  note: null,
  ...over,
})

describe('QueryCard', () => {
  it('runs with edited inputs and shows the ideal-answer comparison', async () => {
    const user = userEvent.setup()
    const run = vi.fn(async () => result())
    render(<QueryCard spec={spec} run={run} />)
    const input = screen.getByLabelText('subject')
    await user.clear(input)
    await user.type(input, 'business:WADI')
    await user.click(screen.getByRole('button', { name: 'Run' }))
    expect(run).toHaveBeenCalledWith({ subject: 'business:WADI' }, false)
    expect(await screen.findByText('✅ Matches ideal answer')).toBeInTheDocument()
    expect(screen.getByText('DynamoDB today: 1 Query')).toBeInTheDocument()
  })

  it('shows a mismatch and n/a when scaled', async () => {
    const user = userEvent.setup()
    const run = vi
      .fn()
      .mockResolvedValueOnce(result({ match: false, checks: [{ path: 'count', mode: 'eq', expected: 18, actual: 17, ok: false }] }))
      .mockResolvedValueOnce(result({ match: null, scale: 20, checks: [] }))
    render(<QueryCard spec={spec} run={run} />)
    await user.click(screen.getByRole('button', { name: 'Run' }))
    expect(await screen.findByText('❌ Differs from ideal answer')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Run' }))
    expect(await screen.findByText('n/a (scale ×20)')).toBeInTheDocument()
  })
})

describe('percentile', () => {
  it('uses nearest-rank', () => {
    const values = Array.from({ length: 20 }, (_, i) => i + 1)
    expect(percentile(values, 50)).toBe(10)
    expect(percentile(values, 95)).toBe(19)
  })
})
