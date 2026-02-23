"""
Database schema — designed by Sigma (Pool Database Architect)
Account lifecycle: CREATED → WARMING → READY → ASSIGNED → IN_USE → RETIRED
"""
from __future__ import annotations
from sqlalchemy import create_engine, Column, String, Integer, DateTime, Text, Float
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from datetime import datetime, timezone
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config.settings import DB_URL


class Base(DeclarativeBase):
    pass


class TitleProfile(Base):
    """One row per STAGE title (movie/series/microdrama)"""
    __tablename__ = "title_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title_id = Column(String, unique=True, nullable=False)   # CMS title ID
    title_name = Column(String, nullable=False)              # Raw name from CMS
    title_type = Column(String, nullable=False)              # movie/series/microdrama
    handle = Column(String)                                  # Generated social handle

    # Platform account IDs
    fb_page_id = Column(String)
    fb_page_url = Column(String)
    yt_channel_id = Column(String)
    yt_channel_url = Column(String)
    ig_account_id = Column(String)
    ig_username = Column(String)

    # Status
    status = Column(String, default="pending")               # pending/creating/done/failed
    error_message = Column(Text)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class TokenVault(Base):
    """Stores all platform tokens — never put tokens in code or logs"""
    __tablename__ = "token_vault"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title_id = Column(String, nullable=False)
    platform = Column(String, nullable=False)                # facebook/instagram/youtube
    token_type = Column(String, nullable=False)              # page_token/system_user/oauth_refresh
    token_value = Column(Text, nullable=False)
    expires_at = Column(DateTime)                            # NULL = never expires
    last_refreshed_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class InstagramPool(Base):
    """Instagram pre-created account pool"""
    __tablename__ = "instagram_pool"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, nullable=False)
    password = Column(Text, nullable=False)
    email = Column(String)
    phone_number = Column(String)
    geelark_device_id = Column(String)
    cookies_file = Column(String)

    status = Column(String, default="created")  # created/warming/ready/assigned/retired
    health_score = Column(Float, default=100.0)
    assigned_title_id = Column(String)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    warmed_at = Column(DateTime)
    assigned_at = Column(DateTime)
    last_rename_at = Column(DateTime)
    rename_count = Column(Integer, default=0)


class WarmupLog(Base):
    """Log of warmup actions per Instagram account"""
    __tablename__ = "warmup_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, nullable=False)
    action_type = Column(String, nullable=False)  # follow/like/browse/story_view
    performed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    success = Column(Integer, default=1)  # 1=success, 0=failed


class EventLog(Base):
    """Full audit trail of every action"""
    __tablename__ = "event_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_type = Column(String, nullable=False)   # title/ig_account
    entity_id = Column(String, nullable=False)
    event_type = Column(String, nullable=False)    # fb_page_created/ig_assigned/token_saved etc
    event_data = Column(Text)                      # JSON
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


def init_db():
    engine = create_engine(DB_URL)
    Base.metadata.create_all(engine)
    return engine


def get_session():
    engine = create_engine(DB_URL)
    Session = sessionmaker(bind=engine)
    return Session()
