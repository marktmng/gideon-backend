import sys
from os.path import abspath, dirname
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool, create_engine
from alembic import context

# Ensure app root is on python path
sys.path.insert(0, dirname(dirname(abspath(__file__))))

from app.core.config import settings
from app.models import Conversation, Message, Task, Memory
from app.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = settings.database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=settings.is_sqlite,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Use application settings database URL
    engine_kwargs = {"poolclass": pool.NullPool}
    if settings.is_sqlite:
        engine_kwargs["connect_args"] = {"check_same_thread": False}

    connectable = create_engine(settings.database_url, **engine_kwargs)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=settings.is_sqlite,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
