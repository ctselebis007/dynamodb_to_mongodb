import { useSyncExternalStore } from 'react'
import { ApiError } from './api'

export interface Toast {
  id: number
  title: string
  hint?: string
  kind: 'error' | 'success'
}

let toasts: Toast[] = []
let nextId = 1
const listeners = new Set<() => void>()

function emit() {
  listeners.forEach((l) => l())
}

export function dismissToast(id: number) {
  toasts = toasts.filter((t) => t.id !== id)
  emit()
}

export function pushToast(t: Omit<Toast, 'id'>) {
  const id = nextId++
  toasts = [...toasts, { ...t, id }]
  emit()
  setTimeout(() => dismissToast(id), t.kind === 'error' ? 8000 : 3000)
}

export function toastError(e: unknown) {
  if (e instanceof ApiError) pushToast({ kind: 'error', title: e.message, hint: e.hint })
  else pushToast({ kind: 'error', title: e instanceof Error ? e.message : String(e) })
}

function subscribe(l: () => void) {
  listeners.add(l)
  return () => listeners.delete(l)
}

export function Toaster() {
  const items = useSyncExternalStore(subscribe, () => toasts)
  return (
    <div className="fixed right-4 bottom-4 z-50 flex w-96 flex-col gap-2" role="status">
      {items.map((t) => (
        <div
          key={t.id}
          className={`rounded-lg border p-3 shadow-lg ${t.kind === 'error' ? 'border-red-200 bg-red-50' : 'border-emerald-200 bg-emerald-50'}`}
        >
          <div className="flex items-start justify-between gap-2">
            <p className="text-sm font-medium">{t.title}</p>
            <button className="text-slate-400 hover:text-slate-700" onClick={() => dismissToast(t.id)} aria-label="Dismiss">
              ×
            </button>
          </div>
          {t.hint && <p className="mt-1 text-xs text-slate-600">{t.hint}</p>}
        </div>
      ))}
    </div>
  )
}
