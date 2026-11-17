import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api, type Schemas } from '../../core/api'
import { QueryCard } from './QueryCard'
import { SemanticPanel } from './SemanticPanel'
import { WritesPanel } from './WritesPanel'

type Catalog = Schemas['Catalog']
type Tab = 'talent' | 'aicp' | 'writes' | 'semantic'

const TABS: { id: Tab; label: string; blurb: string }[] = [
  { id: 'talent', label: 'Talent quads (T1–T7)', blurb: 'talent-rdf-quads: one document per quad, 4 named graphs.' },
  { id: 'aicp', label: 'AICP RDF 1.2 (A1–A5)', blurb: 'aicp-quads: one document per item, facts nested as in DynamoDB.' },
  { id: 'writes', label: 'Writes', blurb: 'Atomic change events and named-graph reloads.' },
  { id: 'semantic', label: 'Semantic', blurb: 'Vector Search over the LIVE snapshot.' },
]

function DynamoGraphPage() {
  const [tab, setTab] = useState<Tab>('talent')
  const { data, error, isLoading } = useQuery({
    queryKey: ['dynamo-graph', 'catalog'],
    queryFn: () => api.get<Catalog>('/api/dynamo-graph/catalog'),
  })
  const active = TABS.find((t) => t.id === tab)!

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold">DynamoDB quads → MongoDB</h1>
        <p className="text-sm text-slate-600">
          Each sample question from the criteria document answered in one call, compared with its ideal answer.
          {data && data.scale > 1 && (
            <strong className="ml-1 text-amber-800">
              Data scaled ×{data.scale}; ideal-answer badges are shown at scale 1 only.
            </strong>
          )}
        </p>
      </header>
      <nav className="flex gap-1 border-b border-slate-200" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${tab === t.id ? 'border-mdb-forest text-mdb-forest' : 'border-transparent text-slate-600 hover:text-slate-900'}`}
          >
            {t.label}
          </button>
        ))}
      </nav>
      <p className="text-sm text-slate-500">{active.blurb}</p>

      {isLoading && <p className="text-slate-500">Loading…</p>}
      {error && <p className="text-red-600">{error.message}</p>}
      {data && !data.seeded && (
        <div role="alert" className="rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <strong>This module&apos;s data isn&apos;t loaded yet.</strong> Open Setup and run Seed Database, then Create
          Indexes.
        </div>
      )}
      {data && (tab === 'talent' || tab === 'aicp') && (
        <div className="space-y-3">
          {data.queries
            .filter((q) => q.group === tab)
            .map((q) => (
              <QueryCard key={q.id} spec={q} />
            ))}
        </div>
      )}
      {data && tab === 'writes' && <WritesPanel scale={data.scale} />}
      {tab === 'semantic' && <SemanticPanel />}
    </div>
  )
}

export const route = { path: 'dynamo-graph', element: <DynamoGraphPage /> }
export const navItem = { label: 'Sample Queries', order: 10, description: 'Quad store sample queries' }
