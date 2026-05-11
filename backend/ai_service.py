import os
import json
import logging
import re
import httpx
import time
import contextvars
from typing import Dict, List, Any, Optional, Tuple
from sqlalchemy.orm import Session

from tracing import traced_call, record_skip

logger = logging.getLogger(__name__)


def _anthropic_response_summary(result: dict) -> dict:
    """Build a sanitized response snapshot for trace entries.

    Strips raw model thinking blocks; keeps text content + token usage so the
    UI can show what came back. Trace truncation in tracing.py caps long text.
    """
    content = result.get("content") or []
    text_parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text_parts.append(block.get("text", ""))
    return {
        "text": "\n".join(text_parts),
        "model": result.get("model"),
        "usage": result.get("usage"),
        "stop_reason": result.get("stop_reason"),
    }

# Token usage accumulator (async-safe via contextvars)
_prompt_tokens: contextvars.ContextVar[int] = contextvars.ContextVar('_prompt_tokens', default=0)
_completion_tokens: contextvars.ContextVar[int] = contextvars.ContextVar('_completion_tokens', default=0)

# Usage logging context — tracks individual AI calls for the ai_usage_log table
_usage_user_id: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar('_usage_user_id', default=None)
_usage_source: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar('_usage_source', default=None)
_usage_execution_id: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar('_usage_execution_id', default=None)
_usage_component_id: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar('_usage_component_id', default=None)
_usage_task: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar('_usage_task', default=None)
_usage_records: contextvars.ContextVar[List[Dict]] = contextvars.ContextVar('_usage_records', default=[])

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

# Cached model pricing
_cached_model_pricing: Dict[str, Dict[str, float]] = {}

def _get_model_pricing(model_id: str) -> Dict[str, float]:
    """Get pricing for a model. Cached to avoid repeated DB lookups."""
    if model_id in _cached_model_pricing:
        return _cached_model_pricing[model_id]
    try:
        from database import SessionLocal
        import models as _models
        db = SessionLocal()
        try:
            m = db.query(_models.AiModel).filter(_models.AiModel.model_id == model_id).first()
            if m:
                pricing = {
                    "input_cost_per_million": m.input_cost_per_million,
                    "output_cost_per_million": m.output_cost_per_million,
                }
                _cached_model_pricing[model_id] = pricing
                return pricing
        finally:
            db.close()
    except Exception:
        pass
    # Fallback: Claude Sonnet 4.5 pricing
    return {"input_cost_per_million": 3.0, "output_cost_per_million": 15.0}

def _calculate_costs(model_id: str, input_tokens: int, output_tokens: int,
                     cache_creation_tokens: int = 0, cache_read_tokens: int = 0) -> Tuple[float, float]:
    """Calculate (actual_cost, billable_cost) in USD for an API call.

    actual_cost: what we pay Anthropic with prompt cache tier pricing.
      - input_tokens @ 1x input rate
      - cache_creation_tokens @ 1.25x input rate (cache write premium)
      - cache_read_tokens @ 0.1x input rate (cache hit discount)
      - output_tokens @ output rate

    billable_cost: baseline we charge users, as if caching were disabled.
      - (input + cache_creation + cache_read) @ 1x input rate
      - output_tokens @ output rate
    This is stable regardless of cache hits, so users see consistent pricing.
    """
    pricing = _get_model_pricing(model_id)
    input_rate = pricing["input_cost_per_million"]
    output_rate = pricing["output_cost_per_million"]
    output_cost = (output_tokens / 1_000_000) * output_rate

    actual = (
        (input_tokens / 1_000_000) * input_rate
        + (cache_creation_tokens / 1_000_000) * input_rate * 1.25
        + (cache_read_tokens / 1_000_000) * input_rate * 0.1
        + output_cost
    )
    billable = (
        ((input_tokens + cache_creation_tokens + cache_read_tokens) / 1_000_000) * input_rate
        + output_cost
    )
    return round(actual, 6), round(billable, 6)


def set_usage_context(
    user_id: int,
    source: str,
    execution_id: Optional[int] = None,
    component_id: Optional[int] = None,
):
    """Set context for AI usage logging. Call before any AI operations."""
    _usage_user_id.set(user_id)
    _usage_source.set(source)
    _usage_execution_id.set(execution_id)
    _usage_component_id.set(component_id)
    _usage_task.set(None)
    _usage_records.set([])


def set_usage_component_id(component_id: Optional[int]):
    """Update the component_id in the usage context (called per-component during execution)."""
    _usage_component_id.set(component_id)


def set_usage_task(task: Optional[str]):
    """Set a descriptive label for the current AI call (e.g. 'extraction', 'summary')."""
    _usage_task.set(task)


def get_usage_cost() -> float:
    """Return the total billable USD cost from in-memory usage records (before flush).

    Returns billable_cost (baseline, no cache discounts) since this drives user-facing
    acorn charges — users should pay the same regardless of cache hit/miss.
    """
    records = _usage_records.get()
    return sum(r.get("billable_cost", 0) for r in records)


def get_usage_actual_cost() -> float:
    """Return the total actual USD cost (with Anthropic cache tier pricing) from in-memory usage records."""
    records = _usage_records.get()
    return sum(r.get("cost", 0) for r in records)


def flush_usage_log(db) -> int:
    """Write accumulated usage records to the ai_usage_log table. Returns count written."""
    import models
    records = _usage_records.get()
    if not records:
        return 0
    for rec in records:
        entry = models.AiUsageLog(**rec)
        db.add(entry)
    db.flush()
    count = len(records)
    _usage_records.set([])
    return count


def reset_token_counter():
    """Reset the token accumulator for a new execution run."""
    _prompt_tokens.set(0)
    _completion_tokens.set(0)


def get_token_totals() -> Dict[str, int]:
    """Return accumulated token counts for the current execution context."""
    prompt = _prompt_tokens.get()
    completion = _completion_tokens.get()
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
    }


def _accumulate_tokens(api_response: dict):
    """Extract usage from a Claude API response and add to the accumulator."""
    usage = api_response.get("usage", {})
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    cache_creation_tokens = usage.get("cache_creation_input_tokens", 0)
    cache_read_tokens = usage.get("cache_read_input_tokens", 0)
    # Effective prompt tokens includes cache write/read tokens for accurate aggregate totals
    effective_prompt_tokens = input_tokens + cache_creation_tokens + cache_read_tokens
    _prompt_tokens.set(_prompt_tokens.get() + effective_prompt_tokens)
    _completion_tokens.set(_completion_tokens.get() + output_tokens)

    # Log cache hit/miss for observability (Phase 7 — single source of truth for cache_hit boolean)
    cache_hit = cache_read_tokens > 0
    logger.info(
        f"AI call cache_hit={cache_hit} created={cache_creation_tokens} read={cache_read_tokens} "
        f"input={input_tokens} output={output_tokens}"
    )

    # Also append to usage records if context is set
    user_id = _usage_user_id.get()
    if user_id is not None:
        model = api_response.get("model", None) or get_active_model()
        actual_cost, billable_cost = _calculate_costs(
            model, input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens
        )
        records = _usage_records.get()
        records.append({
            "user_id": user_id,
            "source": _usage_source.get() or "unknown",
            "execution_id": _usage_execution_id.get(),
            "component_id": _usage_component_id.get(),
            "prompt_tokens": effective_prompt_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": effective_prompt_tokens + output_tokens,
            "ai_model": model,
            "cost": actual_cost,
            "billable_cost": billable_cost,
            "task": _usage_task.get(),
            "cache_creation_input_tokens": cache_creation_tokens,
            "cache_read_input_tokens": cache_read_tokens,
        })
        _usage_records.set(records)
        # Consume-once: reset task after recording to prevent stale labels
        _usage_task.set(None)
        
async def generate_sms_message(
    prompt: str,
    input_data: Dict[str, Any],
    max_chars: int,
    workflow_id: Optional[int] = None,
    db: Optional[Session] = None,
) -> str:
    set_usage_task("SMS Generation")

    api_key = get_claude_client()
    model = get_active_model()

    data_str = json.dumps(input_data, indent=2, default=str)

    system_prompt = f"""
You are writing a business follow-up SMS.

CHANNEL: SMS
HARD CONSTRAINTS:
- Maximum {max_chars} characters total.
- Plain text only.
- No markdown.
- No HTML.
- No subject line.
- Be conversational, direct, and natural.
- Include opt-out text only if the user prompt asks for it.
- Return only the SMS body.
""".strip()

    async with httpx.AsyncClient(timeout=30.0) as client:
        payload = {
            "model": model,
            "max_tokens": 300,
            "temperature": 0.3,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": system_prompt,
                            "cache_control": {"type": "ephemeral"},
                        },
                        {
                            "type": "text",
                            "text": f"User SMS instructions:\n{prompt}\n\nData:\n{data_str}",
                        },
                    ],
                }
            ],
        }

        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        result = response.json()

    _accumulate_tokens(result)

    return result["content"][0]["text"].strip()

async def generate_whatsapp_message(
    prompt: str,
    input_data: Dict[str, Any],
    max_chars: int = 4096,
    workflow_id: Optional[int] = None,
    db: Optional[Session] = None,
) -> str:
    set_usage_task("WhatsApp Generation")

    api_key = get_claude_client()
    model = get_active_model()
    data_str = json.dumps(input_data, indent=2, default=str)

    system_prompt = f"""
You are writing a business follow-up WhatsApp message.

CHANNEL: WhatsApp
CONSTRAINTS:
- Maximum {max_chars} characters, but aim for 200-500 characters.
- Conversational, not email-like.
- No subject line.
- Open with the person's name or a direct hook.
- WhatsApp formatting is allowed: *bold*, _italic_, ~strikethrough~, ```monospace```.
- Use line breaks for readability.
- Short paragraphs.
- Full URLs are allowed.
- No formal sign-offs like "Best regards" or "Sincerely".
- Emoji is acceptable where natural.
- Tone: friendly, direct, casual professional.
- Return only the WhatsApp message body.
""".strip()

    async with httpx.AsyncClient(timeout=30.0) as client:
        payload = {
            "model": model,
            "max_tokens": 700,
            "temperature": 0.4,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": system_prompt,
                            "cache_control": {"type": "ephemeral"},
                        },
                        {
                            "type": "text",
                            "text": f"User WhatsApp instructions:\n{prompt}\n\nData:\n{data_str}",
                        },
                    ],
                }
            ],
        }

        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        result = response.json()

    _accumulate_tokens(result)

    return result["content"][0]["text"].strip()

def get_claude_client():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not configured")
    return api_key


def handle_anthropic_error(error: Exception, context: str = "AI operation") -> Exception:
    """
    Centralized error handler for Anthropic API calls.
    Logs detailed errors server-side, returns generic user messages.

    Args:
        error: The caught exception
        context: Description of what operation failed (for logging)

    Returns:
        Exception with user-friendly message
    """
    if isinstance(error, httpx.TimeoutException):
        logger.error(f"Anthropic API timeout during {context}: {str(error)}", exc_info=True)
        return Exception("The AI service is taking longer than expected. Please try again in a few moments.")

    elif isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        logger.error(f"Anthropic API HTTP {status} during {context}: {str(error)}", exc_info=True)

        if status == 429:
            return Exception("The AI service is currently busy. Please wait a moment and try again.")
        elif status in [401, 403]:
            return Exception("AI service configuration error. Please contact support.")
        elif status >= 500:
            return Exception("The AI service is temporarily unavailable. Please try again later.")
        else:
            return Exception("The AI service encountered an error. Please try again.")

    elif isinstance(error, (httpx.ConnectError, httpx.RequestError)):
        logger.error(f"Anthropic API connection error during {context}: {str(error)}", exc_info=True)
        return Exception("Unable to reach the AI service. Please try again later.")

    elif isinstance(error, json.JSONDecodeError):
        logger.error(f"Invalid AI response during {context}: {str(error)}", exc_info=True)
        return Exception("The AI service returned an invalid response. Please try again.")

    else:
        logger.error(f"Unexpected error during {context}: {str(error)}", exc_info=True)
        return Exception("The AI service is temporarily unavailable. Please try again later.")


# --- Prompt-size budgeting ---
# Sonnet's context window is ~200k tokens (~800k chars at 4 chars/token). We
# target 600k chars so response + caching overhead + token-count drift never
# pushes us over. HEADROOM absorbs rounding error between char and token counts.
# RAG_BLOCK_SHARE caps how much of the budget retrieval can claim before the
# transcript/user-supplied content starts getting squeezed.
#
# TODO: swap char heuristic for tiktoken or Anthropic's count_tokens endpoint
# once the dependency is approved — char budgets are safe but wasteful.
MAX_PROMPT_CHARS = 600_000
PROMPT_CHAR_HEADROOM = 20_000
RAG_BLOCK_SHARE = 0.5
_CHARS_PER_TOKEN = 4  # rough estimate for English; only used for log metrics


def _approx_tokens(char_len: int) -> int:
    return char_len // _CHARS_PER_TOKEN


def _trim_rag_formatted_by_blocks(formatted: str, max_chars: int) -> str:
    """Shrink a RAG-formatted string until it fits in max_chars.

    Blocks produced by rag_service.get_email_context are emitted in priority
    order: RELEVANT RESOURCES > PREVIOUS OUTREACH > CONTACT HISTORY > ORG CONTEXT.
    Dropping from the tail removes the lowest-priority blocks first, which
    approximates "drop lowest-similarity chunks" without needing per-chunk
    scores here. If a single remaining block still exceeds the budget it is
    hard-truncated with an explicit marker so Claude sees the cut.
    """
    if not formatted or len(formatted) <= max_chars:
        return formatted
    blocks = re.split(r'\n\n(?=--- )', formatted)
    while len(blocks) > 1 and len("\n\n".join(blocks)) > max_chars:
        blocks.pop()
    trimmed = "\n\n".join(blocks)
    if len(trimmed) > max_chars:
        trimmed = trimmed[: max_chars - 40] + "\n[... RAG context truncated ...]"
    return trimmed


