import secrets
from sqlalchemy import select
from app.core import database
from app.models.models import AppSetting


async def get_or_create_secret_key() -> str:
    # 只有在数据库连接时才尝试获取或创建密钥
    if database.AsyncSessionLocal is None:  # 数据库未连接，无法从 DB 获取/保存密钥
        return secrets.token_urlsafe(32)  # 直接生成一个临时密钥

    key = await get_setting("secret_key")
    if not key:
        key = secrets.token_urlsafe(32)
        await set_setting("secret_key", key)
    return key


async def get_setting(key: str, default: str = "") -> str:
    if database.AsyncSessionLocal is None:  # 数据库未连接
        return default

    async with database.AsyncSessionLocal() as session:
        result = await session.execute(select(AppSetting).where(AppSetting.key == key))
        setting = result.scalars().first()
        return setting.value if setting else default


async def set_setting(key: str, value: str):
    if database.AsyncSessionLocal is None:  # 数据库未连接
        return  # 无法保存设置

    async with database.AsyncSessionLocal() as session:
        result = await session.execute(select(AppSetting).where(AppSetting.key == key))
        setting = result.scalars().first()
        if setting:
            setting.value = value
        else:
            session.add(AppSetting(key=key, value=value))
        await session.commit()
