import { useQuery } from '@tanstack/react-query'
import { fetchProviders } from '../api/client'
import type { ProviderStatus } from '../api/types'

export function useProviders() {
  return useQuery<ProviderStatus[]>({
    queryKey: ['providers'],
    queryFn: fetchProviders,
    staleTime: 60_000,
  })
}
