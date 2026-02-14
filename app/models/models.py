from typing import Optional
from datetime import datetime
from beanie import Document, Indexed
from pydantic import Field


class User(Document):
    username: Indexed(str, unique=True)
    hashed_password: str
    is_admin: bool = False

    class Settings:
        name = "users"


class Guest(Document):
    ip_address: str
    fingerprint: Indexed(str)
    first_seen: datetime = Field(default_factory=datetime.utcnow)
    last_seen: datetime = Field(default_factory=datetime.utcnow)
    metadata_json: Optional[dict] = None

    class Settings:
        name = "guests"


class AppSetting(Document):
    key: Indexed(str, unique=True)
    value: str
    description: Optional[str] = None

    class Settings:
        name = "settings"
