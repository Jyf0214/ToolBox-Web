import asyncio
from datetime import datetime
from fastapi import APIRouter, Request
from pydantic import BaseModel
from nicegui import ui
from sqlalchemy import select

from app.core import database
from app.models.models import Guest

router = APIRouter(prefix="/api")


class GuestData(BaseModel):
    fingerprint: str
    ip: str


async def get_or_create_guest(
    fingerprint: str, ip: str, user_agent: str, initialized_event: asyncio.Event, db_connected: bool
):
    try:
        await asyncio.wait_for(initialized_event.wait(), timeout=10)
    except asyncio.TimeoutError:
        ui.notify("数据库连接超时。", color="negative")
        return

    if not db_connected:
        return

    async with database.AsyncSessionLocal() as session:
        result = await session.execute(
            select(Guest).where(Guest.fingerprint == fingerprint)
        )
        guest = result.scalars().first()
        
        metadata = {"user_agent": user_agent}
        
        if not guest:
            guest = Guest(
                fingerprint=fingerprint, 
                ip_address=ip,
                metadata_json=metadata
            )
            session.add(guest)
        else:
            guest.ip_address = ip
            guest.last_seen = datetime.utcnow()
            guest.metadata_json = metadata
        await session.commit()


# 注意：这个路由需要能够访问全局状态 state
def setup_tracking_api(state):
    @router.post("/track_guest")
    async def track_guest(data: GuestData, request: Request):
        user_agent = request.headers.get("user-agent", "Unknown")
        await get_or_create_guest(
            data.fingerprint, data.ip, user_agent, state.initialized, state.db_connected
        )
        return {"status": "ok"}

    return router
