"""Story 1.3 验证：登录 / 刷新 / 退出 / me 全 AC 覆盖。

- 离线用例：JWT 签发-解码 round-trip、过期/篡改被拒、Pydantic 校验（不需 DB/Redis）。
- DB 用例（requires_db）：走完整 HTTP 栈 + 真实 DB，验证双 token、refresh 轮转、退出作废、me 鉴权。
- 限流用例（requires_redis）：失败计数锁定 + 成功清零；fail-open 用例离线验证不阻断。
"""

import time
import uuid
from collections.abc import Callable

import jwt
import pytest
from fastapi.testclient import TestClient
from redis.exceptions import RedisError

from muse.core.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_refresh_token,
)
from muse.core.settings import get_settings
from muse.main import app
from muse.models.account import User
from tests.conftest import DB_READY, requires_db

_client = TestClient(app, raise_server_exceptions=False)

# Redis 门禁：与 DB 门禁同源（本地 docker-compose 一并起）；限流用例需真实 Redis。
requires_redis = pytest.mark.skipif(
    not DB_READY, reason="需起容器并设 MUSE_DB_READY=1 才跑限流 Redis 用例"
)


@pytest.fixture(autouse=True, scope="module")
def _client_lifespan() -> "object":
    """以上下文管理器模式运行 TestClient：所有请求共享同一持久事件循环。

    应用的 async DB/Redis engine 是模块级单例，连接池绑定到首个事件循环。TestClient 非上下文
    模式下每个请求起临时循环、用完即关，同一用例内发两次请求（如 login+me）时第二次的新循环
    会撞上首次残留的连接 → RuntimeError: Event loop is closed。用 `with _client` 固定单一循环即解。
    """
    with _client:
        yield


def _login(email: str, password: str) -> object:
    return _client.post("/api/auth/login", json={"email": email, "password": password})


# ---------- 离线：JWT 编解码（AC1/AC2，不需 DB） ----------


def test_access_token_round_trip() -> None:
    uid = uuid.uuid4()
    token, expires_in = create_access_token(uid)
    assert expires_in == get_settings().access_token_ttl_seconds
    assert decode_access_token(token) == uid


def test_expired_access_token_rejected() -> None:
    # 直接造一个 exp 在过去的 access token，验证 decode 抛 token_expired（对接原型 expired 态）。
    settings = get_settings()
    now = int(time.time())
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "type": "access", "iat": now - 100, "exp": now - 10},
        settings.jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(TokenError) as exc:
        decode_access_token(token)
    assert exc.value.reason == "token_expired"


def test_tampered_access_token_rejected() -> None:
    token, _ = create_access_token(uuid.uuid4())
    # 篡改签名段（末位翻转）→ 验签失败 → token_invalid。
    tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
    with pytest.raises(TokenError) as exc:
        decode_access_token(tampered)
    assert exc.value.reason == "token_invalid"


def test_wrong_type_token_rejected() -> None:
    # 用非 access 类型（如 refresh）冒充 access 应被拒（防 token 混用）。
    settings = get_settings()
    now = int(time.time())
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "type": "refresh", "iat": now, "exp": now + 100},
        settings.jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(TokenError) as exc:
        decode_access_token(token)
    assert exc.value.reason == "token_invalid"


def test_refresh_hash_is_sha256_hex_not_argon2() -> None:
    # 陷阱⑤：refresh 哈希用 SHA-256（定长 64 位十六进制），不是 argon2（$argon2 前缀）。
    token = generate_refresh_token()
    h = hash_refresh_token(token)
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)
    assert not h.startswith("$argon2")


def test_missing_exp_token_rejected() -> None:
    # code-review Fix：缺 exp 声明的 token 必须被拒（require exp），杜绝「永不过期」token。
    settings = get_settings()
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "type": "access", "iat": int(time.time())},
        settings.jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(TokenError) as exc:
        decode_access_token(token)
    assert exc.value.reason == "token_invalid"


def test_verify_password_returns_false_on_corrupt_hash() -> None:
    # code-review Fix：库中 password_hash 损坏/非 argon2 格式时，verify 返回 False 而非抛 500。
    import anyio

    from muse.core.security import verify_password

    assert anyio.run(verify_password, "not-a-valid-argon2-hash", "whatever") is False


def test_weak_jwt_secret_fails_fast_in_production() -> None:
    # code-review Fix：debug=False 时，默认占位密钥或过短密钥（含空串）应拒绝启动。
    from pydantic import ValidationError

    from muse.core.settings import Settings

    for weak in ("dev-only-change-me", "", "short-key"):
        with pytest.raises(ValidationError):
            Settings(debug=False, jwt_secret=weak)
    # 足够长的强密钥在 debug=False 下应正常构造。
    ok = Settings(debug=False, jwt_secret="x" * 32)
    assert ok.jwt_secret == "x" * 32