async def analyze_with_haiku(prompt: str, data: Dict[str, Any]) -> str:
    """Haiku-powered variant of analyze_with_ai used for AI Filters and sufficiency gates.

    Haiku is ~10× cheaper than Sonnet and is the right choice for simple classification
    (intent/BANT/bad fit yes-no questions). Haiku must NEVER generate email content.
    """
    set_usage_task("AI Filter (Haiku)")
    try:
        api_key = get_claude_client()
        data_str = json.dumps(data, indent=2, default=str)
        try:
            from rag_service import get_haiku_model
            model = get_haiku_model()
        except Exception:
            # Pull the default from rag_service so a model-string bump only
            # has to happen in one place. If even the import fails, a hardcoded
            # fallback would silently drift from the configured model — better
            # to raise here and force the caller to fix the environment.
            from rag_service import DEFAULT_HAIKU_MODEL
            model = DEFAULT_HAIKU_MODEL

        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "model": model,
                "max_tokens": 512,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}},
                            {"type": "text", "text": f"Data to analyze:\n{data_str}"},
                        ],
                    }
                ],
            }
            async with traced_call(
                "anthropic.haiku",
                request={"prompt": prompt, "data": data_str, "model": model, "max_tokens": 512},
                metadata={"model": model, "task": "AI Filter (Haiku)"},
            ) as t:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()
                if t:
                    t["response"] = _anthropic_response_summary(result)
            _accumulate_tokens(result)
            return result["content"][0]["text"].strip()
    except Exception as e:
        raise handle_anthropic_error(e, "Haiku AI analysis")


async def analyze_with_ai(prompt: str, data: Dict[str, Any]) -> str:
    """
    Generic AI analysis function that takes a prompt and data, returns AI response

    Args:
        prompt: The analysis prompt/instruction for the AI
        data: The data to analyze (will be converted to JSON string)

    Returns:
        AI's response as a string
    """
    set_usage_task("AI Analysis")
    try:
        api_key = get_claude_client()

        # Convert data to formatted JSON string
        data_str = json.dumps(data, indent=2)

        # Call Claude API with prompt caching on the instruction prefix
        model = get_active_model()
        async with httpx.AsyncClient(timeout=60.0) as client:
            payload = {
                "model": model,
                "max_tokens": 1024,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}},
                            {"type": "text", "text": f"Data to analyze:\n{data_str}"},
                        ],
                    }
                ],
            }
            async with traced_call(
                "anthropic.sonnet",
                request={"prompt": prompt, "data": data_str, "model": model, "max_tokens": 1024},
                metadata={"model": model, "task": "AI Analysis"},
            ) as t:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    },
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()
                if t:
                    t["response"] = _anthropic_response_summary(result)
            _accumulate_tokens(result)

            ai_response = result["content"][0]["text"].strip()
            logger.info(f"AI analysis completed, response length: {len(ai_response)}")

            return ai_response

    except Exception as e:
        raise handle_anthropic_error(e, "AI analysis")


async def extract_key_information(transcript: str, extraction_points: List[Dict[str, Any]], participants: List[str] = None, workflow_id: int = None, db: Optional[Session] = None) -> Dict[str, Any]:
    """
    Extract key information from transcript using Claude AI

    Args:
        transcript: The full transcript text
        extraction_points: List of extraction points with name, description, required fields
        participants: List of participant names (optional)
        workflow_id: Workflow ID to fetch universal rules from (optional)

    Returns:
        Dict containing extracted information for each extraction point
    """

    start_time = time.time()
    logger.info(f"Starting key information extraction | Transcript length: {len(transcript)} chars | Extraction points: {len(extraction_points)}")
    set_usage_task("Key Information Extraction")

    try:
        api_key = get_claude_client()
        
        # Get universal rules for this workflow if workflow_id is provided.
        # Reuse caller's session when available.
        universal_rules = ""
        if workflow_id:
            try:
                import models
                _owns = False
                _db = db
                if _db is None:
                    from database import SessionLocal
                    _db = SessionLocal()
                    _owns = True
                try:
                    workflow = _db.query(models.Workflow).filter(models.Workflow.id == workflow_id).first()
                    if workflow and workflow.universal_rules:
                        universal_rules = workflow.universal_rules.strip()
                finally:
                    if _owns:
                        _db.close()
            except Exception as e:
                logger.warning(f"Failed to fetch universal rules for workflow {workflow_id}: {str(e)}")

        # Build the extraction points description for the prompt
        extraction_descriptions = []
        for point in extraction_points:
            name = point.get("name", "")
            description = point.get("description", "")
            required = point.get("required", False)
            required_text = " (Required)" if required else " (Optional)"
            
            extraction_descriptions.append(f"- {name}{required_text}: {description}")
        
        extraction_points_text = "\n".join(extraction_descriptions)
        
        # Create the full prompt for Claude with universal rules if available
        base_instructions = "You are an expert at extracting key information from meeting transcripts. Your task is to analyze the transcript and extract specific information points as requested."
        
        # Add universal rules if they exist
        if universal_rules:
            base_instructions += f"\n\nIMPORTANT UNIVERSAL RULES TO FOLLOW:\n{universal_rules}"
        
        # Split into cacheable instruction prefix and variable data
        instruction_prefix = f"""{base_instructions}

Instructions:
1. Carefully read the entire transcript
2. Extract the requested information points
3. If information is not available or unclear, use null for that field
4. Be concise but comprehensive
5. Focus on factual information from the transcript
6. Return your response as a valid JSON object only

Please analyze the following meeting transcript and extract the requested key information:"""

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

        # Make the API call to Claude with prompt caching
        logger.info("Calling Claude API for key information extraction...")
        api_start = time.time()

        try:
            model = get_active_model()
            async with httpx.AsyncClient() as client:
                payload = {
                    "model": model,
                    "max_tokens": 3500,
                    "temperature": 0.1,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": instruction_prefix, "cache_control": {"type": "ephemeral"}},
                                {"type": "text", "text": variable_data},
                            ],
                        }
                    ],
                }
                async with traced_call(
                    "anthropic.sonnet.extract_key_info",
                    request={"prompt": instruction_prefix, "data": variable_data, "model": model, "max_tokens": 3500},
                    metadata={"model": model, "task": "Extract Key Information"},
                ) as t:
                    response = await client.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={
                            "Content-Type": "application/json",
                            "x-api-key": api_key,
                            "anthropic-version": "2023-06-01"
                        },
                        json=payload,
                        timeout=60.0
                    )
                    response.raise_for_status()
                    claude_response = response.json()
                    if t:
                        t["response"] = _anthropic_response_summary(claude_response)

                api_duration = time.time() - api_start
                logger.info(f"Claude API call completed | Duration: {api_duration:.2f}s | Status: {response.status_code}")

                _accumulate_tokens(claude_response)
                extracted_content = claude_response["content"][0]["text"]
        except Exception as e:
            raise handle_anthropic_error(e, "information extraction")
        
        # Robust JSON parsing with multiple fallback strategies
        try:
            # Clean up the response - sometimes Claude adds markdown formatting
            cleaned_content = extracted_content.strip()
            if cleaned_content.startswith("```json"):
                cleaned_content = cleaned_content.replace("```json", "").replace("```", "").strip()
            elif cleaned_content.startswith("```"):
                cleaned_content = cleaned_content.replace("```", "").strip()

            # Try parsing the cleaned content
            try:
                extracted_data = json.loads(cleaned_content)
            except json.JSONDecodeError as json_err:
                logger.warning(f"Initial JSON parsing failed: {json_err}. Attempting fixes...")

                # Strategy 1: Fix literal newlines, tabs, and carriage returns
                try:
                    fixed_content = cleaned_content.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
                    extracted_data = json.loads(fixed_content)
                    logger.info("JSON parsing succeeded after fixing control characters")
                except json.JSONDecodeError:
                    logger.warning("Control character fix failed. Attempting regex extraction...")

                    # Strategy 2: Extract fields using regex patterns
                    extracted_data = {}

                    # Try to extract each field individually using regex
                    for point in extraction_points:
                        field_name = point.get("name", "")
                        if not field_name:
                            continue

                        # Match field with various patterns (handles arrays and strings)
                        # Pattern matches: "field_name": "value" or "field_name": ["item1", "item2"]
                        pattern = rf'"{re.escape(field_name)}"\s*:\s*(\[[^\]]*\]|"[^"]*(?:\\.[^"]*)*"|null)'
                        match = re.search(pattern, cleaned_content, re.DOTALL)

                        if match:
                            try:
                                # Parse the matched value
                                value_str = match.group(1)
                                value = json.loads(value_str)
                                extracted_data[field_name] = value
                            except:
                                # If parsing fails, try to extract raw text
                                value_str = match.group(1).strip('"')
                                extracted_data[field_name] = value_str
                        else:
                            # Field not found, set to null
                            extracted_data[field_name] = None

                    if extracted_data:
                        logger.info(f"Successfully extracted {len(extracted_data)} fields using regex fallback")
                    else:
                        # Strategy 3: Return empty data with error
                        logger.error(f"All parsing strategies failed. Raw response: {cleaned_content[:500]}")
                        raise Exception(f"Could not parse JSON response after multiple attempts: {json_err}")

        except Exception as e:
            logger.error(f"Failed to parse JSON response: {str(e)}")
            logger.error(f"Raw content (first 1000 chars): {extracted_content[:1000]}")
            raise Exception(f"Claude returned invalid JSON: {str(e)}")
        
        # Add metadata
        result = {
            "extracted_information": extracted_data,
            "extraction_points": extraction_points,
            "participants_detected": participants or [],
            "model_used": get_active_model(),
            "extraction_timestamp": "",
            "status": "success"
        }

        total_duration = time.time() - start_time
        logger.info(f"Key information extraction completed | Duration: {total_duration:.2f}s | Extracted fields: {list(extracted_data.keys())}")
        return result
        
    except Exception as e:
        total_duration = time.time() - start_time
        logger.error(f"Error extracting key information after {total_duration:.2f}s: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "extracted_information": {},
            "extraction_points": extraction_points
        }


