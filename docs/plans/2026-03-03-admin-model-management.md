# Admin-Configurable AI Models Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow admins to manage AI models (add/edit/delete/activate) from the admin page, replace hardcoded model in ai_service.py, and calculate costs accurately per-model using historical data.

**Architecture:** New `ai_models` DB table stores model definitions with pricing. Backend reads active model for AI calls and joins ai_usage_log with ai_models for cost calculations. Frontend gets a new "Models" tab on the admin page and cost.ts fetches model pricing from the API instead of hardcoding.

**Tech Stack:** SQLAlchemy, Alembic, FastAPI, React, TypeScript, Tailwind

---

### Task 1: Database — Add AiModel model and migration

**Files:**
- Modify: `backend/models.py` (add AiModel class after AiUsageLog)
- Create: `backend/alembic/versions/018_add_ai_models.py`

**Step 1: Add AiModel to models.py**

After the `AiUsageLog` class (around line 436), add:

```python
class AiModel(Base):
    """Admin-configurable AI models with pricing."""
    __tablename__ = "ai_models"

    id = Column(Integer, primary_key=True, index=True)
    model_id = Column(String, unique=True, nullable=False)  # API identifier e.g. "claude-sonnet-4-5-20250929"
    display_name = Column(String, nullable=False)  # Human-readable e.g. "Claude Sonnet 4.5"
    input_cost_per_million = Column(Float, nullable=False)  # $/M input tokens
    output_cost_per_million = Column(Float, nullable=False)  # $/M output tokens
    is_active = Column(Boolean, default=False)  # Only one active at a time
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

**Step 2: Create migration**

Run: `cd /home/tauhid/code/aibot2/backend && alembic revision --autogenerate -m "add_ai_models"`

Verify the generated migration creates the `ai_models` table with a unique constraint on `model_id`.

**Step 3: Apply migration**

Run: `cd /home/tauhid/code/aibot2/backend && python migrate.py`

**Step 4: Seed default model**

Create a one-time seed in the migration's `upgrade()` or via a manual SQL insert. Add to the migration's upgrade function after the table creation:

```python
# Seed the current default model
op.execute("""
    INSERT INTO ai_models (model_id, display_name, input_cost_per_million, output_cost_per_million, is_active)
    VALUES ('claude-sonnet-4-5-20250929', 'Claude Sonnet 4.5', 3.0, 15.0, true)
""")
```

**Step 5: Verify**

Run: `cd /home/tauhid/code/aibot2/backend && python -c "import ast; ast.parse(open('models.py').read()); print('OK')"`

**Step 6: Commit**

```bash
git add backend/models.py backend/alembic/versions/018_add_ai_models.py
git commit -m "feat: add ai_models table with pricing and seed default model"
```

---

### Task 2: Backend — Model CRUD endpoints in admin.py

**Files:**
- Modify: `backend/admin.py` (add 5 new endpoints)

**Step 1: Add model endpoints**

At the end of `backend/admin.py`, add these endpoints:

```python
# --- Model Management ---

