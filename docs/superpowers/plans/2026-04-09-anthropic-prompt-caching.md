# Anthropic Prompt Caching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Anthropic's server-side prompt caching (`cache_control`) to all Claude API calls in `ai_service.py`, reducing input token costs by up to 90% for repeated instruction prefixes.

**Architecture:** Every API call in `ai_service.py` currently sends prompts as plain strings. We restructure them to use content block arrays with `cache_control: {"type": "ephemeral"}` markers on the static instruction prefix (system prompt + universal rules). The variable data (transcript, user data) remains uncached at the end. We also update `_accumulate_tokens` to track `cache_creation_input_tokens` and `cache_read_input_tokens` from the API response. All calls use raw `httpx` — no SDK change needed.

**Tech Stack:** Python, httpx (existing), Anthropic Messages API with prompt caching

---

## Key Design Decisions

1. **Where to place `cache_control` markers**: On the system prompt's last content block (which includes universal rules) and optionally on the instruction prefix in the user message. Anthropic caches from the start up to each `cache_control` breakpoint.

2. **System prompt restructuring**: Functions that have a system prompt + universal rules will send `system` as a content array `[{"type": "text", "text": "...", "cache_control": {"type": "ephemeral"}}]` instead of a plain string.

3. **User message restructuring**: For heavy functions (`extract_key_information`, `extract_and_summarize`, `generate_summary`), split the user message into a cacheable instruction block and a variable data block.

4. **Functions WITHOUT a system prompt** (`analyze_with_ai`, `extract_key_information`, `generate_summary`): These embed everything in the user message. We split the user message into two content blocks — instructions (cached) and data (not cached).

5. **Token tracking**: `_accumulate_tokens` will also log `cache_creation_input_tokens` and `cache_read_input_tokens` for observability.

6. **No beta header needed**: Prompt caching is GA as of 2025 — just requires the content block array format with `cache_control`.

---

### Task 1: Update `_accumulate_tokens` for cache metrics

**Files:**
- Modify: `backend/ai_service.py:150-178`

- [ ] **Step 1: Update `_accumulate_tokens` to track cache tokens**

Replace the `_accumulate_tokens` function (lines 150-178) with:

```python
def _accumulate_tokens(api_response: dict):
    """Extract usage from a Claude API response and add to the accumulator."""
    usage = api_response.get("usage", {})
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    cache_creation_tokens = usage.get("cache_creation_input_tokens", 0)
    cache_read_tokens = usage.get("cache_read_input_tokens", 0)
    _prompt_tokens.set(_prompt_tokens.get() + input_tokens)
    _completion_tokens.set(_completion_tokens.get() + output_tokens)

    # Log cache hit/miss for observability
    if cache_creation_tokens or cache_read_tokens:
        logger.info(f"Prompt cache: created={cache_creation_tokens}, read={cache_read_tokens} tokens")

    # Also append to usage records if context is set
    user_id = _usage_user_id.get()
    if user_id is not None:
        model = api_response.get("model", None) or get_active_model()
        cost = _calculate_cost(model, input_tokens, output_tokens)
        records = _usage_records.get()
        records.append({
            "user_id": user_id,
            "source": _usage_source.get() or "unknown",
            "execution_id": _usage_execution_id.get(),
            "component_id": _usage_component_id.get(),
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "ai_model": model,
            "cost": cost,
            "task": _usage_task.get(),
            "cache_creation_input_tokens": cache_creation_tokens,
            "cache_read_input_tokens": cache_read_tokens,
        })
        _usage_records.set(records)
        # Consume-once: reset task after recording to prevent stale labels
        _usage_task.set(None)
```

- [ ] **Step 2: Verify no syntax errors**

Run: `cd /home/tauhid/code/aibot2/backend && python -c "import ai_service; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/ai_service.py
git commit -m "feat: track prompt cache tokens in _accumulate_tokens"
```

---

### Task 2: Add prompt caching to `analyze_with_ai`

**Files:**
- Modify: `backend/ai_service.py:229-282` (the `analyze_with_ai` function)

This function has NO system prompt — everything is in the user message. The prompt (instructions) is cacheable; the data is variable.

- [ ] **Step 1: Restructure the API call to use content blocks**

Replace the API call JSON payload (lines 259-268) from:

```python
json={
    "model": get_active_model(),
    "max_tokens": 1024,
    "messages": [
        {
            "role": "user",
            "content": full_prompt
        }
    ]
}
```

To:

```python
json={
    "model": get_active_model(),
    "max_tokens": 1024,
    "messages": [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": prompt,
                    "cache_control": {"type": "ephemeral"}
                },
                {
                    "type": "text",
                    "text": f"Data to analyze:\n{data_str}"
                }
            ]
        }
    ]
}
```

