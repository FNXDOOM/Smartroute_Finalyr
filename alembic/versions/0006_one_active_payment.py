"""At most one active payment per ride: DB-level backstop for the create-order race."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


revision = "0006_one_active_payment"
down_revision = "0005_carpool_state"
branch_labels = None
depends_on = None

_INDEX = "uq_payments_one_active_per_ride"
_WHERE = "ride_request_id IS NOT NULL AND status IN ('created', 'pending', 'paid')"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "payments" not in set(inspector.get_table_names()):
        return
    if _INDEX in {ix["name"] for ix in inspector.get_indexes("payments")}:
        return
    # Retire older duplicate active payments so the unique index can be built.
    bind.execute(text(
        "UPDATE payments SET status = 'failed', failure_reason = 'superseded_duplicate_active' "
        "WHERE ride_request_id IS NOT NULL AND status IN ('created', 'pending', 'paid') "
        "AND id NOT IN (SELECT MAX(id) FROM payments "
        "WHERE ride_request_id IS NOT NULL AND status IN ('created', 'pending', 'paid') "
        "GROUP BY ride_request_id)"
    ))
    op.create_index(
        _INDEX,
        "payments",
        ["ride_request_id"],
        unique=True,
        postgresql_where=sa.text(_WHERE),
        sqlite_where=sa.text(_WHERE),
    )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if "payments" not in set(inspector.get_table_names()):
        return
    if _INDEX in {ix["name"] for ix in inspector.get_indexes("payments")}:
        op.drop_index(_INDEX, table_name="payments")