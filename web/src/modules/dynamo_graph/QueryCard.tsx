import { useState } from 'react'
import { api, type Schemas } from '../../core/api'
import { QueryDrawer } from '../../core/QueryDrawer'
import { toastError } from '../../core/toast'

export type QuerySpec = Schemas['QuerySpecOut']
export type QueryResult = Schemas['QueryResult']
type Inputs = Record<string, string | number>

const BENCH_RUNS = 20

export function percentile(values: number[], p: number): number {
  const sorted = [...values].sort((a, b) => a - b)
  return sorted[Math.min(sorted.length - 1, Math.ceil((p / 100) * sorted.length) - 1)]
}

export function MatchBadge({ result }: { result: QueryResult }) {
  if (result.match === true)
    return <span className="rounded bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800">✅ Matches ideal answer</span>
  if (result.match === false)
    return <span className="rounded bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800">❌ Differs from ideal answer</span>
  return (
    <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
      {result.scale > 1 ? `n/a (scale ×${result.scale})` : 'n/a (custom inputs)'}
    </span>
  )
}

function fmt(value: unknown): string {
  const s = JSON.stringify(value)
  return s && s.length > 120 ? `${s.slice(0, 117)}…` : (s ?? '—')
}

function toInputs(defaults: Record<string, unknown>): Inputs {
  return Object.fromEntries(Object.entries(defaults).map(([k, v]) => [k, v as string | number]))
}

export function QueryCard({ spec, run = (inputs, explain) => runQuery(spec.id, inputs, explain) }: {
  spec: QuerySpec
  run?: (inputs: Inputs, explain: boolean) => Promise<QueryResult>
}) {
  const [inputs, setInputs] = useState<Inputs>(() => toInputs(spec.defaults))
  const [result, setResult] = useState<QueryResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [drawer, setDrawer] = useState(false)
  const [bench, setBench] = useState<{ p50: number; p95: number } | null>(null)

  const execute = async () => {
    setBusy(true)
    try {
      setResult(await run(inputs, false))
    } catch (e) {
      toastError(e)
    } finally {
      setBusy(false)
    }
  }

  const benchmark = async () => {
    setBusy(true)
    try {
      const times: number[] = []
      let last: QueryResult | null = null
      for (let i = 0; i < BENCH_RUNS; i++) {
        last = await run(inputs, false)
        times.push(last.timings.server_ms)
      }
      setResult(last)
      setBench({ p50: percentile(times, 50), p95: percentile(times, 95) })
    } catch (e) {
      toastError(e)
    } finally {
      setBusy(false)
    }
  }

  return (
    <article className="rounded-lg border border-slate-200 bg-white p-4" aria-label={`${spec.id} ${spec.title}`}>
      <header className="flex flex-wrap items-center gap-2">
        <span className="rounded bg-mdb-slate px-2 py-0.5 font-mono text-xs text-white">{spec.id}</span>
        <h3 className="font-semibold">{spec.title}</h3>
        <span className="text-xs text-slate-500">{spec.pattern}</span>
        <span className="ml-auto flex gap-2 text-xs">
          <span className="rounded bg-amber-50 px-2 py-0.5 text-amber-900">DynamoDB today: {spec.dynamo_today}</span>
          <span className="rounded bg-green-50 px-2 py-0.5 text-mdb-forest">MongoDB: 1 call</span>
        </span>
      </header>

      {Object.keys(inputs).length > 0 && (
        <div className="mt-3 grid gap-2 sm:grid-cols-3">
          {Object.entries(inputs).map(([key, value]) => (
            <label key={key} className="text-xs text-slate-600">
              {key}
              <input
                className="mt-0.5 block w-full rounded border border-slate-300 px-2 py-1 font-mono text-sm text-slate-900"
                type={typeof spec.defaults[key] === 'number' ? 'number' : 'text'}
                value={value}
                onChange={(e) =>
                  setInputs({
                    ...inputs,
                    [key]: typeof spec.defaults[key] === 'number' ? Number(e.target.value) : e.target.value,
                  })
                }
              />
            </label>
          ))}
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          onClick={execute}
          disabled={busy}
          className="rounded bg-mdb-forest px-3 py-1 text-sm font-medium text-white disabled:opacity-50"
        >
          {busy ? 'Running…' : 'Run'}
        </button>
        <button onClick={benchmark} disabled={busy} className="rounded border border-slate-300 px-3 py-1 text-sm disabled:opacity-50">
          Run ×{BENCH_RUNS}
        </button>
        <button
          onClick={() => setInputs(toInputs(spec.defaults))}
          className="rounded px-2 py-1 text-sm text-slate-600 hover:underline"
        >
          Reset inputs
        </button>
        {result && (
          <>
            <MatchBadge result={result} />
            <span className="text-sm text-slate-600">
              Server <strong>{result.timings.server_ms.toFixed(1)} ms</strong>
            </span>
            {bench && (
              <span className="text-sm text-slate-600" data-testid="bench">
                p50 <strong>{bench.p50.toFixed(1)}</strong> · p95 <strong>{bench.p95.toFixed(1)} ms</strong>
              </span>
            )}
            <button onClick={() => setDrawer(true)} className="ml-auto rounded border border-slate-300 px-2 py-0.5 text-sm">
              Query
            </button>
          </>
        )}
      </div>

      {result?.note && <p className="mt-2 text-sm text-slate-500">{result.note}</p>}

      {result && result.checks.length > 0 && (
        <table className="mt-3 w-full text-left text-xs">
          <thead className="text-slate-500">
            <tr>
              <th className="py-1">Check</th>
              <th>Ideal answer</th>
              <th>MongoDB</th>
              <th />
            </tr>
          </thead>
          <tbody className="font-mono">
            {result.checks.map((c) => (
              <tr key={c.path} className="border-t border-slate-100 align-top">
                <td className="py-1 pr-2">
                  {c.path}
                  {c.mode === 'includes' && <span className="text-slate-400"> ⊇</span>}
                </td>
                <td className="pr-2">{fmt(c.expected)}</td>
                <td className="pr-2">{fmt(c.actual)}</td>
                <td>{c.ok ? '✅' : '❌'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {result && result.results.length > 0 && (
        <details className="mt-3">
          <summary className="cursor-pointer text-sm text-slate-600">Result document</summary>
          <pre className="mt-1 max-h-80 overflow-auto rounded bg-slate-50 p-2 text-xs">
            {JSON.stringify(result.results[0], null, 2)}
          </pre>
        </details>
      )}

      {result && (
        <QueryDrawer
          open={drawer}
          onClose={() => setDrawer(false)}
          title={`${spec.id} · ${spec.title}`}
          pipeline={result.pipeline}
          timings={result.timings}
          fetchExplain={async () => (await run(inputs, true)).explain}
        />
      )}
    </article>
  )
}

export function runQuery(id: string, inputs: Inputs, explain: boolean): Promise<QueryResult> {
  return api.post<QueryResult>(`/api/dynamo-graph/query/${id}`, { inputs, explain })
}
