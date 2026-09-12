"""0002_process_mapping: process_steps, equipment, input_output_flows

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── process_steps ────────────────────────────────────────────────────
    op.create_table(
        "process_steps",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("assessment_id", UUID(as_uuid=True), sa.ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("sequence", sa.Integer, nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_outsourced", sa.String(3), nullable=False, server_default="NO"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_process_steps_assessment", "process_steps", ["assessment_id"])

    # ── equipment ────────────────────────────────────────────────────────
    op.create_table(
        "equipment",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("process_step_id", UUID(as_uuid=True), sa.ForeignKey("process_steps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("equipment_type", sa.String(100), nullable=True),
        sa.Column("capacity", sa.String(100), nullable=True),
        sa.Column("fuel_type", sa.String(100), nullable=True),
        sa.Column("energy_type", sa.String(100), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_equipment_process_step", "equipment", ["process_step_id"])

    # ── input_output_flows ───────────────────────────────────────────────
    op.create_table(
        "input_output_flows",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("process_step_id", UUID(as_uuid=True), sa.ForeignKey("process_steps.id", ondelete="SET NULL"), nullable=True),
        sa.Column("equipment_id", UUID(as_uuid=True), sa.ForeignKey("equipment.id", ondelete="SET NULL"), nullable=True),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("item_name", sa.String(255), nullable=False),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("data_availability", sa.String(50), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("direction IN ('INPUT','OUTPUT')", name="ck_flow_direction"),
    )
    op.create_index("ix_flows_process_step", "input_output_flows", ["process_step_id"])
    op.create_index("ix_flows_equipment", "input_output_flows", ["equipment_id"])


def downgrade() -> None:
    op.drop_index("ix_flows_equipment", table_name="input_output_flows")
    op.drop_index("ix_flows_process_step", table_name="input_output_flows")
    op.drop_table("input_output_flows")
    op.drop_index("ix_equipment_process_step", table_name="equipment")
    op.drop_table("equipment")
    op.drop_index("ix_process_steps_assessment", table_name="process_steps")
    op.drop_table("process_steps")
