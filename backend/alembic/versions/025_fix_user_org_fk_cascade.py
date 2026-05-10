"""Fix User.org_id FK from CASCADE to SET NULL for soft-delete safety

Revision ID: 025_fix_user_org_fk_cascade
Revises: 024_add_task_to_ai_usage_log
"""
from alembic import op
from sqlalchemy import text

revision = "025_fix_user_org_fk_cascade"
down_revision = "024_add_task_to_ai_usage_log"


def _get_fk_constraint_name(connection, table, column):
    """Look up the actual FK constraint name from PostgreSQL catalogs."""
    result = connection.execute(text("""
        SELECT con.conname
        FROM pg_constraint con
        JOIN pg_attribute att ON att.attnum = ANY(con.conkey)
            AND att.attrelid = con.conrelid
        WHERE con.conrelid = CAST(:table AS regclass)
            AND att.attname = :column
            AND con.contype = 'f'
        LIMIT 1
    """), {"table": table, "column": column})
    row = result.fetchone()
    return row[0] if row else None


def upgrade():
    conn = op.get_bind()
    fk_name = _get_fk_constraint_name(conn, "users", "org_id")
    if fk_name:
        op.drop_constraint(fk_name, "users", type_="foreignkey")
    op.create_foreign_key(
        "users_org_id_fkey",
        "users",
        "organizations",
        ["org_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade():
    conn = op.get_bind()
    fk_name = _get_fk_constraint_name(conn, "users", "org_id")
    if fk_name:
        op.drop_constraint(fk_name, "users", type_="foreignkey")
    op.create_foreign_key(
        "users_org_id_fkey",
        "users",
        "organizations",
        ["org_id"],
        ["id"],
        ondelete="CASCADE",
    )
