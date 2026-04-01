import { useQuery } from '@tanstack/react-query'
import { fetchCosts, fetchCostEntries } from '../api/client'
import type { CostSummary, CostEntriesPage } from '../api/types'

export function useCosts() {
  return useQuery<CostSummary>({
    queryKey: ['costs'],
    queryFn: fetchCosts,
  })
}

export function useCostEntries(page = 1, perPage = 20) {
  return useQuery<CostEntriesPage>({
    queryKey: ['costs', 'entries', { page, perPage }],
    queryFn: () => fetchCostEntries(page, perPage),
  })
}

/** Fetch all cost entries (up to max_page_size=200) for client-side analysis. */
export function useAllCostEntries() {
  return useQuery<CostEntriesPage>({
    queryKey: ['costs', 'entries', 'all'],
    queryFn: () => fetchCostEntries(1, 200),
    staleTime: 60_000,
  })
}
