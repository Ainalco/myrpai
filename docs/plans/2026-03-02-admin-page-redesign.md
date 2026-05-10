# Admin Page Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Redesign the admin page into 3 focused pages: overview with clickable user table, per-user detail page, and daily usage & cost time-series page.

**Architecture:** Split the monolithic AdminPage into 3 routes. Add cost calculation utility (frontend-side: $3/M input, $15/M output). Extend backend to return prompt/completion token breakdowns in usage-over-time and recent executions in user detail.

**Tech Stack:** React, TypeScript, Recharts, React Query, FastAPI, SQLAlchemy

---

### Task 1: Backend — Add prompt/completion tokens to usage-over-time & recent executions to user detail

**Files:**
- Modify: `backend/admin.py:136-218` (usage-over-time endpoint)
- Modify: `backend/admin.py:221-286` (user detail endpoint)

**Step 1: Update usage-over-time to include prompt_tokens and completion_tokens per day per user**

In `backend/admin.py`, update the usage_rows query (line 147-158) to also select prompt_tokens and completion_tokens:

```python
usage_rows = (
    db.query(
        cast(models.AiUsageLog.created_at, Date).label("date"),
        models.User.username,
        func.coalesce(func.sum(models.AiUsageLog.total_tokens), 0).label("tokens"),
        func.coalesce(func.sum(models.AiUsageLog.prompt_tokens), 0).label("prompt_tokens"),
        func.coalesce(func.sum(models.AiUsageLog.completion_tokens), 0).label("completion_tokens"),
    )
    .join(models.User, models.AiUsageLog.user_id == models.User.id)
    .filter(models.AiUsageLog.created_at >= start_date)
    .group_by(cast(models.AiUsageLog.created_at, Date), models.User.username)
    .order_by(cast(models.AiUsageLog.created_at, Date))
    .all()
)
```

Update the fallback query (line 177-189) similarly with `total_prompt_tokens` and `total_completion_tokens` from Execution.

Update the daily_map building (lines 194-201) to include prompt/completion tokens:

```python
daily_map[date_str] = {"date": date_str, "tokens": 0, "prompt_tokens": 0, "completion_tokens": 0, "executions": 0, "by_user": {}}
# ...
daily_map[date_str]["by_user"][row.username] = {"tokens": 0, "prompt_tokens": 0, "completion_tokens": 0, "executions": 0}
# Add accumulation for prompt_tokens and completion_tokens
```

**Step 2: Add recent executions to user detail endpoint**

In `backend/admin.py`, before the `return` in `get_user_stats` (around line 270), add:

```python
# Recent executions
recent_executions = (
    db.query(models.Execution)
    .join(models.Workflow, models.Execution.workflow_id == models.Workflow.id)
    .filter(models.Workflow.owner_id == user_id)
    .order_by(models.Execution.started_at.desc())
    .limit(20)
    .all()
)
```

Add to the return dict:

```python
"recent_executions": [
    {
        "id": ex.id,
        "workflow_name": ex.workflow.name,
        "status": ex.status,
        "started_at": ex.started_at.isoformat() if ex.started_at else None,
        "total_tokens": ex.total_tokens or 0,
        "total_prompt_tokens": ex.total_prompt_tokens or 0,
        "total_completion_tokens": ex.total_completion_tokens or 0,
    }
    for ex in recent_executions
],
```

**Step 3: Verify backend changes**

Run: `cd /home/tauhid/code/aibot2/backend && python -c "import ast; ast.parse(open('admin.py').read()); print('OK')"`
Expected: OK

**Step 4: Commit**

```bash
git add backend/admin.py
git commit -m "feat(admin): add token breakdown to usage-over-time, recent executions to user detail"
```

---

### Task 2: Frontend — Add cost utility and update API types

**Files:**
- Modify: `frontend/src/lib/api.ts:142-204` (Admin types)
- Create: `frontend/src/lib/cost.ts`

**Step 1: Create cost utility**

Create `frontend/src/lib/cost.ts`:

```typescript
const INPUT_COST_PER_TOKEN = 3 / 1_000_000
const OUTPUT_COST_PER_TOKEN = 15 / 1_000_000

export function calculateCost(promptTokens: number, completionTokens: number): number {
  return promptTokens * INPUT_COST_PER_TOKEN + completionTokens * OUTPUT_COST_PER_TOKEN
}

export function formatCost(dollars: number): string {
  if (dollars >= 1) return `$${dollars.toFixed(2)}`
  if (dollars >= 0.01) return `$${dollars.toFixed(2)}`
  if (dollars > 0) return `$${dollars.toFixed(4)}`
  return '$0.00'
}
```