async def generate_summary(transcript: str, extracted_info: Dict[str, Any], config: Dict[str, Any] = None, workflow_id: int = None, input_data: Dict[str, Any] = None, db: Optional[Session] = None) -> str:
    """
    Generate a summary of the meeting using Claude AI with customizable prompt and style

    Args:
        transcript: The full transcript
        extracted_info: Previously extracted key information
        config: Summary configuration including prompt, style, length settings
        workflow_id: Workflow ID for variable substitution

    Returns:
        String summary of the meeting
    """

    start_time = time.time()
    logger.info(f"Starting summary generation | Transcript length: {len(transcript)} chars")
    set_usage_task("Summary Generation")

    try:
        api_key = get_claude_client()
        
        # Get universal rules for this workflow if workflow_id is provided.
        # Reuse caller's session when available.
        universal_rules = ""
        if workflow_id:
            try:
                import models
                _owns = False
                _db = db
                if _db is None:
                    from database import SessionLocal
                    _db = SessionLocal()
                    _owns = True
                try:
                    workflow = _db.query(models.Workflow).filter(models.Workflow.id == workflow_id).first()
                    if workflow and workflow.universal_rules:
                        universal_rules = workflow.universal_rules.strip()
                finally:
                    if _owns:
                        _db.close()
            except Exception as e:
                logger.warning(f"Failed to fetch universal rules for workflow {workflow_id}: {str(e)}")

        # Get configuration options
        if config is None:
            config = {}
        
        summary_prompt = config.get('summary_prompt', '')
        summary_style = config.get('summary_style', 'professional')
        max_length = config.get('max_length', 'medium')
        
        # Substitute variables in the summary prompt if provided
        if summary_prompt and input_data:
            try:
                from variable_substitution import substitute_variables
                component_outputs = input_data.get("__component_outputs__", {})
                summary_prompt = substitute_variables(
                    summary_prompt,
                    input_data,
                    component_outputs,
                    component_name="Text Generation (Summary Prompt)"
                )
            except Exception as e:
                logger.warning(f"Variable substitution failed in summary prompt: {str(e)}")
        
        # Configure max tokens based on length setting
        max_tokens_map = {
            'short': 1000,
            'medium': 4000,
            'long': 7000,
            'unlimited': 10000
        }
        max_tokens = max_tokens_map.get(max_length, 4000)
        
        # Configure style instructions
        style_instructions = {
            'professional': 'Write in a professional, formal business tone with clear structure.',
            'concise': 'Use bullet points and concise language. Focus on key facts and actionable items.',
            'detailed': 'Provide comprehensive details while maintaining clarity and organization.',
            'executive': 'Write as an executive summary with strategic insights and high-level overview.'
        }
        
        style_instruction = style_instructions.get(summary_style, style_instructions['professional'])
        
        # Build the prompt
        if summary_prompt:
            # Use custom prompt if provided
            base_prompt_start = f"""Based on this meeting transcript and extracted key information, follow this custom prompt:

{summary_prompt}"""
        else:
            # Use default prompt
            base_prompt_start = f"""Based on this meeting transcript and extracted key information, create a summary:"""
        
        # Add universal rules if they exist
        if universal_rules:
            base_prompt_start += f"""

IMPORTANT UNIVERSAL RULES TO FOLLOW:
{universal_rules}"""
        
        # Default summary instructions if no custom prompt
        default_summary = """Create a summary that covers:
1. Main discussion topics
2. Key decisions or outcomes
3. Next steps if any

"""

        # Split into cacheable instruction prefix and variable data
        instruction_prefix = f"""{base_prompt_start}

{default_summary if not summary_prompt else ""}Style guidance: {style_instruction}"""

        # Guard against context window overflow (~200k tokens = ~800k chars)
        MAX_PROMPT_CHARS = 600_000
        total_estimate = len(instruction_prefix) + len(transcript) + len(json.dumps(extracted_info.get('extracted_information', {}), indent=2))
        if total_estimate > MAX_PROMPT_CHARS:
            allowed_transcript = max(0, MAX_PROMPT_CHARS - (total_estimate - len(transcript)))
            if allowed_transcript == 0:
                transcript = "[... transcript omitted for length ...]"
            else:
                half = allowed_transcript // 2
                transcript = transcript[:half] + "\n\n[... middle of transcript omitted for length ...]\n\n" + transcript[-half:]
            logger.warning(f"[SUMMARY] Transcript too long, truncating to ~{allowed_transcript} chars (keeping start + end)")

        variable_data = f"""TRANSCRIPT:
{transcript}

EXTRACTED KEY INFORMATION:
{json.dumps(extracted_info.get('extracted_information', {}), indent=2)}"""

        logger.info(f"[SUMMARY] Calling Claude API | max_tokens={max_tokens} | prompt_length={len(instruction_prefix) + len(variable_data)} chars | model={get_active_model()}")
        api_start = time.time()

        try:
            model = get_active_model()
            async with httpx.AsyncClient() as client:
                payload = {
                    "model": model,
                    "max_tokens": max_tokens,
                    "temperature": 0.3,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": instruction_prefix, "cache_control": {"type": "ephemeral"}},
                                {"type": "text", "text": variable_data},
                            ],
                        }
                    ],
                }
                async with traced_call(
                    "anthropic.sonnet.summary",
                    request={"prompt": instruction_prefix, "data": variable_data, "model": model, "max_tokens": max_tokens},
                    metadata={"model": model, "task": "Summary Generation"},
                ) as t:
                    response = await client.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={
                            "Content-Type": "application/json",
                            "x-api-key": api_key,
                            "anthropic-version": "2023-06-01"
                        },
                        json=payload,
                        timeout=120.0
                    )
                    response.raise_for_status()
                    claude_response = response.json()
                    if t:
                        t["response"] = _anthropic_response_summary(claude_response)

                api_duration = time.time() - api_start
                logger.info(f"Claude API call (summary) completed | Duration: {api_duration:.2f}s | Status: {response.status_code}")

                _accumulate_tokens(claude_response)
                summary_result = claude_response["content"][0]["text"].strip()

                stop_reason = claude_response.get("stop_reason", "")
                if stop_reason == "max_tokens":
                    logger.warning(f"[SUMMARY] Hit max_tokens limit ({max_tokens}). Summary is truncated!")

                total_duration = time.time() - start_time
                logger.info(f"[SUMMARY] Completed | Duration: {total_duration:.2f}s | Length: {len(summary_result)} chars | stop_reason: {stop_reason}")

                return summary_result
        except Exception as e:
            raise handle_anthropic_error(e, "summary generation")

    except Exception as e:
        total_duration = time.time() - start_time
        logger.error(f"Error generating summary after {total_duration:.2f}s: {str(e)}", exc_info=True)
        return f"Summary generation failed: {str(e)}"


# Default extraction points configuration
DEFAULT_EXTRACTION_POINTS = [
    {
        "name": "Participants",
        "description": "List of people who participated in the meeting (names, roles if mentioned)",
        "required": True,
        "type": "array"
    },
    {
        "name": "Pain Points",
        "description": "Business challenges, problems, or pain points discussed during the meeting",
        "required": True,
        "type": "array"
    },
    {
        "name": "Budget",
        "description": "Budget information mentioned (budget range, constraints, or financial requirements)",
        "required": False,
        "type": "string"
    },
    {
        "name": "Timeline",
        "description": "Timeline or deadline information (project timelines, deadlines, or time-related requirements)",
        "required": False,
        "type": "string"
    },
    {
        "name": "Next Steps",
        "description": "Action items, follow-up tasks, or next steps discussed",
        "required": True,
        "type": "array"
    },
    {
        "name": "Competitors",
        "description": "Competitor names or competitive solutions mentioned during the discussion",
        "required": False,
        "type": "array"
    }
]


async def extract_and_summarize(
    transcript: str,
    extraction_points: List[Dict[str, Any]],
    config: Dict[str, Any] = None,
    participants: List[str] = None,
    workflow_id: int = None,
    input_data: Dict[str, Any] = None,
    db: Optional[Session] = None,
) -> Dict[str, Any]:
    """
    Single API call that extracts key information AND generates a summary.
    Replaces the old two-call pattern of extract_key_information + generate_summary.

    Returns:
        Dict with 'extracted_information', 'summary', and metadata
    """
    start_time = time.time()
    logger.info(f"[TEXT-GEN] Starting combined extract+summarize | Transcript: {len(transcript)} chars | Points: {len(extraction_points)}")
    set_usage_task("Extract & Summarize")

    if config is None:
        config = {}

    try:
        api_key = get_claude_client()

        # Get universal rules (reuse caller's session; fall back to a short-lived one only if none provided)
        universal_rules = ""
        if workflow_id:
            try:
                import models
                _owns_session = False
                _db = db
                if _db is None:
                    from database import SessionLocal
                    _db = SessionLocal()
                    _owns_session = True
                try:
                    workflow = _db.query(models.Workflow).filter(models.Workflow.id == workflow_id).first()
                    if workflow and workflow.universal_rules:
                        universal_rules = workflow.universal_rules.strip()
                finally:
                    if _owns_session:
                        _db.close()
            except Exception as e:
                logger.warning(f"Failed to fetch universal rules: {e}")

        # Build extraction points description
        extraction_descriptions = []
        for point in extraction_points:
            name = point.get("name", "")
            description = point.get("description", "")
            required = " (Required)" if point.get("required") else " (Optional)"
            extraction_descriptions.append(f"- {name}{required}: {description}")
        extraction_points_text = "\n".join(extraction_descriptions)

        # Summary config
        summary_prompt = config.get("summary_prompt", "")
        summary_style = config.get("summary_style", "professional")
        max_length = config.get("max_length", "medium")

        # Substitute variables in summary prompt
        if summary_prompt and input_data:
            try:
                from variable_substitution import substitute_variables
                component_outputs = input_data.get("__component_outputs__", {})
                summary_prompt = substitute_variables(
                    summary_prompt, input_data, component_outputs,
                    component_name="Text Generation (Summary Prompt)"
                )
            except Exception as e:
                logger.warning(f"Variable substitution failed in summary prompt: {e}")

        max_tokens_map = {
            'short': 1000,
            'medium': 4000,
            'long': 7000,
            'unlimited': 10000
        }
        max_tokens = max_tokens_map.get(max_length, 4000)

        style_instructions = {
            'professional': 'Write in a professional, formal business tone with clear structure.',
            'concise': 'Use bullet points and concise language. Focus on key facts and actionable items.',
            'detailed': 'Provide comprehensive details while maintaining clarity and organization.',
            'executive': 'Write as an executive summary with strategic insights and high-level overview.'
        }
        style_instruction = style_instructions.get(summary_style, style_instructions['professional'])

        # Build the summary instruction
        if summary_prompt:
            summary_instruction = f"Follow this custom prompt for the summary:\n{summary_prompt}"
        else:
            summary_instruction = """Create a summary that covers:
1. Main discussion topics
2. Key decisions or outcomes
3. Next steps if any"""

        # Build system prompt
        system_prompt = "You are an expert at analyzing meeting transcripts. You will extract structured information AND generate a summary in a single response."
        if universal_rules:
            system_prompt += f"\n\nIMPORTANT UNIVERSAL RULES TO FOLLOW:\n{universal_rules}"

        # Participant context
        participant_context = ""
        if participants:
            participant_context = f"\nKnown participants: {', '.join(p for p in participants if p)}\n"

        # RAG: Inject relationship context if available (auto-injected, invisible to user).
        # Cap the RAG share of the prompt BEFORE concatenation so a huge history
        # block can't squeeze the transcript out — the transcript is the primary
        # signal and its tail is usually the most salient part.
        relationship_context = ""
        if input_data and input_data.get("__relationship_context__"):
            raw_rel = str(input_data["__relationship_context__"])
            rel_budget = int(MAX_PROMPT_CHARS * RAG_BLOCK_SHARE)
            trimmed_rel = _trim_rag_formatted_by_blocks(raw_rel, rel_budget)
            if len(trimmed_rel) < len(raw_rel):
                logger.warning(
                    f"[TEXT-GEN] Relationship context {len(raw_rel)} chars exceeded "
                    f"RAG budget {rel_budget}; trimmed to {len(trimmed_rel)} chars"
                )
            relationship_context = f"""

--- RELATIONSHIP CONTEXT ---
The following is historical context about this contact from prior meetings and interactions.
Use this to enrich your analysis — reference prior decisions, track progression of pain points,
note timeline updates, and flag evolving buying signals. Do NOT mention this context block
to the user or reference it as a separate data source.

{trimmed_rel}
--- END RELATIONSHIP CONTEXT ---
"""
            logger.info(f"[TEXT-GEN] Injecting relationship context ({len(relationship_context)} chars)")

        # Split into cacheable instruction prefix and variable transcript
        instruction_part = f"""Analyze the following meeting transcript. You must produce TWO things in your response:

1. **EXTRACTED INFORMATION** — a JSON object extracting these specific data points:
{extraction_points_text}

2. **SUMMARY** — a meeting summary following these instructions:
{summary_instruction}

Style guidance: {style_instruction}
{participant_context}{relationship_context}"""

        # Budget: transcript gets whatever's left after fixed prompt + RAG + headroom.
        # The +200 reserves space for the response-format template appended below.
        fixed_overhead = len(system_prompt) + len(instruction_part) + 200
        transcript_budget = MAX_PROMPT_CHARS - fixed_overhead - PROMPT_CHAR_HEADROOM
        original_transcript_len = len(transcript)
        if transcript_budget <= 0:
            transcript = "[... transcript omitted for length ...]"
            logger.warning(
                f"[TEXT-GEN] Fixed overhead ({fixed_overhead} chars) left no room for transcript; omitting"
            )
        elif len(transcript) > transcript_budget:
            half = transcript_budget // 2
            transcript = transcript[:half] + "\n\n[... middle of transcript omitted for length ...]\n\n" + transcript[-half:]
            logger.warning(
                f"[TEXT-GEN] Transcript {original_transcript_len} chars truncated to "
                f"~{transcript_budget} chars to fit MAX_PROMPT_CHARS={MAX_PROMPT_CHARS}"
            )

        rag_chars = len(relationship_context)
        transcript_chars = len(transcript)
        total_chars = fixed_overhead + transcript_chars
        logger.info(
            f"[TEXT-GEN] Prompt budget: total={total_chars} (~{_approx_tokens(total_chars)} tok), "
            f"rag={rag_chars} (~{_approx_tokens(rag_chars)} tok), "
            f"transcript={transcript_chars} (~{_approx_tokens(transcript_chars)} tok), "
            f"headroom={PROMPT_CHAR_HEADROOM}"
        )

        transcript_part = f"""TRANSCRIPT:
{transcript}

---

RESPOND IN EXACTLY THIS FORMAT (no other text before or after):

```json
{{EXTRACTED_INFO_JSON}}
```

---SUMMARY---
{{YOUR_SUMMARY_HERE}}"""

        logger.info(f"[TEXT-GEN] Calling Claude API | max_tokens={max_tokens} | prompt_length={len(system_prompt) + len(instruction_part) + len(transcript_part)} chars | model={get_active_model()}")

        try:
            model = get_active_model()
            async with httpx.AsyncClient() as client:
                payload = {
                    "model": model,
                    "max_tokens": max_tokens,
                    "system": [
                        {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}
                    ],
                    "temperature": 0.3,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": instruction_part, "cache_control": {"type": "ephemeral"}},
                            {"type": "text", "text": transcript_part},
                        ]
                    }]
                }
                async with traced_call(
                    "anthropic.sonnet.extract_and_summarize",
                    request={"system": system_prompt, "instruction": instruction_part, "transcript": transcript_part, "model": model, "max_tokens": max_tokens},
                    metadata={"model": model, "task": "Extract and Summarize"},
                ) as t:
                    response = await client.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={
                            "Content-Type": "application/json",
                            "x-api-key": api_key,
                            "anthropic-version": "2023-06-01"
                        },
                        json=payload,
                        timeout=120.0
                    )
                    response.raise_for_status()
                    claude_response = response.json()
                    if t:
                        t["response"] = _anthropic_response_summary(claude_response)
                _accumulate_tokens(claude_response)
        except Exception as e:
            raise handle_anthropic_error(e, "extract and summarize")

        raw_text = claude_response["content"][0]["text"].strip()
        stop_reason = claude_response.get("stop_reason", "")
        if stop_reason == "max_tokens":
            logger.warning(f"[TEXT-GEN] Hit max_tokens limit ({max_tokens}). Output may be truncated!")

        logger.info(f"[TEXT-GEN] API response received | {len(raw_text)} chars | stop_reason={stop_reason}")

        # Parse the response: JSON block + summary after ---SUMMARY---
        extracted_data = {}
        summary_text = ""

        if "---SUMMARY---" in raw_text:
            parts = raw_text.split("---SUMMARY---", 1)
            json_part = parts[0].strip()
            summary_text = parts[1].strip()
        else:
            # Fallback: try to find JSON block and treat the rest as summary
            json_part = raw_text
            summary_text = ""

        # Parse JSON from the extraction part
        cleaned_json = json_part
        if "```json" in cleaned_json:
            cleaned_json = cleaned_json.split("```json", 1)[1]
        if "```" in cleaned_json:
            cleaned_json = cleaned_json.split("```", 1)[0]
        cleaned_json = cleaned_json.strip()

        if cleaned_json:
            try:
                extracted_data = json.loads(cleaned_json)
            except json.JSONDecodeError:
                logger.warning(f"[TEXT-GEN] JSON parsing failed, trying control char fix...")
                try:
                    fixed = cleaned_json.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
                    extracted_data = json.loads(fixed)
                except json.JSONDecodeError:
                    logger.warning(f"[TEXT-GEN] JSON fix failed, trying regex extraction...")
                    for point in extraction_points:
                        field_name = point.get("name", "")
                        if not field_name:
                            continue
                        pattern = rf'"{re.escape(field_name)}"\s*:\s*(\[[^\]]*\]|"[^"]*(?:\\.[^"]*)*"|null|\{{[^}}]*\}})'
                        match = re.search(pattern, cleaned_json, re.DOTALL)
                        if match:
                            try:
                                extracted_data[field_name] = json.loads(match.group(1))
                            except:
                                extracted_data[field_name] = match.group(1).strip('"')
                        else:
                            extracted_data[field_name] = None

        total_duration = time.time() - start_time
        logger.info(f"[TEXT-GEN] Completed | Duration: {total_duration:.2f}s | Extracted: {list(extracted_data.keys())} | Summary: {len(summary_text)} chars")

        return {
            "status": "success",
            "extracted_information": extracted_data,
            "summary": summary_text,
            "model_used": get_active_model(),
        }

    except Exception as e:
        total_duration = time.time() - start_time
        logger.error(f"[TEXT-GEN] Failed after {total_duration:.2f}s: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "extracted_information": {},
            "summary": f"Text generation failed: {str(e)}",
        }


