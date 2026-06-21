"""SQLAlchemy database setup and models."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, Boolean
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from src.config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class CachedVideo(Base):
    """YouTube videos fetched by AI-Times agent."""
    __tablename__ = "cached_videos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(String(20), unique=True, nullable=False)
    title = Column(String(500), nullable=False)
    channel = Column(String(200))
    thumbnail_url = Column(String(500))
    published_at = Column(DateTime)
    category = Column(String(50))  # "news" or "personality"
    fetched_at = Column(DateTime, default=datetime.utcnow)


class EmailRecord(Base):
    """Emails processed by Mailman agent."""
    __tablename__ = "email_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(String(200), unique=True, nullable=False)
    sender = Column(String(300))
    subject = Column(String(500))
    snippet = Column(Text)
    classification = Column(String(50))  # Urgent, Action Required, Follow-Up, etc.
    ai_summary = Column(Text)
    is_starred = Column(Boolean, default=False)
    is_key_person = Column(Boolean, default=False)
    received_at = Column(DateTime)
    processed_at = Column(DateTime, default=datetime.utcnow)


class StockSnapshot(Base):
    """Stock data snapshots from Wallstreet Wolf agent."""
    __tablename__ = "stock_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), nullable=False)
    price = Column(Float)
    change_percent = Column(Float)
    volume = Column(Float)
    market_cap = Column(Float)
    name = Column(String(200))
    fetched_at = Column(DateTime, default=datetime.utcnow)


class NewsArticle(Base):
    """News articles fetched by News Briefer agent."""
    __tablename__ = "news_articles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(200))
    title = Column(String(500), nullable=False)
    description = Column(Text)
    url = Column(String(1000))
    image_url = Column(String(1000))
    category = Column(String(50))
    ai_summary = Column(Text)
    published_at = Column(DateTime)
    fetched_at = Column(DateTime, default=datetime.utcnow)


class AgentLog(Base):
    """Agent activity logs."""
    __tablename__ = "agent_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_name = Column(String(50), nullable=False)
    level = Column(String(10))  # INFO, WARNING, ERROR
    message = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)


class SystemMetric(Base):
    """System resource metrics for monitoring."""
    __tablename__ = "system_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cpu_percent = Column(Float)
    ram_percent = Column(Float)
    disk_percent = Column(Float)
    active_threads = Column(Integer)
    timestamp = Column(DateTime, default=datetime.utcnow)


async def init_db():
    """Create all tables if they don't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """Get a database session."""
    async with async_session() as session:
        yield session
