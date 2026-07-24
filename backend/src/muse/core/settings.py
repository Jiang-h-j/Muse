"""应用配置：pydantic-settings 分环境读取。

DB / Redis 连接串、JWT 签名密钥与双 token 有效期。生产弱密钥 fail-fast 见 model_validator。
"""

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# JWT 默认占位密钥；生产（debug=False）若仍为此值则拒绝启动（fail-fast，见下方校验）。
_DEFAULT_JWT_SECRET = "dev-only-change-me"
# 生产 JWT 密钥最小长度：HS256 密钥过短易被暴力/伪造，低于此长度即拒绝启动。
_MIN_JWT_SECRET_LENGTH = 32


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
    # SQL echo 独立于 debug：存 token_hash/密码哈希后，echo 会打印绑定参数（敏感），
    # 不应随 debug 一起打开——故解耦为独立开关，默认关。
    db_echo: bool = False

    # Redis：ARQ broker + SSE/缓存 + 登录失败限流（Story 1.3 起）
    redis_url: str = "redis://localhost:6379/0"

    # JWT 双 token（Story 1.3）：签名密钥 + access/refresh 有效期（秒）。
    jwt_secret: str = _DEFAULT_JWT_SECRET
    # TTL 必须为正：0 或负值会签发出「签发即过期」的 token，登录后立刻 401 不可用。
    access_token_ttl_seconds: int = Field(default=900, gt=0)  # 15 分钟：短 TTL，无状态本地验签
    refresh_token_ttl_seconds: int = Field(default=60 * 60 * 24 * 30, gt=0)  # 30 天：长效可撤销

    @model_validator(mode="after")
    def _fail_fast_on_weak_secret(self) -> "Settings":
        """生产环境弱 JWT 密钥拒绝启动（deferred-work.md L5，AC6）。

        debug=False 时若 JWT 密钥仍为默认占位值、或短于最小长度（含空串），签名可被伪造/暴力，
        属致命配置错误，宁可启动即失败也不能带病上线。debug=True（本地开发）放行，便于开箱即用。
        """
        if not self.debug and (
            self.jwt_secret == _DEFAULT_JWT_SECRET
            or len(self.jwt_secret) < _MIN_JWT_SECRET_LENGTH
        ):
            raise ValueError(
                f"生产环境（DEBUG=false）必须设置长度≥{_MIN_JWT_SECRET_LENGTH} 的强随机 "
                "JWT_SECRET，当前仍为默认占位值或过短，拒绝启动。"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