@router.get("/models")
async def list_models(
    current_user: models.User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """List all AI models."""
    all_models = db.query(models.AiModel).order_by(models.AiModel.created_at.desc()).all()
    return [
        {
            "id": m.id,
            "model_id": m.model_id,
            "display_name": m.display_name,
            "input_cost_per_million": m.input_cost_per_million,
            "output_cost_per_million": m.output_cost_per_million,
            "is_active": m.is_active,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in all_models
    ]


@router.post("/models", status_code=201)
async def create_model(
    body: dict,
    current_user: models.User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Add a new AI model."""
    existing = db.query(models.AiModel).filter(models.AiModel.model_id == body["model_id"]).first()
    if existing:
        raise HTTPException(status_code=400, detail="Model ID already exists")

    model = models.AiModel(
        model_id=body["model_id"],
        display_name=body["display_name"],
        input_cost_per_million=body["input_cost_per_million"],
        output_cost_per_million=body["output_cost_per_million"],
        is_active=False,
    )
    db.add(model)
    db.commit()
    db.refresh(model)
    return {
        "id": model.id,
        "model_id": model.model_id,
        "display_name": model.display_name,
        "input_cost_per_million": model.input_cost_per_million,
        "output_cost_per_million": model.output_cost_per_million,
        "is_active": model.is_active,
        "created_at": model.created_at.isoformat() if model.created_at else None,
    }


@router.put("/models/{model_db_id}")
async def update_model(
    model_db_id: int,
    body: dict,
    current_user: models.User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Update a model's display name or pricing."""
    model = db.query(models.AiModel).filter(models.AiModel.id == model_db_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    if "display_name" in body:
        model.display_name = body["display_name"]
    if "input_cost_per_million" in body:
        model.input_cost_per_million = body["input_cost_per_million"]
    if "output_cost_per_million" in body:
        model.output_cost_per_million = body["output_cost_per_million"]

    db.commit()
    db.refresh(model)
    return {
        "id": model.id,
        "model_id": model.model_id,
        "display_name": model.display_name,
        "input_cost_per_million": model.input_cost_per_million,
        "output_cost_per_million": model.output_cost_per_million,
        "is_active": model.is_active,
        "created_at": model.created_at.isoformat() if model.created_at else None,
    }


@router.put("/models/{model_db_id}/activate")
async def activate_model(
    model_db_id: int,
    current_user: models.User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Set a model as the active model. Deactivates all others."""
    model = db.query(models.AiModel).filter(models.AiModel.id == model_db_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    # Deactivate all models
    db.query(models.AiModel).update({"is_active": False})
    # Activate the selected one
    model.is_active = True
    db.commit()

    # Clear the cached model in ai_service
    from ai_service import clear_model_cache
    clear_model_cache()

    return {"message": f"Model '{model.display_name}' is now active", "model_id": model.model_id}


@router.delete("/models/{model_db_id}")
async def delete_model(
    model_db_id: int,
    current_user: models.User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Delete a model. Cannot delete the active model."""
    model = db.query(models.AiModel).filter(models.AiModel.id == model_db_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    if model.is_active:
        raise HTTPException(status_code=400, detail="Cannot delete the active model")

    db.delete(model)
    db.commit()
    return {"message": "Model deleted"}
```

**Step 2: Verify**

Run: `cd /home/tauhid/code/aibot2/backend && python -c "import ast; ast.parse(open('admin.py').read()); print('OK')"`

**Step 3: Commit**

```bash
git add backend/admin.py
git commit -m "feat(admin): add model CRUD endpoints"
```

---

### Task 3: Backend — Replace hardcoded model in ai_service.py

**Files:**
- Modify: `backend/ai_service.py` (lines 179, 302, 394, 538, 690, 889, 1064, 1241, 1395, 1569, 1706, 1921)

**Step 1: Add get_active_model() function and cache**

Near the top of `backend/ai_service.py` (after the contextvars section, around line 22), add:

```python
# Cached active model
_cached_model_id: Optional[str] = None

def get_active_model() -> str:
    """Get the currently active AI model ID. Cached in memory, falls back to default."""
    global _cached_model_id
    if _cached_model_id is not None:
        return _cached_model_id
    try:
        from database import SessionLocal
        import models as _models
        db = SessionLocal()
        try:
            active = db.query(_models.AiModel).filter(_models.AiModel.is_active == True).first()
            if active:
                _cached_model_id = active.model_id
                return _cached_model_id
        finally:
            db.close()
    except Exception:
        pass
    return "claude-sonnet-4-5-20250929"  # fallback default

def clear_model_cache():
    """Clear the cached model so next call re-reads from DB."""
    global _cached_model_id
    _cached_model_id = None
```

**Step 2: Replace all 12 hardcoded model references**

Replace every occurrence of `"claude-sonnet-4-5-20250929"` with `get_active_model()`.

For lines where it's in a dict literal like `"model": "claude-sonnet-4-5-20250929"`, change to `"model": get_active_model()`.

For line 394 where it's in metadata like `"model_used": "claude-sonnet-4-5-20250929"`, change to `"model_used": get_active_model()`.

All 12 locations: lines 179, 302, 394, 538, 690, 889, 1064, 1241, 1395, 1569, 1706, 1921.

**Step 3: Verify**

Run: `cd /home/tauhid/code/aibot2/backend && python -c "import ast; ast.parse(open('ai_service.py').read()); print('OK')"`

Verify no hardcoded references remain:
Run: `grep -n "claude-sonnet-4-5-20250929" backend/ai_service.py`
Expected: No output (or only in comments/fallback)

**Step 4: Commit**

```bash
git add backend/ai_service.py
git commit -m "feat: replace hardcoded model with get_active_model() in ai_service"
```

---

### Task 4: Backend — Add cost calculation to admin endpoints

**Files:**
- Modify: `backend/admin.py` (all 3 stats endpoints)

**Step 1: Add a helper function for cost calculation**

At the top of `backend/admin.py` (after imports), add a helper that loads model pricing from the DB:

```python
def _get_model_pricing(db: Session) -> dict:
    """Load all model pricing as {model_id: (input_cost, output_cost)}. Returns dict."""
    all_models = db.query(models.AiModel).all()
    pricing = {}
    active_pricing = (3.0, 15.0)  # fallback
    for m in all_models:
        pricing[m.model_id] = (m.input_cost_per_million, m.output_cost_per_million)
        if m.is_active:
            active_pricing = (m.input_cost_per_million, m.output_cost_per_million)
    pricing["__default__"] = active_pricing
    return pricing

def _calculate_cost(prompt_tokens: int, completion_tokens: int, model_id: str, pricing: dict) -> float:
    """Calculate cost in dollars using model-specific pricing."""
    costs = pricing.get(model_id, pricing.get("__default__", (3.0, 15.0)))
    return (prompt_tokens * costs[0] / 1_000_000) + (completion_tokens * costs[1] / 1_000_000)
```

**Step 2: Update `/stats/overview` endpoint**

In the overview endpoint, after computing per-user token totals, also compute per-user cost. The endpoint already returns `total_prompt_tokens` and `total_completion_tokens` per user. Add cost calculation:

- Load pricing at start: `pricing = _get_model_pricing(db)`
- For total cost: query ai_usage_log grouped by model, then sum costs per model
- Add `total_cost` to the overview response and `cost` to each user object

To calculate total_cost accurately per model, add this query:

```python
# Cost by model for all users
model_usage = (
    db.query(
        models.AiUsageLog.user_id,
        models.AiUsageLog.ai_model,
        func.coalesce(func.sum(models.AiUsageLog.prompt_tokens), 0).label("prompt"),
        func.coalesce(func.sum(models.AiUsageLog.completion_tokens), 0).label("completion"),
    )
    .group_by(models.AiUsageLog.user_id, models.AiUsageLog.ai_model)
    .all()
)

# Build per-user cost map
user_cost_map = {}
total_cost = 0.0
for row in model_usage:
    cost = _calculate_cost(row.prompt, row.completion, row.ai_model or "", pricing)
    user_cost_map[row.user_id] = user_cost_map.get(row.user_id, 0.0) + cost
    total_cost += cost
```

Then add `"total_cost": total_cost` to the response and `"cost": user_cost_map.get(user.id, 0.0)` to each user dict.

**Step 3: Update `/stats/usage-over-time` endpoint**

Add model-aware cost to daily stats. The usage_rows query already groups by date and username. Extend it to also group by ai_model, then calculate cost per group:

Change the main query to also select `models.AiUsageLog.ai_model` and group by it. Then when building daily_map, calculate cost per entry and accumulate.

Add `"cost"` field to each daily stat and per-user daily stat.

**Step 4: Update `/stats/user/{user_id}` endpoint**

Add `"cost"` field to usage_by_source breakdown and calculate total_cost from ai_usage_log grouped by model:

```python
# Total cost from ai_usage_log grouped by model
user_model_usage = (
    db.query(
        models.AiUsageLog.ai_model,
        func.coalesce(func.sum(models.AiUsageLog.prompt_tokens), 0).label("prompt"),
        func.coalesce(func.sum(models.AiUsageLog.completion_tokens), 0).label("completion"),
    )
    .filter(models.AiUsageLog.user_id == user_id)
    .group_by(models.AiUsageLog.ai_model)
    .all()
)
total_cost = sum(_calculate_cost(r.prompt, r.completion, r.ai_model or "", pricing) for r in user_model_usage)
```

Add `"total_cost": total_cost` to the response.

**Step 5: Verify**

Run: `cd /home/tauhid/code/aibot2/backend && python -c "import ast; ast.parse(open('admin.py').read()); print('OK')"`

**Step 6: Commit**

```bash
git add backend/admin.py
git commit -m "feat(admin): add per-model cost calculation to all stats endpoints"
```

---

### Task 5: Frontend — Update cost.ts, API types, and adminApi

**Files:**
- Modify: `frontend/src/lib/cost.ts`
- Modify: `frontend/src/lib/api.ts` (types + adminApi)

**Step 1: Update cost.ts**

Remove the hardcoded cost constants. Keep only `formatCost()`:

```typescript
export function formatCost(dollars: number): string {
  if (dollars >= 1) return `$${dollars.toFixed(2)}`
  if (dollars >= 0.01) return `$${dollars.toFixed(2)}`
  if (dollars > 0) return `$${dollars.toFixed(4)}`
  return '$0.00'
}
```

Remove `calculateCost()` and the constants — cost now comes from the backend.

**Step 2: Add model types to api.ts**

After the existing admin types, add:

```typescript
export interface AiModel {
  id: number
  model_id: string
  display_name: string
  input_cost_per_million: number
  output_cost_per_million: number
  is_active: boolean
  created_at: string | null
}
```

**Step 3: Add model methods to adminApi**

Extend the `adminApi` object:

```typescript
// Add to adminApi:
getModels: () =>
  api.get<AiModel[]>('/admin/models'),

createModel: (data: { model_id: string; display_name: string; input_cost_per_million: number; output_cost_per_million: number }) =>
  api.post<AiModel>('/admin/models', data),

updateModel: (id: number, data: Partial<{ display_name: string; input_cost_per_million: number; output_cost_per_million: number }>) =>
  api.put<AiModel>(`/admin/models/${id}`, data),

activateModel: (id: number) =>
  api.put<{ message: string; model_id: string }>(`/admin/models/${id}/activate`),

deleteModel: (id: number) =>
  api.delete(`/admin/models/${id}`),
```

**Step 4: Update AdminOverview and AdminUserDetail types**

Add `total_cost: number` to `AdminOverview` interface.
Add `cost: number` to `AdminUserStats` interface.
Add `total_cost: number` to `AdminUserDetail` interface.
Add `cost: number` to `DailyStat` and `DailyUserStats` interfaces.

**Step 5: Fix all frontend files that import calculateCost**

Search for `calculateCost` imports in:
- `AdminPage.tsx` — replace with backend-provided `cost` field
- `AdminUserPage.tsx` — replace with backend-provided `total_cost` field
- `AdminUsagePage.tsx` — replace with backend-provided `cost` field

For each file, remove the `calculateCost` import and use the cost values directly from the API response.

**Step 6: Verify**

Run: `cd /home/tauhid/code/aibot2/frontend && npx tsc --noEmit 2>&1 | grep -i "cost\|admin\|model" | head -20`

**Step 7: Commit**

```bash
git add frontend/src/lib/cost.ts frontend/src/lib/api.ts frontend/src/pages/AdminPage.tsx frontend/src/pages/AdminUserPage.tsx frontend/src/pages/AdminUsagePage.tsx
git commit -m "feat(admin): update frontend types and remove hardcoded cost calculation"
```

---

### Task 6: Frontend — Create AdminModelsTab component

**Files:**
- Create: `frontend/src/pages/AdminModelsPage.tsx`

**Step 1: Create the Models management page**

This page at `/admin/models` shows:

1. **Sub-nav**: "Overview" | "Usage & Cost" | "Models" (active)
2. **"Add Model" button** (top right) — opens a dialog/modal
3. **Models table**: Display Name, Model ID, Input $/M, Output $/M, Status (Active badge), Actions (Edit, Activate, Delete)
4. **Add/Edit dialog**: Form with fields for display_name, model_id, input_cost_per_million, output_cost_per_million

Use:
- `useQuery` with `adminApi.getModels()`
- `useMutation` with `adminApi.createModel()`, `updateModel()`, `activateModel()`, `deleteModel()`
- `queryClient.invalidateQueries({ queryKey: ['admin', 'models'] })` after mutations
- Scurry design system colors
- Simple `useState`-based dialog (not a separate component)

Active model row should have a green "Active" badge. Other rows have a "Set Active" button.
Delete button should be disabled/hidden for the active model.

The sub-nav should match the pattern from AdminPage.tsx (Links with border-b-2 styling).

**Step 2: Verify**

Run: `cd /home/tauhid/code/aibot2/frontend && npx tsc --noEmit 2>&1 | grep -i "AdminModels" | head -10`

**Step 3: Commit**

```bash
git add frontend/src/pages/AdminModelsPage.tsx
git commit -m "feat(admin): add models management page"
```

---

### Task 7: Frontend — Add Models route and nav tab

**Files:**
- Modify: `frontend/src/App.tsx` (add import + route)
- Modify: `frontend/src/pages/AdminPage.tsx` (add Models link to sub-nav)
- Modify: `frontend/src/pages/AdminUsagePage.tsx` (add Models link to sub-nav)

**Step 1: Add route in App.tsx**

Import `AdminModelsPage` and add route:

```tsx
import AdminModelsPage from '@/pages/AdminModelsPage'

// Add after other admin routes:
<Route
  path="/admin/models"
  element={
    <AdminRoute>
      <Layout>
        <AdminModelsPage />
      </Layout>
    </AdminRoute>
  }
/>
```

**Step 2: Add "Models" link to AdminPage.tsx sub-nav (lines 114-129)**

Add a third Link after "Usage & Cost":

```tsx
<Link
  to="/admin/models"
  className="pb-3 px-1 text-sm font-medium border-b-2 transition-colors border-transparent text-scurry-latte hover:text-scurry-espresso"
>
  Models
</Link>
```

**Step 3: Add "Models" link to AdminUsagePage.tsx sub-nav**

Same as above — add the Models link to its sub-nav.

**Step 4: Verify**

Run: `cd /home/tauhid/code/aibot2/frontend && npx tsc --noEmit 2>&1 | grep -i "admin\|model" | head -10`

**Step 5: Commit**

```bash
git add frontend/src/App.tsx frontend/src/pages/AdminPage.tsx frontend/src/pages/AdminUsagePage.tsx
git commit -m "feat(admin): add models route and nav links"
```

---

### Task 8: Verify everything end-to-end

**Step 1: Apply migration in Docker**

Run: `docker compose exec backend python migrate.py`

**Step 2: Restart backend**

Run: `docker compose restart backend`

**Step 3: Check backend health**

Run: `curl -s http://localhost:9000/health`

**Step 4: Check frontend compiles**

Run: `cd /home/tauhid/code/aibot2/frontend && npx tsc --noEmit 2>&1 | grep -i "error" | grep -i "admin\|model\|cost" | head -10`
Expected: No errors

**Step 5: Visual verification**

- Navigate to `/admin` — should show cost from backend (not hardcoded)
- Click "Models" tab — should show the default "Claude Sonnet 4.5" model as active
- Add a new model (e.g. "Claude Opus 4.6", model_id: "claude-opus-4-6-20250929", input: $15, output: $75)
- Set it as active — verify the active badge moves
- Check that cost calculations on Overview and Usage pages still work

**Step 6: Final commit**

```bash
git add -A
git commit -m "feat(admin): complete model management with per-model cost tracking"
```
