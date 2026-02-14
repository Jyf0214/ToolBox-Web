import secrets
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.models import AppSetting

async def get_or_create_secret_key() -> str:
    key = await get_setting('secret_key')
    if not key:
        key = secrets.token_urlsafe(32)
        await set_setting('secret_key', key)
    return key

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
