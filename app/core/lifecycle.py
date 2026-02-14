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
        print("数据库初始化成功。")
    except Exception as e:
        print(f"数据库连接失败 (已拒绝不安全连接): {e}")
        state.db_connected = False

    if state.db_connected:
        try:
            settings._SECRET_KEY = await get_or_create_secret_key()
            app.storage.secret = settings._SECRET_KEY

            async with database.AsyncSessionLocal() as session:
                result = await session.execute(select(User).where(User.is_admin))
                admin_exists = result.scalars().first() is not None
            state.needs_setup = admin_exists is None
        except Exception as e:
            print(f"初始化管理员检查失败: {e}")
            state.needs_setup = False
    else:
        state.needs_setup = False

    load_modules(modules_list, module_instances_dict)
    # await sync_modules_with_db(state, modules_list) # 已禁用

    for m in modules_list:
        m.setup_api()
        app.include_router(m.router)

    state.initialized.set()
