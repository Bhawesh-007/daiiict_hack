"""0003_source_identification: identification_runs, source_candidates, source_inventory_items

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── identification_runs ──────────────────────────────────────────────
    op.create_table(
        "identification_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("assessment_id", UUID(as_uuid=True), sa.ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("engine_type", sa.String(50), nullable=False),
        sa.Column("engine_version", sa.String(50), nullable=True),
        sa.Column("input_hash", sa.String(128), nullable=True),
        sa.Column("output_json", JSONB, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="RUNNING"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('RUNNING','COMPLETED','FAILED')", name="ck_identification_run_status"),
    )

    # ── source_candidates ────────────────────────────────────────────────
    op.create_table(
        "source_candidates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("assessment_id", UUID(as_uuid=True), sa.ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("identification_run_id", UUID(as_uuid=True), sa.ForeignKey("identification_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("process_step_id", UUID(as_uuid=True), sa.ForeignKey("process_steps.id", ondelete="SET NULL"), nullable=True),
        sa.Column("equipment_id", UUID(as_uuid=True), sa.ForeignKey("equipment.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_key", sa.String(200), nullable=False),
        sa.Column("source_name", sa.String(255), nullable=False),
        sa.Column("source_category", sa.String(100), nullable=True),
        sa.Column("suggested_scope", sa.String(20), nullable=True),
        sa.Column("origin", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="PROPOSED"),
        sa.Column("evidence_json", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("origin IN ('TEMPLATE','RULE','ML','CHECKLIST','USER')", name="ck_candidate_origin"),
        sa.CheckConstraint("status IN ('PROPOSED','MERGED','DISMISSED','PROMOTED')", name="ck_candidate_status"),
    )
    op.create_index("ix_candidates_assessment_status", "source_candidates", ["assessment_id", "status"])

    # ── source_inventory_items ───────────────────────────────────────────
    op.create_table(
        "source_inventory_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("assessment_id", UUID(as_uuid=True), sa.ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_id", UUID(as_uuid=True), sa.ForeignKey("source_candidates.id", ondelete="SET NULL"), nullable=True),
        sa.Column("process_step_id", UUID(as_uuid=True), sa.ForeignKey("process_steps.id", ondelete="SET NULL"), nullable=True),
        sa.Column("equipment_id", UUID(as_uuid=True), sa.ForeignKey("equipment.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_key", sa.String(200), nullable=False),
        sa.Column("source_name", sa.String(255), nullable=False),
        sa.Column("source_category", sa.String(100), nullable=True),
        sa.Column("scope", sa.String(20), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="POTENTIAL"),
        sa.Column("confirmation_note", sa.Text, nullable=True),
        sa.Column("confirmed_by", sa.String(255), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('CONFIRMED','POTENTIAL','MISSING_INFORMATION','NOT_APPLICABLE','OUTSOURCED')",
            name="ck_inventory_status",
        ),
    )
    op.create_index("ix_inventory_assessment_status", "source_inventory_items", ["assessment_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_inventory_assessment_status", table_name="source_inventory_items")
    op.drop_table("source_inventory_items")
    op.drop_index("ix_candidates_assessment_status", table_name="source_candidates")
    op.drop_table("source_candidates")
    op.drop_table("identification_runs")
