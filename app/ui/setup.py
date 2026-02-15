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
            ui.navigate.to("/admin")
            return

        with ui.card().classes("absolute-center w-[90vw] max-w-md shadow-lg p-6"):
            ui.label("工具箱初始化设置").classes("text-h5 text-center mb-4")
            ui.label("系统检测到这是第一次运行或尚未配置管理员。").classes("text-xs text-slate-500 mb-4 text-center")
            
            admin_username = ui.input("管理员用户名", value="admin").classes("w-full").props('outlined dense')
            admin_password = ui.input(
                "管理员密码", password=True, password_toggle_button=True
            ).classes("w-full").props('outlined dense')
            site_name_input = ui.input("站点名称", value="我的工具箱").classes("w-full").props('outlined dense')

            async def complete_setup():
                try:
                    await asyncio.wait_for(state.initialized.wait(), timeout=10)
                except asyncio.TimeoutError:
                    ui.notify("数据库连接超时，请检查配置。", color="negative")
                    return

                if not admin_username.value or not admin_password.value:
                    ui.notify("用户名和密码不能为空", color="warning")
                    return

                if not state.db_connected:
                    ui.notify("数据库未连接，无法完成初始化。", color="negative")
                    return

                async with database.AsyncSessionLocal() as session:
                    from sqlalchemy import select
                    # 严防死守：再次检查是否已有任何管理员存在
                    stmt = select(User).where(User.is_admin == True)
                    result = await session.execute(stmt)
                    if result.scalars().first():
                        state.needs_setup = False
                        ui.notify("系统已完成初始化，禁止重复设定。", color="warning")
                        ui.navigate.to("/admin")
                        return

                    # 检查用户名冲突
                    stmt_name = select(User).where(User.username == admin_username.value)
                    res_name = await session.execute(stmt_name)
                    if res_name.scalars().first():
                        ui.notify("用户名已被占用，请更换。", color="negative")
                        return

                    # 创建管理员
                    user = User(
                        username=admin_username.value,
                        hashed_password=get_password_hash(admin_password.value),
                        is_admin=True,
                    )
                    session.add(user)
                    await session.commit()

                await set_setting("site_name", site_name_input.value)
                state.needs_setup = False
                ui.notify("管理员账户创建成功！", color="positive")
                ui.navigate.to("/admin")

            ui.button("开始使用", on_click=complete_setup).classes("w-full mt-4").props("elevated")
