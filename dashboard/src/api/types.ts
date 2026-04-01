import { z } from 'zod'
import {
  AssetSummarySchema,
  CostEntriesPageSchema,
  CostEntrySchema,
  CostSummarySchema,
  EvaluationPointSchema,
  GenerationRowSchema,
  HealthResponseSchema,
  InstinctRowSchema,
  LoopTriggerResultSchema,
  ProviderStatusSchema,
  AssetContentSchema,
  LoopRunSchema,
  PendingAssetSchema,
  EvaluateResultSchema,
  RegenerateResultSchema,
  ScanResultSchema,
  ApprovalResultSchema,
  DeployResultSchema,
} from './client'

export type AssetSummary = z.infer<typeof AssetSummarySchema>
export type EvaluationPoint = z.infer<typeof EvaluationPointSchema>
export type CostSummary = z.infer<typeof CostSummarySchema>
export type CostEntry = z.infer<typeof CostEntrySchema>
export type CostEntriesPage = z.infer<typeof CostEntriesPageSchema>
export type InstinctRow = z.infer<typeof InstinctRowSchema>
export type ProviderStatus = z.infer<typeof ProviderStatusSchema>
export type GenerationRow = z.infer<typeof GenerationRowSchema>
export type LoopTriggerResult = z.infer<typeof LoopTriggerResultSchema>
export type HealthResponse = z.infer<typeof HealthResponseSchema>
export type AssetContent = z.infer<typeof AssetContentSchema>
export type LoopRun = z.infer<typeof LoopRunSchema>
export type PendingAsset = z.infer<typeof PendingAssetSchema>
export type EvaluateResult = z.infer<typeof EvaluateResultSchema>
export type RegenerateResult = z.infer<typeof RegenerateResultSchema>
export type ScanResult = z.infer<typeof ScanResultSchema>
export type ApprovalResult = z.infer<typeof ApprovalResultSchema>
export type DeployResult = z.infer<typeof DeployResultSchema>

/** Convert a 0–100 quality score to an A–F letter grade. */
export function scoreToGrade(score: number): 'A' | 'B' | 'C' | 'D' | 'F' {
  if (score >= 90) return 'A'
  if (score >= 75) return 'B'
  if (score >= 60) return 'C'
  if (score >= 40) return 'D'
  return 'F'
}

/** Return a Tailwind colour class for a 0–100 score. */
export function scoreColour(score: number): string {
  if (score >= 80) return 'score-high'
  if (score >= 60) return 'score-mid'
  return 'score-low'
}
