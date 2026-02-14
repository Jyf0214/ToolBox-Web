import os
import re
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


def get_version_from_changelog() -> str:
    """从 CHANGELOG.md 解析版本号，如果失败则返回 '0.0.0'"""
    try:
        changelog_path = os.path.join(os.getcwd(), "CHANGELOG.md")
        if not os.path.exists(changelog_path):
            return "0.0.0"
        with open(changelog_path, "r", encoding="utf-8") as f:
            for line in f:
                # 匹配 ## [x.y.z] 格式
                match = re.search(r"## \[(\d+\.\d+\.\d+)\]", line)
                if match:
                    return match.group(1)
    except (OSError, IOError, re.error):
        # 文件读取错误或正则错误时返回默认值
        return "0.0.0"
    return "0.0.0"


class Settings(BaseSettings):
    # 数据库 URL 是唯一允许的必需环境变量
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "mysql+asyncmy://user:password@localhost:3306/toolbox"
    )

    # 自动获取当前版本
    VERSION: str = get_version_from_changelog()

    # 以下配置将从数据库读取
    _SECRET_KEY: str = ""
    SITE_NAME: str = "ToolBox Web"


settings = Settings()
