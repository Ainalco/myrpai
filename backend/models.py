import enum
from sqlalchemy import Column, Integer, String, Text, DateTime, Date, Boolean, ForeignKey, JSON, Float, Enum as SAEnum, UniqueConstraint

# Hard requirement — NOT wrapped in try/except. A silent JSON fallback would let
# the app start against a real pgvector column and write rows through SQLAlchemy
# as JSON, either failing far from the root cause (DataError on every insert)
# or silently corrupting the index. If this import fails, the deploy is broken
# and needs to fail loudly at module load rather than at query time. pgvector
# is pinned in requirements.txt.
from pgvector.sqlalchemy import Vector

from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


# --- Enums for multi-tenant SaaS ---

class PlanTier(str, enum.Enum):
    trialing = "trialing"
    seedling = "seedling"
    oak = "oak"
    redwood = "redwood"
    ancient_forest = "ancient_forest"


class AccountStatus(str, enum.Enum):
    trialing = "trialing"
    active = "active"
    past_due = "past_due"
    suspended = "suspended"
    cancelled = "cancelled"


class UserRole(str, enum.Enum):
    owner = "owner"
    admin = "admin"
    member = "member"


class AcornTransactionType(str, enum.Enum):
    trial_credit = "trial_credit"
    subscription_credit = "subscription_credit"
    purchase = "purchase"
    usage = "usage"
    adjustment = "adjustment"
    refund = "refund"


class InvitationStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    expired = "expired"
    revoked = "revoked"


# --- Multi-tenant models ---

class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False, index=True)
    domain = Column(String, nullable=True)
    logo_url = Column(String, nullable=True)
    settings = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    account = relationship("Account", back_populates="organization", uselist=False, cascade="all, delete-orphan")
    members = relationship("User", back_populates="organization")
    invitations = relationship("Invitation", back_populates="organization", cascade="all, delete-orphan")


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), unique=True, nullable=False)
    paddle_customer_id = Column(String, nullable=True, unique=True)
    paddle_subscription_id = Column(String, nullable=True, unique=True)
    plan_tier = Column(SAEnum(PlanTier), default=PlanTier.trialing, nullable=False)
    billing_cycle = Column(String, nullable=True)  # "monthly" or "yearly"
    acorn_balance = Column(Float, default=0, nullable=False)
    acorn_allocation_mode = Column(String(20), default="shared", nullable=False)  # "shared" or "locked"
    status = Column(SAEnum(AccountStatus), default=AccountStatus.trialing, nullable=False)
    trial_ends_at = Column(DateTime(timezone=True), nullable=True)
    current_period_ends_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    organization = relationship("Organization", back_populates="account")
    acorn_transactions = relationship("AcornTransaction", back_populates="account", cascade="all, delete-orphan")


class AcornTransaction(Base):
    __tablename__ = "acorn_transactions"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    type = Column(SAEnum(AcornTransactionType), nullable=False)
    amount = Column(Float, nullable=False)  # positive for credits, negative for usage
    balance_after = Column(Float, nullable=False)
    description = Column(String(500), nullable=False)
    paddle_transaction_id = Column(String, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    account = relationship("Account", back_populates="acorn_transactions")
    user = relationship("User")


class SystemConfig(Base):
    __tablename__ = "system_config"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=False)
    description = Column(String(500), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PaddleWebhookEvent(Base):
    """Tracks processed Paddle webhook events for idempotency."""
    __tablename__ = "paddle_webhook_events"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String(255), unique=True, nullable=False, index=True)
    event_type = Column(String(100), nullable=False)
    raw_payload = Column(Text, nullable=True)
    processed_at = Column(DateTime(timezone=True), server_default=func.now())


class Invitation(Base):
    __tablename__ = "invitations"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    invited_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    email = Column(String(255), nullable=False)
    role = Column(SAEnum(UserRole), nullable=False, default=UserRole.member)
    token = Column(String(255), unique=True, nullable=False, index=True)
    status = Column(SAEnum(InvitationStatus), nullable=False, default=InvitationStatus.pending)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    organization = relationship("Organization", back_populates="invitations")
    inviter = relationship("User", foreign_keys=[invited_by])


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(100), nullable=False, index=True)
    target_type = Column(String(50), nullable=True)
    target_id = Column(Integer, nullable=True)
    details = Column(JSON, nullable=True)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    organization = relationship("Organization")
    user = relationship("User")


