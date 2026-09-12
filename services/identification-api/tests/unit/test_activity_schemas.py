from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.activities import ActivityCreate


def test_activity_accepts_zero_and_preserves_original_unit():
    activity = ActivityCreate(
        period_start=datetime(2026, 1, 1, tzinfo=UTC),
        period_end=datetime(2026, 1, 31, tzinfo=UTC),
        quantity="0",
        unit_code="kWh",
    )
    assert activity.quantity == 0
    assert activity.unit_code == "kWh"


def test_activity_rejects_negative_quantity():
    with pytest.raises(ValidationError):
        ActivityCreate(
            period_start=datetime(2026, 1, 1, tzinfo=UTC),
            period_end=datetime(2026, 1, 31, tzinfo=UTC),
            quantity="-1",
            unit_code="litre",
        )


def test_activity_rejects_reversed_period():
    with pytest.raises(ValidationError, match="period_end"):
        ActivityCreate(
            period_start=datetime(2026, 2, 1, tzinfo=UTC),
            period_end=datetime(2026, 1, 31, tzinfo=UTC),
            quantity="1",
            unit_code="kg",
        )
