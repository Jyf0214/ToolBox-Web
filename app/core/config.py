import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    # 数据库 URL 是唯一允许的必需环境变量
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./toolbox.db")
    
    # 以下配置将从数据库读取
    _SECRET_KEY: str = ""
    SITE_NAME: str = "ToolBox Web"

settings = Settings()
