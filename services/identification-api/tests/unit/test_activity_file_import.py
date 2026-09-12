from datetime import UTC, datetime
from decimal import Decimal

import pytest
from app.domain.activities.file_import import ActivityImportError, parse_activity_file


def test_csv_import_detects_common_headers_and_values():
    rows = parse_activity_file(
        "activity.csv",
        b"Source Name,Quantity,Unit,Period Start,Period End\n"
        b"Purchased grid electricity,12000,kWh,2025-04-01,2026-03-31\n"
        b"Stationary fuel combustion,1000,litre,2025-04-01,2026-03-31\n",
    )
    assert len(rows) == 2
    assert rows[0].source_reference == "Purchased grid electricity"
    assert rows[0].quantity == Decimal(12000)
    assert rows[0].unit_code == "kWh"
    assert rows[0].period_start == datetime(2025, 4, 1, tzinfo=UTC)


def test_csv_import_rejects_missing_required_values():
    with pytest.raises(ActivityImportError, match="source, quantity, and unit"):
        parse_activity_file("activity.csv", b"source,quantity,unit\nBoiler,100,\n")


def test_import_rejects_unknown_file_type():
    with pytest.raises(ActivityImportError, match=".csv or .pdf"):
        parse_activity_file("activity.xlsx", b"not supported")
