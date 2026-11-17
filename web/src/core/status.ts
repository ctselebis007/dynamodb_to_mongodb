import { useQuery } from '@tanstack/react-query'
import { api, type Schemas } from './api'

export type SetupStatus = Schemas['SetupStatus']

export const statusKey = ['setup', 'status'] as const

export function useSetupStatus() {
  return useQuery({ queryKey: statusKey, queryFn: () => api.get<SetupStatus>('/api/setup/status') })
}

export function isReady(s: SetupStatus | undefined): boolean {
  return !!s && s.seeded && s.indexed && !s.reseed_required
}