async def generate_email_content(prompt: str, context: Dict[str, Any], workflow_id: int = None, db: Optional[Session] = None) -> str:
    """
    Generate email content using Claude AI based on a prompt and context.
    (Legacy function — generate_email_with_metadata is preferred.)

    Args:        prompt: The instruction/template for email generation
        context: Context data including transcript, extracted info, summary, etc.
        workflow_id: Workflow ID to fetch universal rules from (optional)

    Returns:
        Generated email body text
    """
    set_usage_task("Email Content Generation")
    try:
        api_key = get_claude_client()

        # Get universal rules for this workflow if workflow_id is provided.
        # Reuse caller's session when available.
        universal_rules = ""
        if workflow_id:
            try:
                import models
                _owns = False
                _db = db
                if _db is None:
                    from database import SessionLocal
                    _db = SessionLocal()
                    _owns = True
                try:
                    workflow = _db.query(models.Workflow).filter(models.Workflow.id == workflow_id).first()
                    if workflow and workflow.universal_rules:
                        universal_rules = workflow.universal_rules.strip()
                finally:
                    if _owns:
                        _db.close()
            except Exception as e:
                logger.warning(f"Could not fetch universal rules: {str(e)}")

        # Build the email generation prompt
        system_prompt = "You are a professional email writer. Generate clear, concise, and professional emails based on the provided context and instructions."

        if universal_rules:
            system_prompt += f"\n\nIMPORTANT RULES:\n{universal_rules}"

        # Build context string
        context_parts = []

        if context.get("transcript"):
            context_parts.append(f"Meeting Transcript:\n{context['transcript'][:2000]}")  # Limit to first 2000 chars

        if context.get("extracted_information"):
            context_parts.append(f"\nExtracted Information:\n{json.dumps(context['extracted_information'], indent=2)}")

        if context.get("summary"):
            context_parts.append(f"\nMeeting Summary:\n{context['summary']}")

        if context.get("participants"):
            participants_str = ", ".join([p.get("name", p) if isinstance(p, dict) else p for p in context["participants"]])
            context_parts.append(f"\nParticipants: {participants_str}")

        if context.get("meeting_title"):
            context_parts.append(f"\nMeeting Title: {context['meeting_title']}")

        context_str = "\n".join(context_parts)

        # Combine prompt with context
        full_prompt = f"""
{prompt}

Context:
{context_str}

Generate ONLY the email body. Do NOT include a subject line. Write in a professional, clear, and concise manner.
"""

        # Call Claude API with prompt caching on system prompt
        model = get_active_model()
        async with httpx.AsyncClient(timeout=60.0) as client:
            payload = {
                "model": model,
                "max_tokens": 2048,
                "system": [
                    {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}
                ],
                "messages": [
                    {"role": "user", "content": full_prompt}
                ]
            }
            async with traced_call(
                "anthropic.sonnet.email_content",
                request={"system": system_prompt, "user": full_prompt, "model": model, "max_tokens": 2048},
                metadata={"model": model, "task": "Email Content Generation"},
            ) as t:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    },
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()
                if t:
                    t["response"] = _anthropic_response_summary(result)
            _accumulate_tokens(result)

            email_body = result["content"][0]["text"].strip()
            logger.info(f"Email content generated, length: {len(email_body)}")

            return email_body

    except Exception as e:
        logger.error(f"Email generation error: {str(e)}")
        # Return a fallback template instead of failing
        return f"""Thank you for the meeting. Based on our discussion, I wanted to follow up on the key points we covered.

{prompt}

Please let me know if you have any questions."""


def build_resource_manifest(account_id: int, component_config: dict, db: Optional[Session] = None) -> str:
    """
    Build the resource manifest string for injection into the AI email prompt.
    Returns empty string if resources are disabled or none are configured.

    Reuses the caller's db session when provided.
    """
    if not component_config.get("resources_enabled"):
        logger.debug("[RESOURCES] build_resource_manifest: resources_enabled is falsy, returning empty")
        return ""

    resource_configs = {}
    for rc in component_config.get("resource_config", []):
        resource_configs[str(rc.get("resource_id", ""))] = rc
    logger.debug(f"[RESOURCES] resource_configs from component: {resource_configs}")

    import models
    _owns = False
    _db = db
    if _db is None:
        from database import SessionLocal
        _db = SessionLocal()
        _owns = True
    try:
        resources = (
            _db.query(models.Resource)
            .filter(models.Resource.account_id == account_id, models.Resource.is_active == True)
            .all()
        )
    finally:
        if _owns:
            _db.close()

    if not resources:
        logger.warning(f"[RESOURCES] No active resources found for account_id={account_id}")
        return ""

    logger.debug(f"[RESOURCES] Found {len(resources)} active resources in DB: {[(r.id, r.label, r.type) for r in resources]}")

    # First pass: categorize resources by mode to build accurate header instructions
    always_resources = []
    optional_resources = []
    for resource in resources:
        rc = resource_configs.get(str(resource.id), {})
        mode = rc.get("usage_mode", "disabled")
        logger.debug(f"[RESOURCES] Resource id={resource.id} label='{resource.label}': config_lookup_key='{resource.id}', matched_config={rc}, resolved_mode='{mode}'")
        if mode == "disabled":
            continue
        if mode == "always":
            always_resources.append((resource, rc))
        else:
            optional_resources.append((resource, rc, mode))

    if not always_resources and not optional_resources:
        logger.warning(f"[RESOURCES] All resources resolved to 'disabled'. resource_configs keys={list(resource_configs.keys())}, DB resource ids={[r.id for r in resources]}")
        return ""

    logger.info(f"[RESOURCES] Building manifest: {len(always_resources)} ALWAYS, {len(optional_resources)} optional")

    lines = [
        "",
        "AVAILABLE RESOURCES:",
        "Rules: Max 1 link and 1 attachment per email.",
        'For links: hyperlink the label text naturally within a sentence using <a href="resource:ID">Label</a> format.',
        "For attachments: reference the file naturally in the body. Include the resource ID in the resources_used.attachments array.",
    ]

    # Add mode-aware header instructions
    if always_resources:
        lines.append("MANDATORY: Resources marked REQUIRED below MUST be included in every email. This is non-negotiable.")
    if optional_resources:
        lines.append("For optional resources, only include if contextually appropriate. If nothing fits, omit them.")
    lines.append("")

    # ALWAYS resources first (most important)
    for resource, rc in always_resources:
        type_label = "LINK" if resource.type == "link" else "ATTACHMENT"
        lines.append(f'{type_label}: "{resource.label}" (ID: {resource.id})')
        if resource.type == "link":
            lines.append(f"  URL: {resource.url}")
        else:
            lines.append(f"  File: {resource.file_original_name or resource.label}")
        lines.append("  MODE: REQUIRED — You MUST include this resource in the email.")
        lines.append("")

    # Optional resources
    for resource, rc, mode in optional_resources:
        type_label = "LINK" if resource.type == "link" else "ATTACHMENT"

        if mode == "ai_decides":
            lines.append(f'{type_label}: "{resource.label}" (ID: {resource.id})')
            if resource.type == "link":
                lines.append(f"  URL: {resource.url}")
            else:
                lines.append(f"  File: {resource.file_original_name or resource.label}")
            lines.append("  MODE: Optional — include only when contextually appropriate")
            lines.append(f"  CONTEXT: {resource.description or 'No description'}")
            lines.append("")

        elif mode == "custom_prompt":
            lines.append(f'{type_label}: "{resource.label}" (ID: {resource.id})')
            if resource.type == "link":
                lines.append(f"  URL: {resource.url}")
            else:
                lines.append(f"  File: {resource.file_original_name or resource.label}")
            lines.append("  MODE: Follow these instructions exactly:")
            lines.append(f"  {rc.get('custom_prompt', '')}")
            lines.append("")

    manifest = "\n".join(lines)
    logger.info(f"[RESOURCES] Final manifest ({len(manifest)} chars):\n{manifest}")
    return manifest