**Step 2: Update API types**

In `frontend/src/lib/api.ts`, update these types:

Update `DailyUserStats` (lines 169-172) to add prompt/completion:

```typescript
export interface DailyUserStats {
  tokens: number
  prompt_tokens: number
  completion_tokens: number
  executions: number
}
```

Update `DailyStat` (lines 174-179) to add prompt/completion:

```typescript
export interface DailyStat {
  date: string
  tokens: number
  prompt_tokens: number
  completion_tokens: number
  executions: number
  by_user: Record<string, DailyUserStats>
}
```

Update `AdminUserDetail` (lines 186-204) to add recent_executions and usage_by_source:

```typescript
export interface AdminUserDetail {
  user: {
    id: number
    username: string
    email: string
    full_name: string
    is_active: boolean
    created_at: string | null
  }
  workflows: {
    id: number
    name: string
    is_active: boolean
    created_at: string | null
    execution_count: number
    total_tokens: number
    last_executed: string | null
  }[]
  usage_by_source: {
    source: string
    call_count: number
    tokens: number
  }[]
  recent_executions: {
    id: number
    workflow_name: string
    status: string
    started_at: string | null
    total_tokens: number
    total_prompt_tokens: number
    total_completion_tokens: number
  }[]
}
```

**Step 3: Verify types compile**

Run: `cd /home/tauhid/code/aibot2/frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: No errors (or only pre-existing errors)

**Step 4: Commit**

```bash
git add frontend/src/lib/cost.ts frontend/src/lib/api.ts
git commit -m "feat(admin): add cost utility and update admin API types"
```

---

### Task 3: Frontend — Redesign AdminPage (overview with clickable table + cost)

**Files:**
- Modify: `frontend/src/pages/AdminPage.tsx` (complete rewrite)

**Step 1: Rewrite AdminPage.tsx**

Replace the entire file. The new AdminPage should:

- Import `useNavigate` from react-router-dom
- Import `calculateCost, formatCost` from `@/lib/cost`
- Keep the 4 summary cards but replace "Total Tokens" with "Total Cost" (calculated from prompt/completion tokens)
- Keep the sortable user table but:
  - Add a "Cost" column (calculated from `total_prompt_tokens` and `total_completion_tokens`)
  - Make rows clickable: `onClick={() => navigate(`/admin/user/${user.id}`)}`
  - Add cursor-pointer styling on rows
  - Add a "Cost" sort field
- Remove the "Usage Over Time" tab entirely (it moves to `/admin/usage`)
- Add a sub-navigation bar with links: "Overview" (current), "Usage & Cost" (links to `/admin/usage`)

Key structure:
```tsx
// Sub-nav bar with two links
<nav className="flex gap-4 border-b border-scurry-gray-border">
  <Link to="/admin" className="...active styles...">Overview</Link>
  <Link to="/admin/usage" className="...inactive styles...">Usage & Cost</Link>
</nav>

