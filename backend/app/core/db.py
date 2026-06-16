# backend/app/core/db.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from .config import settings

connect_args = {
    "connect_timeout": settings.db_connect_timeout,
    "sslmode": settings.db_ssl_mode,
}

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_recycle=settings.db_pool_recycle,
    pool_timeout=settings.db_pool_timeout,
    pool_use_lifo=True,
    future=True,
    echo=False,
    connect_args=connect_args,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    future=True,
)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def set_tenant(db: Session, tenant_id: str):
    """
    Placeholder for framtida RLS.
    """
    return