import { useState } from 'react'

export interface Timings {
  server_ms: number
  embed_ms?: number | null
  rerank_ms?: number | null
}

interface Props {
  open: boolean
  onClose: () => void
  title: string
  pipeline: unknown[]
  timings: Timings
  /** Re-runs the same query with `explain: true` and resolves to the explain output. */
  fetchExplain?: () => Promise<unknown>
}

/** Long number arrays (query vectors) are abbreviated for display; Copy always uses the exact JSON. */
export function abbreviate(value: unknown): unknown {
  if (Array.isArray(value)) {
    if (value.length > 8 && value.every((v) => typeof v === 'number')) {
      return [...value.slice(0, 3), `… ${value.length} numbers`]
    }
    return value.map(abbreviate)
  }
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, abbreviate(v)]))
  }
  return value
}

export function QueryDrawer({ open, onClose, title, pipeline, timings, fetchExplain }: Props) {
  const [copied, setCopied] = useState(false)
  const [explainOn, setExplainOn] = useState(false)
  const [explain, setExplain] = useState<unknown>(null)
  const [explainError, setExplainError] = useState<string | null>(null)

  if (!open) return null

  const copy = async () => {
    await navigator.clipboard.writeText(JSON.stringify(pipeline, null, 2))
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const toggleExplain = async (on: boolean) => {
    setExplainOn(on)
    if (!on || !fetchExplain) return
    setExplain(null)
    setExplainError(null)
    try {
      setExplain(await fetchExplain())
    } catch (e) {
      setExplainError(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <aside
      role="dialog"
      aria-label={`${title} query`}
      className="fixed inset-y-0 right-0 z-40 flex w-[36rem] max-w-full flex-col border-l border-slate-200 bg-white shadow-2xl"
    >
      <header className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
        <h2 className="font-semibold">{title}</h2>
        <button onClick={onClose} className="text-slate-500 hover:text-slate-900" aria-label="Close">
          ×
        </button>
      </header>
      <div className="flex items-center gap-4 border-b border-slate-100 px-4 py-2 text-sm text-slate-600">
        <span>
          Server <strong>{timings.server_ms.toFixed(1)} ms</strong>
        </span>
        {timings.embed_ms != null && (
          <span>
            Embed <strong>{timings.embed_ms.toFixed(1)} ms</strong>
          </span>
        )}
        {timings.rerank_ms != null && (
          <span>
            Rerank <strong>{timings.rerank_ms.toFixed(1)} ms</strong>
          </span>
        )}
        <div className="ml-auto flex items-center gap-3">
          {fetchExplain && (
            <label className="flex items-center gap-1">
              <input type="checkbox" checked={explainOn} onChange={(e) => toggleExplain(e.target.checked)} />
              Explain
            </label>
          )}
          <button onClick={copy} className="rounded border border-slate-300 px-2 py-0.5 hover:bg-slate-50">
            {copied ? 'Copied' : 'Copy'}
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-auto p-4">
        <pre className="text-xs leading-relaxed whitespace-pre-wrap" data-testid="pipeline">
          {JSON.stringify(abbreviate(pipeline), null, 2)}
        </pre>
        {explainOn && (
          <section className="mt-4">
            <h3 className="mb-1 text-sm font-semibold">explain("executionStats")</h3>
            {explainError && <p className="text-sm text-red-600">{explainError}</p>}
            {!explain && !explainError && <p className="text-sm text-slate-500">Running…</p>}
            {explain != null && (
              <pre className="max-h-96 overflow-auto rounded bg-slate-50 p-2 text-xs">
                {JSON.stringify(abbreviate(explain), null, 2)}
              </pre>
            )}
          </section>
        )}
      </div>
    </aside>
  )
}