Also remove the `full_prompt` variable construction (line 248: `full_prompt = f"{prompt}\n\nData to analyze:\n{data_str}"`).

- [ ] **Step 2: Verify no syntax errors**

Run: `cd /home/tauhid/code/aibot2/backend && python -c "import ai_service; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/ai_service.py
git commit -m "feat: add prompt caching to analyze_with_ai"
```

---

### Task 3: Add prompt caching to `extract_key_information`

**Files:**
- Modify: `backend/ai_service.py:285-493` (the `extract_key_information` function)

This function has no system prompt. The base instructions + universal rules + extraction points are cacheable. The transcript is variable.

- [ ] **Step 1: Split the prompt into cacheable instruction and variable transcript**

Replace the prompt construction and API call. Instead of building one giant `prompt` string (lines 340-368), split into two parts:

The instruction prefix (everything before the transcript — cacheable):
```python
instruction_prefix = f"""{base_instructions}

Instructions:
1. Carefully read the entire transcript
2. Extract the requested information points
3. If information is not available or unclear, use null for that field
4. Be concise but comprehensive
5. Focus on factual information from the transcript
6. Return your response as a valid JSON object only

Please analyze the following meeting transcript and extract the requested key information:"""
```

The variable data (transcript + extraction points template — the extraction points part could also be cached but it varies per workflow config, so cache the instruction prefix which includes universal rules):
```python
variable_data = f"""
TRANSCRIPT:
{transcript}

EXTRACTION POINTS TO FIND:
{extraction_points_text}

Please return a JSON object with the extracted information. Use the extraction point names as keys. Example format:
{{
    "Participants": ["John Doe", "Jane Smith"],
    "Pain Points": ["Manual data entry", "System integration issues"],
    "Budget": "$50,000 - $100,000",
    "Timeline": "Q1 2024",
    "Next Steps": ["Schedule demo", "Send proposal"],
    "Competitors": ["Salesforce", "HubSpot"]
}}

Return only the JSON object, no additional text."""
```

Then update the API call (lines 383-394) to use content blocks:

```python
json={
    "model": get_active_model(),
    "max_tokens": 3500,
    "temperature": 0.1,
    "messages": [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": instruction_prefix,
                    "cache_control": {"type": "ephemeral"}
                },
                {
                    "type": "text",
                    "text": variable_data
                }
            ]
        }
    ]
}
```

- [ ] **Step 2: Verify no syntax errors**

Run: `cd /home/tauhid/code/aibot2/backend && python -c "import ai_service; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/ai_service.py
git commit -m "feat: add prompt caching to extract_key_information"
```

---

### Task 4: Add prompt caching to `generate_summary`

**Files:**
- Modify: `backend/ai_service.py:496-675` (the `generate_summary` function)

No system prompt. The instruction prefix + universal rules + style guidance is cacheable. The transcript + extracted info is variable.

- [ ] **Step 1: Split prompt and update API call**

Split `base_prompt` into an instruction part and a data part. The instruction part is `base_prompt_start` (already exists, lines 574-588) plus the style guidance. The data part is the transcript and extracted info.

Replace the API call JSON payload (lines 639-649) to use content blocks:

```python
json={
    "model": get_active_model(),
    "max_tokens": max_tokens,
    "temperature": 0.3,
    "messages": [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": base_prompt_start + f"\n\n{default_summary if not summary_prompt else ''}Style guidance: {style_instruction}",
                    "cache_control": {"type": "ephemeral"}
                },
                {
                    "type": "text",
                    "text": f"TRANSCRIPT:\n{transcript}\n\nEXTRACTED KEY INFORMATION:\n{json.dumps(extracted_info.get('extracted_information', {}), indent=2)}"
                }
            ]
        }
    ]
}
```

Note: The truncation guard (lines 608-625) should operate on the transcript portion only, before building the content blocks.

- [ ] **Step 2: Verify no syntax errors**

Run: `cd /home/tauhid/code/aibot2/backend && python -c "import ai_service; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/ai_service.py
git commit -m "feat: add prompt caching to generate_summary"
```

---

### Task 5: Add prompt caching to `extract_and_summarize`

**Files:**
- Modify: `backend/ai_service.py:719-949` (the `extract_and_summarize` function)

This is the highest-value target. It HAS a system prompt and uses universal rules. Cache the system prompt (with rules) and the instruction prefix in the user message. The transcript is variable.

- [ ] **Step 1: Convert system prompt to cached content array**

Replace the system prompt string in the API call (line 867) from:

```python
"system": system_prompt,
```

To:

