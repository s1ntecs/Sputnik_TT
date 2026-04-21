from dataclasses import dataclass
from pathlib import Path

SUSPICIOUS_EXTENSIONS = frozenset({".exe", ".bat", ".cmd", ".sh", ".js"})
MAX_SIZE_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class ScanResult:
    status: str
    details: str
    requires_attention: bool


def scan(original_name: str, mime_type: str, size: int) -> ScanResult:
    reasons: list[str] = []
    extension = Path(original_name).suffix.lower()

    if extension in SUSPICIOUS_EXTENSIONS:
        reasons.append(f"suspicious extension {extension}")
    if size > MAX_SIZE_BYTES:
        reasons.append("file is larger than 10 MB")
    if extension == ".pdf" and mime_type not in {"application/pdf", "application/octet-stream"}:
        reasons.append("pdf extension does not match mime type")

    if reasons:
        return ScanResult(status="suspicious", details=", ".join(reasons), requires_attention=True)
    return ScanResult(status="clean", details="no threats found", requires_attention=False)
