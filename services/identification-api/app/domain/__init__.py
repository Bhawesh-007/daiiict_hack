"""Domain module initialization."""

from app.domain.enums import (
    CandidateOrigin,
    CandidateStatus,
    ChecklistStatus,
    FlowDirection,
    InventoryStatus,
    ProcessOutsourcing,
)

__all__ = [
    "FlowDirection",
    "ProcessOutsourcing",
    "CandidateOrigin",
    "CandidateStatus",
    "InventoryStatus",
    "ChecklistStatus",
]
