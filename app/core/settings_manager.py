from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.models import AppSetting

async def get_setting(key: str, default: str = "") -> str:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(AppSetting).where(AppSetting.key == key))
        setting = result.scalars().first()
        return setting.value if setting else default

async def set_setting(key: str, value: str):
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(AppSetting).where(AppSetting.key == key))
        setting = result.scalars().first()
        if setting:
            setting.value = value
        else:
            db.add(AppSetting(key=key, value=value))
        await db.commit()
