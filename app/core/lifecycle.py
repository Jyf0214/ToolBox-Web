import os
import importlib
import inspect
import asyncio
from sqlalchemy import select
from nicegui import app

from app.core import database
from app.models.models import User
from app.core.database import (
    Base,
    create_engine_with_ssl_fallback,
)
from app.core.config import settings
from app.modules.base import BaseModule
from app.core.settings_manager import get_or_create_secret_key


def load_modules(modules_list, module_instances_dict):
    modules_list.clear()
    module_instances_dict.clear()
    modules_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "modules")
    if not os.path.exists(modules_dir):
        return
    for item in os.listdir(modules_dir):
        if os.path.isdir(os.path.join(modules_dir, item)) and not item.startswith("_"):
            try:
                module_pkg = importlib.import_module(f"app.modules.{item}.router")
                for name, obj in inspect.getmembers(module_pkg):
                    if (
                        inspect.isclass(obj)
                        and issubclass(obj, BaseModule)
                        and obj is not BaseModule
                    ):
                        instance = obj()
                        modules_list.append(instance)
                        module_instances_dict[instance.id] = instance
            except Exception as e:
                print(f"Failed to load module {item}: {e}")


async def sync_modules_with_db(state, modules_list):
    """
    [功能已删除] 原有的模块同步到数据库逻辑已移除。
    待重建：基于新数据库架构的模块注册机制。
    """
    if not state.db_connected:
        return
    # 逻辑已删除
    pass


async def startup_handler(state, modules_list, module_instances_dict):
    try:
        print("正在初始化数据库引擎 (强制 SSL)...")
        # 增加超时处理
        await asyncio.wait_for(create_engine_with_ssl_fallback(), timeout=30)
        state.db_connected = True

        async with database.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

            # --- 自动热补丁: 补全缺失的列 (SQLAlchemy create_all 不处理 Alter) ---
            from sqlalchemy import text

            print("正在检查数据库表结构一致性...")

            # 补齐 tools 表的列
            columns_to_add = [
                ("requires_captcha", "BOOLEAN DEFAULT FALSE NOT NULL"),
                ("rate_limit_count", "INTEGER DEFAULT 0 NOT NULL"),
                ("rate_limit_period", "INTEGER DEFAULT 60 NOT NULL"),
            ]

            for col_name, col_def in columns_to_add:
                try:
                    await conn.execute(
                        text(f"ALTER TABLE tools ADD COLUMN {col_name} {col_def}")
                    )
                    print(f"补全成功: tools.{col_name}")
                except Exception as e:
                    if (
                        "Duplicate column name" in str(e)
                        or "already exists" in str(e).lower()
                    ):
                        pass  # 已存在，忽略
                    else:
                        print(f"同步 tools.{col_name} 失败: {e}")

        print("数据库初始化与同步成功。")
    except Exception as e:
        import traceback

        print("\nFATAL: 应用启动时数据库初始化失败:")
        print(f"错误摘要: {e}")
        print("完整错误堆栈:")
        print(traceback.format_exc())
        state.db_connected = False

    if state.db_connected:
        try:
            settings._SECRET_KEY = await get_or_create_secret_key()
            app.storage.secret = settings._SECRET_KEY

            async with database.AsyncSessionLocal() as session:
                from sqlalchemy import func

                # 使用 count 聚合查询更高效
                result = await session.execute(
                    select(func.count(User.id)).where(User.is_admin)
                )
                admin_count = result.scalar()

            state.needs_setup = admin_count == 0
            print(
                f"管理员账号检查完成: 已存在 {admin_count} 个管理员。Needs Setup: {state.needs_setup}"
            )
        except Exception as e:
            print(f"初始化管理员检查过程中出错: {e}")
            # 如果是表不存在等错误，通常发生在初始化中，设为 True
            state.needs_setup = True
    else:
        # 数据库未连上时，保持 True 允许用户去 /setup 页面等待或修复
        state.needs_setup = True

    load_modules(modules_list, module_instances_dict)
    # await sync_modules_with_db(state, modules_list) # 已禁用

    for m in modules_list:
        m.setup_api()
        app.include_router(m.router)

    state.initialized.set()
