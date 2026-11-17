import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { api, type Schemas } from '../api'
import { statusKey, useSetupStatus } from '../status'
import { pushToast, toastError } from '../toast'

type Masked = Schemas['MaskedSettings']
type Update = Schemas['SettingsUpdate']
type Job = Schemas['Job']
type CheckRow = Schemas['CheckRow']
type Provider = Masked['provider']

export interface FormState {
  mongo_uri: string
  db_name: string
  provider: Provider
  model: string
  api_key: string
  voyage_base_url: string
}

const setupKey = ['setup'] as const

/** Blank secret fields are omitted so the server keeps the stored value. */
export function buildUpdate(form: FormState): Update {
  const update: Update = {
    db_name: form.db_name,
    provider: form.provider,
    model: form.model,
    voyage_base_url: form.voyage_base_url,
  }
  if (form.mongo_uri.trim()) update.mongo_uri = form.mongo_uri.trim()
  if (form.api_key.trim()) update.api_key = form.api_key.trim()
  return update
}

function fromMasked(m: Masked): FormState {
  return {
    mongo_uri: '',
    api_key: '',
    db_name: m.db_name,
    provider: m.provider,
    model: m.model,
    voyage_base_url: m.voyage_base_url,
  }
}

function SecretInput(props: {
  id: string
  label: string
  value: string
  placeholder: string
  onChange: (v: string) => void
}) {
  const [show, setShow] = useState(false)
  return (
    <div>
      <label htmlFor={props.id} className="block text-sm font-medium">
        {props.label}
      </label>
      <div className="mt-1 flex">
        <input
          id={props.id}
          type={show ? 'text' : 'password'}
          autoComplete="off"
          spellCheck={false}
          value={props.value}
          placeholder={props.placeholder}
          onChange={(e) => props.onChange(e.target.value)}
          className="w-full rounded-l-md border border-slate-300 px-3 py-2 font-mono text-sm"
        />
        <button
          type="button"
          onClick={() => setShow((s) => !s)}
          className="rounded-r-md border border-l-0 border-slate-300 px-3 text-sm text-slate-600 hover:bg-slate-50"
          aria-label={show ? `Hide ${props.label}` : `Show ${props.label}`}
        >
          {show ? 'Hide' : 'Show'}
        </button>
      </div>
    </div>
  )
}

const STATUS_STYLE: Record<CheckRow['status'], string> = {
  ok: 'bg-emerald-100 text-emerald-800',
  warn: 'bg-amber-100 text-amber-800',
  fail: 'bg-red-100 text-red-800',
  skip: 'bg-slate-100 text-slate-500',
}

function CheckRows({ rows }: { rows: CheckRow[] }) {
  return (
    <ul className="divide-y divide-slate-100 rounded-md border border-slate-200 bg-white">
      {rows.map((r) => (
        <li key={r.id} className="flex items-start gap-3 px-3 py-2 text-sm">
          <span className={`w-12 rounded px-1.5 py-0.5 text-center text-xs font-semibold uppercase ${STATUS_STYLE[r.status]}`}>
            {r.status}
          </span>
          <div className="flex-1">
            <p className="font-medium">{r.label}</p>
            {r.message && <p className="text-slate-600">{r.message}</p>}
            {r.hint && <p className="text-xs text-amber-700">{r.hint}</p>}
          </div>
          {r.ms != null && <span className="text-xs text-slate-400">{r.ms} ms</span>}
        </li>
      ))}
    </ul>
  )
}

function useJob(id: string | null, onFinished: (job: Job) => void) {
  const query = useQuery({
    queryKey: ['job', id],
    queryFn: () => api.get<Job>(`/api/setup/jobs/${id}`),
    enabled: !!id,
    refetchInterval: (q) => (q.state.data?.status === 'running' || !q.state.data ? 1000 : false),
  })
  const status = query.data?.status
  useEffect(() => {
    if (query.data && status !== 'running') onFinished(query.data)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status])
  return query.data
}

