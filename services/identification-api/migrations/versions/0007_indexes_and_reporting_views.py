"""0007_indexes_and_reporting_views: additional indexes + monthly_emissions_summary and source_contribution_summary views

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-12
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── reporting views ──────────────────────────────────────────────────────────

MONTHLY_EMISSIONS_VIEW = """
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
GROUP BY cr.assessment_id, cl.scope, cl.source_category, date_trunc('month', cl.period_start);
"""

SOURCE_CONTRIBUTION_VIEW = """
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
GROUP BY cr.assessment_id, cr.id, si.source_name, si.source_category, si.scope, cr.total_emissions_kgco2e;
"""


def upgrade() -> None:
    # Views
    op.execute(MONTHLY_EMISSIONS_VIEW)
    op.execute(SOURCE_CONTRIBUTION_VIEW)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS source_contribution_summary;")
    op.execute("DROP VIEW IF EXISTS monthly_emissions_summary;")
