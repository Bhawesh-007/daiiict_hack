BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001

CREATE TABLE companies (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    name VARCHAR(255) NOT NULL, 
    msme_category VARCHAR(50), 
    registration_number VARCHAR(100), 
    contact_email VARCHAR(255), 
    contact_phone VARCHAR(50), 
    address TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id)
);

CREATE TABLE facilities (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    company_id UUID NOT NULL, 
    name VARCHAR(255) NOT NULL, 
    location VARCHAR(500), 
    city VARCHAR(100), 
    state VARCHAR(100), 
    country VARCHAR(100) DEFAULT 'India', 
    grid_region VARCHAR(100), 
    ownership_type VARCHAR(50), 
    latitude NUMERIC(10, 7), 
    longitude NUMERIC(10, 7), 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(company_id) REFERENCES companies (id) ON DELETE CASCADE
);

CREATE TABLE assessments (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    facility_id UUID NOT NULL, 
    industry_name VARCHAR(200) NOT NULL, 
    industry_code VARCHAR(50), 
    industry_template_key VARCHAR(200), 
    industry_template_version VARCHAR(50), 
    reporting_period_start TIMESTAMP WITH TIME ZONE NOT NULL, 
    reporting_period_end TIMESTAMP WITH TIME ZONE NOT NULL, 
    organizational_boundary VARCHAR(100), 
    operational_boundary VARCHAR(100), 
    status VARCHAR(20) DEFAULT 'DRAFT' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_assessment_status CHECK (status IN ('DRAFT','IN_PROGRESS','IDENTIFIED','QUANTIFIED','FINALIZED','ARCHIVED')), 
    CONSTRAINT ck_assessment_period CHECK (reporting_period_end >= reporting_period_start), 
    FOREIGN KEY(facility_id) REFERENCES facilities (id) ON DELETE CASCADE
);

CREATE INDEX ix_assessments_facility_status ON assessments (facility_id, status);

CREATE TABLE assessment_products (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    assessment_id UUID NOT NULL, 
    product_name VARCHAR(255) NOT NULL, 
    quantity NUMERIC(24, 8), 
    unit VARCHAR(50), 
    description TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(assessment_id) REFERENCES assessments (id) ON DELETE CASCADE
);

INSERT INTO alembic_version (version_num) VALUES ('0001') RETURNING alembic_version.version_num;

-- Running upgrade 0001 -> 0002

CREATE TABLE process_steps (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    assessment_id UUID NOT NULL, 
    name VARCHAR(255) NOT NULL, 
    sequence INTEGER, 
    description TEXT, 
    is_outsourced VARCHAR(3) DEFAULT 'NO' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(assessment_id) REFERENCES assessments (id) ON DELETE CASCADE
);

CREATE INDEX ix_process_steps_assessment ON process_steps (assessment_id);

CREATE TABLE equipment (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    process_step_id UUID NOT NULL, 
    name VARCHAR(255) NOT NULL, 
    equipment_type VARCHAR(100), 
    capacity VARCHAR(100), 
    fuel_type VARCHAR(100), 
    energy_type VARCHAR(100), 
    description TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(process_step_id) REFERENCES process_steps (id) ON DELETE CASCADE
);

CREATE INDEX ix_equipment_process_step ON equipment (process_step_id);

CREATE TABLE input_output_flows (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    process_step_id UUID, 
    equipment_id UUID, 
    direction VARCHAR(10) NOT NULL, 
    category VARCHAR(100), 
    item_name VARCHAR(255) NOT NULL, 
    unit VARCHAR(50), 
    data_availability VARCHAR(50), 
    notes TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_flow_direction CHECK (direction IN ('INPUT','OUTPUT')), 
    FOREIGN KEY(process_step_id) REFERENCES process_steps (id) ON DELETE SET NULL, 
    FOREIGN KEY(equipment_id) REFERENCES equipment (id) ON DELETE SET NULL
);

CREATE INDEX ix_flows_process_step ON input_output_flows (process_step_id);

CREATE INDEX ix_flows_equipment ON input_output_flows (equipment_id);

UPDATE alembic_version SET version_num='0002' WHERE alembic_version.version_num = '0001';

-- Running upgrade 0002 -> 0003

CREATE TABLE identification_runs (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    assessment_id UUID NOT NULL, 
    engine_type VARCHAR(50) NOT NULL, 
    engine_version VARCHAR(50), 
    input_hash VARCHAR(128), 
    output_json JSONB, 
    status VARCHAR(20) DEFAULT 'RUNNING' NOT NULL, 
    started_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    completed_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_identification_run_status CHECK (status IN ('RUNNING','COMPLETED','FAILED')), 
    FOREIGN KEY(assessment_id) REFERENCES assessments (id) ON DELETE CASCADE
);

