"""usuarios e inspiraciones

Revision ID: 0001
Revises:
Create Date: 2026-10-10
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("name", sa.String(30), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("email", name="users_email_key"),
    )
    op.create_table(
        "inspirations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("keyword", sa.String(100), nullable=False),
        sa.Column("pexels_id", sa.BigInteger(), nullable=False),
        sa.Column("alt", sa.String(500), nullable=False),
        sa.Column("photographer", sa.String(200), nullable=False),
        sa.Column("photographer_url", sa.String(2048), nullable=False),
        sa.Column("link", sa.String(2048), nullable=False),
        sa.Column("image", sa.String(2048), nullable=False),
        sa.Column(
            "owner_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("owner_id", "pexels_id", name="uq_inspirations_owner_pexels_id"),
    )
    op.create_index("ix_inspirations_owner_id", "inspirations", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_inspirations_owner_id", table_name="inspirations")
    op.drop_table("inspirations")
    op.drop_table("users")
