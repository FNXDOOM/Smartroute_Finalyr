"""Separate live rides from presentation demo runs."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0002_demo_scope"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    for table in ("ride_requests", "cluster_runs", "route_plans", "virtual_stops", "vehicles"):
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "ride_mode" not in columns and "mode" in columns:
            op.alter_column(table, "mode", new_column_name="ride_mode")
            columns.remove("mode")
            columns.add("ride_mode")
        if "ride_mode" not in columns:
            op.add_column(table, sa.Column("ride_mode", sa.String(), nullable=False, server_default="live"))
        if "demo_run_id" not in columns:
            op.add_column(table, sa.Column("demo_run_id", sa.String(), nullable=True))
        indexes = {index["name"] for index in inspector.get_indexes(table)}
        if f"ix_{table}_ride_mode" not in indexes:
            op.create_index(f"ix_{table}_ride_mode", table, ["ride_mode"])
        if f"ix_{table}_demo_run_id" not in indexes:
            op.create_index(f"ix_{table}_demo_run_id", table, ["demo_run_id"])


def downgrade() -> None:
    for table in ("vehicles", "virtual_stops", "route_plans", "cluster_runs", "ride_requests"):
        op.drop_index(f"ix_{table}_demo_run_id", table_name=table)
        op.drop_index(f"ix_{table}_ride_mode", table_name=table)
        op.drop_column(table, "demo_run_id")
        op.drop_column(table, "ride_mode")
