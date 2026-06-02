from logging.config import fileConfig

from alembic import context
from flask import current_app


config = context.config
fileConfig(config.config_file_name)
target_metadata = current_app.extensions["migrate"].db.metadata


def get_engine():
    return current_app.extensions["migrate"].db.engine


def run_migrations_offline():
    context.configure(
        url=str(get_engine().url),
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    with get_engine().connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