# --- Existing models (modified) ---

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String)
    is_active = Column(Boolean, default=True)
    is_superadmin = Column(Boolean, default=False)
    enable_advanced_components = Column(Boolean, default=False)  # Feature flag: allow access to advanced/power-user components
    internal_domains = Column(Text)  # Comma-separated list of internal email domains (e.g., "company.com,company.io")

    # Multi-tenant fields
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)  # nullable — soft-delete preserves user rows
    role = Column(SAEnum(UserRole), default=UserRole.owner)
    locked_acorn_allocation = Column(Float, nullable=True)  # Per-cycle budget cap (set by admin, resets balance on renewal)
    locked_acorn_balance = Column(Float, nullable=True)     # Current remaining (decreases on spend, resets to allocation on cycle renewal)
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    # SMTP Configuration for sending emails
    smtp_host = Column(String)  # e.g., smtp.gmail.com
    smtp_port = Column(Integer)  # e.g., 587, 465
    smtp_username = Column(String)  # SMTP username/email
    smtp_password = Column(Text)  # Encrypted SMTP password
    smtp_use_tls = Column(Boolean, default=True)  # Use TLS encryption
    smtp_from_email = Column(String)  # From email address
    smtp_from_name = Column(String)  # From name

    # Email signature
    email_signature = Column(Text)  # HTML email signature
    email_signature_enabled = Column(Boolean, default=True)  # Whether to append signature to outgoing emails

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    organization = relationship("Organization", back_populates="members")
    workflows = relationship("Workflow", back_populates="owner")
    contacts = relationship("Contact", back_populates="user", cascade="all, delete-orphan")

class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    universal_rules = Column(Text)  # Rules to be injected into all AI prompts for this workflow
    # RAG toggles: {"smart_context_diversity": bool, "thin_transcript_prompt": bool}
    rag_settings = Column(JSON, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    owner = relationship("User", back_populates="workflows")
    components = relationship("Component", back_populates="workflow", cascade="all, delete-orphan")
    executions = relationship("Execution", back_populates="workflow", cascade="all, delete-orphan")
    webhooks = relationship("Webhook", back_populates="workflow", cascade="all, delete-orphan")
    extracted_variables = relationship("ExtractedVariable", back_populates="workflow", cascade="all, delete-orphan")
    email_queue = relationship("EmailQueue", back_populates="workflow", cascade="all, delete-orphan")
    email_sequence_config = relationship("EmailSequenceConfig", back_populates="workflow", uselist=False, cascade="all, delete-orphan")

class Component(Base):
    __tablename__ = "components"
    
    id = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(Integer, ForeignKey("workflows.id"))
    type = Column(String, nullable=False)  # input_sources, text_generation, email, conditional_logic, ai_filter, action
    name = Column(String, nullable=False)
    description = Column(Text)
    configuration = Column(JSON)  # Component-specific config
    position_x = Column(Integer, default=0)
    position_y = Column(Integer, default=0)
    order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    workflow = relationship("Workflow", back_populates="components")
    connections_from = relationship("Connection", foreign_keys="Connection.from_component_id", cascade="all, delete-orphan")
    connections_to = relationship("Connection", foreign_keys="Connection.to_component_id", cascade="all, delete-orphan")
    webhooks = relationship("Webhook", back_populates="component", cascade="all, delete-orphan")
    component_executions = relationship("ComponentExecution", back_populates="component", cascade="all, delete-orphan")
    email_queue_items = relationship(
        "EmailQueue",
        back_populates="component",
        cascade="all, delete-orphan",
        foreign_keys="EmailQueue.component_id",
    )

class Connection(Base):
    __tablename__ = "connections"
    
    id = Column(Integer, primary_key=True, index=True)
    from_component_id = Column(Integer, ForeignKey("components.id"))
    to_component_id = Column(Integer, ForeignKey("components.id"))
    condition = Column(String)  # For conditional connections like "if equals"
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Execution(Base):
    __tablename__ = "executions"
    
    id = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(Integer, ForeignKey("workflows.id"))
    status = Column(String, default="running")  # running, completed, failed
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))
    total_execution_time = Column(Integer)  # milliseconds
    input_data = Column(JSON)  # Input data from webhook or manual trigger
    results = Column(JSON)
    error_message = Column(Text)
    generation_reason = Column(Text, nullable=True)  # Why the sequence/run was generated or skipped
    total_prompt_tokens = Column(Integer, nullable=True)
    total_completion_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)
    rag_trace = Column(JSON, nullable=True)  # Filtered RAG events captured via trace_session for UI visibility

    workflow = relationship("Workflow", back_populates="executions")
    component_executions = relationship("ComponentExecution", back_populates="execution", cascade="all, delete-orphan")
    extracted_variables = relationship("ExtractedVariable", back_populates="execution", cascade="all, delete-orphan")
    email_queue_items = relationship("EmailQueue", back_populates="execution", cascade="all, delete-orphan")

