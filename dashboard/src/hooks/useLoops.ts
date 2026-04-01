import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  fetchLoops,
  fetchLoopRuns,
  fetchPendingAssets,
  fetchRepos,
  triggerLoop,
  approvePendingAsset,
  rejectPendingAsset,
  deployAllPending,
} from '../api/client'
import type { GenerationRow, LoopRun, PendingAsset } from '../api/types'

export function useRepos() {
  return useQuery<string[]>({
    queryKey: ['repos'],
    queryFn: fetchRepos,
  })
}

export function useLoopRuns() {
  return useQuery<LoopRun[]>({
    queryKey: ['loop-runs'],
    queryFn: fetchLoopRuns,
  })
}

export function usePendingAssets(loopId?: string) {
  return useQuery<PendingAsset[]>({
    queryKey: ['pending-assets', { loopId }],
    queryFn: () => fetchPendingAssets(loopId),
  })
}

export function useGenerations() {
  return useQuery<GenerationRow[]>({
    queryKey: ['loops'],
    queryFn: fetchLoops,
  })
}

export function useTriggerLoop() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (params: { loopType?: string; repoPath?: string }) =>
      triggerLoop(params.loopType, params.repoPath),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['loops'] })
      void qc.invalidateQueries({ queryKey: ['loop-runs'] })
    },
  })
}

export function useApprovePending() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (pendingId: string) => approvePendingAsset(pendingId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['pending-assets'] })
      void qc.invalidateQueries({ queryKey: ['loop-runs'] })
      void qc.invalidateQueries({ queryKey: ['assets'] })
    },
  })
}

export function useRejectPending() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (pendingId: string) => rejectPendingAsset(pendingId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['pending-assets'] })
      void qc.invalidateQueries({ queryKey: ['loop-runs'] })
    },
  })
}

export function useDeployAll() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: deployAllPending,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['pending-assets'] })
      void qc.invalidateQueries({ queryKey: ['assets'] })
    },
  })
}
