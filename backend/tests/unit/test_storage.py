import io

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from src.core.exceptions import EmptyUpload
from src.files.storage import stream_to_disk


class _ReadTrackingStream(io.BytesIO):
    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self.read_calls: list[int] = []

    def read(self, size: int = -1) -> bytes:
        self.read_calls.append(size)
        return super().read(size)


def _make_upload(content: bytes, filename: str = "test.txt") -> tuple[UploadFile, _ReadTrackingStream]:
    stream = _ReadTrackingStream(content)
    upload = UploadFile(
        file=stream,
        filename=filename,
        headers=Headers({"content-type": "text/plain"}),
    )
    return upload, stream


async def test_stream_to_disk_writes_file_and_returns_correct_size(isolated_storage):
    data = b"x" * (3 * 1024 * 1024 + 123)
    upload, _ = _make_upload(data, "big.bin")

    _, stored_name, size = await stream_to_disk(upload)

    assert size == len(data)
    assert (isolated_storage / stored_name).read_bytes() == data


async def test_stream_to_disk_reads_in_chunks_not_whole_file(isolated_storage):
    chunk_size = 1024 * 1024
    data = b"x" * (chunk_size * 3 + 7)
    upload, stream = _make_upload(data, "big.bin")

    await stream_to_disk(upload)

    assert len(stream.read_calls) > 1, f"expected chunked reads, got {stream.read_calls}"
    assert all(s > 0 for s in stream.read_calls), stream.read_calls
    assert max(stream.read_calls) == chunk_size


async def test_stream_to_disk_empty_file_raises_and_cleans_up(isolated_storage):
    upload, _ = _make_upload(b"", "empty.txt")

    with pytest.raises(EmptyUpload):
        await stream_to_disk(upload)

    assert list(isolated_storage.iterdir()) == []
