"""
SQLAlchemy ORM models – one common schema for every industry.

16 tables covering the full Layer-1 identification → calculation pipeline.
Industry-specific logic lives in templates/rules loaded at runtime;
the schema itself is industry-agnostic.

PostgreSQL datatype rules
─────────────────────────
• UUID primary keys
• TIMESTAMPTZ for all timestamps
• NUMERIC(24,8)  for activity quantities
• NUMERIC(24,12) for emission factors
• NUMERIC(28,8)  for emission results
• JSONB only for flexible evidence, engine output, and final snapshots
• VARCHAR + CHECK for statuses (easier Alembic evolution than PG enums)
• No FLOAT for emission calculations
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.persistence.database import Base


# ── helpers ──────────────────────────────────────────────────────────────────

def _uuid_pk() -> Column:
    return Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))


def _ts_created() -> Column:
    return Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


def _ts_updated() -> Column:
    return Column(DateTime(timezone=True), nullable=False, server_default=text("now()"), onupdate=datetime.utcnow)


# ═════════════════════════════════════════════════════════════════════════════
# 1.  COMPANIES
# ═════════════════════════════════════════════════════════════════════════════

class Company(Base):
    __tablename__ = "companies"

    id = _uuid_pk()
    name = Column(String(255), nullable=False)
    msme_category = Column(String(50), nullable=True)
    registration_number = Column(String(100), nullable=True)
    contact_email = Column(String(255), nullable=True)
    contact_phone = Column(String(50), nullable=True)
    address = Column(Text, nullable=True)
    created_at = _ts_created()
    updated_at = _ts_updated()

    facilities = relationship("Facility", back_populates="company", cascade="all, delete-orphan")


# ═════════════════════════════════════════════════════════════════════════════
# 2.  FACILITIES
# ═════════════════════════════════════════════════════════════════════════════

class Facility(Base):
    __tablename__ = "facilities"

    id = _uuid_pk()
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    location = Column(String(500), nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    country = Column(String(100), nullable=True, server_default="India")
    grid_region = Column(String(100), nullable=True)
    ownership_type = Column(String(50), nullable=True)
    latitude = Column(Numeric(10, 7), nullable=True)
    longitude = Column(Numeric(10, 7), nullable=True)
    created_at = _ts_created()
    updated_at = _ts_updated()

    company = relationship("Company", back_populates="facilities")
    assessments = relationship("Assessment", back_populates="facility", cascade="all, delete-orphan")


# ═════════════════════════════════════════════════════════════════════════════
# 3.  ASSESSMENTS
# ═════════════════════════════════════════════════════════════════════════════

class Assessment(Base):
    __tablename__ = "assessments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT','IN_PROGRESS','IDENTIFIED','QUANTIFIED','FINALIZED','ARCHIVED')",
            name="ck_assessment_status",
        ),
        CheckConstraint(
            "reporting_period_end >= reporting_period_start",
            name="ck_assessment_period",
        ),
        Index("ix_assessments_facility_status", "facility_id", "status"),
    )

    id = _uuid_pk()
    facility_id = Column(UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False)
    industry_name = Column(String(200), nullable=False)
    industry_code = Column(String(50), nullable=True)
    industry_template_key = Column(String(200), nullable=True)
    industry_template_version = Column(String(50), nullable=True)
    reporting_period_start = Column(DateTime(timezone=True), nullable=False)
    reporting_period_end = Column(DateTime(timezone=True), nullable=False)
    organizational_boundary = Column(String(100), nullable=True)
    operational_boundary = Column(String(100), nullable=True)
    status = Column(String(20), nullable=False, server_default="DRAFT")
    created_at = _ts_created()
    updated_at = _ts_updated()

    facility = relationship("Facility", back_populates="assessments")
    products = relationship("AssessmentProduct", back_populates="assessment", cascade="all, delete-orphan")
    process_steps = relationship("ProcessStep", back_populates="assessment", cascade="all, delete-orphan")
    identification_runs = relationship("IdentificationRun", back_populates="assessment", cascade="all, delete-orphan")
    source_candidates = relationship("SourceCandidate", back_populates="assessment", cascade="all, delete-orphan")
    source_inventory_items = relationship("SourceInventoryItem", back_populates="assessment", cascade="all, delete-orphan")
    calculation_runs = relationship("CalculationRun", back_populates="assessment", cascade="all, delete-orphan")
    final_profiles = relationship("FinalProfile", back_populates="assessment", cascade="all, delete-orphan")


# ═════════════════════════════════════════════════════════════════════════════
# 4.  ASSESSMENT PRODUCTS
# ═════════════════════════════════════════════════════════════════════════════

class AssessmentProduct(Base):
    __tablename__ = "assessment_products"

    id = _uuid_pk()
    assessment_id = Column(UUID(as_uuid=True), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False)
    product_name = Column(String(255), nullable=False)
    quantity = Column(Numeric(24, 8), nullable=True)
    unit = Column(String(50), nullable=True)
    description = Column(Text, nullable=True)
    created_at = _ts_created()

    assessment = relationship("Assessment", back_populates="products")


# ═════════════════════════════════════════════════════════════════════════════
# 5.  PROCESS STEPS
# ═════════════════════════════════════════════════════════════════════════════

class ProcessStep(Base):
    __tablename__ = "process_steps"
    __table_args__ = (
        Index("ix_process_steps_assessment", "assessment_id"),
    )

    id = _uuid_pk()
    assessment_id = Column(UUID(as_uuid=True), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    sequence = Column(Integer, nullable=True)
    description = Column(Text, nullable=True)
    is_outsourced = Column(String(3), nullable=False, server_default="NO")
    created_at = _ts_created()
    updated_at = _ts_updated()

    assessment = relationship("Assessment", back_populates="process_steps")
    equipment = relationship("Equipment", back_populates="process_step", cascade="all, delete-orphan")
    input_output_flows = relationship("InputOutputFlow", back_populates="process_step", cascade="all, delete-orphan")


# ═════════════════════════════════════════════════════════════════════════════
# 6.  EQUIPMENT
# ═════════════════════════════════════════════════════════════════════════════

class Equipment(Base):
    __tablename__ = "equipment"
    __table_args__ = (
        Index("ix_equipment_process_step", "process_step_id"),
    )

    id = _uuid_pk()
    process_step_id = Column(UUID(as_uuid=True), ForeignKey("process_steps.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    equipment_type = Column(String(100), nullable=True)
    capacity = Column(String(100), nullable=True)
    fuel_type = Column(String(100), nullable=True)
    energy_type = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    created_at = _ts_created()
    updated_at = _ts_updated()

    process_step = relationship("ProcessStep", back_populates="equipment")
    input_output_flows = relationship("InputOutputFlow", back_populates="equipment", cascade="all, delete-orphan")


# ═════════════════════════════════════════════════════════════════════════════
# 7.  INPUT / OUTPUT FLOWS
# ═════════════════════════════════════════════════════════════════════════════

class InputOutputFlow(Base):
    __tablename__ = "input_output_flows"
    __table_args__ = (
        CheckConstraint(
            "direction IN ('INPUT','OUTPUT')",
            name="ck_flow_direction",
        ),
        Index("ix_flows_process_step", "process_step_id"),
        Index("ix_flows_equipment", "equipment_id"),
    )

    id = _uuid_pk()
    process_step_id = Column(UUID(as_uuid=True), ForeignKey("process_steps.id", ondelete="SET NULL"), nullable=True)
    equipment_id = Column(UUID(as_uuid=True), ForeignKey("equipment.id", ondelete="SET NULL"), nullable=True)
    direction = Column(String(10), nullable=False)
    category = Column(String(100), nullable=True)
    item_name = Column(String(255), nullable=False)
    unit = Column(String(50), nullable=True)
    data_availability = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = _ts_created()

    process_step = relationship("ProcessStep", back_populates="input_output_flows")
    equipment = relationship("Equipment", back_populates="input_output_flows")


# ═════════════════════════════════════════════════════════════════════════════
# 8.  IDENTIFICATION RUNS
# ═════════════════════════════════════════════════════════════════════════════

class IdentificationRun(Base):
    __tablename__ = "identification_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('RUNNING','COMPLETED','FAILED')",
            name="ck_identification_run_status",
        ),
    )

    id = _uuid_pk()
    assessment_id = Column(UUID(as_uuid=True), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False)
    engine_type = Column(String(50), nullable=False)
    engine_version = Column(String(50), nullable=True)
    input_hash = Column(String(128), nullable=True)
    output_json = Column(JSONB, nullable=True)
    status = Column(String(20), nullable=False, server_default="RUNNING")
    started_at = _ts_created()
    completed_at = Column(DateTime(timezone=True), nullable=True)

    assessment = relationship("Assessment", back_populates="identification_runs")
    candidates = relationship("SourceCandidate", back_populates="identification_run", cascade="all, delete-orphan")


# ═════════════════════════════════════════════════════════════════════════════
# 9.  SOURCE CANDIDATES
# ═════════════════════════════════════════════════════════════════════════════

class SourceCandidate(Base):
    __tablename__ = "source_candidates"
    __table_args__ = (
        CheckConstraint(
            "origin IN ('TEMPLATE','RULE','ML','CHECKLIST','USER')",
            name="ck_candidate_origin",
        ),
        CheckConstraint(
            "status IN ('PROPOSED','MERGED','DISMISSED','PROMOTED')",
            name="ck_candidate_status",
        ),
        Index("ix_candidates_assessment_status", "assessment_id", "status"),
    )

    id = _uuid_pk()
    assessment_id = Column(UUID(as_uuid=True), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False)
    identification_run_id = Column(UUID(as_uuid=True), ForeignKey("identification_runs.id", ondelete="SET NULL"), nullable=True)
    process_step_id = Column(UUID(as_uuid=True), ForeignKey("process_steps.id", ondelete="SET NULL"), nullable=True)
    equipment_id = Column(UUID(as_uuid=True), ForeignKey("equipment.id", ondelete="SET NULL"), nullable=True)
    source_key = Column(String(200), nullable=False)
    source_name = Column(String(255), nullable=False)
    source_category = Column(String(100), nullable=True)
    suggested_scope = Column(String(20), nullable=True)
    origin = Column(String(20), nullable=False)
    reason = Column(Text, nullable=True)
    confidence = Column(Numeric(5, 4), nullable=True)
    status = Column(String(20), nullable=False, server_default="PROPOSED")
    evidence_json = Column(JSONB, nullable=True)
    created_at = _ts_created()

    assessment = relationship("Assessment", back_populates="source_candidates")
    identification_run = relationship("IdentificationRun", back_populates="candidates")


# ═════════════════════════════════════════════════════════════════════════════
# 10. SOURCE INVENTORY ITEMS
# ═════════════════════════════════════════════════════════════════════════════

class SourceInventoryItem(Base):
    __tablename__ = "source_inventory_items"
    __table_args__ = (
        CheckConstraint(
            "status IN ('CONFIRMED','POTENTIAL','MISSING_INFORMATION','NOT_APPLICABLE','OUTSOURCED')",
            name="ck_inventory_status",
        ),
        Index("ix_inventory_assessment_status", "assessment_id", "status"),
    )

    id = _uuid_pk()
    assessment_id = Column(UUID(as_uuid=True), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("source_candidates.id", ondelete="SET NULL"), nullable=True)
    process_step_id = Column(UUID(as_uuid=True), ForeignKey("process_steps.id", ondelete="SET NULL"), nullable=True)
    equipment_id = Column(UUID(as_uuid=True), ForeignKey("equipment.id", ondelete="SET NULL"), nullable=True)
    source_key = Column(String(200), nullable=False)
    source_name = Column(String(255), nullable=False)
    source_category = Column(String(100), nullable=True)
    scope = Column(String(20), nullable=True)
    status = Column(String(30), nullable=False, server_default="POTENTIAL")
    confirmation_note = Column(Text, nullable=True)
    confirmed_by = Column(String(255), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = _ts_created()
    updated_at = _ts_updated()

    assessment = relationship("Assessment", back_populates="source_inventory_items")
    candidate = relationship("SourceCandidate")
    activity_records = relationship("ActivityRecord", back_populates="source_inventory_item", cascade="all, delete-orphan")


# ═════════════════════════════════════════════════════════════════════════════
# 11. ACTIVITY RECORDS
# ═════════════════════════════════════════════════════════════════════════════

class ActivityRecord(Base):
    __tablename__ = "activity_records"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="ck_activity_quantity_positive"),
        CheckConstraint("normalized_quantity >= 0", name="ck_activity_norm_qty_positive"),
        CheckConstraint("period_end >= period_start", name="ck_activity_period"),
        Index("ix_activity_source_period", "source_inventory_item_id", "period_start"),
    )

    id = _uuid_pk()
    source_inventory_item_id = Column(
        UUID(as_uuid=True),
        ForeignKey("source_inventory_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)
    quantity = Column(Numeric(24, 8), nullable=False)
    unit_code = Column(String(50), nullable=False)
    normalized_quantity = Column(Numeric(24, 8), nullable=True)
    normalized_unit_code = Column(String(50), nullable=True)
    normalization_multiplier = Column(Numeric(24, 12), nullable=True)
    data_source_type = Column(String(30), nullable=True)
    data_quality = Column(String(30), nullable=True)
    evidence_reference = Column(String(500), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = _ts_created()

    source_inventory_item = relationship("SourceInventoryItem", back_populates="activity_records")


# ═════════════════════════════════════════════════════════════════════════════
# 12. EMISSION FACTORS
# ═════════════════════════════════════════════════════════════════════════════

class EmissionFactor(Base):
    __tablename__ = "emission_factors"
    __table_args__ = (
        UniqueConstraint("factor_code", "version", name="uq_factor_code_version"),
        CheckConstraint("factor_value >= 0", name="ck_factor_value_positive"),
        Index("ix_factors_code_version", "factor_code", "version"),
    )

    id = _uuid_pk()
    factor_code = Column(String(100), nullable=False)
    version = Column(String(50), nullable=False)
    name = Column(String(255), nullable=False)
    source_category = Column(String(100), nullable=True)
    scope = Column(String(20), nullable=True)
    factor_value = Column(Numeric(24, 12), nullable=False)
    activity_unit = Column(String(50), nullable=False)
    emission_unit = Column(String(50), nullable=False, server_default="kgCO2e")
    geography = Column(String(100), nullable=True)
    valid_from = Column(DateTime(timezone=True), nullable=True)
    valid_to = Column(DateTime(timezone=True), nullable=True)
    source_organization = Column(String(255), nullable=True)
    source_document = Column(String(500), nullable=True)
    source_url = Column(String(500), nullable=True)
    method = Column(String(100), nullable=True)
    quality_rating = Column(String(20), nullable=True)
    metadata_json = Column(JSONB, nullable=True)
    created_at = _ts_created()


# ═════════════════════════════════════════════════════════════════════════════
# 13. CALCULATION RUNS
# ═════════════════════════════════════════════════════════════════════════════

class CalculationRun(Base):
    __tablename__ = "calculation_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('RUNNING','COMPLETED','FAILED')",
            name="ck_calc_run_status",
        ),
    )

    id = _uuid_pk()
    assessment_id = Column(UUID(as_uuid=True), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False)
    methodology_version = Column(String(50), nullable=True)
    factor_set_version = Column(String(50), nullable=True)
    status = Column(String(20), nullable=False, server_default="RUNNING")
    total_emissions_kgco2e = Column(Numeric(28, 8), nullable=True)
    notes = Column(Text, nullable=True)
    started_at = _ts_created()
    completed_at = Column(DateTime(timezone=True), nullable=True)

    assessment = relationship("Assessment", back_populates="calculation_runs")
    lines = relationship("CalculationLine", back_populates="calculation_run", cascade="all, delete-orphan")


# ═════════════════════════════════════════════════════════════════════════════
# 14. CALCULATION LINES
# ═════════════════════════════════════════════════════════════════════════════

class CalculationLine(Base):
    __tablename__ = "calculation_lines"
    __table_args__ = (
        Index("ix_calc_lines_run", "calculation_run_id"),
    )

    id = _uuid_pk()
    calculation_run_id = Column(UUID(as_uuid=True), ForeignKey("calculation_runs.id", ondelete="CASCADE"), nullable=False)
    source_inventory_item_id = Column(UUID(as_uuid=True), ForeignKey("source_inventory_items.id", ondelete="SET NULL"), nullable=True)
    activity_record_id = Column(UUID(as_uuid=True), ForeignKey("activity_records.id", ondelete="SET NULL"), nullable=True)
    emission_factor_id = Column(UUID(as_uuid=True), ForeignKey("emission_factors.id", ondelete="SET NULL"), nullable=True)
    period_start = Column(DateTime(timezone=True), nullable=True)
    period_end = Column(DateTime(timezone=True), nullable=True)
    original_quantity = Column(Numeric(24, 8), nullable=True)
    original_unit = Column(String(50), nullable=True)
    normalized_quantity = Column(Numeric(24, 8), nullable=True)
    normalized_unit = Column(String(50), nullable=True)
    conversion_multiplier = Column(Numeric(24, 12), nullable=True)
    factor_value_snapshot = Column(Numeric(24, 12), nullable=False)
    factor_unit_snapshot = Column(String(50), nullable=True)
    emissions_kgco2e = Column(Numeric(28, 8), nullable=False)
    scope = Column(String(20), nullable=True)
    source_category = Column(String(100), nullable=True)
    created_at = _ts_created()

    calculation_run = relationship("CalculationRun", back_populates="lines")


# ═════════════════════════════════════════════════════════════════════════════
# 15. FINAL PROFILES
# ═════════════════════════════════════════════════════════════════════════════

class FinalProfile(Base):
    __tablename__ = "final_profiles"
    __table_args__ = (
        UniqueConstraint("assessment_id", "version", name="uq_profile_assessment_version"),
        Index("ix_profiles_assessment_version", "assessment_id", "version"),
    )

    id = _uuid_pk()
    assessment_id = Column(UUID(as_uuid=True), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False)
    calculation_run_id = Column(UUID(as_uuid=True), ForeignKey("calculation_runs.id", ondelete="SET NULL"), nullable=True)
    version = Column(Integer, nullable=False)
    total_emissions_kgco2e = Column(Numeric(28, 8), nullable=False)
    completeness_percentage = Column(Numeric(5, 2), nullable=True)
    scope_totals_json = Column(JSONB, nullable=True)
    category_totals_json = Column(JSONB, nullable=True)
    source_ranking_json = Column(JSONB, nullable=True)
    unquantified_sources_json = Column(JSONB, nullable=True)
    profile_snapshot_json = Column(JSONB, nullable=True)
    checksum = Column(String(128), nullable=True)
    finalized_by = Column(String(255), nullable=True)
    finalized_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    assessment = relationship("Assessment", back_populates="final_profiles")


# ═════════════════════════════════════════════════════════════════════════════
# 16. AUDIT EVENTS
# ═════════════════════════════════════════════════════════════════════════════

class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = _uuid_pk()
    actor = Column(String(255), nullable=True)
    action = Column(String(100), nullable=False)
    entity_type = Column(String(100), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=True)
    before_value = Column(JSONB, nullable=True)
    after_value = Column(JSONB, nullable=True)
    metadata_json = Column(JSONB, nullable=True)
    created_at = _ts_created()
