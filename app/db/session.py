from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings

settings = get_settings()

# SQLite needs check_same_thread=False; PostgreSQL ignores it via connect_args
if settings.DATABASE_URL.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}
    _pool_pre_ping = False
else:
    _connect_args = {"sslmode": "require"} if "sslmode" not in settings.DATABASE_URL else {}
    _pool_pre_ping = True

engine = create_engine(settings.DATABASE_URL, connect_args=_connect_args, pool_pre_ping=_pool_pre_ping)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
