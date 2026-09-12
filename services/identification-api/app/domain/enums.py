"""Shared domain enums matching database CHECK constraints."""

from enum import Enum


class FlowDirection(str, Enum):
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"


class ProcessOutsourcing(str, Enum):
    YES = "YES"
    NO = "NO"


class CandidateOrigin(str, Enum):
    TEMPLATE = "TEMPLATE"
    RULE = "RULE"
    ML = "ML"
    CHECKLIST = "CHECKLIST"
    USER = "USER"


class CandidateStatus(str, Enum):
    PROPOSED = "PROPOSED"
    MERGED = "MERGED"
    DISMISSED = "DISMISSED"
    PROMOTED = "PROMOTED"


class InventoryStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    POTENTIAL = "POTENTIAL"
    MISSING_INFORMATION = "MISSING_INFORMATION"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    OUTSOURCED = "OUTSOURCED"


class ChecklistStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    POTENTIAL = "POTENTIAL"
    MISSING_INFORMATION = "MISSING_INFORMATION"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    OUTSOURCED = "OUTSOURCED"
