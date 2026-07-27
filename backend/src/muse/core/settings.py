"""应用配置：pydantic-settings 分环境读取。

DB / Redis 连接串、JWT 签名密钥与双 token 有效期。生产弱密钥 fail-fast 见 model_validator。
"""

import base64
import binascii
from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# JWT 默认占位密钥；生产（debug=False）若仍为此值则拒绝启动（fail-fast，见下方校验）。
_DEFAULT_JWT_SECRET = "dev-only-change-me"
# 生产 JWT 密钥最小长度：HS256 密钥过短易被暴力/伪造，低于此长度即拒绝启动。
_MIN_JWT_SECRET_LENGTH = 32

# BYOK 主密钥默认占位值；生产（debug=False）若仍为此值则拒绝启动（与 JWT 同构，Story 1.7）。
_DEFAULT_BYOK_MASTER_KEY = "dev-only-byok-key-change-me"
# AES-256-GCM 要求密钥恰好 32 字节；约定 BYOK_MASTER_KEY 存 base64(32 字节随机串)。
_BYOK_MASTER_KEY_BYTES = 32


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

    # BYOK 主密钥（Story 1.7）：应用层 AES-256-GCM 加解密用户 API Key 的主密钥（NFR6/AR9）。
    # 约定存 base64(32 字节随机串)；生产 fail-fast 见 _fail_fast_on_weak_byok_master_key。
    byok_master_key: str = _DEFAULT_BYOK_MASTER_KEY

    # 托管免费额度护栏阈值（Story 1.8，AR6/AR14）：托管路径累计用量触顶即拦。
    # **护栏计量单位 = tokens 而非「章」**（dev 定档，story Dev Notes 推荐 A）：usage_ledger 一次
    # LLM 调用记一行、一章要 5–10 次调用，COUNT(*) 数的是调用不是章，拿它当章数会 5–10 倍虚高触顶；
    # SUM(total_tokens) 与「一次调用一行」的记账粒度天然对齐、无换算歧义。展示层「N/M 章」由前端接线
    # 切片折算或改文案（本 story 不改 app.js）。
    # **占位默认值**：粗略对齐原型「5 章免费」（app.js:2081，假设占位单章 ~40k tokens），
    # 真实数值待 Epic 4 盲测出单章真实 token 成本后定档（architecture.md:200/531）。业务配置非安全
    # 密钥，占位默认值可直接用于生产，故**不加 fail-fast**（与 JWT/BYOK 主密钥相反）。
    free_quota_tokens: int = Field(default=200_000, gt=0)

    # DeepSeek Provider（Story 2.1，AR12/焦点一）：托管默认路径的模型接入配置。
    # deepseek_api_key 是 **Muse 自有** Key（托管路径用；BYOK 路径用用户自己的 Key，见
    # byok_service）。**无 fail-fast**（与 JWT/BYOK 主密钥相反，参照 free_quota_tokens 决策）：
    # DeepSeek key 是业务配置而非安全密钥——空值只导致 chat/stream 调用报明确错误、不导致越权，
    # 故不加 model_validator 拒启动。空串默认便于本地/CI 无 key 时其余功能正常跑，真实调用时缺 key
    # 由 Provider 报错。
    deepseek_api_key: str = ""
    # base_url 切到 DeepSeek（OpenAI SDK 兼容，spike P1 实测确认）；允许 .env 覆盖便于换区域/代理。
    deepseek_base_url: str = "https://api.deepseek.com"
    # 双档模型名（spike P1 `models.list()` 已实测确认与 architecture.md:196 完全吻合）：
    # thinking 档起草/审查、fast 档提取/轻任务，均 128K 上下文。配置化便于模型改名时不改代码。
    deepseek_model_thinking: str = "deepseek-v4-pro"
    deepseek_model_fast: str = "deepseek-v4-flash"

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

    @model_validator(mode="after")
    def _fail_fast_on_weak_byok_master_key(self) -> "Settings":
        """生产环境弱 BYOK 主密钥拒绝启动（NFR6/AR9，与 JWT fail-fast 同构）。

        debug=False 时若主密钥仍为默认占位值、或 base64 解码后不是恰好 32 字节（含非法 base64、
        空串、长度不符），AES-256-GCM 无法安全加密用户 API Key，属致命配置错误，拒绝启动。
        debug=True（本地开发）放行——_load_master_key 会对占位值做确定性派生保证开箱即用。
        """
        if self.debug:
            return self
        if self.byok_master_key == _DEFAULT_BYOK_MASTER_KEY:
            raise ValueError(
                "生产环境（DEBUG=false）必须设置 BYOK_MASTER_KEY 为 base64 编码的 32 字节强随机"
                '串，当前仍为默认占位值，拒绝启动。可用 python -c "import base64,os; '
                'print(base64.urlsafe_b64encode(os.urandom(32)).decode())" 生成。'
            )
        try:
            decoded = base64.urlsafe_b64decode(self.byok_master_key)
        except (binascii.Error, ValueError) as exc:
            raise ValueError(
                "生产环境 BYOK_MASTER_KEY 必须为合法 base64 编码，当前无法解码，拒绝启动。"
            ) from exc
        if len(decoded) != _BYOK_MASTER_KEY_BYTES:
            raise ValueError(
                f"生产环境 BYOK_MASTER_KEY base64 解码后必须恰好 {_BYOK_MASTER_KEY_BYTES} 字节"
                f"（AES-256-GCM 要求），当前为 {len(decoded)} 字节，拒绝启动。"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
