import asyncio
from datetime import datetime
from fastapi import APIRouter
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
    fingerprint: str, ip: str, initialized_event: asyncio.Event, db_connected: bool
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
        if not guest:
            guest = Guest(fingerprint=fingerprint, ip_address=ip)
            session.add(guest)
        else:
            guest.ip_address = ip
            guest.last_seen = datetime.utcnow()
        await session.commit()


# 注意：这个路由需要能够访问全局状态 state
# 我们将在 main.py 中通过依赖或闭包来注册它，或者直接在这里引用
def setup_tracking_api(state):
    @router.post("/track_guest")
    async def track_guest(data: GuestData):
        await get_or_create_guest(
            data.fingerprint, data.ip, state.initialized, state.db_connected
        )
        return {"status": "ok"}

    return router
