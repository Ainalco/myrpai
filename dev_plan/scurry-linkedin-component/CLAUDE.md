# LinkedIn Component â Scurry.ai Add-On

## â ï¸ MUST USE CLAUDE CODE FOR THIS PROJECT

This project is designed for development with **Claude Code** (Anthropic's CLI coding agent). Do NOT attempt to build this manually or with a different AI tool. Claude Code has the context, codebase access, and agentic capabilities required. Install: https://docs.anthropic.com/en/docs/claude-code

---

## What This Is

A messaging component for Scurry.ai that generates AI-powered LinkedIn message sequences (connection requests, InMails, and DMs) from meeting transcripts. Unlike the other channel components, **LinkedIn does NOT support automated sending via API for most users**. This component generates draft messages that go into Scurry's queue for the user to copy and send manually on LinkedIn â OR â sends via LinkedIn API for users with LinkedIn Sales Navigator Team/Enterprise who have API access.

**Think of it as:** the email component's AI generation + queue/approval, but instead of `send_via_smtp()`, the default output is a **draft queue** the user acts on manually. API send is the premium path.

---

## Why This Matters

**The reality of B2B sales follow-ups:**

After a meeting, the salesperson often needs to:

1. Send a follow-up email (Scurry already does this)
2. Connect on LinkedIn + send a personalized connection note
3. Send a LinkedIn DM or InMail if already connected

Steps 2 and 3 are currently 100% manual. Scurry can generate the content automatically â the user just needs to paste it. That alone saves 5-10 minutes per meeting.

**For Sales Navigator users:** Full API send is possible, making this fully automated like the email component.

---

## Architecture â How It Fits

```
Input (Fireflies) â Text Generation â [LinkedIn Msg 1] â [LinkedIn Msg 2] â [LinkedIn Msg 3]
OR mixed: â [Email 1] â [LinkedIn Connection] â [Email 2]
```

New component type `linkedin_message` in ComponentExecutor.

**Two delivery modes:**

1. **Draft Mode (default)** â AI generates message â queue â user reviews â copies text â sends manually on LinkedIn
2. **API Mode (Sales Navigator)** â AI generates message â queue â user approves â Scurry sends via LinkedIn API

---

## What Already Exists (DO NOT REBUILD)

Same as all other channel components â plug into:

1. **ComponentExecutor dispatcher** â Add `elif component_type == "linkedin": execute_linkedin()`
2. **COMPONENT_TYPES registry** â Register LinkedIn
3. **AI prompt system** â Same Claude API + variable substitution
4. **Queue/approval flow** â Same pending â approved â sent/copied
5. **Send timing** â Reuse (for API mode). In draft mode, timing is advisory ("send this on Day 3").
6. **AI Filter** â Same pre-send validation
7. **Timeline Check** â Same contact history review
8. **Acorn cost tracking** â Same deduction for AI generation

---

## What You ARE Building

### 1. LinkedIn Service (`backend/linkedin_service.py`)

```python
class LinkedInService:
    def __init__(self, db: Session, user: models.User):
        self.db = db
        self.user = user

    async def execute_linkedin_async(
        self,
        config: dict,
        input_data: dict,
        workflow_id: int = None,
        execution_id: int = None,
        component_id: int = None,
    ) -> dict:
        """
        1. Resolve recipient LinkedIn profile from input_data or contact record
        2. Determine message type: connection_request, dm, or inmail
        3. Generate message via Claude API (same prompt system)
           - Inject LinkedIn-specific constraints (see below)
        4. Run AI filter if enabled
        5. Run timeline check if enabled
        6. Create queue entry in message_queue table
           - Draft mode: status = "draft_ready" (user copies and sends)
           - API mode: status = "pending" (standard approval â send flow)
        7. Return for review
        """
```

**LinkedIn-specific prompt injection:**

For **Connection Requests:**

```
CHANNEL: LinkedIn Connection Request
HARD CONSTRAINTS:
- Maximum 300 characters. This is a hard LinkedIn limit. NO EXCEPTIONS.
- No links allowed in connection request notes.
- Reference the meeting specifically â this is a warm connection, not cold outreach.
- Be personal and specific. Generic "I'd like to add you" gets ignored.
- No sales pitch. Just establish the connection with meeting context.
- First person, casual professional tone.
```

For **Direct Messages (already connected):**

```
CHANNEL: LinkedIn Direct Message
CONSTRAINTS:
- Maximum 8000 characters, but aim for 200-500.
- Professional but conversational. LinkedIn DMs sit between email and Slack in formality.
- Can include links (LinkedIn auto-previews them).
- Reference the meeting and any shared connections/context.
- No heavy formatting â LinkedIn DMs support minimal markdown.
- Can include bullet points with â¢ character.
- One clear CTA per message.
```

For **InMails (Sales Navigator):**

```
CHANNEL: LinkedIn InMail
CONSTRAINTS:
- Subject line required. Maximum 200 characters.
- Body maximum 1900 characters for free InMails, 3000 for paid.
- InMails have higher open rates than email â make the subject compelling.
- Reference the meeting. InMail after a meeting is highly unusual and stands out.
- Professional tone. InMail feels more formal than DM.
- Include a clear, specific CTA.
```

### 2. LinkedIn Delivery Adapter (`backend/linkedin_delivery.py`)

**Draft Mode (no API needed):**

```python
class LinkedInDraftAdapter:
    """
    No external API calls. Just formats the message for the queue.
    User copies the text and sends it on LinkedIn manually.
    """

    def prepare_draft(self, message_type: str, content: dict) -> dict:
        """
        Format the message for the draft queue.
        Returns structured data the frontend renders as a "copy to clipboard" card.
        """
        if message_type == "connection_request":
            return {
                "type": "connection_request",
                "note": content["body"],         # Max 300 chars
                "char_count": len(content["body"]),
                "recipient_name": content["recipient_name"],
                "recipient_linkedin_url": content.get("linkedin_url"),
                "delivery_mode": "draft",
                "instructions": "Copy the note below and send as a LinkedIn connection request.",
            }
        elif message_type == "dm":
            return {
                "type": "dm",
                "body": content["body"],
                "recipient_name": content["recipient_name"],
                "recipient_linkedin_url": content.get("linkedin_url"),
                "delivery_mode": "draft",
                "instructions": "Copy the message below and send as a LinkedIn DM.",
            }
        elif message_type == "inmail":
            return {
                "type": "inmail",
                "subject": content["subject"],
                "body": content["body"],
                "recipient_name": content["recipient_name"],
                "delivery_mode": "draft",
                "instructions": "Copy the subject and message below and send as a LinkedIn InMail.",
            }
```

**API Mode (Sales Navigator â Phase 2):**

```python
class LinkedInAPIAdapter:
    """
    For LinkedIn Sales Navigator Team/Enterprise users with API access.
    Uses LinkedIn Marketing/Sales API for programmatic sending.
    """
    BASE_URL = "https://api.linkedin.com/v2"

    def __init__(self, access_token: str):
        self.access_token = access_token

    async def send_message(self, recipient_urn: str, body: str) -> dict:
        """
        Send LinkedIn message via API.
        Requires: LinkedIn Sales Navigator Team/Enterprise + approved API app.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/messages",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "X-Restli-Protocol-Version": "2.0.0",
                },
                json={
                    "recipients": [recipient_urn],
                    "subject": "",
                    "body": body,
                }
            )
            return response.json()

    async def send_connection_request(self, recipient_urn: str, message: str) -> dict:
        """Send connection request with note."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/invitations",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "X-Restli-Protocol-Version": "2.0.0",
                },
                json={
                    "invitee": recipient_urn,
                    "message": message,  # Max 300 chars
                }
            )
            return response.json()
```

### 3. API Routes (`backend/linkedin.py`)

- `POST /linkedin/generate` â Execute LinkedIn component (generate message)
- `GET /linkedin/queue` â List queued LinkedIn messages/drafts
- `POST /linkedin/queue/{id}/approve` â Approve (API mode: sends. Draft mode: marks as "ready to copy")
- `POST /linkedin/queue/{id}/edit` â Manual edit
- `POST /linkedin/queue/{id}/skip` â Skip
- `DELETE /linkedin/queue/{id}` â Delete
- `POST /linkedin/queue/{id}/ai-edit` â Quick AI edit
- `POST /linkedin/queue/{id}/mark-sent` â User marks as manually sent (draft mode)
- `GET /linkedin/queue/{id}/copy` â Returns formatted text for clipboard copy
- `POST /linkedin/oauth/callback` â OAuth callback (for API mode)

### 4. Database Model (`backend/models_patch_linkedin.py`)

**Use the existing `email_queue` table.** Add `channel = 'linkedin'`. Same pattern as all other channel components â table gets renamed later.

```sql
-- If previous components haven't already added these:
ALTER TABLE email_queue ADD COLUMN IF NOT EXISTS channel VARCHAR(20) DEFAULT 'email';
ALTER TABLE email_queue ADD COLUMN IF NOT EXISTS delivery_status VARCHAR(20);

-- LinkedIn-specific fields
ALTER TABLE email_queue ADD COLUMN linkedin_message_type VARCHAR(30);  -- connection_request, dm, inmail
ALTER TABLE email_queue ADD COLUMN linkedin_profile_url VARCHAR(500);
ALTER TABLE email_queue ADD COLUMN linkedin_urn VARCHAR(100);
ALTER TABLE email_queue ADD COLUMN delivery_mode VARCHAR(10) DEFAULT 'draft';  -- draft, api
ALTER TABLE email_queue ADD COLUMN manually_sent_at TIMESTAMP WITH TIME ZONE;
```

**IMPORTANT:** Same email_queue table, `channel = 'linkedin'`. All existing queries still work.

**Draft mode status values:**

- `draft_ready` â AI generated, ready for user to copy
- `copied` â User copied the text (optional tracking)
- `manually_sent` â User confirmed they sent it on LinkedIn

### 5. Integration Patches

Standard pattern:

1. `components.py` â Add `"linkedin"` to COMPONENT_TYPES
2. `executions.py` â Add `execute_linkedin()` + dispatcher
3. `main.py` â Register linkedin router
4. `requirements.txt` â `httpx` (already present from other components)
5. `migrations/` â Alembic migration

### 6. Contact â LinkedIn Matching

**How we find the LinkedIn profile:**

```python
async def resolve_linkedin_recipient(self, input_data: dict) -> dict:
    """
    Priority:
    1. Explicit linkedin_url in input_data (from Text Generation extraction)
    2. Stored linkedin_url on Scurry contact record
    3. Pipedrive contact field (if CRM connected)
    4. None â user manually adds LinkedIn URL in queue
    """
    # From transcript extraction
    linkedin_url = input_data.get("linkedin_url")
    if linkedin_url:
        return {"url": linkedin_url, "source": "transcript"}

    # From contact record
    contact_id = input_data.get("contact_id")
    if contact_id:
        contact = self.db.query(Contact).get(contact_id)
        if contact and contact.linkedin_url:
            return {"url": contact.linkedin_url, "source": "contact"}

    # From Pipedrive
    pipedrive_person = input_data.get("pipedrive_person", {})
    linkedin_field = pipedrive_person.get("linkedin") or pipedrive_person.get("social_linkedin")
    if linkedin_field:
        return {"url": linkedin_field, "source": "pipedrive"}

    return {"url": None, "source": None}  # User adds manually
```

**Text Generation update:** Add `linkedin_url` to the "Bonus Nut" extraction fields so it's automatically pulled from meeting transcripts when mentioned.

### 7. Tests

- Unit tests: Message generation per type (connection/DM/InMail), char limit enforcement, draft formatting
- Integration tests: Queue CRUD, approval flow, manual send tracking, copy endpoint
- Edge cases: Over char limit, missing LinkedIn URL, connection request without note, API mode fallback to draft
- No mock LinkedIn API needed for draft mode (no external calls)

---

## Config Schema

```python
"linkedin": {
    "name": "LinkedIn Message",
    "description": "Generate LinkedIn connection requests, DMs, and InMails",
    "icon": "linkedin",
    "color": "#0A66C2",
    "category": "outbound",
    "inputs": ["trigger_data", "extracted_information", "research_brief"],
    "outputs": ["message_body", "message_type", "linkedin_url", "approval_status"],
    "config_schema": {
        "message_type": {
            "type": "select",
            "label": "Message Type",
            "options": ["connection_request", "dm", "inmail"],
            "default": "dm",
            "help": "Connection Request: 300 char limit, for new connections. DM: for existing connections. InMail: Sales Navigator only."
        },
        "ai_prompt": {
            "type": "textarea",
            "label": "AI Instructions",
            "placeholder": "Tell the AI what kind of LinkedIn message to write...",
            "required": True
        },
        "delivery_mode": {
            "type": "select",
            "label": "Delivery Mode",
            "options": ["draft", "api"],
            "default": "draft",
            "help": "Draft: AI generates, you copy & send manually. API: Auto-send (requires Sales Navigator)."
        },
        "send_timing": {
            "type": "select",
            "options": ["immediate", "fixed_delay", "ai_decides"],
            "default": "fixed_delay",
            "help": "In draft mode, timing is advisory (suggested send date)."
        },
        "delay_config": {
            "type": "object",
            "fields": {
                "delay_hours": {"type": "number", "default": 0},
                "delay_days": {"type": "number", "default": 1},
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
        }
    }
}
```

---

## Draft Mode Queue UX (Frontend Guidance)

The LinkedIn draft queue is different from email/SMS/WhatsApp queues because the user acts on it manually:

```
[LinkedIn DM Draft] â John Smith
âââ Status: ð Ready to Send
âââ Suggested send: Tomorrow at 10 AM
âââ LinkedIn: linkedin.com/in/johnsmith â [Open Profile]
âââ Message type: Direct Message
â
âââ âââââââââââââââââââââââââââââââââââ
â   â Hey John, really enjoyed our    â
â   â conversation about the RevOps   â
â   â pipeline challenges...          â
â   â                                 â
â   â [ð Copy Message]  [âï¸ Edit]    â
â   âââââââââââââââââââââââââââââââââââ
â
âââ [Mark as Sent]  [Skip]  [Delete]
âââ [AI Edit: "make it shorter"]
```

**Key actions:**

- **Copy Message** â Copies formatted text to clipboard. User pastes into LinkedIn.
- **Open Profile** â Opens LinkedIn profile in new tab (so user can send the message).
- **Mark as Sent** â User confirms they sent it. Updates status + timestamp. This keeps Scurry's timeline accurate.
- **Suggested send date** â Advisory. In draft mode, the "when to send" is a recommendation, not an automated action.

---

## Key Constraints

- **Draft mode is the default and primary use case.** API mode is Phase 2 and requires Sales Navigator. Build draft mode first and make it excellent.
- **Connection request: 300 chars HARD LIMIT.** LinkedIn rejects anything over. Test this extensively. The AI prompt must enforce it strictly.
- **InMail subject: 200 chars max.** Also hard limit.
- **LinkedIn URL matching is imperfect.** Users may need to manually add LinkedIn URLs to contacts. Make the "add LinkedIn URL" flow smooth in the queue UI.
- **No delivery confirmation in draft mode.** We rely on the user clicking "Mark as Sent." Track this but don't nag.
- **LinkedIn API access is restricted.** Most users won't have API access. Draft mode must work perfectly standalone.
- **Rate limiting (API mode):** LinkedIn has strict rate limits. Max 100 API calls per day for messaging. Implement daily cap tracking.

---

## Build Order

1. Database migration (message_queue LinkedIn fields + new statuses)
2. LinkedInDraftAdapter (format drafts for queue â no external API calls)
3. LinkedInService class (AI generation per message type + queue creation)
4. Contact â LinkedIn URL matching
5. FastAPI routes (queue CRUD + copy endpoint + mark-sent)
6. Integration patches
7. Tests
8. **(Phase 2)** LinkedInAPIAdapter for Sales Navigator users
9. **(Phase 2)** OAuth flow for LinkedIn API

---

## Files to Create

```
linkedin-component/
âââ CLAUDE.md                    â This file
âââ README.md                    â Quick overview
âââ backend/
â   âââ linkedin_service.py      â Core service (generation + queue)
â   âââ linkedin_delivery.py     â Draft adapter (Phase 1) + API adapter (Phase 2)
â   âââ linkedin.py              â FastAPI routes
â   âââ models_patch_linkedin.py â Database model/migration
â   âââ INTEGRATION_PATCHES.py
âââ tests/
    âââ test_linkedin_service.py
    âââ test_linkedin_delivery.py
    âââ test_linkedin_routes.py
```

---

## Reference Files (Read These First)

1. `research-component/backend/research_service.py` â Service class pattern
2. `research-component/backend/INTEGRATION_PATCHES.py` â Integration pattern
3. `sms-component/CLAUDE.md` â SMS spec (shared patterns)
4. `whatsapp-component/CLAUDE.md` â WhatsApp spec (24h window = similar to LinkedIn API restriction)
5. `Scurry-Platform-Context-Doc.md` â Full platform architecture
6. `CLAUDE.md` (root) â Project rules

---

## Hard Rules

- **Never break existing flows.** LinkedIn is additive.
- **Never store LinkedIn OAuth tokens in plaintext.** Encrypt at rest.
- **Never auto-send in draft mode.** The whole point is user control.
- **Never exceed character limits.** Connection request = 300, InMail subject = 200. Hard reject, don't truncate.
- **Never expose LinkedIn profile data beyond what's needed.** Privacy matters.
- **Feature branch only.** Branch: `feature/linkedin-component`. Never commit to main.
- **Present tense commits.** Match project convention.
- **Draft mode is Phase 1. API mode is Phase 2.** Don't build API mode until draft mode is complete and tested.