async def generate_email_with_metadata(
    prompt: str,
    delivery_settings: Dict[str, Any],
    workflow_id: int = None,
    input_data: Dict[str, Any] = None,
    db: Optional[Session] = None,
) -> Dict[str, Any]:
    """
    Generate complete email with subject, body, and optimal send time using Claude AI.

    The prompt contains the user's instructions (with variables substituted).
    input_data provides additional pipeline context (summary, extracted info, participants)
    so the AI can write highly personalized emails even if the prompt doesn't reference
    every available data point.

    Args:
        prompt: The user's email generation prompt (already has variables substituted with actual data)
        delivery_settings: Delivery settings configuration (send_timing, constraints, etc.)
        workflow_id: Workflow ID to fetch universal rules from (optional)
        input_data: Pipeline execution data (summary, extracted_information, participants, etc.)

    Returns:
        Dict with email_subject, email_body, and email_time (human-readable time description)
    """
    set_usage_task("Email Generation")
    try:
        api_key = get_claude_client()

        # Get universal rules and signature status for this workflow.
        # Reuse caller's session; only spin up a short-lived one if none was passed.
        universal_rules = ""
        has_signature = False
        if workflow_id:
            try:
                import models
                _owns_session = False
                _db = db
                if _db is None:
                    from database import SessionLocal
                    _db = SessionLocal()
                    _owns_session = True
                try:
                    workflow = _db.query(models.Workflow).filter(models.Workflow.id == workflow_id).first()
                    if workflow:
                        if workflow.universal_rules:
                            universal_rules = workflow.universal_rules.strip()
                        # Check if the workflow owner has a signature configured
                        owner = _db.query(models.User).filter(models.User.id == workflow.owner_id).first()
                        if owner and owner.email_signature_enabled and owner.email_signature:
                            has_signature = True
                finally:
                    if _owns_session:
                        _db.close()
            except Exception as e:
                logger.warning(f"Could not fetch workflow context: {str(e)}")

        # Build the email generation prompt
        system_prompt = "You are a professional email writer and scheduling expert. Generate effective emails with optimal subject lines and send times based on the user's instructions and delivery settings."

        if universal_rules:
            system_prompt += f"\n\nIMPORTANT UNIVERSAL RULES:\n{universal_rules}"

        if has_signature:
            system_prompt += "\n\nSIGNATURE RULE: The user has a custom email signature that will be automatically appended. Do NOT include any sign-off, closing, or signature (like 'Best regards', 'Sincerely', 'Thanks', name, title, etc.) at the end of the email body. End with your last substantive sentence or call-to-action. The signature block handles the closing."

        # Resource manifest — inject into system prompt if resources are enabled
        resource_manifest = ""
        if input_data:
            component_config = input_data.get("__component_config__", {})
            resource_account_id = input_data.get("__account_id__")

            # Fallback: derive account_id from the configured resource IDs.
            # Reuse caller's session; only create one if we weren't given one.
            if not resource_account_id and component_config.get("resources_enabled"):
                resource_configs = component_config.get("resource_config", [])
                if resource_configs:
                    first_rid = resource_configs[0].get("resource_id")
                    if first_rid:
                        import models as _m
                        _owns = False
                        _rdb = db
                        if _rdb is None:
                            from database import SessionLocal
                            _rdb = SessionLocal()
                            _owns = True
                        try:
                            res = _rdb.query(_m.Resource).filter(_m.Resource.id == int(first_rid)).first()
                            if res:
                                resource_account_id = res.account_id
                                logger.info(f"[RESOURCES] account_id={resource_account_id} derived from resource_id={first_rid}")
                        except (ValueError, TypeError):
                            logger.warning(f"[RESOURCES] Non-numeric resource_id in config: {first_rid}")
                        finally:
                            if _owns:
                                _rdb.close()

            logger.info(f"[RESOURCES] account_id={resource_account_id}, resources_enabled={component_config.get('resources_enabled')}, resource_config={component_config.get('resource_config')}")
            if resource_account_id and component_config.get("resources_enabled"):
                try:
                    resource_manifest = build_resource_manifest(resource_account_id, component_config, db=db)
                    logger.info(f"[RESOURCES] manifest built, length={len(resource_manifest)}")
                except Exception as e:
                    logger.warning(f"Failed to build resource manifest: {e}")
            else:
                logger.warning(f"[RESOURCES] skipped — account_id={'present' if resource_account_id else 'MISSING'}, resources_enabled={component_config.get('resources_enabled')}")
        else:
            logger.warning("[RESOURCES] skipped — no input_data available")

        if resource_manifest:
            system_prompt += f"\n{resource_manifest}"
            logger.info("[RESOURCES] manifest injected into system prompt")
        else:
            logger.warning("[RESOURCES] manifest is EMPTY — no resources will be included in the email")

        # Build delivery settings description
        send_timing = delivery_settings.get("send_timing", "ai_optimized")
        ai_optimization_target = delivery_settings.get("ai_optimization_target", "open_rates")
        ai_time_window = delivery_settings.get("ai_time_window", "24_hours")
        business_hours_only = delivery_settings.get("business_hours_only", True)
        respect_timezone = delivery_settings.get("respect_timezone", True)
        avoid_weekends = delivery_settings.get("avoid_weekends", False)

        # Time window mapping
        time_window_hours = {
            "24_hours": 24,
            "48_hours": 48,
            "72_hours": 72,
            "1_week": 168
        }
        window_hours = time_window_hours.get(ai_time_window, 24)

        delivery_instructions = f"""
Delivery Settings:
- Send Timing: {send_timing}
- Optimization Target: {ai_optimization_target}
- Time Window: Next {window_hours} hours
- Business Hours Only (9am-5pm): {business_hours_only}
- Respect Recipient Timezone: {respect_timezone}
- Avoid Weekends: {avoid_weekends}
"""

        # RAG (Phase 4): Retrieve the four-block email context (resources, previous outreach,
        # contact history, org context). The blocks are injected as a single invisible RAG
        # prefix after the cached system prompt. Also runs an optional Haiku sufficiency check
        # and one follow-up retrieval when the initial context is insufficient.
        rag_resource_block = ""
        rag_used_chunk_ids: List[int] = []
        if input_data:
            try:
                from rag_service import (
                    get_email_context,
                    check_context_sufficiency,
                    retrieve_context,
                    deduplicate_results,
                )

                rag_account_id = input_data.get("__account_id__")
                if not rag_account_id:
                    record_skip(type="rag.skip", reason="no_account_id", metadata={"path": "email_gen"})
                if rag_account_id:
                    # Build query from email purpose + key topics from Text Gen output
                    rag_query_parts = [prompt[:500]]  # email purpose (truncated)
                    extracted_info_for_rag = input_data.get("extracted_information", {})
                    if isinstance(extracted_info_for_rag, dict):
                        for key in ("Pain Points", "Next Steps", "Key Topics", "Action Items", "Budget"):
                            val = extracted_info_for_rag.get(key)
                            if val:
                                if isinstance(val, list):
                                    rag_query_parts.append(", ".join(str(v) for v in val))
                                else:
                                    rag_query_parts.append(str(val))
                    rag_query = " ".join(rag_query_parts)

                    # Smart Context Diversity: pull used_chunk_ids and toggle from input_data
                    rag_contact_id = input_data.get("__contact_id__")
                    rag_org_id = input_data.get("__org_id__")
                    sequence_used_ids = input_data.get("__sequence_used_chunk_ids__") or []
                    apply_diversity = bool(input_data.get("__rag_apply_diversity__", True))

                    # Reuse caller's session so the RAG retrieval + sufficiency gate
                    # don't open an extra connection per email. Only fall back to a
                    # short-lived one when invoked outside a request path.
                    _owns_rag = False
                    _rag_db = db
                    if _rag_db is None:
                        from database import SessionLocal
                        _rag_db = SessionLocal()
                        _owns_rag = True
                    try:
                        ctx = await get_email_context(
                            db=_rag_db,
                            account_id=rag_account_id,
                            query_text=rag_query,
                            contact_id=rag_contact_id,
                            org_id=rag_org_id,
                            used_chunk_ids=sequence_used_ids,
                            apply_diversity=apply_diversity,
                        )

                        formatted = ctx.get("formatted") if ctx else None

                        # Phase 6 — Haiku sufficiency gate (runs exactly here for email generation)
                        if formatted:
                            verdict, gap = await check_context_sufficiency(formatted, rag_query, db=_rag_db)
                            if verdict == "MISSING" and gap:
                                logger.info(f"[RAG] Haiku sufficiency: MISSING '{gap}' — running one compensating retrieval")
                                extra = await retrieve_context(
                                    db=_rag_db,
                                    query_text=gap,
                                    account_id=rag_account_id,
                                    source_types=["resource", "text_gen_output", "generated_email", "transcript_chunk"],
                                    contact_id=rag_contact_id,
                                    org_id=rag_org_id,
                                    limit=3,
                                    penalize_ids=sequence_used_ids if apply_diversity else None,
                                    penalty_multiplier=(0.5 if apply_diversity else 1.0),
                                )
                                if extra:
                                    extra = deduplicate_results(extra)
                                    extra_text = "\n\n".join(
                                        f"[Gap-fill: {r['source_type']}]\n{r['chunk_text']}" for r in extra[:3]
                                    )
                                    formatted = f"{formatted}\n\n--- ADDITIONAL CONTEXT ---\n{extra_text}\n--- END ADDITIONAL CONTEXT ---"
                                    rag_used_chunk_ids.extend(r["id"] for r in extra[:3])

                        if formatted:
                            # Cap RAG share before it meets the user prompt. Blocks are
                            # emitted in priority order (resources > outreach > contact
                            # history > org context), so trimming from the tail drops
                            # the lowest-priority context first.
                            rag_cap = int(MAX_PROMPT_CHARS * RAG_BLOCK_SHARE)
                            trimmed_formatted = _trim_rag_formatted_by_blocks(formatted, rag_cap)
                            if len(trimmed_formatted) < len(formatted):
                                logger.warning(
                                    f"[RAG] Formatted context {len(formatted)} chars exceeded "
                                    f"cap {rag_cap}; trimmed to {len(trimmed_formatted)} chars"
                                )
                            rag_resource_block = f"\n\n{trimmed_formatted}\n"
                            rag_used_chunk_ids.extend(ctx.get("used_chunk_ids", []))
                            # Expose collected ids to caller so the email-queue row can store them
                            input_data["__rag_used_chunk_ids__"] = list(dict.fromkeys(rag_used_chunk_ids))
                            logger.info(f"[RAG] Injected {len(rag_resource_block)} chars ({len(rag_used_chunk_ids)} chunks) into email prompt")
                    finally:
                        if _owns_rag:
                            _rag_db.close()
                else:
                    logger.debug("[RAG] No account_id available, skipping retrieval")
            except Exception as e:
                logger.warning(f"[RAG] Email context retrieval failed (non-blocking): {e}")

        # Build pipeline context from input_data so the AI has meeting details
        pipeline_context = ""
        if input_data:
            context_parts = []

            # Include summary if available
            summary = input_data.get("summary")
            if summary and isinstance(summary, str) and len(summary.strip()) > 0:
                context_parts.append(f"Meeting Summary:\n{summary}")

            # Include extracted information (Pain Points, Action Items, etc.)
            extracted_info = input_data.get("extracted_information", {})
            if isinstance(extracted_info, dict) and extracted_info:
                info_lines = []
                for key, value in extracted_info.items():
                    if isinstance(value, list):
                        formatted = ", ".join(str(v) for v in value)
                    elif isinstance(value, dict):
                        import json as _json
                        formatted = _json.dumps(value, indent=2)
                    else:
                        formatted = str(value)
                    info_lines.append(f"- {key}: {formatted}")
                if info_lines:
                    context_parts.append("Extracted Information:\n" + "\n".join(info_lines))

            # Include participant details
            participants = input_data.get("participants", [])
            if participants:
                participant_lines = []
                for p in participants:
                    if isinstance(p, dict):
                        name = p.get("name", "Unknown")
                        email = p.get("email", "")
                        participant_lines.append(f"- {name} ({email})" if email else f"- {name}")
                    elif isinstance(p, str):
                        participant_lines.append(f"- {p}")
                if participant_lines:
                    context_parts.append("Participants:\n" + "\n".join(participant_lines))

            # Include meeting title if available
            meeting_title = input_data.get("meeting_title")
            if meeting_title:
                context_parts.append(f"Meeting Title: {meeting_title}")

            if context_parts:
                pipeline_context = "\n\n--- Meeting/Pipeline Context ---\n" + "\n\n".join(context_parts) + "\n--- End Context ---\n"

        # Build resource-conditional prompt parts
        body_resource_hint = ""
        resources_used_field = ""
        resources_used_example = ""
        has_always = False
        if resource_manifest:
            # Check if any resources are marked "always" in the component config
            if input_data:
                cc = input_data.get("__component_config__", {})
                for rc in cc.get("resource_config", []):
                    if rc.get("usage_mode") == "always":
                        has_always = True
                        break

            if has_always:
                body_resource_hint = ' The body MUST be HTML formatted. You MUST include all REQUIRED resources listed in the system prompt — this is mandatory, not optional. Use <a href="resource:ID">Label</a> to hyperlink link resources. If you reference a file attachment, mention it naturally in the text.'
                resources_used_field = '\n6. **resources_used** (REQUIRED): An object with "links" (array of resource IDs used as hyperlinks) and "attachments" (array of resource IDs for file attachments). You MUST include all resource IDs marked REQUIRED in the system prompt. This field is mandatory when REQUIRED resources exist.'
            else:
                body_resource_hint = ' The body MUST be HTML formatted. Use <a href="resource:ID">Label</a> to hyperlink any resources you decide to include. If you reference a file attachment, mention it naturally in the text.'
                resources_used_field = '\n6. **resources_used**: An object with "links" (array of resource IDs used as hyperlinks) and "attachments" (array of resource IDs for file attachments). Only include IDs of resources you actually used. Omit this field if no resources were used.'
            resources_used_example = ',\n    "resources_used": {"links": [1], "attachments": [4]}'

        # Final budget enforcement for the user-message prompt. The system
        # prompt is small and fixed; the user message carries RAG + pipeline
        # context + the user's instructions and can grow unbounded without
        # this. Preservation order (highest priority last to trim):
        #   1. User's email instructions (prompt)  — never touch
        #   2. Pipeline context (summary/extracted info) — trim second
        #   3. RAG block                          — trim first (already capped above)
        delivery_and_template_overhead = 2000  # rough size of static template below
        fixed_user_msg = len(prompt) + len(delivery_instructions) + delivery_and_template_overhead
        user_msg_budget = MAX_PROMPT_CHARS - len(system_prompt) - PROMPT_CHAR_HEADROOM
        dynamic_budget = user_msg_budget - fixed_user_msg
        dynamic_used = len(rag_resource_block) + len(pipeline_context)
        if dynamic_used > dynamic_budget and dynamic_budget > 0:
            # Shrink pipeline_context first (summary tolerates a tail cut).
            overflow = dynamic_used - dynamic_budget
            if len(pipeline_context) > 0 and overflow > 0:
                keep = max(0, len(pipeline_context) - overflow)
                if keep < len(pipeline_context):
                    original_pipeline_len = len(pipeline_context)
                    pipeline_context = pipeline_context[:keep] + "\n[... pipeline context truncated ...]\n"
                    logger.warning(
                        f"[EMAIL-GEN] Pipeline context truncated {original_pipeline_len}→{len(pipeline_context)} chars to fit budget"
                    )
            # If still overflowing, shrink RAG block from the tail (drops ORG CONTEXT first via _trim).
            if (len(rag_resource_block) + len(pipeline_context)) > dynamic_budget and len(rag_resource_block) > 0:
                new_rag_cap = max(0, dynamic_budget - len(pipeline_context))
                new_rag = _trim_rag_formatted_by_blocks(rag_resource_block, new_rag_cap)
                if len(new_rag) < len(rag_resource_block):
                    logger.warning(
                        f"[EMAIL-GEN] RAG block re-trimmed {len(rag_resource_block)}→{len(new_rag)} chars to fit remaining budget"
                    )
                rag_resource_block = new_rag

        rag_chars = len(rag_resource_block)
        pipeline_chars = len(pipeline_context)
        prompt_chars = len(prompt)
        total_chars = len(system_prompt) + rag_chars + pipeline_chars + fixed_user_msg
        logger.info(
            f"[EMAIL-GEN] Prompt budget: total={total_chars} (~{_approx_tokens(total_chars)} tok), "
            f"system={len(system_prompt)}, rag={rag_chars} (~{_approx_tokens(rag_chars)} tok), "
            f"pipeline={pipeline_chars} (~{_approx_tokens(pipeline_chars)} tok), "
            f"user_instructions={prompt_chars} (~{_approx_tokens(prompt_chars)} tok), "
            f"budget={MAX_PROMPT_CHARS}, headroom={PROMPT_CHAR_HEADROOM}"
        )

        full_prompt = f"""{rag_resource_block}
{pipeline_context}

User's Email Instructions:
{prompt}
{delivery_instructions}

Please generate a complete email based on the user's instructions above. Return your response as a JSON object with these components:

1. **email_subject**: A compelling subject line that will maximize {ai_optimization_target}
2. **email_body**: The complete email body (professional and clear, following the user's instructions).{body_resource_hint}
3. **email_time**: The optimal time to send this email (as a human-readable description like "Tomorrow at 10:00 AM" or "Today at 2:30 PM")
4. **timing_reason**: A brief explanation of why you chose this send time (e.g., "Mid-morning Tuesday maximizes open rates for B2B")
5. **generation_reason**: A brief explanation of your key content/personalization decisions (e.g., "Referenced budget concern, used soft tone because no next steps confirmed"){resources_used_field}

Consider these factors for optimal send time:
- The time window constraint ({window_hours} hours from now)
- Business hours constraint: {business_hours_only}
- Weekend avoidance: {avoid_weekends}
- Optimization goal: {ai_optimization_target}
- Typical email engagement patterns (mid-morning and early afternoon are often best)

IMPORTANT: Return ONLY a valid JSON object. Make sure to properly escape all special characters (newlines as \\n, quotes as \\", etc.) in the JSON string values.

Return in this exact format:
{{
    "email_subject": "Your subject line here",
    "email_body": "Your email body here with proper\\nline breaks\\nescaped",
    "email_time": "Tomorrow at 10:00 AM",
    "timing_reason": "Brief explanation of timing choice",
    "generation_reason": "Brief explanation of content decisions"{resources_used_example}
}}
"""

        # Log the full prompts for debugging resource issues
        logger.debug(f"[EMAIL-GEN] System prompt ({len(system_prompt)} chars):\n{system_prompt}")
        logger.debug(f"[EMAIL-GEN] User prompt ({len(full_prompt)} chars):\n{full_prompt}")
        if resource_manifest:
            logger.info(f"[EMAIL-GEN] Resource hints in user prompt: body_hint={'MANDATORY' if has_always else 'optional'}, resources_used_field={'REQUIRED' if has_always else 'optional'}")

        # Call Claude API with prompt caching on system prompt
        model = get_active_model()
        async with httpx.AsyncClient(timeout=60.0) as client:
            payload = {
                "model": model,
                "max_tokens": 2048,
                "system": [
                    {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}
                ],
                "temperature": 0.7,
                "messages": [
                    {"role": "user", "content": full_prompt}
                ]
            }
            async with traced_call(
                "anthropic.sonnet.email_with_metadata",
                request={"system": system_prompt, "user": full_prompt, "model": model, "max_tokens": 2048},
                metadata={"model": model, "task": "Email With Metadata"},
            ) as t:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    },
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()
                if t:
                    t["response"] = _anthropic_response_summary(result)
            _accumulate_tokens(result)

            ai_response = result["content"][0]["text"].strip()
            logger.info(f"[EMAIL-GEN] Raw AI response ({len(ai_response)} chars):\n{ai_response[:2000]}")

            # Clean up the response - sometimes Claude adds markdown formatting
            cleaned_response = ai_response
            if cleaned_response.startswith("```json"):
                cleaned_response = cleaned_response.replace("```json", "").replace("```", "").strip()
            elif cleaned_response.startswith("```"):
                cleaned_response = cleaned_response.replace("```", "").strip()

            # Try to parse JSON - if it fails due to control characters, try to extract fields manually
            try:
                email_data = json.loads(cleaned_response)
            except json.JSONDecodeError as json_err:
                logger.warning(f"JSON parsing failed: {json_err}. Attempting manual extraction...")

                # Manual extraction using regex as fallback
                import re

                # Try to extract fields using regex patterns
                subject_match = re.search(r'"email_subject"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', cleaned_response)
                body_match = re.search(r'"email_body"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', cleaned_response, re.DOTALL)
                time_match = re.search(r'"email_time"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', cleaned_response)
                timing_reason_match = re.search(r'"timing_reason"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', cleaned_response)
                generation_reason_match = re.search(r'"generation_reason"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', cleaned_response)

                # If regex extraction fails, try a different approach: find the JSON object boundaries
                if not (subject_match and body_match and time_match):
                    # Try to find content between braces and extract using a more lenient approach
                    try:
                        # Replace literal newlines with \n
                        fixed_response = cleaned_response.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
                        email_data = json.loads(fixed_response)
                    except:
                        # Last resort: extract using simpler pattern matching
                        subject_match = re.search(r'email_subject["\s:]+([^\n,}]+)', cleaned_response)
                        body_match = re.search(r'email_body["\s:]+(.+?)(?=,?\s*"email_time)', cleaned_response, re.DOTALL)
                        time_match = re.search(r'email_time["\s:]+([^\n,}]+)', cleaned_response)
                        timing_reason_match = timing_reason_match or re.search(r'timing_reason["\s:]+([^\n,}]+)', cleaned_response)
                        generation_reason_match = generation_reason_match or re.search(r'generation_reason["\s:]+([^\n,}]+)', cleaned_response)

                        email_data = {
                            "email_subject": subject_match.group(1).strip(' "') if subject_match else "Follow-up",
                            "email_body": body_match.group(1).strip(' "') if body_match else "Email content could not be parsed.",
                            "email_time": time_match.group(1).strip(' "') if time_match else "As soon as possible",
                            "timing_reason": timing_reason_match.group(1).strip(' "') if timing_reason_match else None,
                            "generation_reason": generation_reason_match.group(1).strip(' "') if generation_reason_match else None,
                        }
                else:
                    email_data = {
                        "email_subject": subject_match.group(1) if subject_match else "Follow-up",
                        "email_body": body_match.group(1) if body_match else "Email content could not be parsed.",
                        "email_time": time_match.group(1) if time_match else "As soon as possible",
                        "timing_reason": timing_reason_match.group(1) if timing_reason_match else None,
                        "generation_reason": generation_reason_match.group(1) if generation_reason_match else None,
                    }

            logger.info(f"Email with metadata generated successfully")

            # Clean up email body — convert escaped newlines to real newlines
            raw_body = email_data.get("email_body", "")
            if isinstance(raw_body, str):
                # Replace literal \n sequences that survived JSON parsing
                raw_body = raw_body.replace("\\n", "\n").replace("\\r", "")
                # Strip any "Email Body:" prefix the AI might have added
                for prefix in ["Email Body:", "email_body:", "Body:"]:
                    if raw_body.lstrip().startswith(prefix):
                        raw_body = raw_body.lstrip()[len(prefix):].lstrip()
                        break

            result_dict = {
                "email_subject": email_data.get("email_subject", "Follow-up"),
                "email_body": raw_body,
                "email_time": email_data.get("email_time", "As soon as possible"),
                "timing_reason": email_data.get("timing_reason"),
                "generation_reason": email_data.get("generation_reason"),
            }

            # Pass through resources_used if the AI included it
            if email_data.get("resources_used"):
                result_dict["resources_used"] = email_data["resources_used"]
                logger.info(f"[EMAIL-GEN] AI included resources_used: {email_data['resources_used']}")
            elif resource_manifest:
                logger.warning(f"[EMAIL-GEN] Resource manifest was injected but AI returned NO resources_used. Parsed email_data keys: {list(email_data.keys())}")

            # Log whether resource:ID placeholders are in the body
            if resource_manifest:
                body = result_dict.get("email_body", "")
                has_resource_links = "resource:" in body
                logger.info(f"[EMAIL-GEN] Email body contains resource:ID placeholders: {has_resource_links}")
                if not has_resource_links:
                    logger.warning(f"[EMAIL-GEN] Resource manifest was present but email body has NO resource links. Body preview: {body[:500]}")

            return result_dict

    except Exception as e:
        logger.error(f"Email with metadata generation error: {str(e)}", exc_info=True)
        # Return fallback values
        return {
            "email_subject": "Follow-up from our meeting",
            "email_body": """Thank you for taking the time to meet with me. I wanted to follow up on our discussion.

Based on our conversation, I will send you additional details shortly.

Please let me know if you have any questions in the meantime.

Best regards""",
            "email_time": "As soon as possible"
        }