class ComponentExecution(Base):
    __tablename__ = "component_executions"

    id = Column(Integer, primary_key=True, index=True)
    execution_id = Column(Integer, ForeignKey("executions.id"))
    component_id = Column(Integer, ForeignKey("components.id"))
    status = Column(String, default="pending")  # pending, running, completed, failed
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    execution_time = Column(Integer)  # milliseconds
    input_data = Column(JSON)
    output_data = Column(JSON)
    error_message = Column(Text)

    execution = relationship("Execution", back_populates="component_executions")
    component = relationship("Component", back_populates="component_executions")

class ExtractedVariable(Base):
    __tablename__ = "extracted_variables"
    
    id = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(Integer, ForeignKey("workflows.id"))
    execution_id = Column(Integer, ForeignKey("executions.id"))
    variable_name = Column(String, nullable=False)  # e.g., "Participants", "Budget"
    variable_key = Column(String, nullable=False)   # e.g., "participants", "budget"
    variable_value = Column(JSON, nullable=True)    # The extracted data
    data_type = Column(String, default="string")    # string, array, number, boolean
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    workflow = relationship("Workflow", back_populates="extracted_variables")
    execution = relationship("Execution", back_populates="extracted_variables")

class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    service_name = Column(String, nullable=False)  # fireflies, pipedrive, etc.
    encrypted_key = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_used_at = Column(DateTime(timezone=True))

    # Relationship to user
    user = relationship("User")


class Contact(Base):
    """
    Tracks contacts (email recipients) for activity history and conflict detection.
    """
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    email = Column(String, nullable=False, index=True)
    primary_email = Column(String, nullable=True, index=True)  # Canonical primary email
    name = Column(String)
    title = Column(String)  # e.g., "VP of Engineering"
    company = Column(String)
    contact_organization_id = Column(Integer, ForeignKey("contact_organizations.id"), nullable=True)
    avatar_initials = Column(String(2))  # e.g., "SC"

    # External CRM linkage
    external_person_id = Column(String, nullable=True)
    crm_provider = Column(String, nullable=True)  # e.g., "pipedrive"

    last_contacted_at = Column(DateTime(timezone=True))
    contact_count = Column(Integer, default=0)

    # Contact lifecycle
    status = Column(String, nullable=True)  # active, churned, prospect, etc.
    # Deterministic DNC flag consumed by _rag_presend_decision before any AI
    # call. Backfilled once from status='do_not_contact' in migration 043;
    # new writes should set this explicitly. Separate from status so ops can
    # change the lifecycle label without disturbing the gate.
    dnc_status = Column(Boolean, default=False, nullable=False, server_default="false", index=True)
    last_activity_at = Column(DateTime(timezone=True), nullable=True)
    last_activity_type = Column(String, nullable=True)
    last_activity_direction = Column(String, nullable=True)  # inbound, outbound
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    crm_synced_at = Column(DateTime(timezone=True))

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="contacts")
    organization = relationship("ContactOrganization", back_populates="contacts", foreign_keys=[contact_organization_id])
    activities = relationship("ContactActivity", back_populates="contact", cascade="all, delete-orphan", order_by="desc(ContactActivity.occurred_at)")
    email_queue_items = relationship("EmailQueue", back_populates="contact")
    contact_emails = relationship("ContactEmail", back_populates="contact", cascade="all, delete-orphan")
    deals = relationship("ContactDeal", back_populates="contact", cascade="all, delete-orphan")
    stats = relationship("ContactStats", back_populates="contact", uselist=False, cascade="all, delete-orphan")
    pulse = relationship("ContactPulse", back_populates="contact", uselist=False, cascade="all, delete-orphan")
    thread_digests = relationship("ThreadDigest", back_populates="contact", cascade="all, delete-orphan")
    meetings = relationship("MeetingHistory", back_populates="contact", cascade="all, delete-orphan")
    sequence_runs = relationship("SequenceRun", back_populates="contact", cascade="all, delete-orphan")


