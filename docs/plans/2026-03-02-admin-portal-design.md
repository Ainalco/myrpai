# Admin Portal Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an admin portal at `/admin` where admin users can view platform-wide stats: token usage per user, workflow execution counts, and workflow counts, with summary tables and time-series charts.

**Architecture:** Add `is_admin` boolean to User model. New `backend/admin.py` router with SQL aggregation endpoints. New `AdminPage.tsx` with tabbed UI (Overview + Usage Over Time) using Recharts for charts. Auth guard at both backend (403) and frontend (redirect) levels.

**Tech Stack:** FastAPI (backend), React + TypeScript + Recharts (frontend), Alembic (migration), SQLAlchemy (queries)

---

### Task 1: Add `is_admin` column to User model + migration

**Files:**
- Modify: `backend/models.py:14` (add is_admin column after is_active)
- Create: `backend/alembic/versions/016_add_is_admin_to_users.py`

**Step 1: Add column to User model**

In `backend/models.py`, add after line 14 (`is_active = Column(Boolean, default=True)`):

```python
is_admin = Column(Boolean, default=False)
```

**Step 2: Create Alembic migration**

Run:
```bash
cd backend && alembic revision --autogenerate -m "add is_admin to users"
```

Verify the generated migration contains `op.add_column('users', sa.Column('is_admin', sa.Boolean(), nullable=True))` in upgrade and `op.drop_column('users', 'is_admin')` in downgrade.

Rename the generated file to `016_add_is_admin_to_users.py` for consistency.

**Step 3: Apply migration**

Run:
```bash
cd backend && python migrate.py
```

Expected: Migration applied successfully.

**Step 4: Mark your user as admin**

Run (adjust username):
```bash
docker compose exec postgres psql -U workflow_user -d workflow_platform -c "UPDATE users SET is_admin = true WHERE id = 1;"
```

**Step 5: Commit**

```bash
git add backend/models.py backend/alembic/versions/016_add_is_admin_to_users.py
git commit -m "feat: add is_admin column to users table"
```

---

### Task 2: Add `is_admin` to auth Pydantic model + context

**Files:**
- Modify: `backend/auth.py:49` (add is_admin to User response model)
- Modify: `frontend/src/lib/api.ts:48-63` (add is_admin to User type)
- Modify: `frontend/src/contexts/AuthContext.tsx` (no changes needed, it already passes through User)

**Step 1: Update backend auth User model**

In `backend/auth.py`, in the `User` Pydantic model (around line 48), add after `is_active`:

```python
is_admin: bool = False
```

**Step 2: Update frontend User type**

In `frontend/src/lib/api.ts`, in the `User` interface (around line 48), add after `is_active`:

```typescript
is_admin?: boolean
```

**Step 3: Verify**

Start the app and call `GET /auth/me` — response should include `is_admin` field. The AuthContext already passes the full User object through, so `user.is_admin` will be available in React components.

**Step 4: Commit**

```bash
git add backend/auth.py frontend/src/lib/api.ts
git commit -m "feat: expose is_admin field in auth response and frontend types"
```

---

### Task 3: Create backend admin router with auth guard

**Files:**
- Create: `backend/admin.py`
- Modify: `backend/main.py:21,93` (import and register admin router)

