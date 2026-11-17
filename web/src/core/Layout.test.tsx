import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import { Banner, Nav } from './Layout'
import { loadModules, type DemoModule } from './modules'
import type { SetupStatus } from './status'

const fake: DemoModule = { route: { path: 'fake', element: <div /> }, navItem: { label: 'Fake Module' } }

function status(over: Partial<SetupStatus> = {}): SetupStatus {
  return {
    configured: true,
    reachable: true,
    seeded: true,
    indexed: true,
    reseed_required: false,
    meta: null,
    modules: ['fake'],
    error: null,
    ...over,
  }
}

describe('Nav', () => {
  it('discovers modules from the glob shape and shows them', () => {
    const modules = loadModules({ '../modules/fake/index.tsx': fake, '../modules/bad/index.tsx': {} })
    render(<Nav modules={modules} status={status()} />, { wrapper: MemoryRouter })
    expect(screen.getByRole('link', { name: 'Fake Module' })).toHaveAttribute('href', '/fake')
  })

  it('disables module links until seeded and indexed', () => {
    render(<Nav modules={[fake]} status={status({ indexed: false })} />, { wrapper: MemoryRouter })
    expect(screen.queryByRole('link', { name: 'Fake Module' })).toBeNull()
    expect(screen.getByText('Fake Module')).toHaveAttribute('aria-disabled', 'true')
  })

  it('keeps public modules enabled before seeding', () => {
    const story: DemoModule = { route: { path: 'story', element: <div />, public: true }, navItem: { label: 'Story' } }
    render(<Nav modules={[fake, story]} status={status({ seeded: false })} />, { wrapper: MemoryRouter })
    expect(screen.getByRole('link', { name: 'Story' })).toHaveAttribute('href', '/story')
    expect(screen.queryByRole('link', { name: 'Fake Module' })).toBeNull()
  })
})

describe('Banner', () => {
  it('shows on reseed_required', () => {
    render(<Banner status={status({ reseed_required: true })} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Re-seed required')
  })

  it('is hidden otherwise', () => {
    const { container } = render(<Banner status={status()} />)
    expect(container).toBeEmptyDOMElement()
  })
})