def test_non_positive_token_ttl_rejected() -> None:
    # code-review Fix：TTL 为 0 或负数会签发「签发即过期」token，配置校验应拒绝。
    from pydantic import ValidationError

    from muse.core.settings import Settings

    with pytest.raises(ValidationError):
        Settings(access_token_ttl_seconds=0)
    with pytest.raises(ValidationError):
        Settings(refresh_token_ttl_seconds=-1)


# ---------- 离线：登录入参校验 + 鉴权缺失（不需 DB） ----------


def test_login_missing_password_422() -> None:
    resp = _client.post("/api/auth/login", json={"email": "a@example.com"})
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


def test_me_without_token_401() -> None:
    # 无 Authorization 头访问受保护端点 → 401 token_invalid（AC5）。
    resp = _client.get("/api/auth/me")
    assert resp.status_code == 401
    body = resp.json()
    assert set(body.keys()) == {"code", "message", "detail"}
    assert body["code"] == "token_invalid"
    assert body["detail"]["expired"] is True


def test_me_with_garbage_token_401() -> None:
    resp = _client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "token_invalid"


def test_me_with_expired_token_401() -> None:
    # 过期 access 访问 me → 401 token_expired（对接原型 #/login?state=expired）。
    settings = get_settings()
    now = int(time.time())
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "type": "access", "iat": now - 100, "exp": now - 10},
        settings.jwt_secret,
        algorithm="HS256",
    )
    resp = _client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "token_expired"


# ---------- DB 端到端：AC1 正确登录签发双 token + me 可访问 ----------


@requires_db
def test_login_success_issues_tokens(make_user: Callable[..., User]) -> None:
    make_user("alice@example.com", "password123")
    resp = _login("alice@example.com", "password123")

    assert resp.status_code == 200
    body = resp.json()
    # camelCase 边界（AR4）：accessToken/refreshToken/tokenType/expiresIn。
    assert set(body.keys()) == {"accessToken", "refreshToken", "tokenType", "expiresIn"}
    assert body["tokenType"] == "Bearer"
    assert body["expiresIn"] == get_settings().access_token_ttl_seconds
    assert body["accessToken"] and body["refreshToken"]


@requires_db
def test_login_then_me_accessible(make_user: Callable[..., User]) -> None:
    user = make_user("bob@example.com", "password123")
    access = _login("bob@example.com", "password123").json()["accessToken"]

    resp = _client.get("/api/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "bob@example.com"
    assert body["id"] == str(user.id)


@requires_db
def test_login_email_case_insensitive(make_user: Callable[..., User]) -> None:
    # 登录邮箱归一化口径与注册一致：大小写差异仍能登录（否则查不到 user）。
    make_user("carol@example.com", "password123")
    resp = _login("Carol@Example.com", "password123")
    assert resp.status_code == 200


# ---------- DB 端到端：AC3 邮箱/密码错误被拒，不签发 token ----------


@requires_db
def test_wrong_password_rejected(make_user: Callable[..., User]) -> None:
    make_user("dave@example.com", "password123")
    resp = _login("dave@example.com", "wrong-password")
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "invalid_credentials"
    assert body["detail"]["invalid"] is True
    # 不签发任何 token。
    assert "accessToken" not in resp.text
    assert "wrong-password" not in resp.text


@requires_db
def test_nonexistent_email_rejected_same_message(make_user: Callable[..., User]) -> None:
    # 邮箱不存在与密码错误**共用同一文案 + 同一 code**（AC3，不泄露账号是否存在）。
    make_user("erin@example.com", "password123")
    wrong_pw = _login("erin@example.com", "wrong-password").json()
    no_user = _login("ghost@example.com", "password123").json()
    assert wrong_pw["code"] == no_user["code"] == "invalid_credentials"
    assert wrong_pw["message"] == no_user["message"]


# ---------- DB 端到端：AC2 refresh 刷新得新 access；refresh 失效/轮转后旧的被拒 ----------


@requires_db
def test_refresh_issues_new_access(make_user: Callable[..., User]) -> None:
    make_user("frank@example.com", "password123")
    tokens = _login("frank@example.com", "password123").json()

    resp = _client.post("/api/auth/refresh", json={"refreshToken": tokens["refreshToken"]})
    assert resp.status_code == 200
    new_tokens = resp.json()
    # 新 access 可访问 me。
    me = _client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {new_tokens['accessToken']}"}
    )
    assert me.status_code == 200


