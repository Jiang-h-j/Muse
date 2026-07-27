import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from muse.core.settings import get_settings

# 自动导入所有 ORM 模型，确保它们注册到 Base.metadata，供 autogenerate 检测。
# load_all_models() 会发现 muse.models 包内的全部模型模块——新建业务表只需
# 在该包内加模型文件，无需再手动登记 import（根治「漏 import 致 autogenerate
# 看不见新表却不报错」；契约由 tests/test_migrations_metadata.py 门禁守护）。
from muse.models import Base, load_all_models

load_all_models()

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# DSN 收敛到单一事实源：从 core.settings 注入（postgresql+psycopg://，psycopg3 async），
# 覆盖 alembic.ini 的占位值，避免连接串两处维护、且确保用 psycopg 而非 asyncpg。
# 转义 % → %%：alembic 底层 ConfigParser 用 BasicInterpolation，密码含 % 时会被误当插值语法。
config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