async def generate_email_subject(
    subject_prompt: str,
    email_body: str,
    delivery_settings: Dict[str, Any],
    workflow_id: int = None,
    db: Optional[Session] = None,
) -> str:
    """
    Generate email subject line based on custom prompt and the generated email body.

    This function is called AFTER the email body has been generated, allowing the
    subject line to reference the actual content of the email.

    Args:
        subject_prompt: The user's custom subject line generation prompt
        email_body: The already-generated email body content
        delivery_settings: Delivery settings configuration (for optimization target)
        workflow_id: Workflow ID to fetch universal rules from (optional)

    Returns:
        String containing the generated subject line
    """
    set_usage_task("Email Subject Generation")
    try:
        api_key = get_claude_client()

        # Get universal rules for this workflow if workflow_id is provided.
        # Reuse caller's session when available to avoid opening an extra connection.
        universal_rules = ""
        if workflow_id:
            try:
                import models
                _owns = False
                _db = db
                if _db is None:
                    from database import SessionLocal
                    _db = SessionLocal()
                    _owns = True
                try:
                    workflow = _db.query(models.Workflow).filter(models.Workflow.id == workflow_id).first()
                    if workflow and workflow.universal_rules:
                        universal_rules = workflow.universal_rules.strip()
                finally:
                    if _owns:
                        _db.close()
            except Exception as e:
                logger.warning(f"Could not fetch universal rules: {str(e)}")

        # Build the system prompt
        system_prompt = "You are a professional email subject line writer. Generate compelling subject lines that maximize email engagement."

        if universal_rules:
            system_prompt += f"\n\nIMPORTANT UNIVERSAL RULES:\n{universal_rules}"

        # Get optimization target
        ai_optimization_target = delivery_settings.get("ai_optimization_target", "open_rates")

        # Build the prompt for subject generation
        full_prompt = f"""
User's Subject Line Instructions:
{subject_prompt}

Email Body Context:
{email_body}

Optimization Goal: Maximize {ai_optimization_target}

Please generate a compelling email subject line based on the user's instructions above.
You have access to the email body content for context, so you can reference specific points from the email.

IMPORTANT: Return ONLY the subject line text itself, without any quotes, JSON formatting, or explanations.
Keep it concise and compelling (typically 40-60 characters for optimal display).
"""

        # Call Claude API with prompt caching on system prompt
        model = get_active_model()
        async with httpx.AsyncClient(timeout=60.0) as client:
            payload = {
                "model": model,
                "max_tokens": 256,
                "system": [
                    {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}
                ],
                "temperature": 0.7,
                "messages": [
                    {"role": "user", "content": full_prompt}
                ]
            }
            async with traced_call(
                "anthropic.sonnet.email_subject",
                request={"system": system_prompt, "user": full_prompt, "model": model, "max_tokens": 256},
                metadata={"model": model, "task": "Email Subject"},
            ) as t:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    },
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()
                if t:
                    t["response"] = _anthropic_response_summary(result)
            _accumulate_tokens(result)

            subject_line = result["content"][0]["text"].strip()

            # Clean up any quotes or formatting that might have been added
            subject_line = subject_line.strip('"\'')

            logger.info(f"Custom email subject generated successfully: {subject_line}")

            return subject_line

    except Exception as e:
        logger.error(f"Email subject generation error: {str(e)}", exc_info=True)
        # Return a fallback subject
        return "Follow-up from our meeting"


