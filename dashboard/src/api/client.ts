import { z } from 'zod'

export const AssetSummarySchema = z.object({
  asset_path: z.string(),
  asset_type: z.string(),
  asset_name: z.string(),
  repo_path: z.string(),
  latest_score: z.number(),
  evaluation_count: z.number().int(),
  last_evaluated: z.string(),
  status: z.string(),
})

export const EvaluationPointSchema = z.object({
  evaluation_id: z.string(),
  asset_name: z.string(),
  asset_type: z.string(),
  quality_score: z.number(),
  evaluated_at: z.string(),
  repo_path: z.string(),
})

export const CostSummarySchema = z.object({
  total_usd: z.number(),
  by_provider: z.record(z.string(), z.number()),
  by_model: z.record(z.string(), z.number()),
  entry_count: z.number().int(),
  cache_hit_rate: z.number(),
})

export const CostEntrySchema = z.object({
  cost_id: z.string(),
  timestamp: z.string(),
  provider: z.string(),
  model: z.string(),
  asset_type: z.string(),
  asset_name: z.string(),
  input_tokens: z.number().int(),
  output_tokens: z.number().int(),
  cost_usd: z.number(),
  latency_ms: z.number().int(),
  tier: z.string(),
  was_fallback: z.boolean(),
})

export const CostEntriesPageSchema = z.object({
  items: z.array(CostEntrySchema),
  total: z.number().int(),
  page: z.number().int(),
  per_page: z.number().int(),
})

export const InstinctRowSchema = z.object({
  instinct_id: z.string(),
  content: z.string(),
  category: z.string(),
  trust_tier: z.string(),
  confidence: z.number(),
  use_count: z.number().int(),
  success_rate: z.number(),
  created_at: z.string(),
})

export const ProviderStatusSchema = z.object({
  provider: z.string(),
  model: z.string(),
  available: z.boolean(),
  key_configured: z.boolean(),
})

export const GenerationRowSchema = z.object({
  cache_key: z.string(),
  asset_type: z.string(),
  name: z.string(),
  generated_at: z.string(),
  provider: z.string(),
  model: z.string(),
  cost_usd: z.number(),
})

export const LoopTriggerResultSchema = z.object({
  job_id: z.string(),
  status: z.string(),
  message: z.string(),
  command: z.string(),
  loop_type: z.string(),
  repo_path: z.string(),
})

export const HealthResponseSchema = z.object({
  status: z.string(),
  db: z.string(),
})

const API_BASE: string = (import.meta.env['VITE_API_URL'] as string | undefined) ?? ''

// ── Generic fetch helper ──────────────────────────────────────────────────────

export async function fetchApi<T>(
  path: string,
  schema: z.ZodSchema<T>,
  options?: RequestInit
): Promise<T> {
  const timeoutSignal = AbortSignal.timeout(30_000)
  const signal = options?.signal
    ? AbortSignal.any([options.signal, timeoutSignal])
    : timeoutSignal
  const res = await fetch(`${API_BASE}${path}`, { ...options, signal })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = (await res.json()) as { message?: string }
      if (body?.message) detail = body.message
    } catch {
      /* ignore parse errors */
    }
    throw new Error(`API error ${res.status}: ${detail}`)
  }
  const json: unknown = await res.json()
  return schema.parse(json)
}

// ── Typed endpoint functions ──────────────────────────────────────────────────

export function fetchAssets(type?: string) {
  const qs = type ? `?type=${encodeURIComponent(type)}` : ''
  return fetchApi(`/api/assets${qs}`, z.array(AssetSummarySchema))
}

export function fetchAssetDetail(assetPath: string) {
  return fetchApi(
    `/api/assets/${encodeURIComponent(assetPath)}`,
    z.array(EvaluationPointSchema)
  )
}

export function fetchEvaluations(limit?: number) {
  const qs = limit != null ? `?limit=${limit}` : ''
  return fetchApi(`/api/evaluations${qs}`, z.array(EvaluationPointSchema))
}

export function fetchCosts() {
  return fetchApi('/api/costs', CostSummarySchema)
}

export function fetchCostEntries(page = 1, perPage = 20) {
  return fetchApi(
    `/api/costs/entries?page=${page}&per_page=${perPage}`,
    CostEntriesPageSchema
  )
}

export function fetchInstincts() {
  return fetchApi('/api/instincts', z.array(InstinctRowSchema))
}

export function fetchProviders() {
  return fetchApi('/api/providers', z.array(ProviderStatusSchema))
}

