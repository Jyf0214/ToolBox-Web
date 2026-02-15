from sqlalchemy import Column, Integer, String, JSON, DateTime, Boolean
from datetime import datetime
from app.core.database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(
        String(255), unique=True, index=True, nullable=False
    )  # MySQL 需要指定 String 长度
    hashed_password = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)


class Guest(Base):
    __tablename__ = "guests"
    id = Column(Integer, primary_key=True, index=True)
    ip_address = Column(String(255), nullable=False)
    fingerprint = Column(String(255), index=True, nullable=False)
    first_seen = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    metadata_json = Column(JSON, nullable=True)


class AppSetting(Base):
    __tablename__ = "settings"
    key = Column(String(255), primary_key=True, nullable=False)
    value = Column(String(255), nullable=False)
    description = Column(String(255), nullable=True)


class Tool(Base):
    __tablename__ = "tools"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, index=True, nullable=False)
    display_name = Column(String(255), nullable=False)
    is_enabled = Column(Boolean, default=True, nullable=False)
    is_guest_allowed = Column(Boolean, default=True, nullable=False)
    rate_limit_count = Column(Integer, default=0, nullable=False)  # 0 表示不限制
    rate_limit_period = Column(Integer, default=60, nullable=False) # 默认 60 秒
