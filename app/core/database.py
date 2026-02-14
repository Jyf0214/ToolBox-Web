import ssl
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from app.core.config import settings

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# SQLAlchemy 基类
Base = declarative_base()

# 全局变量
engine = None
AsyncSessionLocal = None


async def create_engine_with_ssl_fallback():
    """
    创建数据库引擎，强制使用 SSL。
    如果第一次握手因为证书不可信失败，则在下一次尝试中信任该证书。
    严禁使用非 SSL 连接。
    """
    global engine, AsyncSessionLocal

    db_url = settings.DATABASE_URL

    # 全局禁止不安全的连接方式
    # 检查 DATABASE_URL 中是否包含试图禁用 SSL 的参数
    if "ssl=disabled" in db_url.lower() or "ssl=false" in db_url.lower():
        logger.error(
            "Insecure connection strings are banned. Please remove ssl=disabled or ssl=false."
        )
        raise ValueError("Insecure database connections are strictly prohibited.")

    # 第一次尝试：使用标准 SSL 验证
    # connect_args={"ssl": True} 会强制启用 SSL
    connect_args = {"ssl": True}

    logger.info("Attempting to connect to database with mandatory SSL...")

    try:
        temp_engine = create_async_engine(
            db_url, connect_args=connect_args, pool_pre_ping=True
        )
        # 测试连接
        async with temp_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        engine = temp_engine
        logger.info("Database connected successfully with verified SSL.")
    except (OperationalError, Exception) as e:
        error_msg = str(e)
        # 捕获 SSL 证书验证失败相关的错误
        if any(
            err in error_msg
            for err in [
                "CERTIFICATE_VERIFY_FAILED",
                "certificate verify failed",
                "SSL certificate validation",
            ]
        ):
            logger.warning(
                "SSL certificate verification failed. Retrying with Trust-On-First-Use (trusting untrusted certificate)..."
            )

            # 创建一个不验证 CA 的 SSL 上下文，但仍然加密
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            connect_args_tofu = {"ssl": ctx}

            try:
                temp_engine_tofu = create_async_engine(
                    db_url, connect_args=connect_args_tofu, pool_pre_ping=True
                )
                async with temp_engine_tofu.connect() as conn:
                    await conn.execute(text("SELECT 1"))
                engine = temp_engine_tofu
                logger.info(
                    "Database connected successfully with SSL (untrusted certificate accepted)."
                )
            except Exception as retry_e:
                logger.error(
                    f"Database connection failed even after trusting certificate: {retry_e}"
                )
                raise retry_e
        else:
            logger.error(f"Database connection failed: {error_msg}")
            raise e

    # 初始化 Session 工厂
    AsyncSessionLocal = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )


def create_session_local():
    """
    确保 AsyncSessionLocal 已初始化。
    """
    global AsyncSessionLocal
    if AsyncSessionLocal is None:
        raise RuntimeError(
            "Database engine not initialized. Call create_engine_with_ssl_fallback first."
        )
    return AsyncSessionLocal


async def get_db():
    """
    FastAPI 依赖注入使用的数据库 Session 生成器。
    """
    if AsyncSessionLocal is None:
        await create_engine_with_ssl_fallback()

    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
