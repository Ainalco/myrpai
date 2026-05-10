# ============================================================================
# EMAIL SEQUENCE CONFIGURATION MODELS
# Add this to the END of your backend/models.py file
# ============================================================================

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


# ============================================================================
# ALSO ADD THIS RELATIONSHIP TO YOUR EXISTING Workflow MODEL:
# ============================================================================
# In the Workflow class (around line 49), add this line after email_queue:
#
#     email_sequence_config = relationship("EmailSequenceConfig", back_populates="workflow", uselist=False, cascade="all, delete-orphan")
#
# ============================================================================
