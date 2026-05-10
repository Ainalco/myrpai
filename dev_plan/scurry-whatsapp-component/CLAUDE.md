# WhatsApp Component â Scurry.ai Add-On

## â ï¸ MUST USE CLAUDE CODE FOR THIS PROJECT

This project is designed for development with **Claude Code** (Anthropic's CLI coding agent). Do NOT attempt to build this manually or with a different AI tool. Claude Code has the context, codebase access, and agentic capabilities required. Install: https://docs.anthropic.com/en/docs/claude-code

---

## What This Is

A messaging component for Scurry.ai that sends AI-generated WhatsApp follow-up sequences via the WhatsApp Business Cloud API. It reuses the **exact same architecture** as the existing email component â same AI prompt system, same queue/approval flow, same send timing logic (immediate/fixed delay/AI decides), same AI filter, same timeline check. The ONLY difference is the delivery channel: WhatsApp Cloud API instead of SMTP.

**Think of it as:** the email component, but `send_via_smtp()` becomes `send_via_whatsapp()` and the AI prompt adjusts for WhatsApp's conversational tone + formatting.

---

## Architecture â How It Fits

```
Existing Scurry Pipeline:
  Input (Fireflies) â Text Generation â [Email 1] â [Email 2] â [Email 3]

With WhatsApp Component:
  Input (Fireflies) â Text Generation â [WhatsApp 1] â [WhatsApp 2] â [WhatsApp 3]
  OR mixed: â [Email 1] â [WhatsApp 2] â [Email 3]
```

The WhatsApp component is a **new component type** in the ComponentExecutor dispatcher. Same workflow pipeline, same input_data, same queue/approval system.

---

## What Already Exists (DO NOT REBUILD)

These systems are already built and working. **Plug into them:**

1. **ComponentExecutor dispatcher** (`backend/executions.py`) â Add `elif component_type == "whatsapp": execute_whatsapp()`
2. **COMPONENT_TYPES registry** (`backend/components.py`) â Register WhatsApp with config_schema
3. **AI prompt system** â Claude API call with variable substitution
4. **Queue/approval flow** â Pending â Approved â Sent
5. **Send timing** â Immediate / Fixed Delay / AI Decides (reuse exact same logic)
6. **AI Filter** â Pre-send validation (reuse as-is)
7. **Timeline Check** â Opus reads contact history (reuse as-is)
8. **Acorn cost tracking** â Same deduction pattern
9. **Variable substitution engine** â Same `{{variable}}` resolution

---

## What You ARE Building

### 1. WhatsApp Service (`backend/whatsapp_service.py`)

Core service class. Follow the exact pattern of `research_service.py`:

```python
class WhatsAppService:
    def __init__(self, db: Session, user: models.User):
        self.db = db
        self.user = user

    async def execute_whatsapp_async(
        self,
        config: dict,
        input_data: dict,
        workflow_id: int = None,
        execution_id: int = None,
        component_id: int = None,
    ) -> dict:
        """
        1. Resolve recipient phone number from input_data
        2. Generate WhatsApp message via Claude API (SAME prompt system as email)
           - Inject WhatsApp-specific system instruction (see below)
        3. Run AI filter if enabled (SAME as email)
        4. Run timeline check if enabled (SAME as email)
        5. Create queue entry in message_queue table
        6. Return for approval
        """
```

**WhatsApp-specific prompt injection** (prepend to user's ai_prompt):

````
CHANNEL: WhatsApp
CONSTRAINTS:
- Maximum 4096 characters (WhatsApp limit), but aim for 200-500 chars.
- WhatsApp is CONVERSATIONAL. Write like a text message, not an email.
- No subject line. Open with the person's name or a direct hook.
- WhatsApp formatting supported: *bold*, _italic_, ~strikethrough~, ```monospace```
- Use line breaks for readability. Short paragraphs.
- Can include links (full URLs, WhatsApp auto-previews them).
- No formal sign-offs ("Best regards", "Sincerely"). Just sign with first name or nothing.
- Emoji use is acceptable and encouraged where natural.
- Tone: friendly, direct, casual professional.
````

### 2. WhatsApp Delivery Adapter (`backend/whatsapp_delivery.py`)

Wrapper around WhatsApp Business Cloud API (Meta Graph API):

```python
import httpx

class WhatsAppAdapter:
    BASE_URL = "https://graph.facebook.com/v21.0"

    def __init__(self, phone_number_id: str, access_token: str):
        self.phone_number_id = phone_number_id
        self.access_token = access_token

    async def send_message(self, to: str, body: str) -> dict:
        """
        Send text message via WhatsApp Cloud API.
        POST /{phone_number_id}/messages
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/{self.phone_number_id}/messages",
                headers={"Authorization": f"Bearer {self.access_token}"},
                json={
                    "messaging_product": "whatsapp",
                    "to": to,
                    "type": "text",
                    "text": {"body": body}
                }
            )
            data = response.json()
            return {
                "message_id": data["messages"][0]["id"],
                "status": "sent",
            }

    async def send_template_message(self, to: str, template_name: str, params: list) -> dict:
        """
        Send template message (for initiating conversations outside 24h window).
        Templates must be pre-approved in Meta Business Manager.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/{self.phone_number_id}/messages",
                headers={"Authorization": f"Bearer {self.access_token}"},
                json={
                    "messaging_product": "whatsapp",
                    "to": to,
                    "type": "template",
                    "template": {
                        "name": template_name,
                        "language": {"code": "en"},
                        "components": [{
                            "type": "body",
                            "parameters": [{"type": "text", "text": p} for p in params]
                        }]
                    }
                }
            )
            return response.json()
```

### 3. API Routes (`backend/whatsapp.py`)

FastAPI router:

- `POST /whatsapp/send` â Execute WhatsApp component (called by workflow engine)
- `GET /whatsapp/queue` â List queued WhatsApp messages
- `POST /whatsapp/queue/{id}/approve` â Approve and schedule
- `POST /whatsapp/queue/{id}/edit` â Manual edit
- `POST /whatsapp/queue/{id}/skip` â Skip
- `DELETE /whatsapp/queue/{id}` â Delete
- `POST /whatsapp/queue/{id}/ai-edit` â Quick AI edit
- `POST /whatsapp/webhook` â Incoming webhook from Meta (delivery receipts + incoming messages)
- `GET /whatsapp/webhook` â Webhook verification endpoint (Meta requires GET for setup)
- `GET /whatsapp/templates` â List approved message templates from Meta

### 4. Database Model (`backend/models_patch_whatsapp.py`)

**Use the existing `email_queue` table.** Add `channel = 'whatsapp'` to distinguish from email/SMS. The table will be renamed later â for now the `channel` field makes it obvious in the queue UI.

```sql
-- If SMS component hasn't already added these:
ALTER TABLE email_queue ADD COLUMN IF NOT EXISTS channel VARCHAR(20) DEFAULT 'email';
ALTER TABLE email_queue ADD COLUMN IF NOT EXISTS recipient_phone VARCHAR(20);
ALTER TABLE email_queue ADD COLUMN IF NOT EXISTS delivery_status VARCHAR(20);

-- WhatsApp-specific fields
ALTER TABLE email_queue ADD COLUMN whatsapp_message_id VARCHAR(100);
ALTER TABLE email_queue ADD COLUMN whatsapp_template_name VARCHAR(100);
ALTER TABLE email_queue ADD COLUMN is_template_message BOOLEAN DEFAULT FALSE;
ALTER TABLE email_queue ADD COLUMN conversation_window_expires_at TIMESTAMP WITH TIME ZONE;
```

**IMPORTANT:** Same email_queue table, `channel = 'whatsapp'`. All existing email queries still work. Queue UI shows channel type per item.

### 5. Integration Patches (`backend/INTEGRATION_PATCHES.py`)

1. `components.py` â Add `"whatsapp"` to COMPONENT_TYPES
2. `executions.py` â Add `execute_whatsapp()` static method + dispatcher entry
3. `main.py` â Register whatsapp router
4. `requirements.txt` â Add `httpx>=0.27.0` (if not already present)
5. `migrations/` â Alembic migration for WhatsApp-specific fields

### 6. Settings Integration

User configures WhatsApp Business in Settings â Integrations:

- WhatsApp Business Phone Number ID
- Permanent Access Token (from Meta Business Manager)
- Webhook Verify Token (for Meta webhook setup)
- Business Account ID (for template management)

Store encrypted in user's integration_settings JSON.

### 7. Tests (`tests/`)

- Unit tests: WhatsApp message generation, formatting, char limits
- Integration tests: Queue CRUD, approval flow, template vs freeform routing
- Mock WhatsApp API: Never hit real Meta API in tests
- Edge cases: 24h window expiry, template fallback, invalid phone formats

---

## WhatsApp-Specific Complexity: The 24-Hour Window

**This is the ONE thing that makes WhatsApp different from SMS/email:**

WhatsApp Business API has a **24-hour conversation window**:

- If the contact has messaged your WhatsApp Business number in the last 24 hours â you can send freeform messages (any content).
- If the 24-hour window has expired â you MUST use a pre-approved **template message** to re-initiate.

**How to handle this:**

```python
async def determine_message_type(self, contact_phone: str) -> str:
    """
    Check if we're within the 24h conversation window.
    If yes â send freeform text message
    If no â send template message (must be pre-approved in Meta)
    """
    # Check last inbound message timestamp from this contact
    last_inbound = await self.get_last_inbound_message(contact_phone)

    if last_inbound and (datetime.now() - last_inbound.received_at).hours < 24:
        return "freeform"
    else:
        return "template"
```

**For MVP:** Default to template messages for ALL first-touch messages. Freeform only when we have confirmed conversation window. This is the safe approach.

**Template strategy:** Create 3 generic templates in Meta Business Manager:

1. `meeting_followup_1` â "Hi {{1}}, great speaking with you about {{2}}. {{3}}"
2. `meeting_followup_2` â "Hi {{1}}, following up on our conversation about {{2}}. {{3}}"
3. `meeting_followup_3` â "Hi {{1}}, wanted to share something relevant to {{2}}. {{3}}"

The AI generates the parameter values that slot into the template.

---

## Config Schema

```python
"whatsapp": {
    "name": "WhatsApp Message",
    "description": "Send AI-generated WhatsApp follow-ups",
    "icon": "message-circle",
    "color": "#25D366",
    "category": "outbound",
    "inputs": ["trigger_data", "extracted_information", "research_brief"],
    "outputs": ["message_body", "message_type", "approval_status", "sent_at"],
    "config_schema": {
        "ai_prompt": {
            "type": "textarea",
            "label": "AI Instructions",
            "placeholder": "Tell the AI what kind of WhatsApp message to write...",
            "required": True
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
            "default": True
        },
        "timeline_check": {
            "type": "toggle",
            "label": "Timeline Check",
            "default": True
        },
        "message_style": {
            "type": "select",
            "label": "Message Style",
            "options": ["conversational", "professional", "brief"],
            "default": "conversational"
        },
        "fallback_template": {
            "type": "select",
            "label": "Template (outside 24h window)",
            "options": ["meeting_followup_1", "meeting_followup_2", "meeting_followup_3"],
            "default": "meeting_followup_1",
            "help": "Used when contact hasn't messaged in 24h"
        }
    }
}
```

---

## Key Constraints

- **24-hour window is the #1 complexity.** Handle template vs freeform routing correctly. Default to templates when in doubt.
- **Phone number required with country code.** WhatsApp requires international format (e.g., +1234567890). Validate and normalize.
- **User sets up their own WhatsApp Business account.** Scurry does NOT provide WhatsApp numbers. User connects their existing Business account.
- **Template messages must be pre-approved by Meta.** This takes 24-48 hours. Document the template setup process clearly.
- **Delivery receipts come via webhook.** Meta sends status updates (sent, delivered, read) to our webhook endpoint.
- **No rich media in MVP.** Text messages only. Images/documents/buttons are Phase 2.

---

## Build Order

1. Database migration (message_queue WhatsApp fields)
2. WhatsAppService class with mock API (AI generation + queue creation)
3. WhatsAppAdapter with real Cloud API calls
4. 24-hour window detection + template routing logic
5. FastAPI routes (queue CRUD + approval + webhook)
6. Integration patches (ComponentExecutor, COMPONENT_TYPES, router registration)
7. Settings integration (WhatsApp credentials storage)
8. Meta webhook setup (verification + status callbacks)
9. Tests (unit + integration)

---

## Files to Create

```
whatsapp-component/
âââ CLAUDE.md                  â This file
âââ README.md                  â Quick overview for GitHub
âââ backend/
â   âââ whatsapp_service.py    â Core service (generation + queue + AI features)
â   âââ whatsapp_delivery.py   â WhatsApp Cloud API adapter
â   âââ whatsapp.py            â FastAPI routes
â   âââ models_patch_whatsapp.py â Database model/migration
â   âââ INTEGRATION_PATCHES.py â Exact changes to existing files
âââ tests/
    âââ test_whatsapp_service.py
    âââ test_whatsapp_delivery.py
    âââ test_whatsapp_routes.py
```

---

## Reference Files (Read These First)

1. `research-component/backend/research_service.py` â Service class pattern
2. `research-component/backend/INTEGRATION_PATCHES.py` â Integration pattern
3. `research-component/backend/research.py` â FastAPI route pattern
4. `cold-email-engine/ai_engine.py` â Claude API call pattern
5. `sms-component/CLAUDE.md` â SMS component spec (build SMS first, WhatsApp second â shared patterns)
6. `Scurry-Platform-Context-Doc.md` â Full platform architecture
7. `CLAUDE.md` (root) â Project rules

---

## Hard Rules

- **Never break the existing email flow.** WhatsApp is additive.
- **Never store Meta tokens in plaintext.** Encrypt at rest.
- **Never send WhatsApp messages without user approval.** Queue first, always.
- **Never send freeform messages outside 24h window.** Default to template.
- **Feature branch only.** Branch: `feature/whatsapp-component`. Never commit to main.
- **Present tense commits.** Match project convention.
- **Match existing code style exactly.**
