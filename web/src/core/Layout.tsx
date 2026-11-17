import type { ReactNode } from 'react'
import { NavLink, Outlet } from 'react-router'
import type { DemoModule } from './modules'
import { isReady, useSetupStatus, type SetupStatus } from './status'
import { Toaster } from './toast'

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-md px-3 py-1.5 text-sm font-medium ${isActive ? 'bg-white/10 text-mdb-green' : 'text-slate-200 hover:bg-white/10'}`

export function Nav({ modules, status }: { modules: DemoModule[]; status: SetupStatus | undefined }) {
  const ready = isReady(status)
  return (
    <nav className="flex items-center gap-1" aria-label="Main">
      <NavLink to="/setup" className={linkClass}>
        Setup
      </NavLink>
      {modules.map((m) =>
        ready || m.route.public ? (
          <NavLink key={m.route.path} to={`/${m.route.path}`} className={linkClass}>
            {m.navItem.label}
          </NavLink>
        ) : (
          <span
            key={m.route.path}
            aria-disabled="true"
            title="Seed the database and create indexes on Setup first"
            className="cursor-not-allowed rounded-md px-3 py-1.5 text-sm font-medium text-slate-500"
          >
            {m.navItem.label}
          </span>
        ),
      )}
    </nav>
  )
}

export function Banner({ status }: { status: SetupStatus | undefined }) {
  if (!status?.reseed_required) return null
  return (
    <div role="alert" className="border-b border-amber-300 bg-amber-50 px-6 py-2 text-sm text-amber-900">
      <strong>Re-seed required.</strong> The data was embedded with{' '}
      {status.meta ? `${status.meta.provider} / ${status.meta.model}` : 'a different model'}. Run Seed and Create
      Indexes on Setup.
    </div>
  )
}

export function Layout({ modules }: { modules: DemoModule[] }) {
  const { data: status } = useSetupStatus()
  return (
    <div className="min-h-screen">
      <header className="bg-mdb-slate flex items-center gap-6 px-6 py-3 text-white">
        <span className="font-semibold">
          <span className="text-mdb-green">MongoDB</span> Demo
        </span>
        <Nav modules={modules} status={status} />
      </header>
      <Banner status={status} />
      <main className="mx-auto max-w-7xl p-6">
        <Outlet />
      </main>
      <Toaster />
    </div>
  )
}

export function ReadyGate({ children }: { children: ReactNode }) {
  const { data: status, isLoading } = useSetupStatus()
  if (isLoading) return <p className="text-slate-500">Loading…</p>
  if (!isReady(status)) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-6">
        <p className="font-medium">This demo isn&apos;t ready yet.</p>
        <p className="mt-1 text-sm text-slate-600">
          Open{' '}
          <NavLink to="/setup" className="text-mdb-forest underline">
            Setup
          </NavLink>
          , then Seed Database and Create Indexes.
        </p>
      </div>
    )
  }
  return <>{children}</>
}
