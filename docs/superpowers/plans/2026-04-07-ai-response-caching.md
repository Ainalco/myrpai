# AI Response Caching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cache all AI (Anthropic API) responses in Redis so identical inputs within a configurable TTL window return cached results without hitting the API.

**Architecture:** Two helper functions (`_ai_cache_key` and the existing `cache_get`/`cache_set`) wrap every Anthropic API call in `ai_service.py`. A `skip_cache` flag on `ExecutionCreate` flows through `execute_workflow_background` into `input_data["__skip_cache__"]`, where each AI function reads it. A new `AI_CACHE_TTL_MINUTES` env var controls TTL.

**Tech Stack:** Python, Redis (existing `cache_service.py`), FastAPI, SQLAlchemy, Alembic

---

### Task 1: Add cache helpers to ai_service.py

**Files:**
- Modify: `backend/ai_service.py:1-10` (imports/top-of-file)

- [ ] **Step 1: Add cache helper functions at the top of ai_service.py**

Add these imports and helpers after the existing imports (line 8) and before line 10 (`logger = ...`):

```python
import hashlib
from cache_service import cache_get, cache_set

# AI response cache TTL (read from env, default 30 minutes)
AI_CACHE_TTL_SECONDS = int(os.getenv("AI_CACHE_TTL_MINUTES", "30")) * 60


def _ai_cache_key(cache_input: str) -> str:
    """Build a Redis key from a SHA-256 hash of the full AI input string."""
    digest = hashlib.sha256(cache_input.encode("utf-8")).hexdigest()
    return f"ai_cache:{digest}"
```

- [ ] **Step 2: Verify the import works**

Run: `cd /home/tauhid/code/aibot2/backend && python -c "from ai_service import _ai_cache_key; print(_ai_cache_key('test'))"`
Expected: `ai_cache:<64-char hex>`

- [ ] **Step 3: Commit**

```bash
cd /home/tauhid/code/aibot2
git add backend/ai_service.py
git commit -m "feat: add AI response cache helpers to ai_service.py"
```

---

### Task 2: Cache `analyze_with_ai`

**Files:**
- Modify: `backend/ai_service.py:229-282` (`analyze_with_ai` function)

- [ ] **Step 1: Add caching to analyze_with_ai**

The function currently builds `full_prompt` at line 248 and calls the API at line 251. Insert cache logic around the API call. The modified function should:

1. Accept an optional `skip_cache: bool = False` parameter.
2. Build a `cache_input` string from `full_prompt + model_id`.
3. If `skip_cache` is False, check Redis for cached response; if found, return it immediately (skip `_accumulate_tokens` and `set_usage_task`).
4. On cache miss (or skip_cache=True), call the API as before, then store the response in Redis.

Replace the entire `analyze_with_ai` function (lines 229-282) with:

```python
async def analyze_with_ai(prompt: str, data: Dict[str, Any], skip_cache: bool = False) -> str:
    """
    Generic AI analysis function that takes a prompt and data, returns AI response.
    Results are cached in Redis for AI_CACHE_TTL_SECONDS unless skip_cache is True.
    """
    # Build canonical input for cache key
    data_str = json.dumps(data, indent=2, sort_keys=True)
    full_prompt = f"{prompt}\n\nData to analyze:\n{data_str}"
    model_id = get_active_model()
    cache_input = f"{full_prompt}||{model_id}"

    # Check cache (unless skipping)
    if not skip_cache:
        cache_key = _ai_cache_key(cache_input)
        cached = cache_get(cache_key)
        if cached is not None:
            logger.info("AI analysis cache HIT")
            return cached

    set_usage_task("AI Analysis")
    try:
        api_key = get_claude_client()

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": model_id,
                    "max_tokens": 1024,
                    "messages": [
                        {
                            "role": "user",
                            "content": full_prompt
                        }
                    ]
                }
            )

            response.raise_for_status()
            result = response.json()
            _accumulate_tokens(result)

            ai_response = result["content"][0]["text"].strip()
            logger.info(f"AI analysis completed, response length: {len(ai_response)}")

            # Store in cache
            cache_key = _ai_cache_key(cache_input)
            cache_set(cache_key, ai_response, ttl=AI_CACHE_TTL_SECONDS)

            return ai_response

    except Exception as e:
        raise handle_anthropic_error(e, "AI analysis")
```