export function fetchRepos() {
  return fetchApi('/api/repos', z.array(z.string()))
}

export function fetchLoops() {
  return fetchApi('/api/loops', z.array(GenerationRowSchema))
}

export function triggerLoop(loopType = 'improve', repoPath = '.') {
  return fetchApi('/api/loops/trigger', LoopTriggerResultSchema, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ loop_type: loopType, repo_path: repoPath }),
  })
}

export function fetchHealth() {
  return fetchApi('/api/health', HealthResponseSchema)
}

// ── New schemas for asset detail, loop runs, pending assets ───────────────────

export const AssetContentSchema = z.object({
  asset_path: z.string(),
  asset_name: z.string(),
  asset_type: z.string(),
  content: z.string(),
  repo_path: z.string(),
  quality_score: z.number().nullable(),
  last_evaluated: z.string().nullable(),
})

export const LoopRunSchema = z.object({
  loop_id: z.string(),
  loop_type: z.string(),
  repo_path: z.string(),
  status: z.string(),
  stop_reason: z.string().nullable(),
  iteration: z.number().int(),
  total_cost: z.number(),
  avg_score: z.number().nullable(),
  started_at: z.string(),
  completed_at: z.string().nullable(),
})

export const PendingAssetSchema = z.object({
  pending_id: z.string(),
  asset_type: z.string(),
  asset_name: z.string(),
  file_path: z.string(),
  content: z.string(),
  previous_content: z.string().nullable(),
  previous_score: z.number().nullable(),
  new_score: z.number(),
  generation_method: z.string(),
  loop_id: z.string(),
  iteration: z.number().int(),
  created_at: z.string(),
  status: z.string(),
})

// ── Action result schemas ─────────────────────────────────────────────────────

export const EvaluateResultSchema = z.object({
  asset_path: z.string(),
  quality_score: z.number().nullable(),
  status: z.string(),
  message: z.string(),
})

export const RegenerateResultSchema = z.object({
  asset_path: z.string(),
  status: z.string(),
  message: z.string(),
})

export const ScanResultSchema = z.object({
  asset_path: z.string(),
  findings: z.array(
    z.object({
      severity: z.string(),
      message: z.string(),
      line: z.string().optional(),
      rule_id: z.string().optional(),
      matched_text: z.string().optional(),
    })
  ),
  status: z.string(),
})

export const ApprovalResultSchema = z.object({
  pending_id: z.string(),
  status: z.string(),
})

export const DeployResultSchema = z.object({
  deployed_count: z.number().int(),
})

// ── New fetch functions ───────────────────────────────────────────────────────

export function fetchAssetContent(assetPath: string) {
  return fetchApi(
    `/api/assets/${encodeURIComponent(assetPath)}/content`,
    AssetContentSchema
  )
}

export function fetchLoopRuns() {
  return fetchApi('/api/loops/state', z.array(LoopRunSchema))
}

export function fetchPendingAssets(loopId?: string) {
  const qs = loopId ? `?loop_id=${encodeURIComponent(loopId)}` : ''
  return fetchApi(`/api/loops/pending${qs}`, z.array(PendingAssetSchema))
}

// ── Asset action functions ────────────────────────────────────────────────────

export function evaluateAsset(assetPath: string) {
  return fetchApi(
    `/api/assets/${encodeURIComponent(assetPath)}/evaluate`,
    EvaluateResultSchema,
    { method: 'POST' }
  )
}

export function regenerateAsset(assetPath: string) {
  return fetchApi(
    `/api/assets/${encodeURIComponent(assetPath)}/regenerate`,
    RegenerateResultSchema,
    { method: 'POST' }
  )
}

export function scanAsset(assetPath: string) {
  return fetchApi(
    `/api/assets/${encodeURIComponent(assetPath)}/scan`,
    ScanResultSchema,
    { method: 'POST' }
  )
}

// ── Pending asset action functions ────────────────────────────────────────────

export function approvePendingAsset(pendingId: string) {
  return fetchApi(
    `/api/loops/pending/${encodeURIComponent(pendingId)}/approve`,
    ApprovalResultSchema,
    { method: 'POST' }
  )
}

export function rejectPendingAsset(pendingId: string) {
  return fetchApi(
    `/api/loops/pending/${encodeURIComponent(pendingId)}/reject`,
    ApprovalResultSchema,
    { method: 'POST' }
  )
}

export function deployAllPending() {
  return fetchApi('/api/loops/pending/deploy', DeployResultSchema, {
    method: 'POST',
  })
}
