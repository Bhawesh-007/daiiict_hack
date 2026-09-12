"""0006_final_profiles_and_audit: final_profiles, audit_events

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── final_profiles ───────────────────────────────────────────────────
    op.create_table(
        "final_profiles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("assessment_id", UUID(as_uuid=True), sa.ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("calculation_run_id", UUID(as_uuid=True),
                  sa.ForeignKey("calculation_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("total_emissions_kgco2e", sa.Numeric(28, 8), nullable=False),
        sa.Column("completeness_percentage", sa.Numeric(5, 2), nullable=True),
        sa.Column("scope_totals_json", JSONB, nullable=True),
        sa.Column("category_totals_json", JSONB, nullable=True),
        sa.Column("source_ranking_json", JSONB, nullable=True),
        sa.Column("unquantified_sources_json", JSONB, nullable=True),
        sa.Column("profile_snapshot_json", JSONB, nullable=True),
        sa.Column("checksum", sa.String(128), nullable=True),
        sa.Column("finalized_by", sa.String(255), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("assessment_id", "version", name="uq_profile_assessment_version"),
    )
    op.create_index("ix_profiles_assessment_version", "final_profiles", ["assessment_id", "version"])

    # ── audit_events ─────────────────────────────────────────────────────
    op.create_table(
        "audit_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("actor", sa.String(255), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=True),
        sa.Column("before_value", JSONB, nullable=True),
        sa.Column("after_value", JSONB, nullable=True),
        sa.Column("metadata_json", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_index("ix_profiles_assessment_version", table_name="final_profiles")
    op.drop_table("final_profiles")