@requires_db
def test_refresh_rotation_invalidates_old(make_user: Callable[..., User]) -> None:
    # 陷阱④：refresh 轮转——旧 refresh 用过一次即作废，重放被拒。
    make_user("grace@example.com", "password123")
    tokens = _login("grace@example.com", "password123").json()
    old_refresh = tokens["refreshToken"]

    first = _client.post("/api/auth/refresh", json={"refreshToken": old_refresh})
    assert first.status_code == 200

    replay = _client.post("/api/auth/refresh", json={"refreshToken": old_refresh})
    assert replay.status_code == 401
    assert replay.json()["code"] == "token_invalid"


@requires_db
def test_refresh_invalid_token_rejected() -> None:
    resp = _client.post("/api/auth/refresh", json={"refreshToken": "no-such-refresh"})
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "token_invalid"
    assert body["detail"]["expired"] is True


# ---------- DB 端到端：AC5 退出作废 refresh，受保护接口需重新登录 ----------


@requires_db
def test_logout_revokes_refresh(make_user: Callable[..., User]) -> None:
    make_user("heidi@example.com", "password123")
    tokens = _login("heidi@example.com", "password123").json()

    logout = _client.post("/api/auth/logout", json={"refreshToken": tokens["refreshToken"]})
    assert logout.status_code == 204

    # 退出后旧 refresh 刷新一律 401。
    resp = _client.post("/api/auth/refresh", json={"refreshToken": tokens["refreshToken"]})
    assert resp.status_code == 401
    assert resp.json()["code"] == "token_invalid"


@requires_db
def test_logout_is_idempotent(make_user: Callable[..., User]) -> None:
    # 陷阱⑦：重复退出（同一 refresh）仍返回成功，不报错。
    make_user("ivan@example.com", "password123")
    tokens = _login("ivan@example.com", "password123").json()
    payload = {"refreshToken": tokens["refreshToken"]}
    assert _client.post("/api/auth/logout", json=payload).status_code == 204
    assert _client.post("/api/auth/logout", json=payload).status_code == 204


@requires_db
def test_logout_unknown_refresh_succeeds() -> None:
    # 不存在的 refresh 退出也视为成功（终态操作幂等）。
    resp = _client.post("/api/auth/logout", json={"refreshToken": "never-existed"})
    assert resp.status_code == 204


# ---------- 限流：AC4 失败超阈值锁定 + 成功清零（requires_redis） ----------


@requires_redis
def test_login_lockout_after_threshold(make_user: Callable[..., User]) -> None:
    from muse.services import rate_limit

    email = "locktest@example.com"
    make_user(email, "password123")

    # 连续失败达阈值：每次失败计数 +1，达 MAX_ATTEMPTS 即锁定（conftest 已清 Redis，用例独立）。
    for _ in range(rate_limit.MAX_ATTEMPTS):
        _login(email, "wrong-password")

    # 锁定窗口内即便密码正确也被拒（锁定判定在密码校验之前，陷阱⑥）。
    resp = _login(email, "password123")
    assert resp.status_code == 429
    body = resp.json()
    assert body["code"] == "too_many_attempts"
    assert body["detail"]["locked"] is True


@requires_redis
def test_login_success_resets_failure_count(make_user: Callable[..., User]) -> None:
    from muse.services import rate_limit

    email = "resettest@example.com"
    make_user(email, "password123")

    # 几次失败（未达阈值）后成功登录，计数应清零——之后不应因历史失败被锁。
    for _ in range(rate_limit.MAX_ATTEMPTS - 1):
        _login(email, "wrong-password")
    assert _login(email, "password123").status_code == 200

    # 清零后再失败一次不应立即锁定。
    assert _login(email, "wrong-password").status_code == 401


# ---------- 限流 fail-open：Redis 不可用不阻断登录（离线，monkeypatch） ----------


@requires_db
def test_rate_limit_fail_open_when_redis_down(
    make_user: Callable[..., User], monkeypatch: pytest.MonkeyPatch
) -> None:
    from muse.services import rate_limit

    make_user("failopen@example.com", "password123")

    # 模拟 Redis 全线不可用：客户端所有操作抛 RedisError，登录仍应放行成功（fail-open，AC4）。
    monkeypatch.setattr(rate_limit, "_client", lambda: _FakeBoomClient())

    resp = _login("failopen@example.com", "password123")
    assert resp.status_code == 200


class _FakeBoomClient:
    """所有操作抛 RedisError 的假客户端，验证限流层 fail-open。"""

    async def get(self, *args: object, **kwargs: object) -> object:
        raise RedisError("down")

    async def incr(self, *args: object, **kwargs: object) -> object:
        raise RedisError("down")

    async def expire(self, *args: object, **kwargs: object) -> object:
        raise RedisError("down")

    async def delete(self, *args: object, **kwargs: object) -> object:
        raise RedisError("down")
