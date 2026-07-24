"""账户域 API schema：注册请求/响应（AR4 camelCase 边界）。

RegisterRequest 继承 CamelModel，前端提交的 camelCase（inviteCode）自动映射到
snake_case（invite_code）。RegisterResponse 只暴露安全视图（id/email），
绝不含 password_hash。
"""

import uuid

from pydantic import EmailStr, Field, field_validator

from muse.schemas.base import CamelModel


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
    def _normalize_email(cls, value: str) -> str:
        """邮箱归一化：去空白 + 小写。

        避免 `Alice@x.com` 与 `alice@x.com` 绕过唯一约束建重复账号，并与 1.3 登录口径一致。
        同时兜住超长邮箱：格式合法但超列宽的邮箱在此 422 拦截，否则落库抛 DataError 退化成 500。
        """
        normalized = value.strip().lower()
        if len(normalized) > 320:
            raise ValueError("邮箱长度超出上限")
        return normalized


class RegisterResponse(CamelModel):
    """注册成功响应：新用户安全视图。绝不含 password_hash（AC1）。"""

    id: uuid.UUID
    email: EmailStr
