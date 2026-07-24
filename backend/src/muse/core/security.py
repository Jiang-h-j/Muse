"""安全基座：密码哈希（argon2）、JWT 双 token 签发/校验、refresh 随机串生成。

- 密码哈希：hash_password / verify_password（argon2-cffi，经 anyio 线程池，绝不明文存密码）。
- JWT access token：create_access_token / decode_access_token（PyJWT HS256，无状态短期）。
- refresh token：generate_refresh_token / hash_refresh_token（高熵随机串 + SHA-256）。
- AES-GCM BYOK 加解密：Story 1.7（BYOK API Key 绑定）。
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

import anyio
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from muse.core.settings import get_settings

# argon2 默认参数即业界推荐强度；哈希串自带算法/盐/参数，校验无需额外存盐。
_password_hasher = PasswordHasher()

# 等时防枚举用固定假 hash（陷阱③）：登录时对不存在的 user 也跑一次真实 argon2 verify，
# 消除「存在=慢 verify / 不存在=快返回」的时序侧信道。模块级生成 → 参数永远与真实密码哈希一致
# （即便日后调整 argon2 默认参数也自动跟随），import 时一次性开销可接受。
DUMMY_PASSWORD_HASH = _password_hasher.hash("muse-timing-equalizer")

_JWT_ALGORITHM = "HS256"


class TokenError(Exception):
    """access token 解码失败的语义化结果。

    reason 区分过期（token_expired，对接原型 expired 态）与非法（token_invalid），
    上层据此选择 error envelope code。
    """

    def __init__(self, reason: Literal["token_expired", "token_invalid"]) -> None:
        self.reason = reason
        super().__init__(reason)


async def hash_password(plain: str) -> str:
    """把明文密码哈希为 argon2 编码串（含盐与参数）；绝不存明文（AC1）。

    argon2 是 CPU 密集同步调用（默认数十~数百 ms 且吃内存），挪到线程池执行，
    避免阻塞 async 事件循环拖垮所有并发请求。
    """
    return await anyio.to_thread.run_sync(_password_hasher.hash, plain)


async def verify_password(password_hash: str, plain: str) -> bool:
    """校验明文密码与 argon2 哈希是否匹配（AC1/AC3）。

    同样挪线程池（argon2 verify 与 hash 同为 CPU 密集）。不匹配返回 False 而非抛异常，
    便于登录侧对「user 不存在」也跑一次等时 verify 消除时序侧信道（陷阱③）。
    """

    def _verify() -> bool:
        try:
            return _password_hasher.verify(password_hash, plain)
        except (VerificationError, InvalidHashError):
            # VerifyMismatchError（密码不匹配）⊂ VerificationError；InvalidHashError（库中哈希
            # 损坏/非 argon2 格式，属 ValueError 支线）一并归为校验失败，避免逃逸成 500。
            return False

    return await anyio.to_thread.run_sync(_verify)


def create_access_token(user_id: uuid.UUID) -> tuple[str, int]:
    """签发无状态 access JWT，返回 (token, expires_in秒)。

    payload {sub, type:"access", iat, exp}，HS256 + settings.jwt_secret。
    无状态 = 每请求本地验签、不查库；短 TTL 由 settings.access_token_ttl_seconds 控制。
    """
    settings = get_settings()
    ttl = settings.access_token_ttl_seconds
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(seconds=ttl),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=_JWT_ALGORITHM)
    return token, ttl


def decode_access_token(token: str) -> uuid.UUID:
    """校验并解出 access token 的用户 id；失败抛语义化 TokenError（陷阱①）。

    PyJWT 过期抛 ExpiredSignatureError→token_expired、其它非法抛 InvalidTokenError→token_invalid。
    额外校验 type=="access"，拒绝用 refresh/其它类型 token 冒充 access。
    """
    settings = get_settings()
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[_JWT_ALGORITHM],
            options={"require": ["exp"]},  # 缺 exp 的 token 一律拒绝，杜绝「永不过期」token
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("token_expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("token_invalid") from exc

    if claims.get("type") != "access":
        raise TokenError("token_invalid")
    try:
        return uuid.UUID(claims["sub"])
    except (KeyError, ValueError) as exc:
        raise TokenError("token_invalid") from exc


def generate_refresh_token() -> str:
    """生成高熵 refresh 明文串（仅下发前端一次，不落库明文）。"""
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    """refresh 明文 → SHA-256 十六进制（落库/查库用）。

    refresh 是高熵随机串，无字典/暴力面，SHA-256 足够且快；用 argon2 会让高频刷新路径
    无谓变慢（陷阱⑤）。与低熵、需抗暴力的密码（argon2）严格区分，勿混用。
    """
    return hashlib.sha256(token.encode()).hexdigest()
