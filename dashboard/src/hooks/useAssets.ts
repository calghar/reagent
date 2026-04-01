import { useQuery } from '@tanstack/react-query'
import { fetchAssets, fetchAssetDetail } from '../api/client'
import type { AssetSummary, EvaluationPoint } from '../api/types'

export function useAssets(type?: string) {
  return useQuery<AssetSummary[]>({
    queryKey: ['assets', { type }],
    queryFn: () => fetchAssets(type),
  })
}

export function useAssetDetail(assetPath: string) {
  return useQuery<EvaluationPoint[]>({
    queryKey: ['assets', assetPath],
    queryFn: () => fetchAssetDetail(assetPath),
    enabled: Boolean(assetPath),
  })
}