**Step 1: Create `backend/admin.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Date
from datetime import datetime, timedelta
from typing import Optional
import logging

from database import get_db
from auth import get_current_active_user
import models

logger = logging.getLogger(__name__)

router = APIRouter()


async def get_current_admin_user(
    current_user: models.User = Depends(get_current_active_user),
) -> models.User:
    """Dependency that ensures the current user is an admin."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


@router.get("/stats/overview")
async def get_admin_overview(
    current_user: models.User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Get platform overview stats and per-user breakdown."""
    # Total counts
    total_users = db.query(func.count(models.User.id)).scalar()
    total_workflows = db.query(func.count(models.Workflow.id)).scalar()
    total_executions = db.query(func.count(models.Execution.id)).scalar()

    # Total tokens across all executions
    token_result = db.query(
        func.coalesce(func.sum(models.Execution.total_tokens), 0),
        func.coalesce(func.sum(models.Execution.total_prompt_tokens), 0),
        func.coalesce(func.sum(models.Execution.total_completion_tokens), 0),
    ).first()
    total_tokens = token_result[0]
    total_prompt_tokens = token_result[1]
    total_completion_tokens = token_result[2]

    # Per-user stats
    users = db.query(models.User).all()
    user_stats = []
    for user in users:
        workflow_count = (
            db.query(func.count(models.Workflow.id))
            .filter(models.Workflow.owner_id == user.id)
            .scalar()
        )
        # Execution stats via workflows
        user_executions = (
            db.query(
                func.count(models.Execution.id),
                func.coalesce(func.sum(models.Execution.total_tokens), 0),
                func.coalesce(func.sum(models.Execution.total_prompt_tokens), 0),
                func.coalesce(func.sum(models.Execution.total_completion_tokens), 0),
                func.max(models.Execution.started_at),
            )
            .join(models.Workflow, models.Execution.workflow_id == models.Workflow.id)
            .filter(models.Workflow.owner_id == user.id)
            .first()
        )

        user_stats.append({
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "is_active": user.is_active,
            "is_admin": user.is_admin,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "workflow_count": workflow_count,
            "execution_count": user_executions[0] if user_executions else 0,
            "total_tokens": user_executions[1] if user_executions else 0,
            "total_prompt_tokens": user_executions[2] if user_executions else 0,
            "total_completion_tokens": user_executions[3] if user_executions else 0,
            "last_active": user_executions[4].isoformat() if user_executions and user_executions[4] else None,
        })

    return {
        "total_users": total_users,
        "total_workflows": total_workflows,
        "total_executions": total_executions,
        "total_tokens": total_tokens,
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "users": user_stats,
    }


@router.get("/stats/usage-over-time")
async def get_usage_over_time(
    days: int = Query(default=30, ge=1, le=365),
    current_user: models.User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Get daily aggregated token usage and execution counts."""
    start_date = datetime.utcnow() - timedelta(days=days)

    # Daily stats aggregated by user
    daily_rows = (
        db.query(
            cast(models.Execution.started_at, Date).label("date"),
            models.User.username,
            func.count(models.Execution.id).label("executions"),
            func.coalesce(func.sum(models.Execution.total_tokens), 0).label("tokens"),
        )
        .join(models.Workflow, models.Execution.workflow_id == models.Workflow.id)
        .join(models.User, models.Workflow.owner_id == models.User.id)
        .filter(models.Execution.started_at >= start_date)
        .group_by(cast(models.Execution.started_at, Date), models.User.username)
        .order_by(cast(models.Execution.started_at, Date))
        .all()
    )

    # Organize into daily_stats structure
    daily_map = {}
    for row in daily_rows:
        date_str = row.date.isoformat() if row.date else None
        if date_str not in daily_map:
            daily_map[date_str] = {"date": date_str, "tokens": 0, "executions": 0, "by_user": {}}
        daily_map[date_str]["tokens"] += row.tokens
        daily_map[date_str]["executions"] += row.executions
        daily_map[date_str]["by_user"][row.username] = {
            "tokens": row.tokens,
            "executions": row.executions,
        }

    return {
        "days": days,
        "daily_stats": list(daily_map.values()),
    }


@router.get("/stats/user/{user_id}")
async def get_user_stats(
    user_id: int,
    current_user: models.User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Get detailed stats for a specific user."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get workflows
    workflows = (
        db.query(models.Workflow)
        .filter(models.Workflow.owner_id == user_id)
        .all()
    )

    workflow_stats = []
    for wf in workflows:
        exec_stats = (
            db.query(
                func.count(models.Execution.id),
                func.coalesce(func.sum(models.Execution.total_tokens), 0),
                func.max(models.Execution.started_at),
            )
            .filter(models.Execution.workflow_id == wf.id)
            .first()
        )
        workflow_stats.append({
            "id": wf.id,
            "name": wf.name,
            "is_active": wf.is_active,
            "created_at": wf.created_at.isoformat() if wf.created_at else None,
            "execution_count": exec_stats[0] if exec_stats else 0,
            "total_tokens": exec_stats[1] if exec_stats else 0,
            "last_executed": exec_stats[2].isoformat() if exec_stats and exec_stats[2] else None,
        })

    return {
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
        "workflows": workflow_stats,
    }
```