class ContactActivity(Base):
    """
    Tracks activity history for a contact (emails sent, opened, replies, meetings, etc.)
    """
    __tablename__ = "contact_activities"

    id = Column(Integer, primary_key=True, index=True)
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    email_queue_id = Column(Integer, ForeignKey("email_queue.id"), nullable=True)
    contact_organization_id = Column(Integer, ForeignKey("contact_organizations.id"), nullable=True)
    deal_id = Column(Integer, ForeignKey("contact_deals.id"), nullable=True)

    activity_type = Column(String, nullable=False)  # email_sent, email_opened, reply_received, meeting, bounced
    direction = Column(String, nullable=True)  # inbound, outbound
    source_type = Column(String, nullable=True)  # gmail, smtp, fireflies, manual, etc.
    source_id = Column(String, nullable=True)  # External ID in the source system
    thread_id = Column(String, nullable=True)  # Email thread ID
    subject = Column(String, nullable=True)
    summary = Column(Text, nullable=True)
    raw_content = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    activity_at = Column(DateTime(timezone=True), nullable=True)  # When the activity occurred externally

    title = Column(String)  # Display title
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    is_new = Column(Boolean, default=True)  # For "NEW" badge
    extra_data = Column(JSON)  # Extra data (e.g., email subject, meeting title)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    contact = relationship("Contact", back_populates="activities")
    user = relationship("User")
    email_queue = relationship("EmailQueue", back_populates="activities")
    deal = relationship("ContactDeal", foreign_keys=[deal_id])


