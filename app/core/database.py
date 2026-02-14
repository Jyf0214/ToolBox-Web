from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

# MongoDB 客户端
client = AsyncIOMotorClient(settings.DATABASE_URL)

# 获取数据库实例（从 URL 中解析或使用默认值）
# 如果 DATABASE_URL 中没有指定数据库名，motor 默认使用 'test'
# 我们可以从 URL 中提取，或者在配置中指定
db_name = settings.DATABASE_URL.split("/")[-1].split("?")[0] or "toolbox"
db = client[db_name]
