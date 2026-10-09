"""Persist retry backoff independently of broker delivery."""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("task", sa.Column("available_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("task", "available_at")
