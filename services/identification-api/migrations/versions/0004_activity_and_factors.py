"""0004_activity_and_factors: activity_records, emission_factors

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── activity_records ─────────────────────────────────────────────────
    op.create_table(
        "activity_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_inventory_item_id", UUID(as_uuid=True),
                  sa.ForeignKey("source_inventory_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("unit_code", sa.String(50), nullable=False),
        sa.Column("normalized_quantity", sa.Numeric(24, 8), nullable=True),
        sa.Column("normalized_unit_code", sa.String(50), nullable=True),
        sa.Column("normalization_multiplier", sa.Numeric(24, 12), nullable=True),
        sa.Column("data_source_type", sa.String(30), nullable=True),
        sa.Column("data_quality", sa.String(30), nullable=True),
        sa.Column("evidence_reference", sa.String(500), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("quantity >= 0", name="ck_activity_quantity_positive"),
        sa.CheckConstraint("normalized_quantity >= 0", name="ck_activity_norm_qty_positive"),
        sa.CheckConstraint("period_end >= period_start", name="ck_activity_period"),
    )
    op.create_index("ix_activity_source_period", "activity_records", ["source_inventory_item_id", "period_start"])

    # ── emission_factors ─────────────────────────────────────────────────
    op.create_table(
        "emission_factors",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("factor_code", sa.String(100), nullable=False),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("source_category", sa.String(100), nullable=True),
        sa.Column("scope", sa.String(20), nullable=True),
        sa.Column("factor_value", sa.Numeric(24, 12), nullable=False),
        sa.Column("activity_unit", sa.String(50), nullable=False),
        sa.Column("emission_unit", sa.String(50), nullable=False, server_default="kgCO2e"),
        sa.Column("geography", sa.String(100), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_organization", sa.String(255), nullable=True),
        sa.Column("source_document", sa.String(500), nullable=True),
        sa.Column("source_url", sa.String(500), nullable=True),
        sa.Column("method", sa.String(100), nullable=True),
        sa.Column("quality_rating", sa.String(20), nullable=True),
        sa.Column("metadata_json", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("factor_code", "version", name="uq_factor_code_version"),
        sa.CheckConstraint("factor_value >= 0", name="ck_factor_value_positive"),
    )
    op.create_index("ix_factors_code_version", "emission_factors", ["factor_code", "version"])


def downgrade() -> None:
    op.drop_index("ix_factors_code_version", table_name="emission_factors")
    op.drop_table("emission_factors")
    op.drop_index("ix_activity_source_period", table_name="activity_records")
    op.drop_table("activity_records")
