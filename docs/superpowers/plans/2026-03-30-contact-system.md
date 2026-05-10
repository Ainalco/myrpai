# Contact System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the contact system backend — the memory layer that tracks every interaction per person/organization, enables context-aware email sending, and serves the existing frontend UI with zero frontend changes to the mock data shapes.

**Architecture:** Person + Organization model with multi-email support. Contacts are created on-demand via `get_or_create_contact()` when the workflow engine queues emails. Pre-computed stats in `contact_stats`, AI intelligence in `contact_pulse`. All queries scoped by `user_id`, soft-delete everywhere, PostgreSQL advisory locks to prevent race-condition duplicates.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL 15, Alembic, Pydantic v2

**Branch:** `josh` (create from `main`)

**Spec Reference:** `docs/contact-system-api-guide.md` (build spec), project knowledge handoff doc (architecture bible)

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/alembic/versions/027_add_contact_system.py` | CREATE | Migration: 8 new tables, columns on contacts/contact_activities/email_queue |
| `backend/models.py` | MODIFY (lines 327-376, append after line 620) | Add 8 model classes, update Contact + ContactActivity + EmailQueue |
| `backend/contacts_schemas.py` | CREATE | All Pydantic request/response schemas matching frontend contract |
| `backend/contacts_service.py` | CREATE | Business logic: get_or_create, log_activity, stats, merge, pulse |
| `backend/contacts.py` | REWRITE | Persons router — all /contacts endpoints |
| `backend/contact_orgs.py` | CREATE | Organizations router — all /contact-organizations endpoints |
| `backend/main.py` | MODIFY (lines 20-21, 97-98) | Register contact_orgs router, update contacts import |
| `frontend/src/lib/api.ts` | MODIFY (lines 584-735) | Update contact types + API calls to match new contract |
| `frontend/src/pages/ContactPersonsPage.tsx` | MODIFY | Swap MOCK_CONTACTS → useQuery |
| `frontend/src/pages/ContactOrganizationsPage.tsx` | MODIFY | Swap MOCK_ORGS → useQuery |

---

## Task 1: Branch Setup + Migration 027

**Files:**
- Create: `backend/alembic/versions/027_add_contact_system.py`

- [ ] **Step 1: Create and switch to josh branch**

```bash
cd /home/tauhid/code/aibot2
git checkout -b josh
```

- [ ] **Step 2: Write migration 027**

Create `backend/alembic/versions/027_add_contact_system.py`:

```python
"""Add contact system tables: organizations, emails, deals, stats, pulse, threads, meetings, sequences

Revision ID: 027_add_contact_system
Revises: 026_add_locked_acorn_allocation
"""
from alembic import op
import sqlalchemy as sa

revision = "027_add_contact_system"
down_revision = "026_add_locked_acorn_allocation"


