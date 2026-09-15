"""Add payments table for Razorpay checkout."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0003_payments"
down_revision = "0002_demo_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "payments" in tables:
        return
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("ride_request_id", sa.Integer(), sa.ForeignKey("ride_requests.id"), nullable=True),
        sa.Column("purpose", sa.String(), nullable=False, server_default="ride_fare"),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(), nullable=False, server_default="INR"),
        sa.Column("status", sa.String(), nullable=False, server_default="created"),
        sa.Column("razorpay_order_id", sa.String(), nullable=True),
        sa.Column("razorpay_payment_id", sa.String(), nullable=True),
        sa.Column("verified", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_reason", sa.String(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_payments_id", "payments", ["id"])
    op.create_index("ix_payments_user_id", "payments", ["user_id"])
    op.create_index("ix_payments_ride_request_id", "payments", ["ride_request_id"])
    op.create_index("ix_payments_status", "payments", ["status"])
    op.create_index("ix_payments_razorpay_order_id", "payments", ["razorpay_order_id"])


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if "payments" not in set(inspector.get_table_names()):
        return
    op.drop_index("ix_payments_razorpay_order_id", table_name="payments")
    op.drop_index("ix_payments_status", table_name="payments")
    op.drop_index("ix_payments_ride_request_id", table_name="payments")
    op.drop_index("ix_payments_user_id", table_name="payments")
    op.drop_index("ix_payments_id", table_name="payments")
    op.drop_table("payments")
