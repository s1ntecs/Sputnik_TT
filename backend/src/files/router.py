from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_session
from src.files import service
from src.files.dependencies import get_file_or_404
from src.files.models import StoredFile
from src.files.schemas import FileItem, FileUpdate
from src.scanning.tasks import scan_file_for_threats

router = APIRouter(prefix="/files", tags=["files"])

TitleForm = Annotated[str, Form(min_length=1, max_length=255)]


@router.get("", response_model=list[FileItem])
async def list_files_view(session: AsyncSession = Depends(get_session)):
    return await service.list_files(session)


@router.post("", response_model=FileItem, status_code=status.HTTP_201_CREATED)
async def create_file_view(
    title: TitleForm,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    file_item = await service.create_file(session, title=title, upload_file=file)
    scan_file_for_threats.delay(file_item.id)
    return file_item


@router.get("/{file_id}", response_model=FileItem)
async def get_file_view(file_item: StoredFile = Depends(get_file_or_404)):
    return file_item


@router.patch("/{file_id}", response_model=FileItem)
async def update_file_view(
    file_id: str,
    payload: FileUpdate,
    session: AsyncSession = Depends(get_session),
):
    return await service.update_file(session, file_id=file_id, title=payload.title)


@router.get("/{file_id}/download")
async def download_file(
    file_id: str,
    session: AsyncSession = Depends(get_session),
):
    file_item, stored_path = await service.get_file_with_path(session, file_id)
    encoded = quote(file_item.original_name)
    return FileResponse(
        path=stored_path,
        media_type=file_item.mime_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"
        },
    )


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file_view(
    file_id: str,
    session: AsyncSession = Depends(get_session),
):
    await service.delete_file(session, file_id)