CREATE TABLE source_candidates (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    assessment_id UUID NOT NULL, 
    identification_run_id UUID, 
    process_step_id UUID, 
    equipment_id UUID, 
    source_key VARCHAR(200) NOT NULL, 
    source_name VARCHAR(255) NOT NULL, 
    source_category VARCHAR(100), 
    suggested_scope VARCHAR(20), 
    origin VARCHAR(20) NOT NULL, 
    reason TEXT, 
    confidence NUMERIC(5, 4), 
    status VARCHAR(20) DEFAULT 'PROPOSED' NOT NULL, 
    evidence_json JSONB, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_candidate_origin CHECK (origin IN ('TEMPLATE','RULE','ML','CHECKLIST','USER')), 
    CONSTRAINT ck_candidate_status CHECK (status IN ('PROPOSED','MERGED','DISMISSED','PROMOTED')), 
    FOREIGN KEY(assessment_id) REFERENCES assessments (id) ON DELETE CASCADE, 
    FOREIGN KEY(identification_run_id) REFERENCES identification_runs (id) ON DELETE SET NULL, 
    FOREIGN KEY(process_step_id) REFERENCES process_steps (id) ON DELETE SET NULL, 
    FOREIGN KEY(equipment_id) REFERENCES equipment (id) ON DELETE SET NULL
);

CREATE INDEX ix_candidates_assessment_status ON source_candidates (assessment_id, status);

CREATE TABLE source_inventory_items (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    assessment_id UUID NOT NULL, 
    candidate_id UUID, 
    process_step_id UUID, 
    equipment_id UUID, 
    source_key VARCHAR(200) NOT NULL, 
    source_name VARCHAR(255) NOT NULL, 
    source_category VARCHAR(100), 
    scope VARCHAR(20), 
    status VARCHAR(30) DEFAULT 'POTENTIAL' NOT NULL, 
    confirmation_note TEXT, 
    confirmed_by VARCHAR(255), 
    confirmed_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_inventory_status CHECK (status IN ('CONFIRMED','POTENTIAL','MISSING_INFORMATION','NOT_APPLICABLE','OUTSOURCED')), 
    FOREIGN KEY(assessment_id) REFERENCES assessments (id) ON DELETE CASCADE, 
    FOREIGN KEY(candidate_id) REFERENCES source_candidates (id) ON DELETE SET NULL, 
    FOREIGN KEY(process_step_id) REFERENCES process_steps (id) ON DELETE SET NULL, 
    FOREIGN KEY(equipment_id) REFERENCES equipment (id) ON DELETE SET NULL
);

CREATE INDEX ix_inventory_assessment_status ON source_inventory_items (assessment_id, status);

UPDATE alembic_version SET version_num='0003' WHERE alembic_version.version_num = '0002';

-- Running upgrade 0003 -> 0004

CREATE TABLE activity_records (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    source_inventory_item_id UUID NOT NULL, 
    period_start TIMESTAMP WITH TIME ZONE NOT NULL, 
    period_end TIMESTAMP WITH TIME ZONE NOT NULL, 
    quantity NUMERIC(24, 8) NOT NULL, 
    unit_code VARCHAR(50) NOT NULL, 
    normalized_quantity NUMERIC(24, 8), 
    normalized_unit_code VARCHAR(50), 
    normalization_multiplier NUMERIC(24, 12), 
    data_source_type VARCHAR(30), 
    data_quality VARCHAR(30), 
    evidence_reference VARCHAR(500), 
    notes TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_activity_quantity_positive CHECK (quantity >= 0), 
    CONSTRAINT ck_activity_norm_qty_positive CHECK (normalized_quantity >= 0), 
    CONSTRAINT ck_activity_period CHECK (period_end >= period_start), 
    FOREIGN KEY(source_inventory_item_id) REFERENCES source_inventory_items (id) ON DELETE CASCADE
);

CREATE INDEX ix_activity_source_period ON activity_records (source_inventory_item_id, period_start);

CREATE TABLE emission_factors (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    factor_code VARCHAR(100) NOT NULL, 
    version VARCHAR(50) NOT NULL, 
    name VARCHAR(255) NOT NULL, 
    source_category VARCHAR(100), 
    scope VARCHAR(20), 
    factor_value NUMERIC(24, 12) NOT NULL, 
    activity_unit VARCHAR(50) NOT NULL, 
    emission_unit VARCHAR(50) DEFAULT 'kgCO2e' NOT NULL, 
    geography VARCHAR(100), 
    valid_from TIMESTAMP WITH TIME ZONE, 
    valid_to TIMESTAMP WITH TIME ZONE, 
    source_organization VARCHAR(255), 
    source_document VARCHAR(500), 
    source_url VARCHAR(500), 
    method VARCHAR(100), 
    quality_rating VARCHAR(20), 
    metadata_json JSONB, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_factor_code_version UNIQUE (factor_code, version), 
    CONSTRAINT ck_factor_value_positive CHECK (factor_value >= 0)
);

CREATE INDEX ix_factors_code_version ON emission_factors (factor_code, version);

UPDATE alembic_version SET version_num='0004' WHERE alembic_version.version_num = '0003';

-- Running upgrade 0004 -> 0005