async def match_organization_with_ai(
    organizations: List[Dict[str, Any]],
    company_name: str,
    context: Dict[str, Any] = None,
    workflow_id: int = None,
    db: Optional[Session] = None,
) -> Dict[str, Any]:
    """
    Match a company name to a Pipedrive organization using AI with fuzzy pre-filtering

    Args:
        organizations: List of organizations from Pipedrive [{id, name, address, owner_id}]
        company_name: The company name to match against
        context: Additional context data (transcript, extracted info, etc.)
        workflow_id: Workflow ID to fetch universal rules from (optional)

    Returns:
        Dict containing matched organization_id and confidence score
    """
    set_usage_task("Organization Matching")
    try:
        from difflib import SequenceMatcher

        api_key = get_claude_client()

        # Get universal rules for this workflow if workflow_id is provided.
        # Reuse caller's session when available.
        universal_rules = ""
        if workflow_id:
            try:
                import models
                _owns = False
                _db = db
                if _db is None:
                    from database import SessionLocal
                    _db = SessionLocal()
                    _owns = True
                try:
                    workflow = _db.query(models.Workflow).filter(models.Workflow.id == workflow_id).first()
                    if workflow and workflow.universal_rules:
                        universal_rules = workflow.universal_rules.strip()
                finally:
                    if _owns:
                        _db.close()
            except Exception as e:
                logger.warning(f"Could not fetch universal rules: {str(e)}")

        # PRE-FILTER: Use fuzzy matching to narrow down candidates before AI
        logger.info(f"Pre-filtering {len(organizations)} organizations using fuzzy matching...")

        # Score each organization based on name similarity
        scored_orgs = []
        company_name_lower = company_name.lower().strip()

        for org in organizations:
            org_name = org.get('name', '').lower().strip()
            if not org_name:
                continue

            # Calculate similarity ratio (0.0 to 1.0)
            similarity = SequenceMatcher(None, company_name_lower, org_name).ratio()

            # Bonus points for partial matches (e.g., "Acme" matches "Acme Corporation")
            if company_name_lower in org_name or org_name in company_name_lower:
                similarity = max(similarity, 0.85)

            scored_orgs.append({
                'org': org,
                'similarity': similarity,
                'name': org.get('name', '')
            })

        # Sort by similarity (highest first) and take top 50
        scored_orgs.sort(key=lambda x: x['similarity'], reverse=True)
        top_candidates = scored_orgs[:50]

        if not top_candidates:
            logger.error("No organizations found after fuzzy filtering")
            return {
                "success": False,
                "error": "No matching organizations found",
                "organization_id": None
            }

        logger.info(f"Fuzzy pre-filter: Top match has {top_candidates[0]['similarity']:.2%} similarity ({top_candidates[0]['name']})")
        logger.info(f"Sending top {len(top_candidates)} candidates to AI for final matching")

        # Prepare the filtered organization list for AI
        org_list_str = "\n".join([
            f"ID: {item['org']['id']} | Name: {item['org']['name']}" +
            (f" | Address: {item['org']['address']}" if item['org'].get('address') else "") +
            f" | Similarity: {item['similarity']:.1%}"
            for item in top_candidates
        ])

        # Build the prompt
        system_prompt = "You are an expert at matching company names to database records. You can handle variations in naming, abbreviations, and different formats."

        if universal_rules:
            system_prompt += f"\n\nIMPORTANT UNIVERSAL RULES:\n{universal_rules}"

        # Add context information if available
        context_str = ""
        if context:
            if context.get("transcript"):
                context_str += f"\nTranscript excerpt:\n{context['transcript'][:1000]}"
            if context.get("extracted_information"):
                context_str += f"\n\nExtracted information:\n{json.dumps(context['extracted_information'], indent=2)}"

        full_prompt = f"""Given the following company name to match:
"{company_name}"
{context_str}

And this list of organizations from Pipedrive (pre-filtered and sorted by similarity):
{org_list_str}

NOTE: The organizations above are already pre-filtered using fuzzy matching and sorted by similarity score. The top matches are most likely to be correct.

Please find the best matching organization from the list. Consider:
- The similarity scores provided (higher is better)
- Exact name matches
- Common abbreviations (e.g., "Corp" vs "Corporation", "Inc" vs "Incorporated")
- Slight spelling variations
- Parent/subsidiary relationships
- Context from the transcript if provided

Return ONLY a valid JSON object with this format:
{{
    "organization_id": <the numeric ID of the matched organization>,
    "confidence": <"high", "medium", or "low">,
    "reasoning": <brief explanation of why this match was selected>
}}

If no reasonable match is found, return:
{{
    "organization_id": null,
    "confidence": "none",
    "reasoning": "No matching organization found in the list"
}}
"""

        logger.info(f"Calling Claude API for organization matching | Company: {company_name} | Org count: {len(organizations)}")

        # Call Claude API with prompt caching on system prompt
        model = get_active_model()
        async with httpx.AsyncClient(timeout=60.0) as client:
            payload = {
                "model": model,
                "max_tokens": 512,
                "system": [
                    {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}
                ],
                "temperature": 0.1,
                "messages": [
                    {"role": "user", "content": full_prompt}
                ]
            }
            async with traced_call(
                "anthropic.sonnet.match_org",
                request={"system": system_prompt, "user": full_prompt, "model": model, "max_tokens": 512},
                metadata={"model": model, "task": "Match Organization"},
            ) as t:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    },
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()
                if t:
                    t["response"] = _anthropic_response_summary(result)
            _accumulate_tokens(result)

            ai_response = result["content"][0]["text"].strip()

            cleaned_response = ai_response
            if cleaned_response.startswith("```json"):
                cleaned_response = cleaned_response.replace("```json", "").replace("```", "").strip()
            elif cleaned_response.startswith("```"):
                cleaned_response = cleaned_response.replace("```", "").strip()

            try:
                match_data = json.loads(cleaned_response)
            except json.JSONDecodeError as json_err:
                logger.error(f"JSON parsing failed: {json_err}. Response: {cleaned_response[:500]}")
                return {
                    "success": False,
                    "error": "Failed to parse AI response",
                    "organization_id": None
                }

            org_id = match_data.get("organization_id")
            confidence = match_data.get("confidence", "unknown")
            reasoning = match_data.get("reasoning", "")

            if org_id:
                logger.info(f"Organization match found | ID: {org_id} | Confidence: {confidence}")
            else:
                logger.warning(f"No organization match found | Confidence: {confidence} | Reasoning: {reasoning}")

            return {
                "success": True if org_id else False,
                "organization_id": org_id,
                "confidence": confidence,
                "reasoning": reasoning
            }

    except Exception as e:
        error = handle_anthropic_error(e, "organization matching")
        return {
            "success": False,
            "error": str(error),
            "organization_id": None
        }


async def select_deal_with_ai(
    deals: List[Dict[str, Any]],
    context: Dict[str, Any] = None,
    workflow_id: int = None
) -> Dict[str, Any]:
    """
    Select the most relevant deal from a list using AI

    Args:
        deals: List of deals from Pipedrive [{id, title, value, status, stage_id, ...}]
        context: Context data including transcript, extracted info, etc.
        workflow_id: Workflow ID to fetch universal rules from (optional)

    Returns:
        Dict containing selected deal_id and reasoning
    """
    set_usage_task("Deal Selection")
    try:
        api_key = get_claude_client()

        # Get universal rules for this workflow if workflow_id is provided
        universal_rules = ""
        if workflow_id:
            try:
                from database import get_db
                import models

                # Get database session
                db = next(get_db())
                workflow = db.query(models.Workflow).filter(models.Workflow.id == workflow_id).first()
                if workflow and workflow.universal_rules:
                    universal_rules = workflow.universal_rules.strip()
            except Exception as e:
                logger.warning(f"Could not fetch universal rules: {str(e)}")

        # Prepare the deal list for AI
        deal_list_str = "\n".join([
            f"ID: {deal['id']} | Title: {deal['title']} | Value: {deal.get('value', 'N/A')} {deal.get('currency', '')} | Status: {deal.get('status', 'N/A')} | Updated: {deal.get('update_time', 'N/A')}"
            for deal in deals[:50]  # Limit to first 50 deals
        ])

        # Build context string
        context_str = ""
        if context:
            if context.get("transcript"):
                context_str += f"\nTranscript excerpt:\n{context['transcript'][:2000]}"
            if context.get("extracted_information"):
                context_str += f"\n\nExtracted information:\n{json.dumps(context['extracted_information'], indent=2)}"
            if context.get("company_name"):
                context_str += f"\n\nCompany name: {context['company_name']}"

        # Build the prompt
        system_prompt = "You are an expert at analyzing business conversations and matching them to the most relevant sales deals."

        if universal_rules:
            system_prompt += f"\n\nIMPORTANT UNIVERSAL RULES:\n{universal_rules}"

        full_prompt = f"""Given the following context from a business conversation:
{context_str}

And this list of deals from Pipedrive:
{deal_list_str}

Please select the most relevant deal based on:
- Deal title matching topics discussed in the conversation
- Deal status (prefer active/open deals over closed ones)
- Most recent deals (based on update_time)
- Deal value relevance to the discussion
- Any specific mentions or clues in the transcript

Return ONLY a valid JSON object with this format:
{{
    "deal_id": <the numeric ID of the selected deal>,
    "confidence": <"high", "medium", or "low">,
    "reasoning": <brief explanation of why this deal was selected>
}}

If you cannot determine which deal is most relevant, select the most recently updated open deal.
"""

        logger.info(f"Calling Claude API for deal selection | Deal count: {len(deals)}")

        # Call Claude API with prompt caching on system prompt
        model = get_active_model()
        async with httpx.AsyncClient(timeout=60.0) as client:
            payload = {
                "model": model,
                "max_tokens": 512,
                "system": [
                    {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}
                ],
                "temperature": 0.2,
                "messages": [
                    {"role": "user", "content": full_prompt}
                ]
            }
            async with traced_call(
                "anthropic.sonnet.select_deal",
                request={"system": system_prompt, "user": full_prompt, "model": model, "max_tokens": 512},
                metadata={"model": model, "task": "Select Deal"},
            ) as t:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    },
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()
                if t:
                    t["response"] = _anthropic_response_summary(result)
            _accumulate_tokens(result)

            ai_response = result["content"][0]["text"].strip()

            cleaned_response = ai_response
            if cleaned_response.startswith("```json"):
                cleaned_response = cleaned_response.replace("```json", "").replace("```", "").strip()
            elif cleaned_response.startswith("```"):
                cleaned_response = cleaned_response.replace("```", "").strip()

            try:
                selection_data = json.loads(cleaned_response)
            except json.JSONDecodeError as json_err:
                logger.error(f"JSON parsing failed: {json_err}. Response: {cleaned_response[:500]}")
                # Fallback: return the first deal
                return {
                    "success": False,
                    "error": "Failed to parse AI response",
                    "deal_id": deals[0]['id'] if deals else None,
                    "reasoning": "AI parsing failed, using first deal as fallback"
                }

            logger.info(f"Deal selected | ID: {selection_data.get('deal_id')} | Confidence: {selection_data.get('confidence')}")

            return {
                "success": True,
                "deal_id": selection_data.get("deal_id"),
                "confidence": selection_data.get("confidence", "unknown"),
                "reasoning": selection_data.get("reasoning", "")
            }

    except Exception as e:
        error = handle_anthropic_error(e, "deal selection")
        # Fallback: return the first deal if available
        return {
            "success": False,
            "error": str(error),
            "deal_id": deals[0]['id'] if deals else None,
            "reasoning": f"Error occurred. Using first deal as fallback."
        }


# ============================================================================
# EMAIL SEQUENCE AI FUNCTIONS
# ============================================================================

async def generate_sequence_emails(
    transcript_summary: Dict[str, Any],
    num_emails: int = 3,
    custom_prompt: Optional[str] = None,
    tone: str = "professional",
    include_variables: List[str] = None,
    workflow_id: int = None
) -> Dict[str, Any]:
    """
    Generate email sequence content using AI based on transcript summary.

    Args:
        transcript_summary: Extracted information from the transcript
        num_emails: Number of emails to generate (default 3)
        custom_prompt: Custom instructions for generation
        tone: Email tone (professional, friendly, formal, casual)
        include_variables: List of variables to include in emails
        workflow_id: Workflow ID for universal rules

    Returns:
        Dict with emails and generation metadata
    """
    set_usage_task("Sequence Email Generation")
    try:
        api_key = get_claude_client()

        # Get universal rules and signature status if workflow_id provided
        universal_rules = ""
        has_signature = False
        if workflow_id:
            try:
                from database import get_db
                import models
                db = next(get_db())
                workflow = db.query(models.Workflow).filter(models.Workflow.id == workflow_id).first()
                if workflow:
                    if workflow.universal_rules:
                        universal_rules = workflow.universal_rules.strip()
                    owner = db.query(models.User).filter(models.User.id == workflow.owner_id).first()
                    if owner and owner.email_signature_enabled and owner.email_signature:
                        has_signature = True
            except Exception as e:
                logger.warning(f"Could not fetch workflow context: {str(e)}")

        # Build the prompt
        summary_json = json.dumps(transcript_summary, indent=2)

        variables_section = ""
        if include_variables:
            variables_section = f"""
Use these extracted variables in the emails where appropriate:
{', '.join(include_variables)}

For each variable, use the format {{{{variable_name}}}} in the email content.
"""

        tone_guidance = {
            "professional": "Maintain a professional, business-appropriate tone. Be clear and concise.",
            "friendly": "Use a warm, approachable tone while remaining professional. Add personality.",
            "formal": "Use formal business language. Be respectful and traditional in style.",
            "casual": "Use a conversational, relaxed tone while still being professional."
        }

        signature_rule = ""
        if has_signature:
            signature_rule = "\n\nSIGNATURE RULE: The user has a custom email signature that is automatically appended. Do NOT include any sign-off, closing, or signature (like 'Best regards', 'Sincerely', name, title, etc.) at the end of email bodies. End each email with the last substantive sentence or call-to-action."

        system_prompt = f"""You are an expert sales copywriter who specializes in follow-up email sequences.
{universal_rules if universal_rules else ""}{signature_rule}

TONE GUIDANCE: {tone_guidance.get(tone, tone_guidance['professional'])}
"""

        user_prompt = f"""Based on this meeting transcript summary, generate a {num_emails}-email follow-up sequence.

TRANSCRIPT SUMMARY:
{summary_json}

{variables_section}

{custom_prompt if custom_prompt else ""}

Generate {num_emails} emails with strategic timing recommendations. Each email should:
1. Build on the previous email
2. Reference specific points from the meeting
3. Provide value (not just "checking in")
4. Have a clear call-to-action

Return a JSON object with this exact structure:
{{
    "emails": [
        {{
            "order": 1,
            "name": "Initial Follow-up",
            "subject": "Subject line here",
            "body": "Email body with {{{{variable}}}} placeholders",
            "timing_recommendation": {{
                "delay_value": 1,
                "delay_unit": "days",
                "reasoning": "Why this timing"
            }},
            "purpose": "Brief description of this email's goal"
        }}
    ],
    "sequence_strategy": "Brief explanation of the overall sequence strategy"
}}

Return ONLY the JSON object, no additional text."""

        logger.info(f"Generating {num_emails} sequence emails with AI")

        model = get_active_model()
        async with httpx.AsyncClient(timeout=90.0) as client:
            payload = {
                "model": model,
                "max_tokens": 4096,
                "system": [
                    {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}
                ],
                "temperature": 0.7,
                "messages": [
                    {"role": "user", "content": user_prompt}
                ]
            }
            async with traced_call(
                "anthropic.sonnet.sequence_emails",
                request={"system": system_prompt, "user": user_prompt, "model": model, "max_tokens": 4096},
                metadata={"model": model, "task": "Generate Sequence Emails"},
            ) as t:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    },
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()
                if t:
                    t["response"] = _anthropic_response_summary(result)
            _accumulate_tokens(result)

            ai_response = result["content"][0]["text"].strip()

            # Clean up response
            cleaned_response = ai_response
            if cleaned_response.startswith("```json"):
                cleaned_response = cleaned_response.replace("```json", "").replace("```", "").strip()
            elif cleaned_response.startswith("```"):
                cleaned_response = cleaned_response.replace("```", "").strip()

            try:
                generated_data = json.loads(cleaned_response)
            except json.JSONDecodeError as e:
                logger.error(f"JSON parsing failed: {e}. Response: {cleaned_response[:500]}")
                raise Exception("Failed to parse AI response")

            logger.info(f"Successfully generated {len(generated_data.get('emails', []))} emails")

            return {
                "emails": generated_data.get("emails", []),
                "generation_metadata": {
                    "sequence_strategy": generated_data.get("sequence_strategy", ""),
                    "tone": tone,
                    "num_emails_requested": num_emails,
                    "num_emails_generated": len(generated_data.get("emails", []))
                }
            }

    except Exception as e:
        raise handle_anthropic_error(e, "email sequence generation")


