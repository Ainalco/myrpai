# AI Response Caching Design

## Problem

Every AI call in the platform hits the Anthropic API, even when the same prompt and data were sent minutes ago. This wastes API credits and adds latency for repeated workflow executions with identical inputs.

## Solution

A caching layer in `ai_service.py` that stores AI responses in Redis, keyed by a hash of the full input. Cached responses are returned directly, bypassing the API call, token accumulation, and usage logging.

## Environment Variable

- **`AI_CACHE_TTL_MINUTES`** — TTL for cached AI responses in minutes. Default: `30`. Read at module level in `ai_service.py` and converted to seconds for Redis.

## Cache Key Format

```
ai_cache:{sha256(prompt + data + model_id)}
```

- `ai_cache:` prefix separates AI cache from existing Fireflies/Pipedrive cache keys
- SHA-256 of the concatenated prompt string, serialized data, and active model ID
- Model ID inclusion ensures cache invalidation on model switch

## Cached Functions

All 7 AI functions in `ai_service.py`:

1. `analyze_with_ai(prompt, data)` — generic AI analysis
2. `extract_key_information(transcript, extraction_points, ...)` — transcript data extraction
3. `extract_and_summarize(transcript, ...)` — combined extraction + summary
4. `generate_email_content(prompt, context, ...)` — email body generation
5. `generate_email_with_metadata(...)` — email with subject/recipients
6. `generate_email_subject(...)` — subject line generation
7. `match_organization_with_ai(...)` — CRM organization matching

## Implementation Approach

A single helper function `_ai_cache_get(cache_input_str)` and `_ai_cache_set(cache_input_str, response)` in `ai_service.py` that:

1. Builds a cache key from `ai_cache:` + SHA-256 of the input string
2. Uses existing `cache_get` / `cache_set` from `cache_service.py`
3. Reads `AI_CACHE_TTL_MINUTES` from environment, defaults to 30, converts to seconds

Each AI function is modified to:
1. Build a canonical string from its inputs (prompt + data + model_id)
2. If `skip_cache` is False: check cache, return on hit
3. Call the Anthropic API on cache miss
4. Store the response in cache (even when `skip_cache` is True — fresh result benefits future calls)

## Skip-Cache Flag

- `skip_cache: bool` parameter added to the execution trigger endpoint `POST /api/executions/`
- Stored on the `Execution` model (new boolean column, default `False`)
- Threaded through `execute_workflow()` → `execute_component()` → AI service functions
- When `True`: skip cache lookup, still write result to cache
- No UI changes required initially — the flag is API-driven

## Token Tracking on Cache Hits

Cache hits must NOT:
- Call `_accumulate_tokens()` — no tokens were consumed
- Log to the `ai_usage_log` table — no API call was made

This keeps cost tracking accurate.

## Graceful Degradation

Follows existing `cache_service.py` pattern:
- If Redis is unavailable, `cache_get` returns `None` and `cache_set` silently fails
- All AI calls proceed normally without caching — no errors, no disruption

## Cache Clearing

- Targeted: `cache_clear_pattern("ai_cache:*")` clears all AI cache
- Natural expiry: entries expire after `AI_CACHE_TTL_MINUTES`
- No admin endpoint needed initially — can use existing `cache_clear_pattern` utility

## Files Modified

1. **`backend/ai_service.py`** — Add cache helpers, modify all 7 AI functions
2. **`backend/executions.py`** — Thread `skip_cache` flag through execution engine
3. **`backend/models.py`** — Add `skip_cache` column to `Execution` model
4. **`backend/executions.py`** (router) — Accept `skip_cache` in execution creation endpoint
5. **`backend/alembic/versions/`** — Migration for new `skip_cache` column
6. **`.env.example` or `CLAUDE.md`** — Document `AI_CACHE_TTL_MINUTES`
