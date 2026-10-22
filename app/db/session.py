"""Database session and connection management."""
from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Configure engine arguments based on driver
engine_kwargs = {"echo": False}
if settings.is_sqlite:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # Pool settings for PostgreSQL / production
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20

try:
    engine = create_engine(settings.database_url, **engine_kwargs)
except Exception as e:
    logger.error("Failed to initialize database engine for URL: %s. Error: %s", settings.database_url.split("@")[-1], str(e))
    raise

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def verify_database_connection() -> bool:
    """Check that the configured database is reachable without silent fallbacks."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection successfully established to: %s", "SQLite" if settings.is_sqlite else "PostgreSQL")
        return True
    except (OperationalError, SQLAlchemyError) as err:
        logger.error(
            "CRITICAL: Failed to connect to the configured database [%s]. "
            "Please check DATABASE_URL, database server status, and credentials. Error details: %s",
            settings.database_url.split("@")[-1],
            str(err)
        )
        raise RuntimeError(f"Database connection failure for configured DATABASE_URL: {err}") from err


def get_db() -> Generator[Session, None, None]:
    """Dependency for providing a transactional database session."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
