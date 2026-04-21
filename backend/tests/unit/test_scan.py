from src.scanning.scan import scan


def test_clean_pdf_with_matching_mime():
    result = scan("doc.pdf", "application/pdf", 1024)
    assert result.status == "clean"
    assert result.requires_attention is False


def test_exe_is_suspicious():
    result = scan("installer.exe", "application/octet-stream", 1024)
    assert result.status == "suspicious"
    assert "suspicious extension .exe" in result.details


def test_oversized_file_is_suspicious():
    result = scan("huge.txt", "text/plain", 11 * 1024 * 1024)
    assert result.status == "suspicious"
    assert "larger than 10 MB" in result.details


def test_pdf_with_wrong_mime_is_suspicious():
    result = scan("doc.pdf", "image/jpeg", 1024)
    assert result.status == "suspicious"
    assert "pdf extension does not match mime type" in result.details


def test_multiple_reasons_combined():
    result = scan("script.sh", "text/plain", 20 * 1024 * 1024)
    assert result.status == "suspicious"
    assert "suspicious extension .sh" in result.details
    assert "larger than 10 MB" in result.details
