import asyncio
from nicegui import ui
from app.core import database
from app.models.models import User
from app.core.auth import get_password_hash
from app.core.settings_manager import set_setting


def create_setup_page(state):
    @ui.page("/setup")
    async def setup_page():
        if not state.needs_setup:
            ui.navigate.to("/")
            return

        with ui.card().classes("absolute-center w-[90vw] max-w-md shadow-lg p-6"):
            ui.label("工具箱初始化设置").classes("text-h5 text-center mb-4")
            admin_username = ui.input("管理员用户名", value="admin").classes("w-full")
            admin_password = ui.input(
                "管理员密码", password=True, password_toggle_button=True
            ).classes("w-full")
            site_name_input = ui.input("站点名称", value="我的工具箱").classes("w-full")

            async def complete_setup():
                try:
                    await asyncio.wait_for(state.initialized.wait(), timeout=10)
                except asyncio.TimeoutError:
                    ui.notify("数据库连接超时。", color="negative")
                    return

                if not admin_username.value or not admin_password.value:
                    ui.notify("字段不能为空", color="negative")
                    return

                if not state.db_connected:
                    ui.notify("数据库未连接，无法完成初始化设置。", color="negative")
                    return

                async with database.AsyncSessionLocal() as session:
                    from sqlalchemy import select
                    # 检查用户是否已存在
                    stmt = select(User).where(User.username == admin_username.value)
                    result = await session.execute(stmt)
                    existing_user = result.scalars().first()

                    if existing_user:
                        # 如果已存在，则更新密码
                        existing_user.hashed_password = get_password_hash(admin_password.value)
                        existing_user.is_admin = True
                        ui.notify(f"用户 {admin_username.value} 已存在，已更新其管理员密码。", color="info")
                    else:
                        # 不存在则创建
                        user = User(
                            username=admin_username.value,
                            hashed_password=get_password_hash(admin_password.value),
                            is_admin=True,
                        )
                        session.add(user)
                    
                    await session.commit()

                await set_setting("site_name", site_name_input.value)
                state.needs_setup = False
                ui.notify("初始化完成！", color="positive")
                ui.navigate.to("/admin")

            ui.button("完成设置", on_click=complete_setup).classes("w-full mt-4")
