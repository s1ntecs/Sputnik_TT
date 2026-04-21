from pathlib import Path
from uuid import uuid4

import aiofiles
from fastapi import UploadFile

from src.core.config import get_settings
from src.core.exceptions import EmptyUpload


async def stream_to_disk(upload_file: UploadFile) -> tuple[str, str, int]:
    """
    Пишет upload_file на диск чанками, считает итоговый размер на лету.
    Возвращает (file_id, stored_name, size_bytes).
    Если файл оказался пустым — удаляет его с диска и бросает EmptyUpload.
    """
    settings = get_settings()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)

    file_id = str(uuid4())
    suffix = Path(upload_file.filename or "").suffix
    stored_name = f"{file_id}{suffix}"
    stored_path = settings.storage_dir / stored_name

    size = 0
    async with aiofiles.open(stored_path, "wb") as out:
        while chunk := await upload_file.read(settings.upload_chunk_size):
            await out.write(chunk)
            size += len(chunk)

    if size == 0:
        stored_path.unlink(missing_ok=True)
        raise EmptyUpload()

    return file_id, stored_name, size


def delete_stored(stored_name: str) -> None:
    settings = get_settings()
    path = settings.storage_dir / stored_name
    path.unlink(missing_ok=True)
