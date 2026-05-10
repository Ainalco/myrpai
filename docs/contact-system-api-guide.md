# 🐿️ Contact System API — Claude Code Developer Guide

**For:** Tauhid (Claude Code)
**Branch:** `josh`
**Stack:** FastAPI, SQLAlchemy, PostgreSQL, Alembic

---

## What This Doc Covers

Everything needed to build the contact system backend. The frontend UI is already built with mock data — your job is to make the API return data in the exact shapes the UI expects so we can swap `MOCK_CONTACTS` → `useQuery` with zero frontend changes.

**Reference docs in project knowledge (read these for full context):**
- `Dev — Contact System Developer Handoff (Mar 2026)` — full architecture, data models, CRM abstraction, conflict detection, AI intelligence layer
- `Dev — Contact System Roadmap (Mar 2026)` — phased integration plan
- `Dev — Email Queue README (Mar 2026)` — existing email queue system

This doc is the **build spec**. The handoff doc is the **architecture bible**. When in doubt, the handoff doc wins.

---

## Database Context

**Already exists (from migrations 011, 020):**
- `contacts` table — basic: id, user_id, email, name, title, company, avatar_initials, last_contacted_at, contact_count
- `contact_activities` table — basic: id, contact_id, user_id, email_queue_id, activity_type, title, occurred_at, is_new, extra_data
- `organizations` table — this is the **billing/account** orgs table (Paddle, plan tiers). NOT contact orgs.
- `email_queue.contact_id` — already linked

**Migration 027 adds:**
- New columns on `contacts`: primary_email, contact_organization_id, external_person_id, crm_provider, status, last_activity_at, last_activity_type, last_activity_direction, deleted_at
- New columns on `contact_activities`: contact_organization_id, deal_id, direction, source_type, source_id, thread_id, subject, summary, raw_content, metadata, activity_at
- New tables: `contact_organizations`, `contact_emails`, `contact_deals`, `contact_stats`, `contact_pulse`, `thread_digests`, `meeting_history`, `sequence_runs`
- New columns on `email_queue`: thread_id, deal_id, sequence_run_id