// 4 stat cards (Users, Workflows, Executions, Total Cost)
// Clickable user table with cost column
```

**Step 2: Verify it compiles**

Run: `cd /home/tauhid/code/aibot2/frontend && npx tsc --noEmit 2>&1 | head -20`

**Step 3: Commit**

```bash
git add frontend/src/pages/AdminPage.tsx
git commit -m "feat(admin): redesign overview page with clickable user table and cost"
```

---

### Task 4: Frontend — Create AdminUserPage (per-user detail)

**Files:**
- Create: `frontend/src/pages/AdminUserPage.tsx`

**Step 1: Create AdminUserPage.tsx**

This page at `/admin/user/:id` shows:

1. **Back link** + **Header**: User name, email, joined date, admin badge
2. **3 summary cards**: Total Cost, Workflows count, Executions count
3. **Token Usage by Source** section: horizontal bar chart using Recharts `BarChart` with `layout="vertical"` showing tokens per source (execution, component_test, email_edit, etc.)
4. **Workflows table**: name, execution count, tokens, cost, last executed, active badge
5. **Recent Executions** table: workflow name, status badge (green=completed, red=failed, yellow=running), tokens, cost, timestamp

Use:
- `useParams()` to get `id`
- `useQuery` with `adminApi.getUserDetail(id)`
- `calculateCost`/`formatCost` from `@/lib/cost`
- `Link` to go back to `/admin`
- `useNavigate` for navigation
- Recharts `BarChart` for source breakdown
- Scurry design system colors

Status badge colors:
- completed: `bg-green-100 text-green-700`
- failed: `bg-red-100 text-red-700`
- running: `bg-yellow-100 text-yellow-700`

**Step 2: Verify it compiles**

Run: `cd /home/tauhid/code/aibot2/frontend && npx tsc --noEmit 2>&1 | head -20`

**Step 3: Commit**

```bash
git add frontend/src/pages/AdminUserPage.tsx
git commit -m "feat(admin): add per-user detail page with source breakdown and execution log"
```

---

### Task 5: Frontend — Create AdminUsagePage (daily time-series + cost)

**Files:**
- Create: `frontend/src/pages/AdminUsagePage.tsx`

**Step 1: Create AdminUsagePage.tsx**

This page at `/admin/usage` shows:

1. **Sub-nav**: "Overview" (link to `/admin`) | "Usage & Cost" (active)
2. **Day selector**: 7d / 30d / 90d buttons
3. **Period summary cards**: Total Cost, Total Tokens (prompt + completion), Total Executions for selected period
4. **Daily Cost chart**: `AreaChart` with two stacked areas — input cost and output cost per day. Calculate from daily `prompt_tokens * 3/1M` and `completion_tokens * 15/1M`
5. **Daily Token Usage chart**: `LineChart` with per-user lines (same as old Usage Over Time tab but cleaner)
6. **Daily Executions chart**: `BarChart` with execution count per day

Use:
- `useQuery` with `adminApi.getUsageOverTime(days)`
- `calculateCost`/`formatCost` from `@/lib/cost`
- `Link` for sub-nav
- Recharts `AreaChart`, `LineChart`, `BarChart`
- Scurry design system colors
- Same `USER_COLORS` array for per-user lines

**Step 2: Verify it compiles**

Run: `cd /home/tauhid/code/aibot2/frontend && npx tsc --noEmit 2>&1 | head -20`

**Step 3: Commit**

```bash
git add frontend/src/pages/AdminUsagePage.tsx
git commit -m "feat(admin): add usage & cost time-series page"
```

---

### Task 6: Frontend — Add routes for new pages

**Files:**
- Modify: `frontend/src/App.tsx:20,191-200` (imports and routes)

**Step 1: Add imports and routes**

In `frontend/src/App.tsx`, add imports:

```typescript
import AdminUserPage from '@/pages/AdminUserPage'
import AdminUsagePage from '@/pages/AdminUsagePage'
```

After the existing `/admin` route (lines 191-200), add two new routes:

```tsx
<Route
  path="/admin/usage"
  element={
    <AdminRoute>
      <Layout>
        <AdminUsagePage />
      </Layout>
    </AdminRoute>
  }
/>
<Route
  path="/admin/user/:id"
  element={
    <AdminRoute>
      <Layout>
        <AdminUserPage />
      </Layout>
    </AdminRoute>
  }
/>
```

**Important:** Place `/admin/usage` and `/admin/user/:id` BEFORE the `/admin` route OR keep them after — React Router v6 handles specificity automatically, but to be safe keep specific routes before the catch-all.

**Step 2: Verify it compiles**

Run: `cd /home/tauhid/code/aibot2/frontend && npx tsc --noEmit 2>&1 | head -20`

**Step 3: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(admin): add routes for user detail and usage pages"
```

---

### Task 7: Verify everything works end-to-end

**Step 1: Restart backend to pick up admin.py changes**

Run: `docker compose restart backend`

**Step 2: Check backend health**

Run: `curl -s http://localhost:9000/health`
Expected: `{"status":"healthy"...}`

**Step 3: Check frontend compiles cleanly**

Run: `cd /home/tauhid/code/aibot2/frontend && npx tsc --noEmit 2>&1 | grep -i error | head -10`
Expected: No admin-related errors

**Step 4: Visually verify in browser**

- Navigate to `/admin` — should show overview with clickable user rows and cost column
- Click a user row — should navigate to `/admin/user/:id` with detail view
- Click "Usage & Cost" tab — should navigate to `/admin/usage` with time-series charts
- Back links should work

**Step 5: Final commit**

```bash
git add -A
git commit -m "feat(admin): complete admin page redesign with per-user detail and cost tracking"
```
