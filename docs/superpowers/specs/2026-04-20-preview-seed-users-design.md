# Preview Environment Seed Users

## Problem

The preview environment (PR-per-VM via `docker-compose.preview.yml`) boots with an empty database after `python migrate.py` runs. To test the app we must manually register a user every time a preview comes up. We need deterministic seed accounts that exist on every fresh preview boot.

## Goal

On preview boot, automatically create three known users so that anyone testing a PR can log in immediately:

| Email | Password | Role |
|---|---|---|
| `admin@scurry.ai` | `12345678` | Platform superadmin (own org) |
| `org@scurry.ai` | `12345678` | Org owner of the shared preview org |
| `user@scurry.ai` | `12345678` | Regular member of the shared preview org |

## Non-Goals

- No seed workflows, components, contacts, or other domain data
- No API endpoint — script-only invocation
- No Alembic data migration — this must never run in staging/prod
- No UI to manage seed users

## Architecture

### Execution gate

A standalone Python script `backend/seed_preview.py`, invoked from the preview compose `command` between `migrate.py` and `uvicorn`. The script self-gates on `DEPLOYMENT_MODE=preview`: any other value (including unset) causes it to log a skip message and exit 0. This keeps the same image safe to run in dev/prod by accident.

### Idempotency

Seeding runs on every preview boot, so it must be rerunnable without duplicates or errors:

- Each user is looked up by email; if present, left untouched
- The shared org is looked up by a fixed slug `scurry-preview`; created only if missing
- The admin org is looked up by slug `scurry-preview-admin`; created only if missing
- Each org's `Account` is created if missing (lookup via `org_id`)
- The initial `AcornTransaction` is created only when the `Account` is created (not re-granted on reruns)
- Partial-failure recovery: if a prior run created the org but crashed before the user, the next run finds the org and attaches the user to it

Everything happens in a single transaction per user-creation path; commit on success, rollback on error.

### Data created

**Org A — "Scurry Preview (Admin)"** (slug `scurry-preview-admin`, domain `scurry.ai`)
- `Account`: `plan_tier=trialing`, `status=trialing`, `acorn_balance=trial_acorns`, `trial_ends_at=now+trial_days`
- `AcornTransaction`: type `trial_credit`, amount `trial_acorns`, description `"Trial acorns (seed)"`
- `User`: `admin@scurry.ai`, `is_superadmin=True`, `role=owner`, `full_name="Scurry Admin"`, `is_active=True`

**Org B — "Scurry Preview"** (slug `scurry-preview`, domain `scurry.ai`)
- `Account`: same defaults as Org A
- `AcornTransaction`: same shape as Org A
- `User` (owner): `org@scurry.ai`, `is_superadmin=False`, `role=owner`, `full_name="Scurry Org Owner"`, `is_active=True`
- `User` (member): `user@scurry.ai`, `is_superadmin=False`, `role=member`, `full_name="Scurry User"`, `is_active=True`

`trial_acorns` and `trial_days` are read from `system_config` via `get_config_float`/`get_config_int` (defaults 100 and 14 — mirrors the register flow in `auth.py`).

Passwords are hashed with `auth.get_password_hash` (bcrypt via passlib), not hardcoded hashes.

### Logging

The script uses the existing `logging_config` module (or plain `print` if that's heavier than needed) to emit one line per action:

- `"DEPLOYMENT_MODE=<value>, skipping seed"` when not preview
- `"Created org <slug>"` / `"Org <slug> already exists"`
- `"Created user <email>"` / `"User <email> already exists"`
- `"Seed complete"` at the end

### Compose wiring

`docker/docker-compose.preview.yml` backend service `command` changes from:

```yaml
command: sh -c "python migrate.py && uvicorn main:socket_app --host 0.0.0.0 --port 9000"
```

to:

```yaml
command: sh -c "python migrate.py && python seed_preview.py && uvicorn main:socket_app --host 0.0.0.0 --port 9000"
```

Only this compose file is modified. `docker-compose.yml` and `docker-compose.prod.yml` are untouched.

## Failure modes

- **DB unreachable**: `migrate.py` already handles retry-until-ready, so by the time seed runs the DB is up. If it fails anyway, the script exits non-zero and the backend container fails to start — visible in `docker compose logs`.
- **Script crash mid-run**: The transaction for the failing path rolls back; the next preview boot or container restart reruns seed and completes the missing pieces via idempotency lookups.
- **Seed bug in prod**: Blocked by the `DEPLOYMENT_MODE=preview` gate. The gate is the first thing the script checks.

## Testing

Manual verification is sufficient — this is preview-only tooling:

1. Fresh preview boot: check logs for "Created org" / "Created user" lines for all 3 users and 2 orgs
2. Log in to the frontend with each of the 3 accounts; confirm they see expected views (admin sees admin pages; org owner and member see the same shared org data)
3. Restart the backend container and check logs show "already exists" for all 5 records — no duplicates
4. Run the same image locally with `DEPLOYMENT_MODE` unset: seed script logs the skip message and exits 0

No automated tests. The script is small, single-purpose, and its blast radius is bounded by the preview gate.

## Files touched

- `backend/seed_preview.py` — new
- `docker/docker-compose.preview.yml` — one-line `command` change
