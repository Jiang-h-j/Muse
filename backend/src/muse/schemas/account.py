"""账户域 API schema：注册/登录/刷新/退出/鉴权（AR4 camelCase 边界）。

请求 schema 继承 CamelModel，前端提交的 camelCase（inviteCode/refreshToken）自动映射到
snake_case。响应只暴露安全视图，绝不含 password_hash / token 明文以外的敏感字段。
登录邮箱复用注册同一归一化口径（_normalize_email），否则大小写差会查不到 user。
"""

import uuid

from pydantic import EmailStr, Field, field_validator

from muse.schemas.base import CamelModel

_EMAIL_MAX_LENGTH = 320
# refresh 明文为 secrets.token_urlsafe(32)（约 43 字符）；给宽松上界防超大 body 打到 SHA-256/DB。
_REFRESH_TOKEN_MAX_LENGTH = 512


def _normalize_email(value: str) -> str:
    """邮箱归一化：去空白 + 小写；超列宽 422 兜底。

    注册与登录共用同一口径——避免 `Alice@x.com` 与 `alice@x.com` 在注册侧绕过唯一约束、
    或在登录侧因大小写差异查不到已注册 user。超长邮箱在此拦截，否则落库/查询边界异常。
    """
    normalized = value.strip().lower()
    if len(normalized) > _EMAIL_MAX_LENGTH:
        raise ValueError("邮箱长度超出上限")
    return normalized


class RegisterRequest(CamelModel):
    """注册入参。后端独立用 Pydantic 校验，不信任前端（AC4）。

    约束与原型契约对齐：邀请码必填（app.js:305）、密码 ≥8 位（app.js:307）。
    长度上限对齐 DB 列宽并防超大输入放大 argon2 开销。
    """

    invite_code: str = Field(min_length=1, max_length=64)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        return _normalize_email(value)


class RegisterResponse(CamelModel):
    """注册成功响应：新用户安全视图。绝不含 password_hash（AC1）。"""

    id: uuid.UUID
    email: EmailStr


class LoginRequest(CamelModel):
    """登录入参（AC1）。

    密码**不设 min_length**——登录不应暴露密码策略（避免旁路提示攻击者密码规则），
    仅要求非空；邮箱复用注册归一化口径，保证与已存 user 的邮箱大小写一致可查。
    """

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        return _normalize_email(value)


class TokenResponse(CamelModel):
    """登录/刷新成功响应：双 token（AC1/AC2）。

    边界自动 camelCase：accessToken / refreshToken / tokenType / expiresIn。
    refresh 明文仅在此下发前端一次（服务端只存其 SHA-256 哈希，泄库不可反推）。
    """

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int


class RefreshRequest(CamelModel):
    """刷新入参（AC2）：前端提交 refreshToken 自动映射 refresh_token。"""

    refresh_token: str = Field(min_length=1, max_length=_REFRESH_TOKEN_MAX_LENGTH)


class LogoutRequest(CamelModel):
    """退出入参（AC5）：提交当前 refreshToken 以作废对应会话。"""

    refresh_token: str = Field(min_length=1, max_length=_REFRESH_TOKEN_MAX_LENGTH)


class MeResponse(CamelModel):
    """受保护端点 /me 响应：当前登录用户安全视图（AC5）。"""

    id: uuid.UUID
    email: EmailStr
