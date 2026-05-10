# Slack DM Component â Scurry.ai Add-On

## â ï¸ MUST USE CLAUDE CODE FOR THIS PROJECT

This project is designed for development with **Claude Code** (Anthropic's CLI coding agent). Do NOT attempt to build this manually or with a different AI tool. Claude Code has the context, codebase access, and agentic capabilities required. Install: https://docs.anthropic.com/en/docs/claude-code

---

## What This Is

A messaging component for Scurry.ai that sends AI-generated follow-up sequences as Slack Direct Messages via the Slack Web API. It reuses the **exact same architecture** as the existing email component â same AI prompt system, same queue/approval flow, same send timing logic (immediate/fixed delay/AI decides), same AI filter, same timeline check. The ONLY difference is the delivery channel: Slack DM instead of SMTP.

**Think of it as:** the email component, but `send_via_smtp()` becomes `send_via_slack_dm()`.

---

## Why Slack Matters for Scurry

**Use cases that email/SMS/WhatsApp don't cover:**

1. **Internal deal handoffs** â Sales rep has a meeting â Scurry generates a follow-up sequence â sends it as Slack DMs to the account manager or CS team member who needs to act.
2. **Team selling** â Multiple people on the same deal. After a meeting, Scurry DMs each person their specific follow-up action.
3. **Partner/vendor follow-ups** â Many B2B relationships live in shared Slack channels or DMs, not email.
4. **Slack Connect** â External contacts on shared channels. DM follow-ups feel native, not salesy.
5. **Internal notifications** â "Hey, the meeting with Acme went well. Here's the summary and next steps" as a DM to the team lead.

**Key insight:** Not every follow-up after a meeting is an external sales email. Many are internal actions. Slack is where those live.

---

## Architecture â How It Fits

```
Existing Scurry Pipeline:
  Input (Fireflies) â Text Generation â [Email 1] â [Email 2] â [Email 3]

With Slack Component:
  Input (Fireflies) â Text Generation â [Slack DM 1] â [Slack DM 2] â [Slack DM 3]
  OR mixed: â [Email 1] â [Slack DM to team] â [Email 2]
```

New component type `slack_message` in the ComponentExecutor dispatcher.

---

## What Already Exists (DO NOT REBUILD)

Plug into these existing systems:

1. **ComponentExecutor dispatcher** (`backend/executions.py`) â Add `elif component_type == "slack": execute_slack()`
2. **COMPONENT_TYPES registry** (`backend/components.py`) â Register Slack
3. **AI prompt system** â Same Claude API + variable substitution
4. **Queue/approval flow** â Same pending â approved â sent
5. **Send timing** â Same immediate / fixed delay / AI decides
6. **AI Filter** â Same pre-send validation
7. **Timeline Check** â Same contact history review
8. **Acorn cost tracking** â Same deduction
9. **Variable substitution** â Same `{{variable}}` resolution

**If other messaging components (SMS/WhatsApp/Telegram) are already built:** Reuse the message_queue table with `channel = 'slack'`. Reuse any shared message service base class.

---

## What You ARE Building

### 1. Slack Service (`backend/slack_service.py`)

```python
class SlackService:
    def __init__(self, db: Session, user: models.User):
        self.db = db
        self.user = user

    async def execute_slack_async(
        self,
        config: dict,
        input_data: dict,
        workflow_id: int = None,
        execution_id: int = None,
        component_id: int = None,
    ) -> dict:
        """
        1. Resolve recipient Slack user ID from input_data or contact record
        2. Generate message via Claude API (same prompt system)
           - Inject Slack-specific system instruction (see below)
        3. Run AI filter if enabled (same as email)
        4. Run timeline check if enabled (same as email)
        5. Create queue entry in message_queue table
        6. Return for approval
        """
```

**Slack-specific prompt injection:**

````
CHANNEL: Slack Direct Message
CONSTRAINTS:
- Write like a Slack message, not an email. Casual, direct, no formalities.
- No subject line. Open with the person's name or jump straight into content.
- Slack mrkdwn formatting: *bold*, _italic_, ~strikethrough~, `code`, ```code block```, >blockquote
- Use bullet points (â¢) for action items or lists.
- Can include links: <https://url.com|Display Text>
- Keep it scannable â people skim Slack. 2-4 short paragraphs max.
- Emoji use is natural and encouraged (:wave:, :rocket:, :white_check_mark:).
- No "Dear", "Hi [Name],", "Best regards", "Sincerely" â this isn't email.
- If sharing meeting notes/summary, use a structured format with headers.
- Maximum 4000 characters (Slack message limit), but aim for 200-800 chars.
````

### 2. Slack Delivery Adapter (`backend/slack_delivery.py`)

Wrapper around Slack Web API:

```python
from slack_sdk.web.async_client import AsyncWebClient

class SlackAdapter:
    def __init__(self, bot_token: str):
        self.client = AsyncWebClient(token=bot_token)

    async def send_dm(self, user_id: str, text: str, blocks: list = None) -> dict:
        """
        Send DM via Slack. Opens a conversation (DM channel) then posts message.
        """
        # Step 1: Open/get DM channel with user
        conversation = await self.client.conversations_open(users=[user_id])
        channel_id = conversation["channel"]["id"]

        # Step 2: Send message
        result = await self.client.chat_postMessage(
            channel=channel_id,
            text=text,          # Fallback text
            blocks=blocks,      # Rich formatting (optional)
            unfurl_links=True,
            unfurl_media=True,
        )
        return {
            "channel": channel_id,
            "ts": result["ts"],         # Message timestamp (Slack's message ID)
            "status": "sent",
        }

    async def send_channel_message(self, channel_id: str, text: str, thread_ts: str = None) -> dict:
        """
        Send message to a channel (for team notifications).
        Optional: reply in thread if thread_ts provided.
        """
        result = await self.client.chat_postMessage(
            channel=channel_id,
            text=text,
            thread_ts=thread_ts,
        )
        return {
            "channel": channel_id,
            "ts": result["ts"],
            "status": "sent",
        }

    async def schedule_message(self, channel_id: str, text: str, post_at: int) -> dict:
        """
        Schedule a message for later delivery.
        post_at: Unix timestamp of when to send.
        """
        result = await self.client.chat_scheduleMessage(
            channel=channel_id,
            text=text,
            post_at=post_at,
        )
        return {
            "channel": channel_id,
            "scheduled_message_id": result["scheduled_message_id"],
            "status": "scheduled",
        }

    async def lookup_user_by_email(self, email: str) -> dict:
        """
        Find Slack user by their email address.
        This is how we bridge Scurry contacts â Slack users.
        """
        try:
            result = await self.client.users_lookupByEmail(email=email)
            return {
                "user_id": result["user"]["id"],
                "display_name": result["user"]["profile"]["display_name"],
                "real_name": result["user"]["profile"]["real_name"],
                "status": "found",
            }
        except Exception:
            return {"status": "not_found"}

    async def list_workspace_users(self) -> list:
        """List all users in the workspace (for contact matching UI)."""
        result = await self.client.users_list()
        return [
            {
                "user_id": m["id"],
                "name": m["profile"].get("real_name", ""),
                "email": m["profile"].get("email", ""),
                "display_name": m["profile"].get("display_name", ""),
                "is_bot": m.get("is_bot", False),
            }
            for m in result["members"]
            if not m.get("deleted") and not m.get("is_bot")
        ]
```

### 3. API Routes (`backend/slack.py`)

FastAPI router:

- `POST /slack/send` â Execute Slack component (called by workflow engine)
- `GET /slack/queue` â List queued Slack messages
- `POST /slack/queue/{id}/approve` â Approve and schedule
- `POST /slack/queue/{id}/edit` â Manual edit
- `POST /slack/queue/{id}/skip` â Skip
- `DELETE /slack/queue/{id}` â Delete
- `POST /slack/queue/{id}/ai-edit` â Quick AI edit
- `GET /slack/users` â List workspace users (for recipient picker)
- `GET /slack/users/lookup?email=x` â Find Slack user by email
- `GET /slack/channels` â List channels (for channel message mode)
- `POST /slack/oauth/callback` â OAuth callback for Slack app install

### 4. Database Model (`backend/models_patch_slack.py`)

**Use the existing `email_queue` table.** Add `channel = 'slack'`. Same pattern as SMS/WhatsApp/Telegram â table gets renamed later.

```sql
-- If previous components haven't already added these:
ALTER TABLE email_queue ADD COLUMN IF NOT EXISTS channel VARCHAR(20) DEFAULT 'email';
ALTER TABLE email_queue ADD COLUMN IF NOT EXISTS delivery_status VARCHAR(20);

-- Slack-specific fields
ALTER TABLE email_queue ADD COLUMN slack_user_id VARCHAR(20);
ALTER TABLE email_queue ADD COLUMN slack_channel_id VARCHAR(20);
ALTER TABLE email_queue ADD COLUMN slack_message_ts VARCHAR(20);
ALTER TABLE email_queue ADD COLUMN slack_scheduled_message_id VARCHAR(50);
ALTER TABLE email_queue ADD COLUMN slack_thread_ts VARCHAR(20);
ALTER TABLE email_queue ADD COLUMN is_channel_message BOOLEAN DEFAULT FALSE;
```

**IMPORTANT:** Same email_queue table, `channel = 'slack'`. All existing queries still work.

### 5. Integration Patches (`backend/INTEGRATION_PATCHES.py`)

1. `components.py` â Add `"slack"` to COMPONENT_TYPES
2. `executions.py` â Add `execute_slack()` static method + dispatcher entry
3. `main.py` â Register slack router
4. `requirements.txt` â Add `slack-sdk>=3.27.0`
5. `migrations/` â Alembic migration

### 6. Slack App Setup & OAuth

Users install a Slack App to their workspace. This requires:

**Slack App Configuration (created once by Scurry):**

- App name: "Scurry.ai"
- Bot token scopes: `chat:write`, `users:read`, `users:read.email`, `channels:read`, `im:write`
- OAuth redirect URL: `https://app.scurry.ai/integrations/slack/callback`
- Install flow: User clicks "Connect Slack" in Settings â Integrations â redirected to Slack OAuth â approves â token stored

**Credentials stored per user:**

- Bot Token (`xoxb-...`) â for API calls
- Team ID â Slack workspace identifier
- Bot User ID â the bot's own user ID (to avoid messaging self)

Store encrypted in user's integration_settings JSON.

### 7. Contact â Slack User Matching

**Primary method: Email lookup**

```python
async def resolve_slack_recipient(self, input_data: dict) -> str:
    """
    Try to find the Slack user ID for the recipient.
    Priority:
    1. Explicit slack_user_id in input_data
    2. Look up by email from contact record
    3. Manual assignment from Scurry contact â Slack user mapping
    """
    # Direct ID
    if input_data.get("slack_user_id"):
        return input_data["slack_user_id"]

    # Email lookup
    email = input_data.get("email") or input_data.get("recipient_email")
    if email:
        result = await self.slack_adapter.lookup_user_by_email(email)
        if result["status"] == "found":
            return result["user_id"]

    # Check stored mapping
    mapping = self.get_slack_contact_mapping(input_data.get("contact_id"))
    if mapping:
        return mapping.slack_user_id

    return None  # Queue with "missing_recipient" status
```

**This works well because:** Most B2B contacts share the same email in Scurry and Slack (especially in Slack Connect workspaces). Email lookup covers 80%+ of cases.

### 8. Two Delivery Modes

**Mode A: Direct Message (default)**

- One-to-one DM with a specific Slack user
- Used for: personal follow-ups, deal handoffs, action item assignments

**Mode B: Channel Message**

- Post to a Slack channel (e.g., #deals, #team-updates)
- Used for: team notifications, meeting summaries, deal progress updates
- Optional: threaded reply to group related messages

Config determines which mode:

```python
"delivery_mode": {
    "type": "select",
    "options": ["dm", "channel"],
    "default": "dm"
},
"target_channel": {
    "type": "text",
    "label": "Channel (for channel mode)",
    "placeholder": "#deals or C0123456789",
    "visible_when": {"delivery_mode": "channel"}
}
```

### 9. Tests

- Unit tests: Slack message generation, mrkdwn formatting, user lookup
- Integration tests: Queue CRUD, approval flow, OAuth token handling
- Mock Slack API: Never hit real Slack in tests
- Edge cases: User not found, deactivated user, bot not in channel, rate limits

---

## Config Schema

```python
"slack": {
    "name": "Slack Message",
    "description": "Send AI-generated Slack DMs or channel messages",
    "icon": "hash",
    "color": "#4A154B",
    "category": "outbound",
    "inputs": ["trigger_data", "extracted_information", "research_brief"],
    "outputs": ["message_body", "slack_user_id", "approval_status", "sent_at"],
    "config_schema": {
        "ai_prompt": {
            "type": "textarea",
            "label": "AI Instructions",
            "placeholder": "Tell the AI what kind of Slack message to write...",
            "required": True
        },
        "delivery_mode": {
            "type": "select",
            "label": "Delivery Mode",
            "options": ["dm", "channel"],
            "default": "dm",
            "help": "DM = direct message to one person. Channel = post to a Slack channel."
        },
        "target_channel": {
            "type": "text",
            "label": "Target Channel",
            "placeholder": "#deals",
            "visible_when": {"delivery_mode": "channel"},
            "help": "Channel name or ID"
        },
        "thread_replies": {
            "type": "toggle",
            "label": "Thread follow-ups",
            "default": True,
            "help": "Send sequence messages as threaded replies to the first message"
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
        "include_meeting_summary": {
            "type": "toggle",
            "label": "Include meeting summary block",
            "default": False,
            "help": "Appends a formatted meeting summary to the message"
        }
    }
}
```

---

## Slack-Specific Feature: Threaded Sequences

Unlike email/SMS/WhatsApp where each message is standalone, Slack sequences can be **threaded**:

```
[DM Channel with John]
âââ Message 1: "Hey John, great meeting today. Here's what I took away..." (ts: 1234)
â   âââ Message 2 (thread reply, Day 3): "Following up on the ROI analysis..." (thread_ts: 1234)
â   âââ Message 3 (thread reply, Day 7): "Quick check â any thoughts on..." (thread_ts: 1234)
```

**Implementation:** When `thread_replies` is enabled:

1. First message in sequence sends normally â store `ts` as `thread_ts`
2. Subsequent messages in same sequence use `thread_ts` to reply in thread
3. Store `thread_ts` on the workflow execution context so downstream components can reference it

This keeps the DM clean (one notification thread per deal/meeting) instead of spamming separate messages.

---

## Slack Native: Scheduled Messages

Slack has **built-in scheduled messages** (`chat.scheduleMessage`). This means for the "fixed delay" send timing, we can use Slack's native scheduling instead of our own scheduler polling:

```python
if send_timing == "fixed_delay":
    # Use Slack's native scheduling â more reliable than our own
    post_at = int((datetime.now() + timedelta(days=delay_days)).timestamp())
    result = await self.slack_adapter.schedule_message(
        channel_id=dm_channel,
        text=message_body,
        post_at=post_at,
    )
    # Store scheduled_message_id for cancellation if needed
```

**Benefit:** No need to run our scheduler for Slack messages. Slack handles the timing. One less moving part.

---

## Key Constraints

- **Slack App must be installed to the workspace.** OAuth flow required. Can't just plug in a token.
- **Bot must be in the channel for channel messages.** Auto-join on first attempt, or error gracefully.
- **4000 character limit per message.** Enforce in AI prompt.
- **Rate limits:** 1 message per second per channel. Implement queue-level rate limiting for bulk sends.
- **Slack Connect:** Works for external users in shared channels/DMs, but email lookup won't work for external users. Need manual mapping.
- **No delivery receipts.** Slack doesn't have "read receipts" in the API. We know it was sent, not read.
- **Free tier workspaces:** 90-day message history limit. Not our problem, but worth noting.

---

## Build Order

1. Database migration (message_queue Slack fields)
2. SlackAdapter (API wrapper â send DM, channel message, schedule, user lookup)
3. OAuth flow (install Slack app, store tokens)
4. Contact â Slack user matching (email lookup + manual mapping)
5. SlackService class (AI generation + queue creation)
6. FastAPI routes (queue CRUD + approval + user/channel listing)
7. Threaded sequence support
8. Integration patches
9. Tests

---

## Files to Create

```
slack-component/
âââ CLAUDE.md                â This file
âââ README.md                â Quick overview
âââ backend/
â   âââ slack_service.py     â Core service (generation + queue + AI features)
â   âââ slack_delivery.py    â Slack Web API adapter
â   âââ slack.py             â FastAPI routes
â   âââ slack_oauth.py       â OAuth install flow
â   âââ models_patch_slack.py â Database model/migration
â   âââ INTEGRATION_PATCHES.py
âââ tests/
    âââ test_slack_service.py
    âââ test_slack_delivery.py
    âââ test_slack_routes.py
```

---

## Reference Files (Read These First)

1. `research-component/backend/research_service.py` â Service class pattern
2. `research-component/backend/INTEGRATION_PATCHES.py` â Integration pattern
3. `sms-component/CLAUDE.md` â SMS spec (shared patterns)
4. `whatsapp-component/CLAUDE.md` â WhatsApp spec (shared patterns)
5. `Scurry-Platform-Context-Doc.md` â Full platform architecture
6. `CLAUDE.md` (root) â Project rules

---

## Hard Rules

- **Never break existing flows.** Slack is additive.
- **Never store OAuth tokens in plaintext.** Encrypt at rest.
- **Never send messages without user approval.** Queue first.
- **Never post to channels without explicit config.** Default is DM only.
- **Never message the bot itself.** Filter out bot user ID from recipients.
- **Feature branch only.** Branch: `feature/slack-component`. Never commit to main.
- **Present tense commits.** Match project convention.