class Webhook(Base):
    __tablename__ = "webhooks"

    id = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(Integer, ForeignKey("workflows.id"))
    component_id = Column(Integer, ForeignKey("components.id"))
    name = Column(String, nullable=False)
    description = Column(Text)
    webhook_url = Column(String)
    webhook_token = Column(String, unique=True, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    workflow = relationship("Workflow", back_populates="webhooks")
    component = relationship("Component", back_populates="webhooks")

class EmailQueue(Base):
    __tablename__ = "email_queue"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    workflow_id = Column(Integer, ForeignKey("workflows.id"))
    execution_id = Column(Integer, ForeignKey("executions.id"))
    component_id = Column(Integer, ForeignKey("components.id"))

    # Contact linking
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=True)

    # Email details
    recipient_email = Column(String, nullable=False)
    recipient_name = Column(String)
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    cc = Column(JSON)  # List of CC email addresses
    bcc = Column(JSON)  # List of BCC email addresses

    # Version tracking for edits
    original_subject = Column(String)  # Original AI-generated subject
    original_body = Column(Text)  # Original AI-generated body
    edit_source = Column(String)  # 'ai', 'manual', or null
    ai_edit_prompt = Column(Text)  # The prompt used for AI edit

    # Approval workflow
    approval_status = Column(String, default="pending")  # pending, approved, skipped
    approved_at = Column(DateTime(timezone=True))

    # Sequence tracking (for "Email X of Y" display)
    sequence_config_id = Column(Integer, ForeignKey("email_sequence_configs.id"), nullable=True)
    sequence_email_id = Column(Integer, ForeignKey("sequence_emails.id"), nullable=True)
    sequence_position = Column(Integer)  # Position in sequence (1, 2, 3...)
    sequence_total = Column(Integer)  # Total emails in sequence

    # Scheduling
    scheduled_at = Column(DateTime(timezone=True), nullable=False)  # When to send
    sent_at = Column(DateTime(timezone=True))  # When actually sent

    # Status tracking
    status = Column(String, default="pending")  # pending, sent, failed, cancelled
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)

    # Pre-send check (re-evaluate a CRM condition before sending)
    pre_send_check_field = Column(String, nullable=True)     # CRM field name: stage, status, value, etc.
    pre_send_check_operator = Column(String, nullable=True)  # equals, not_equals, contains, etc.
    pre_send_check_value = Column(String, nullable=True)     # Expected value
    pre_send_check_context = Column(JSON, nullable=True)     # {"participant_emails": [...]}

    # Multi-group pre-send check (new format — takes precedence over flat fields above)
    pre_send_check_config = Column(JSON, nullable=True)     # {"condition_groups": [...], "group_logic": "AND"|"OR", "data_source": "pipedrive", "context": {...}}

    # AI reasoning
    timing_reason = Column(Text, nullable=True)      # Why AI picked this send time
    generation_reason = Column(Text, nullable=True)   # Why email was generated this way

    # Contact system linkage
    thread_id = Column(String, nullable=True)  # Email thread ID for grouping
    message_id_header = Column(String, nullable=True)  # RFC 2822 Message-ID for reply threading
    thread_parent_component_id = Column(Integer, ForeignKey("components.id", ondelete="SET NULL"), nullable=True)
    thread_parent_queue_id = Column(Integer, ForeignKey("email_queue.id", ondelete="SET NULL"), nullable=True)
    thread_fallback_reason = Column(String, nullable=True)
    sender_provider = Column(String, nullable=True)  # gmail, outlook, smtp
    sender_account_email = Column(String, nullable=True)
    deal_id = Column(Integer, ForeignKey("contact_deals.id"), nullable=True)
    sequence_run_id = Column(Integer, ForeignKey("sequence_runs.id"), nullable=True)

    # RAG tracking: chunk ids retrieved during generation (for diversity penalty on later emails in the sequence)
    used_chunk_ids = Column(JSON, nullable=True)
    # Org-level warning surfaced from pre-send snapshot (non-DNC signals from other contacts at same org)
    org_warning = Column(Text, nullable=True)

    # Fresh-check audit trail (migration 043). Written by the DNC short-
    # circuit in _rag_presend_decision and, eventually, the broader
    # fresh_check pipeline in T2/T3.
    #   action — "cancel_sequence" | "skip_email" | "resume_after" | ...
    #   rule_triggered — short id of the rule that fired ("dnc", "reply", ...)
    #   reason — human text shown in the UI
    #   resume_date — for actions that pause rather than cancel
    fresh_check_action = Column(String(32), nullable=True)
    fresh_check_rule_triggered = Column(String(64), nullable=True)
    fresh_check_reason = Column(Text, nullable=True)
    fresh_check_resume_date = Column(Date, nullable=True)
    # RAG pre-send defer counter. Bumped when the Sonnet STOP/CONTINUE call errors or
    # returns a malformed response; reset on a clean CONTINUE/HOLD. After
    # rag.presend_defer_max defers we fall back to sending (see migration 040).
    rag_defer_count = Column(Integer, default=0, nullable=False, server_default="0")

    # --- Anthropic Batch API pipeline (see migration 039) ---
    # batch_stage is the AI-generation state machine, orthogonal to `status` (SMTP send state).
    # Values: null | pending_submit | submitting | submitted | completed | failed
    batch_stage = Column(String(32), nullable=True, index=True)
    # sha256 of (id, prompt_hash), UNIQUE. DB-level guard against double submit.
    idempotency_key = Column(String(64), nullable=True, unique=True)
    # sha256 of the prompt body; stable across restarts so idempotency_key is stable.
    prompt_hash = Column(String(64), nullable=True)
    # Echoed back by Anthropic on each result; the authoritative reconciliation key.
    custom_id = Column(String(128), nullable=True, index=True)
    # Anthropic-assigned batch id (written in phase-2 commit, after the API accepts the batch).
    batch_id = Column(String(255), nullable=True, index=True)
    # Mirrors Anthropic batch state: in_progress, ended, canceled, expired.
    batch_status = Column(String(32), nullable=True, index=True)
    # Phase-2 commit timestamp.
    batch_submitted_at = Column(DateTime(timezone=True), nullable=True)
    # Persisted request body so reconciliation/replay does not need to rebuild the prompt.
    batch_request_payload = Column(JSON, nullable=True)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User")
    workflow = relationship("Workflow", back_populates="email_queue")
    execution = relationship("Execution", back_populates="email_queue_items")
    component = relationship(
        "Component",
        back_populates="email_queue_items",
        foreign_keys=[component_id],
    )
    contact = relationship("Contact", back_populates="email_queue_items")
    activities = relationship("ContactActivity", back_populates="email_queue")
    sequence_config = relationship("EmailSequenceConfig")
    sequence_email = relationship("SequenceEmail")
    contact_deal = relationship("ContactDeal", foreign_keys="EmailQueue.deal_id")
    sequence_run = relationship("SequenceRun", foreign_keys="EmailQueue.sequence_run_id")
    thread_parent_component = relationship("Component", foreign_keys=[thread_parent_component_id])
    thread_parent_queue = relationship("EmailQueue", foreign_keys=[thread_parent_queue_id], remote_side=[id])


