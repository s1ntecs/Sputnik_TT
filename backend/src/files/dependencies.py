from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_session
from src.files import service
from src.files.models import StoredFile


async def get_file_or_404(
    file_id: str,
    session: AsyncSession = Depends(get_session),
) -> StoredFile:
    return await service.get_file(session, file_id)
