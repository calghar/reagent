import { useQuery } from '@tanstack/react-query'
import { fetchEvaluations } from '../api/client'
import type { EvaluationPoint } from '../api/types'

export function useEvaluations(limit?: number) {
  return useQuery<EvaluationPoint[]>({
    queryKey: ['evaluations', { limit }],
    queryFn: () => fetchEvaluations(limit),
  })
}
