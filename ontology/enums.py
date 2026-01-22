from enum import Enum

class EntityType(str, Enum):
    CONCEPT = "Concept"
    EVENT = "Event"
    PROCESS = "Process"
    OBJECT = "Object"
    PERSON = "Person"
    ORGANIZATION = "Organization"
    PLACE = "Place"

class UsageContext(str, Enum):
    DEFINITION = "definition"
    DOCTRINAL_CLAIM = "doctrinal_claim"
    HISTORICAL_REPORT = "historical_report"
    OBSERVATION = "observation"
    HYPOTHESIS = "hypothesis"
    INTERPRETATION = "interpretation"
    COMPARISON = "comparison"
    REFUTATION = "refutation"

class UncertaintyLevel(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