Note: `data` is serialized with `sort_keys=True` to ensure consistent cache keys regardless of dict key order.

- [ ] **Step 2: Commit**

```bash
git add backend/ai_service.py
git commit -m "feat: add response caching to analyze_with_ai"
```

---

### Task 3: Cache `extract_key_information`

**Files:**
- Modify: `backend/ai_service.py:285-493` (`extract_key_information` function)

- [ ] **Step 1: Add caching to extract_key_information**

Add `skip_cache: bool = False` parameter. Build the cache input from the full prompt string (which includes transcript, extraction points, and universal rules) + model_id. Check cache before the API call at line 374. Store the full `result` dict in cache after success.

At line 285, change the signature to:

```python
async def extract_key_information(transcript: str, extraction_points: List[Dict[str, Any]], participants: List[str] = None, workflow_id: int = None, skip_cache: bool = False) -> Dict[str, Any]:
```

After the prompt is fully built (after line 368, the `Return only the JSON object...` line), and before the API call block (line 370), insert:

```python
        # Cache check
        model_id = get_active_model()
        cache_input = f"{prompt}||{model_id}"
        if not skip_cache:
            cache_key = _ai_cache_key(cache_input)
            cached = cache_get(cache_key)
            if cached is not None:
                logger.info("Key information extraction cache HIT")
                return cached
```

After the `result` dict is built (after line 483, `return result`), but before the return, insert a cache store:

```python
        # Store in cache
        cache_key = _ai_cache_key(cache_input)
        cache_set(cache_key, result, ttl=AI_CACHE_TTL_SECONDS)
```

- [ ] **Step 2: Commit**

```bash
git add backend/ai_service.py
git commit -m "feat: add response caching to extract_key_information"
```

---

### Task 4: Cache `extract_and_summarize`

**Files:**
- Modify: `backend/ai_service.py:719-949` (`extract_and_summarize` function)

- [ ] **Step 1: Add caching to extract_and_summarize**

Add `skip_cache: bool = False` to the function signature at line 719:

```python
async def extract_and_summarize(
    transcript: str,
    extraction_points: List[Dict[str, Any]],
    config: Dict[str, Any] = None,
    participants: List[str] = None,
    workflow_id: int = None,
    input_data: Dict[str, Any] = None,
    skip_cache: bool = False,
) -> Dict[str, Any]:
```

After the full prompt and system_prompt are built (after line 840, the closing `"""`), and before the context window guard (line 843), insert:

```python
        # Cache check
        cache_input = f"{system_prompt}||{prompt}||{get_active_model()}"
        if not skip_cache:
            cache_key = _ai_cache_key(cache_input)
            cached = cache_get(cache_key)
            if cached is not None:
                logger.info("[TEXT-GEN] Extract+summarize cache HIT")
                return cached
```

After the successful return dict is built (line 934-939), before `return`, insert:

```python
        # Store in cache
        cache_key = _ai_cache_key(cache_input)
        cache_set(cache_key, result_to_return, ttl=AI_CACHE_TTL_SECONDS)
```

Note: assign the return dict to a variable `result_to_return` instead of returning inline, so you can cache it before returning.

Change lines 934-939 from:
```python
        return {
            "status": "success",
            ...
        }
```
to:
```python
        result_to_return = {
            "status": "success",
            "extracted_information": extracted_data,
            "summary": summary_text,
            "model_used": get_active_model(),
        }

        # Store in cache
        cache_key = _ai_cache_key(cache_input)
        cache_set(cache_key, result_to_return, ttl=AI_CACHE_TTL_SECONDS)

        return result_to_return
```