async def optimize_email_timing(
    transcript_summary: Dict[str, Any],
    emails: List[Dict[str, Any]],
    custom_prompt: Optional[str] = None,
    workflow_id: int = None
) -> Dict[str, Any]:
    """
    Use AI to optimize the timing of emails in a sequence based on transcript context.

    Args:
        transcript_summary: Extracted information from the transcript
        emails: List of emails with current timing
        custom_prompt: Custom instructions for timing optimization
        workflow_id: Workflow ID for universal rules

    Returns:
        Dict with optimized timing recommendations and reasoning
    """
    set_usage_task("Email Timing Optimization")
    try:
        api_key = get_claude_client()

        # Get universal rules if workflow_id provided
        universal_rules = ""
        if workflow_id:
            try:
                from database import get_db
                import models
                db = next(get_db())
                workflow = db.query(models.Workflow).filter(models.Workflow.id == workflow_id).first()
                if workflow and workflow.universal_rules:
                    universal_rules = workflow.universal_rules.strip()
            except Exception as e:
                logger.warning(f"Could not fetch universal rules: {str(e)}")

        summary_json = json.dumps(transcript_summary, indent=2)
        emails_json = json.dumps(emails, indent=2)

        system_prompt = f"""You are an expert in sales psychology and email timing optimization.
Your goal is to recommend optimal timing for follow-up emails based on the context of sales conversations.
{universal_rules if universal_rules else ""}

Consider factors like:
- Urgency signals from the conversation
- Decision timeline mentioned
- Day of week effectiveness (Tue-Thu typically best)
- Time between touches (not too aggressive, not too sparse)
- Buyer engagement level
"""

        user_prompt = f"""Analyze this transcript summary and current email sequence timing.
Recommend optimal timing adjustments.

TRANSCRIPT SUMMARY:
{summary_json}

CURRENT EMAIL SEQUENCE:
{emails_json}

{custom_prompt if custom_prompt else ""}

Return a JSON object with this structure:
{{
    "optimized_timing": [
        {{
            "email_order": 1,
            "original_delay": "1 days",
            "recommended_delay_value": 1,
            "recommended_delay_unit": "days",
            "recommended_day": null,
            "recommended_time": "10:00",
            "confidence": "high",
            "reasoning": "Why this timing is optimal"
        }}
    ],
    "reasoning": "Overall strategy explanation",
    "urgency_detected": "high/medium/low",
    "decision_timeline": "immediate/short-term/long-term/unknown"
}}

Return ONLY the JSON object."""

        logger.info("Optimizing email timing with AI")

        model = get_active_model()
        async with httpx.AsyncClient(timeout=60.0) as client:
            payload = {
                "model": model,
                "max_tokens": 2048,
                "system": [
                    {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}
                ],
                "temperature": 0.3,
                "messages": [
                    {"role": "user", "content": user_prompt}
                ]
            }
            async with traced_call(
                "anthropic.sonnet.optimize_timing",
                request={"system": system_prompt, "user": user_prompt, "model": model, "max_tokens": 2048},
                metadata={"model": model, "task": "Optimize Email Timing"},
            ) as t:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    },
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()
                if t:
                    t["response"] = _anthropic_response_summary(result)
            _accumulate_tokens(result)

            ai_response = result["content"][0]["text"].strip()

            # Clean up response
            cleaned_response = ai_response
            if cleaned_response.startswith("```json"):
                cleaned_response = cleaned_response.replace("```json", "").replace("```", "").strip()
            elif cleaned_response.startswith("```"):
                cleaned_response = cleaned_response.replace("```", "").strip()

            try:
                timing_data = json.loads(cleaned_response)
            except json.JSONDecodeError as e:
                logger.error(f"JSON parsing failed: {e}. Response: {cleaned_response[:500]}")
                raise Exception("Failed to parse AI timing response")

            logger.info(f"Successfully optimized timing for {len(timing_data.get('optimized_timing', []))} emails")

            return {
                "optimized_timing": timing_data.get("optimized_timing", []),
                "reasoning": timing_data.get("reasoning", ""),
                "metadata": {
                    "urgency_detected": timing_data.get("urgency_detected", "unknown"),
                    "decision_timeline": timing_data.get("decision_timeline", "unknown")
                }
            }

    except Exception as e:
        raise handle_anthropic_error(e, "email timing optimization")


async def check_sequence_skip_conditions(
    skip_conditions: List[Dict[str, Any]],
    context_data: Dict[str, Any],
    workflow_id: int = None
) -> Dict[str, Any]:
    """
    Check if a sequence should be skipped based on conditions and context.

    Args:
        skip_conditions: List of skip condition rules
        context_data: Context including CRM data, transcript data, etc.
        workflow_id: Workflow ID for logging

    Returns:
        Dict with should_skip boolean and reason
    """
    set_usage_task("Skip Condition Check")
    try:
        for condition in skip_conditions:
            condition_type = condition.get("type")
            operator = condition.get("operator")
            value = condition.get("value")
            field = condition.get("field")

            # Get the actual value from context
            if condition_type == "deal_stage":
                actual_value = context_data.get("deal", {}).get("stage_id") or context_data.get("deal", {}).get("stage")
            elif condition_type == "deal_status":
                actual_value = context_data.get("deal", {}).get("status")
            elif condition_type == "contact_field":
                actual_value = context_data.get("contact", {}).get(field)
            elif condition_type == "reply_received":
                actual_value = context_data.get("reply_received", False)
            elif condition_type == "days_since_last_email":
                actual_value = context_data.get("days_since_last_email", 0)
            else:
                logger.warning(f"Unknown skip condition type: {condition_type}")
                continue

            # Evaluate condition
            skip = False
            if operator == "equals":
                skip = str(actual_value).lower() == str(value).lower()
            elif operator == "not_equals":
                skip = str(actual_value).lower() != str(value).lower()
            elif operator == "contains":
                skip = str(value).lower() in str(actual_value).lower()
            elif operator == "greater_than":
                skip = float(actual_value or 0) > float(value)
            elif operator == "less_than":
                skip = float(actual_value or 0) < float(value)
            elif operator == "is_true":
                skip = bool(actual_value) == True
            elif operator == "is_false":
                skip = bool(actual_value) == False

            if skip:
                reason = f"Skip condition met: {condition_type} {operator} {value}"
                logger.info(f"Sequence skip triggered for workflow {workflow_id}: {reason}")
                return {
                    "should_skip": True,
                    "reason": reason,
                    "condition": condition
                }

        return {
            "should_skip": False,
            "reason": None,
            "condition": None
        }

    except Exception as e:
        logger.error(f"Error checking skip conditions: {str(e)}")
        # Don't skip on error - let the sequence proceed
        return {
            "should_skip": False,
            "reason": f"Error checking conditions: {str(e)}",
            "condition": None
        }


# ============================================================================
# EMAIL QUEUE ENHANCEMENT AI FUNCTIONS
# ============================================================================

async def ai_edit_email_content(
    original_subject: str,
    original_body: str,
    edit_prompt: str,
    contact_context: Optional[Dict[str, Any]] = None,
    has_signature: bool = False,
) -> Dict[str, Any]:
    """
    Use AI to make a small tweak to an email based on user instruction.

    This function is designed for quick, targeted edits to queued emails.
    It makes minimal changes (max ~30 words added) based on the user's prompt.

    Args:
        original_subject: The current email subject
        original_body: The current email body
        edit_prompt: User's instruction for the edit (e.g., "acknowledge her reply about liking the proposal")
        contact_context: Optional context about the contact (name, company, recent activities)

    Returns:
        Dict with modified_subject, modified_body, and changes_summary
    """
    set_usage_task("Email Edit")
    try:
        api_key = get_claude_client()

        # Build context section if available
        context_section = ""
        if contact_context:
            context_parts = []
            if contact_context.get("name"):
                context_parts.append(f"Contact: {contact_context['name']}")
            if contact_context.get("company"):
                context_parts.append(f"Company: {contact_context['company']}")
            if contact_context.get("recent_activities"):
                activities = contact_context["recent_activities"][:3]  # Limit to 3 most recent
                activity_strs = [f"- {a['type']}: {a['title']} ({a['date']})" for a in activities]
                context_parts.append(f"Recent Activity:\n" + "\n".join(activity_strs))

            if context_parts:
                context_section = f"""
CONTACT CONTEXT:
{chr(10).join(context_parts)}
"""

        signature_rule = ""
        if has_signature:
            signature_rule = "\n7. The user has a custom email signature appended automatically. Do NOT add any sign-off, closing, or signature (like 'Best regards', 'Sincerely', name, etc.). End with the last substantive sentence."

        system_prompt = f"""You are a professional email editor. Your task is to make minimal, targeted edits to emails based on user instructions.

IMPORTANT RULES:
1. Make MINIMAL changes - only modify what's necessary to address the user's request
2. Add no more than ~30 words to address the instruction
3. Maintain the email's original tone and style
4. Keep the overall structure intact
5. If the subject line doesn't need changes, return it unchanged
6. Be natural and professional in your edits{signature_rule}"""

        user_prompt = f"""Please make a small edit to this email based on my instruction.

MY EDIT INSTRUCTION:
{edit_prompt}
{context_section}
CURRENT EMAIL:
Subject: {original_subject}

{original_body}

---

Make the minimal necessary changes to address my instruction. Add no more than ~30 words.

Return a JSON object with:
{{
    "modified_subject": "the subject (unchanged unless the instruction requires it)",
    "modified_body": "the modified email body with your edit incorporated naturally",
    "changes_summary": "brief description of what was changed (max 15 words)"
}}

Return ONLY the JSON object."""

        logger.info(f"AI editing email | Prompt: {edit_prompt[:100]}...")

        model = get_active_model()
        async with httpx.AsyncClient(timeout=45.0) as client:
            payload = {
                "model": model,
                "max_tokens": 2048,
                "system": [
                    {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}
                ],
                "temperature": 0.5,
                "messages": [
                    {"role": "user", "content": user_prompt}
                ]
            }
            async with traced_call(
                "anthropic.sonnet.edit_email",
                request={"system": system_prompt, "user": user_prompt, "model": model, "max_tokens": 2048},
                metadata={"model": model, "task": "Edit Email Content"},
            ) as t:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    },
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()
                if t:
                    t["response"] = _anthropic_response_summary(result)
            _accumulate_tokens(result)

            ai_response = result["content"][0]["text"].strip()

            # Clean up response
            cleaned_response = ai_response
            if cleaned_response.startswith("```json"):
                cleaned_response = cleaned_response.replace("```json", "").replace("```", "").strip()
            elif cleaned_response.startswith("```"):
                cleaned_response = cleaned_response.replace("```", "").strip()

            try:
                edit_data = json.loads(cleaned_response)
            except json.JSONDecodeError as e:
                logger.error(f"JSON parsing failed: {e}. Response: {cleaned_response[:500]}")
                # Try to extract fields using regex as fallback
                subject_match = re.search(r'"modified_subject"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', cleaned_response)
                body_match = re.search(r'"modified_body"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', cleaned_response, re.DOTALL)
                summary_match = re.search(r'"changes_summary"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', cleaned_response)

                edit_data = {
                    "modified_subject": subject_match.group(1) if subject_match else original_subject,
                    "modified_body": body_match.group(1).replace('\\n', '\n') if body_match else original_body,
                    "changes_summary": summary_match.group(1) if summary_match else "Edit applied"
                }

            # Ensure the body has proper newlines (unescape if needed)
            if "modified_body" in edit_data:
                edit_data["modified_body"] = edit_data["modified_body"].replace('\\n', '\n')

            logger.info(f"AI edit complete | Summary: {edit_data.get('changes_summary', 'No summary')}")

            return {
                "modified_subject": edit_data.get("modified_subject", original_subject),
                "modified_body": edit_data.get("modified_body", original_body),
                "changes_summary": edit_data.get("changes_summary", "Edit applied")
            }

    except Exception as e:
        raise handle_anthropic_error(e, "email content editing")