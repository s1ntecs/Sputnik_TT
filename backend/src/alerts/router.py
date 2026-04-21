from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.alerts import service
from src.alerts.schemas import AlertItem
from src.core.database import get_session

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertItem])
async def list_alerts_view(session: AsyncSession = Depends(get_session)):
    return await service.list_alerts(session)
