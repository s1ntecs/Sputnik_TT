import io
from unittest.mock import AsyncMock

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from src.files import service


@pytest.fixture
def fake_upload() -> UploadFile:
    return UploadFile(
        file=io.BytesIO(b"content"),
        filename="a.txt",
        headers=Headers({"content-type": "text/plain"}),
    )


async def test_create_file_removes_stored_file_when_commit_fails(
    isolated_storage,
    fake_upload,
):
    failing_session = AsyncMock()
    failing_session.add = lambda _obj: None
    failing_session.commit.side_effect = RuntimeError("db down")

    with pytest.raises(RuntimeError):
        await service.create_file(failing_session, title="x", upload_file=fake_upload)

    assert list(isolated_storage.iterdir()) == []
