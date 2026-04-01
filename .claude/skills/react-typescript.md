---
name: react-typescript
description: React 19 + TypeScript coding standards for the reagent dashboard. Load this skill when writing or reviewing frontend code in the dashboard/ directory.
---

# React 19 + TypeScript Standards for Reagent Dashboard

Standards for the reagent web dashboard. All code in `dashboard/` follows these rules.

## Project Setup

- **React 19** with TypeScript strict mode
- **Vite** for development and build
- **@tanstack/react-query** for server state
- **Recharts** for data visualization
- **Zod** for runtime type validation of API responses
- **CSS Modules** or Tailwind for styling

## TypeScript Configuration

```json
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "target": "ES2024",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "paths": { "@/*": ["./src/*"] }
  }
}
```

Rules:

- `strict: true` always. No `any` — use `unknown` + narrowing.
- `noUncheckedIndexedAccess` catches missing index checks.
- Path aliases (`@/components/...`) for clean imports.

## Component Patterns

```tsx
// Prefer function keyword for components
type AssetCardProps = {
  asset: Asset;
  onSelect: (id: string) => void;
};

function AssetCard({ asset, onSelect }: AssetCardProps) {
  return (
    <article
      className={styles.card}
      onClick={() => onSelect(asset.id)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && onSelect(asset.id)}
    >
      <GradeBadge grade={asset.grade} />
      <h3>{asset.name}</h3>
      <p>{asset.type}</p>
    </article>
  );
}

export { AssetCard };
```

Rules:

- `function` keyword for components, not arrow functions.
- Explicit `Props` type (not inline). Named export.
- Semantic HTML: `article`, `section`, `nav`, `main`, not div soup.
- Keyboard accessibility: `tabIndex`, `onKeyDown` for interactive non-button elements.
- Prefer `button` for clickable elements when semantically appropriate.

## Data Fetching with React Query

```tsx
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchAssets, triggerLoop } from '@/api/client';

// Queries
function useAssets() {
  return useQuery({
    queryKey: ['assets'],
    queryFn: fetchAssets,
    staleTime: 30_000,
  });
}

function useAsset(id: string) {
  return useQuery({
    queryKey: ['assets', id],
    queryFn: () => fetchAssetById(id),
    enabled: Boolean(id),
  });
}

// Mutations
function useTriggerLoop() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: triggerLoop,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['loops'] });
    },
  });
}
```

Rules:

- **All server data via React Query**. Never `useEffect` + `fetch`.
- Query keys: `['resource']` for lists, `['resource', id]` for detail.
- `staleTime` set per query based on data freshness needs.
- Mutations invalidate related queries on success.
- Error/loading states handled in components with discriminated unions.

## API Client

```tsx
// dashboard/src/api/client.ts
const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8080';

async function fetchJson<T>(path: string, schema: z.ZodType<T>): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`);
  if (!response.ok) {
    throw new ApiError(response.status, await response.text());
  }
  const data: unknown = await response.json();
  return schema.parse(data);
}

// Typed endpoints
const AssetSchema = z.object({
  id: z.string(),
  name: z.string(),
  type: z.enum(['agent', 'skill', 'hook', 'command', 'rule', 'claude_md']),
  grade: z.enum(['A', 'B', 'C', 'D', 'F']),
  score: z.number(),
});

type Asset = z.infer<typeof AssetSchema>;

function fetchAssets(): Promise<Asset[]> {
  return fetchJson('/api/assets', z.array(AssetSchema));
}
```

Rules:

- Zod schemas validate ALL API responses at runtime.
- `z.infer<typeof Schema>` derives TypeScript types from Zod schemas (single source of truth).
- Typed error class for API errors.
- Base URL from environment variable with localhost fallback.

## SSE (Server-Sent Events) Client

```tsx
function useLoopProgress(loopId: string | null) {
  const [progress, setProgress] = useState<LoopProgress | null>(null);

  useEffect(() => {
    if (!loopId) return;

    const source = new EventSource(`${BASE_URL}/api/loops/${loopId}/events`);
    source.onmessage = (event) => {
      const data = LoopProgressSchema.parse(JSON.parse(event.data));
      setProgress(data);
    };
    source.onerror = () => source.close();

    return () => source.close();
  }, [loopId]);

  return progress;
}
```

SSE is the one exception to the "no useEffect + fetch" rule — EventSource requires imperative setup.

## Styling

```css
/* Use CSS variables for theming */
:root {
  --color-bg: #0a0a0b;
  --color-surface: #141416;
  --color-border: #2a2a2e;
  --color-text: #e4e4e7;
  --color-text-muted: #71717a;
  --color-accent: #3b82f6;
  --color-success: #22c55e;
  --color-warning: #eab308;
  --color-error: #ef4444;
  --radius: 8px;
  --font-mono: 'JetBrains Mono', monospace;
  --font-sans: 'IBM Plex Sans', system-ui, sans-serif;
}
```

Rules:

- CSS variables for all design tokens. Dark theme by default (developer tool).
- Responsive: container queries for component-level responsiveness.
- No inline styles except truly dynamic values (chart dimensions).
- Accessible contrast ratios (WCAG AA minimum).
- Transitions: 150-200ms for micro-interactions, ease-out timing.

## Charts (Recharts)

```tsx
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

function EvalTrendChart({ data }: { data: EvalDataPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={data}>
        <XAxis dataKey="date" />
        <YAxis domain={[0, 100]} />
        <Tooltip />
        <Line type="monotone" dataKey="score" stroke="var(--color-accent)" strokeWidth={2} />
      </LineChart>
    </ResponsiveContainer>
  );
}
```

Rules:

- Always wrap in `ResponsiveContainer`.
- Use CSS variables for chart colors.
- Accessible: include `Tooltip` for data values.

## File Organization

```sh
dashboard/src/
  main.tsx              # Entry point, React Query provider
  App.tsx               # Router, layout
  api/
    client.ts           # Typed fetch functions
    schemas.ts          # Zod schemas
    sse.ts              # EventSource hooks
  pages/
    AssetOverview.tsx
    EvalTrends.tsx
    CostMonitor.tsx
    InstinctStore.tsx
    ProviderConfig.tsx
    LoopControl.tsx
  components/
    Sidebar.tsx
    AssetCard.tsx
    GradeBadge.tsx
    ScoreChart.tsx
    CostChart.tsx
  hooks/
    useAssets.ts
    useCosts.ts
    useLoopProgress.ts
```

Rules:

- Pages in `pages/`. Reusable components in `components/`. Custom hooks in `hooks/`.
- One component per file. File name matches component name.
- Index files only for barrel exports, not for components.

## References

- React 19: <https://react.dev/blog/2024/12/05/react-19>
- React Reference: <https://react.dev/reference/react>
- TanStack Query v5: <https://tanstack.com/query/latest/docs/framework/react/overview>
- Vite: <https://vite.dev/guide/>
- Recharts: <https://recharts.org/en-US/api>
- Zod: <https://zod.dev/>
- TypeScript Handbook: <https://www.typescriptlang.org/docs/handbook/>
- Josh Comeau's CSS: <https://www.joshwcomeau.com/css/>
- Web Accessibility (WAI): <https://www.w3.org/WAI/fundamentals/>
- Total TypeScript (Matt Pocock): <https://www.totaltypescript.com/>
