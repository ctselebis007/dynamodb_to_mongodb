import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import type { Schemas } from '../../core/api'
import { ReloadTimeline } from './WritesPanel'

const pipeline = [{ $match: { graph: 'talent:metadata' } }, { $group: { _id: '$predicate', quads: { $sum: 1 } } }]

const result: Schemas['ReloadResult'] = {
  graph: 'talent:metadata',
  deleted: 2,
  inserted: 2,
  ms: 1500,
  total_ms: 1620,
  steps: [
    { name: 'Profile current graph', op: 'aggregate', kind: 'aggregate', in_transaction: false, command: pipeline, docs: 2, ms: 12.3, result: '2 quads across 1 predicates' },
    { name: 'Delete current graph', op: 'deleteMany', kind: 'write', in_transaction: true, command: { filter: { graph: 'talent:metadata' } }, docs: 2, ms: 250, result: '2 quads deleted' },
    { name: 'Commit transaction', op: 'commitTransaction', kind: 'txn', in_transaction: true, command: { commitTransaction: 1 }, docs: null, ms: 1200, result: 'changes visible to readers' },
  ],
}

describe('ReloadTimeline', () => {
  it('lists each step with its time and expands to show the pipeline', async () => {
    const user = userEvent.setup()
    render(<ReloadTimeline result={result} />)
    const rows = screen.getAllByRole('row').slice(1)
    expect(rows).toHaveLength(3)
    expect(within(rows[0]).getByText('12.3 ms')).toBeInTheDocument()
    expect(within(rows[2]).getByText('1.20 s')).toBeInTheDocument()
    expect(screen.queryByTestId('reload-step-command')).not.toBeInTheDocument()

    await user.click(screen.getByText('Profile current graph'))
    expect(screen.getByTestId('reload-step-command')).toHaveTextContent('"$group"')
    expect(screen.getByText('2 quads across 1 predicates')).toBeInTheDocument()
  })
})