class EmailSequenceConfig(Base):
    """
    Configuration for an email sequence attached to a workflow.
    Each workflow can have one email sequence configuration.
    """
    __tablename__ = "email_sequence_configs"

    id = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(Integer, ForeignKey("workflows.id"), unique=True)

    # Sequence settings
    name = Column(String, nullable=False)
    is_enabled = Column(Boolean, default=True)

    # AI optimization settings
    ai_optimize_timing = Column(Boolean, default=False)  # Let AI decide optimal timing
    ai_optimization_prompt = Column(Text)  # Custom prompt for AI timing decisions

    # Global delivery settings
    send_method = Column(String)  # smtp, pipedrive
    timezone = Column(String)

    # Business hours (when emails can be sent)
    business_hours_only = Column(Boolean, default=True)
    business_hours_start = Column(String)  # HH:MM format
    business_hours_end = Column(String)
    business_days = Column(JSON)  # ["monday", "tuesday", ...]

    # Skip conditions (JSON array of conditions)
    skip_conditions = Column(JSON)
    # Example: [{"type": "deal_stage", "operator": "equals", "value": "closed_won"}]

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    workflow = relationship("Workflow", back_populates="email_sequence_config")
    emails = relationship("SequenceEmail", back_populates="sequence_config", cascade="all, delete-orphan", order_by="SequenceEmail.order")


class SequenceEmail(Base):
    """
    Individual email within a sequence.
    Supports both relative timing (delay from previous) and specific day/time.
    """
    __tablename__ = "sequence_emails"

    id = Column(Integer, primary_key=True, index=True)
    sequence_config_id = Column(Integer, ForeignKey("email_sequence_configs.id"))

    # Email order in sequence (1, 2, 3...)
    order = Column(Integer, nullable=False, default=1)

    # Email content
    name = Column(String)  # Display name like "Initial Follow-up"
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=False)

    # Timing mode: "relative" (delay from previous) or "specific" (specific day/time)
    timing_mode = Column(String)

    # Relative timing (when timing_mode = "relative")
    delay_value = Column(Integer)  # Number value
    delay_unit = Column(String)  # minutes, hours, days, weeks

    # Specific timing (when timing_mode = "specific")
    specific_day = Column(String)  # monday, tuesday, etc. or "same_day", "next_day"
    specific_time = Column(String)  # HH:MM format

    # AI timing override
    ai_decides_timing = Column(Boolean, default=False)  # Let AI decide this email's timing
    ai_timing_context = Column(Text)  # Context for AI timing decision

    # Email-specific settings
    is_enabled = Column(Boolean, default=True)

    # Generation settings
    generation_prompt = Column(Text)  # Custom prompt for generating this email
    use_variables = Column(JSON)  # Variables to include: ["participant_name", "company", "pain_points"]

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    sequence_config = relationship("EmailSequenceConfig", back_populates="emails")


class ScheduledSequenceEmail(Base):
    """
    Tracks scheduled/sent emails from sequences.
    Links to the existing EmailQueue for actual sending.
    """
    __tablename__ = "scheduled_sequence_emails"

    id = Column(Integer, primary_key=True, index=True)
    sequence_config_id = Column(Integer, ForeignKey("email_sequence_configs.id"))
    sequence_email_id = Column(Integer, ForeignKey("sequence_emails.id"))
    execution_id = Column(Integer, ForeignKey("executions.id"))
    email_queue_id = Column(Integer, ForeignKey("email_queue.id"))  # Links to actual email

    # Recipient info (denormalized for easy querying)
    recipient_email = Column(String, nullable=False)
    recipient_name = Column(String)

    # Status tracking
    status = Column(String, default="scheduled")  # scheduled, sent, skipped, failed, cancelled
    skip_reason = Column(Text)  # Why was it skipped (if applicable)

    # Timing info
    scheduled_for = Column(DateTime(timezone=True))
    sent_at = Column(DateTime(timezone=True))

    # AI timing decision (if applicable)
    ai_decided_timing = Column(Boolean, default=False)
    ai_timing_reasoning = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class AiUsageLog(Base):
    """Tracks every AI API call for accurate token usage reporting."""
    __tablename__ = "ai_usage_log"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    source = Column(String, nullable=False, index=True)  # execution, component_test, email_edit, pre_send_check, sequence_generation
    execution_id = Column(Integer, ForeignKey("executions.id"), nullable=True)
    component_id = Column(Integer, ForeignKey("components.id"), nullable=True)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    cache_creation_input_tokens = Column(Integer, default=0, server_default="0")  # Anthropic prompt cache: tokens written to cache
    cache_read_input_tokens = Column(Integer, default=0, server_default="0")  # Anthropic prompt cache: tokens read from cache
    ai_model = Column(String, nullable=True)
    cost = Column(Float, default=0)  # Actual USD cost to us (with Anthropic cache tier pricing)
    billable_cost = Column(Float, default=0, server_default="0")  # Baseline USD cost we charge users (as if no caching)
    task = Column(String, nullable=True)  # What the AI call did: "extraction", "summary", "email_generation", etc.
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User")
    execution = relationship("Execution")
    component = relationship("Component")


