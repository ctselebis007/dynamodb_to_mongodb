import { useState } from 'react'
import { api, type Schemas } from '../../core/api'
import { pushToast, toastError } from '../../core/toast'

type ReplaceRequest = Schemas['ReplaceRequest']
type ReplaceResult = Schemas['ReplaceResult']
type ReloadResult = Schemas['ReloadResult']
type ReloadStep = Schemas['ReloadStep']
type Graph = Schemas['ReloadRequest']['graph']

const GRAPHS: Graph[] = ['talent:hierarchy', 'talent:costcenters', 'talent:github', 'talent:metadata']

const DEFAULT_REPLACE: ReplaceRequest = {
  graph: 'talent:metadata',
  subject: 'line:REALGAR_SHOAL_ZIRCON_SAVANNA_BASIN_BASALT',
  predicate: 'rdfs:label',
  old_object: 'TALUS-Basin Magnetite & Hoodoo',
  new_object: 'TALUS-Basin Magnetite & Hoodoo (renamed)',
  simulate_failure: false,
}

const FIELDS = ['graph', 'subject', 'predicate', 'old_object', 'new_object'] as const

const KIND_STYLE: Record<ReloadStep['kind'], { bar: string; label: string }> = {
  app: { bar: 'bg-slate-400', label: 'App' },
  aggregate: { bar: 'bg-sky-500', label: 'Aggregation' },
  write: { bar: 'bg-mdb-forest', label: 'Write' },
  txn: { bar: 'bg-amber-500', label: 'Transaction' },
}

const fmtMs = (ms: number) => (ms >= 1000 ? `${(ms / 1000).toFixed(2)} s` : `${ms.toFixed(1)} ms`)