```python
"system": [
    {
        "type": "text",
        "text": system_prompt,
        "cache_control": {"type": "ephemeral"}
    }
],
```

- [ ] **Step 2: Split user message into cached instructions and variable transcript**

Split the user `prompt` (lines 818-840) into two parts. The instruction part (everything except the transcript):

```python
instruction_part = f"""Analyze the following meeting transcript. You must produce TWO things in your response:

1. **EXTRACTED INFORMATION** — a JSON object extracting these specific data points:
{extraction_points_text}

2. **SUMMARY** — a meeting summary following these instructions:
{summary_instruction}

Style guidance: {style_instruction}
{participant_context}"""

transcript_part = f"""TRANSCRIPT:
{transcript}

---

RESPOND IN EXACTLY THIS FORMAT (no other text before or after):

```json
{{EXTRACTED_INFO_JSON}}
```

---SUMMARY---
{{YOUR_SUMMARY_HERE}}"""
```

Then update the messages in the API call (line 869) to:

```python
"messages": [{
    "role": "user",
    "content": [
        {
            "type": "text",
            "text": instruction_part,
            "cache_control": {"type": "ephemeral"}
        },
        {
            "type": "text",
            "text": transcript_part
        }
    ]
}]
```

The context window guard (lines 843-851) should operate on the transcript string before building `transcript_part`.

- [ ] **Step 3: Verify no syntax errors**

Run: `cd /home/tauhid/code/aibot2/backend && python -c "import ai_service; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/ai_service.py
git commit -m "feat: add prompt caching to extract_and_summarize"
```

---

### Task 6: Add prompt caching to `generate_email_content`

**Files:**
- Modify: `backend/ai_service.py:952-1059` (the `generate_email_content` function)

Has system prompt with universal rules. Cache the system prompt.

- [ ] **Step 1: Convert system prompt to cached content array**

Replace the API call JSON (lines 1029-1039):

```python
json={
    "model": get_active_model(),
    "max_tokens": 2048,
    "system": [
        {
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"}
        }
    ],
    "messages": [
        {
            "role": "user",
            "content": full_prompt
        }
    ]
}
```

- [ ] **Step 2: Verify no syntax errors**

Run: `cd /home/tauhid/code/aibot2/backend && python -c "import ai_service; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/ai_service.py
git commit -m "feat: add prompt caching to generate_email_content"
```

---

### Task 7: Add prompt caching to `generate_email_with_metadata`

**Files:**
- Modify: `backend/ai_service.py:1169-1540` (the `generate_email_with_metadata` function)

Has system prompt with universal rules + signature rule + resource manifest. This is the most complex system prompt — all of it should be cached.

- [ ] **Step 1: Convert system prompt to cached content array**

Replace the API call JSON (lines 1413-1424):

```python
json={
    "model": get_active_model(),
    "max_tokens": 2048,
    "system": [
        {
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"}
        }
    ],
    "temperature": 0.7,
    "messages": [
        {
            "role": "user",
            "content": full_prompt
        }
    ]
}
```

- [ ] **Step 2: Verify no syntax errors**

Run: `cd /home/tauhid/code/aibot2/backend && python -c "import ai_service; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/ai_service.py
git commit -m "feat: add prompt caching to generate_email_with_metadata"
```

---

### Task 8: Add prompt caching to `generate_email_subject`

**Files:**
- Modify: `backend/ai_service.py:1543-1649` (the `generate_email_subject` function)

Has system prompt with universal rules. Cache the system prompt.

- [ ] **Step 1: Convert system prompt to cached content array**

Replace the API call JSON (lines 1618-1629):

```python
json={
    "model": get_active_model(),
    "max_tokens": 256,
    "system": [
        {
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"}
        }
    ],
    "temperature": 0.7,
    "messages": [
        {
            "role": "user",
            "content": full_prompt
        }
    ]
}
```

- [ ] **Step 2: Verify no syntax errors**

Run: `cd /home/tauhid/code/aibot2/backend && python -c "import ai_service; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/ai_service.py
git commit -m "feat: add prompt caching to generate_email_subject"
```

---

### Task 9: Add prompt caching to `match_organization_with_ai`

**Files:**
- Modify: `backend/ai_service.py:1652-1857` (the `match_organization_with_ai` function)

Has system prompt with universal rules. Cache the system prompt.

- [ ] **Step 1: Convert system prompt to cached content array**

Replace the API call JSON (lines 1796-1807):

```python
json={
    "model": get_active_model(),
    "max_tokens": 512,
    "system": [
        {
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"}
        }
    ],
    "temperature": 0.1,
    "messages": [
        {
            "role": "user",
            "content": full_prompt
        }
    ]
}
```

