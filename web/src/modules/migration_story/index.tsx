import { useState } from 'react'
import { NavLink } from 'react-router'
import {
  ACCESS_PATTERNS,
  FIDELITY,
  FLEXIBILITY,
  ROUND_TRIPS,
  SIMPLIFICATION,
  TRANSFORMATIONS,
  type Benefit,
} from './data'
import { ClusterSizing } from './ClusterSizing'
import { FieldMapper } from './FieldMapper'

const MAX_CALLS = Math.max(...ROUND_TRIPS.map((r) => r.calls ?? 0))

function Section({ eyebrow, title, children }: { eyebrow: string; title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-4">
      <div>
        <p className="text-xs font-semibold tracking-widest text-mdb-forest uppercase">{eyebrow}</p>
        <h2 className="text-xl font-semibold text-mdb-slate">{title}</h2>
      </div>
      {children}
    </section>
  )
}

function Hero() {
  return (
    <header className="overflow-hidden rounded-2xl bg-mdb-slate p-8 text-white">
      <p className="text-xs font-semibold tracking-widest text-mdb-green uppercase">DynamoDB → MongoDB Atlas</p>
      <h1 className="mt-2 max-w-3xl text-3xl leading-tight font-semibold">
        Same quads, same nested facts. Keys you no longer have to design around.
      </h1>
      <p className="mt-3 max-w-3xl text-slate-300">
        Two DynamoDB tables become two MongoDB collections, item for item. The composite keys and GSI copies become
        indexes, and every sample question runs as a single server-side call.
      </p>
      <div className="mt-6 grid gap-3 sm:grid-cols-[1fr_auto_1fr] sm:items-center">
        <div className="space-y-2">
          {[
            ['talent-rdf-quads', 'PK · SK · GSI-predicate'],
            ['aicp-quads', 'pk · sk'],
          ].map(([t, keys]) => (
            <div key={t} className="rounded-lg border border-orange-300/40 bg-orange-400/10 px-4 py-2 font-mono text-sm">
              <span className="text-orange-300">table</span> {t}
              <span className="ml-2 text-xs text-slate-400">{keys}</span>
            </div>
          ))}
        </div>
        <div className="text-center text-3xl text-mdb-green" aria-hidden>
          ➜
        </div>
        <div className="space-y-2">
          {[
            ['talent_quads', '3 indexes · Search'],
            ['aicp_items', '3 indexes · Vector'],
          ].map(([c, extras]) => (
            <div key={c} className="rounded-lg border border-mdb-green/50 bg-mdb-green/10 px-4 py-2 font-mono text-sm">
              <span className="text-mdb-green">collection</span> {c}
              <span className="ml-2 text-xs text-slate-400">{extras}</span>
            </div>
          ))}
        </div>
      </div>
      <dl className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-4">
        {[
          ['12 / 12', 'questions answered in one call each'],
          ['55 → 1', 'calls for the 3-level subtree (T3)'],
          ['4 → 0', 'Scans across the 12 questions'],
          ['0', 'search engines to keep in sync'],
        ].map(([v, l]) => (
          <div key={l}>
            <dt className="text-2xl font-semibold text-mdb-green">{v}</dt>
            <dd className="text-xs text-slate-300">{l}</dd>
          </div>
        ))}
      </dl>
    </header>
  )
}

function Transformation() {
  const [id, setId] = useState(TRANSFORMATIONS[0].id)
  const t = TRANSFORMATIONS.find((x) => x.id === id)!
  return (
    <Section eyebrow="1 · The transformation" title="What happens to each item">
      <div className="flex flex-wrap items-center gap-2" role="tablist">
        {TRANSFORMATIONS.map((x) => (
          <button
            key={x.id}
            role="tab"
            aria-selected={x.id === id}
            onClick={() => setId(x.id)}
            className={`rounded-lg border px-3 py-1.5 text-sm ${
              x.id === id ? 'border-mdb-forest bg-mdb-forest text-white' : 'border-slate-300 bg-white text-slate-700'
            }`}
          >
            <span className="font-mono">{x.table}</span> → <span className="font-mono">{x.collection}</span>
          </button>
        ))}
        <span className="text-sm text-slate-500">{t.grain}</span>
      </div>
      <FieldMapper key={t.id} t={t} />
    </Section>
  )
}