function JobProgress({ job }: { job: Job | undefined }) {
  if (!job) return null
  return (
    <div className="mt-3 space-y-2">
      <div className="h-2 overflow-hidden rounded bg-slate-200">
        <div
          className={`h-full transition-all ${job.status === 'error' ? 'bg-red-500' : 'bg-mdb-green'}`}
          style={{ width: `${job.progress}%` }}
        />
      </div>
      <ul className="space-y-1 text-sm">
        {job.steps.map((s) => (
          <li key={s.id} className="flex justify-between gap-2">
            <span>{s.label}</span>
            <span className={s.status === 'error' ? 'text-red-600' : 'text-slate-500'}>
              {s.status === 'done' ? '✓ ' : ''}
              {s.detail || s.status}
            </span>
          </li>
        ))}
      </ul>
      {job.error && (
        <p className="text-sm text-red-700">
          {job.error.message} {job.error.hint && <span className="text-slate-600">— {job.error.hint}</span>}
        </p>
      )}
    </div>
  )
}

const btn = 'rounded-md px-4 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50'

export function SetupPage() {
  const qc = useQueryClient()
  const { data: saved } = useQuery({ queryKey: setupKey, queryFn: () => api.get<Masked>('/api/setup') })
  const { data: status } = useSetupStatus()
  const [form, setForm] = useState<FormState | null>(null)
  const [rows, setRows] = useState<CheckRow[] | null>(null)
  const [seedJobId, setSeedJobId] = useState<string | null>(null)
  const [indexJobId, setIndexJobId] = useState<string | null>(null)

  useEffect(() => {
    if (saved && !form) setForm(fromMasked(saved))
  }, [saved, form])

  const refresh = () => qc.invalidateQueries({ queryKey: statusKey })
  const seedJob = useJob(seedJobId, refresh)
  const indexJob = useJob(indexJobId, refresh)

  const save = useMutation({
    mutationFn: (f: FormState) => api.put<Masked>('/api/setup', buildUpdate(f)),
    onSuccess: (m) => {
      qc.setQueryData(setupKey, m)
      setForm(fromMasked(m))
      refresh()
      pushToast({ kind: 'success', title: 'Settings saved' })
    },
    onError: toastError,
  })
  const test = useMutation({
    mutationFn: (f: FormState) => api.post<Schemas['CheckResults']>('/api/setup/test', buildUpdate(f)),
    onMutate: () => setRows(null),
    onSuccess: (r) => setRows(r.rows),
    onError: toastError,
  })
  const seed = useMutation({
    mutationFn: () => api.post<Job>('/api/setup/seed', { confirm: true }),
    onSuccess: (job) => setSeedJobId(job.id),
    onError: toastError,
  })
  const indexes = useMutation({
    mutationFn: () => api.post<Job>('/api/setup/indexes'),
    onSuccess: (job) => setIndexJobId(job.id),
    onError: toastError,
  })

  if (!saved || !form) return <p className="text-slate-500">Loading settings…</p>

  const models = saved.models[form.provider] ?? {}
  const dims = models[form.model]
  const dirty = JSON.stringify(buildUpdate(form)) !== JSON.stringify(buildUpdate(fromMasked(saved)))
  const set = (patch: Partial<FormState>) => setForm({ ...form, ...patch })
  const seeding = seedJob?.status === 'running' || seed.isPending
  const indexing = indexJob?.status === 'running' || indexes.isPending
  const noModules = status?.modules.length === 0

  const confirmSeed = () => {
    const names = status?.modules.join(', ')
    if (window.confirm(`Seeding drops and recreates the collections for: ${names}. Continue?`)) seed.mutate()
  }

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <section className="space-y-4 rounded-lg border border-slate-200 bg-white p-6">
        <h1 className="text-xl font-semibold">Setup</h1>
        <SecretInput
          id="mongo_uri"
          label="MongoDB URI"
          value={form.mongo_uri}
          placeholder={saved.has_uri ? `${saved.mongo_uri} (saved, leave blank to keep)` : 'mongodb+srv://user:pass@cluster.mongodb.net/'}
          onChange={(v) => set({ mongo_uri: v })}
        />
        <div>
          <label htmlFor="db_name" className="block text-sm font-medium">
            Database name
          </label>
          <input
            id="db_name"
            value={form.db_name}
            onChange={(e) => set({ db_name: e.target.value })}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label htmlFor="provider" className="block text-sm font-medium">
              Embedding provider
            </label>
            <select
              id="provider"
              value={form.provider}
              onChange={(e) => {
                const provider = e.target.value as Provider
                // The first model in the server registry is the provider default.
                set({ provider, model: Object.keys(saved.models[provider] ?? {})[0] ?? '' })
              }}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            >
              <option value="voyage">Voyage AI</option>
              <option value="openai">OpenAI</option>
            </select>
          </div>
          <div>
            <label htmlFor="model" className="block text-sm font-medium">
              Model
            </label>
            <select
              id="model"
              value={form.model}
              onChange={(e) => set({ model: e.target.value })}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            >
              {Object.keys(models).map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
            <p className="mt-1 text-xs text-slate-500" data-testid="dims">
              {dims} dimensions
            </p>
          </div>
        </div>
        <SecretInput
          id="api_key"
          label="API key"
          value={form.api_key}
          placeholder={saved.has_key ? `•••• ${saved.key_last4 ?? ''} (saved, leave blank to keep)` : form.provider === 'voyage' ? 'Atlas model API key or Voyage key' : 'sk-…'}
          onChange={(v) => set({ api_key: v })}
        />
        {form.provider === 'voyage' && (
          <details className="text-sm">
            <summary className="cursor-pointer text-slate-600">Advanced</summary>
            <label htmlFor="voyage_base_url" className="mt-2 block text-sm font-medium">
              Voyage base URL
            </label>
            <input
              id="voyage_base_url"
              value={form.voyage_base_url}
              onChange={(e) => set({ voyage_base_url: e.target.value })}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 font-mono text-sm"
            />
            <p className="mt-1 text-xs text-slate-500">
              https://ai.mongodb.com for Atlas model API keys, https://api.voyageai.com for Voyage keys.
            </p>
          </details>
        )}
        <div className="flex gap-2 pt-2">
          <button className={`${btn} bg-mdb-forest text-white hover:bg-mdb-forest/90`} disabled={save.isPending} onClick={() => save.mutate(form)}>
            Save
          </button>
          <button className={`${btn} border border-slate-300 hover:bg-slate-50`} disabled={test.isPending} onClick={() => test.mutate(form)}>
            {test.isPending ? 'Testing…' : 'Test Connections'}
          </button>
        </div>
        {rows && <CheckRows rows={rows} />}
      </section>

      <section className="space-y-6">
        {noModules && (
          <div className="rounded-lg border border-sky-200 bg-sky-50 p-4 text-sm text-sky-900" role="note">
            <p className="font-medium">No feature modules yet.</p>
            <p className="mt-1">
              Add your own under <code>api/app/modules/&lt;name&gt;/</code> and <code>web/src/modules/&lt;name&gt;/</code> (see
              &ldquo;Build your own module&rdquo; in the README), then restart <code>npm run dev</code>. Seed and Create
              Indexes work once a module defines data.
            </p>
          </div>
        )}
        <div className="rounded-lg border border-slate-200 bg-white p-6">
          <h2 className="font-semibold">1. Seed Database</h2>
          <p className="mt-1 text-sm text-slate-600">
            Generates deterministic synthetic data for each module, embeds it with the selected model, and inserts it.
          </p>
          {status?.meta?.seeded_at && (
            <p className="mt-1 text-xs text-slate-500">
              Seeded with {status.meta.provider} / {status.meta.model} ({status.meta.dims} dims)
            </p>
          )}
          <button
            className={`${btn} bg-mdb-forest mt-3 text-white`}
            disabled={dirty || seeding || !saved.has_uri || noModules}
            title={dirty ? 'Save your changes first' : undefined}
            onClick={confirmSeed}
          >
            {seeding ? 'Seeding…' : 'Seed Database'}
          </button>
          <JobProgress job={seedJob} />
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-6">
          <h2 className="font-semibold">2. Create Indexes</h2>
          <p className="mt-1 text-sm text-slate-600">Creates regular, Atlas Search and Vector Search indexes and waits until they are queryable.</p>
          {status?.indexed && <p className="mt-1 text-xs text-emerald-700">All indexes ready.</p>}
          <button
            className={`${btn} bg-mdb-forest mt-3 text-white`}
            disabled={dirty || indexing || !status?.seeded || seeding || noModules}
            onClick={() => indexes.mutate()}
          >
            {indexing ? 'Building…' : 'Create Indexes'}
          </button>
          <JobProgress job={indexJob} />
        </div>
        {status?.error && (
          <p className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">
            {status.error.message} <span className="text-slate-600">{status.error.hint}</span>
          </p>
        )}
      </section>
    </div>
  )
}
