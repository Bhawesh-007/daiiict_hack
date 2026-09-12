"""0008_layer1_constraints: store recommendation constraints in Layer 1."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("assessments", sa.Column("business_constraints", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("assessments", "business_constraints")

