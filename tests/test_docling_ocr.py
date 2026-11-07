import sys

import pytest

from ph_energy_data.collectors.base import ExtractionError
from ph_energy_data.extraction.docling_ocr import DoclingOcr


def test_missing_docling_install_explains_how_to_fix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "docling.document_converter", None)
    with pytest.raises(RuntimeError, match="--extra ocr"):
        DoclingOcr().first_page_markdown(b"%PDF")


def test_unreadable_pdf_raises_extraction_error() -> None:
    pytest.importorskip("docling")
    with pytest.raises(ExtractionError, match="unreadable PDF"):
        DoclingOcr().first_page_markdown(b"not a pdf")