class AiModel(Base):
    """Admin-configurable AI models with pricing."""
    __tablename__ = "ai_models"

    id = Column(Integer, primary_key=True, index=True)
    model_id = Column(String, unique=True, nullable=False)  # API identifier e.g. "claude-sonnet-4-5-20250929"
    display_name = Column(String, nullable=False)  # Human-readable e.g. "Claude Sonnet 4.5"
    input_cost_per_million = Column(Float, nullable=False)  # $/M input tokens
    output_cost_per_million = Column(Float, nullable=False)  # $/M output tokens
    is_active = Column(Boolean, default=False)  # Only one active at a time
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# --- Contact System V2 Models ---

class ContactOrganization(Base):
    """
    Company/organization entity for grouping contacts and deals.
    """
    __tablename__ = "contact_organizations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    domain = Column(String, nullable=True, index=True)
    external_org_id = Column(String, nullable=True)  # ID in external CRM
    crm_provider = Column(String, nullable=True)  # e.g., "pipedrive"
    do_not_contact_propagation = Column(Boolean, default=True)  # Propagate DNC flag to all contacts
    # Org-level deterministic DNC flag. Seeded false in migration 043 —
    # populating it is T3's job. When true, _rag_presend_decision short-
    # circuits every email to any contact at this org before any AI call.
    dnc_status = Column(Boolean, default=False, nullable=False, server_default="false", index=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    dnc = Column(Boolean, default=False, nullable=False)
    dnc_set_at = Column(DateTime(timezone=True), nullable=True)
    dnc_set_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    dnc_propagation_status = Column(String, nullable=True)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    contacts = relationship("Contact", back_populates="organization", foreign_keys="Contact.contact_organization_id")
    deals = relationship("ContactDeal", back_populates="organization", foreign_keys="ContactDeal.contact_organization_id")
    


class ContactEmail(Base):
    """
    Multiple email addresses per contact, one marked as primary.
    """
    __tablename__ = "contact_emails"

    id = Column(Integer, primary_key=True, index=True)
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=False, index=True)
    email = Column(String, nullable=False, index=True)
    is_primary = Column(Boolean, default=False)
    verified = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    contact = relationship("Contact", back_populates="contact_emails")


class ContactDeal(Base):
    """
    CRM deal linked to a contact.
    """
    __tablename__ = "contact_deals"

    id = Column(Integer, primary_key=True, index=True)
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    contact_organization_id = Column(Integer, ForeignKey("contact_organizations.id"), nullable=True)
    external_deal_id = Column(String, nullable=True)  # ID in external CRM
    crm_provider = Column(String, nullable=True)  # e.g., "pipedrive"
    title = Column(String, nullable=True)
    status = Column(String, default="open")  # open, won, lost
    stage_name = Column(String, nullable=True)
    value = Column(Float, nullable=True)
    expected_close_date = Column(DateTime(timezone=True), nullable=True)
    currency = Column(String, default="USD")
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    contact = relationship("Contact", back_populates="deals")
    organization = relationship("ContactOrganization", back_populates="deals", foreign_keys=[contact_organization_id])
    user = relationship("User")


class ContactStats(Base):
    """
    Computed statistics for a contact (one row per contact).
    """
    __tablename__ = "contact_stats"

    id = Column(Integer, primary_key=True, index=True)
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=False, unique=True, index=True)
    emails_sent = Column(Integer, default=0)
    emails_received = Column(Integer, default=0)
    reply_rate = Column(Float, default=0.0)
    meetings_count = Column(Integer, default=0)
    active_sequences = Column(Integer, default=0)
    open_deals = Column(Integer, default=0)
    total_deal_value = Column(Float, default=0.0)
    last_computed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    contact = relationship("Contact", back_populates="stats", uselist=False)


