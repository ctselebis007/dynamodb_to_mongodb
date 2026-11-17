import { useState } from 'react'
import { api } from '../../core/api'
import { QueryDrawer } from '../../core/QueryDrawer'
import { toastError } from '../../core/toast'
import type { QueryResult } from './QueryCard'

interface Hit {
  id?: string
  label?: string | null
  types?: string[]
  score?: number
}

export function SemanticPanel() {
  const [text, setText] = useState('single sign-on enforcement for the Claude admin console')
  const [result, setResult] = useState<QueryResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [drawer, setDrawer] = useState(false)

  const search = (explain: boolean) => api.post<QueryResult>('/api/dynamo-graph/semantic', { text, explain })

  const run = async () => {
    setBusy(true)
    try {
      setResult(await search(false))
    } catch (e) {
      toastError(e)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <h3 className="font-semibold">Semantic search over LIVE entities (bonus)</h3>
      <p className="mt-1 text-sm text-slate-600">
        <code>$vectorSearch</code> over embedded labels and comments of the aicp-quads LIVE snapshot. None of the 12
        sample queries need this; it shows what an AI agent could ask in natural language.
      </p>
      <div className="mt-3 flex gap-2">
        <input
          aria-label="Semantic query"
          className="flex-1 rounded border border-slate-300 px-2 py-1 text-sm"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && run()}
        />
        <button
          onClick={run}
          disabled={busy || !text.trim()}
          className="rounded bg-mdb-forest px-3 py-1 text-sm font-medium text-white disabled:opacity-50"
        >
          {busy ? 'Searching…' : 'Search'}
        </button>
        {result && (
          <button onClick={() => setDrawer(true)} className="rounded border border-slate-300 px-2 py-0.5 text-sm">
            Query
          </button>
        )}
      </div>
      {result && (
        <ol className="mt-3 space-y-1 text-sm">
          {(result.results as Hit[]).map((h) => (
            <li key={h.id} className="flex gap-2">
              <span className="w-14 shrink-0 font-mono text-xs text-slate-500">{h.score?.toFixed(3)}</span>
              <span className="font-mono">{h.id}</span>
              <span className="text-slate-600">{h.label}</span>
            </li>
          ))}
          {result.note && <li className="text-slate-500">{result.note}</li>}
        </ol>
      )}
      {result && (
        <QueryDrawer
          open={drawer}
          onClose={() => setDrawer(false)}
          title="Semantic search"
          pipeline={result.pipeline}
          timings={result.timings}
          fetchExplain={async () => (await search(true)).explain}
        />
      )}
    </section>
  )
}
