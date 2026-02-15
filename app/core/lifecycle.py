import os
import importlib
import inspect
import asyncio
from sqlalchemy import select
from nicegui import app

from app.core import database
from app.models.models import AdminConfig
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
    if not state.db_connected:
        return
    pass


async def startup_handler(state, modules_list, module_instances_dict):
    try:
        print("正在初始化数据库引擎 (强制 SSL)...")
        await asyncio.wait_for(create_engine_with_ssl_fallback(), timeout=30)
        state.db_connected = True

        async with database.engine.begin() as conn:
            # 创建所有表 (包括新的 admin_credentials)
            await conn.run_sync(Base.metadata.create_all)

            # 补齐 tools 表的列
            from sqlalchemy import text

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
                except Exception:
                    pass

        print("数据库核心引擎就绪。")
    except Exception as e:
        import traceback

        print(f"\nFATAL: 数据库初始化失败: {e}\n{traceback.format_exc()}")
        state.db_connected = False

    # 核心：推翻原本逻辑，使用专门的 AdminConfig 表
    if state.db_connected:
        try:
            settings._SECRET_KEY = await get_or_create_secret_key()
            app.storage.secret = settings._SECRET_KEY

            async with database.AsyncSessionLocal() as session:
                from sqlalchemy import func

                # 直接查询 admin_credentials 表
                result = await session.execute(select(func.count(AdminConfig.id)))
                admin_count = result.scalar() or 0

            state.needs_setup = admin_count == 0
            print(
                f"管理员凭据检测: 表中存在 {admin_count} 个凭据。Needs Setup: {state.needs_setup}"
            )
        except Exception as e:
            print(f"管理员凭据表查询异常: {e}")
            state.needs_setup = True
    else:
        state.needs_setup = True

    load_modules(modules_list, module_instances_dict)
    for m in modules_list:
        m.setup_api()
        app.include_router(m.router)

    state.initialized.set()