**Step 2: Register the router in `backend/main.py`**

Add import at the top (after line 21, alongside other router imports):
```python
from admin import router as admin_router
```

Add router registration (after line 93, alongside other `app.include_router` calls):
```python
app.include_router(admin_router, prefix="/admin", tags=["Admin"])
```

**Step 3: Verify**

```bash
curl -H "Authorization: Bearer <admin-token>" http://localhost:9000/admin/stats/overview
```

Expected: JSON with user stats. Non-admin tokens should return 403.

**Step 4: Commit**

```bash
git add backend/admin.py backend/main.py
git commit -m "feat: add admin API endpoints for platform stats"
```

---

### Task 4: Install Recharts + add admin API client

**Files:**
- Modify: `frontend/package.json` (add recharts dependency)
- Modify: `frontend/src/lib/api.ts` (add admin API types and functions)

**Step 1: Install Recharts**

```bash
cd frontend && pnpm add recharts
```

**Step 2: Add admin types and API functions to `frontend/src/lib/api.ts`**

Add these types near the other type definitions (after the `WorkflowStats` interface around line 139):

```typescript
// Admin types
export interface AdminUserStats {
  id: number
  username: string
  email: string
  full_name?: string
  is_active: boolean
  is_admin: boolean
  created_at?: string
  workflow_count: number
  execution_count: number
  total_tokens: number
  total_prompt_tokens: number
  total_completion_tokens: number
  last_active?: string
}

export interface AdminOverview {
  total_users: number
  total_workflows: number
  total_executions: number
  total_tokens: number
  total_prompt_tokens: number
  total_completion_tokens: number
  users: AdminUserStats[]
}

export interface DailyUserStats {
  tokens: number
  executions: number
}

export interface DailyStat {
  date: string
  tokens: number
  executions: number
  by_user: Record<string, DailyUserStats>
}

export interface UsageOverTime {
  days: number
  daily_stats: DailyStat[]
}

export interface AdminUserDetail {
  user: {
    id: number
    username: string
    email: string
    full_name?: string
    is_active: boolean
    created_at?: string
  }
  workflows: Array<{
    id: number
    name: string
    is_active: boolean
    created_at?: string
    execution_count: number
    total_tokens: number
    last_executed?: string
  }>
}
```

Add admin API functions at the end of the file (before `export default api`):

```typescript
// Admin API
export const adminApi = {
  getOverview: () =>
    api.get<AdminOverview>('/admin/stats/overview'),

  getUsageOverTime: (days = 30) =>
    api.get<UsageOverTime>('/admin/stats/usage-over-time', {
      params: { days },
    }),

  getUserDetail: (userId: number) =>
    api.get<AdminUserDetail>(`/admin/stats/user/${userId}`),
}
```

**Step 3: Commit**

```bash
git add frontend/package.json frontend/pnpm-lock.yaml frontend/src/lib/api.ts
git commit -m "feat: add recharts dependency and admin API client"
```

---

### Task 5: Create AdminPage with Overview tab

**Files:**
- Create: `frontend/src/pages/AdminPage.tsx`

**Step 1: Create the admin page**

