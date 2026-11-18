import { useState } from 'react'
import {
  CLUSTER_TIERS,
  HORIZONS,
  OTHER_STORES_QUADS,
  QUAD,
  SEARCH_TIERS,
  SNAPSHOT,
  SNAPSHOT_OPTIONS,
  formatBytes,
  quadCeiling,
  size,
  wiredTigerCacheGB,
  type ClusterTier,
} from './sizing'

const tierSpec = (t: ClusterTier) => `${t.ramGB} GB RAM · ${t.vcpu} vCPU · ${t.storageGB} GB`

function TierBadge({ tier, tone }: { tier: ClusterTier; tone: 'cluster' | 'search' }) {
  return (
    <span
      className={`inline-block rounded px-2 py-0.5 font-mono text-sm font-semibold text-white ${tone === 'cluster' ? 'bg-mdb-forest' : 'bg-sky-700'}`}
      title={tierSpec(tier)}
    >
      {tier.name}
    </span>
  )
}

export function ClusterSizing() {
  const [snapshots, setSnapshots] = useState(30)
  const [otherStores, setOtherStores] = useState(false)
  const extra = otherStores ? OTHER_STORES_QUADS : 0
  const rows = HORIZONS.map((h) => ({ h, s: size(h.quads + (h.id === 'current' ? 0 : extra), h.id === 'current' ? 2 : snapshots) }))
  const near = rows.find((r) => r.h.id === 'near')!.s
  const peak = rows[rows.length - 1].s
  const m30Ceiling = quadCeiling(CLUSTER_TIERS[0])

  const metric = (label: string, value: (s: (typeof rows)[number]['s']) => React.ReactNode, hint?: string) => (
    <tr className="border-t border-slate-100">
      <th scope="row" className="w-64 px-3 py-2 text-left font-normal text-slate-600">
        {label}
        {hint && <span className="block text-xs text-slate-400">{hint}</span>}
      </th>
      {rows.map(({ h, s }) => (
        <td key={h.id} className="px-3 py-2 text-right tabular-nums">
          {value(s)}
        </td>
      ))}
    </tr>
  )

  return (
    <section className="space-y-4">
      <div>
        <p className="text-xs font-semibold tracking-widest text-mdb-forest uppercase">6 · Sizing</p>
        <h2 className="text-xl font-semibold text-mdb-slate">Cluster and Search Node size for the future volumes</h2>
        <p className="mt-1 max-w-4xl text-sm text-slate-600">
          Projected from the per-document sizes measured on this demo&apos;s Atlas database and the estimates in
          Sample_Queries_Criteria.md §4. Phase 1 needs are small; the tier is set by the production floor first, then by
          keeping the working set in memory.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-4 text-sm">
        <label className="flex items-center gap-2">
          RDF 1.2 snapshots kept
          <select
            className="rounded border border-slate-300 px-2 py-1"
            value={snapshots}
            onChange={(e) => setSnapshots(Number(e.target.value))}
          >
            {SNAPSHOT_OPTIONS.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={otherStores} onChange={(e) => setOtherStores(e.target.checked)} />
          Include the two other quad stores (+{OTHER_STORES_QUADS.toLocaleString()} quads)
        </label>
        <span className="text-xs text-slate-500">Both are open [CONFIRM] items in §4.</span>
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-sm" aria-label="Sizing by horizon">
          <thead className="bg-slate-50 text-xs text-slate-500">
            <tr>
              <th className="px-3 py-2 text-left uppercase">Horizon</th>
              {rows.map(({ h }) => (
                <th key={h.id} className="px-3 py-2 text-right">
                  <span className="block text-sm font-semibold text-mdb-slate">{h.label}</span>
                  <span className="font-normal">{h.driver}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {metric('Quads', (s) => s.quads.toLocaleString())}
            {metric('RDF 1.2 items', (s) => s.aicpItems.toLocaleString(), `${SNAPSHOT.items} per snapshot`)}
            {metric('Data + indexes on disk', (s) => formatBytes(s.diskBytes))}
            {metric('Working set (RAM)', (s) => formatBytes(s.workingSetBytes), 'quad data + all indexes + 2 snapshots')}
            {metric('Base cluster', (s) => <TierBadge tier={s.cluster} tone="cluster" />, 'replica set, 3 nodes')}
            {metric('Search index (text)', (s) => formatBytes(s.textIndexBytes), 'talent_labels, estimate')}
            {metric('Vector index', (s) => formatBytes(s.vectorIndexBytes), 'aicp_semantic, 1,024 dims')}
            {metric('Dedicated Search Nodes', (s) => <TierBadge tier={s.search} tone="search" />, 'High-CPU, 2 nodes minimum')}
          </tbody>
        </table>
      </div>

      <div className="grid gap-3 lg:grid-cols-3">
        <article className="rounded-xl border border-green-200 bg-green-50/60 p-4">
          <p className="text-xs font-semibold tracking-wide text-mdb-forest uppercase">Recommendation · Phase 1</p>
          <p className="mt-2 text-lg font-semibold text-mdb-slate">
            {near.cluster.name} + 2 × {near.search.name}
          </p>
          <p className="mt-1 text-sm text-slate-600">
            {near.cluster.name} ({tierSpec(near.cluster)}, {wiredTigerCacheGB(near.cluster)} GB cache) holds the near-term
            working set of {formatBytes(near.workingSetBytes)} with room to spare. Two {near.search.name} Search Nodes{' '}
            {`(${tierSpec(near.search)})`} keep the text and vector indexes in memory and off the database nodes.
          </p>
        </article>
        <article className="rounded-xl border border-slate-200 bg-white p-4">
          <p className="text-xs font-semibold tracking-wide text-slate-500 uppercase">Scale trigger</p>
          <p className="mt-2 text-lg font-semibold text-mdb-slate">
            ~{(m30Ceiling / 1_000_000).toFixed(1)}M quads → {CLUSTER_TIERS[1].name}
          </p>
          <p className="mt-1 text-sm text-slate-600">
            Past that, quad data and indexes ({(QUAD.dataBytes + QUAD.indexBytes).toLocaleString()} B per quad) exceed 70% of
            the {CLUSTER_TIERS[0].name} cache. At the high horizon the plan is <strong>{peak.cluster.name}</strong> +{' '}
            <strong>2 × {peak.search.name}</strong>. Scaling is online and can be automated with cluster auto-scaling.
          </p>
        </article>
        <article className="rounded-xl border border-slate-200 bg-white p-4">
          <p className="text-xs font-semibold tracking-wide text-slate-500 uppercase">Later phase (not sized)</p>
          <p className="mt-2 text-lg font-semibold text-mdb-slate">
            {CLUSTER_TIERS[1].name} + 2 × {SEARCH_TIERS[1].name}
          </p>
          <p className="mt-1 text-sm text-slate-600">
            Policy checks under 100 ms for low hundreds of readers are CPU-bound, not size-bound: double the vCPUs{' '}
            {`(${CLUSTER_TIERS[1].vcpu} on ${CLUSTER_TIERS[1].name}, ${SEARCH_TIERS[1].vcpu} on ${SEARCH_TIERS[1].name})`} and
            add Search Nodes for query throughput. No Phase 1 choice blocks this.
          </p>
        </article>
      </div>

      <details className="rounded-lg border border-slate-200 bg-white p-3 text-sm text-slate-600">
        <summary className="cursor-pointer font-medium text-mdb-slate">Assumptions and method</summary>
        <ul className="mt-2 list-disc space-y-1 pl-5">
          <li>
            Measured per quad: {QUAD.dataBytes} B document, {QUAD.storageBytes} B on disk, {QUAD.indexBytes} B across the 4
            indexes (after repeated reloads, so on the high side). New sources are assumed to have the same quad shape.
          </li>
          <li>
            Measured per RDF 1.2 item: {(SNAPSHOT.dataBytes / 1024).toFixed(1)} KB, mostly the {SNAPSHOT.dims}-dim
            embedding stored as doubles. Storing it as a BSON float32 vector would cut it by about half; int8 quantization
            shrinks the vector index about 4×.
          </li>
          <li>
            Base cluster: smallest tier whose WiredTiger cache (50% of RAM − 1 GB) holds the working set at 70%, with 2×
            disk headroom for staged reloads, oplog and growth. M30 is the floor: M10/M20 are burstable, and the criteria
            need point-in-time recovery, private endpoints and encryption at rest.
          </li>
          <li>
            Search Nodes: smallest High-CPU tier (us-east-1) whose RAM, less ~1 GB for mongot, holds the text + vector
            indexes, with 2× disk for index rebuilds plus the 20% local-SSD overhead. S20 is the Atlas default and production
            minimum. Search index sizes are estimates; confirm with the Atlas Search index-size metric.
          </li>
          <li>Read/write mix of 95/5 and a handful of concurrent readers make CPU a non-issue for Phase 1.</li>
        </ul>
      </details>
    </section>
  )
}
