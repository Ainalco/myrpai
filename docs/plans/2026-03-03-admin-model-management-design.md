# Admin-Configurable AI Models with Per-Model Cost Tracking

## Problem
Model name is hardcoded in 12 places in ai_service.py. Cost is hardcoded in frontend. No way to switch models or track costs accurately when different models are used over time.

## Design

### Database: `ai_models` table
- `id` Integer PK
- `model_id` String unique — API identifier (e.g. `claude-sonnet-4-5-20250929`)
- `display_name` String — Human-readable (e.g. "Claude Sonnet 4.5")
- `input_cost_per_million` Float — $/M input tokens
- `output_cost_per_million` Float — $/M output tokens
- `is_active` Boolean — Only one active at a time
- `created_at` DateTime

### Backend

**New admin endpoints:**
- `GET /admin/models` — list all models
- `POST /admin/models` — add model
- `PUT /admin/models/{id}` — update model costs/name
- `PUT /admin/models/{id}/activate` — set active (deactivates others)
- `DELETE /admin/models/{id}` — remove (only if not active)

**ai_service.py changes:**
- Replace hardcoded model with `get_active_model()` function
- Cache active model in memory, refresh on change
- All 12 call sites use the cached model_id

**Cost calculation (backend-side):**
- Admin cost endpoints JOIN ai_usage_log.ai_model → ai_models to get per-model pricing
- Cost = (prompt_tokens × input_cost / 1M) + (completion_tokens × output_cost / 1M)
- NULL ai_model entries fall back to active model pricing

### Frontend

**Remove hardcoded cost.ts constants** — keep formatCost() utility, backend provides dollar amounts.

**New "Models" tab on /admin:**
- Table: Name, Model ID, Input $/M, Output $/M, Active badge
- Actions: Add Model dialog, Edit, Set Active, Delete
- Only admin can manage

**Updated admin types** for model CRUD API.

### Cost Flow
AI call → response includes model → ai_usage_log.ai_model recorded
→ Admin queries JOIN with ai_models for accurate historical cost
→ Different models = different costs, all tracked correctly