```tsx
import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Users,
  Workflow,
  Zap,
  Coins,
  ArrowUpDown,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import { adminApi, AdminUserStats } from '@/lib/api'

type SortField = 'username' | 'workflow_count' | 'execution_count' | 'total_tokens' | 'last_active'
type SortDir = 'asc' | 'desc'
type Tab = 'overview' | 'usage'

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}

function formatDate(iso?: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

function formatShortDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

// Color palette for user lines in charts
const USER_COLORS = [
  '#f97316', '#3b82f6', '#10b981', '#8b5cf6', '#ef4444',
  '#06b6d4', '#f59e0b', '#ec4899', '#14b8a6', '#6366f1',
]

export default function AdminPage() {
  const [tab, setTab] = useState<Tab>('overview')
  const [sortField, setSortField] = useState<SortField>('total_tokens')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [days, setDays] = useState(30)

  const { data: overview, isLoading: overviewLoading } = useQuery({
    queryKey: ['admin', 'overview'],
    queryFn: () => adminApi.getOverview().then((r) => r.data),
  })

  const { data: usage, isLoading: usageLoading } = useQuery({
    queryKey: ['admin', 'usage', days],
    queryFn: () => adminApi.getUsageOverTime(days).then((r) => r.data),
    enabled: tab === 'usage',
  })

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      setSortDir('desc')
    }
  }

  const sortedUsers = React.useMemo(() => {
    if (!overview?.users) return []
    return [...overview.users].sort((a, b) => {
      let aVal: any = a[sortField]
      let bVal: any = b[sortField]
      if (sortField === 'last_active') {
        aVal = aVal ? new Date(aVal).getTime() : 0
        bVal = bVal ? new Date(bVal).getTime() : 0
      }
      if (typeof aVal === 'string') aVal = aVal.toLowerCase()
      if (typeof bVal === 'string') bVal = bVal.toLowerCase()
      if (aVal < bVal) return sortDir === 'asc' ? -1 : 1
      if (aVal > bVal) return sortDir === 'asc' ? 1 : -1
      return 0
    })
  }, [overview?.users, sortField, sortDir])

  // Prepare chart data from usage
  const chartData = React.useMemo(() => {
    if (!usage?.daily_stats) return []
    return usage.daily_stats.map((d) => ({
      date: formatShortDate(d.date),
      tokens: d.tokens,
      executions: d.executions,
      ...Object.fromEntries(
        Object.entries(d.by_user).map(([user, stats]) => [`${user}_tokens`, stats.tokens])
      ),
    }))
  }, [usage])

  const usernames = React.useMemo(() => {
    if (!usage?.daily_stats) return []
    const names = new Set<string>()
    usage.daily_stats.forEach((d) =>
      Object.keys(d.by_user).forEach((u) => names.add(u))
    )
    return Array.from(names)
  }, [usage])

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return <ArrowUpDown className="h-3 w-3 ml-1 opacity-40" />
    return sortDir === 'asc' ? (
      <ChevronUp className="h-3 w-3 ml-1" />
    ) : (
      <ChevronDown className="h-3 w-3 ml-1" />
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-scurry-espresso">Admin Portal</h1>
        <p className="text-sm text-scurry-latte mt-1">Platform-wide statistics and user analytics</p>
      </div>

      {/* Tabs */}
      <div className="border-b border-scurry-gray-border">
        <nav className="flex gap-4">
          {[
            { id: 'overview' as Tab, label: 'Overview' },
            { id: 'usage' as Tab, label: 'Usage Over Time' },
          ].map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`pb-3 px-1 text-sm font-medium border-b-2 transition-colors ${
                tab === t.id
                  ? 'border-scurry-orange text-scurry-orange'
                  : 'border-transparent text-scurry-latte hover:text-scurry-espresso'
              }`}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Overview Tab */}
      {tab === 'overview' && (
        <>
          {overviewLoading ? (
            <div className="flex justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-scurry-orange" />
            </div>
          ) : overview ? (
            <>
              {/* Summary Cards */}
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                {[
                  { label: 'Total Users', value: overview.total_users, icon: Users, color: 'text-blue-600 bg-blue-50' },
                  { label: 'Total Workflows', value: overview.total_workflows, icon: Workflow, color: 'text-purple-600 bg-purple-50' },
                  { label: 'Total Executions', value: overview.total_executions, icon: Zap, color: 'text-green-600 bg-green-50' },
                  { label: 'Total Tokens', value: formatTokens(overview.total_tokens), icon: Coins, color: 'text-orange-600 bg-orange-50' },
                ].map((card) => {
                  const Icon = card.icon
                  return (
                    <div key={card.label} className="bg-white rounded-lg border border-scurry-gray-border p-4">
                      <div className="flex items-center gap-3">
                        <div className={`p-2 rounded-lg ${card.color}`}>
                          <Icon className="h-5 w-5" />
                        </div>
                        <div>
                          <p className="text-xs text-scurry-latte">{card.label}</p>
                          <p className="text-xl font-bold text-scurry-espresso">{card.value}</p>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>

              {/* User Stats Table */}
              <div className="bg-white rounded-lg border border-scurry-gray-border overflow-hidden">
                <div className="px-4 py-3 border-b border-scurry-gray-border">
                  <h2 className="text-sm font-semibold text-scurry-espresso">User Breakdown</h2>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-scurry-foam text-left text-xs text-scurry-latte uppercase tracking-wider">
                        {[
                          { field: 'username' as SortField, label: 'User' },
                          { field: 'workflow_count' as SortField, label: 'Workflows' },
                          { field: 'execution_count' as SortField, label: 'Executions' },
                          { field: 'total_tokens' as SortField, label: 'Tokens Used' },
                          { field: 'last_active' as SortField, label: 'Last Active' },
                        ].map((col) => (
                          <th
                            key={col.field}
                            className="px-4 py-3 cursor-pointer hover:bg-scurry-gray-light select-none"
                            onClick={() => toggleSort(col.field)}
                          >
                            <span className="flex items-center">
                              {col.label}
                              <SortIcon field={col.field} />
                            </span>
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-scurry-gray-border">
                      {sortedUsers.map((user) => (
                        <tr key={user.id} className="hover:bg-scurry-foam/50">
                          <td className="px-4 py-3">
                            <div>
                              <span className="font-medium text-scurry-espresso">{user.username}</span>
                              {user.is_admin && (
                                <span className="ml-2 text-[10px] bg-scurry-orange text-white px-1.5 py-0.5 rounded-full font-medium">
                                  Admin
                                </span>
                              )}
                            </div>
                            <span className="text-xs text-scurry-gray-muted">{user.email}</span>
                          </td>
                          <td className="px-4 py-3 text-scurry-espresso">{user.workflow_count}</td>
                          <td className="px-4 py-3 text-scurry-espresso">{user.execution_count}</td>
                          <td className="px-4 py-3">
                            <span className="font-medium text-scurry-espresso">{formatTokens(user.total_tokens)}</span>
                            <div className="text-[10px] text-scurry-gray-muted">
                              {formatTokens(user.total_prompt_tokens)} in / {formatTokens(user.total_completion_tokens)} out
                            </div>
                          </td>
                          <td className="px-4 py-3 text-scurry-latte">{formatDate(user.last_active)}</td>
                        </tr>
                      ))}
                      {sortedUsers.length === 0 && (
                        <tr>
                          <td colSpan={5} className="px-4 py-8 text-center text-scurry-gray-muted">
                            No users found
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          ) : null}
        </>
      )}

      {/* Usage Over Time Tab */}
      {tab === 'usage' && (
        <>
          {/* Time range selector */}
          <div className="flex gap-2">
            {[
              { label: '7 days', value: 7 },
              { label: '30 days', value: 30 },
              { label: '90 days', value: 90 },
            ].map((opt) => (
              <button
                key={opt.value}
                onClick={() => setDays(opt.value)}
                className={`px-3 py-1.5 text-sm rounded-md border transition-colors ${
                  days === opt.value
                    ? 'bg-scurry-orange text-white border-scurry-orange'
                    : 'bg-white text-scurry-latte border-scurry-gray-border hover:border-scurry-orange'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>

          {usageLoading ? (
            <div className="flex justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-scurry-orange" />
            </div>
          ) : chartData.length > 0 ? (
            <>
              {/* Token Usage Chart */}
              <div className="bg-white rounded-lg border border-scurry-gray-border p-4">
                <h3 className="text-sm font-semibold text-scurry-espresso mb-4">Daily Token Usage</h3>
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                    <YAxis tick={{ fontSize: 12 }} tickFormatter={formatTokens} />
                    <Tooltip formatter={(value: number) => formatTokens(value)} />
                    <Legend />
                    {usernames.map((username, i) => (
                      <Line
                        key={username}
                        type="monotone"
                        dataKey={`${username}_tokens`}
                        name={username}
                        stroke={USER_COLORS[i % USER_COLORS.length]}
                        strokeWidth={2}
                        dot={false}
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </div>

              {/* Execution Count Chart */}
              <div className="bg-white rounded-lg border border-scurry-gray-border p-4">
                <h3 className="text-sm font-semibold text-scurry-espresso mb-4">Daily Executions</h3>
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                    <YAxis tick={{ fontSize: 12 }} />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="executions" name="Executions" fill="#f97316" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </>
          ) : (
            <div className="bg-white rounded-lg border border-scurry-gray-border p-8 text-center text-scurry-gray-muted">
              No usage data for the selected period
            </div>
          )}
        </>
      )}
    </div>
  )
}
```

**Step 2: Commit**

```bash
git add frontend/src/pages/AdminPage.tsx
git commit -m "feat: create AdminPage with overview and usage charts"
```

---

### Task 6: Add admin route and nav link

**Files:**
- Modify: `frontend/src/App.tsx:12-19,86-163` (add import, route, AdminRoute guard)
- Modify: `frontend/src/components/Layout.tsx:4,9,28-53` (add Shield icon import, admin nav item)

**Step 1: Update `frontend/src/App.tsx`**

Add import alongside other page imports (around line 19):
```typescript
import AdminPage from '@/pages/AdminPage'
```

Add an `AdminRoute` component after the existing `PublicRoute` component (after line 75):
```tsx
// Admin Route component
const AdminRoute: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const { user, loading } = useAuth()

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <LoadingSpinner />
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/login" replace />
  }

  if (!user.is_admin) {
    return <Navigate to="/dashboard" replace />
  }

  return <>{children}</>
}
```

Add admin route inside `<Routes>` after the `/emails` route (after line 163):
```tsx
<Route
  path="/admin"
  element={
    <AdminRoute>
      <Layout>
        <AdminPage />
      </Layout>
    </AdminRoute>
  }