**Critical naming:** Contact orgs use `contact_organizations` table and `contact_organization_id` FK — NOT `organizations` (that's billing).

---

## Frontend → API Contract

The UI is built. These are the **exact JSON shapes** each endpoint must return. Field names must match precisely — the frontend destructures these directly.

### GET /contacts — List View

The frontend currently loads all contacts and filters client-side. Return the full list (with server-side search/filter support for later).

```json
{
  "items": [
    {
      "id": 1,
      "name": "Sarah Chen",
      "email": "sarah@acmecorp.com",
      "orgId": 1,
      "orgName": "Acme Corp",
      "status": "active",
      "pipedrive": true,
      "lastActivity": "2h ago",
      "stats": {
        "sent": 23,
        "received": 8,
        "rate": "34.8%",
        "meetings": 3,
        "sequences": 2,
        "openDeals": 2,
        "dealValue": 45000
      },
      "emails": ["sarah@acmecorp.com", "s.chen@acme.io"]
    }
  ],
  "counts": {
    "active": 2,
    "paused": 1,
    "dnc": 1,
    "bounced": 1
  },
  "nextCursor": null,
  "hasMore": false
}
```

**Query params:** `?search=&status=&cursor=&limit=50`

**Notes:**
- `pipedrive` = true when `external_person_id IS NOT NULL AND crm_provider = 'pipedrive'`
- `lastActivity` = relative time string computed from `last_activity_at` ("2h ago", "1d ago", "3d ago", "1w ago")
- `rate` = string with percent sign (compute: `emails_received / emails_sent * 100` formatted to 1 decimal + "%")
- `counts` = status counts across ALL contacts (not just filtered page), always returned
- `stats` comes from `contact_stats` table (pre-computed)
- `emails` = list of all email addresses from `contact_emails` table

### GET /contacts/{id} — Detail View

Returns the full contact with all nested data. The frontend loads this once and renders all 5 tabs from it.

```json
{
  "id": 1,
  "name": "Sarah Chen",
  "email": "sarah@acmecorp.com",
  "orgId": 1,
  "orgName": "Acme Corp",
  "status": "active",
  "pipedrive": true,
  "lastActivity": "2h ago",
  "emails": ["sarah@acmecorp.com", "s.chen@acme.io"],
  "stats": {
    "sent": 23,
    "received": 8,
    "rate": "34.8%",
    "meetings": 3,
    "sequences": 2,
    "openDeals": 2,
    "dealValue": 45000
  },
  "pulse": {
    "summary": "Active prospect with strong buying signals...",
    "sentiment": "positive",
    "engagement": "high",
    "intent": "interested",
    "action": "continue_sequence",
    "topics": ["pricing", "integration", "timeline"],
    "objections": ["Salesforce integration", "team adoption"],
    "lastMeeting": "Mar 8, 2026"
  },
  "deals": [
    {
      "id": 1,
      "title": "Acme Corp - Enterprise License",
      "status": "open",
      "stage": "Negotiation",
      "value": 30000,
      "expected": "Apr 15, 2026"
    }
  ],
  "timeline": [
    {
      "id": 1,
      "type": "email_reply",
      "dir": "inbound",
      "source": "gmail_push",
      "subject": "Re: Implementation Timeline",
      "summary": "Sarah confirmed readiness pending CTO approval.",
      "at": "Mar 13, 10:24 AM",
      "deal": "Enterprise License"
    }
  ],
  "threads": [
    {
      "id": "t1",
      "summary": "Implementation timeline — confirmed readiness, pending CTO.",
      "sentiment": "positive",
      "status": "waiting_on_us",
      "msgs": 5,
      "lastAt": "Mar 13",
      "messages": [
        {
          "id": "m1",
          "from": "you",
          "to": "sarah@acmecorp.com",
          "subject": "Implementation Timeline",
          "body": "Hi Sarah,\n\nFollowing up on our demo...",
          "at": "Mar 11, 2:15 PM"
        }
      ]
    }
  ],
  "meetings": [
    {
      "id": 1,
      "date": "Mar 8, 2026",
      "source": "Fireflies",
      "summary": "45-min demo. Pricing, Salesforce, Q2.",
      "keyPoints": ["Budget approved Q2", "Team of 12"],
      "objections": ["Integration complexity"],
      "signals": ["Annual pricing interest"],
      "stage": "Negotiation"
    }
  ]
}
```

**Field mapping (DB → JSON):**

| DB field | JSON field | Transform |
|----------|-----------|-----------|
| `contact_stats.emails_sent` | `stats.sent` | direct |
| `contact_stats.emails_received` | `stats.received` | direct |
| `contact_stats.reply_rate` | `stats.rate` | format as `"{value}%"` |
| `contact_stats.meetings_count` | `stats.meetings` | direct |
| `contact_stats.active_sequences` | `stats.sequences` | direct |
| `contact_stats.open_deals` | `stats.openDeals` | direct |
| `contact_stats.total_deal_value` | `stats.dealValue` | direct |
| `contact_pulse.summary` | `pulse.summary` | direct |
| `contact_pulse.sentiment` | `pulse.sentiment` | direct |
| `contact_pulse.engagement_level` | `pulse.engagement` | direct |
| `contact_pulse.intent` | `pulse.intent` | direct |
| `contact_pulse.recommended_action` | `pulse.action` | direct |
| `contact_pulse.key_topics` | `pulse.topics` | direct (JSON array) |
| `contact_pulse.key_objections` | `pulse.objections` | direct (JSON array) |
| `contact_pulse.last_meeting_date` | `pulse.lastMeeting` | format as `"Mar 8, 2026"` or null |
| `contact_deals.stage_name` | `deals[].stage` | direct |
| `contact_deals.expected_close_date` | `deals[].expected` | format as `"Apr 15, 2026"` |
| `contact_activities.activity_type` | `timeline[].type` | direct |
| `contact_activities.direction` | `timeline[].dir` | direct |
| `contact_activities.source_type` | `timeline[].source` | direct |
| `contact_activities.activity_at` | `timeline[].at` | format as `"Mar 13, 10:24 AM"` |
| `thread_digests.thread_status` | `threads[].status` | direct |
| `thread_digests.message_count` | `threads[].msgs` | direct |
| `thread_digests.last_message_at` | `threads[].lastAt` | format as `"Mar 13"` |
| `meeting_history.buying_signals` | `meetings[].signals` | direct (JSON array) |
| `meeting_history.deal_stage_at_time` | `meetings[].stage` | direct |

**Thread messages — `from` field logic:**
- If the sender email matches the user's connected email account → `"you"`
- Otherwise → the sender's email address

**Timeline — `deal` field:**
- This is a string display name (e.g., `"Enterprise License"`), NOT a deal ID
- Populated by joining `contact_activities.deal_id` → `contact_deals.title` and extracting the short name

### GET /contact-organizations — Org List

```json
{
  "items": [
    {
      "id": 1,
      "name": "Acme Corp",
      "domain": "acmecorp.com",
      "contacts": 3,
      "openDeals": 2,
      "totalValue": 45000,
      "dnc": false,
      "dncProp": true
    }
  ]
}
```

**Query params:** `?search=&cursor=&limit=50`

**Notes:**
- `contacts` = count of non-deleted contacts with this `contact_organization_id`
- `openDeals` = sum of open deals across all contacts in this org
- `totalValue` = sum of deal values for open deals across all contacts
- `dnc` = true if ANY contact in org has `status = 'do_not_contact'`
- `dncProp` = `do_not_contact_propagation` from `contact_organizations`

### GET /contact-organizations/{id} — Org Detail

```json
{
  "id": 1,
  "name": "Acme Corp",
  "domain": "acmecorp.com",
  "contacts": 3,
  "openDeals": 2,
  "totalValue": 45000,
  "dnc": false,
  "dncProp": true,
  "persons": [
    {
      "id": 1,
      "name": "Sarah Chen",
      "email": "sarah@acmecorp.com",
      "status": "active"
    }
  ]
}
```

---

## API Endpoint Reference

**Router prefix:** `/contacts` for persons, `/contact-organizations` for orgs
**Auth:** All endpoints require authenticated user. All queries scoped by `user_id`.
**Pagination:** Cursor-based on all list endpoints.

### Persons

| Method | Endpoint | Description | Priority |
|--------|----------|-------------|----------|
| GET | /contacts | List + search + filter + counts | P0 |
| GET | /contacts/{id} | Full detail (all tabs data) | P0 |
| POST | /contacts | Manual create | P1 |
| PUT | /contacts/{id} | Update name, org, etc. | P1 |
| PUT | /contacts/{id}/status | Set active/paused/DNC/bounced | P1 |
| DELETE | /contacts/{id} | Soft-delete | P1 |
| POST | /contacts/{id}/note | Add note to timeline | P2 |
| POST | /contacts/{id}/merge | Merge with another contact | P2 |
| POST | /contacts/{id}/refresh-pulse | Regenerate Contact Pulse | P2 |
| GET | /contacts/export | CSV export | P2 |

### Organizations

| Method | Endpoint | Description | Priority |
|--------|----------|-------------|----------|
| GET | /contact-organizations | List + search | P0 |
| GET | /contact-organizations/{id} | Detail + persons list | P0 |
| PUT | /contact-organizations/{id} | Update (name, DNC propagation) | P1 |
| POST | /contact-organizations/{id}/merge | Merge orgs | P2 |
| GET | /contact-organizations/export | CSV export | P2 |

---

## Service Layer Functions

These are the core business logic functions. Build as `backend/services/contacts.py`.

### get_or_create_contact(db, user_id, email, name=None, organization_name=None) → Contact

The most important function. Called by the workflow engine when queuing emails.

```
1. Normalize email to lowercase
2. Check contact_emails table for existing match (JOIN contacts WHERE user_id AND deleted_at IS NULL)
3. If found → return existing contact
4. If not found:
   a. Acquire PostgreSQL advisory lock (hash of user_id + email)
   b. Double-check (another request may have created it while waiting)
   c. Extract domain from email
   d. Skip org creation for freemail domains (gmail.com, yahoo.com, etc.)
   e. For non-freemail: get_or_create org by domain (same advisory lock pattern)
   f. Create Contact record
   g. Create ContactEmail record (is_primary=True)
   h. Create ContactStats record (all zeros)
   i. Release advisory lock in finally block
   j. Return new contact
```

**Freemail domains list:**
gmail.com, yahoo.com, hotmail.com, outlook.com, aol.com, icloud.com, mail.com, protonmail.com, zoho.com, yandex.com, live.com, msn.com, me.com, fastmail.com, tutanota.com, hey.com

### log_activity(db, user_id, contact_id, activity_type, direction, source_type, source_id=None, ...) → ContactActivity

```
1. Check idempotency: if source_id provided, check uq_activity_source constraint
2. Create ContactActivity record
3. Update contact.last_activity_at, last_activity_type, last_activity_direction
4. Update contact_stats (increment appropriate counter)
5. Return the activity
```

### update_contact_stats(db, contact_id)

Recompute all stats from scratch (safe recalc):
```
emails_sent = COUNT activities WHERE activity_type = 'email_sent'
emails_received = COUNT activities WHERE direction = 'inbound'
reply_rate = (emails_received / emails_sent * 100) if emails_sent > 0 else 0
meetings_count = COUNT meeting_history records
active_sequences = COUNT sequence_runs WHERE status = 'active'
open_deals = COUNT contact_deals WHERE status = 'open'
total_deal_value = SUM contact_deals.value WHERE status = 'open'
```

### merge_contacts(db, user_id, keep_id, merge_id) → Contact

```
1. Verify both contacts exist and belong to user_id
2. Move all contact_emails from merge → keep
3. Move all contact_activities from merge → keep
4. Move all contact_deals from merge → keep
5. Move all thread_digests from merge → keep
6. Move all meeting_history from merge → keep
7. Move all sequence_runs from merge → keep
8. Update email_queue.contact_id from merge → keep
9. Log a 'contact_merged' activity on the kept contact
10. Soft-delete the merged contact (set deleted_at)
11. Recompute stats on kept contact
```

---

## Hard Rules

1. **Every DB query scoped by `user_id`** — no exceptions
2. **Soft delete everywhere** — `WHERE deleted_at IS NULL` on all reads
3. **Parameterized queries only** — no string concatenation in SQL
4. **Advisory locks on create** — prevent race condition duplicates
5. **Append-only activities** — never edit or delete activities
6. **Structured JSON logging** — every operation logs user_id + contact_id + operation name
7. **All work on `josh` branch** — never commit to main

---

## Build Order

Build and test each phase before moving to the next. Each phase makes more of the UI functional.

### Phase 1: Models + Migration

Run migration 027. Verify all tables exist. This may already be done by the time you read this.

**Test:** `alembic upgrade head` succeeds. All tables queryable.

### Phase 2: Core CRUD + List Endpoints (P0)

Build the router (`backend/routers/contacts.py`) with:
- GET /contacts (list with search, status filter, counts)
- GET /contacts/{id} (full detail — return empty arrays for deals/timeline/threads/meetings/pulse until those are populated)
- GET /contact-organizations (list with search)
- GET /contact-organizations/{id} (detail + persons)
- `get_or_create_contact()` service function

Register router in main.py.

**Test:**
- Manually POST a contact → appears in GET /contacts
- Search by name/email/org works
- Status filter returns correct subsets
- Counts are accurate
- GET /contacts/{id} returns full shape (empty nested arrays is fine)
- Org list/detail work

**Frontend wire:** Replace `MOCK_CONTACTS` and `MOCK_ORGS` with useQuery calls. Both list views go live.

### Phase 3: Write Endpoints (P1)

- POST /contacts (manual create, calls get_or_create_contact)
- PUT /contacts/{id} (update)
- PUT /contacts/{id}/status (status change + DNC propagation logic)
- DELETE /contacts/{id} (soft delete)
- PUT /contact-organizations/{id} (update)

**Test:**
- Create → appears in list
- Update name → reflected
- Set DNC → contact shows DNC status
- Set DNC with org propagation → other contacts at same org get flagged
- Delete → gone from list, still in DB with deleted_at set

### Phase 4: Workflow Integration

Hook `get_or_create_contact()` into the workflow engine's email queuing:
- When workflow queues an email → call get_or_create_contact → set email_queue.contact_id
- After email sends → call log_activity(type="email_sent", direction="outbound")
- After sequence starts → call log_activity(type="sequence_started")

**Test:**
- Run a workflow → contacts auto-created
- Contacts page shows real data from workflow runs
- Timeline tab shows "email_sent" and "sequence_started" events

### Phase 5: Stats + Timeline + Deals

- `update_contact_stats()` — called after each activity log
- Timeline endpoint data (already returned in GET /contacts/{id})
- Deal data from CRM hydration (Pipedrive pull on contact create)

**Test:**
- Stats row in contact header shows real numbers
- Timeline tab shows activities in chronological order
- Deals tab shows Pipedrive deals (if CRM connected)

### Phase 6: Threads + Meetings

- Thread digest storage and retrieval
- Meeting history from transcript processing
- Hook into workflow engine: when transcript processed → store_meeting_history()

**Test:**
- Threads tab shows email conversation groups
- Expanding a thread shows messages
- Meetings tab shows transcript summaries with key points/objections/signals

### Phase 7: Intelligence Layer

- `generate_contact_pulse()` — Claude API call to summarize contact state
- POST /contacts/{id}/refresh-pulse
- Auto-regenerate on: inbound reply, meeting processed, deal stage change

**Test:**
- Pulse tab shows AI-generated summary
- Sentiment/engagement/intent badges populated
- Topics and objections extracted
- Manual refresh works

### Phase 8: Remaining Features

- POST /contacts/{id}/note
- POST /contacts/{id}/merge + POST /contact-organizations/{id}/merge
- GET /contacts/export + GET /contact-organizations/export (CSV)
- Conflict detection integration (check_contact_conflicts before send)

---

## File Structure

```
backend/
├── routers/
│   └── contacts.py          ← All API endpoints
├── services/
│   └── contacts.py          ← Business logic (get_or_create, log_activity, merge, stats, pulse)
├── schemas/
│   └── contacts.py          ← Pydantic request/response models
└── alembic/versions/
    └── 027_add_contact_system.py
```

Add to `models.py`: All model classes from `contact_models.py`.
Add to `main.py`: `from routers.contacts import router as contacts_router` + `app.include_router(contacts_router)`.
