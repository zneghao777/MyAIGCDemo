"""Add opt-in creative drafts, immutable revisions and candidates without rewriting old assets."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    j = sa.JSON().with_variant(JSONB, "postgresql")
    for table in ("project", "scene", "character"):
        op.add_column(table, sa.Column("creative", j, nullable=True))
    for table in ("creative_revision", "creative_candidate"):
        extra = (
            []
            if table.endswith("revision")
            else [
                sa.Column("fingerprint", sa.String(), nullable=False),
                sa.Column("task_id", sa.String(36), sa.ForeignKey("task.id", ondelete="SET NULL")),
            ]
        )
        op.create_table(
            table,
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "project_id", sa.String(36), sa.ForeignKey("project.id", ondelete="CASCADE"), nullable=False
            ),
            sa.Column("entity_id", sa.String(36), nullable=False),
            sa.Column("kind", sa.String(), nullable=False),
            sa.Column("data", j, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            *extra,
        )
        for key in ("project_id", "entity_id"):
            op.create_index(f"ix_{table}_{key}", table, [key])
    op.create_table(
        "library_character",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("data", j, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    for table in ("library_character", "creative_candidate", "creative_revision"):
        op.drop_table(table)
    for table in ("character", "scene", "project"):
        op.drop_column(table, "creative")
