"""Add is_shared to ride_requests: carpool vs private ride."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0004_ride_sharing"
down_revision = "0003_payments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "ride_requests" not in set(inspector.get_table_names()):
        return
    columns = {column["name"] for column in inspector.get_columns("ride_requests")}
    if "is_shared" not in columns:
        op.add_column(
            "ride_requests",
            sa.Column("is_shared", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
    indexes = {index["name"] for index in inspector.get_indexes("ride_requests")}
    if "ix_ride_requests_is_shared" not in indexes:
        op.create_index("ix_ride_requests_is_shared", "ride_requests", ["is_shared"])


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if "ride_requests" not in set(inspector.get_table_names()):
        return
    indexes = {index["name"] for index in inspector.get_indexes("ride_requests")}
    if "ix_ride_requests_is_shared" in indexes:
        op.drop_index("ix_ride_requests_is_shared", table_name="ride_requests")
    columns = {column["name"] for column in inspector.get_columns("ride_requests")}
    if "is_shared" in columns:
        op.drop_column("ride_requests", "is_shared")
