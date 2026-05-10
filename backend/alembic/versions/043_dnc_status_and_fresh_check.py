"""Add dnc_status + fresh_check columns for T1 (#174).

Adds the deterministic DNC short-circuit surface that _rag_presend_decision
reads before any AI call. Scope is intentionally T1 only:

  * contacts.dnc_status (bool, default false). Backfilled from the existing
    contacts.status='do_not_contact' signal so customers who already flagged
    recipients keep their protection on day 1 — a 1:1 semantic mapping, no
    inference risk.
  * contact_organizations.dnc_status (bool, default false). Seeded false
    everywhere rather than inferred from do_not_contact_propagation, which
    defaults True on every org and does NOT mean "this org is DNC" (it means
    "when a contact goes DNC, propagate to siblings"). Populating this
    column is T3's job — this migration just makes the slot exist.
  * email_queue.fresh_check_action / _rule_triggered / _reason /
    _resume_date. Write target for the fresh_check pipeline; read by admin
    UI and retry logic. Nullable so rows predating this migration stay
    untouched.

Revision ID: 043_dnc_status_and_fresh_check
Revises: 042_content_embeddings_acct_idx
"""
from alembic import op
import sqlalchemy as sa


revision = "043_dnc_status_and_fresh_check"
down_revision = "042_content_embeddings_acct_idx"


def upgrade():
    # --- Contact: dnc_status, backfilled from status='do_not_contact' ---
    op.add_column(
        "contacts",
        sa.Column(
            "dnc_status",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    # 1:1 backfill from the existing signal. Covers customers who already
    # flagged recipients via the contact status so they keep DNC protection
    # the moment the read path goes live.
    op.execute(
        "UPDATE contacts SET dnc_status = true "
        "WHERE status = 'do_not_contact'"
    )
    op.create_index(
        "ix_contacts_dnc_status",
        "contacts",
        ["dnc_status"],
    )

    # --- ContactOrganization: dnc_status, seeded false ---
    op.add_column(
        "contact_organizations",
        sa.Column(
            "dnc_status",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_index(
        "ix_contact_organizations_dnc_status",
        "contact_organizations",
        ["dnc_status"],
    )

    # --- EmailQueue: fresh_check audit trail ---
    op.add_column(
        "email_queue",
        sa.Column("fresh_check_action", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "email_queue",
        sa.Column("fresh_check_rule_triggered", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "email_queue",
        sa.Column("fresh_check_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "email_queue",
        sa.Column("fresh_check_resume_date", sa.Date(), nullable=True),
    )


def downgrade():
    op.drop_column("email_queue", "fresh_check_resume_date")
    op.drop_column("email_queue", "fresh_check_reason")
    op.drop_column("email_queue", "fresh_check_rule_triggered")
    op.drop_column("email_queue", "fresh_check_action")

    op.drop_index("ix_contact_organizations_dnc_status", table_name="contact_organizations")
    op.drop_column("contact_organizations", "dnc_status")

    op.drop_index("ix_contacts_dnc_status", table_name="contacts")
    op.drop_column("contacts", "dnc_status")
