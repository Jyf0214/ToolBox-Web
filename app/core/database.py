from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import text
from app.core.config import settings
import ssl
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# SQLAlchemy 基类
Base = declarative_base()

# 初始化引擎的占位符
engine = None
AsyncSessionLocal = None


async def create_engine_with_ssl_fallback():
    global engine

    db_url = settings.DATABASE_URL

    # 确保是 MySQL URL 并使用正确的异步驱动
    if db_url.startswith("mysql://"):
        db_url = db_url.replace("mysql://", "mysql+asyncmy://", 1)
        logger.info(
            f"Automatically updated database URL schema to: {db_url.split('@')[-1]}"
        )
    elif not db_url.startswith("mysql+asyncmy://"):
        logger.error(
            f"Unsupported database URL schema: {db_url}. Expected mysql+asyncmy:// or mysql://"
        )
        raise ValueError(
            "Unsupported database URL schema. Expected mysql+asyncmy:// or mysql://"
        )

    # 优先级 1: 默认 SSL (driver-dependent)
    try:
        logger.info("Attempting MySQL connection with default SSL...")
        temp_engine = create_async_engine(db_url, echo=False)
        async with temp_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("MySQL connection successful with default SSL.")
        engine = temp_engine
        return
    except Exception as e:
        logger.warning(f"Default SSL connection failed: {e}. Trying next method...")

    # 优先级 2: 显式禁用 SSL 证书验证 (用于自签名或不可信证书)
    try:
        logger.info("Attempting MySQL connection with SSL (no verification)...")
        # 创建显式的 SSL 上下文并禁用验证
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        # 使用 connect_args 传递 SSL 上下文
        temp_engine = create_async_engine(db_url, echo=False, connect_args={"ssl": ctx})
        async with temp_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.warning("MySQL connection successful with SSL (verification disabled).")
        engine = temp_engine
        return
    except Exception as e:
        logger.warning(
            f"SSL (no verification) connection failed: {e}. Trying next method..."
        )

    # 优先级 3: 完全不使用 SSL (TiDB Cloud 通常会拒绝)
    try:
        logger.info("Attempting MySQL connection without SSL...")
        # 显式禁用 SSL
        temp_engine = create_async_engine(
            db_url, echo=False, connect_args={"ssl": False}
        )
        async with temp_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("MySQL connection successful without SSL.")
        engine = temp_engine
        return
    except Exception as e:
        logger.error(f"MySQL connection failed after all attempts: {e}")
        raise


# 创建 SessionLocal
def create_session_local():
    global AsyncSessionLocal
    if engine is None:
        raise RuntimeError(
            "Database engine not initialized. Call create_engine_with_ssl_fallback() first."
        )
    AsyncSessionLocal = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    logger.info("AsyncSessionLocal initialized successfully.")


# 获取数据库 session
async def get_db():
    if AsyncSessionLocal is None:
        raise RuntimeError(
            "AsyncSessionLocal not initialized. Call create_engine_with_ssl_fallback() and create_session_local() first."
        )
    async with AsyncSessionLocal() as session:
        yield session
