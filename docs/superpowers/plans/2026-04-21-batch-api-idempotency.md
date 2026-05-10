# Anthropic Batch API — idempotent submit design

**Status:** design-only. Owner: Sarat (branch `91-rag-wire-batch-api-...`).
**Context:** the previous batch worker was scaffolded in migration 035 and
deleted in commit 2e73d18 / migration 037 because it was never wired up. This
note captures the correctness contract the replacement worker must satisfy,
so it isn't rediscovered after a prod incident.

## The failure mode

A naive submit loop:

```python
for row in pending_rows:
    batch_id = submit_batch(prompts)   # network call to Anthropic
    row.batch_id = batch_id
    row.status = "submitted"
db.commit()                            # single commit at the end
```

If the worker dies between `submit_batch()` returning and `db.commit()`
landing — SIGKILL, OOM, container restart, DB failover — Anthropic has
already accepted the batch and will charge for it, but Postgres still shows
the rows as `pending_submit`. On worker restart the next poll re-selects the
same rows and resubmits. Result: double Anthropic cost and, once both batches
complete, double-sent emails.

There is no server-side dedup for us either, because the current scaffolding
sent neither an idempotency key nor a deterministic `custom_id`.

## Required contract

### 1. Two-phase write around every network call

Before `submit_batch`:

```python
idempotency_key = sha256(f"{row.id}:{row.prompt_hash}").hexdigest()
row.status = "submitting"
row.idempotency_key = idempotency_key
db.commit()                            # phase 1 — durable before the call
```

Then call Anthropic. After the call returns successfully:

```python
row.batch_id = batch_id
row.status = "submitted"
row.batch_submitted_at = now
db.commit()                            # phase 2
```

This turns the crash window from "any point between submit and commit" into
"the interval the request is actually in flight with Anthropic," and makes
every row in `submitting` a known-ambiguous state that reconciliation
resolves deterministically.

### 2. Deterministic `custom_id` per request

Every request inside the batch body must carry:

```
custom_id = f"email_queue:{row.id}:{row.prompt_hash[:8]}"
```

`custom_id` is echoed back by Anthropic on every result, so we can reconcile
results to `email_queue.id` without trusting our own `batch_id` column. This
also means a duplicate batch submission is recoverable: if we find the
`custom_id` in a batch we didn't record, we adopt it rather than resubmitting.

### 3. Startup reconciliation before any resubmit

On worker startup, for every row with `status="submitting"`:

1. Query the Anthropic batch-list endpoint and enumerate batches created in
   the last N hours (bounded by our retention window — 24h is safe).
2. For each batch, fetch the request manifest and match on `custom_id`.
3. If a match is found:
   - If the batch is in progress: adopt the `batch_id`, transition to
     `submitted`, let the normal poll loop handle it.
   - If the batch is complete: move the row to `submitted` and immediately
     ingest the result.
4. Only if no batch on Anthropic's side contains our `custom_id` may the
   worker resubmit.

Reconciliation runs **before** the submit loop on every startup, not just
the first one after a crash — this makes recovery the normal path rather
than a special case.

### 4. Schema additions (reintroduce in Sarat's migration)

Migration 037 dropped these; they need to come back, plus one new column:

| column | type | purpose |
| --- | --- | --- |
| `batch_id` | `varchar(255)` | Anthropic-assigned batch id, nullable until submitted |
| `batch_status` | `varchar(32)` | mirrors Anthropic states (in_progress, ended, canceled, expired) |
| `batch_submitted_at` | `timestamptz` | phase-2 write timestamp |
| `batch_request_payload` | `jsonb` | persisted for reconciliation + replay |
| `idempotency_key` | `varchar(64)` | sha256 hex, **UNIQUE** so a duplicate submit is a DB-level error, not a silent dupe |

And one new enum value on `email_queue.status`: `submitting`.

Indexes: `(status)` already exists; add `(idempotency_key)` UNIQUE and
`(batch_id)` for reconciliation lookups.

### 5. Test requirements

The PR must ship with at least these integration tests, using a mock
Anthropic client:

1. **Crash after submit, before phase-2 commit**: mock returns a `batch_id`,
   then the test raises `KeyboardInterrupt` before phase-2. Restart the
   worker. Assert: Anthropic is not called a second time for the same rows,
   and the rows transition to `submitted` via reconciliation.
2. **Duplicate submit attempt**: two worker instances race on the same row.
   Assert: the `idempotency_key` UNIQUE constraint forces one to lose; the
   loser reconciles instead of submitting.
3. **Reconciliation with partial batch results**: pre-populate Anthropic
   mock with a completed batch containing the row's `custom_id`. Assert: row
   jumps from `submitting` straight to `submitted` + result ingested without
   a new submit.

## Out of scope

- Retry/backoff policy for 5xx from Anthropic — orthogonal, handle
  separately.
- Priority / tier routing across batches — orthogonal.
- Cost accounting for reconciled batches — existing billable-cost path
  handles it once `batch_id` is attached.

## Cross-refs

- Deleted worker: commit `2e73d18` (removed `backend/batch_worker.py`,
  219 LOC).
- Schema cleanup: `backend/alembic/versions/037_drop_batch_columns.py`.
- Original scaffolding: `backend/alembic/versions/035_rag_tuning_and_batch_worker.py`
  (later trimmed — the batch-column creation was already removed).
