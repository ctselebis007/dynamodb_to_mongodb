import { describe, expect, it } from 'vitest'
import { CLUSTER_TIERS, HORIZONS, quadCeiling, size } from './sizing'

const quads = (id: string) => HORIZONS.find((h) => h.id === id)!.quads

describe('size', () => {
  it('keeps the M30 floor and S20 Search Nodes up to the near term', () => {
    for (const id of ['current', 'near', 'horizon-1m']) {
      const s = size(quads(id), 30)
      expect([s.cluster.name, s.search.name]).toEqual(['M30', 'S20'])
    }
  })

  it('moves to M40 once the working set outgrows the M30 cache', () => {
    const ceiling = quadCeiling(CLUSTER_TIERS[0])
    expect(size(ceiling - 50_000, 2).cluster.name).toBe('M30')
    expect(size(ceiling + 50_000, 2).cluster.name).toBe('M40')
    expect(size(quads('horizon-3m'), 30).cluster.name).toBe('M40')
  })

  it('grows the vector index and Search tier with retained snapshots', () => {
    const few = size(quads('near'), 2)
    const many = size(quads('near'), 365)
    expect(many.vectorIndexBytes).toBeGreaterThan(few.vectorIndexBytes * 100)
    expect(size(20_000_000, 365).search.name).not.toBe('S20')
  })
})
