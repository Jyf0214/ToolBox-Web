import ssl
import logging
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import text
from app.core.config import settings

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# SQLAlchemy 基类
Base = declarative_base()

# 全局变量
engine = None
AsyncSessionLocal = None


async def test_connection_with_timeout(db_url, connect_args, timeout=10.0):
    """
    在一个独立的任务中测试数据库连接，确保超时控制有效。
    """
    temp_engine = create_async_engine(
        db_url, connect_args=connect_args, pool_pre_ping=True
    )
    try:
        async with temp_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return temp_engine
    except Exception as e:
        await temp_engine.dispose()
        raise e


async def create_engine_with_ssl_fallback():
    """
    创建数据库引擎，强制使用 SSL。
    如果第一次握手因为证书不可信失败或超时，则在下一次尝试中信任该证书。
    严禁使用非 SSL 连接。
    """
    global engine, AsyncSessionLocal

    db_url = settings.DATABASE_URL

    # 1. 自动处理协议头
    if db_url.startswith("mysql://"):
        db_url = db_url.replace("mysql://", "mysql+asyncmy://", 1)
        print("DEBUG: 自动修正数据库协议头为 mysql+asyncmy://")
    elif not db_url.startswith("mysql+asyncmy://"):
        print(f"CRITICAL: 不支持的数据库协议: {db_url.split('://')[0]}")
        raise ValueError("Unsupported database dialect. Use mysql+asyncmy://")

    # 2. 全局禁止不安全的连接参数
    if "ssl=disabled" in db_url.lower() or "ssl=false" in db_url.lower():
        print("CRITICAL: 检测到不安全的连接字符串参数 (ssl=disabled/false)，已拒绝。")
        raise ValueError("Insecure database connections are strictly prohibited.")

    # 3. 第一次尝试：使用标准 SSL 验证
    print("\n[1/2] 正在尝试标准 SSL 连接... (超时设定: 10s)")
    print(f"目标节点: {db_url.split('@')[-1]}")

    try:
        engine = await asyncio.wait_for(
            test_connection_with_timeout(db_url, {"ssl": True}), timeout=10.0
        )
        print("SUCCESS: 标准 SSL 连接验证通过。")
    except (asyncio.TimeoutError, Exception) as e:
        error_msg = str(e) or "Connection Handshake Timeout"
        print(f"反馈: 第一次连接尝试未通过。原因: {error_msg}")

        # 4. 第二次尝试：TOFU 模式 (信任证书并强制 SSL 加密)
        print("\n[2/2] 正在切换至 TOFU 模式 (信任证书并强制 SSL 加密)...")

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        try:
            engine = await asyncio.wait_for(
                test_connection_with_timeout(db_url, {"ssl": ctx}), timeout=15.0
            )
            print("SUCCESS: TOFU 加密连接建立成功。")
        except Exception as retry_e:
            print(f"FATAL: 数据库所有加密连接尝试均失败: {retry_e}")
            raise retry_e

    # 5. 初始化 Session 工厂
    AsyncSessionLocal = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )


def create_session_local():
    global AsyncSessionLocal
    if AsyncSessionLocal is None:
        raise RuntimeError("Database engine not initialized.")
    return AsyncSessionLocal


async def get_db():
    if AsyncSessionLocal is None:
        await create_engine_with_ssl_fallback()
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
