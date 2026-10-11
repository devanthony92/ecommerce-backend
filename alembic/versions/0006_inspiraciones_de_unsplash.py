"""inspiraciones de unsplash: pexels_id (número) pasa a photo_id (texto)

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_inspirations_owner_pexels_id", "inspirations", type_="unique")
    op.alter_column("inspirations", "pexels_id", new_column_name="photo_id")
    op.alter_column(
        "inspirations",
        "photo_id",
        type_=sa.String(64),
        existing_type=sa.BigInteger(),
        existing_nullable=False,
        postgresql_using="photo_id::text",
    )
    op.create_unique_constraint(
        "uq_inspirations_owner_photo_id", "inspirations", ["owner_id", "photo_id"]
    )


def downgrade() -> None:
    # Solo funciona si todos los ids son numéricos (como los de Pexels).
    op.drop_constraint("uq_inspirations_owner_photo_id", "inspirations", type_="unique")
    op.alter_column(
        "inspirations",
        "photo_id",
        type_=sa.BigInteger(),
        existing_type=sa.String(64),
        existing_nullable=False,
        postgresql_using="photo_id::bigint",
    )
    op.alter_column("inspirations", "photo_id", new_column_name="pexels_id")
    op.create_unique_constraint(
        "uq_inspirations_owner_pexels_id", "inspirations", ["owner_id", "pexels_id"]
    )
