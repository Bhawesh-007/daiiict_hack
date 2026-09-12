"""Safe parsing helpers for imported activity-data CSV and PDF files."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO
from typing import Any


class ActivityImportError(ValueError):
    """Raised for invalid or unsupported activity-data uploads."""


@dataclass(frozen=True)
class ImportedActivity:
    source_reference: str
    quantity: Decimal
    unit_code: str
    period_start: datetime | None = None
    period_end: datetime | None = None
    evidence_reference: str | None = None
    notes: str | None = None


_SOURCE_HEADERS = ("source_key", "source", "source_name", "emission_source")
_QUANTITY_HEADERS = ("quantity", "value", "amount", "consumption", "activity_quantity")
_UNIT_HEADERS = ("unit", "unit_code", "uom")
_START_HEADERS = ("period_start", "start_date", "from_date")
_END_HEADERS = ("period_end", "end_date", "to_date")
_LINE = re.compile(
    r"(?P<source>[A-Za-z][A-Za-z0-9 _/()&.-]{2,}?)\s*[:,-]\s*"
    r"(?P<quantity>\d+(?:\.\d+)?)\s*(?P<unit>[A-Za-z][A-Za-z0-9_-]*)"
)


def _key(value: str) -> str:
    return "_".join(value.strip().lower().replace("-", " ").split())


def _first(row: dict[str, str], candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        value = row.get(candidate)
        if value:
            return value.strip()
    return None


def _date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError as exc:
        raise ActivityImportError(f"Invalid date: {value}") from exc


def _activity(source: str | None, quantity: str | None, unit: str | None, **kwargs: Any) -> ImportedActivity:
    if not source or quantity is None or not unit:
        raise ActivityImportError("Each imported row needs source, quantity, and unit")
    try:
        value = Decimal(quantity.replace(",", ""))
    except (InvalidOperation, AttributeError) as exc:
        raise ActivityImportError(f"Invalid quantity for {source}: {quantity}") from exc
    if value < 0:
        raise ActivityImportError(f"Quantity cannot be negative for {source}")
    return ImportedActivity(source_reference=source, quantity=value, unit_code=unit, **kwargs)


def parse_csv(payload: bytes) -> list[ImportedActivity]:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ActivityImportError("CSV must be UTF-8 encoded") from exc
    reader = csv.DictReader(StringIO(text))
    if not reader.fieldnames:
        raise ActivityImportError("CSV needs a header row")
    rows: list[ImportedActivity] = []
    for raw in reader:
        row = {_key(key): str(value or "").strip() for key, value in raw.items() if key}
        if not any(row.values()):
            continue
        rows.append(
            _activity(
                _first(row, _SOURCE_HEADERS),
                _first(row, _QUANTITY_HEADERS),
                _first(row, _UNIT_HEADERS),
                period_start=_date(_first(row, _START_HEADERS)),
                period_end=_date(_first(row, _END_HEADERS)),
                evidence_reference=row.get("evidence_reference") or row.get("reference"),
                notes=row.get("notes"),
            )
        )
    if not rows:
        raise ActivityImportError("No activity rows were found in the CSV")
    return rows


def parse_pdf(payload: bytes) -> list[ImportedActivity]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ActivityImportError("PDF import requires the pypdf package") from exc
    try:
        text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(payload)).pages)
    except Exception as exc:
        raise ActivityImportError("The PDF could not be read; upload a text-based PDF or CSV") from exc
    rows = [
        _activity(match.group("source"), match.group("quantity"), match.group("unit"))
        for match in _LINE.finditer(text)
    ]
    if not rows:
        raise ActivityImportError(
            "No source, quantity, and unit rows were detected in the PDF; use a CSV for scanned PDFs"
        )
    return rows


def parse_activity_file(filename: str, payload: bytes) -> list[ImportedActivity]:
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix == "csv":
        return parse_csv(payload)
    if suffix == "pdf":
        return parse_pdf(payload)
    raise ActivityImportError("Upload a .csv or .pdf file")
