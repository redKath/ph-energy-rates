from functools import lru_cache
from io import BytesIO
from typing import Any


@lru_cache
def _converter() -> Any:
    try:
        from docling.document_converter import DocumentConverter
    except ImportError as exc:
        raise RuntimeError("Docling is not installed; run `uv sync --extra ocr`") from exc
    return DocumentConverter()


def first_page_markdown(pdf: bytes) -> str:
    """OCR the first page of a (possibly scanned) PDF and return it as markdown."""
    from docling.datamodel.base_models import DocumentStream

    source = DocumentStream(name="document.pdf", stream=BytesIO(pdf))
    result = _converter().convert(source, page_range=(1, 1))
    return str(result.document.export_to_markdown())