def upgrade():
    # --- New table: contact_organizations ---
    op.create_table(
        "contact_organizations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("domain", sa.String),
        sa.Column("external_org_id", sa.String),
        sa.Column("crm_provider", sa.String),
        sa.Column("do_not_contact_propagation", sa.Boolean, server_default="true"),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_contact_orgs_user_id", "contact_organizations", ["user_id"])
    op.create_index("ix_contact_orgs_domain", "contact_organizations", ["domain"])

    # --- Add columns to contacts ---
    op.add_column("contacts", sa.Column("primary_email", sa.String))
    op.add_column("contacts", sa.Column("contact_organization_id", sa.Integer, sa.ForeignKey("contact_organizations.id")))
    op.add_column("contacts", sa.Column("external_person_id", sa.String))
    op.add_column("contacts", sa.Column("crm_provider", sa.String))
    op.add_column("contacts", sa.Column("status", sa.String, server_default="active"))
    op.add_column("contacts", sa.Column("last_activity_at", sa.DateTime(timezone=True)))
    op.add_column("contacts", sa.Column("last_activity_type", sa.String))
    op.add_column("contacts", sa.Column("last_activity_direction", sa.String))
    op.add_column("contacts", sa.Column("deleted_at", sa.DateTime(timezone=True)))
    op.create_index("ix_contacts_status", "contacts", ["status"])
    op.create_index("ix_contacts_org_id", "contacts", ["contact_organization_id"])

    # Backfill primary_email from existing email column
    op.execute("UPDATE contacts SET primary_email = email WHERE primary_email IS NULL")

    # --- New table: contact_emails ---
    op.create_table(
        "contact_emails",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("contact_id", sa.Integer, sa.ForeignKey("contacts.id"), nullable=False),
        sa.Column("email", sa.String, nullable=False),
        sa.Column("is_primary", sa.Boolean, server_default="false"),
        sa.Column("verified", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_contact_emails_email", "contact_emails", ["email"])
    op.create_index("ix_contact_emails_contact_id", "contact_emails", ["contact_id"])

    # Backfill contact_emails from existing contacts
    op.execute("""
        INSERT INTO contact_emails (contact_id, email, is_primary)
        SELECT id, email, true FROM contacts WHERE email IS NOT NULL
    """)

    # --- New table: contact_deals ---
    op.create_table(
        "contact_deals",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("contact_id", sa.Integer, sa.ForeignKey("contacts.id"), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("contact_organization_id", sa.Integer, sa.ForeignKey("contact_organizations.id")),
        sa.Column("external_deal_id", sa.String),
        sa.Column("crm_provider", sa.String),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("status", sa.String, server_default="open"),
        sa.Column("stage_name", sa.String),
        sa.Column("value", sa.Float),
        sa.Column("expected_close_date", sa.DateTime(timezone=True)),
        sa.Column("currency", sa.String, server_default="USD"),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_contact_deals_contact_id", "contact_deals", ["contact_id"])

    # --- New table: contact_stats ---
    op.create_table(
        "contact_stats",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("contact_id", sa.Integer, sa.ForeignKey("contacts.id"), nullable=False, unique=True),
        sa.Column("emails_sent", sa.Integer, server_default="0"),
        sa.Column("emails_received", sa.Integer, server_default="0"),
        sa.Column("reply_rate", sa.Float, server_default="0"),
        sa.Column("meetings_count", sa.Integer, server_default="0"),
        sa.Column("active_sequences", sa.Integer, server_default="0"),
        sa.Column("open_deals", sa.Integer, server_default="0"),
        sa.Column("total_deal_value", sa.Float, server_default="0"),
        sa.Column("last_computed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )

    # Backfill contact_stats rows for existing contacts
    op.execute("""
        INSERT INTO contact_stats (contact_id, emails_sent, emails_received)
        SELECT c.id,
               COALESCE((SELECT COUNT(*) FROM contact_activities ca WHERE ca.contact_id = c.id AND ca.activity_type = 'email_sent'), 0),
               COALESCE((SELECT COUNT(*) FROM contact_activities ca WHERE ca.contact_id = c.id AND ca.activity_type = 'reply_received'), 0)
        FROM contacts c
    """)

    # --- New table: contact_pulse ---
    op.create_table(
        "contact_pulse",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("contact_id", sa.Integer, sa.ForeignKey("contacts.id"), nullable=False, unique=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("summary", sa.Text),
        sa.Column("sentiment", sa.String),
        sa.Column("engagement_level", sa.String),
        sa.Column("intent", sa.String),
        sa.Column("recommended_action", sa.String),
        sa.Column("key_topics", sa.JSON),
        sa.Column("key_objections", sa.JSON),
        sa.Column("last_meeting_date", sa.DateTime(timezone=True)),
        sa.Column("generated_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )

    # --- New table: thread_digests ---
    op.create_table(
        "thread_digests",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("contact_id", sa.Integer, sa.ForeignKey("contacts.id"), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("thread_id", sa.String, nullable=False),
        sa.Column("subject", sa.String),
        sa.Column("summary", sa.Text),
        sa.Column("sentiment", sa.String),
        sa.Column("thread_status", sa.String),
        sa.Column("message_count", sa.Integer, server_default="0"),
        sa.Column("last_message_at", sa.DateTime(timezone=True)),
        sa.Column("participants", sa.JSON),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_thread_digests_contact_id", "thread_digests", ["contact_id"])
    op.create_index("ix_thread_digests_thread_id", "thread_digests", ["thread_id"])

    # --- New table: meeting_history ---
    op.create_table(
        "meeting_history",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("contact_id", sa.Integer, sa.ForeignKey("contacts.id"), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("external_meeting_id", sa.String),
        sa.Column("source", sa.String),
        sa.Column("meeting_date", sa.DateTime(timezone=True)),
        sa.Column("summary", sa.Text),
        sa.Column("key_points", sa.JSON),
        sa.Column("objections", sa.JSON),
        sa.Column("buying_signals", sa.JSON),
        sa.Column("deal_stage_at_time", sa.String),
        sa.Column("duration_minutes", sa.Integer),
        sa.Column("participants", sa.JSON),
        sa.Column("raw_transcript_url", sa.String),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_meeting_history_contact_id", "meeting_history", ["contact_id"])

    # --- New table: sequence_runs ---
    op.create_table(
        "sequence_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("contact_id", sa.Integer, sa.ForeignKey("contacts.id"), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("sequence_config_id", sa.Integer, sa.ForeignKey("email_sequence_configs.id")),
        sa.Column("status", sa.String, server_default="active"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("current_step", sa.Integer, server_default="0"),
        sa.Column("total_steps", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_sequence_runs_contact_id", "sequence_runs", ["contact_id"])

    # --- Add columns to contact_activities ---
    op.add_column("contact_activities", sa.Column("contact_organization_id", sa.Integer, sa.ForeignKey("contact_organizations.id")))
    op.add_column("contact_activities", sa.Column("deal_id", sa.Integer, sa.ForeignKey("contact_deals.id")))
    op.add_column("contact_activities", sa.Column("direction", sa.String))
    op.add_column("contact_activities", sa.Column("source_type", sa.String))
    op.add_column("contact_activities", sa.Column("source_id", sa.String))
    op.add_column("contact_activities", sa.Column("thread_id", sa.String))
    op.add_column("contact_activities", sa.Column("subject", sa.String))
    op.add_column("contact_activities", sa.Column("summary", sa.Text))
    op.add_column("contact_activities", sa.Column("raw_content", sa.Text))
    op.add_column("contact_activities", sa.Column("metadata_json", sa.JSON))
    op.add_column("contact_activities", sa.Column("activity_at", sa.DateTime(timezone=True)))

    # Unique constraint for activity idempotency (NULL source_id rows won't conflict)
    op.create_index(
        "uq_activity_source",
        "contact_activities",
        ["user_id", "source_type", "source_id"],
        unique=True,
        postgresql_where=sa.text("source_id IS NOT NULL"),
    )

    # Backfill activity_at from occurred_at for existing activities
    op.execute("UPDATE contact_activities SET activity_at = occurred_at WHERE activity_at IS NULL")

    # --- Add columns to email_queue ---
    op.add_column("email_queue", sa.Column("thread_id", sa.String))
    op.add_column("email_queue", sa.Column("deal_id", sa.Integer, sa.ForeignKey("contact_deals.id")))
    op.add_column("email_queue", sa.Column("sequence_run_id", sa.Integer, sa.ForeignKey("sequence_runs.id")))


def downgrade():
    # email_queue columns
    op.drop_column("email_queue", "sequence_run_id")
    op.drop_column("email_queue", "deal_id")
    op.drop_column("email_queue", "thread_id")

    # contact_activities columns
    op.drop_index("uq_activity_source", "contact_activities")
    op.drop_column("contact_activities", "activity_at")
    op.drop_column("contact_activities", "metadata_json")
    op.drop_column("contact_activities", "raw_content")
    op.drop_column("contact_activities", "summary")
    op.drop_column("contact_activities", "subject")
    op.drop_column("contact_activities", "thread_id")
    op.drop_column("contact_activities", "source_id")
    op.drop_column("contact_activities", "source_type")
    op.drop_column("contact_activities", "direction")
    op.drop_column("contact_activities", "deal_id")
    op.drop_column("contact_activities", "contact_organization_id")

    # New tables (reverse order of creation)
    op.drop_table("sequence_runs")
    op.drop_table("meeting_history")
    op.drop_table("thread_digests")
    op.drop_table("contact_pulse")
    op.drop_table("contact_stats")
    op.drop_table("contact_emails")
    op.drop_table("contact_deals")

    # contacts columns
    op.drop_index("ix_contacts_org_id", "contacts")
    op.drop_index("ix_contacts_status", "contacts")
    op.drop_column("contacts", "deleted_at")
    op.drop_column("contacts", "last_activity_direction")
    op.drop_column("contacts", "last_activity_type")
    op.drop_column("contacts", "last_activity_at")
    op.drop_column("contacts", "status")
    op.drop_column("contacts", "crm_provider")
    op.drop_column("contacts", "external_person_id")
    op.drop_column("contacts", "contact_organization_id")
    op.drop_column("contacts", "primary_email")

    # contact_organizations
    op.drop_table("contact_organizations")
```

- [ ] **Step 3: Run migration**

```bash
cd /home/tauhid/code/aibot2/backend
python migrate.py
```

Expected: Migration applies cleanly. All tables created.

- [ ] **Step 4: Verify tables exist**

```bash
cd /home/tauhid/code/aibot2
docker compose exec postgres psql -U workflow_user -d workflow_platform \
  -c "\dt contact_*" \
  -c "\dt thread_digests" \
  -c "\dt meeting_history" \
  -c "\dt sequence_runs"
```

Expected: All 8 new tables listed: `contact_organizations`, `contact_emails`, `contact_deals`, `contact_stats`, `contact_pulse`, `thread_digests`, `meeting_history`, `sequence_runs`.

- [ ] **Step 5: Verify backfills**

```bash
docker compose exec postgres psql -U workflow_user -d workflow_platform \
  -c "SELECT COUNT(*) FROM contact_emails;" \
  -c "SELECT COUNT(*) FROM contact_stats;" \
  -c "SELECT COUNT(*) as contacts_with_primary FROM contacts WHERE primary_email IS NOT NULL;"
```

Expected: `contact_emails` count matches `contacts` count. All contacts have `primary_email` set.

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/027_add_contact_system.py
git commit -m "feat: add migration 027 — contact system tables and columns"
```

---

## Task 2: SQLAlchemy Models

**Files:**
- Modify: `backend/models.py` (update Contact at line 327, ContactActivity at line 353, EmailQueue at line 395, append new classes after line 620)

- [ ] **Step 1: Update Contact model with new columns and relationships**

In `backend/models.py`, replace the Contact class (lines 327-351) with:

```python
class Contact(Base):
    """
    Tracks contacts (email recipients) for activity history and conflict detection.
    Person model in the Person + Organization contact system.
    """
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    email = Column(String, nullable=False, index=True)
    name = Column(String)
    title = Column(String)
    company = Column(String)
    avatar_initials = Column(String(2))

    # V2 contact system fields
    primary_email = Column(String)
    contact_organization_id = Column(Integer, ForeignKey("contact_organizations.id"))
    external_person_id = Column(String)
    crm_provider = Column(String)
    status = Column(String, default="active")  # active, paused, do_not_contact, bounced

    # Activity tracking (denormalized for fast list queries)
    last_contacted_at = Column(DateTime(timezone=True))
    contact_count = Column(Integer, default=0)
    last_activity_at = Column(DateTime(timezone=True))
    last_activity_type = Column(String)
    last_activity_direction = Column(String)

    # Soft delete
    deleted_at = Column(DateTime(timezone=True))

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="contacts")
    organization = relationship("ContactOrganization", back_populates="contacts")
    activities = relationship("ContactActivity", back_populates="contact", cascade="all, delete-orphan", order_by="desc(ContactActivity.occurred_at)")
    email_queue_items = relationship("EmailQueue", back_populates="contact")
    contact_emails = relationship("ContactEmail", back_populates="contact", cascade="all, delete-orphan")
    deals = relationship("ContactDeal", back_populates="contact", cascade="all, delete-orphan")
    stats = relationship("ContactStats", back_populates="contact", uselist=False, cascade="all, delete-orphan")
    pulse = relationship("ContactPulse", back_populates="contact", uselist=False, cascade="all, delete-orphan")
    thread_digests = relationship("ThreadDigest", back_populates="contact", cascade="all, delete-orphan")
    meetings = relationship("MeetingHistory", back_populates="contact", cascade="all, delete-orphan")
    sequence_runs = relationship("SequenceRun", back_populates="contact", cascade="all, delete-orphan")
```

- [ ] **Step 2: Update ContactActivity model with new columns**

Replace ContactActivity class (lines 353-376) with:

```python
class ContactActivity(Base):
    """
    Tracks activity history for a contact (emails sent, opened, replies, meetings, etc.)
    Append-only — never edit or delete activities.
    """
    __tablename__ = "contact_activities"

    id = Column(Integer, primary_key=True, index=True)
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    email_queue_id = Column(Integer, ForeignKey("email_queue.id"), nullable=True)

    activity_type = Column(String, nullable=False)  # email_sent, email_reply, sequence_started, meeting, deal_stage_change, note, contact_merged
    title = Column(String)
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    is_new = Column(Boolean, default=True)
    extra_data = Column(JSON)

    # V2 fields
    contact_organization_id = Column(Integer, ForeignKey("contact_organizations.id"))
    deal_id = Column(Integer, ForeignKey("contact_deals.id"))
    direction = Column(String)  # inbound, outbound, internal
    source_type = Column(String)  # gmail_push, scurry_sequence, crm_sync, scurry_transcript
    source_id = Column(String)  # External ID for idempotency
    thread_id = Column(String)
    subject = Column(String)
    summary = Column(Text)
    raw_content = Column(Text)
    metadata_json = Column(JSON)
    activity_at = Column(DateTime(timezone=True))

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    contact = relationship("Contact", back_populates="activities")
    user = relationship("User")
    email_queue = relationship("EmailQueue", back_populates="activities")
    deal = relationship("ContactDeal")
```

- [ ] **Step 3: Add new columns to EmailQueue model**

In the EmailQueue class (around line 450, before the relationships section), add these three columns:

```python
    # Contact system V2 linking
    thread_id = Column(String)
    deal_id = Column(Integer, ForeignKey("contact_deals.id"))
    sequence_run_id = Column(Integer, ForeignKey("sequence_runs.id"))
```

And add relationships to the EmailQueue relationships block:

```python
    contact_deal = relationship("ContactDeal")
    sequence_run = relationship("SequenceRun")
```

- [ ] **Step 4: Add all 8 new model classes at end of models.py**

Append after the last class in models.py (after `AiModel`):

```python
# --- Contact System V2 Models ---

class ContactOrganization(Base):
    """
    Organization in the contact system. Separate from billing Organizations table.
    Groups contacts by company domain.
    """
    __tablename__ = "contact_organizations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    domain = Column(String)
    external_org_id = Column(String)
    crm_provider = Column(String)
    do_not_contact_propagation = Column(Boolean, default=True)
    deleted_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User")
    contacts = relationship("Contact", back_populates="organization")
    deals = relationship("ContactDeal", back_populates="organization")


class ContactEmail(Base):
    """Multiple email addresses per contact."""
    __tablename__ = "contact_emails"

    id = Column(Integer, primary_key=True, index=True)
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=False)
    email = Column(String, nullable=False)
    is_primary = Column(Boolean, default=False)
    verified = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    contact = relationship("Contact", back_populates="contact_emails")


class ContactDeal(Base):
    """Deals linked to a contact, synced from CRM."""
    __tablename__ = "contact_deals"

    id = Column(Integer, primary_key=True, index=True)
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    contact_organization_id = Column(Integer, ForeignKey("contact_organizations.id"))
    external_deal_id = Column(String)
    crm_provider = Column(String)
    title = Column(String, nullable=False)
    status = Column(String, default="open")  # open, won, lost
    stage_name = Column(String)
    value = Column(Float)
    expected_close_date = Column(DateTime(timezone=True))
    currency = Column(String, default="USD")
    deleted_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    contact = relationship("Contact", back_populates="deals")
    organization = relationship("ContactOrganization", back_populates="deals")
    user = relationship("User")


class ContactStats(Base):
    """Pre-computed statistics per contact. One row per contact."""
    __tablename__ = "contact_stats"

    id = Column(Integer, primary_key=True, index=True)
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=False, unique=True)
    emails_sent = Column(Integer, default=0)
    emails_received = Column(Integer, default=0)
    reply_rate = Column(Float, default=0.0)
    meetings_count = Column(Integer, default=0)
    active_sequences = Column(Integer, default=0)
    open_deals = Column(Integer, default=0)
    total_deal_value = Column(Float, default=0.0)
    last_computed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    contact = relationship("Contact", back_populates="stats")


class ContactPulse(Base):
    """AI-generated intelligence summary per contact. One row per contact."""
    __tablename__ = "contact_pulse"

    id = Column(Integer, primary_key=True, index=True)
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=False, unique=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    summary = Column(Text)
    sentiment = Column(String)  # positive, neutral, negative, unknown
    engagement_level = Column(String)  # high, medium, low
    intent = Column(String)  # interested, evaluating, not_interested
    recommended_action = Column(String)  # continue_sequence, pause, close_out
    key_topics = Column(JSON)  # ["pricing", "integration"]
    key_objections = Column(JSON)  # ["Salesforce integration"]
    last_meeting_date = Column(DateTime(timezone=True))
    generated_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    contact = relationship("Contact", back_populates="pulse")
    user = relationship("User")


class ThreadDigest(Base):
    """Email thread summary linked to a contact."""
    __tablename__ = "thread_digests"

    id = Column(Integer, primary_key=True, index=True)
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    thread_id = Column(String, nullable=False)
    subject = Column(String)
    summary = Column(Text)
    sentiment = Column(String)
    thread_status = Column(String)  # active, waiting_on_us, waiting_on_them, closed
    message_count = Column(Integer, default=0)
    last_message_at = Column(DateTime(timezone=True))
    participants = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    contact = relationship("Contact", back_populates="thread_digests")
    user = relationship("User")


class MeetingHistory(Base):
    """Meeting transcript summaries from Fireflies or other sources."""
    __tablename__ = "meeting_history"

    id = Column(Integer, primary_key=True, index=True)
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    external_meeting_id = Column(String)
    source = Column(String)  # Fireflies, manual
    meeting_date = Column(DateTime(timezone=True))
    summary = Column(Text)
    key_points = Column(JSON)
    objections = Column(JSON)
    buying_signals = Column(JSON)
    deal_stage_at_time = Column(String)
    duration_minutes = Column(Integer)
    participants = Column(JSON)
    raw_transcript_url = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    contact = relationship("Contact", back_populates="meetings")
    user = relationship("User")


class SequenceRun(Base):
    """Tracks a sequence execution against a specific contact."""
    __tablename__ = "sequence_runs"

    id = Column(Integer, primary_key=True, index=True)
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    sequence_config_id = Column(Integer, ForeignKey("email_sequence_configs.id"))
    status = Column(String, default="active")  # active, completed, paused, cancelled
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    current_step = Column(Integer, default=0)
    total_steps = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    contact = relationship("Contact", back_populates="sequence_runs")
    user = relationship("User")
    sequence_config = relationship("EmailSequenceConfig")
```

- [ ] **Step 5: Verify models load**

```bash
cd /home/tauhid/code/aibot2/backend
python -c "import models; print('All models loaded successfully')"
```

Expected: No import errors.

- [ ] **Step 6: Commit**

```bash
git add backend/models.py
git commit -m "feat: add contact system V2 models — 8 new classes + updated Contact/ContactActivity/EmailQueue"
```

---

## Task 3: Pydantic Schemas + Utility Functions

**Files:**
- Create: `backend/contacts_schemas.py`

- [ ] **Step 1: Create contacts_schemas.py with all response/request models**

```python
"""
Pydantic schemas for the contact system API.
Field names match the frontend contract exactly (camelCase where needed).
"""
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime


# --- Utility functions for formatting ---

def format_relative_time(dt: Optional[datetime]) -> Optional[str]:
    """Convert datetime to relative time string: '2h ago', '1d ago', '3d ago', '1w ago'"""
    if dt is None:
        return None
    now = datetime.utcnow()
    diff = now - dt
    seconds = diff.total_seconds()

    if seconds < 3600:
        return f"{max(1, int(seconds / 60))}m ago"
    elif seconds < 86400:
        return f"{int(seconds / 3600)}h ago"
    elif diff.days < 7:
        return f"{diff.days}d ago"
    elif diff.days < 30:
        return f"{diff.days // 7}w ago"
    elif diff.days < 365:
        return f"{diff.days // 30}mo ago"
    else:
        return f"{diff.days // 365}y ago"


def format_rate(reply_rate: Optional[float]) -> str:
    """Format reply rate as string with percent sign: '34.8%'"""
    if reply_rate is None or reply_rate == 0:
        return "0.0%"
    return f"{reply_rate:.1f}%"


def format_date_long(dt: Optional[datetime]) -> Optional[str]:
    """Format as 'Apr 15, 2026'"""
    if dt is None:
        return None
    return dt.strftime("%b %-d, %Y")


def format_datetime_short(dt: Optional[datetime]) -> Optional[str]:
    """Format as 'Mar 13, 10:24 AM'"""
    if dt is None:
        return None
    return dt.strftime("%b %-d, %-I:%M %p")


def format_date_short(dt: Optional[datetime]) -> Optional[str]:
    """Format as 'Mar 13'"""
    if dt is None:
        return None
    return dt.strftime("%b %-d")


# --- Stats ---

class ContactStatsResponse(BaseModel):
    sent: int = 0
    received: int = 0
    rate: str = "0.0%"
    meetings: int = 0
    sequences: int = 0
    openDeals: int = 0
    dealValue: float = 0


# --- Pulse ---

class ContactPulseResponse(BaseModel):
    summary: Optional[str] = None
    sentiment: Optional[str] = None
    engagement: Optional[str] = None
    intent: Optional[str] = None
    action: Optional[str] = None
    topics: List[str] = []
    objections: List[str] = []
    lastMeeting: Optional[str] = None


# --- Deals ---

class ContactDealResponse(BaseModel):
    id: int
    title: str
    status: str
    stage: Optional[str] = None
    value: Optional[float] = None
    expected: Optional[str] = None


# --- Timeline ---

class TimelineEventResponse(BaseModel):
    id: int
    type: str
    dir: Optional[str] = None
    source: Optional[str] = None
    subject: Optional[str] = None
    summary: Optional[str] = None
    at: Optional[str] = None
    deal: Optional[str] = None


# --- Threads ---

class ThreadMessageResponse(BaseModel):
    id: str
    sender: str = Field(serialization_alias="from")  # "you" or email address
    to: str
    subject: Optional[str] = None
    body: Optional[str] = None
    at: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)


class ThreadResponse(BaseModel):
    id: str
    summary: Optional[str] = None
    sentiment: Optional[str] = None
    status: Optional[str] = None
    msgs: int = 0
    lastAt: Optional[str] = None
    messages: List[ThreadMessageResponse] = []


# --- Meetings ---

class MeetingResponse(BaseModel):
    id: int
    date: Optional[str] = None
    source: Optional[str] = None
    summary: Optional[str] = None
    keyPoints: List[str] = []
    objections: List[str] = []
    signals: List[str] = []
    stage: Optional[str] = None


# --- Contact List Item (GET /contacts) ---

class ContactListItem(BaseModel):
    id: int
    name: Optional[str] = None
    email: str
    orgId: Optional[int] = None
    orgName: Optional[str] = None
    status: str = "active"
    pipedrive: bool = False
    lastActivity: Optional[str] = None
    stats: ContactStatsResponse = ContactStatsResponse()
    emails: List[str] = []


class StatusCounts(BaseModel):
    active: int = 0
    paused: int = 0
    dnc: int = 0
    bounced: int = 0


class ContactListResponse(BaseModel):
    items: List[ContactListItem]
    counts: StatusCounts
    nextCursor: Optional[int] = None
    hasMore: bool = False


# --- Contact Detail (GET /contacts/{id}) ---

class ContactDetailResponse(BaseModel):
    id: int
    name: Optional[str] = None
    email: str
    orgId: Optional[int] = None
    orgName: Optional[str] = None
    status: str = "active"
    pipedrive: bool = False
    lastActivity: Optional[str] = None
    emails: List[str] = []
    stats: ContactStatsResponse = ContactStatsResponse()
    pulse: ContactPulseResponse = ContactPulseResponse()  # Never null — frontend accesses p.sentiment without null check
    deals: List[ContactDealResponse] = []
    timeline: List[TimelineEventResponse] = []
    threads: List[ThreadResponse] = []
    meetings: List[MeetingResponse] = []


# --- Organization List ---

class OrgListItem(BaseModel):
    id: int
    name: str
    domain: Optional[str] = None
    contacts: int = 0
    openDeals: int = 0
    totalValue: float = 0
    dnc: bool = False
    dncProp: bool = True


class OrgListResponse(BaseModel):
    items: List[OrgListItem]


class OrgPersonItem(BaseModel):
    id: int
    name: Optional[str] = None
    email: str
    status: str = "active"


class OrgDetailResponse(BaseModel):
    id: int
    name: str
    domain: Optional[str] = None
    contacts: int = 0
    openDeals: int = 0
    totalValue: float = 0
    dnc: bool = False
    dncProp: bool = True
    persons: List[OrgPersonItem] = []


# --- Request Schemas ---

class ContactCreateRequest(BaseModel):
    email: str
    name: Optional[str] = None
    organization_name: Optional[str] = None


class ContactUpdateRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    title: Optional[str] = None
    company: Optional[str] = None
    contact_organization_id: Optional[int] = None


class ContactStatusRequest(BaseModel):
    status: str  # active, paused, do_not_contact, bounced


class OrgUpdateRequest(BaseModel):
    name: Optional[str] = None
    do_not_contact_propagation: Optional[bool] = None


class ContactNoteRequest(BaseModel):
    content: str


class ContactMergeRequest(BaseModel):
    merge_id: int  # ID of contact to merge into this one
```

- [ ] **Step 2: Verify schema imports**

```bash
cd /home/tauhid/code/aibot2/backend
python -c "from contacts_schemas import *; print('All schemas loaded successfully')"
```

- [ ] **Step 3: Commit**

```bash
git add backend/contacts_schemas.py
git commit -m "feat: add contact system Pydantic schemas matching frontend contract"
```

---

## Task 4: Core Service — get_or_create_contact

**Files:**
- Create: `backend/contacts_service.py`

- [ ] **Step 1: Create contacts_service.py with get_or_create_contact and helpers**

```python
"""
Contact system business logic.
Core functions: get_or_create_contact, log_activity, update_contact_stats, merge_contacts.
"""
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from datetime import datetime
import logging

import models

logger = logging.getLogger(__name__)

# Freemail domains — skip org creation for these
FREEMAIL_DOMAINS = frozenset({
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com",
    "icloud.com", "mail.com", "protonmail.com", "zoho.com", "yandex.com",
    "live.com", "msn.com", "me.com", "fastmail.com", "tutanota.com", "hey.com",
})


def generate_initials(name: Optional[str], email: str) -> str:
    """Generate avatar initials from name or email."""
    if name:
        parts = name.split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        elif len(parts) == 1 and len(parts[0]) >= 2:
            return parts[0][:2].upper()
    return email[:2].upper()


def _extract_domain(email: str) -> str:
    """Extract domain from email address."""
    return email.rsplit("@", 1)[-1].lower()


def _get_or_create_org(
    db: Session,
    user_id: int,
    domain: str,
    org_name: Optional[str] = None,
) -> Optional[models.ContactOrganization]:
    """Get or create a contact organization by domain. Returns None for freemail domains."""
    if domain in FREEMAIL_DOMAINS:
        return None

    org = db.query(models.ContactOrganization).filter(
        models.ContactOrganization.user_id == user_id,
        models.ContactOrganization.domain == domain,
        models.ContactOrganization.deleted_at.is_(None),
    ).first()

    if org:
        return org

    # Use advisory lock to prevent race condition
    lock_key = hash(f"org:{user_id}:{domain}") & 0x7FFFFFFF
    try:
        db.execute(text(f"SELECT pg_advisory_xact_lock({lock_key})"))
    except Exception:
        # Graceful degradation if not PostgreSQL (e.g., tests with SQLite)
        pass

    # Double-check after acquiring lock
    org = db.query(models.ContactOrganization).filter(
        models.ContactOrganization.user_id == user_id,
        models.ContactOrganization.domain == domain,
        models.ContactOrganization.deleted_at.is_(None),
    ).first()
    if org:
        return org

    display_name = org_name or domain.split(".")[0].title()
    org = models.ContactOrganization(
        user_id=user_id,
        name=display_name,
        domain=domain,
    )
    db.add(org)
    db.flush()
    logger.info("Created contact org", extra={"user_id": user_id, "org_id": org.id, "domain": domain})
    return org


def get_or_create_contact(
    db: Session,
    user_id: int,
    email: str,
    name: Optional[str] = None,
    organization_name: Optional[str] = None,
) -> models.Contact:
    """
    Get an existing contact or create a new one.
    Lookup is via contact_emails table (multi-email support).
    Uses PostgreSQL advisory locks to prevent race-condition duplicates.
    """
    email = email.strip().lower()

    # 1. Check contact_emails for existing match
    contact_email = db.query(models.ContactEmail).join(models.Contact).filter(
        models.Contact.user_id == user_id,
        models.ContactEmail.email == email,
        models.Contact.deleted_at.is_(None),
    ).first()

    if contact_email:
        return contact_email.contact

    # 2. Acquire advisory lock to prevent duplicates
    lock_key = hash(f"contact:{user_id}:{email}") & 0x7FFFFFFF
    try:
        db.execute(text(f"SELECT pg_advisory_xact_lock({lock_key})"))
    except Exception:
        pass  # Graceful degradation for non-PG databases

    # 3. Double-check after lock
    contact_email = db.query(models.ContactEmail).join(models.Contact).filter(
        models.Contact.user_id == user_id,
        models.ContactEmail.email == email,
        models.Contact.deleted_at.is_(None),
    ).first()
    if contact_email:
        return contact_email.contact

    # 4. Extract domain and get/create org
    domain = _extract_domain(email)
    org = _get_or_create_org(db, user_id, domain, organization_name)

    # 5. Create Contact
    contact = models.Contact(
        user_id=user_id,
        email=email,
        primary_email=email,
        name=name,
        company=organization_name or (org.name if org else None),
        avatar_initials=generate_initials(name, email),
        contact_organization_id=org.id if org else None,
        status="active",
        contact_count=0,
    )
    db.add(contact)
    db.flush()

    # 6. Create ContactEmail (primary)
    db.add(models.ContactEmail(
        contact_id=contact.id,
        email=email,
        is_primary=True,
    ))

    # 7. Create ContactStats (all zeros)
    db.add(models.ContactStats(contact_id=contact.id))

    db.flush()
    logger.info("Created contact", extra={"user_id": user_id, "contact_id": contact.id, "email": email})
    return contact


def log_activity(
    db: Session,
    user_id: int,
    contact_id: int,
    activity_type: str,
    direction: Optional[str] = None,
    source_type: Optional[str] = None,
    source_id: Optional[str] = None,
    email_queue_id: Optional[int] = None,
    deal_id: Optional[int] = None,
    thread_id: Optional[str] = None,
    subject: Optional[str] = None,
    summary: Optional[str] = None,
    title: Optional[str] = None,
) -> models.ContactActivity:
    """
    Log an activity on a contact's timeline.
    Idempotent when source_id is provided (skips duplicate).
    Updates contact denormalized fields and stats.
    """
    # Idempotency check
    if source_id and source_type:
        existing = db.query(models.ContactActivity).filter(
            models.ContactActivity.user_id == user_id,
            models.ContactActivity.source_type == source_type,
            models.ContactActivity.source_id == source_id,
        ).first()
        if existing:
            return existing

    now = datetime.utcnow()
    activity = models.ContactActivity(
        contact_id=contact_id,
        user_id=user_id,
        email_queue_id=email_queue_id,
        activity_type=activity_type,
        title=title or f"{activity_type.replace('_', ' ').title()}",
        occurred_at=now,
        activity_at=now,
        is_new=True,
        direction=direction,
        source_type=source_type,
        source_id=source_id,
        deal_id=deal_id,
        thread_id=thread_id,
        subject=subject,
        summary=summary,
    )
    db.add(activity)

    # Update denormalized fields on contact
    contact = db.query(models.Contact).filter(models.Contact.id == contact_id).first()
    if contact:
        contact.last_activity_at = now
        contact.last_activity_type = activity_type
        contact.last_activity_direction = direction
        if activity_type == "email_sent":
            contact.last_contacted_at = now
            contact.contact_count = (contact.contact_count or 0) + 1

    # Increment stats
    stats = db.query(models.ContactStats).filter(
        models.ContactStats.contact_id == contact_id
    ).first()
    if stats:
        if activity_type == "email_sent":
            stats.emails_sent = (stats.emails_sent or 0) + 1
        elif direction == "inbound":
            stats.emails_received = (stats.emails_received or 0) + 1
        # Recompute reply rate
        if stats.emails_sent and stats.emails_sent > 0:
            stats.reply_rate = (stats.emails_received or 0) / stats.emails_sent * 100
        stats.last_computed_at = now

    db.flush()
    logger.info("Logged activity", extra={
        "user_id": user_id, "contact_id": contact_id,
        "activity_type": activity_type, "direction": direction,
    })
    return activity


def update_contact_stats(db: Session, contact_id: int) -> None:
    """
    Recompute all stats from scratch (safe full recalc).
    Call this after bulk operations or when incremental updates may have drifted.
    """
    stats = db.query(models.ContactStats).filter(
        models.ContactStats.contact_id == contact_id
    ).first()
    if not stats:
        stats = models.ContactStats(contact_id=contact_id)
        db.add(stats)

    # Count activities by type
    stats.emails_sent = db.query(func.count(models.ContactActivity.id)).filter(
        models.ContactActivity.contact_id == contact_id,
        models.ContactActivity.activity_type == "email_sent",
    ).scalar() or 0

    stats.emails_received = db.query(func.count(models.ContactActivity.id)).filter(
        models.ContactActivity.contact_id == contact_id,
        models.ContactActivity.direction == "inbound",
    ).scalar() or 0

    stats.reply_rate = (
        (stats.emails_received / stats.emails_sent * 100)
        if stats.emails_sent > 0 else 0.0
    )

    stats.meetings_count = db.query(func.count(models.MeetingHistory.id)).filter(
        models.MeetingHistory.contact_id == contact_id,
    ).scalar() or 0

    stats.active_sequences = db.query(func.count(models.SequenceRun.id)).filter(
        models.SequenceRun.contact_id == contact_id,
        models.SequenceRun.status == "active",
    ).scalar() or 0

    stats.open_deals = db.query(func.count(models.ContactDeal.id)).filter(
        models.ContactDeal.contact_id == contact_id,
        models.ContactDeal.status == "open",
        models.ContactDeal.deleted_at.is_(None),
    ).scalar() or 0

    stats.total_deal_value = db.query(func.coalesce(func.sum(models.ContactDeal.value), 0)).filter(
        models.ContactDeal.contact_id == contact_id,
        models.ContactDeal.status == "open",
        models.ContactDeal.deleted_at.is_(None),
    ).scalar() or 0

    stats.last_computed_at = datetime.utcnow()
    db.flush()


def merge_contacts(
    db: Session,
    user_id: int,
    keep_id: int,
    merge_id: int,
) -> models.Contact:
    """
    Merge merge_id into keep_id. Moves all child records, soft-deletes the merged contact.
    """
    keep = db.query(models.Contact).filter(
        models.Contact.id == keep_id,
        models.Contact.user_id == user_id,
        models.Contact.deleted_at.is_(None),
    ).first()
    merge = db.query(models.Contact).filter(
        models.Contact.id == merge_id,
        models.Contact.user_id == user_id,
        models.Contact.deleted_at.is_(None),
    ).first()

    if not keep or not merge:
        raise ValueError("Both contacts must exist and belong to user")

    # Move all child records from merge → keep
    db.query(models.ContactEmail).filter(
        models.ContactEmail.contact_id == merge_id
    ).update({"contact_id": keep_id})

    db.query(models.ContactActivity).filter(
        models.ContactActivity.contact_id == merge_id
    ).update({"contact_id": keep_id})

    db.query(models.ContactDeal).filter(
        models.ContactDeal.contact_id == merge_id
    ).update({"contact_id": keep_id})

    db.query(models.ThreadDigest).filter(
        models.ThreadDigest.contact_id == merge_id
    ).update({"contact_id": keep_id})

    db.query(models.MeetingHistory).filter(
        models.MeetingHistory.contact_id == merge_id
    ).update({"contact_id": keep_id})

    db.query(models.SequenceRun).filter(
        models.SequenceRun.contact_id == merge_id
    ).update({"contact_id": keep_id})

    db.query(models.EmailQueue).filter(
        models.EmailQueue.contact_id == merge_id
    ).update({"contact_id": keep_id})

    # Log the merge as an activity
    now = datetime.utcnow()
    db.add(models.ContactActivity(
        contact_id=keep_id,
        user_id=user_id,
        activity_type="contact_merged",
        title=f"Merged with {merge.name or merge.email}",
        occurred_at=now,
        activity_at=now,
        is_new=False,
    ))

    # Soft-delete the merged contact
    merge.deleted_at = now

    # Delete orphaned stats/pulse from merged contact
    db.query(models.ContactStats).filter(
        models.ContactStats.contact_id == merge_id
    ).delete()
    db.query(models.ContactPulse).filter(
        models.ContactPulse.contact_id == merge_id
    ).delete()

    # Recompute stats on kept contact
    db.flush()
    update_contact_stats(db, keep_id)

    logger.info("Merged contacts", extra={
        "user_id": user_id, "keep_id": keep_id, "merge_id": merge_id,
    })
    return keep


# --- Legacy compatibility wrappers ---
# These match the old contacts.py function signatures so existing callers don't break.

def record_email_sent(
    db: Session,
    contact: models.Contact,
    email_queue_id: int,
    subject: str,
) -> None:
    """Record that an email was sent to a contact. Legacy wrapper around log_activity."""
    log_activity(
        db=db,
        user_id=contact.user_id,
        contact_id=contact.id,
        activity_type="email_sent",
        direction="outbound",
        source_type="scurry_sequence",
        email_queue_id=email_queue_id,
        subject=subject,
        title=f"Email sent: {subject[:50]}{'...' if len(subject) > 50 else ''}",
    )
```

- [ ] **Step 2: Verify service imports**

```bash
cd /home/tauhid/code/aibot2/backend
python -c "from contacts_service import get_or_create_contact, log_activity, record_email_sent; print('Service loaded')"
```

- [ ] **Step 3: Commit**

```bash
git add backend/contacts_service.py
git commit -m "feat: add contact service layer — get_or_create, log_activity, stats, merge"
```

---

## Task 5: Persons Router — List Endpoint (P0)

**Files:**
- Rewrite: `backend/contacts.py`

- [ ] **Step 1: Rewrite contacts.py with the list endpoint**

Replace the entire contents of `backend/contacts.py` with:

```python
"""
Contact persons router — all /contacts endpoints.
Serves the frontend ContactPersonsPage with exact JSON shapes.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy import func
from datetime import datetime
import logging

from database import get_db
from auth import get_current_active_user
import models
from contacts_schemas import (
    ContactListItem, ContactListResponse, StatusCounts, ContactStatsResponse,
    ContactDetailResponse, ContactPulseResponse, ContactDealResponse,
    TimelineEventResponse, ThreadResponse, ThreadMessageResponse,
    MeetingResponse, ContactCreateRequest, ContactUpdateRequest,
    ContactStatusRequest, ContactNoteRequest, ContactMergeRequest,
    format_relative_time, format_rate, format_date_long, format_datetime_short,
    format_date_short,
)
from contacts_service import (
    get_or_create_contact, log_activity, update_contact_stats,
    merge_contacts, record_email_sent, generate_initials,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _build_stats_response(stats: Optional[models.ContactStats]) -> ContactStatsResponse:
    """Build stats response dict from ContactStats model."""
    if not stats:
        return ContactStatsResponse()
    return ContactStatsResponse(
        sent=stats.emails_sent or 0,
        received=stats.emails_received or 0,
        rate=format_rate(stats.reply_rate),
        meetings=stats.meetings_count or 0,
        sequences=stats.active_sequences or 0,
        openDeals=stats.open_deals or 0,
        dealValue=stats.total_deal_value or 0,
    )


def _build_list_item(contact: models.Contact) -> ContactListItem:
    """Build a ContactListItem from a Contact model with eager-loaded relations."""
    org = contact.organization
    email_list = [ce.email for ce in (contact.contact_emails or [])]
    if not email_list:
        email_list = [contact.email]

    return ContactListItem(
        id=contact.id,
        name=contact.name,
        email=contact.email,
        orgId=contact.contact_organization_id,
        orgName=org.name if org else contact.company,
        status=contact.status or "active",
        pipedrive=bool(contact.external_person_id and contact.crm_provider == "pipedrive"),
        lastActivity=format_relative_time(contact.last_activity_at),
        stats=_build_stats_response(contact.stats),
        emails=email_list,
    )


@router.get("/", response_model=ContactListResponse)
async def list_contacts(
    search: Optional[str] = Query(None, description="Search by name, email, or company"),
    status: Optional[str] = Query(None, description="Filter by status: active, paused, do_not_contact, bounced"),
    cursor: Optional[int] = Query(None, description="Cursor for pagination (last contact ID)"),
    limit: int = Query(50, le=200),
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """List contacts with search, status filter, cursor pagination, and status counts."""
    base_filter = [
        models.Contact.user_id == current_user.id,
        models.Contact.deleted_at.is_(None),
    ]

    # --- Status counts (across ALL contacts, unfiltered) ---
    count_rows = db.query(
        models.Contact.status,
        func.count(models.Contact.id),
    ).filter(*base_filter).group_by(models.Contact.status).all()

    counts_map = {row[0]: row[1] for row in count_rows}
    counts = StatusCounts(
        active=counts_map.get("active", 0),
        paused=counts_map.get("paused", 0),
        dnc=counts_map.get("do_not_contact", 0),
        bounced=counts_map.get("bounced", 0),
    )

    # --- Filtered query ---
    query = db.query(models.Contact).options(
        joinedload(models.Contact.organization),
        joinedload(models.Contact.stats),
        selectinload(models.Contact.contact_emails),
    ).filter(*base_filter)

    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            (models.Contact.name.ilike(search_filter))
            | (models.Contact.email.ilike(search_filter))
            | (models.Contact.company.ilike(search_filter))
        )

    if status:
        query = query.filter(models.Contact.status == status)

    # Cursor-based pagination (ordered by id desc for deterministic paging)
    query = query.order_by(models.Contact.id.desc())
    if cursor:
        query = query.filter(models.Contact.id < cursor)

    results = query.limit(limit + 1).all()
    has_more = len(results) > limit
    items = results[:limit]
    next_cursor = items[-1].id if has_more and items else None

    return ContactListResponse(
        items=[_build_list_item(c) for c in items],
        counts=counts,
        nextCursor=next_cursor,
        hasMore=has_more,
    )
```

- [ ] **Step 2: Verify router loads**

```bash
cd /home/tauhid/code/aibot2/backend
python -c "from contacts import router; print(f'Router loaded with {len(router.routes)} routes')"
```

Expected: Router loaded with 1 route (the list endpoint so far).

- [ ] **Step 3: Commit**

```bash
git add backend/contacts.py
git commit -m "feat: rewrite contacts router with GET /contacts — cursor pagination, search, filter, counts"
```

---

## Task 6: Persons Router — Detail Endpoint (P0)

**Files:**
- Modify: `backend/contacts.py` (append after list endpoint)

- [ ] **Step 1: Add the detail endpoint to contacts.py**

Append to `backend/contacts.py`:

```python


@router.get("/{contact_id}", response_model=ContactDetailResponse)
async def get_contact_detail(
    contact_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get full contact detail with all tab data (pulse, deals, timeline, threads, meetings)."""
    contact = db.query(models.Contact).options(
        joinedload(models.Contact.organization),
        joinedload(models.Contact.stats),
        joinedload(models.Contact.pulse),
        selectinload(models.Contact.contact_emails),
        selectinload(models.Contact.deals),
        selectinload(models.Contact.thread_digests),
        selectinload(models.Contact.meetings),
    ).filter(
        models.Contact.id == contact_id,
        models.Contact.user_id == current_user.id,
        models.Contact.deleted_at.is_(None),
    ).first()

    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    # Load activities separately with limit (can be large)
    activities = db.query(models.ContactActivity).filter(
        models.ContactActivity.contact_id == contact_id,
    ).order_by(models.ContactActivity.activity_at.desc().nullslast()).limit(100).all()

    org = contact.organization
    email_list = [ce.email for ce in (contact.contact_emails or [])]
    if not email_list:
        email_list = [contact.email]

    # Build deals with deal title lookup
    deal_map = {}
    deals_response = []
    for deal in (contact.deals or []):
        if deal.deleted_at:
            continue
        deal_map[deal.id] = deal.title
        deals_response.append(ContactDealResponse(
            id=deal.id,
            title=deal.title,
            status=deal.status or "open",
            stage=deal.stage_name,
            value=deal.value,
            expected=format_date_long(deal.expected_close_date),
        ))

    # Build timeline from activities
    timeline = []
    for act in activities:
        deal_title = deal_map.get(act.deal_id) if act.deal_id else None
        # Extract short deal name (e.g., "Acme Corp - Enterprise License" → "Enterprise License")
        if deal_title and " - " in deal_title:
            deal_title = deal_title.split(" - ", 1)[1]
        timeline.append(TimelineEventResponse(
            id=act.id,
            type=act.activity_type,
            dir=act.direction,
            source=act.source_type,
            subject=act.subject,
            summary=act.summary or act.title,
            at=format_datetime_short(act.activity_at or act.occurred_at),
            deal=deal_title,
        ))

    # Build threads from thread_digests
    threads = []
    for td in (contact.thread_digests or []):
        # Load messages from email_queue for this thread
        messages = []
        if td.thread_id:
            eq_items = db.query(models.EmailQueue).filter(
                models.EmailQueue.thread_id == td.thread_id,
                models.EmailQueue.user_id == current_user.id,
                models.EmailQueue.status == "sent",
            ).order_by(models.EmailQueue.sent_at).all()

            user_email = current_user.smtp_username or current_user.email
            for eq in eq_items:
                messages.append(ThreadMessageResponse(
                    id=str(eq.id),
                    sender="you",
                    to=eq.recipient_email,
                    subject=eq.subject,
                    body=eq.body,
                    at=format_datetime_short(eq.sent_at or eq.scheduled_at),
                ))

        threads.append(ThreadResponse(
            id=td.thread_id or str(td.id),
            summary=td.summary,
            sentiment=td.sentiment,
            status=td.thread_status,
            msgs=td.message_count or 0,
            lastAt=format_date_short(td.last_message_at),
            messages=messages,
        ))

    # Build meetings
    meetings_response = []
    for m in (contact.meetings or []):
        meetings_response.append(MeetingResponse(
            id=m.id,
            date=format_date_long(m.meeting_date),
            source=m.source,
            summary=m.summary,
            keyPoints=m.key_points or [],
            objections=m.objections or [],
            signals=m.buying_signals or [],
            stage=m.deal_stage_at_time,
        ))

    # Build pulse (always return an object — frontend does `c.pulse.sentiment` without null checks)
    if contact.pulse:
        p = contact.pulse
        pulse_response = ContactPulseResponse(
            summary=p.summary,
            sentiment=p.sentiment,
            engagement=p.engagement_level,
            intent=p.intent,
            action=p.recommended_action,
            topics=p.key_topics or [],
            objections=p.key_objections or [],
            lastMeeting=format_date_long(p.last_meeting_date),
        )
    else:
        pulse_response = ContactPulseResponse(
            summary="No intelligence data yet. Pulse generates after interactions.",
            sentiment="unknown",
            engagement="low",
            intent="evaluating",
            action="send_followup",
        )

    return ContactDetailResponse(
        id=contact.id,
        name=contact.name,
        email=contact.email,
        orgId=contact.contact_organization_id,
        orgName=org.name if org else contact.company,
        status=contact.status or "active",
        pipedrive=bool(contact.external_person_id and contact.crm_provider == "pipedrive"),
        lastActivity=format_relative_time(contact.last_activity_at),
        emails=email_list,
        stats=_build_stats_response(contact.stats),
        pulse=pulse_response,
        deals=deals_response,
        timeline=timeline,
        threads=threads,
        meetings=meetings_response,
    )
```

- [ ] **Step 2: Verify**

```bash
cd /home/tauhid/code/aibot2/backend
python -c "from contacts import router; print(f'Router loaded with {len(router.routes)} routes')"
```

Expected: 2 routes.

- [ ] **Step 3: Commit**

```bash
git add backend/contacts.py
git commit -m "feat: add GET /contacts/{id} — full detail with pulse, deals, timeline, threads, meetings"
```

---

## Task 7: Organizations Router (P0)

**Files:**
- Create: `backend/contact_orgs.py`

- [ ] **Step 1: Create contact_orgs.py**

```python
"""
Contact organizations router — all /contact-organizations endpoints.
Serves the frontend ContactOrganizationsPage.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
import logging

from database import get_db
from auth import get_current_active_user
import models
from contacts_schemas import (
    OrgListItem, OrgListResponse, OrgDetailResponse, OrgPersonItem,
    OrgUpdateRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_model=OrgListResponse)
async def list_organizations(
    search: Optional[str] = Query(None),
    cursor: Optional[int] = Query(None),
    limit: int = Query(50, le=200),
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """List contact organizations with aggregated stats."""
    query = db.query(models.ContactOrganization).filter(
        models.ContactOrganization.user_id == current_user.id,
        models.ContactOrganization.deleted_at.is_(None),
    )

    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            (models.ContactOrganization.name.ilike(search_filter))
            | (models.ContactOrganization.domain.ilike(search_filter))
        )

    query = query.order_by(models.ContactOrganization.name)
    if cursor:
        query = query.filter(models.ContactOrganization.id > cursor)

    orgs = query.limit(limit).all()

    items = []
    for org in orgs:
        # Count non-deleted contacts in this org
        contact_count = db.query(func.count(models.Contact.id)).filter(
            models.Contact.contact_organization_id == org.id,
            models.Contact.deleted_at.is_(None),
        ).scalar() or 0

        # Aggregate open deals across all contacts in org
        deal_stats = db.query(
            func.count(models.ContactDeal.id),
            func.coalesce(func.sum(models.ContactDeal.value), 0),
        ).join(models.Contact, models.ContactDeal.contact_id == models.Contact.id).filter(
            models.Contact.contact_organization_id == org.id,
            models.Contact.deleted_at.is_(None),
            models.ContactDeal.status == "open",
            models.ContactDeal.deleted_at.is_(None),
        ).first()

        open_deals = deal_stats[0] if deal_stats else 0
        total_value = float(deal_stats[1]) if deal_stats else 0.0

        # Check if any contact has DNC status
        has_dnc = db.query(models.Contact.id).filter(
            models.Contact.contact_organization_id == org.id,
            models.Contact.deleted_at.is_(None),
            models.Contact.status == "do_not_contact",
        ).first() is not None

        items.append(OrgListItem(
            id=org.id,
            name=org.name,
            domain=org.domain,
            contacts=contact_count,
            openDeals=open_deals,
            totalValue=total_value,
            dnc=has_dnc,
            dncProp=org.do_not_contact_propagation if org.do_not_contact_propagation is not None else True,
        ))

    return OrgListResponse(items=items)


@router.get("/{org_id}", response_model=OrgDetailResponse)
async def get_organization_detail(
    org_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get organization detail with persons list."""
    org = db.query(models.ContactOrganization).filter(
        models.ContactOrganization.id == org_id,
        models.ContactOrganization.user_id == current_user.id,
        models.ContactOrganization.deleted_at.is_(None),
    ).first()

    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    contacts = db.query(models.Contact).filter(
        models.Contact.contact_organization_id == org.id,
        models.Contact.deleted_at.is_(None),
    ).all()

    # Aggregate stats
    deal_stats = db.query(
        func.count(models.ContactDeal.id),
        func.coalesce(func.sum(models.ContactDeal.value), 0),
    ).join(models.Contact, models.ContactDeal.contact_id == models.Contact.id).filter(
        models.Contact.contact_organization_id == org.id,
        models.Contact.deleted_at.is_(None),
        models.ContactDeal.status == "open",
        models.ContactDeal.deleted_at.is_(None),
    ).first()

    has_dnc = any(c.status == "do_not_contact" for c in contacts)

    persons = [
        OrgPersonItem(id=c.id, name=c.name, email=c.email, status=c.status or "active")
        for c in contacts
    ]

    return OrgDetailResponse(
        id=org.id,
        name=org.name,
        domain=org.domain,
        contacts=len(contacts),
        openDeals=deal_stats[0] if deal_stats else 0,
        totalValue=float(deal_stats[1]) if deal_stats else 0.0,
        dnc=has_dnc,
        dncProp=org.do_not_contact_propagation if org.do_not_contact_propagation is not None else True,
        persons=persons,
    )


@router.put("/{org_id}", response_model=OrgDetailResponse)
async def update_organization(
    org_id: int,
    data: OrgUpdateRequest,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Update organization name or DNC propagation setting."""
    org = db.query(models.ContactOrganization).filter(
        models.ContactOrganization.id == org_id,
        models.ContactOrganization.user_id == current_user.id,
        models.ContactOrganization.deleted_at.is_(None),
    ).first()

    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    if data.name is not None:
        org.name = data.name
    if data.do_not_contact_propagation is not None:
        org.do_not_contact_propagation = data.do_not_contact_propagation

    db.commit()

    # Re-fetch using the detail endpoint logic
    return await get_organization_detail(org_id, current_user, db)


@router.post("/{org_id}/merge")
async def merge_organization(
    org_id: int,
    data: dict,  # {"merge_id": int}
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Merge another org into this one. Moves all contacts from merge org to keep org."""
    merge_id = data.get("merge_id")
    if not merge_id:
        raise HTTPException(status_code=400, detail="merge_id required")

    keep_org = db.query(models.ContactOrganization).filter(
        models.ContactOrganization.id == org_id,
        models.ContactOrganization.user_id == current_user.id,
        models.ContactOrganization.deleted_at.is_(None),
    ).first()
    merge_org = db.query(models.ContactOrganization).filter(
        models.ContactOrganization.id == merge_id,
        models.ContactOrganization.user_id == current_user.id,
        models.ContactOrganization.deleted_at.is_(None),
    ).first()

    if not keep_org or not merge_org:
        raise HTTPException(status_code=404, detail="Both organizations must exist")

    # Move contacts from merge org to keep org
    db.query(models.Contact).filter(
        models.Contact.contact_organization_id == merge_id,
        models.Contact.deleted_at.is_(None),
    ).update({"contact_organization_id": org_id})

    # Move deals from merge org to keep org
    db.query(models.ContactDeal).filter(
        models.ContactDeal.contact_organization_id == merge_id,
    ).update({"contact_organization_id": org_id})

    # Soft-delete the merged org
    from datetime import datetime
    merge_org.deleted_at = datetime.utcnow()
    db.commit()

    return {"success": True, "keptId": org_id}
```

- [ ] **Step 2: Verify**

```bash
cd /home/tauhid/code/aibot2/backend
python -c "from contact_orgs import router; print(f'Org router loaded with {len(router.routes)} routes')"
```

Expected: 3 routes.

- [ ] **Step 3: Commit**

```bash
git add backend/contact_orgs.py
git commit -m "feat: add contact organizations router — list, detail, update endpoints"
```

---

## Task 8: Router Registration + Smoke Test

**Files:**
- Modify: `backend/main.py` (lines 20-21, 97-98)

- [ ] **Step 1: Update main.py imports and router registration**

In `backend/main.py`, add the import for contact_orgs (after the contacts import on line 20):

```python
from contact_orgs import router as contact_orgs_router
```

Add router registration after the existing contacts line (after line 97):

```python
app.include_router(contact_orgs_router, prefix="/contact-organizations", tags=["Contact Organizations"])
```

- [ ] **Step 2: Update any other files that import from old contacts.py**

Search for imports of the old `get_or_create_contact` and `record_email_sent` from `contacts`. Only `main.py` imports from contacts. The old functions (`get_or_create_contact`, `record_email_sent`) were only used within `contacts.py` itself — they are utility functions called by external code via direct import.

Check if any file imports these functions:

```bash
cd /home/tauhid/code/aibot2/backend
grep -rn "from contacts import\|from contacts_service import" --include="*.py" .
```

If any file besides `main.py` imports from `contacts`, update it to import from `contacts_service` instead. The email_queue.py module accesses contacts via `models.Contact` (SQLAlchemy queries), not via the old utility functions.

- [ ] **Step 3: Start the server and smoke test**

```bash
cd /home/tauhid/code/aibot2/backend
python -c "from main import app; print('App loaded successfully')"
```

Expected: No import errors.

Then start the server and test:

```bash
# Start backend (in Docker or locally)
# Then test with curl:
curl -s http://localhost:9000/contacts/ -H "Authorization: Bearer <token>" | python -m json.tool | head -20
curl -s http://localhost:9000/contact-organizations/ -H "Authorization: Bearer <token>" | python -m json.tool | head -20
```

Expected: Both return JSON with the correct shape (`items`, `counts`, `nextCursor`, `hasMore` for contacts; `items` for orgs).

- [ ] **Step 4: Commit**

```bash
git add backend/main.py
git commit -m "feat: register contact-organizations router in main.py"
```

---

## Task 9: Write Endpoints (P1)

**Files:**
- Modify: `backend/contacts.py` (append after detail endpoint)

- [ ] **Step 1: Add POST, PUT, PUT status, DELETE endpoints**

Append to `backend/contacts.py`:

```python


# --- Write Endpoints (P1) ---

@router.post("/", response_model=ContactDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_contact(
    data: ContactCreateRequest,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Create a new contact (calls get_or_create_contact internally)."""
    contact = get_or_create_contact(
        db=db,
        user_id=current_user.id,
        email=data.email,
        name=data.name,
        organization_name=data.organization_name,
    )
    db.commit()
    return await get_contact_detail(contact.id, current_user, db)


@router.put("/{contact_id}", response_model=ContactDetailResponse)
async def update_contact(
    contact_id: int,
    data: ContactUpdateRequest,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Update contact fields."""
    contact = db.query(models.Contact).filter(
        models.Contact.id == contact_id,
        models.Contact.user_id == current_user.id,
        models.Contact.deleted_at.is_(None),
    ).first()

    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    if data.name is not None:
        contact.name = data.name
        contact.avatar_initials = generate_initials(data.name, contact.email)
    if data.email is not None:
        contact.email = data.email
        contact.primary_email = data.email
    if data.title is not None:
        contact.title = data.title
    if data.company is not None:
        contact.company = data.company
    if data.contact_organization_id is not None:
        contact.contact_organization_id = data.contact_organization_id

    db.commit()
    return await get_contact_detail(contact_id, current_user, db)


@router.put("/{contact_id}/status")
async def update_contact_status(
    contact_id: int,
    data: ContactStatusRequest,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Set contact status (active/paused/do_not_contact/bounced) with DNC org propagation."""
    if data.status not in ("active", "paused", "do_not_contact", "bounced"):
        raise HTTPException(status_code=400, detail="Invalid status")

    contact = db.query(models.Contact).filter(
        models.Contact.id == contact_id,
        models.Contact.user_id == current_user.id,
        models.Contact.deleted_at.is_(None),
    ).first()

    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    contact.status = data.status

    # DNC org propagation: if setting DNC and org has propagation enabled,
    # set all other contacts at the same org to DNC too
    if data.status == "do_not_contact" and contact.contact_organization_id:
        org = db.query(models.ContactOrganization).filter(
            models.ContactOrganization.id == contact.contact_organization_id,
        ).first()
        if org and org.do_not_contact_propagation:
            db.query(models.Contact).filter(
                models.Contact.contact_organization_id == org.id,
                models.Contact.user_id == current_user.id,
                models.Contact.deleted_at.is_(None),
                models.Contact.id != contact_id,
            ).update({"status": "do_not_contact"})

    db.commit()
    return {"success": True, "status": data.status}


@router.delete("/{contact_id}")
async def delete_contact(
    contact_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Soft-delete a contact."""
    contact = db.query(models.Contact).filter(
        models.Contact.id == contact_id,
        models.Contact.user_id == current_user.id,
        models.Contact.deleted_at.is_(None),
    ).first()

    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    contact.deleted_at = datetime.utcnow()
    db.commit()

    return {"success": True}


@router.post("/{contact_id}/note")
async def add_contact_note(
    contact_id: int,
    data: ContactNoteRequest,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Add a note to the contact timeline."""
    contact = db.query(models.Contact).filter(
        models.Contact.id == contact_id,
        models.Contact.user_id == current_user.id,
        models.Contact.deleted_at.is_(None),
    ).first()

    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    activity = log_activity(
        db=db,
        user_id=current_user.id,
        contact_id=contact_id,
        activity_type="note",
        direction="internal",
        summary=data.content,
        title="Note added",
    )
    db.commit()

    return {"success": True, "activityId": activity.id}


@router.post("/{contact_id}/merge")
async def merge_contact(
    contact_id: int,
    data: ContactMergeRequest,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Merge another contact into this one."""
    try:
        kept = merge_contacts(
            db=db,
            user_id=current_user.id,
            keep_id=contact_id,
            merge_id=data.merge_id,
        )
        db.commit()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"success": True, "keptId": kept.id}
```

- [ ] **Step 2: Verify all routes**

```bash
cd /home/tauhid/code/aibot2/backend
python -c "from contacts import router; print(f'Router: {len(router.routes)} routes')"
```

Expected: 8 routes (GET list, GET detail, POST create, PUT update, PUT status, DELETE, POST note, POST merge).

- [ ] **Step 3: Commit**

```bash
git add backend/contacts.py
git commit -m "feat: add contact write endpoints — create, update, status, delete, note, merge"
```

---

## Task 10: Workflow Integration

**Files:**
- Modify: `backend/executions.py` — Hook get_or_create_contact into email queuing
- Modify: `backend/email_worker.py` — Hook log_activity into post-send

This task connects the contact system to the existing workflow engine. When a workflow queues an email, the contact is auto-created. When an email is sent, it's logged as an activity.

- [ ] **Step 1: Find the email queuing code in executions.py**

Search for where `EmailQueue` records are created:

```bash
cd /home/tauhid/code/aibot2/backend
grep -n "EmailQueue(" executions.py
```

At each location where an `EmailQueue` is created with a `recipient_email`, add a contact lookup:

```python
from contacts_service import get_or_create_contact

# Before creating EmailQueue record:
contact = get_or_create_contact(
    db=db,
    user_id=user_id,
    email=recipient_email,
    name=recipient_name,
)
# Then set email_queue.contact_id = contact.id
```

- [ ] **Step 2: Find the email sending code in email_worker.py**

Search for where email status is updated to "sent":

```bash
cd /home/tauhid/code/aibot2/backend
grep -n 'status.*=.*"sent"\|record_email_sent' email_worker.py email_queue.py
```

At each location where an email is marked as sent, add activity logging:

```python
from contacts_service import log_activity

# After email is successfully sent and status set to "sent":
if email_record.contact_id:
    log_activity(
        db=db,
        user_id=email_record.user_id,
        contact_id=email_record.contact_id,
        activity_type="email_sent",
        direction="outbound",
        source_type="scurry_sequence",
        source_id=f"eq_{email_record.id}",
        email_queue_id=email_record.id,
        subject=email_record.subject,
        title=f"Email sent: {email_record.subject[:50]}",
    )
```

- [ ] **Step 3: Test with a workflow run**

Run a workflow that sends an email. Verify:
1. A Contact record is created (or found) for the recipient
2. A ContactEmail record exists
3. A ContactStats record exists
4. After email sends, a ContactActivity is logged

```bash
docker compose exec postgres psql -U workflow_user -d workflow_platform \
  -c "SELECT id, email, name, status FROM contacts ORDER BY id DESC LIMIT 5;" \
  -c "SELECT id, contact_id, activity_type, direction FROM contact_activities ORDER BY id DESC LIMIT 5;"
```

- [ ] **Step 4: Commit**

```bash
git add backend/executions.py backend/email_worker.py
git commit -m "feat: integrate contact system with workflow engine — auto-create on queue, log on send"
```

---

## Task 11: Contact Pulse — AI Intelligence Layer

**Files:**
- Modify: `backend/contacts_service.py` (append)
- Modify: `backend/contacts.py` (add refresh-pulse endpoint)

- [ ] **Step 1: Add generate_contact_pulse to contacts_service.py**

Append to `backend/contacts_service.py`:

```python
def generate_contact_pulse(
    db: Session,
    user_id: int,
    contact_id: int,
) -> models.ContactPulse:
    """
    Generate or refresh the AI Contact Pulse for a contact.
    Summarizes all activities, deals, meetings into actionable intelligence.
    """
    import json
    from ai_service import analyze_with_ai

    contact = db.query(models.Contact).filter(
        models.Contact.id == contact_id,
        models.Contact.user_id == user_id,
        models.Contact.deleted_at.is_(None),
    ).first()
    if not contact:
        raise ValueError("Contact not found")

    # Gather context
    recent_activities = db.query(models.ContactActivity).filter(
        models.ContactActivity.contact_id == contact_id,
    ).order_by(models.ContactActivity.activity_at.desc().nullslast()).limit(30).all()

    deals = db.query(models.ContactDeal).filter(
        models.ContactDeal.contact_id == contact_id,
        models.ContactDeal.deleted_at.is_(None),
    ).all()

    meetings = db.query(models.MeetingHistory).filter(
        models.MeetingHistory.contact_id == contact_id,
    ).order_by(models.MeetingHistory.meeting_date.desc()).limit(5).all()

    stats = db.query(models.ContactStats).filter(
        models.ContactStats.contact_id == contact_id,
    ).first()

    # Build prompt context
    activities_text = "\n".join([
        f"- [{a.activity_type}] {a.summary or a.title} ({a.direction or 'n/a'}, {a.activity_at})"
        for a in recent_activities
    ])

    deals_text = "\n".join([
        f"- {d.title}: {d.status} ({d.stage_name}), ${d.value or 0}"
        for d in deals
    ]) or "No deals"

    meetings_text = "\n".join([
        f"- {m.meeting_date}: {m.summary}"
        for m in meetings
    ]) or "No meetings"

    stats_text = ""
    if stats:
        stats_text = f"Emails sent: {stats.emails_sent}, Received: {stats.emails_received}, Reply rate: {stats.reply_rate:.1f}%, Meetings: {stats.meetings_count}"

    prompt = f"""Analyze this contact and provide a JSON intelligence summary.

Contact: {contact.name or contact.email}
Company: {contact.company or 'Unknown'}
Status: {contact.status}
Stats: {stats_text}

Recent Activity (newest first):
{activities_text or "No activities"}

Deals:
{deals_text}

Meetings:
{meetings_text}

Return ONLY a JSON object with these fields:
- summary: 1-2 sentence executive summary of this contact's engagement
- sentiment: "positive", "neutral", or "negative"
- engagement: "high", "medium", or "low"
- intent: "interested", "evaluating", or "not_interested"
- action: "continue_sequence", "pause", "send_followup", or "close_out"
- topics: array of key discussion topics (max 5)
- objections: array of objections or concerns raised (max 5)
"""

    try:
        result = analyze_with_ai(prompt, "")
        data = json.loads(result) if isinstance(result, str) else result
    except Exception as e:
        logger.error(f"Pulse generation failed for contact {contact_id}: {e}")
        data = {
            "summary": "Unable to generate pulse — insufficient data.",
            "sentiment": "unknown",
            "engagement": "low",
            "intent": "evaluating",
            "action": "send_followup",
            "topics": [],
            "objections": [],
        }

    now = datetime.utcnow()

    # Get last meeting date
    last_meeting = db.query(models.MeetingHistory.meeting_date).filter(
        models.MeetingHistory.contact_id == contact_id,
    ).order_by(models.MeetingHistory.meeting_date.desc()).first()

    # Upsert pulse
    pulse = db.query(models.ContactPulse).filter(
        models.ContactPulse.contact_id == contact_id,
    ).first()

    if not pulse:
        pulse = models.ContactPulse(
            contact_id=contact_id,
            user_id=user_id,
        )
        db.add(pulse)

    pulse.summary = data.get("summary")
    pulse.sentiment = data.get("sentiment")
    pulse.engagement_level = data.get("engagement")
    pulse.intent = data.get("intent")
    pulse.recommended_action = data.get("action")
    pulse.key_topics = data.get("topics", [])
    pulse.key_objections = data.get("objections", [])
    pulse.last_meeting_date = last_meeting[0] if last_meeting else None
    pulse.generated_at = now

    db.flush()
    logger.info("Generated contact pulse", extra={"user_id": user_id, "contact_id": contact_id})
    return pulse
```

- [ ] **Step 2: Add refresh-pulse endpoint to contacts.py**

Append to `backend/contacts.py`:

```python


@router.post("/{contact_id}/refresh-pulse")
async def refresh_contact_pulse(
    contact_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Regenerate the Contact Pulse AI intelligence summary."""
    from contacts_service import generate_contact_pulse

    contact = db.query(models.Contact).filter(
        models.Contact.id == contact_id,
        models.Contact.user_id == current_user.id,
        models.Contact.deleted_at.is_(None),
    ).first()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    pulse = generate_contact_pulse(db, current_user.id, contact_id)
    db.commit()

    return {"success": True, "generatedAt": pulse.generated_at.isoformat() if pulse.generated_at else None}
```

- [ ] **Step 3: Commit**

```bash
git add backend/contacts_service.py backend/contacts.py
git commit -m "feat: add Contact Pulse AI intelligence — generate and refresh endpoints"
```

---

## Task 12: Frontend API Wiring

**Files:**
- Modify: `frontend/src/lib/api.ts` (lines 584-735)
- Modify: `frontend/src/pages/ContactPersonsPage.tsx`
- Modify: `frontend/src/pages/ContactOrganizationsPage.tsx`

- [ ] **Step 1: Update api.ts contact types and API calls**

Replace the existing contact types and API calls in `frontend/src/lib/api.ts` (the `ContactInfo`, `ContactActivity`, `Contact`, and `contactsApi` sections) with:

```typescript
// --- Contact System V2 Types ---

export interface ContactStats {
  sent: number
  received: number
  rate: string
  meetings: number
  sequences: number
  openDeals: number
  dealValue: number
}

export interface ContactPulse {
  summary: string | null
  sentiment: string | null
  engagement: string | null
  intent: string | null
  action: string | null
  topics: string[]
  objections: string[]
  lastMeeting: string | null
}

export interface ContactDeal {
  id: number
  title: string
  status: string
  stage: string | null
  value: number | null
  expected: string | null
}

export interface TimelineEvent {
  id: number
  type: string
  dir: string | null
  source: string | null
  subject?: string
  summary: string | null
  at: string | null
  deal?: string
}

export interface ThreadMessage {
  id: string
  from: string  // "you" or sender email — backend serializes via Field(serialization_alias="from")
  to: string
  subject?: string
  body?: string
  at?: string
}

export interface Thread {
  id: string
  summary: string | null
  sentiment: string | null
  status: string | null
  msgs: number
  lastAt: string | null
  messages: ThreadMessage[]
}

export interface Meeting {
  id: number
  date: string | null
  source: string | null
  summary: string | null
  keyPoints: string[]
  objections: string[]
  signals: string[]
  stage: string | null
}

export interface ContactListItem {
  id: number
  name: string | null
  email: string
  orgId: number | null
  orgName: string | null
  status: string
  pipedrive: boolean
  lastActivity: string | null
  stats: ContactStats
  emails: string[]
}

export interface ContactListResponse {
  items: ContactListItem[]
  counts: { active: number; paused: number; dnc: number; bounced: number }
  nextCursor: number | null
  hasMore: boolean
}

export interface ContactDetail extends ContactListItem {
  pulse: ContactPulse  // Always present — API returns default pulse if none generated
  deals: ContactDeal[]
  timeline: TimelineEvent[]
  threads: Thread[]
  meetings: Meeting[]
}

export interface OrgListItem {
  id: number
  name: string
  domain: string | null
  contacts: number
  openDeals: number
  totalValue: number
  dnc: boolean
  dncProp: boolean
}

export interface OrgDetail extends OrgListItem {
  persons: { id: number; name: string | null; email: string; status: string }[]
}

// Contacts API
export const contactsApi = {
  list: (params?: { search?: string; status?: string; cursor?: number; limit?: number }) =>
    api.get<ContactListResponse>('/contacts/', { params }),

  getById: (contactId: number) =>
    api.get<ContactDetail>(`/contacts/${contactId}`),

  create: (data: { email: string; name?: string; organization_name?: string }) =>
    api.post<ContactDetail>('/contacts/', data),

  update: (contactId: number, data: { name?: string; email?: string; title?: string; company?: string }) =>
    api.put<ContactDetail>(`/contacts/${contactId}`, data),

  updateStatus: (contactId: number, status: string) =>
    api.put(`/contacts/${contactId}/status`, { status }),

  delete: (contactId: number) =>
    api.delete(`/contacts/${contactId}`),

  addNote: (contactId: number, content: string) =>
    api.post(`/contacts/${contactId}/note`, { content }),

  merge: (keepId: number, mergeId: number) =>
    api.post(`/contacts/${keepId}/merge`, { merge_id: mergeId }),

  refreshPulse: (contactId: number) =>
    api.post(`/contacts/${contactId}/refresh-pulse`),
}

export const contactOrgsApi = {
  list: (params?: { search?: string; cursor?: number; limit?: number }) =>
    api.get<{ items: OrgListItem[] }>('/contact-organizations/', { params }),

  getById: (orgId: number) =>
    api.get<OrgDetail>(`/contact-organizations/${orgId}`),

  update: (orgId: number, data: { name?: string; do_not_contact_propagation?: boolean }) =>
    api.put<OrgDetail>(`/contact-organizations/${orgId}`, data),
}
```

- [ ] **Step 2: Swap MOCK_CONTACTS → useQuery in ContactPersonsPage.tsx**

**Critical pattern change:** The list endpoint returns `ContactListItem` (no pulse/deals/timeline/threads/meetings). The detail view needs the full `ContactDetail`. The frontend must fetch detail data when a contact is clicked — NOT pass the list item directly.

Add imports at top of file:

```typescript
import { useQuery } from '@tanstack/react-query'
import { contactsApi, type ContactListItem, type ContactDetail } from '@/lib/api'
```

Replace state and data loading (lines 559-578):

```typescript
const ContactPersonsPage: React.FC = () => {
  const [selectedContactId, setSelectedContactId] = useState<number | null>(null)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<FilterType>(null)

  // List query
  const { data: contactsResponse } = useQuery({
    queryKey: ['contacts-persons', search, statusFilter],
    queryFn: () => contactsApi.list({
      search: search || undefined,
      status: statusFilter || undefined,
    }).then(r => r.data),
  })
  const contacts = contactsResponse?.items ?? []
  const counts = contactsResponse?.counts ?? { active: 0, paused: 0, dnc: 0, bounced: 0 }

  // Detail query (only when a contact is selected)
  const { data: selectedContact } = useQuery({
    queryKey: ['contact-detail', selectedContactId],
    queryFn: () => contactsApi.getById(selectedContactId!).then(r => r.data),
    enabled: !!selectedContactId,
  })
```

Replace the detail rendering check (line 580-582):

```typescript
  if (selectedContactId && selectedContact) {
    return <ContactDetail contact={selectedContact} onBack={() => setSelectedContactId(null)} />
  }
```

Replace the click handler in the contact list (line 656):

```typescript
onClick={() => setSelectedContactId(c.id)}
```

Remove the `useMemo` for `counts` (lines 573-578) — use the API counts instead.

The `filtered` useMemo still works for client-side filtering on the returned items:

```typescript
  const filtered = useMemo(() => contacts.filter(c => {
    const q = search.toLowerCase()
    return (!q || (c.name || '').toLowerCase().includes(q) || c.email.includes(q) || (c.orgName || '').toLowerCase().includes(q)) && (!statusFilter || c.status === statusFilter)
  }), [contacts, search, statusFilter])
```

Delete the `MOCK_CONTACTS` array (lines 118-191) and update the `Contact` type references to use `ContactListItem` for the list and `ContactDetail` for the detail view.

**Note:** The `ContactDetail` component already accepts `contact: Contact` — this type needs to match `ContactDetail` from api.ts. The `Contact` interface defined locally can be removed, and the imported `ContactDetail` type used instead. The internal `ContactStats`, `ContactPulse`, `Deal`, etc. interfaces (lines 27-114) can also be removed since they're now in api.ts.

- [ ] **Step 3: Swap MOCK_ORGS → useQuery in ContactOrganizationsPage.tsx**

**Same two-step pattern:** The org list returns `OrgListItem` (no persons). The detail view needs `OrgDetail` with `persons`. Fetch on click.

Add imports:

```typescript
import { useQuery } from '@tanstack/react-query'
import { contactOrgsApi, type OrgListItem, type OrgDetail } from '@/lib/api'
```

Replace state and data loading (lines 172-177):

```typescript
const ContactOrganizationsPage: React.FC = () => {
  const [selectedOrgId, setSelectedOrgId] = useState<number | null>(null)
  const [search, setSearch] = useState('')

  // List query
  const { data: orgsResponse } = useQuery({
    queryKey: ['contact-organizations', search],
    queryFn: () => contactOrgsApi.list({ search: search || undefined }).then(r => r.data),
  })
  const orgs = orgsResponse?.items ?? []

  // Detail query
  const { data: selectedOrgDetail } = useQuery({
    queryKey: ['contact-org-detail', selectedOrgId],
    queryFn: () => contactOrgsApi.getById(selectedOrgId!).then(r => r.data),
    enabled: !!selectedOrgId,
  })
```

Replace the detail rendering check (line 184-186):

```typescript
  if (selectedOrgId && selectedOrgDetail) {
    return <OrgDetail org={selectedOrgDetail} onBack={() => setSelectedOrgId(null)} />
  }
```

Update `OrgDetail` component (line 80-81) to use the API data for persons instead of `MOCK_ORG_CONTACTS`:

```typescript
function OrgDetail({ org, onBack }: { org: OrgDetail; onBack: () => void }) {
  const contacts = org.persons || []
```

Replace click handler (line 215):

```typescript
onClick={() => setSelectedOrgId(o.id)}
```

Delete `MOCK_ORGS` (lines 43-49) and `MOCK_ORG_CONTACTS` (lines 51-64). Delete the local `Organization` and `OrgContact` interfaces (lines 23-39) — use types from api.ts.

- [ ] **Step 4: Test frontend renders**

```bash
cd /home/tauhid/code/aibot2/frontend
bun run dev
```

Navigate to `/contacts/persons` and `/contacts/organizations`. Both should render (with real data if backend is running, or empty lists if no data yet). Click a contact to verify detail loads via API.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/pages/ContactPersonsPage.tsx frontend/src/pages/ContactOrganizationsPage.tsx
git commit -m "feat: wire frontend to contact system API — replace mock data with useQuery, two-step fetch"
```

---

## Task 13: CSV Export Endpoints (P2)

**Files:**
- Modify: `backend/contacts.py` (append)
- Modify: `backend/contact_orgs.py` (append)

- [ ] **Step 1: Add export endpoint to contacts.py**

Append to `backend/contacts.py`:

```python
from fastapi.responses import StreamingResponse
import csv
import io


@router.get("/export")
async def export_contacts(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Export all contacts as CSV."""
    contacts = db.query(models.Contact).options(
        joinedload(models.Contact.organization),
        joinedload(models.Contact.stats),
    ).filter(
        models.Contact.user_id == current_user.id,
        models.Contact.deleted_at.is_(None),
    ).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Email", "Organization", "Status", "Emails Sent", "Emails Received", "Reply Rate", "Open Deals"])

    for c in contacts:
        s = c.stats
        writer.writerow([
            c.name or "",
            c.email,
            c.organization.name if c.organization else c.company or "",
            c.status or "active",
            s.emails_sent if s else 0,
            s.emails_received if s else 0,
            f"{s.reply_rate:.1f}%" if s and s.reply_rate else "0.0%",
            s.open_deals if s else 0,
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=contacts.csv"},
    )
```

**CRITICAL route ordering:** The `/export` route MUST be defined BEFORE `/{contact_id}` in the router file, because FastAPI matches routes in order and "export" would be captured by `{contact_id}` as a path parameter. When adding this code, insert the `export_contacts` function definition in `contacts.py` between `list_contacts` and `get_contact_detail`. Same applies in `contact_orgs.py` — put `export_organizations` before `get_organization_detail`.

- [ ] **Step 2: Add org export to contact_orgs.py**

Append to `backend/contact_orgs.py`:

```python
from fastapi.responses import StreamingResponse
import csv
import io


@router.get("/export")
async def export_organizations(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Export all contact organizations as CSV."""
    orgs = db.query(models.ContactOrganization).filter(
        models.ContactOrganization.user_id == current_user.id,
        models.ContactOrganization.deleted_at.is_(None),
    ).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Domain", "Contacts", "DNC", "DNC Propagation"])

    for org in orgs:
        contact_count = db.query(func.count(models.Contact.id)).filter(
            models.Contact.contact_organization_id == org.id,
            models.Contact.deleted_at.is_(None),
        ).scalar() or 0

        has_dnc = db.query(models.Contact.id).filter(
            models.Contact.contact_organization_id == org.id,
            models.Contact.status == "do_not_contact",
            models.Contact.deleted_at.is_(None),
        ).first() is not None

        writer.writerow([
            org.name,
            org.domain or "",
            contact_count,
            "Yes" if has_dnc else "No",
            "Yes" if org.do_not_contact_propagation else "No",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=contact-organizations.csv"},
    )
```

**Same route ordering note:** The `/export` route must appear before `/{org_id}` in the router.

- [ ] **Step 3: Commit**

```bash
git add backend/contacts.py backend/contact_orgs.py
git commit -m "feat: add CSV export for contacts and contact organizations"
```

---

## Task 14: Final Validation

- [ ] **Step 1: Run backend and verify all endpoints**

```bash
cd /home/tauhid/code/aibot2/backend
python -c "
from contacts import router as cr
from contact_orgs import router as or_
print(f'Contact routes: {len(cr.routes)}')
print(f'Org routes: {len(or_.routes)}')
for r in cr.routes:
    print(f'  {", ".join(r.methods)} {r.path}')
for r in or_.routes:
    print(f'  {", ".join(r.methods)} {r.path}')
"
```

Expected endpoints:

**Contacts (prefix /contacts):**
- GET / (list with search, status filter, counts, cursor pagination)
- GET /export (CSV download)
- GET /{contact_id} (full detail with all 5 tabs)
- POST / (create via get_or_create_contact)
- PUT /{contact_id} (update fields)
- PUT /{contact_id}/status (with DNC org propagation)
- DELETE /{contact_id} (soft delete)
- POST /{contact_id}/note (add to timeline)
- POST /{contact_id}/merge (merge contacts)
- POST /{contact_id}/refresh-pulse (regenerate AI intelligence)

**Organizations (prefix /contact-organizations):**
- GET / (list with search, aggregated stats)
- GET /export (CSV download)
- GET /{org_id} (detail with persons list)
- PUT /{org_id} (update name, DNC propagation)
- POST /{org_id}/merge (merge organizations)

- [ ] **Step 2: Verify frontend TypeScript**

```bash
cd /home/tauhid/code/aibot2/frontend
npx tsc --noEmit
```

Expected: No type errors related to contact types.

- [ ] **Step 3: Final commit with all remaining changes**

```bash
git add -A
git status
# Review that only expected files are staged
git commit -m "feat: contact system V2 — complete implementation with all endpoints"
```

---

## Hard Rules Checklist

Before marking the implementation as complete, verify each rule from the spec:

- [ ] Every DB query is scoped by `user_id`
- [ ] Soft delete: `WHERE deleted_at IS NULL` on all reads
- [ ] Parameterized queries only (no string concatenation in SQL)
- [ ] Advisory locks on create (in get_or_create_contact and _get_or_create_org)
- [ ] Activities are append-only (no update/delete endpoints for activities)
- [ ] Structured JSON logging (user_id + contact_id + operation in all log calls)
- [ ] All work on `josh` branch
