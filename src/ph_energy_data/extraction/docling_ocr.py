from io import BytesIO
from typing import TYPE_CHECKING

from ph_energy_data.collectors.base import ExtractionError

if TYPE_CHECKING:
    from docling.document_converter import DocumentConverter


class DoclingOcr:
    """Reads scanned PDFs with Docling. The OCR models load on first use."""

    def __init__(self) -> None:
        self._converter: DocumentConverter | None = None

    def first_page_markdown(self, pdf: bytes) -> str:
        """OCR the first page of a (possibly scanned) PDF and return it as markdown."""
        try:
            from docling.datamodel.base_models import DocumentStream
            from docling.document_converter import DocumentConverter
            from docling.exceptions import ConversionError
        except ImportError as exc:
            raise RuntimeError("Docling is not installed; run `uv sync --extra ocr`") from exc

        if self._converter is None:
            self._converter = DocumentConverter()
        source = DocumentStream(name="document.pdf", stream=BytesIO(pdf))
        try:
            result = self._converter.convert(source, page_range=(1, 1))
        except ConversionError as exc:
            raise ExtractionError(f"unreadable PDF: {exc}") from exc
        return str(result.document.export_to_markdown())