- [ ] **Step 2: Commit**

```bash
git add backend/ai_service.py
git commit -m "feat: add response caching to extract_and_summarize"
```

---

### Task 5: Cache `generate_email_content`

**Files:**
- Modify: `backend/ai_service.py:952-1059` (`generate_email_content` function)

- [ ] **Step 1: Add caching to generate_email_content**

Add `skip_cache: bool = False` to the signature. Build cache input from `system_prompt + full_prompt + model_id`. Check before the API call, store after.

Change line 952 to:
```python
async def generate_email_content(prompt: str, context: Dict[str, Any], workflow_id: int = None, skip_cache: bool = False) -> str:
```

After `full_prompt` is built (after line 1018), insert:

```python
        # Cache check
        model_id = get_active_model()
        cache_input = f"{system_prompt}||{full_prompt}||{model_id}"
        if not skip_cache:
            cache_key = _ai_cache_key(cache_input)
            cached = cache_get(cache_key)
            if cached is not None:
                logger.info("Email content generation cache HIT")
                return cached
```

After `email_body` is extracted (after line 1048), before `return email_body`, insert:

```python
            # Store in cache
            cache_key = _ai_cache_key(cache_input)
            cache_set(cache_key, email_body, ttl=AI_CACHE_TTL_SECONDS)
```

- [ ] **Step 2: Commit**

```bash
git add backend/ai_service.py
git commit -m "feat: add response caching to generate_email_content"
```

---

### Task 6: Cache `generate_email_with_metadata`

**Files:**
- Modify: `backend/ai_service.py:1169-1540` (`generate_email_with_metadata` function)

- [ ] **Step 1: Add caching to generate_email_with_metadata**

Add `skip_cache: bool = False` to the signature at line 1169:
```python
async def generate_email_with_metadata(
    prompt: str,
    delivery_settings: Dict[str, Any],
    workflow_id: int = None,
    input_data: Dict[str, Any] = None,
    skip_cache: bool = False,
) -> Dict[str, Any]:
```

After `full_prompt` is built (after line 1396), insert:

```python
        # Cache check
        model_id = get_active_model()
        cache_input = f"{system_prompt}||{full_prompt}||{model_id}"
        if not skip_cache:
            cache_key = _ai_cache_key(cache_input)
            cached = cache_get(cache_key)
            if cached is not None:
                logger.info("[EMAIL-GEN] Cache HIT")
                return cached
```

After `result_dict` is fully built (after line 1523, just before `return result_dict`), insert:

```python
            # Store in cache
            cache_key = _ai_cache_key(cache_input)
            cache_set(cache_key, result_dict, ttl=AI_CACHE_TTL_SECONDS)
```

- [ ] **Step 2: Commit**

```bash
git add backend/ai_service.py
git commit -m "feat: add response caching to generate_email_with_metadata"
```

---

### Task 7: Cache `generate_email_subject`

**Files:**
- Modify: `backend/ai_service.py:1543-1649` (`generate_email_subject` function)

- [ ] **Step 1: Add caching to generate_email_subject**

Add `skip_cache: bool = False` to the signature:
```python
async def generate_email_subject(
    subject_prompt: str,
    email_body: str,
    delivery_settings: Dict[str, Any],
    workflow_id: int = None,
    skip_cache: bool = False,
) -> str:
```

After `full_prompt` is built (after line 1607), insert:

```python
        # Cache check
        model_id = get_active_model()
        cache_input = f"{system_prompt}||{full_prompt}||{model_id}"
        if not skip_cache:
            cache_key = _ai_cache_key(cache_input)
            cached = cache_get(cache_key)
            if cached is not None:
                logger.info("Email subject generation cache HIT")
                return cached
```

After `subject_line` is cleaned (after line 1640), before `return subject_line`, insert:

```python
            # Store in cache
            cache_key = _ai_cache_key(cache_input)
            cache_set(cache_key, subject_line, ttl=AI_CACHE_TTL_SECONDS)
```

