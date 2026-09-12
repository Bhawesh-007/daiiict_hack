"""0005_calculations: calculation_runs, calculation_lines

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── calculation_runs ─────────────────────────────────────────────────
    op.create_table(
        "calculation_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("assessment_id", UUID(as_uuid=True), sa.ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("methodology_version", sa.String(50), nullable=True),
        sa.Column("factor_set_version", sa.String(50), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="RUNNING"),
        sa.Column("total_emissions_kgco2e", sa.Numeric(28, 8), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('RUNNING','COMPLETED','FAILED')", name="ck_calc_run_status"),
    )

    # ── calculation_lines ────────────────────────────────────────────────
    op.create_table(
        "calculation_lines",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("calculation_run_id", UUID(as_uuid=True),
                  sa.ForeignKey("calculation_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_inventory_item_id", UUID(as_uuid=True),
                  sa.ForeignKey("source_inventory_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("activity_record_id", UUID(as_uuid=True),
                  sa.ForeignKey("activity_records.id", ondelete="SET NULL"), nullable=True),
        sa.Column("emission_factor_id", UUID(as_uuid=True),
                  sa.ForeignKey("emission_factors.id", ondelete="SET NULL"), nullable=True),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("original_quantity", sa.Numeric(24, 8), nullable=True),
        sa.Column("original_unit", sa.String(50), nullable=True),
        sa.Column("normalized_quantity", sa.Numeric(24, 8), nullable=True),
        sa.Column("normalized_unit", sa.String(50), nullable=True),
        sa.Column("conversion_multiplier", sa.Numeric(24, 12), nullable=True),
        sa.Column("factor_value_snapshot", sa.Numeric(24, 12), nullable=False),
        sa.Column("factor_unit_snapshot", sa.String(50), nullable=True),
        sa.Column("emissions_kgco2e", sa.Numeric(28, 8), nullable=False),
        sa.Column("scope", sa.String(20), nullable=True),
        sa.Column("source_category", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_calc_lines_run", "calculation_lines", ["calculation_run_id"])


def downgrade() -> None:
    op.drop_index("ix_calc_lines_run", table_name="calculation_lines")
    op.drop_table("calculation_lines")
    op.drop_table("calculation_runs")
