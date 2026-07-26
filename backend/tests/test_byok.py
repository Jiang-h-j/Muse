"""Story 1.7 验证：BYOK API Key 绑定（AES-GCM 安全存取，全 AC 覆盖）。

- 离线用例（不需 DB）：加解密单元（往返 / 随机 nonce / 篡改检测）、鉴权缺失/过期 401。
- DB 用例（requires_db）：走完整 HTTP 栈 + 真实 DB——AC1 绑定落库只回掩码 + 真加密非明存、
  AC2 空/纯空白/非法 provider 拒绝且不写库、AC3 替换/解绑真实持久化、AC4 查询 + 租户隔离
  （越权=不存在不泄露存在性）、AC5 get_decrypted_key_for_user 内部接口契约。
"""

import time
import uuid
from collections.abc import Callable

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from muse.core.security import (
    KeyDecryptError,
    decrypt_api_key,
    encrypt_api_key,
)
from muse.core.settings import get_settings
from muse.main import app
from muse.models.account import ByokKey, User
from tests.conftest import requires_db

_client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True, scope="module")
def _client_lifespan() -> "object":
    """以上下文管理器模式运行 TestClient：所有请求共享同一持久事件循环（与 test_projects 同源）。"""
    with _client:
        yield


# ========== 离线：AES-GCM 加解密单元（不需 DB，陷阱②⑥）==========


def test_encrypt_decrypt_roundtrip() -> None:
    # 往返：decrypt(encrypt(x)) == x（AC1 真加密可逆）。
    plaintext = "sk-deepseek-abcdef1234567890a1b2"
    assert decrypt_api_key(encrypt_api_key(plaintext)) == plaintext


def test_encrypt_uses_random_nonce() -> None:
    # 同一明文两次加密密文必须不同（陷阱②：随机 nonce 绝不复用，否则灾难性泄露密钥流）。
    plaintext = "sk-same-key-encrypted-twice"
    assert encrypt_api_key(plaintext) != encrypt_api_key(plaintext)


def test_decrypt_tampered_ciphertext_raises() -> None:
    # 篡改密文 → GCM 认证失败 → KeyDecryptError（陷阱⑥：不 silently 吞成空串）。
    import base64

    token = encrypt_api_key("sk-tamper-target")
    blob = bytearray(base64.urlsafe_b64decode(token))
    blob[-1] ^= 0x01  # 翻转末字节（GCM tag 的一部分）
    tampered = base64.urlsafe_b64encode(bytes(blob)).decode()
    with pytest.raises(KeyDecryptError):
        decrypt_api_key(tampered)


def test_decrypt_garbage_raises() -> None:
    # 非法 base64 / 残缺密文 → KeyDecryptError，绝不返回空串。
    with pytest.raises(KeyDecryptError):
        decrypt_api_key("!!!not-valid-base64!!!")
    with pytest.raises(KeyDecryptError):
        decrypt_api_key("AAAA")  # 合法 base64 但长度不足以切出 nonce+密文


# ========== 离线：鉴权前置（无 token 不需 DB）==========


def test_bind_byok_without_token_401() -> None:
    # 未登录绑定 → 401 token_invalid（CurrentUser 依赖先于业务挡下，AC1 前置）。
    resp = _client.put("/api/byok", json={"apiKey": "sk-x", "provider": "deepseek"})
    assert resp.status_code == 401
    body = resp.json()
    assert set(body.keys()) == {"code", "message", "detail"}
    assert body["code"] == "token_invalid"


def test_get_byok_without_token_401() -> None:
    resp = _client.get("/api/byok")
    assert resp.status_code == 401
    assert resp.json()["code"] == "token_invalid"


def test_delete_byok_without_token_401() -> None:
    resp = _client.delete("/api/byok")
    assert resp.status_code == 401
    assert resp.json()["code"] == "token_invalid"


