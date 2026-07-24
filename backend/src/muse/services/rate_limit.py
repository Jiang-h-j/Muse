"""登录失败限流（AR6，AC4）：按归一化邮箱在时间窗内计失败次数，超阈值锁定。

设计：Redis key `login:fail:<normalized_email>`，`INCR` + 首次 `EXPIRE`（窗口 15 min），
计数达阈值（5）即视为锁定。锁定判定必须在密码校验**之前**（陷阱⑥），锁定态直接拒绝、
不进 argon2 verify（省开销且不泄露账号是否存在）。

fail-open：Redis 连接异常时记 warning 并放行（内测期可用性优先，AC4）——限流是防滥用的
加固层，不应因中间件抖动把合法用户挡在门外。
"""

import logging

from redis import asyncio as aioredis
from redis.exceptions import RedisError

from muse.core.settings import get_settings

logger = logging.getLogger("muse")

# 默认阈值与窗口：5 次 / 15 分钟（AC4）。达到 MAX_ATTEMPTS 即锁定。
MAX_ATTEMPTS = 5
WINDOW_SECONDS = 15 * 60

_KEY_PREFIX = "login:fail:"

# 原子计数 + 保底 TTL（Lua 在 Redis 内单次原子执行，杜绝 INCR 与 EXPIRE 之间的窗口）：
# 每次 INCR 后，只要 key 还没有 TTL（新建或历史遗留无过期）就补设窗口过期。
# 这样即便某次 EXPIRE 因故未生效，下一次失败也会补上 TTL，不会出现「计数永不过期→永久锁定」。
_INCR_WITH_TTL_LUA = """
local count = redis.call('INCR', KEYS[1])
if redis.call('TTL', KEYS[1]) < 0 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""

_redis_client: aioredis.Redis | None = None


def _client() -> aioredis.Redis:
    """惰性单例 async Redis 客户端；复用 settings.redis_url。"""
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    return _redis_client


def _key(email: str) -> str:
    return f"{_KEY_PREFIX}{email}"


async def is_locked(email: str) -> bool:
    """账号是否已达锁定阈值。Redis 不可用时 fail-open 返回 False（放行，AC4）。"""
    try:
        raw = await _client().get(_key(email))
    except RedisError as exc:
        logger.warning("限流 is_locked 读取失败，fail-open 放行：%s", exc)
        return False
    if raw is None:
        return False
    try:
        return int(raw) >= MAX_ATTEMPTS
    except ValueError:
        return False


async def check_and_incr_login_failure(email: str) -> None:
    """记一次登录失败：原子 INCR + 保底 EXPIRE。Redis 不可用时 fail-open（不阻断）。

    用 Lua 脚本把「INCR 后若无 TTL 则设窗口过期」合并为单次原子操作：窗口从「第一次失败」
    起算，且杜绝「INCR 成功但 EXPIRE 未执行 → 计数永不过期 → 账号被永久锁定」的死锁窗口。
    """
    try:
        await _client().eval(_INCR_WITH_TTL_LUA, 1, _key(email), WINDOW_SECONDS)
    except RedisError as exc:
        logger.warning("限流 incr 失败，fail-open 不计数：%s", exc)


async def reset_login_failures(email: str) -> None:
    """登录成功后清零失败计数（AC4）。Redis 不可用时静默放过。"""
    try:
        await _client().delete(_key(email))
    except RedisError as exc:
        logger.warning("限流 reset 失败：%s", exc)