export function ReloadTimeline({ result }: { result: ReloadResult }) {
  const [open, setOpen] = useState<number | null>(null)
  const max = Math.max(...result.steps.map((s) => s.ms), 1)
  return (
    <div className="mt-3 rounded bg-slate-50 p-2 text-sm text-slate-700" data-testid="reload-result">
      <p>
        {result.graph}: deleted {result.deleted.toLocaleString()}, inserted {result.inserted.toLocaleString()} in{' '}
        <strong>{(result.ms / 1000).toFixed(2)} s</strong> (transaction) · {fmtMs(result.total_ms)} end to end
      </p>
      <div className="mt-2 flex flex-wrap gap-3 text-xs text-slate-500">
        {Object.values(KIND_STYLE).map((k) => (
          <span key={k.label} className="flex items-center gap-1">
            <span className={`inline-block h-2 w-3 rounded-sm ${k.bar}`} />
            {k.label}
          </span>
        ))}
        <span className="flex items-center gap-1">
          <span className="inline-block h-3 w-1 bg-amber-400" />
          Inside transaction
        </span>
      </div>
      <table className="mt-2 w-full table-fixed text-xs">
        <thead className="text-left text-slate-500">
          <tr>
            <th className="w-6">#</th>
            <th>Step</th>
            <th className="w-28">Operation</th>
            <th className="w-14 text-right">Docs</th>
            <th className="w-20 text-right">Time</th>
            <th className="w-1/4 pl-2" aria-label="Relative time" />
          </tr>
        </thead>
        <tbody>
          {result.steps.map((step, i) => (
            <ReloadStepRow
              key={i}
              index={i}
              step={step}
              max={max}
              open={open === i}
              onToggle={() => setOpen(open === i ? null : i)}
            />
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ReloadStepRow({
  index,
  step,
  max,
  open,
  onToggle,
}: {
  index: number
  step: ReloadStep
  max: number
  open: boolean
  onToggle: () => void
}) {
  const style = KIND_STYLE[step.kind]
  return (
    <>
      <tr
        className={`cursor-pointer border-t border-slate-200 hover:bg-white ${step.in_transaction ? 'border-l-4 border-l-amber-400' : ''}`}
        onClick={onToggle}
        aria-expanded={open}
      >
        <td className="py-1 pl-1 text-slate-400">{index + 1}</td>
        <td className="truncate py-1" title={step.result}>
          <span className="mr-1 text-slate-400">{open ? '▾' : '▸'}</span>
          {step.name}
        </td>
        <td className="truncate py-1 font-mono">{step.op}</td>
        <td className="py-1 text-right tabular-nums">{step.docs?.toLocaleString() ?? '—'}</td>
        <td className="py-1 text-right font-medium tabular-nums">{fmtMs(step.ms)}</td>
        <td className="py-1 pl-2">
          <div className="h-2 rounded-sm bg-slate-200">
            <div
              className={`h-2 rounded-sm ${style.bar}`}
              style={{ width: `${Math.max((step.ms / max) * 100, 1)}%` }}
            />
          </div>
        </td>
      </tr>
      {open && (
        <tr className={step.in_transaction ? 'border-l-4 border-l-amber-400' : ''}>
          <td />
          <td colSpan={5} className="pb-2">
            <p className="text-slate-600">{step.result}</p>
            <pre className="mt-1 max-h-48 overflow-auto rounded bg-white p-2 text-xs" data-testid="reload-step-command">
              {JSON.stringify(step.command, null, 2)}
            </pre>
          </td>
        </tr>
      )}
    </>
  )
}

export function WritesPanel({ scale }: { scale: number }) {
  const [form, setForm] = useState<ReplaceRequest>(DEFAULT_REPLACE)
  const [replace, setReplace] = useState<ReplaceResult | null>(null)
  const [graph, setGraph] = useState<Graph>('talent:metadata')
  const [reload, setReload] = useState<ReloadResult | null>(null)
  const [busy, setBusy] = useState(false)

  const guarded = async (fn: () => Promise<void>) => {
    setBusy(true)
    try {
      await fn()
    } catch (e) {
      toastError(e)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h3 className="font-semibold">Atomic quad replace</h3>
        <p className="mt-1 text-sm text-slate-600">
          Delete one quad and insert its replacement in a single transaction. Tick &quot;simulate failure&quot; to abort
          after both writes and show that nothing changed. Run T4 afterwards to see the new line label.
        </p>
        <div className="mt-3 grid gap-2">
          {FIELDS.map((key) => (
            <label key={key} className="text-xs text-slate-600">
              {key}
              <input
                className="mt-0.5 block w-full rounded border border-slate-300 px-2 py-1 font-mono text-sm text-slate-900"
                value={form[key]}
                onChange={(e) => setForm({ ...form, [key]: e.target.value })}
              />
            </label>
          ))}
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={!!form.simulate_failure}
              onChange={(e) => setForm({ ...form, simulate_failure: e.target.checked })}
            />
            Simulate failure (abort the transaction)
          </label>
        </div>
        <div className="mt-3 flex gap-2">
          <button
            disabled={busy}
            onClick={() =>
              guarded(async () => setReplace(await api.post<ReplaceResult>('/api/dynamo-graph/writes/replace-quad', form)))
            }
            className="rounded bg-mdb-forest px-3 py-1 text-sm font-medium text-white disabled:opacity-50"
          >
            Replace quad
          </button>
          <button
            onClick={() => setForm({ ...form, old_object: form.new_object, new_object: form.old_object })}
            className="rounded border border-slate-300 px-3 py-1 text-sm"
          >
            Swap old ↔ new
          </button>
        </div>
        {replace && (
          <div className="mt-3 rounded bg-slate-50 p-2 text-sm" data-testid="replace-result">
            <p className={replace.committed ? 'text-green-800' : 'text-amber-800'}>{replace.message}</p>
            <p className="text-slate-600">
              {replace.ms.toFixed(1)} ms · objects now: <code>{replace.objects_after.join(', ') || '—'}</code>
            </p>
          </div>
        )}
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h3 className="font-semibold">Named-graph reload</h3>
        <p className="mt-1 text-sm text-slate-600">
          Replace every quad of one named graph from the workbook in one transaction. Readers see the old graph until
          commit. Target: 15,000 documents in under 5 minutes.
        </p>
        <div className="mt-3 flex items-end gap-2">
          <label className="text-xs text-slate-600">
            graph
            <select
              className="mt-0.5 block rounded border border-slate-300 px-2 py-1 text-sm text-slate-900"
              value={graph}
              onChange={(e) => setGraph(e.target.value as Graph)}
            >
              {GRAPHS.map((g) => (
                <option key={g}>{g}</option>
              ))}
            </select>
          </label>
          <button
            disabled={busy || scale !== 1}
            title={scale !== 1 ? 'Only enabled at scale 1 (transaction size limit)' : undefined}
            onClick={() =>
              guarded(async () => {
                const r = await api.post<ReloadResult>('/api/dynamo-graph/writes/reload-graph', { graph })
                setReload(r)
                pushToast({ kind: 'success', title: `Reloaded ${r.graph}` })
              })
            }
            className="rounded bg-mdb-forest px-3 py-1 text-sm font-medium text-white disabled:opacity-50"
          >
            Reload graph
          </button>
        </div>
        {scale !== 1 && (
          <p className="mt-2 text-sm text-amber-800">
            Disabled at scale ×{scale}: a single transaction would exceed the 60s limit. Production would use a staged
            load and swap.
          </p>
        )}
        {reload && <ReloadTimeline result={reload} />}
      </section>
    </div>
  )
}
