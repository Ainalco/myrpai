# Pipedrive Background Sync Pipeline — Design Spec

**Goal:** Continuously sync Pipedrive persons and deals into the contact system via a background worker, with manual sync endpoints for on-demand use.

**Core Principle:** We only ADD and UPDATE. We never auto-delete contacts or deals. Pipedrive is an enrichment source, not the source of truth.

---

## Architecture

A standalone background worker (`pipedrive_worker.py`) runs every 5 minutes, queries contacts due for sync using smart interval logic, and syncs each one with Pipedrive. The same sync function is callable from manual API endpoints.

### Files

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/alembic/versions/028_add_crm_synced_at.py` | CREATE | Migration: add `crm_synced_at` column to contacts |
| `backend/models.py` | MODIFY | Add `crm_synced_at` to Contact model |
| `backend/pipedrive_sync.py` | CREATE | Shared sync logic (used by worker + endpoints) |
| `backend/pipedrive_worker.py` | CREATE | Standalone background worker process |
| `backend/contacts.py` | MODIFY | Add 2 manual sync endpoints |

---

## Smart Interval Logic

A `crm_synced_at` DateTime column on `contacts` (migration 028) tracks when each contact was last synced.

| Contact state | Sync interval | Reasoning |
|---|---|---|
| Never synced (`crm_synced_at IS NULL`) | Immediate (highest priority) | New contacts need initial linking |
| Has open deals OR `last_activity_at` within 48h | Every 15 minutes | Active prospects — deal stages change fast |
| Everything else | Every 6 hours | Dormant contacts — check periodically |

The worker query sorts by priority: never synced first, then most overdue.

**Batch cap:** 30 contacts per user per cycle (~60 API calls, within Pipedrive's 80 req/2s limit).

---

## Core Sync Function: `sync_contact_pipedrive`

For a single contact:

1. **Person lookup:** Get all emails from `contact_emails`, try each against `find_person_by_email()` from existing `pipedrive_service.py`. First match wins.
2. **If person NOT found:** Set `crm_synced_at = now` (don't re-check every 5 min). Will retry after 6h. Return early.
3. **Link person:** Set `contact.external_person_id = str(pipedrive_person_id)`, `contact.crm_provider = "pipedrive"`.
4. **Link org:** If Pipedrive person has `organization.id`, update our `ContactOrganization.external_org_id` and update the org name to the Pipedrive canonical name (e.g., "Acme Corp" vs auto-generated "Acmecorp").
5. **Fetch deals:** `GET /v1/persons/{person_id}/deals?status=all_not_deleted` — paginated, returns ALL deals.
6. **Resolve stage names:** Call `get_deal_stages(db, user_id)` from existing `pipedrive_service.py` (cached 24h) for stage_id → stage_name mapping.
7. **Upsert deals:** For each Pipedrive deal:
   - Lookup existing `ContactDeal` by `external_deal_id` + `crm_provider="pipedrive"`
   - If **new**: create `ContactDeal`, log `deal_stage_change` activity ("New deal: {title} at {stage}")
   - If **exists and stage changed**: update stage_name, log `deal_stage_change` activity ("{title}: {old_stage} → {new_stage}")
   - If **exists and status changed** (open→won/lost): update status, log `deal_status_change` activity
   - If **unchanged**: touch `updated_at` only
8. **No auto-deletion.** Deals that disappear from Pipedrive are left as-is in our system.
9. **Recompute stats:** Call `update_contact_stats(db, contact_id)` to refresh `open_deals` + `total_deal_value`.
10. **Set `crm_synced_at = now`.**

---

## Worker Architecture: `pipedrive_worker.py`

Follows the same pattern as `email_worker.py`:

- Standalone script with `while True` loop
- Configurable interval: `PIPEDRIVE_SYNC_INTERVAL` env var (default 300 seconds / 5 min)
- Creates its own DB session per cycle
- Per cycle:
  1. Query all users who have an active Pipedrive API key (`api_keys` table, `service_name="pipedrive"`, `is_active=True`)
  2. For each user, call `get_contacts_due_for_sync(db, user_id, limit=30)`
  3. For each contact, call `sync_contact_pipedrive(db, user_id, contact_id)`
  4. Sleep 100ms between contacts for rate limiting
  5. Log summary: "Synced N contacts for user X (Y new deals, Z updated)"
- One contact failure doesn't stop the batch (try/except per contact)

---

## API Endpoints

### `POST /contacts/{contact_id}/sync-crm`

Manual sync single contact. Calls `sync_contact_pipedrive()` directly.

Response:
```json
{
  "success": true,
  "personFound": true,
  "externalPersonId": "12345",
  "dealsTotal": 3,
  "dealsCreated": 2,
  "dealsUpdated": 1,
  "orgLinked": true,
  "orgName": "Acme Corp"
}
```

### `POST /contacts/sync-crm`

Manual trigger full sync cycle for current user. Iterates over all user's contacts due for sync.

Response:
```json
{
  "success": true,
  "contactsSynced": 15,
  "personsFound": 12,
  "dealsCreated": 8,
  "dealsUpdated": 3
}
```

**Route ordering:** Both endpoints must be defined BEFORE `/{contact_id}` routes in the router. `sync-crm` is a string that can't parse as int, but this follows the established `/export` pattern for safety.

---

## Error Handling

| Scenario | Behavior |
|---|---|
| No Pipedrive API key for user | Worker skips user. Manual endpoint returns `{"success": false, "error": "Pipedrive API key not configured"}` |
| Person not found | Set `crm_synced_at = now`. Retry after 6h. Not an error. |
| API rate limit (HTTP 429) | Worker sleeps 30s, then resumes with next contact |
| API error (HTTP 5xx) | Log error, skip contact, continue batch |
| Single contact sync failure | Log error, continue with next contact. Never crash the worker. |
| Pipedrive key revoked/invalid | Log error, skip all contacts for that user this cycle |

---

## Existing Functions Reused

From `backend/pipedrive_service.py` (no modifications needed):
- `get_pipedrive_api_key(db, user_id)` — retrieve decrypted API token
- `find_person_by_email(db, user_id, email)` — search Pipedrive for person
- `get_deal_stages(db, user_id)` — cached stage_id → stage_name mapping
- `get_enriched_deal_data(db, user_id, deal)` — adds stage_name to deal dict

From `backend/contacts_service.py` (no modifications needed):
- `log_activity(db, user_id, contact_id, ...)` — log timeline events
- `update_contact_stats(db, contact_id)` — recompute deal counts

---

## Data Never Deleted

- **Contacts** are never deleted by the sync. They are created by the workflow engine and belong to us.
- **Deals** are never auto-deleted. If a deal disappears from Pipedrive (deleted, moved to another person, API issue), our `ContactDeal` record stays as-is.
- **Organizations** are never deleted by the sync. Only enriched (name update, external_org_id linking).
