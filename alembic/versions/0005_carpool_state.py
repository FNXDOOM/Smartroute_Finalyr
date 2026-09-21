"""Add carpool_status to ride_requests: per-rider carpool lifecycle stage."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0005_carpool_state"
down_revision = "0004_ride_sharing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "ride_requests" not in set(inspector.get_table_names()):
        return
    columns = {column["name"] for column in inspector.get_columns("ride_requests")}
    if "carpool_status" not in columns:
        op.add_column(
            "ride_requests",
            sa.Column("carpool_status", sa.String(), nullable=True),
        )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if "ride_requests" not in set(inspector.get_table_names()):
        return
    columns = {column["name"] for column in inspector.get_columns("ride_requests")}
    if "carpool_status" in columns:
        op.drop_column("ride_requests", "carpool_status")
