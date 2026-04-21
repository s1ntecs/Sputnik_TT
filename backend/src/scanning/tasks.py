import asyncio
import logging
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.alerts.service import create_alert
from src.core.config import get_settings
from src.files.models import StoredFile
from src.scanning.celery_app import celery_app
from src.scanning.metadata import extract
from src.scanning.scan import scan

logger = logging.getLogger(__name__)


def _run_with_session(coro_fn: Callable[[AsyncSession], Awaitable[None]]) -> None:
    async def runner() -> None:
        engine = create_async_engine(get_settings().database_url)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with maker() as session:
                await coro_fn(session)
        finally:
            await engine.dispose()

    asyncio.run(runner())


@celery_app.task(name="scan_file_for_threats")
def scan_file_for_threats(file_id: str) -> None:
    _run_with_session(lambda s: _scan_file_for_threats(s, file_id))


@celery_app.task(name="extract_file_metadata")
def extract_file_metadata(file_id: str) -> None:
    _run_with_session(lambda s: _extract_file_metadata(s, file_id))


@celery_app.task(name="send_file_alert")
def send_file_alert(file_id: str) -> None:
    _run_with_session(lambda s: _send_file_alert(s, file_id))


async def _scan_file_for_threats(session: AsyncSession, file_id: str) -> None:
    file_item = await session.get(StoredFile, file_id)
    if not file_item:
        logger.warning("scan: file %s not found", file_id)
        return

    file_item.processing_status = "processing"
    await session.commit()

    result = scan(file_item.original_name, file_item.mime_type, file_item.size)
    file_item.scan_status = result.status
    file_item.scan_details = result.details
    file_item.requires_attention = result.requires_attention
    await session.commit()

    extract_file_metadata.delay(file_id)


async def _extract_file_metadata(session: AsyncSession, file_id: str) -> None:
    file_item = await session.get(StoredFile, file_id)
    if not file_item:
        logger.warning("metadata: file %s not found", file_id)
        return

    stored_path = get_settings().storage_dir / file_item.stored_name
    if not stored_path.exists():
        file_item.processing_status = "failed"
        file_item.scan_status = file_item.scan_status or "failed"
        file_item.scan_details = "stored file not found during metadata extraction"
        await session.commit()
        send_file_alert.delay(file_id)
        return

    file_item.metadata_json = extract(
        stored_path,
        file_item.original_name,
        file_item.mime_type,
        file_item.size,
    )
    file_item.processing_status = "processed"
    await session.commit()

    send_file_alert.delay(file_id)


async def _send_file_alert(session: AsyncSession, file_id: str) -> None:
    file_item = await session.get(StoredFile, file_id)
    if not file_item:
        return

    if file_item.processing_status == "failed":
        level, message = "critical", "File processing failed"
    elif file_item.requires_attention:
        level, message = "warning", f"File requires attention: {file_item.scan_details}"
    else:
        level, message = "info", "File processed successfully"

    await create_alert(session, file_id=file_id, level=level, message=message)
