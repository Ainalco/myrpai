# Telegram Component â Scurry.ai Add-On

## â ï¸ MUST USE CLAUDE CODE FOR THIS PROJECT

This project is designed for development with **Claude Code** (Anthropic's CLI coding agent). Do NOT attempt to build this manually or with a different AI tool. Claude Code has the context, codebase access, and agentic capabilities required. Install: https://docs.anthropic.com/en/docs/claude-code

---

## What This Is

A messaging component for Scurry.ai that sends AI-generated follow-up sequences via Telegram Bot API. It reuses the **exact same architecture** as the existing email component â same AI prompt system, same queue/approval flow, same send timing logic, same AI filter, same timeline check. The ONLY difference is the delivery channel: Telegram Bot API instead of SMTP.

**Think of it as:** the email component, but `send_via_smtp()` becomes `send_via_telegram_bot()`.

**Priority: LOW.** Build SMS and WhatsApp components first. Telegram is third in line.

---

## Architecture â How It Fits

Same component-based pipeline as email, SMS, and WhatsApp:

```
Input (Fireflies) â Text Generation â [Telegram 1] â [Telegram 2] â [Telegram 3]
```

New component type `telegram_message` in the ComponentExecutor dispatcher.

---

## What Already Exists (DO NOT REBUILD)

Same as SMS/WhatsApp â plug into existing systems:

1. **ComponentExecutor dispatcher** â Add `elif component_type == "telegram": execute_telegram()`
2. **COMPONENT_TYPES registry** â Register Telegram
3. **AI prompt system** â Same Claude API + variable substitution
4. **Queue/approval flow** â Same pending â approved â sent
5. **Send timing** â Same immediate / fixed delay / AI decides
6. **AI Filter** â Same pre-send validation
7. **Timeline Check** â Same contact history review
8. **Acorn cost tracking** â Same deduction
9. **Variable substitution** â Same `{{variable}}` resolution

**If SMS/WhatsApp components are already built:** Reuse the message_queue table with `channel = 'telegram'`. Reuse any shared message service base class they created.

---

## What You ARE Building

### 1. Telegram Service (`backend/telegram_service.py`)

```python
class TelegramService:
    def __init__(self, db: Session, user: models.User):
        self.db = db
        self.user = user

    async def execute_telegram_async(
        self,
        config: dict,
        input_data: dict,
        workflow_id: int = None,
        execution_id: int = None,
        component_id: int = None,
    ) -> dict:
        """
        1. Resolve recipient Telegram chat_id from input_data or contact record
        2. Generate message via Claude API (same prompt system)
        3. Run AI filter if enabled (same as email)
        4. Run timeline check if enabled (same as email)
        5. Create queue entry in message_queue table
        6. Return for approval
        """
```

**Telegram-specific prompt injection:**

````
CHANNEL: Telegram
CONSTRAINTS:
- Maximum 4096 characters, but aim for 200-600 chars.
- Telegram markdown supported: **bold**, __italic__, `code`, ```code block```, [links](url), ~~strikethrough~~
- Conversational tone, like a professional chat message.
- No subject line. Open directly with the person's name or context.
- Can use line breaks freely for readability.
- Emoji use is natural on Telegram.
- No formal sign-offs.
````

### 2. Telegram Delivery Adapter (`backend/telegram_delivery.py`)

Wrapper around Telegram Bot API:

```python
import httpx

class TelegramAdapter:
    BASE_URL = "https://api.telegram.org/bot{token}"

    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.base_url = self.BASE_URL.format(token=bot_token)

    async def send_message(self, chat_id: str, text: str, parse_mode: str = "MarkdownV2") -> dict:
        """Send text message via Telegram Bot API."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                    "disable_web_page_preview": False,
                }
            )
            data = response.json()
            if not data["ok"]:
                raise Exception(f"Telegram API error: {data['description']}")
            return {
                "message_id": data["result"]["message_id"],
                "status": "sent",
            }

    async def get_updates(self, offset: int = None) -> list:
        """Poll for incoming messages (to get chat_ids from new contacts)."""
        async with httpx.AsyncClient() as client:
            params = {}
            if offset:
                params["offset"] = offset
            response = await client.get(
                f"{self.base_url}/getUpdates",
                params=params
            )
            return response.json().get("result", [])
```

### 3. API Routes (`backend/telegram.py`)

- `POST /telegram/send` â Execute Telegram component
- `GET /telegram/queue` â List queued Telegram messages
- `POST /telegram/queue/{id}/approve` â Approve and schedule
- `POST /telegram/queue/{id}/edit` â Manual edit
- `POST /telegram/queue/{id}/skip` â Skip
- `DELETE /telegram/queue/{id}` â Delete
- `POST /telegram/queue/{id}/ai-edit` â Quick AI edit
- `POST /telegram/webhook` â Incoming updates from Telegram (delivery + new contacts)
- `GET /telegram/bot-info` â Get bot details (name, username, link)
- `GET /telegram/contacts` â List contacts who have messaged the bot

### 4. Database Model (`backend/models_patch_telegram.py`)

**Use the existing `email_queue` table.** Add `channel = 'telegram'`. Same pattern as SMS/WhatsApp â table gets renamed later.

```sql
-- If previous components haven't already added these:
ALTER TABLE email_queue ADD COLUMN IF NOT EXISTS channel VARCHAR(20) DEFAULT 'email';
ALTER TABLE email_queue ADD COLUMN IF NOT EXISTS delivery_status VARCHAR(20);

-- Telegram-specific fields
ALTER TABLE email_queue ADD COLUMN telegram_chat_id VARCHAR(50);
ALTER TABLE email_queue ADD COLUMN telegram_message_id INTEGER;
```

**IMPORTANT:** Same email_queue table, `channel = 'telegram'`. All existing queries still work.

Also need a **telegram_contacts** table to track who has messaged the bot:

```sql
CREATE TABLE telegram_contacts (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL FK,          -- Scurry user who owns the bot
    telegram_chat_id VARCHAR(50),     -- Telegram user's chat ID
    telegram_username VARCHAR(100),   -- @username
    telegram_first_name VARCHAR(100),
    telegram_last_name VARCHAR(100),
    contact_id INT FK,                -- Link to Scurry contact (if matched)
    first_message_at TIMESTAMP,
    last_message_at TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,   -- Has the user blocked the bot?
    created_at TIMESTAMP DEFAULT now()
);
```

### 5. Integration Patches

1. `components.py` â Add `"telegram"` to COMPONENT_TYPES
2. `executions.py` â Add `execute_telegram()` + dispatcher
3. `main.py` â Register telegram router
4. `requirements.txt` â `httpx` (likely already added by WhatsApp component)
5. `migrations/` â Alembic migration

### 6. Settings Integration

User configures in Settings â Integrations:

- Telegram Bot Token (from BotFather)
- Webhook URL (auto-configured, or manual for custom domains)

### 7. Contact Matching

**The Telegram-specific challenge:** Telegram bots can only message users who have messaged them first. So we need:

1. **Bot link sharing:** Generate a link (`t.me/YourBotName?start=ref_CONTACT_ID`) that the Scurry user can share with contacts.
2. **Auto-matching:** When someone messages the bot with a `/start ref_CONTACT_ID` deep link, automatically match their Telegram chat_id to the Scurry contact.
3. **Manual matching:** In the Scurry UI, user can manually link a Telegram contact to a Scurry contact record.

```python
async def handle_start_command(self, message: dict):
    """Handle /start command with optional contact reference."""
    text = message.get("text", "")
    chat_id = message["chat"]["id"]

    # Check for deep link parameter
    if text.startswith("/start ref_"):
        contact_id = text.replace("/start ref_", "")
        # Link this Telegram user to the Scurry contact
        await self.link_telegram_to_contact(chat_id, int(contact_id))
        await self.send_message(chat_id, "Connected! You'll receive follow-up messages here.")
    else:
        await self.send_message(chat_id, "Hi! I'm a Scurry.ai bot. Your contact will be linked shortly.")
```

---

## Config Schema

```python
"telegram": {
    "name": "Telegram Message",
    "description": "Send AI-generated Telegram follow-ups via Bot API",
    "icon": "send",
    "color": "#0088cc",
    "category": "outbound",
    "inputs": ["trigger_data", "extracted_information", "research_brief"],
    "outputs": ["message_body", "approval_status", "sent_at"],
    "config_schema": {
        "ai_prompt": {
            "type": "textarea",
            "label": "AI Instructions",
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
        "parse_mode": {
            "type": "select",
            "label": "Formatting",
            "options": ["MarkdownV2", "HTML", "plain"],
            "default": "MarkdownV2"
        }
    }
}
```

---

## Key Constraints

- **Bot must be messaged first.** Users cannot cold-send Telegram messages. Contact must have initiated conversation with the bot. This is the fundamental limitation.
- **Deep link strategy is critical.** The `/start ref_CONTACT_ID` pattern is how we bridge Scurry contacts to Telegram chat_ids. Without this, no automated matching.
- **Phone number optional.** Unlike SMS/WhatsApp, Telegram uses chat_id (not phone). Contact matching happens via deep link or manual assignment.
- **MarkdownV2 escaping.** Telegram's MarkdownV2 requires escaping special characters. The AI-generated text must be escaped before sending, OR use HTML parse mode to avoid escaping issues.
- **Bot rate limits.** Telegram limits: 30 messages/second to different chats, 20 messages/minute to same chat. Implement rate limiting in the send worker.
- **No cost to user for delivery.** Telegram Bot API is free. User only pays acorns for AI generation.

---

## Build Order

1. Database migration (telegram_contacts table + message_queue telegram fields)
2. TelegramAdapter (bot API wrapper â send + receive + webhook)
3. Contact matching system (deep links + auto-link + manual link)
4. TelegramService class (AI generation + queue creation)
5. FastAPI routes (queue CRUD + approval + webhook + bot info)
6. Integration patches
7. Settings integration (bot token storage)
8. Tests

---

## Files to Create

```
telegram-component/
âââ CLAUDE.md                    â This file
âââ README.md                    â Quick overview
âââ backend/
â   âââ telegram_service.py      â Core service
â   âââ telegram_delivery.py     â Bot API adapter
â   âââ telegram.py              â FastAPI routes
â   âââ models_patch_telegram.py â Database model/migration
â   âââ INTEGRATION_PATCHES.py   â Exact changes to existing files
âââ tests/
    âââ test_telegram_service.py
    âââ test_telegram_delivery.py
    âââ test_telegram_routes.py
```

---

## Reference Files (Read These First)

1. `research-component/backend/research_service.py` â Service class pattern
2. `sms-component/CLAUDE.md` â SMS spec (build first, shared patterns)
3. `whatsapp-component/CLAUDE.md` â WhatsApp spec (build second)
4. `research-component/backend/INTEGRATION_PATCHES.py` â Integration pattern
5. `Scurry-Platform-Context-Doc.md` â Full platform architecture
6. `CLAUDE.md` (root) â Project rules

---

## Hard Rules

- **Never break existing flows.** Telegram is additive.
- **Never store bot tokens in plaintext.** Encrypt at rest.
- **Never send messages without user approval.** Queue first.
- **Never send to contacts who haven't messaged the bot.** Check telegram_contacts table.
- **Feature branch only.** Branch: `feature/telegram-component`. Never commit to main.
- **Present tense commits.** Match project convention.
