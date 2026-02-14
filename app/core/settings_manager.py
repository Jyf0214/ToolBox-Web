import secrets
from app.models.models import AppSetting


async def get_or_create_secret_key() -> str:
    key = await get_setting("secret_key")
    if not key:
        key = secrets.token_urlsafe(32)
        await set_setting("secret_key", key)
    return key


async def get_setting(key: str, default: str = "") -> str:
    setting = await AppSetting.find_one(AppSetting.key == key)
    return setting.value if setting else default


async def set_setting(key: str, value: str):
    setting = await AppSetting.find_one(AppSetting.key == key)
    if setting:
        setting.value = value
        await setting.save()
    else:
        setting = AppSetting(key=key, value=value)
        await setting.insert()
