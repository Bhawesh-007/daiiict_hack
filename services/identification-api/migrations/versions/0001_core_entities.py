"""0001_core_entities: companies, facilities, assessments, assessment_products

Revision ID: 0001
Revises: None
Create Date: 2026-09-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── companies ────────────────────────────────────────────────────────
    op.create_table(
        "companies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("msme_category", sa.String(50), nullable=True),
        sa.Column("registration_number", sa.String(100), nullable=True),
        sa.Column("contact_email", sa.String(255), nullable=True),
        sa.Column("contact_phone", sa.String(50), nullable=True),
        sa.Column("address", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # ── facilities ───────────────────────────────────────────────────────
    op.create_table(
        "facilities",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("location", sa.String(500), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("state", sa.String(100), nullable=True),
        sa.Column("country", sa.String(100), nullable=True, server_default="India"),
        sa.Column("grid_region", sa.String(100), nullable=True),
        sa.Column("ownership_type", sa.String(50), nullable=True),
        sa.Column("latitude", sa.Numeric(10, 7), nullable=True),
        sa.Column("longitude", sa.Numeric(10, 7), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # ── assessments ──────────────────────────────────────────────────────
    op.create_table(
        "assessments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("facility_id", UUID(as_uuid=True), sa.ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("industry_name", sa.String(200), nullable=False),
        sa.Column("industry_code", sa.String(50), nullable=True),
        sa.Column("industry_template_key", sa.String(200), nullable=True),
        sa.Column("industry_template_version", sa.String(50), nullable=True),
        sa.Column("reporting_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reporting_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organizational_boundary", sa.String(100), nullable=True),
        sa.Column("operational_boundary", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('DRAFT','IN_PROGRESS','IDENTIFIED','QUANTIFIED','FINALIZED','ARCHIVED')",
            name="ck_assessment_status",
        ),
        sa.CheckConstraint(
            "reporting_period_end >= reporting_period_start",
            name="ck_assessment_period",
        ),
    )
    op.create_index("ix_assessments_facility_status", "assessments", ["facility_id", "status"])

    # ── assessment_products ──────────────────────────────────────────────
    op.create_table(
        "assessment_products",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("assessment_id", UUID(as_uuid=True), sa.ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_name", sa.String(255), nullable=False),
        sa.Column("quantity", sa.Numeric(24, 8), nullable=True),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("assessment_products")
    op.drop_index("ix_assessments_facility_status", table_name="assessments")
    op.drop_table("assessments")
    op.drop_table("facilities")
    op.drop_table("companies")
