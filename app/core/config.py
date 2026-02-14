import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    # 唯一允许的硬编码环境变量
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./toolbox.db")
    
    # 以下配置应在数据库中存储，这里提供默认值
    SECRET_KEY: str = os.getenv("SECRET_KEY", "temporary-secret-key")
    ADMIN_PASSWORD_HASH: str = "" # 将在初始化时设置
    SITE_NAME: str = "ToolBox Web"

settings = Settings()
