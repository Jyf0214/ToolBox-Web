import secrets
import os
from sqlalchemy import select
from app.core import database
from app.models.models import AppSetting

SECRET_FILE = ".secret_key"


def get_local_secret() -> str:
    """从本地文件获取密钥，如果不存在则创建"""
    if os.path.exists(SECRET_FILE):
        with open(SECRET_FILE, "r") as f:
            return f.read().strip()
    key = secrets.token_urlsafe(32)
    with open(SECRET_FILE, "w") as f:
        f.write(key)
    return key


async def get_or_create_secret_key() -> str:
    # 优先使用数据库中的密钥
    if database.AsyncSessionLocal is not None:
        key = await get_setting("secret_key")
        if key:
            return key

    # 如果数据库没有，或者没连上，使用本地文件的密钥
    local_key = get_local_secret()

    # 如果数据库连上了但没存，存进去
    if database.AsyncSessionLocal is not None:
        await set_setting("secret_key", local_key)

    return local_key


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