- [ ] **Step 2: Verify no syntax errors**

Run: `cd /home/tauhid/code/aibot2/backend && python -c "import ai_service; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/ai_service.py
git commit -m "feat: add prompt caching to match_organization_with_ai"
```

---

### Task 10: Add prompt caching to `select_deal_with_ai`

**Files:**
- Modify: `backend/ai_service.py:1860-2009` (the `select_deal_with_ai` function)

Has system prompt with universal rules. Cache the system prompt.

- [ ] **Step 1: Convert system prompt to cached content array**

Replace the API call JSON (lines 1951-1962):

```python
json={
    "model": get_active_model(),
    "max_tokens": 512,
    "system": [
        {
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"}
        }
    ],
    "temperature": 0.2,
    "messages": [
        {
            "role": "user",
            "content": full_prompt
        }
    ]
}
```

- [ ] **Step 2: Verify no syntax errors**

Run: `cd /home/tauhid/code/aibot2/backend && python -c "import ai_service; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/ai_service.py
git commit -m "feat: add prompt caching to select_deal_with_ai"
```

---

### Task 11: Add prompt caching to `generate_sequence_emails`

**Files:**
- Modify: `backend/ai_service.py:2016-2178` (the `generate_sequence_emails` function)

Has system prompt with universal rules + tone guidance + signature rule. Cache the system prompt.

- [ ] **Step 1: Convert system prompt to cached content array**

Replace the API call JSON (lines 2135-2143):

```python
json={
    "model": get_active_model(),
    "max_tokens": 4096,
    "system": [
        {
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"}
        }
    ],
    "temperature": 0.7,
    "messages": [
        {"role": "user", "content": user_prompt}
    ]
}
```

- [ ] **Step 2: Verify no syntax errors**

Run: `cd /home/tauhid/code/aibot2/backend && python -c "import ai_service; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/ai_service.py
git commit -m "feat: add prompt caching to generate_sequence_emails"
```

---

### Task 12: Add prompt caching to `optimize_email_timing`

**Files:**
- Modify: `backend/ai_service.py:2181-2315` (the `optimize_email_timing` function)

Has system prompt with universal rules. Cache the system prompt.

- [ ] **Step 1: Convert system prompt to cached content array**

Replace the API call JSON (lines 2273-2281):

```python
json={
    "model": get_active_model(),
    "max_tokens": 2048,
    "system": [
        {
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"}
        }
    ],
    "temperature": 0.3,
    "messages": [
        {"role": "user", "content": user_prompt}
    ]
}
```

- [ ] **Step 2: Verify no syntax errors**

Run: `cd /home/tauhid/code/aibot2/backend && python -c "import ai_service; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/ai_service.py
git commit -m "feat: add prompt caching to optimize_email_timing"
```

---

### Task 13: Add prompt caching to `ai_edit_email_content`

**Files:**
- Modify: `backend/ai_service.py:2403-2547` (the `ai_edit_email_content` function)

Has system prompt (no universal rules, but static instructions). Cache the system prompt.

- [ ] **Step 1: Convert system prompt to cached content array**

Replace the API call JSON (lines 2495-2503):

```python
json={
    "model": get_active_model(),
    "max_tokens": 2048,
    "system": [
        {
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"}
        }
    ],
    "temperature": 0.5,
    "messages": [
        {"role": "user", "content": user_prompt}
    ]
}
```

- [ ] **Step 2: Verify no syntax errors**

Run: `cd /home/tauhid/code/aibot2/backend && python -c "import ai_service; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/ai_service.py
git commit -m "feat: add prompt caching to ai_edit_email_content"
```

---

### Task 14: Final verification — all API calls use prompt caching

- [ ] **Step 1: Grep to verify all API calls use cache_control**

Run: `cd /home/tauhid/code/aibot2/backend && grep -c "api.anthropic.com/v1/messages" ai_service.py` — count total API calls.
Run: `cd /home/tauhid/code/aibot2/backend && grep -c "cache_control" ai_service.py` — count cache_control usages. Should be >= the API call count.

- [ ] **Step 2: Verify no plain string `"system":` remains**

Run: `cd /home/tauhid/code/aibot2/backend && grep -n '"system":' ai_service.py` — all matches should show array format `[{` not plain string.

- [ ] **Step 3: Full import check**

Run: `cd /home/tauhid/code/aibot2/backend && python -c "import ai_service; print('All functions loaded OK')"`
Expected: `All functions loaded OK`

- [ ] **Step 4: Final commit**

```bash
git add backend/ai_service.py
git commit -m "feat: complete Anthropic prompt caching across all AI calls"
```