- [ ] **Step 2: Commit**

```bash
git add backend/ai_service.py
git commit -m "feat: add response caching to generate_email_subject"
```

---

### Task 8: Cache `match_organization_with_ai`

**Files:**
- Modify: `backend/ai_service.py:1652+` (`match_organization_with_ai` function)

- [ ] **Step 1: Add caching to match_organization_with_ai**

Add `skip_cache: bool = False` to the signature:
```python
async def match_organization_with_ai(
    organizations: List[Dict[str, Any]],
    company_name: str,
    context: Dict[str, Any] = None,
    workflow_id: int = None,
    skip_cache: bool = False,
) -> Dict[str, Any]:
```

This function calls the Anthropic API internally after building the prompt. Place the cache check after the full prompt is assembled (after `org_list_str` and the prompt are built), before the API call. Build cache input from `system_prompt + prompt + model_id`.

Cache the final return dict on success. Do NOT cache error responses.

- [ ] **Step 2: Commit**

```bash
git add backend/ai_service.py
git commit -m "feat: add response caching to match_organization_with_ai"
```

---

### Task 9: Thread `skip_cache` through the execution engine

**Files:**
- Modify: `backend/executions.py:33-36` (ExecutionCreate model)
- Modify: `backend/executions.py:1556-1602` (execute_workflow_background)
- Modify: `backend/executions.py:1892-1974` (execute_workflow endpoint)

- [ ] **Step 1: Add skip_cache to ExecutionCreate**

At line 33, add the field:

```python
class ExecutionCreate(BaseModel):
    workflow_id: int
    test_mode: bool = False
    fireflies_transcript_id: Optional[str] = None
    skip_cache: bool = False
```

- [ ] **Step 2: Add skip_cache to the Execution model**

In `backend/models.py`, add a column to the `Execution` class (after `total_tokens` at line 270):

```python
    skip_cache = Column(Boolean, default=False)
```

Also add the `Boolean` import if not already present in the `Column` imports.

- [ ] **Step 3: Set skip_cache when creating the execution record**

In `execute_workflow` (line 1960), add `skip_cache` to the Execution constructor:

```python
    db_execution = models.Execution(
        workflow_id=workflow_id,
        status="running",
        input_data=input_data,
        skip_cache=execution_data.skip_cache,
    )
```

- [ ] **Step 4: Inject skip_cache into execution_data in execute_workflow_background**

In `execute_workflow_background`, after `execution_data` is set (line 1607), add:

```python
        # Thread skip_cache flag into the data flowing through components
        execution_data["__skip_cache__"] = bool(execution.skip_cache)
```

- [ ] **Step 5: Commit**

```bash
git add backend/executions.py backend/models.py
git commit -m "feat: thread skip_cache flag through execution engine"
```

---

### Task 10: Pass `skip_cache` from component executors to AI functions

**Files:**
- Modify: `backend/executions.py` — all `execute_*` methods that call AI functions

- [ ] **Step 1: Update execute_ai_filter (line 166)**

At line 198, change:
```python
ai_response = await analyze_with_ai(ai_prompt_processed, input_data)
```
to:
```python
skip_cache = input_data.get("__skip_cache__", False)
ai_response = await analyze_with_ai(ai_prompt_processed, input_data, skip_cache=skip_cache)
```

- [ ] **Step 2: Update execute_text_generation (line 276)**

At line 303, change:
```python
            result = await extract_and_summarize(
                transcript=transcript,
                extraction_points=extraction_points,
                config=config,
                participants=participant_names,
                workflow_id=workflow_id,
                input_data=input_data,
            )
```
to:
```python
            skip_cache = input_data.get("__skip_cache__", False)
            result = await extract_and_summarize(
                transcript=transcript,
                extraction_points=extraction_points,
                config=config,
                participants=participant_names,
                workflow_id=workflow_id,
                input_data=input_data,
                skip_cache=skip_cache,
            )
```

- [ ] **Step 3: Update execute_email (line 341)**

