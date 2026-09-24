from pathlib import Path

from ..verification.binary import MAGIC


def detect_magic(path: str | Path) -> str | None:
    with Path(path).open("rb") as handle:
        prefix = handle.read(8)
    return next((mime for magic, mime in MAGIC.items() if prefix.startswith(magic)), None)


def extract_identity(path: str | Path, mime_type: str, max_pages: int = 10) -> dict:
    """Extract bounded identity text without invoking office applications."""
    target = Path(path)
    mime = (mime_type or detect_magic(target) or "").split(";", 1)[0].lower()
    if mime == "application/pdf":
        import pymupdf
        document = pymupdf.open(target)
        pages = min(len(document), max_pages)
        text = "\n".join(document[index].get_text() for index in range(pages))
        document.close()
        return {"text": text, "identity_source": "BINARY_CONTENT", "pages_read": pages,
                "page_range": [1, pages], "extractor": "pymupdf"}
    if mime in {"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/zip"}:
        from docx import Document
        document = Document(target)
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        return {"text": text, "identity_source": "BINARY_CONTENT", "pages_read": None,
                "page_range": None, "extractor": "python-docx"}
    return {"text": "", "identity_source": "BINARY_UNSUPPORTED", "pages_read": 0,
            "page_range": None, "extractor": None}
