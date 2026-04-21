import mimetypes
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.exceptions import FileNotFound, StoredFileMissing
from src.files.models import StoredFile
from src.files.storage import delete_stored, stream_to_disk


async def list_files(session: AsyncSession) -> list[StoredFile]:
    result = await session.execute(select(StoredFile).order_by(StoredFile.created_at.desc()))
    return list(result.scalars().all())


async def get_file(session: AsyncSession, file_id: str) -> StoredFile:
    file_item = await session.get(StoredFile, file_id)
    if not file_item:
        raise FileNotFound()
    return file_item


async def create_file(session: AsyncSession, title: str, upload_file: UploadFile) -> StoredFile:
    file_id, stored_name, size = await stream_to_disk(upload_file)

    mime_type = (
        upload_file.content_type
        or mimetypes.guess_type(stored_name)[0]
        or "application/octet-stream"
    )
    file_item = StoredFile(
        id=file_id,
        title=title,
        original_name=upload_file.filename or stored_name,
        stored_name=stored_name,
        mime_type=mime_type,
        size=size,
        processing_status="uploaded",
    )
    try:
        session.add(file_item)
        await session.commit()
        await session.refresh(file_item)
    except Exception:
        delete_stored(stored_name)
        raise
    return file_item


async def update_file(session: AsyncSession, file_id: str, title: str) -> StoredFile:
    file_item = await get_file(session, file_id)
    file_item.title = title
    await session.commit()
    await session.refresh(file_item)
    return file_item


async def delete_file(session: AsyncSession, file_id: str) -> None:
    file_item = await get_file(session, file_id)
    delete_stored(file_item.stored_name)
    await session.delete(file_item)
    await session.commit()


async def get_file_with_path(session: AsyncSession, file_id: str) -> tuple[StoredFile, Path]:
    file_item = await get_file(session, file_id)
    stored_path = get_settings().storage_dir / file_item.stored_name
    if not stored_path.exists():
        raise StoredFileMissing()
    return file_item, stored_path
