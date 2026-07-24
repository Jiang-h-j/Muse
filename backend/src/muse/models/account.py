"""账户域 ORM 模型：User（多租户根）与 InviteCode（邀请码）。

User 是全项目租户根（NFR3）：后续 project / byok_key / usage_ledger 等业务表
均带 user_id FK 指向本表，实现行级隔离。本 story 只建 user + invite_code，
字段保持精简够用，勿提前塞后续 story 的字段。
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
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