At line 420 where `generate_email_with_metadata` is called, change:
```python
                email_metadata = await generate_email_with_metadata(
                    email_prompt_processed,
                    delivery_settings,
                    workflow_id,
                    input_data
                )
```
to:
```python
                skip_cache = input_data.get("__skip_cache__", False)
                email_metadata = await generate_email_with_metadata(
                    email_prompt_processed,
                    delivery_settings,
                    workflow_id,
                    input_data,
                    skip_cache=skip_cache,
                )
```

Also find the `generate_email_subject` call in execute_email and add `skip_cache=skip_cache` there. Search for `generate_email_subject` in the execute_email method (around line 493) and add the parameter.

- [ ] **Step 4: Update execute_company_name_matcher (line 1147)**

At line 1200 where `analyze_with_ai` is called:
```python
company_name_response = await analyze_with_ai(ai_prompt, input_data)
```
change to:
```python
skip_cache = input_data.get("__skip_cache__", False)
company_name_response = await analyze_with_ai(ai_prompt, input_data, skip_cache=skip_cache)
```

Also find the `match_organization_with_ai` call in the same function and add `skip_cache=skip_cache`.

- [ ] **Step 5: Commit**

```bash
git add backend/executions.py
git commit -m "feat: pass skip_cache from component executors to AI functions"
```

---

### Task 11: Create Alembic migration for skip_cache column

**Files:**
- Create: `backend/alembic/versions/031_add_skip_cache_to_executions.py`

- [ ] **Step 1: Create the migration file**

```python
"""Add skip_cache column to executions

Revision ID: 031
Revises: 030
Create Date: 2026-04-07
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '031'
down_revision = '030'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('executions', sa.Column('skip_cache', sa.Boolean(), server_default=sa.text('false'), nullable=True))


def downgrade() -> None:
    op.drop_column('executions', 'skip_cache')
```

- [ ] **Step 2: Run migration**

Run: `cd /home/tauhid/code/aibot2/backend && python migrate.py`
Expected: Migration applies successfully.

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/031_add_skip_cache_to_executions.py
git commit -m "feat: add skip_cache column migration for executions table"
```

---

### Task 12: Document the AI_CACHE_TTL_MINUTES environment variable

**Files:**
- Modify: `CLAUDE.md` (add to environment variables section)

- [ ] **Step 1: Add AI_CACHE_TTL_MINUTES to the env vars section in CLAUDE.md**

In the "Working with Environment Variables" section, after the `EMAIL_WORKER_INTERVAL` entry, add:

```bash
# AI Response Cache
AI_CACHE_TTL_MINUTES=30             # How long AI responses are cached (minutes, default: 30)
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document AI_CACHE_TTL_MINUTES environment variable"
```

---

### Task 13: Manual verification

- [ ] **Step 1: Start the services**

```bash
cd /home/tauhid/code/aibot2
docker compose up -d
```

- [ ] **Step 2: Verify Redis has ai_cache entries after an execution**

After triggering a workflow execution, check Redis:
```bash
docker compose exec redis redis-cli KEYS "ai_cache:*"
```
Expected: One or more `ai_cache:*` keys appear.

- [ ] **Step 3: Verify cache TTL**

```bash
docker compose exec redis redis-cli TTL "ai_cache:<one-of-the-keys>"
```
Expected: A number close to 1800 (30 minutes in seconds).

- [ ] **Step 4: Verify skip_cache works**

Send a POST to `/api/executions/` with `"skip_cache": true` in the body. Check backend logs — should see API calls happening (no "cache HIT" messages).

- [ ] **Step 5: Verify cache clearing**

```bash
docker compose exec redis redis-cli KEYS "ai_cache:*" | wc -l
# Then clear
docker compose exec redis redis-cli EVAL "for _,k in ipairs(redis.call('keys','ai_cache:*')) do redis.call('del',k) end" 0
docker compose exec redis redis-cli KEYS "ai_cache:*" | wc -l
```
Expected: Count drops to 0.
