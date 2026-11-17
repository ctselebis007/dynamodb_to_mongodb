import { useState } from 'react'
import { KINDS, type Field, type MapKind, type Transformation } from './data'

interface Highlight {
  map: string | null
  kind: MapKind | null
}

function FieldRow({ field, kind, state, onFocus }: {
  field: Field
  kind: MapKind
  state: 'on' | 'off' | 'idle'
  onFocus: (map: string | null) => void
}) {
  const k = KINDS[kind]
  return (
    <li
      tabIndex={0}
      data-map={field.map}
      data-state={state}
      onMouseEnter={() => onFocus(field.map)}
      onMouseLeave={() => onFocus(null)}
      onFocus={() => onFocus(field.map)}
      onBlur={() => onFocus(null)}
      className={`flex gap-2 border-l-4 py-0.5 pl-2 font-mono text-xs leading-relaxed transition ${k.bar} ${
        state === 'on' ? 'bg-white/90 ring-2 ring-mdb-green' : state === 'off' ? 'opacity-30' : ''
      } ${kind === 'dropped' ? 'line-through decoration-rose-400/70' : ''}`}
    >
      <span className="shrink-0 font-semibold">{field.key}:</span>
      <span className="break-all">{field.value}</span>
    </li>
  )
}

export function FieldMapper({ t }: { t: Transformation }) {
  const [hl, setHl] = useState<Highlight>({ map: null, kind: null })
  const kindOf = (map: string) => t.mappings.find((m) => m.id === map)?.kind ?? 'kept'
  const stateOf = (map: string): 'on' | 'off' | 'idle' => {
    if (hl.map) return hl.map === map ? 'on' : 'off'
    if (hl.kind) return kindOf(map) === hl.kind ? 'on' : 'off'
    return 'idle'
  }
  const focusMap = (map: string | null) => setHl((h) => ({ ...h, map }))
  const usedKinds = [...new Set(t.mappings.map((m) => m.kind))]
  const active = t.mappings.find((m) => m.id === hl.map)

  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-2" role="group" aria-label="Highlight by kind of change">
        {usedKinds.map((kind) => (
          <button
            key={kind}
            aria-pressed={hl.kind === kind}
            onClick={() => setHl({ map: null, kind: hl.kind === kind ? null : kind })}
            className={`flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs ${
              hl.kind === kind ? 'border-mdb-slate bg-mdb-slate text-white' : 'border-slate-300 bg-white text-slate-700'
            }`}
          >
            <span className={`h-2 w-2 rounded-full ${KINDS[kind].dot}`} />
            {KINDS[kind].label}
          </button>
        ))}
      </div>

      <div className="grid items-start gap-4 lg:grid-cols-[1fr_auto_1fr]">
        <section className="rounded-xl border border-orange-200 bg-orange-50/60 p-4" aria-label="DynamoDB item">
          <header className="mb-2 flex items-baseline justify-between">
            <h4 className="font-semibold text-orange-900">DynamoDB item</h4>
            <span className="font-mono text-xs text-orange-800">table {t.table}</span>
          </header>
          <ul className="space-y-0.5">
            {t.dynamo.map((f) => (
              <FieldRow key={f.key} field={f} kind={kindOf(f.map)} state={stateOf(f.map)} onFocus={focusMap} />
            ))}
          </ul>
        </section>

        <div className="flex flex-row items-center justify-center gap-2 py-2 text-slate-400 lg:flex-col lg:pt-24" aria-hidden>
          <span className="rotate-90 text-3xl lg:rotate-0">➜</span>
          <span className="rounded bg-slate-100 px-2 py-0.5 font-mono text-[10px] text-slate-500">convert.py</span>
        </div>

        <section className="rounded-xl border border-green-200 bg-green-50/60 p-4" aria-label="MongoDB document">
          <header className="mb-2 flex items-baseline justify-between">
            <h4 className="font-semibold text-mdb-forest">MongoDB document</h4>
            <span className="font-mono text-xs text-mdb-forest">collection {t.collection}</span>
          </header>
          <ul className="space-y-0.5">
            {t.mongo.map((f) => (
              <FieldRow key={f.key} field={f} kind={kindOf(f.map)} state={stateOf(f.map)} onFocus={focusMap} />
            ))}
          </ul>
          <h5 className="mt-3 mb-1 text-xs font-semibold tracking-wide text-slate-500 uppercase">Indexes</h5>
          <ul className="flex flex-wrap gap-1.5">
            {t.indexes.map((ix) => {
              const state = stateOf(ix.map)
              return (
                <li
                  key={ix.name}
                  tabIndex={0}
                  title={ix.keys}
                  onMouseEnter={() => focusMap(ix.map)}
                  onMouseLeave={() => focusMap(null)}
                  onFocus={() => focusMap(ix.map)}
                  onBlur={() => focusMap(null)}
                  className={`rounded border border-green-300 bg-white px-2 py-0.5 font-mono text-[11px] transition ${
                    state === 'on' ? 'ring-2 ring-mdb-green' : state === 'off' ? 'opacity-30' : ''
                  }`}
                >
                  {ix.name}
                  <span className="ml-1 text-slate-500">{ix.keys}</span>
                </li>
              )
            })}
          </ul>
        </section>
      </div>

      <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {t.mappings.map((m) => {
          const state = stateOf(m.id)
          return (
            <article
              key={m.id}
              tabIndex={0}
              onMouseEnter={() => focusMap(m.id)}
              onMouseLeave={() => focusMap(null)}
              onFocus={() => focusMap(m.id)}
              onBlur={() => focusMap(null)}
              aria-current={active?.id === m.id ? 'true' : undefined}
              className={`rounded-lg border bg-white p-3 transition ${
                state === 'on' ? 'border-mdb-green shadow-md' : state === 'off' ? 'opacity-40' : 'border-slate-200'
              }`}
            >
              <h5 className={`flex items-center gap-1.5 text-sm font-semibold ${KINDS[m.kind].text}`}>
                <span className={`h-2 w-2 shrink-0 rounded-full ${KINDS[m.kind].dot}`} />
                {m.title}
              </h5>
              <p className="mt-1 text-xs leading-relaxed text-slate-600">{m.detail}</p>
            </article>
          )
        })}
      </div>
      <p className="mt-2 text-xs text-slate-500">
        {t.footnote} Hover a field, an index or a card to trace it across.
      </p>
    </div>
  )
}