/>
```

**Step 2: Update `frontend/src/components/Layout.tsx`**

Add `Shield` to the lucide-react import (line 4):
```typescript
import {
  LayoutDashboard,
  Workflow,
  Settings,
  LogOut,
  User,
  Menu,
  X,
  Mail,
  Shield,
} from 'lucide-react'
```

Update the `navigation` array (around line 28) to conditionally include admin:

Replace the entire `const navigation = [...]` block with:
```typescript
const navigation = [
  {
    name: 'Dashboard',
    href: '/dashboard',
    icon: LayoutDashboard,
    current: location.pathname === '/dashboard',
  },
  {
    name: 'Workflows',
    href: '/workflows',
    icon: Workflow,
    current: location.pathname.startsWith('/workflows'),
  },
  {
    name: 'Email Queue',
    href: '/emails',
    icon: Mail,
    current: location.pathname === '/emails',
  },
  {
    name: 'Settings',
    href: '/settings',
    icon: Settings,
    current: location.pathname === '/settings',
  },
  ...(user?.is_admin
    ? [
        {
          name: 'Admin',
          href: '/admin',
          icon: Shield,
          current: location.pathname === '/admin',
        },
      ]
    : []),
]
```

**Step 3: Verify**

Log in as an admin user. The sidebar should show an "Admin" link. Clicking it navigates to `/admin` with stats. Non-admin users should not see the link and be redirected if they manually navigate to `/admin`.

**Step 4: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/Layout.tsx
git commit -m "feat: add admin route with auth guard and sidebar navigation"
```

---

### Task 7: End-to-end verification

**Step 1: Start the app**

```bash
docker compose up -d
cd frontend && pnpm run dev
```

**Step 2: Verify admin flow**

1. Log in as admin user
2. Check sidebar shows "Admin" link
3. Click "Admin" — overview tab loads with summary cards and user table
4. Click column headers — table sorts correctly
5. Switch to "Usage Over Time" tab — charts render
6. Toggle 7d / 30d / 90d — charts update

**Step 3: Verify non-admin flow**

1. Log in as non-admin user (or create one)
2. Check sidebar does NOT show "Admin" link
3. Navigate manually to `/admin` — redirected to `/dashboard`

**Step 4: Verify API protection**

```bash
# With non-admin token:
curl -H "Authorization: Bearer <non-admin-token>" http://localhost:9000/admin/stats/overview
# Expected: 403 Forbidden
```

**Step 5: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix: address admin portal issues from e2e testing"
```