def test_bind_byok_expired_token_401() -> None:
    # 过期 access 绑定 → 401 token_expired（对接原型 #/login?state=expired）。
    settings = get_settings()
    now = int(time.time())
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "type": "access", "iat": now - 100, "exp": now - 10},
        settings.jwt_secret,
        algorithm="HS256",
    )
    resp = _client.put(
        "/api/byok",
        json={"apiKey": "sk-x", "provider": "deepseek"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "token_expired"


# ========== DB 端到端：AC1 绑定落库 + 只回掩码 + 真加密非明存 ==========


@requires_db
def test_bind_persists_encrypted_and_returns_masked_only(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
    db_engine: Engine,
) -> None:
    user = make_user("byok-bind@example.com")
    plaintext = "sk-deepseek-secret-key-tail1234"
    resp = _client.put(
        "/api/byok",
        json={"apiKey": plaintext, "provider": "deepseek"},
        headers=auth_headers(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    # camelCase 边界（AR4）：bound/provider/maskedKey，绝无明文字段（AC1 安全红线）。
    assert set(body.keys()) == {"bound", "provider", "maskedKey"}
    assert body["bound"] is True
    assert body["provider"] == "deepseek"
    assert body["maskedKey"] == "…1234"  # 中性掩码 …+尾 4 位（陷阱⑦不硬编码 sk-）
    # 响应体绝不含明文 Key（AC1）。
    assert plaintext not in resp.text

    # 真加密非明存：直查 DB，encrypted_key != 明文，且 decrypt 能还原（验证真 AES-GCM 加密）。
    with Session(db_engine) as session:
        row = session.scalar(select(ByokKey).where(ByokKey.user_id == user.id))
        assert row is not None
        assert row.encrypted_key != plaintext
        assert plaintext not in row.encrypted_key
        assert decrypt_api_key(row.encrypted_key) == plaintext
        assert row.key_suffix == "1234"


@requires_db
def test_bind_strips_whitespace_before_encrypt(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
    db_engine: Engine,
) -> None:
    # 首尾空白被 strip 后再加密（避免复制粘贴污染）；掩码尾 4 位取自 strip 后的明文。
    user = make_user("byok-strip@example.com")
    resp = _client.put(
        "/api/byok",
        json={"apiKey": "  sk-claude-padded-key-tailABCD  ", "provider": "claude"},
        headers=auth_headers(user),
    )
    assert resp.status_code == 200
    assert resp.json()["maskedKey"] == "…ABCD"
    with Session(db_engine) as session:
        row = session.scalar(select(ByokKey).where(ByokKey.user_id == user.id))
        assert row is not None
        assert decrypt_api_key(row.encrypted_key) == "sk-claude-padded-key-tailABCD"


@requires_db
def test_bind_short_key_masks_full_suffix_no_plaintext_leak(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
    db_engine: Engine,
) -> None:
    # 回归（code-review Finding #1）：≤4 字符 Key 不得因 key[-4:] 退化而把整串明文写进
    # key_suffix / maskedKey——短 Key 全打码，明文只在密文里（陷阱① 安全红线）。
    user = make_user("byok-shortkey@example.com")
    short_key = "abc"  # 长度 3 ≤ _SUFFIX_LEN，切片 "abc"[-4:] 会返回整串
    resp = _client.put(
        "/api/byok",
        json={"apiKey": short_key, "provider": "custom"},
        headers=auth_headers(user),
    )
    assert resp.status_code == 200
    # 掩码全打码、绝不回显明文短 Key。
    assert resp.json()["maskedKey"] == "…***"
    assert short_key not in resp.text
    with Session(db_engine) as session:
        row = session.scalar(select(ByokKey).where(ByokKey.user_id == user.id))
        assert row is not None
        # key_suffix 列不含明文；明文仅存在于可解密的密文中。
        assert row.key_suffix == "***"
        assert short_key not in row.key_suffix
        assert decrypt_api_key(row.encrypted_key) == short_key


# ========== DB 端到端：AC2 校验（空/纯空白/非法 provider 拒绝且不写库）==========


@requires_db
def test_bind_empty_key_rejected_422(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
    db_engine: Engine,
) -> None:
    # 明显空串 "" 被 schema min_length=1 拦 → 422 validation_error，不写库（AC2）。
    user = make_user("byok-empty@example.com")
    resp = _client.put(
        "/api/byok", json={"apiKey": "", "provider": "deepseek"}, headers=auth_headers(user)
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"
    with Session(db_engine) as session:
        assert session.scalar(select(ByokKey).where(ByokKey.user_id == user.id)) is None


@requires_db
def test_bind_whitespace_only_key_rejected_400(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
    db_engine: Engine,
) -> None:
    # 纯空白 "   " 过得了 min_length，但 service._validate_key strip 后判空 → 400
    # byok_invalid_key，不写库（AC2 两条路径分工，dev notes 明确）。
    user = make_user("byok-blank@example.com")
    resp = _client.put(
        "/api/byok", json={"apiKey": "     ", "provider": "deepseek"}, headers=auth_headers(user)
    )
    assert resp.status_code == 400
    body = resp.json()
    assert set(body.keys()) == {"code", "message", "detail"}
    assert body["code"] == "byok_invalid_key"
    with Session(db_engine) as session:
        assert session.scalar(select(ByokKey).where(ByokKey.user_id == user.id)) is None


@requires_db
def test_bind_invalid_provider_rejected_422(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
    db_engine: Engine,
) -> None:
    # 非法 provider 被 schema Literal 拦 → 422，不写库（AC2）。
    user = make_user("byok-provider@example.com")
    resp = _client.put(
        "/api/byok",
        json={"apiKey": "sk-valid-key", "provider": "openai"},
        headers=auth_headers(user),
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"
    with Session(db_engine) as session:
        assert session.scalar(select(ByokKey).where(ByokKey.user_id == user.id)) is None


@requires_db
def test_bind_key_too_long_rejected_422(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # 超长 Key（>512）被 schema max_length 拦 → 422（AC2 防超大输入）。
    user = make_user("byok-toolong@example.com")
    resp = _client.put(
        "/api/byok",
        json={"apiKey": "s" * 513, "provider": "custom"},
        headers=auth_headers(user),
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


# ========== DB 端到端：AC3 替换（覆盖，唯一约束）+ 解绑 ==========


@requires_db
def test_replace_key_overwrites_single_record(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
    db_engine: Engine,
) -> None:
    # 绑定 A → 再 PUT 绑定 B → GET 掩码为 B 的尾 4 位、DB 仅一条记录（唯一约束，AC3 替换）。
    user = make_user("byok-replace@example.com")
    headers = auth_headers(user)
    _client.put(
        "/api/byok",
        json={"apiKey": "sk-first-key-tailAAAA", "provider": "deepseek"},
        headers=headers,
    )
    resp_b = _client.put(
        "/api/byok",
        json={"apiKey": "sk-second-key-tailBBBB", "provider": "claude"},
        headers=headers,
    )
    assert resp_b.status_code == 200
    assert resp_b.json()["maskedKey"] == "…BBBB"
    assert resp_b.json()["provider"] == "claude"

    # GET 反映最新绑定；DB 仅一条（替换非新增）。
    status = _client.get("/api/byok", headers=headers).json()
    assert status["maskedKey"] == "…BBBB"
    with Session(db_engine) as session:
        rows = session.scalars(select(ByokKey).where(ByokKey.user_id == user.id)).all()
        assert len(rows) == 1
        assert decrypt_api_key(rows[0].encrypted_key) == "sk-second-key-tailBBBB"


@requires_db
def test_unbind_deletes_and_falls_back_to_empty(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
    db_engine: Engine,
) -> None:
    # 绑定 → DELETE → 204 无体 → GET 返 bound:false、DB 无记录（AC3 解绑真实持久化）。
    user = make_user("byok-unbind@example.com")
    headers = auth_headers(user)
    _client.put(
        "/api/byok",
        json={"apiKey": "sk-to-be-unbound-tailCCCC", "provider": "deepseek"},
        headers=headers,
    )
    resp = _client.delete("/api/byok", headers=headers)
    assert resp.status_code == 204
    assert resp.content == b""  # 204 No Content 无响应体

    status = _client.get("/api/byok", headers=headers).json()
    assert status == {"bound": False, "provider": None, "maskedKey": None}
    with Session(db_engine) as session:
        assert session.scalar(select(ByokKey).where(ByokKey.user_id == user.id)) is None


@requires_db
def test_unbind_when_not_bound_is_idempotent_204(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # 未绑定时解绑 → 幂等 204（「确保没有绑定」的意图，删 0 行也成功）。
    user = make_user("byok-unbind-noop@example.com")
    resp = _client.delete("/api/byok", headers=auth_headers(user))
    assert resp.status_code == 204


# ========== DB 端到端：AC4 查询空态 + 租户隔离（越权=不存在，NFR3）==========


@requires_db
def test_get_status_unbound_returns_false(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # 未绑定 GET → bound:false 空态（AC4）。
    user = make_user("byok-status-empty@example.com")
    resp = _client.get("/api/byok", headers=auth_headers(user))
    assert resp.status_code == 200
    assert resp.json() == {"bound": False, "provider": None, "maskedKey": None}


@requires_db
def test_tenant_isolation_get_and_delete(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
    db_engine: Engine,
) -> None:
    # A 绑定后：B GET 只见自己（bound:false）、B DELETE 删不到 A 的（A 记录分毫未动，AC4/NFR3）。
    alice = make_user("byok-tenant-a@example.com")
    bob = make_user("byok-tenant-b@example.com")
    _client.put(
        "/api/byok",
        json={"apiKey": "sk-alice-secret-tailAAAA", "provider": "deepseek"},
        headers=auth_headers(alice),
    )

    # B 查不到 A 的绑定（不泄露 A 是否绑定）。
    bob_status = _client.get("/api/byok", headers=auth_headers(bob)).json()
    assert bob_status == {"bound": False, "provider": None, "maskedKey": None}

    # B 解绑（幂等 204）删不到 A 的记录。
    assert _client.delete("/api/byok", headers=auth_headers(bob)).status_code == 204
    with Session(db_engine) as session:
        alice_row = session.scalar(select(ByokKey).where(ByokKey.user_id == alice.id))
        assert alice_row is not None  # A 的记录分毫未动
        assert decrypt_api_key(alice_row.encrypted_key) == "sk-alice-secret-tailAAAA"

    # A 自己仍能查到掩码。
    alice_status = _client.get("/api/byok", headers=auth_headers(alice)).json()
    assert alice_status["bound"] is True
    assert alice_status["maskedKey"] == "…AAAA"


# ========== DB 端到端：AC5 内部接口 get_decrypted_key_for_user（供 Epic 2 消费）==========


@requires_db
async def test_get_decrypted_key_for_user_contract(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # 绑定后返明文、未绑定返 None（AC5 契约，供 Epic 2 Provider 层决定走用户 Key 还是托管）。
    # 用独立 async engine（本用例自己的事件循环内创建/释放），避免与 module 级 TestClient 的
    # 应用 async engine 跨事件循环复用（同 test_projects「Event loop is closed」治理思路）。
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from muse.services import byok_service

    bound_user = make_user("byok-internal-bound@example.com")
    unbound_user = make_user("byok-internal-unbound@example.com")
    plaintext = "sk-internal-consume-tailDDDD"
    _client.put(
        "/api/byok",
        json={"apiKey": plaintext, "provider": "custom"},
        headers=auth_headers(bound_user),
    )

    engine = create_async_engine(get_settings().database_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_maker() as session:
            got = await byok_service.get_decrypted_key_for_user(session, bound_user.id)
            assert got == plaintext  # 已绑定 → 明文
            none = await byok_service.get_decrypted_key_for_user(session, unbound_user.id)
            assert none is None  # 未绑定 → None
    finally:
        await engine.dispose()
