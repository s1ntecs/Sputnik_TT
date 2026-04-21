import re
from pathlib import Path

PDF_PAGE_RE = re.compile(rb"/Type\s*/Page(?![a-zA-Z])")


def extract(stored_path: Path, original_name: str, mime_type: str, size: int) -> dict:
    metadata: dict = {
        "extension": Path(original_name).suffix.lower(),
        "size_bytes": size,
        "mime_type": mime_type,
    }

    if mime_type.startswith("text/"):
        content = stored_path.read_text(encoding="utf-8", errors="ignore")
        metadata["line_count"] = len(content.splitlines())
        metadata["char_count"] = len(content)
    elif mime_type == "application/pdf":
        metadata["approx_page_count"] = _count_pdf_pages(stored_path)

    return metadata


def _count_pdf_pages(path: Path) -> int:
    data = path.read_bytes()
    count = len(PDF_PAGE_RE.findall(data))
    return max(count, 1)
