"""Story 1.2 验证：POST /api/auth/register 全 AC 覆盖。

- DB 用例（requires_db）：走完整 HTTP 栈 + 真实 DB，验证落库、哈希、邀请码消费、并发约束。
- 离线用例：AC4 的 Pydantic 422 校验 + 脱敏，用 dependency override 不依赖 DB。
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import Engine, select

from muse.main import app
from muse.models.account import InviteCode, User
from tests.conftest import requires_db

_client = TestClient(app, raise_server_exceptions=False)


def _register(invite_code: str, email: str, password: str) -> object:
    # 前端提交 camelCase inviteCode（app.js），验证 AR4 边界映射到 invite_code。
    return _client.post(
        "/api/auth/register",
        json={"inviteCode": invite_code, "email": email, "password": password},
    )


# ---------- AC1：有效码注册成功 ----------


@requires_db
def test_valid_invite_registers_success(
    make_invite: Callable[..., str], db_engine: Engine
) -> None:
    code = make_invite("GOOD-CODE")
    resp = _register(code, "alice@example.com", "password123")

    assert resp.status_code == 201
    body = resp.json()
    # 响应是 camelCase 安全视图：含 id/email，绝不含 password/passwordHash。
    assert set(body.keys()) == {"id", "email"}
    assert body["email"] == "alice@example.com"
    assert "password" not in resp.text.lower()

    with db_engine.connect() as conn:
        user = conn.execute(
            select(User.email, User.password_hash).where(User.email == "alice@example.com")
        ).one()
    # AC1：密码经 argon2 哈希存储，绝不明文。
    assert user.password_hash != "password123"
    assert user.password_hash.startswith("$argon2")


@requires_db
def test_valid_invite_marked_used(make_invite: Callable[..., str], db_engine: Engine) -> None:
    code = make_invite("CONSUME-CODE")
    resp = _register(code, "bob@example.com", "password123")
    assert resp.status_code == 201

    with db_engine.connect() as conn:
        invite = conn.execute(
            select(InviteCode.used_at, InviteCode.used_by).where(InviteCode.code == code)
        ).one()
        user_id = conn.execute(
            select(User.id).where(User.email == "bob@example.com")
        ).scalar_one()
    # AC1：邀请码被标记为已用，记录使用者与使用时间。
    assert invite.used_at is not None
    assert invite.used_by == user_id


# ---------- AC2：邀请码无效/已用/过期被拒 ----------


@requires_db
def test_nonexistent_invite_rejected(get_user: Callable[[str], User | None]) -> None:
    resp = _register("NO-SUCH-CODE", "carol@example.com", "password123")
    assert resp.status_code == 400
    body = resp.json()
    # 统一 error envelope + 兼容原型的 invalid 布尔位（app.js:262 分支）。
    assert set(body.keys()) == {"code", "message", "detail"}
    assert body["code"] == "invalid_invite"
    assert body["detail"]["invalid"] is True
    # 账号不被创建。
    assert get_user("carol@example.com") is None


@requires_db
def test_used_invite_rejected(
    make_invite: Callable[..., str], get_user: Callable[[str], User | None]
) -> None:
    code = make_invite("ALREADY-USED", used_at=datetime.now(UTC))
    resp = _register(code, "dave@example.com", "password123")
    assert resp.status_code == 400
    assert resp.json()["code"] == "invalid_invite"
    assert get_user("dave@example.com") is None


@requires_db
def test_expired_invite_rejected(
    make_invite: Callable[..., str], get_user: Callable[[str], User | None]
) -> None:
    code = make_invite("EXPIRED", expires_at=datetime.now(UTC) - timedelta(days=1))
    resp = _register(code, "erin@example.com", "password123")
    assert resp.status_code == 400
    assert resp.json()["code"] == "invalid_invite"
    assert get_user("erin@example.com") is None


# ---------- AC3：邮箱重复冲突 ----------


@requires_db
def test_duplicate_email_conflict(make_invite: Callable[..., str], db_engine: Engine) -> None:
    first = make_invite("CODE-1")
    assert _register(first, "frank@example.com", "password123").status_code == 201

    second = make_invite("CODE-2")
    resp = _register(second, "frank@example.com", "password456")
    assert resp.status_code == 409
    body = resp.json()
    assert body["code"] == "email_conflict"
    # 不泄露密码/内部细节。
    assert "password456" not in resp.text
    assert "password_hash" not in resp.text

    with db_engine.connect() as conn:
        count = conn.execute(
            select(User).where(User.email == "frank@example.com")
        ).all()
    assert len(count) == 1  # 未创建重复账号


@requires_db
def test_email_conflict_does_not_consume_invite(
    make_invite: Callable[..., str], db_engine: Engine
) -> None:
    first = make_invite("CODE-A")
    assert _register(first, "grace@example.com", "password123").status_code == 201

    # 用第二个码 + 已存在邮箱：应冲突，且第二个码不被消费（AC3）。
    second = make_invite("CODE-B")
    assert _register(second, "grace@example.com", "password456").status_code == 409

    with db_engine.connect() as conn:
        invite = conn.execute(
            select(InviteCode.used_at).where(InviteCode.code == second)
        ).one()
    assert invite.used_at is None  # 邮箱冲突不消耗邀请码


@requires_db
def test_same_invite_cannot_be_reused(
    make_invite: Callable[..., str], get_user: Callable[[str], User | None]
) -> None:
    # 陷阱③一次性门禁：同一码第一次注册成功后，第二个不同邮箱再用同码必被拒（已用）。
    code = make_invite("ONE-SHOT")
    assert _register(code, "user1@example.com", "password123").status_code == 201

    resp = _register(code, "user2@example.com", "password123")
    assert resp.status_code == 400
    assert resp.json()["code"] == "invalid_invite"
    assert get_user("user2@example.com") is None  # 第二个账号不被创建


@requires_db
def test_email_normalized_case_insensitive_conflict(
    make_invite: Callable[..., str], db_engine: Engine
) -> None:
    # code-review 修复：邮箱归一化（strip+lower）后，大小写不同的同一邮箱不得绕过唯一约束。
    first = make_invite("NORM-1")
    assert _register(first, "Alice@Example.com", "password123").status_code == 201

    second = make_invite("NORM-2")
    resp = _register(second, "alice@example.com", "password456")
    assert resp.status_code == 409
    assert resp.json()["code"] == "email_conflict"

    with db_engine.connect() as conn:
        count = conn.execute(
            select(User).where(User.email == "alice@example.com")
        ).all()
    # 归一化存储：库里只有一条小写邮箱，未因大小写建重复账号。
    assert len(count) == 1


# ---------- AC4：后端独立校验 + 脱敏（离线，不需 DB） ----------


def test_short_password_rejected_422() -> None:
    # 哨兵密码用独特串（<8 位触发校验），避免与 Pydantic 错误码 string_too_short 子串碰撞——
    # 我们要验证的是「提交的原始值不被反射」，而非错误码里恰好含某单词。
    resp = _register("ANY-CODE", "heidi@example.com", "a1b2c")
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "validation_error"
    # AC4 脱敏：不回显提交的原始密码值（input 已被全局 handler 剔除）。
    assert "a1b2c" not in resp.text


def test_invalid_email_rejected_422() -> None:
    resp = _register("ANY-CODE", "not-an-email", "password123")
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


def test_empty_invite_rejected_422() -> None:
    resp = _register("", "ivan@example.com", "password123")
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


def test_password_never_reflected_in_validation_error() -> None:
    # 组合非法（邮箱错 + 密码短），确保任何校验错误都不反射明文密码（AC4 脱敏硬要求）。
    resp = _register("ANY", "bad", "supersecret")
    assert resp.status_code == 422
    assert "supersecret" not in resp.text


def test_oversized_password_rejected_422() -> None:
    # code-review 修复：密码超上限（max_length=128）应 422 拦截，
    # 防超大输入放大同步 argon2 开销（DoS 面）。
    resp = _register("ANY-CODE", "jack@example.com", "x" * 129)
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"
