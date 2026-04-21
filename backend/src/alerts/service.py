from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.alerts.models import Alert


async def list_alerts(session: AsyncSession) -> list[Alert]:
    result = await session.execute(select(Alert).order_by(Alert.created_at.desc()))
    return list(result.scalars().all())


async def create_alert(session: AsyncSession, file_id: str, level: str, message: str) -> Alert:
    alert = Alert(file_id=file_id, level=level, message=message)
    session.add(alert)
    await session.commit()
    await session.refresh(alert)
    return alert
