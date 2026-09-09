"""Create the initial SmartRouteAI schema."""

from alembic import op
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from database import Base
import models  # noqa: F401

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the initial database schema migration."""
    # Versioned baseline; startup never alters tables
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    """Revert the initial database schema migration."""
    Base.metadata.drop_all(bind=op.get_bind())