CREATE TABLE calculation_runs (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    assessment_id UUID NOT NULL, 
    methodology_version VARCHAR(50), 
    factor_set_version VARCHAR(50), 
    status VARCHAR(20) DEFAULT 'RUNNING' NOT NULL, 
    total_emissions_kgco2e NUMERIC(28, 8), 
    notes TEXT, 
    started_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    completed_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_calc_run_status CHECK (status IN ('RUNNING','COMPLETED','FAILED')), 
    FOREIGN KEY(assessment_id) REFERENCES assessments (id) ON DELETE CASCADE
);

CREATE TABLE calculation_lines (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    calculation_run_id UUID NOT NULL, 
    source_inventory_item_id UUID, 
    activity_record_id UUID, 
    emission_factor_id UUID, 
    period_start TIMESTAMP WITH TIME ZONE, 
    period_end TIMESTAMP WITH TIME ZONE, 
    original_quantity NUMERIC(24, 8), 
    original_unit VARCHAR(50), 
    normalized_quantity NUMERIC(24, 8), 
    normalized_unit VARCHAR(50), 
    conversion_multiplier NUMERIC(24, 12), 
    factor_value_snapshot NUMERIC(24, 12) NOT NULL, 
    factor_unit_snapshot VARCHAR(50), 
    emissions_kgco2e NUMERIC(28, 8) NOT NULL, 
    scope VARCHAR(20), 
    source_category VARCHAR(100), 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(calculation_run_id) REFERENCES calculation_runs (id) ON DELETE CASCADE, 
    FOREIGN KEY(source_inventory_item_id) REFERENCES source_inventory_items (id) ON DELETE SET NULL, 
    FOREIGN KEY(activity_record_id) REFERENCES activity_records (id) ON DELETE SET NULL, 
    FOREIGN KEY(emission_factor_id) REFERENCES emission_factors (id) ON DELETE SET NULL
);

CREATE INDEX ix_calc_lines_run ON calculation_lines (calculation_run_id);

UPDATE alembic_version SET version_num='0005' WHERE alembic_version.version_num = '0004';

-- Running upgrade 0005 -> 0006

CREATE TABLE final_profiles (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    assessment_id UUID NOT NULL, 
    calculation_run_id UUID, 
    version INTEGER NOT NULL, 
    total_emissions_kgco2e NUMERIC(28, 8) NOT NULL, 
    completeness_percentage NUMERIC(5, 2), 
    scope_totals_json JSONB, 
    category_totals_json JSONB, 
    source_ranking_json JSONB, 
    unquantified_sources_json JSONB, 
    profile_snapshot_json JSONB, 
    checksum VARCHAR(128), 
    finalized_by VARCHAR(255), 
    finalized_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_profile_assessment_version UNIQUE (assessment_id, version), 
    FOREIGN KEY(assessment_id) REFERENCES assessments (id) ON DELETE CASCADE, 
    FOREIGN KEY(calculation_run_id) REFERENCES calculation_runs (id) ON DELETE SET NULL
);

CREATE INDEX ix_profiles_assessment_version ON final_profiles (assessment_id, version);

CREATE TABLE audit_events (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    actor VARCHAR(255), 
    action VARCHAR(100) NOT NULL, 
    entity_type VARCHAR(100) NOT NULL, 
    entity_id UUID, 
    before_value JSONB, 
    after_value JSONB, 
    metadata_json JSONB, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id)
);

UPDATE alembic_version SET version_num='0006' WHERE alembic_version.version_num = '0005';

-- Running upgrade 0006 -> 0007

CREATE OR REPLACE VIEW monthly_emissions_summary AS
SELECT
    cr.assessment_id,
    cl.scope,
    cl.source_category,
    date_trunc('month', cl.period_start)  AS month,
    SUM(cl.emissions_kgco2e)              AS total_emissions_kgco2e,
    COUNT(*)                              AS line_count
FROM calculation_lines cl
JOIN calculation_runs cr ON cr.id = cl.calculation_run_id
WHERE cr.status = 'COMPLETED'
GROUP BY cr.assessment_id, cl.scope, cl.source_category, date_trunc('month', cl.period_start);;

CREATE OR REPLACE VIEW source_contribution_summary AS
SELECT
    cr.assessment_id,
    cr.id                                            AS calculation_run_id,
    si.source_name,
    si.source_category,
    si.scope,
    SUM(cl.emissions_kgco2e)                         AS source_emissions_kgco2e,
    cr.total_emissions_kgco2e                        AS run_total_kgco2e,
    CASE
        WHEN cr.total_emissions_kgco2e > 0
        THEN ROUND(SUM(cl.emissions_kgco2e) / cr.total_emissions_kgco2e * 100, 2)
        ELSE 0
    END                                              AS contribution_percentage
FROM calculation_lines cl
JOIN calculation_runs cr  ON cr.id = cl.calculation_run_id
JOIN source_inventory_items si ON si.id = cl.source_inventory_item_id
WHERE cr.status = 'COMPLETED'
GROUP BY cr.assessment_id, cr.id, si.source_name, si.source_category, si.scope, cr.total_emissions_kgco2e;;

UPDATE alembic_version SET version_num='0007' WHERE alembic_version.version_num = '0006';

COMMIT;

