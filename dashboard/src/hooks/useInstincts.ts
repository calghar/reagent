import { useQuery } from '@tanstack/react-query'
import { fetchInstincts } from '../api/client'
import type { InstinctRow } from '../api/types'

export function useInstincts() {
  return useQuery<InstinctRow[]>({
    queryKey: ['instincts'],
    queryFn: fetchInstincts,
  })
}
