"""Performance indexes for clustering, demand, notifications and tracking."""

from alembic import op

revision = "0007_performance_indexes"
down_revision = "0006_one_active_payment"
branch_labels = None
depends_on = None

_INDEXES = (
    ("ix_ride_requests_ride_mode_status", "ride_requests", ["ride_mode", "status"]),
    ("ix_ride_requests_h3_index_status", "ride_requests", ["h3_index", "status"]),
    ("ix_ride_requests_status_request_time", "ride_requests", ["status", "request_time"]),
    ("ix_ride_requests_cluster_id", "ride_requests", ["cluster_id"]),
    ("ix_ride_requests_virtual_stop_id", "ride_requests", ["virtual_stop_id"]),
    ("ix_demand_snapshots_created_at", "demand_snapshots", ["created_at"]),
    ("ix_demand_snapshots_h3_index_created_at", "demand_snapshots", ["h3_index", "created_at"]),
    ("ix_notifications_user_id_is_read_created_at", "notifications", ["user_id", "is_read", "created_at"]),
    ("ix_tracking_events_created_at", "tracking_events", ["created_at"]),
    ("ix_tracking_events_vehicle_id_created_at", "tracking_events", ["vehicle_id", "created_at"]),
)


def upgrade() -> None:
    for name, table, columns in _INDEXES:
        op.create_index(name, table, columns, unique=False, if_not_exists=True)


def downgrade() -> None:
    for name, table, _columns in reversed(_INDEXES):
        op.drop_index(name, table_name=table, if_exists=True)
