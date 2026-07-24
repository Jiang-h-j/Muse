"""安全基座：密码哈希（argon2）、后续 JWT 双 token 与 BYOK AES-GCM 加解密。

- 密码哈希：本 story（1.2）实现 hash_password（argon2-cffi，绝不明文存密码）。
- JWT 双 token 签发/校验：Story 1.3（用户登录与会话）——届时在此加 verify_password + JWT。
- AES-GCM BYOK 加解密：Story 1.7（BYOK API Key 绑定）。
"""

import anyio
from argon2 import PasswordHasher

# argon2 默认参数即业界推荐强度；哈希串自带算法/盐/参数，校验无需额外存盐。
_password_hasher = PasswordHasher()


async def hash_password(plain: str) -> str:
    """把明文密码哈希为 argon2 编码串（含盐与参数）；绝不存明文（AC1）。

    argon2 是 CPU 密集同步调用（默认数十~数百 ms 且吃内存），挪到线程池执行，
    避免阻塞 async 事件循环拖垮所有并发请求。
    """
    return await anyio.to_thread.run_sync(_password_hasher.hash, plain)
