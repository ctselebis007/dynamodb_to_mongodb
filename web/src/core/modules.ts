import type { ReactNode } from 'react'

/** Contract for `src/modules/<name>/index.tsx`: export `route` and `navItem`. */
export interface DemoModule {
  /** `public` pages are static and stay available before Seed / Create Indexes. */
  route: { path: string; element: ReactNode; public?: boolean }
  navItem: { label: string; order?: number; description?: string }
}

type Globbed = Record<string, Partial<DemoModule>>

const discovered = import.meta.glob<Partial<DemoModule>>('../modules/*/index.tsx', { eager: true })

export function loadModules(found: Globbed = discovered): DemoModule[] {
  return Object.entries(found)
    .filter((entry): entry is [string, DemoModule] => {
      const ok = !!entry[1].route && !!entry[1].navItem
      if (!ok) console.warn(`Skipping ${entry[0]}: export { route, navItem }`)
      return ok
    })
    .map(([, m]) => m)
    .sort((a, b) => (a.navItem.order ?? 100) - (b.navItem.order ?? 100))
}