class ContactPulse(Base):
    """
    AI-generated intelligence summary for a contact (one row per contact).
    """
    __tablename__ = "contact_pulse"

    id = Column(Integer, primary_key=True, index=True)
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=False, unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    summary = Column(Text, nullable=True)
    sentiment = Column(String, nullable=True)  # positive, neutral, negative
    engagement_level = Column(String, nullable=True)  # high, medium, low
    intent = Column(String, nullable=True)  # buying, evaluating, churning, etc.
    recommended_action = Column(String, nullable=True)
    key_topics = Column(JSON, nullable=True)
    key_objections = Column(JSON, nullable=True)
    last_meeting_date = Column(DateTime(timezone=True), nullable=True)
    generated_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    contact = relationship("Contact", back_populates="pulse", uselist=False)
    user = relationship("User")


class ThreadDigest(Base):
    """
    Summarized digest of an email thread for a contact.
    """
    __tablename__ = "thread_digests"

    id = Column(Integer, primary_key=True, index=True)
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    thread_id = Column(String, nullable=False, index=True)
    subject = Column(String, nullable=True)
    summary = Column(Text, nullable=True)
    sentiment = Column(String, nullable=True)
    thread_status = Column(String, nullable=True)  # open, resolved, awaiting_reply, etc.
    message_count = Column(Integer, default=0)
    last_message_at = Column(DateTime(timezone=True), nullable=True)
    participants = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    contact = relationship("Contact", back_populates="thread_digests")
    user = relationship("User")


class MeetingHistory(Base):
    """
    Meeting history linked to a contact (sourced from Fireflies or other providers).
    """
    __tablename__ = "meeting_history"
    __table_args__ = (
        UniqueConstraint("contact_id", "external_meeting_id", name="uq_meeting_contact_external"),
    )

    id = Column(Integer, primary_key=True, index=True)
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    external_meeting_id = Column(String, nullable=True)  # ID in source system (e.g., Fireflies)
    source = Column(String, nullable=True)  # fireflies, google_meet, zoom, manual, etc.
    meeting_date = Column(DateTime(timezone=True), nullable=True)
    summary = Column(Text, nullable=True)
    key_points = Column(JSON, nullable=True)
    objections = Column(JSON, nullable=True)
    buying_signals = Column(JSON, nullable=True)
    deal_stage_at_time = Column(String, nullable=True)
    duration_minutes = Column(Integer, nullable=True)
    participants = Column(JSON, nullable=True)
    raw_transcript_url = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    contact = relationship("Contact", back_populates="meetings")
    user = relationship("User")


class SequenceRun(Base):
    """
    Tracks an active sequence run for a contact.
    """
    __tablename__ = "sequence_runs"

    id = Column(Integer, primary_key=True, index=True)
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    sequence_config_id = Column(Integer, ForeignKey("email_sequence_configs.id"), nullable=True, index=True)
    status = Column(String, default="active")  # active, completed, paused, cancelled
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    current_step = Column(Integer, default=0)
    total_steps = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    contact = relationship("Contact", back_populates="sequence_runs")


class Resource(Base):
    __tablename__ = "resources"
    __table_args__ = (
        UniqueConstraint("account_id", "type", "label", name="uq_resource_account_type_label"),
    )

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String(10), nullable=False)  # 'link' or 'file'
    label = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)
    url = Column(Text, nullable=True)
    file_path = Column(Text, nullable=True)
    file_size_bytes = Column(Integer, nullable=True)
    file_original_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    account = relationship("Account", backref="resources")


class ContentEmbedding(Base):
    """
    Stores chunked and embedded text for RAG retrieval.
    Sources: resources, text_gen_output, transcript_chunk, activity, generated_email.
    """
    __tablename__ = "content_embeddings"
    __table_args__ = (
        UniqueConstraint("source_type", "source_id", "chunk_index", name="uq_embedding_source_chunk"),
    )

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type = Column(String(50), nullable=False)  # resource, text_gen_output, transcript_chunk, activity, generated_email
    source_id = Column(String(255), nullable=False)  # e.g. resource:42, execution:99
    contact_id = Column(Integer, ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True, index=True)
    org_id = Column(Integer, ForeignKey("contact_organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    chunk_text = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False, server_default="0")
    embedding = Column(Vector(1536))
    chunk_metadata = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    account = relationship("Account")
    contact = relationship("Contact")
    organization = relationship("ContactOrganization")


class RagRetrievalLog(Base):
    """Per-call latency record for RAG retrievals, used by the observability dashboard."""
    __tablename__ = "rag_retrieval_log"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=True, index=True)
    latency_ms = Column(Integer, nullable=False)
    result_count = Column(Integer, nullable=False, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
