from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import OperationalError
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
    global engine, AsyncSessionLocal

    db_url = settings.DATABASE_URL

    # 确保是 MySQL URL 并使用正确的异步驱动
    if db_url.startswith("mysql://"):
        db_url = db_url.replace("mysql://", "mysql+asyncmy://", 1)
        logger.info(
            f"Automatically updated database URL schema to: {db_url.split('@')[-1]}"
        )  # 只打印主机部分以保护敏感信息
    elif not db_url.startswith("mysql+asyncmy://"):
        logger.error(
            f"Unsupported database URL schema: {db_url}. Expected mysql+asyncmy:// or mysql://"
        )
        raise ValueError(
            "Unsupported database URL schema. Expected mysql+asyncmy:// or mysql://"
        )

    # 解析 URL 以便手动修改 SSL 参数
    from sqlalchemy.engine import URL

    parsed_url = URL.create_from_string(db_url)

    # 尝试连接 - 优先级 1: 默认 SSL (driver-dependent, 通常启用)
    try:
        logger.info("Attempting MySQL connection with default SSL...")
        engine = create_async_engine(db_url, echo=False)
        async with engine.connect() as conn:
            await conn.run_sync(lambda sync_conn: sync_conn.execute("SELECT 1"))
        logger.info("MySQL connection successful with default SSL.")
        return
    except OperationalError as e:
        if "SSL" in str(e) or "certificate" in str(e) or "handshake" in str(e):
            logger.warning(
                f"MySQL connection with default SSL failed: {e}. Attempting without SSL verification..."
            )
        else:
            logger.warning(
                f"MySQL connection with default SSL failed (non-SSL error): {e}. Attempting without SSL verification..."
            )
    except Exception as e:
        logger.warning(
            f"Unexpected error during default SSL connection attempt: {e}. Attempting without SSL verification..."
        )

    # 尝试连接 - 优先级 2: 禁用 SSL 证书验证
    # 这通常通过在 URL 中添加参数或通过 connect_args 实现。
    # asyncmy 驱动通常通过 `ssl_verify_cert=False` 或 `ssl_disabled=True` (如果支持) 来控制
    # 默认情况下，asyncmy 可能会自动启用 SSL 并验证。这里我们尝试明确关闭验证。
    # 假设可以在 connect_args 中传递 `ssl` 字典或 `ssl_verify_cert`
    try:
        logger.info("Attempting MySQL connection with SSL (no verification)...")
        # 构建新的 URL，添加 SSL 参数
        connect_args = {
            "ssl": {
                "ssl_verify_mode": ssl.CERT_NONE  # 禁用证书验证
            }
        }
        # 如果 asyncmy 不支持 ssl_verify_mode, 可能需要其他参数，例如 ssl_disabled=True
        # 但是 CERT_NONE 是标准做法
        engine = create_async_engine(db_url, echo=False, connect_args=connect_args)
        async with engine.connect() as conn:
            await conn.run_sync(lambda sync_conn: sync_conn.execute("SELECT 1"))
        logger.warning(
            "MySQL connection successful with SSL, but certificate verification was disabled. 连接SSL认证不可信。"
        )
        return
    except OperationalError as e:
        if "SSL" in str(e) or "certificate" in str(e) or "handshake" in str(e):
            logger.warning(
                f"MySQL connection with SSL (no verification) failed: {e}. Attempting without SSL at all..."
            )
        else:
            logger.warning(
                f"MySQL connection with SSL (no verification) failed (non-SSL error): {e}. Attempting without SSL at all..."
            )
    except Exception as e:
        logger.warning(
            f"Unexpected error during SSL (no verification) connection attempt: {e}. Attempting without SSL at all..."
        )

    # 尝试连接 - 优先级 3: 完全不使用 SSL
    try:
        logger.info("Attempting MySQL connection without SSL...")
        # 重建 URL，确保移除所有 SSL 参数，并可能添加明确的 disable_ssl
        new_url = parsed_url.set(
            query={k: v for k, v in parsed_url.query.items() if not k.startswith("ssl")}
        )
        # asyncmy 驱动默认会尝试 SSL, 可能需要在 connect_args 明确传递 ssl=False 或者设置 ssl_disabled=True
        # 对于 asyncmy, 可以在 drivername 中指定 no-ssl 版本或在 connect_args 中控制
        # 实际操作中，如果 URL 字符串不包含ssl相关参数，并且connect_args中不指定，asyncmy默认行为可能根据MySQL服务器配置
        # 最简单粗暴的方式是确保 URL 本身不带 ssl=true 并在 connect_args 不指定
        # asyncmy 的默认行为是如果 mysql_ssl=True (默认) 则尝试 SSL
        # 我们可以通过 `drivername` 来强制不使用 SSL
        if parsed_url.drivername == "mysql+asyncmy":
            new_url = new_url.set(drivername="mysql+asyncmy")  # Keep original driver
            # 尝试通过 connect_args 明确禁用 SSL
            engine = create_async_engine(
                new_url, echo=False, connect_args={"ssl": False}
            )  # asyncmy uses ssl=False
        else:
            engine = create_async_engine(new_url, echo=False)

        async with engine.connect() as conn:
            await conn.run_sync(lambda sync_conn: sync_conn.execute("SELECT 1"))
        logger.info("MySQL connection successful without SSL.")
        return
    except Exception as e:
        logger.error(f"MySQL connection failed without SSL after all attempts: {e}")
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


# 获取数据库 session
async def get_db():
    if AsyncSessionLocal is None:
        raise RuntimeError(
            "AsyncSessionLocal not initialized. Call create_engine_with_ssl_fallback() and create_session_local() first."
        )
    async with AsyncSessionLocal() as session:
        yield session
