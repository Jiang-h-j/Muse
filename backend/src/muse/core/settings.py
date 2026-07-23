"""应用配置：pydantic-settings 分环境读取。

本 story 只需 DB / Redis 连接串与占位密钥；JWT / BYOK 主密钥等由后续 story 填充实际逻辑。
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 应用
    app_name: str = "Muse"
    debug: bool = False

    # 数据库：SQLAlchemy 2.0 async + psycopg3（DSN 必须为 postgresql+psycopg://）
    database_url: str = "postgresql+psycopg://muse:muse@localhost:5432/muse"

    # Redis：后续 ARQ broker + SSE/缓存（本 story 仅容器起得来即可）
    redis_url: str = "redis://localhost:6379/0"

    # 占位密钥：JWT 签名密钥，实际签发逻辑在 Story 1.3
    jwt_secret: str = "dev-only-change-me"


@lru_cache
def get_settings() -> Settings:
    return Settings()
