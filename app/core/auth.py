import bcrypt
import httpx
from nicegui import app


async def verify_turnstile(token: str, secret_key: str) -> bool:
    """后端验证 Cloudflare Turnstile Token"""
    if not token:
        return False
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(
                "https://challenges.cloudflare.com/turnstile/v0/siteverify",
                data={"secret": secret_key, "response": token},
                timeout=10.0,
            )
            data = res.json()
            return data.get("success", False)
    except Exception as e:
        print(f"[Security] Turnstile verification error: {e}")
        return False


def get_password_hash(password: str) -> str:
    """使用 bcrypt 对密码进行哈希处理"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证明文密码与哈希值是否匹配"""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )


def is_authenticated() -> bool:
    """检查当前会话是否已通过身份验证"""
    return app.storage.user.get("authenticated", False)
