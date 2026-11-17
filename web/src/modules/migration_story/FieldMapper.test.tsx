import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { TRANSFORMATIONS } from './data'
import { FieldMapper } from './FieldMapper'

const talent = TRANSFORMATIONS[0]

describe('FieldMapper', () => {
  it('hovering a DynamoDB key highlights the index that replaces it', async () => {
    const user = userEvent.setup()
    render(<FieldMapper t={talent} />)
    const dynamo = screen.getByRole('region', { name: 'DynamoDB item' })
    await user.hover(within(dynamo).getByText('GSI1PK:'))
    const mongo = screen.getByRole('region', { name: 'MongoDB document' })
    expect(within(mongo).getByText(/^object_predicate/).closest('li')).toHaveClass('ring-2')
    expect(within(mongo).getByText('subject:').closest('li')).toHaveAttribute('data-state', 'off')
  })

  it('legend chip highlights every field of one kind of change', async () => {
    const user = userEvent.setup()
    render(<FieldMapper t={talent} />)
    await user.click(screen.getByRole('button', { name: /Key attribute replaced by an index/ }))
    const dynamo = screen.getByRole('region', { name: 'DynamoDB item' })
    for (const key of ['PK:', 'SK:', 'GSI1PK:', 'GSI1SK:']) {
      expect(within(dynamo).getByText(key).closest('li')).toHaveAttribute('data-state', 'on')
    }
    expect(within(dynamo).getByText('graph:').closest('li')).toHaveAttribute('data-state', 'off')
  })
})

describe('transformation content', () => {
  it('every field and index points at a defined mapping', () => {
    for (const t of TRANSFORMATIONS) {
      const ids = new Set(t.mappings.map((m) => m.id))
      for (const ref of [...t.dynamo, ...t.mongo, ...t.indexes]) expect(ids).toContain(ref.map)
    }
  })
})
