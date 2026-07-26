"""账户域 ORM 模型：User（多租户根）与 InviteCode（邀请码）。

User 是全项目租户根（NFR3）：后续 project / byok_key / usage_ledger 等业务表
均带 user_id FK 指向本表，实现行级隔离。本 story 只建 user + invite_code，
字段保持精简够用，勿提前塞后续 story 的字段。
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from muse.models.base import Base, TimestampMixin, UUIDPKMixin


class User(Base, UUIDPKMixin, TimestampMixin):
    """用户账号；多租户根。

    email 加唯一约束——并发重复注册由 DB 层兜底（先查后插存在 TOCTOU 竞态）。
    密码只存 argon2 哈希，绝不明文。
    """

    __tablename__ = "user"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)


class InviteCode(Base, UUIDPKMixin, TimestampMixin):
    """邀请码；早期创作者注册凭证。

    使用状态由 used_at / used_by 表达（NULL = 未使用），不设冗余 is_used 布尔，
    避免布尔位与时间/使用者字段不一致。expires_at 可空表示永不过期。
    """

    __tablename__ = "invite_code"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # 记录使用者与使用时间；二者 NULL 即未使用（消费时单事务条件更新，见 auth_service）。
    used_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RefreshSession(Base, UUIDPKMixin, TimestampMixin):
    """refresh token 会话；access 无状态不可撤销的短板由本表弥补（AC5 退出、AC2 失效判定）。

    只存 refresh 明文的 SHA-256 十六进制哈希（token_hash），明文仅下发前端一次——泄库不可反推。
    revoked_at NULL = 有效；退出/轮转时置为 now() 即作废。放账户域（本文件）而非新建模块，
    复用 migrations/env.py 既有 `from muse.models import account` import，免踩空迁移陷阱。
    """

    __tablename__ = "refresh_session"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id"), nullable=False, index=True
    )
    # refresh 是高熵随机串（无字典/暴力面），SHA-256 十六进制定长 64；唯一约束防撞。
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ByokKey(Base, UUIDPKMixin, TimestampMixin):
    """BYOK（Bring Your Own Key）：用户自带的 LLM API Key，AES-GCM 加密后落库（Story 1.7）。

    放账户域（本文件）而非新建模块，复用 migrations/env.py 既有 `from muse.models import account`
    import，免踩空迁移陷阱（deferred-work.md L10）。V1 按账户级绑定（user_id 唯一）——每账户至多
    一条 BYOK，支撑「绑定即替换」的 upsert 语义（陷阱④）；未来若需作品级，加 project_id + 复合唯一
    即可平滑升级，账户级是其子集不阻塞。明文 API Key 绝不落库：只存 encrypted_key 密文 + 尾 4 位
    明文供掩码回显（陷阱①）。
    """

    __tablename__ = "byok_key"

    # user_id 唯一 = 每账户至多一条 BYOK（陷阱④ 替换语义的约束基础）；FK 指向租户根 user。
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id"), unique=True, nullable=False, index=True
    )
    # provider 存英文枚举 deepseek/claude/custom（与 mode/phase 存英文枚举一脉相承）。
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    # AES-GCM 密文单串 base64(nonce‖ciphertext)；API Key 长度不定，用 Text 不封顶。
    encrypted_key: Mapped[str] = mapped_column(Text, nullable=False)
    # 明文尾 4 位，供掩码回显（避免每次查询只为取尾 4 位而解密整串）；仅尾 4 位不足以泄露密钥。
    key_suffix: Mapped[str] = mapped_column(String(8), nullable=False)


class UsageLedger(Base, UUIDPKMixin, TimestampMixin):
    """用量流水（Story 1.8，AR9/AR14）：每次 LLM 调用记一行 tokens 与成本。

    放账户域（本文件）而非新建模块，复用 migrations/env.py 既有 `from muse.models import account`
    import，免踩空迁移陷阱（deferred-work.md L10，与 ByokKey 同款理由）。

    与 ByokKey 的关键差异（陷阱①）：BYOK 是账户级单例（user_id 唯一，每账户至多一条）；用量是
    **一对多流水**——每次 LLM 调用插一行，同账户 N 行。故 user_id **只加 index、绝不 unique**
    （加速按账户聚合的护栏/展示查询），照抄 ByokKey 的 unique 会让第二次记账违反唯一约束炸掉。

    **本 story 只建表 + 供 Epic 2 消费的记账/护栏接口，不自行触发任何 LLM 调用、不埋点到生成链路**
    （AR14 跨 epic 受控依赖）：tokens 数与成本是 LLM 调用的返回产物，本 story 无处可埋，实际写入由
    Epic 2 Story 2.1 建 Provider 层时接入（见 story Dev Notes「跨 Epic 边界」）。
    """

    __tablename__ = "usage_ledger"

    # 租户列：FK 指向 user 根，**非 unique**（一对多流水）；index 支撑按账户聚合（护栏/展示）。
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id"), nullable=False, index=True
    )
    # 用量可归属某作品，也可账户级（探索/设定阶段可能无 project 上下文）；V1 允许空。
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project.id"), nullable=True, index=True
    )
    # 归账面英文枚举 hosted/byok（区分托管 vs 自有 Key，NFR5）：护栏只累计 hosted、byok 不占额度。
    # 与 mode/phase/provider 存英文枚举一脉相承。记账那刻的绑定态由调用方（Epic 2 Provider）传入。
    billing_path: Mapped[str] = mapped_column(String(16), nullable=False)
    # tokens 三分量（AR14）：prompt/completion 明细 + total 冗余（护栏按 SUM(total_tokens) 聚合，
    # 免每次聚合都算 prompt+completion）。默认 0，均非空。
    prompt_tokens: Mapped[int] = mapped_column(nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(nullable=False, default=0)
    # 成本金额（陷阱②）：**用 Numeric/Decimal 不用 Float**——钱不能用浮点（0.1+0.2≠0.3 累加漂移）。
    # Numeric(12,6)：6 位小数容纳 per-token 微额成本，12 位精度足够内测期。Python 侧全程 Decimal。
    cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), nullable=False, default=Decimal("0")
    )
    # 记录哪个模型产生本次用量，便于成本审计（architecture.md:181 全链路 trace）；V1 可空。
    model_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
