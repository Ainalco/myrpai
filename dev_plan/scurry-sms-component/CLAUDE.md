# SMS Component â Scurry.ai Add-On

## â ï¸ MUST USE CLAUDE CODE FOR THIS PROJECT

This project is designed for development with **Claude Code** (Anthropic's CLI coding agent). Do NOT attempt to build this manually or with a different AI tool. Claude Code has the context, codebase access, and agentic capabilities required. Install: https://docs.anthropic.com/en/docs/claude-code

---

## What This Is

A messaging component for Scurry.ai that sends AI-generated SMS follow-up sequences via Twilio. It reuses the **exact same architecture** as the existing email component â same AI prompt system, same queue/approval flow, same send timing logic (immediate/fixed delay/AI decides), same AI filter, same timeline check. The ONLY difference is the delivery channel: Twilio SMS instead of SMTP email.

**Think of it as:** the email component, but `send_via_smtp()` becomes `send_via_twilio()` and the AI prompt enforces SMS character limits.

---

## Architecture â How It Fits

```
Existing Scurry Pipeline:
  Input (Fireflies) â Text Generation â [Email 1] â [Email 2] â [Email 3]

With SMS Component:
  Input (Fireflies) â Text Generation â [SMS 1] â [SMS 2] â [SMS 3]
  OR mixed: â [Email 1] â [SMS 2] â [Email 3]
```

The SMS component is a **new component type** in the ComponentExecutor dispatcher. It plugs into the same workflow pipeline, receives the same input_data (contact info, research, extracted fields), and outputs to the same queue/approval system.

---

## What Already Exists (DO NOT REBUILD)

These systems are already built and working. Your job is to **plug into them**, not recreate them:

1. **ComponentExecutor dispatcher** (`backend/executions.py`) â Routes component_type â execute method. You add `elif component_type == "sms": execute_sms()`
2. **COMPONENT_TYPES registry** (`backend/components.py`) â Register SMS with config_schema, inputs, outputs
3. **AI prompt system** â Claude API call with variable substitution (`{{contact.name}}`, `{{research.pain_points}}`, etc.)
4. **Queue/approval flow** â Pending â Approved â Sent status transitions. Same UI pattern.
5. **Send timing** â Immediate / Fixed Delay / AI Decides. Reuse the exact same logic.
6. **AI Filter** â Pre-send validation (check placeholders, personalization, tone). Reuse as-is.
7. **Timeline Check** â Opus reads contact history before send. Reuse as-is.
8. **Acorn cost tracking** â Deduct from user balance for AI generation. Same pattern.
9. **Variable substitution engine** â Resolves `{{variable}}` in prompts from upstream component outputs.

---

## What You ARE Building

### 1. SMS Service (`backend/sms_service.py`)

Core service class. Follow the exact pattern of `research_service.py`:

```python
class SMSService:
    def __init__(self, db: Session, user: models.User):
        self.db = db
        self.user = user

    async def execute_sms_async(
        self,
        config: dict,
        input_data: dict,
        workflow_id: int = None,
        execution_id: int = None,
        component_id: int = None,
    ) -> dict:
        """
        1. Resolve recipient phone number from input_data
        2. Generate SMS content via Claude API (SAME prompt system as email)
           - Inject SMS-specific system instruction: "Max 160 chars, no formatting, plain text only"
           - Still uses config["ai_prompt"] with variable substitution
        3. Run AI filter if enabled (SAME as email)
        4. Run timeline check if enabled (SAME as email)
        5. Create queue entry in message_queue table
        6. Return for approval
        """
```

**SMS-specific prompt injection** (prepend to user's ai_prompt):

```
CHANNEL: SMS
HARD CONSTRAINTS:
- Maximum 160 characters (1 SMS segment). Absolute max 320 chars (2 segments).
- Plain text only. No formatting, no markdown, no HTML.
- No subject line.
- Include opt-out: "Reply STOP to unsubscribe" (counts toward char limit).
- Be conversational and direct. SMS is informal.
- If including a link, use a short URL.
```

### 2. Twilio Delivery Adapter (`backend/sms_delivery.py`)

Thin wrapper around Twilio's Python SDK. This is the ONLY truly new code:

```python
from twilio.rest import Client

class TwilioAdapter:
    def __init__(self, account_sid: str, auth_token: str, from_number: str):
        self.client = Client(account_sid, auth_token)
        self.from_number = from_number

    async def send_sms(self, to: str, body: str) -> dict:
        """
        Send SMS via Twilio. Returns message SID + status.
        Handle errors: invalid number, insufficient funds, rate limits.
        """
        message = self.client.messages.create(
            body=body,
            from_=self.from_number,
            to=to,
            status_callback=WEBHOOK_URL  # For delivery receipts
        )
        return {
            "sid": message.sid,
            "status": message.status,
            "segments": message.num_segments,
            "price": message.price,
        }
```

### 3. API Routes (`backend/sms.py`)

FastAPI router. Follow `research.py` pattern:

- `POST /sms/send` â Execute SMS component (called by workflow engine)
- `GET /sms/queue` â List queued SMS messages (with status filter)
- `POST /sms/queue/{id}/approve` â Approve and schedule SMS
- `POST /sms/queue/{id}/edit` â Manual edit of SMS content
- `POST /sms/queue/{id}/skip` â Skip this SMS
- `DELETE /sms/queue/{id}` â Delete from queue
- `POST /sms/queue/{id}/ai-edit` â Quick AI edit (same as email)
- `GET /sms/status/{sid}` â Check Twilio delivery status
- `POST /sms/webhook/status` â Twilio status callback endpoint

### 4. Database Model (`backend/models_patch_sms.py`)

**Use the existing `email_queue` table.** Add a `channel` field to distinguish SMS from email. The table will be renamed from `email_queue` to something more generic later â for now, just add the channel indicator so it's obvious in the queue UI which items are SMS vs email.

```sql
-- Add to existing email_queue table
ALTER TABLE email_queue ADD COLUMN channel VARCHAR(20) DEFAULT 'email';
-- Values: 'email', 'sms' (more channels added by other components later)

-- SMS-specific fields
ALTER TABLE email_queue ADD COLUMN recipient_phone VARCHAR(20);
ALTER TABLE email_queue ADD COLUMN character_count INTEGER;
ALTER TABLE email_queue ADD COLUMN sms_segments INTEGER;
ALTER TABLE email_queue ADD COLUMN twilio_message_sid VARCHAR(100);
ALTER TABLE email_queue ADD COLUMN delivery_status VARCHAR(20);  -- queued, sent, delivered, failed, undelivered

CREATE INDEX idx_email_queue_channel ON email_queue(channel);
```

**IMPORTANT:** All existing email queries continue to work â they just need a `WHERE channel = 'email'` filter added (or they return everything, which is fine for the unified queue view). New SMS items go in with `channel = 'sms'`.

**The queue will be renamed later.** For now, email_queue holds all channel types. The `channel` field makes it obvious in the UI which type each item is.

### 5. Integration Patches (`backend/INTEGRATION_PATCHES.py`)

Exact code changes needed in existing files (same pattern as research component):

1. `components.py` â Add `"sms"` to COMPONENT_TYPES
2. `executions.py` â Add `execute_sms()` static method + dispatcher entry
3. `main.py` â Register sms router
4. `requirements.txt` â Add `twilio>=9.0.0`
5. `migrations/` â Alembic migration for sms_queue table

### 6. Settings Integration

User configures Twilio credentials in Settings â Integrations:

- Twilio Account SID
- Twilio Auth Token
- From Phone Number (Twilio number)

Store encrypted in user's integration_settings JSON field (same pattern as Pipedrive/Fireflies credentials).

### 7. Tests (`tests/`)

Follow `test_research.py` pattern:

- Unit tests: SMS generation with char limits, prompt injection, variable substitution
- Integration tests: Queue CRUD, approval flow, status transitions
- Mock Twilio: Never hit real Twilio API in tests
- Edge cases: Over char limit handling, invalid phone numbers, opt-out detection

---

## Config Schema (What the UI Renders)

```python
"sms": {
    "name": "SMS Message",
    "description": "Send AI-generated SMS follow-ups via Twilio",
    "icon": "smartphone",
    "color": "#4CAF50",
    "category": "outbound",
    "inputs": ["trigger_data", "extracted_information", "research_brief"],
    "outputs": ["message_body", "character_count", "segments", "approval_status", "sent_at"],
    "config_schema": {
        "ai_prompt": {
            "type": "textarea",
            "label": "AI Instructions",
            "placeholder": "Tell the AI what kind of SMS to write...",
            "required": True,
            "help": "The AI will automatically enforce SMS character limits."
        },
        "send_timing": {
            "type": "select",
            "options": ["immediate", "fixed_delay", "ai_decides"],
            "default": "immediate"
        },
        "delay_config": {
            "type": "object",
            "fields": {
                "delay_hours": {"type": "number", "default": 0},
                "delay_days": {"type": "number", "default": 0},
                "business_hours_only": {"type": "toggle", "default": True}
            },
            "visible_when": {"send_timing": "fixed_delay"}
        },
        "ai_filter": {
            "type": "toggle",
            "label": "AI Quality Filter",
            "default": True,
            "help": "AI reviews message before queuing"
        },
        "timeline_check": {
            "type": "toggle",
            "label": "Timeline Check",
            "default": True,
            "help": "Check contact history before sending"
        },
        "max_segments": {
            "type": "select",
            "label": "Max SMS Segments",
            "options": [1, 2, 3],
            "default": 1,
            "help": "1 segment = 160 chars, 2 = 320, 3 = 480"
        },
        "include_opt_out": {
            "type": "toggle",
            "label": "Include opt-out text",
            "default": True,
            "help": "Appends 'Reply STOP to unsubscribe' (required for compliance)"
        }
    }
}
```

---

## Key Constraints

- **Character limits are THE constraint.** The AI prompt MUST enforce 160/320/480 char limits. Test this heavily.
- **Phone number required.** Must come from Text Generation extraction (`phone` field) or contact record. If missing â queue entry with status "missing_phone" â user prompted to add.
- **User pays Twilio directly.** Scurry does NOT mark up SMS delivery cost. User has their own Twilio account. Scurry only charges acorns for AI generation.
- **Compliance:** STOP/opt-out handling is mandatory. Twilio handles this at their level, but we must include opt-out text in messages.
- **No attachments.** SMS is text-only. If the workflow has resources configured, ignore them for SMS (or convert PDF link to short URL).

---

## Build Order

1. Database migration (message_queue changes OR sms_queue table)
2. SMSService class with mock Twilio (AI generation + queue creation)
3. TwilioAdapter with real API calls
4. FastAPI routes (queue CRUD + approval + webhook)
5. Integration patches (ComponentExecutor, COMPONENT_TYPES, router registration)
6. Settings integration (Twilio credentials storage)
7. Tests (unit + integration)
8. Status callback webhook (delivery receipts from Twilio)

---

## Files to Create

```
sms-component/
âââ CLAUDE.md              â This file
âââ README.md              â Quick overview for GitHub
âââ backend/
â   âââ sms_service.py     â Core service (generation + queue + AI features)
â   âââ sms_delivery.py    â Twilio adapter (thin wrapper)
â   âââ sms.py             â FastAPI routes
â   âââ models_patch_sms.py â Database model/migration
â   âââ INTEGRATION_PATCHES.py â Exact changes to existing files
âââ tests/
    âââ test_sms_service.py
    âââ test_sms_delivery.py
    âââ test_sms_routes.py
```

---

## Reference Files (Read These First)

Before writing any code, read these files in the main repo to understand the patterns:

1. `research-component/backend/research_service.py` â Service class pattern (your primary template)
2. `research-component/backend/INTEGRATION_PATCHES.py` â How to integrate into ComponentExecutor
3. `research-component/backend/research.py` â FastAPI route pattern
4. `research-component/backend/models_patch.py` â Database model pattern
5. `cold-email-engine/ai_engine.py` â Claude API call pattern + JSON parsing
6. `Scurry-Platform-Context-Doc.md` â Full platform architecture
7. `CLAUDE.md` (root) â Project rules, autonomy tiers, hard boundaries

---

## Hard Rules

- **Never break the existing email flow.** SMS is additive. If you're modifying email_queue â message_queue, ensure ALL existing email queries still work.
- **Never store Twilio credentials in plaintext.** Encrypt at rest, same pattern as other integration credentials.
- **Never send SMS without user approval.** Everything goes through the queue first.
- **Never exceed character limits silently.** If AI generates over-limit text, truncate + warn in queue, don't send truncated.
- **Feature branch only.** Branch: `feature/sms-component`. Never commit to main.
- **Present tense commits.** "Add SMS service class" not "Added SMS service class."
- **PSR-12 equivalent for Python.** Match existing project code style exactly.
