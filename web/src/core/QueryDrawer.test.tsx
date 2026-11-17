import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { QueryDrawer, abbreviate } from './QueryDrawer'

const pipeline = [
  { $vectorSearch: { index: 'v', path: 'embedding', queryVector: Array.from({ length: 20 }, (_, i) => i / 10) } },
  { $limit: 5 },
]

describe('QueryDrawer', () => {
  it('copy writes the exact pipeline JSON', async () => {
    const user = userEvent.setup()
    const writeText = vi.spyOn(navigator.clipboard, 'writeText')
    render(<QueryDrawer open onClose={() => {}} title="Vector" pipeline={pipeline} timings={{ server_ms: 12.3 }} />)
    await user.click(screen.getByRole('button', { name: 'Copy' }))
    expect(writeText).toHaveBeenCalledWith(JSON.stringify(pipeline, null, 2))
    expect(screen.getByTestId('pipeline')).toHaveTextContent('… 20 numbers')
  })

  it('explain toggle requests explain output', async () => {
    const user = userEvent.setup()
    const fetchExplain = vi.fn(async () => ({ executionStats: { nReturned: 5 } }))
    render(
      <QueryDrawer
        open
        onClose={() => {}}
        title="Vector"
        pipeline={pipeline}
        timings={{ server_ms: 1, embed_ms: 2 }}
        fetchExplain={fetchExplain}
      />,
    )
    await user.click(screen.getByLabelText('Explain'))
    expect(fetchExplain).toHaveBeenCalledOnce()
    expect(await screen.findByText(/nReturned/)).toBeInTheDocument()
  })

  it('abbreviate keeps short arrays', () => {
    expect(abbreviate({ a: [1, 2, 3] })).toEqual({ a: [1, 2, 3] })
  })
})