function RoundTrips() {
  return (
    <Section eyebrow="2 · Round trips" title="DynamoDB calls per question vs. MongoDB">
      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <div className="mb-3 flex flex-wrap gap-4 text-xs text-slate-600">
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-5 rounded-sm bg-orange-400" /> DynamoDB Queries / GetItems
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-5 rounded-sm bg-[repeating-linear-gradient(45deg,#fb923c_0_4px,#fed7aa_4px_8px)]" />{' '}
            Scan of the whole table or snapshot
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-5 rounded-sm bg-mdb-forest" /> MongoDB: 1 call
          </span>
        </div>
        <ul className="space-y-2" aria-label="Calls per question">
          {ROUND_TRIPS.map((r) => (
            <li key={r.id} className="grid grid-cols-[2.5rem_14rem_1fr] items-center gap-3 text-sm max-md:grid-cols-[2.5rem_1fr]">
              <span className="rounded bg-mdb-slate px-1.5 py-0.5 text-center font-mono text-xs text-white">{r.id}</span>
              <span className="truncate text-slate-700 max-md:hidden" title={r.question}>
                {r.question}
              </span>
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <div className="min-w-0 flex-1">
                    <div
                      className={`h-3 rounded-sm ${
                        r.calls === null
                          ? 'w-full bg-[repeating-linear-gradient(45deg,#fb923c_0_4px,#fed7aa_4px_8px)]'
                          : 'bg-orange-400'
                      }`}
                      style={r.calls === null ? undefined : { width: `${Math.max(1.5, (r.calls / MAX_CALLS) * 100)}%` }}
                    />
                  </div>
                  <span className="w-56 shrink-0 text-xs text-orange-900 max-md:w-32">{r.dynamo}</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="h-3 rounded-sm bg-mdb-forest" style={{ width: `${(1 / MAX_CALLS) * 100}%`, minWidth: '0.4rem' }} />
                  </div>
                  <span className="w-56 shrink-0 text-xs text-mdb-forest max-md:w-32">1 aggregation</span>
                </div>
              </div>
            </li>
          ))}
        </ul>
        <p className="mt-3 text-xs text-slate-500">
          DynamoDB figures come from Sample_Queries_Criteria.md. Each MongoDB call is the pipeline shown on the Sample
          Queries page, checked against the same ideal answers.
        </p>
      </div>
    </Section>
  )
}

function AccessPatterns() {
  return (
    <Section eyebrow="3 · Access patterns" title="From key design to indexes">
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs text-slate-500 uppercase">
            <tr>
              <th className="px-3 py-2">Need</th>
              <th className="px-3 py-2 text-orange-800">DynamoDB today</th>
              <th className="px-3 py-2 text-mdb-forest">MongoDB</th>
              <th className="px-3 py-2">Query</th>
            </tr>
          </thead>
          <tbody>
            {ACCESS_PATTERNS.map((a) => (
              <tr key={a.need} className="border-t border-slate-100">
                <td className="px-3 py-2 font-medium">{a.need}</td>
                <td className="px-3 py-2 text-slate-600">{a.dynamo}</td>
                <td className="px-3 py-2 font-mono text-xs text-mdb-forest">{a.mongo}</td>
                <td className="px-3 py-2 font-mono text-xs">{a.queries}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  )
}

function BenefitColumn({ title, tone, items }: { title: string; tone: string; items: Benefit[] }) {
  return (
    <div>
      <h3 className={`mb-2 text-sm font-semibold tracking-wide uppercase ${tone}`}>{title}</h3>
      <div className="grid gap-3">
        {items.map((b) => (
          <article key={b.title} className="rounded-lg border border-slate-200 bg-white p-4">
            <h4 className="font-semibold text-mdb-slate">{b.title}</h4>
            <p className="mt-1 text-sm leading-relaxed text-slate-600">{b.body}</p>
            <p className="mt-2 inline-block rounded bg-green-50 px-2 py-0.5 font-mono text-xs text-mdb-forest">{b.proof}</p>
          </article>
        ))}
      </div>
    </div>
  )
}

function Benefits() {
  return (
    <Section eyebrow="4 · Why it matters" title="Simpler to run, freer to evolve">
      <div className="grid gap-6 lg:grid-cols-2">
        <BenefitColumn title="Simplification" tone="text-sky-800" items={SIMPLIFICATION} />
        <BenefitColumn title="Flexibility" tone="text-emerald-800" items={FLEXIBILITY} />
      </div>
    </Section>
  )
}

function Fidelity() {
  return (
    <Section eyebrow="5 · Nothing lost" title="A faithful migration, verified">
      <div className="grid gap-3 sm:grid-cols-4">
        {FIDELITY.map((f) => (
          <div key={f.label} className="rounded-xl border border-green-200 bg-green-50/60 p-4">
            <p className="text-2xl font-semibold text-mdb-forest">{f.value}</p>
            <p className="text-sm text-slate-600">{f.label}</p>
          </div>
        ))}
      </div>
      <p className="text-sm text-slate-600">
        The golden-answer test seeds the converted data and checks every question against the criteria document.{' '}
        <NavLink to="/dynamo-graph" className="font-medium text-mdb-forest underline">
          Run the sample queries yourself →
        </NavLink>
      </p>
    </Section>
  )
}

export function MigrationStoryPage() {
  return (
    <div className="space-y-10">
      <Hero />
      <Transformation />
      <RoundTrips />
      <AccessPatterns />
      <Benefits />
      <Fidelity />
      <ClusterSizing />
    </div>
  )
}

export const route = { path: 'transformation', element: <MigrationStoryPage />, public: true }
export const navItem = { label: 'Transformation', order: 5, description: 'DynamoDB tables → MongoDB collections' }
