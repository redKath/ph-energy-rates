from enum import StrEnum


class UtilityType(StrEnum):
    PRIVATE_DU = "private_du"
    ELECTRIC_COOPERATIVE = "electric_cooperative"
    SUPPLIER = "supplier"


class CustomerClass(StrEnum):
    RESIDENTIAL = "residential"


class ExtractionMethod(StrEnum):
    HTML_PARSER = "html_parser"
    PDF_PARSER = "pdf_parser"
    OCR_PARSER = "ocr_parser"
    LLM = "llm"
    MANUAL = "manual"


class RateBasis(StrEnum):
    # Total per kWh as printed by the source.
    PUBLISHED_TOTAL = "published_total"
    # Total computed by summing published per-kWh components.
    SUMMED_COMPONENTS = "summed_components"


class RateStatus(StrEnum):
    PUBLISHED = "published"
    FLAGGED = "flagged"
    REJECTED = "rejected"


class RunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
