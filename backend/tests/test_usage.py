"""Story 1.8 验证：托管免费额度护栏与用量展示（全 AC 覆盖）。

- 离线用例（不需 DB）：鉴权缺失/过期 401；护栏阈值逻辑单元（mock repo/byok，放行 / 触顶 >=
  边界 / BYOK 短路三分支）——**按 tokens 阈值触顶，不写「插 N 行流水→429」**（防固化
  COUNT(*)≠章数 的错口径，story Task 3 高危提示）。
- DB 用例（requires_db）：走真实 DB——AC1 记账落库（tokens/cost Decimal 精确非浮点）、
  AC2 护栏放行/触顶 429、AC3 展示 used 随记账增长、AC4 BYOK 豁免（即便超阈值也放行）、
  租户隔离（NFR3，A 记账 B 不可见）。

护栏计量单位 = tokens（SUM(total_tokens) vs settings.free_quota_tokens，dev 定档）；触顶判定 >=。
"""

import time
import uuid
from collections.abc import Callable
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from muse.core.errors import ErrorEnvelope
from muse.core.settings import get_settings
from muse.main import app
from muse.models.account import UsageLedger, User
from muse.services import usage_service
from tests.conftest import requires_db

_client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True, scope="module")
def _client_lifespan() -> "object":
    """以上下文管理器模式运行 TestClient：所有请求共享同一持久事件循环（与 test_byok 同源）。"""
    with _client:
        yield


# ========== 离线：鉴权前置（无 token 不需 DB）==========


def test_get_usage_without_token_401() -> None:
    # 未登录查用量 → 401 token_invalid（CurrentUser 依赖先于业务挡下，AC3 前置）。
    resp = _client.get("/api/usage")
    assert resp.status_code == 401
    body = resp.json()
    assert set(body.keys()) == {"code", "message", "detail"}
    assert body["code"] == "token_invalid"


def test_get_usage_expired_token_401() -> None:
    # 过期 access → 401 token_expired（对接原型 #/login?state=expired）。
    settings = get_settings()
    now = int(time.time())
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "type": "access", "iat": now - 100, "exp": now - 10},
        settings.jwt_secret,
        algorithm="HS256",
    )
    resp = _client.get("/api/usage", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "token_expired"


# ========== 离线：护栏阈值逻辑单元（mock repo/byok，不需 DB，AC2/AC4 三分支）==========
# 关键：按 tokens 阈值触顶，**不**写「插 N 行流水→429」（防固化 COUNT(*)≠章数 错口径）。


async def test_check_quota_under_threshold_passes() -> None:
    # 托管用户已用 < 阈值 → 放行，返回 remaining（AC2 放行分支）。
    uid = uuid.uuid4()
    quota = get_settings().free_quota_tokens
    with (
        patch.object(
            usage_service.byok_service,
            "get_binding_status",
            # 未绑定 BYOK（bound=False）→ 走托管护栏
            new=AsyncMock(
                return_value={"bound": False, "provider": None, "masked_key": None}
            ),
        ),
        patch.object(
            usage_service.account_repo,
            "sum_hosted_usage",
            new=AsyncMock(return_value=quota - 100),  # 已用差 100 tokens 触顶
        ),
    ):
        result = await usage_service.check_quota(AsyncMock(), uid)
    assert result["quota_applies"] is True
    assert result["billing_path"] == "hosted"
    assert result["used"] == quota - 100
    assert result["remaining"] == 100


async def test_check_quota_at_threshold_raises_429() -> None:
    # 边界值 used == quota 必测（触顶判定用 >=：已用满即拦，陷阱④）→ 抛 429 quota_exceeded。
    uid = uuid.uuid4()
    quota = get_settings().free_quota_tokens
    with (
        patch.object(
            usage_service.byok_service,
            "get_binding_status",
            new=AsyncMock(
                return_value={"bound": False, "provider": None, "masked_key": None}
            ),
        ),
        patch.object(
            usage_service.account_repo,
            "sum_hosted_usage",
            new=AsyncMock(return_value=quota),  # 恰好用满
        ),
        pytest.raises(ErrorEnvelope) as exc_info,
    ):
        await usage_service.check_quota(AsyncMock(), uid)
    err = exc_info.value
    assert err.code == "quota_exceeded"
    assert err.http_status == 429
    assert isinstance(err.detail, dict)
    assert err.detail["quotaExceeded"] is True
    assert err.detail["used"] == quota
    assert err.detail["quota"] == quota


async def test_check_quota_over_threshold_raises_429() -> None:
    # 已用 > 阈值 → 同样触顶抛 429（>= 判定覆盖超额）。
    uid = uuid.uuid4()
    quota = get_settings().free_quota_tokens
    with (
        patch.object(
            usage_service.byok_service,
            "get_binding_status",
            new=AsyncMock(
                return_value={"bound": False, "provider": None, "masked_key": None}
            ),
        ),
        patch.object(
            usage_service.account_repo,
            "sum_hosted_usage",
            new=AsyncMock(return_value=quota + 5000),
        ),
        pytest.raises(ErrorEnvelope) as exc_info,
    ):
        await usage_service.check_quota(AsyncMock(), uid)
    assert exc_info.value.http_status == 429


async def test_check_quota_byok_short_circuits_without_checking_usage() -> None:
    # BYOK 优先短路（陷阱③）：已绑定 → 立即放行、**根本不查 usage 累计**（不调 sum_hosted_usage）。
    uid = uuid.uuid4()
    sum_spy = AsyncMock(return_value=999_999_999)  # 即便造超大已用量也不该被调用
    with (
        patch.object(
            usage_service.byok_service,
            "get_binding_status",
            new=AsyncMock(
                return_value={
                    "bound": True,
                    "provider": "deepseek",
                    "masked_key": "…tail",
                }
            ),  # 已绑定 BYOK
        ),
        patch.object(usage_service.account_repo, "sum_hosted_usage", new=sum_spy),
    ):
        result = await usage_service.check_quota(AsyncMock(), uid)
    assert result == {"quota_applies": False, "billing_path": "byok"}
    sum_spy.assert_not_awaited()  # 短路：BYOK 用户根本不查托管累计


# ========== DB 端到端：AC1 记账落库（tokens/cost Decimal 精确非浮点）==========


@requires_db
async def test_record_usage_persists_with_exact_decimal_cost(
    make_user: Callable[..., User],
) -> None:
    # AC1：record_usage 落库 → 直查 DB 有对应行、tokens/billing_path 正确、cost 为 Decimal 精确值
    # （非浮点误差，陷阱②）。用独立 async engine（本用例自己的事件循环内），避免与 module 级
    # TestClient 的应用 async engine 跨事件循环复用（test_byok 同源治理思路）。
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    user = make_user("usage-record@example.com")
    # cost 全程 Decimal（陷阱②）：断言落库后仍是 Decimal 且值精确。注意 Decimal 相加本就精确
    # （0.1+0.2 == 0.3），漂移只发生在 float——本用例守的是「cost 列/ORM/驱动不把值降级成
    # float」这条链路（下方 isinstance + 精确相等断言），而非「Decimal 相加会不会漂移」。
    cost = Decimal("0.100000") + Decimal("0.200000")
    engine = create_async_engine(get_settings().database_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_maker() as session:
            usage = await usage_service.record_usage(
                session,
                user_id=user.id,
                billing_path="hosted",
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
                cost=cost,
                model_name="deepseek-chat",
            )
            assert usage.id is not None
    finally:
        await engine.dispose()

    # 直查 DB（同步引擎）核对落库值。
    from tests.conftest import _sync_engine

    with Session(_sync_engine()) as session:
        row = session.scalar(select(UsageLedger).where(UsageLedger.user_id == user.id))
        assert row is not None
        assert row.billing_path == "hosted"
        assert row.prompt_tokens == 100
        assert row.completion_tokens == 50
        assert row.total_tokens == 150
        assert row.model_name == "deepseek-chat"
        # cost 落库后仍精确等于 Decimal("0.3") 且类型仍是 Decimal——证明 ORM/Numeric/驱动
        # 未把值降级成 float（float 才会出现 0.30000000000000004 之类）。
        assert row.cost == Decimal("0.300000")
        assert isinstance(row.cost, Decimal)


# ========== DB 端到端：AC2 护栏放行/触顶（按 tokens 阈值，非流水行数）==========


@requires_db
async def test_check_quota_db_passes_then_blocks_at_token_threshold(
    make_user: Callable[..., User],
) -> None:
    # AC2：托管用户未触顶 check_quota 返 remaining；记账累计到 tokens 阈值后 → 抛 429。
    # **按 tokens 阈值触顶**（记满阈值 tokens），不是「插满 N 行」——一行就可记满阈值 tokens。
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    user = make_user("usage-guard@example.com")
    quota = get_settings().free_quota_tokens
    engine = create_async_engine(get_settings().database_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_maker() as session:
            # 未记账 → 放行、remaining 满额。
            first = await usage_service.check_quota(session, user.id)
            assert first["quota_applies"] is True
            assert first["used"] == 0
            assert first["remaining"] == quota

            # 记一行 hosted 用量恰好用满阈值（一行即可达 tokens 阈值，验证按 tokens 非行数）。
            await usage_service.record_usage(
                session,
                user_id=user.id,
                billing_path="hosted",
                prompt_tokens=quota,
                completion_tokens=0,
                total_tokens=quota,
                cost=Decimal("1.0"),
            )

            # 已用 == 阈值 → 触顶抛 429（>= 判定）。
            with pytest.raises(ErrorEnvelope) as exc_info:
                await usage_service.check_quota(session, user.id)
            assert exc_info.value.http_status == 429
            assert exc_info.value.code == "quota_exceeded"
            assert isinstance(exc_info.value.detail, dict)
            assert exc_info.value.detail["quotaExceeded"] is True
    finally:
        await engine.dispose()


# ========== DB 端到端：AC3 展示（GET /api/usage，used 随记账增长）==========


@requires_db
def test_get_usage_hosted_view_reflects_recorded_usage(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
    db_engine: Engine,
) -> None:
    # AC3：托管用户 GET /api/usage → 200 billingPath/quotaApplies/used/quota/remaining。
    user = make_user("usage-view@example.com")
    quota = get_settings().free_quota_tokens

    # 初始无用量：used=0、remaining 满额。
    resp = _client.get("/api/usage", headers=auth_headers(user))
    assert resp.status_code == 200
    body = resp.json()
    # camelCase 边界（AR4）。
    assert body["billingPath"] == "hosted"
    assert body["quotaApplies"] is True
    assert body["used"] == 0
    assert body["quota"] == quota
    assert body["remaining"] == quota
    assert body["resetAt"] is None  # V1 累计总量护栏，不做每日重置

    # 直插一行 hosted 流水（模拟 Epic 2 记账），used 随之增长。
    with Session(db_engine) as session:
        session.add(
            UsageLedger(
                user_id=user.id,
                billing_path="hosted",
                prompt_tokens=1000,
                completion_tokens=200,
                total_tokens=1200,
                cost=Decimal("0.05"),
            )
        )
        session.commit()

    resp2 = _client.get("/api/usage", headers=auth_headers(user))
    body2 = resp2.json()
    assert body2["used"] == 1200
    assert body2["remaining"] == quota - 1200


# ========== DB 端到端：AC4 BYOK 豁免（即便超阈值也放行 + 展示 null）==========


@requires_db
async def test_byok_user_exempt_from_quota_even_over_threshold(
    make_user: Callable[..., User],
) -> None:
    # AC4：绑定 BYOK 后即便 hosted 流水已超阈值，check_quota 仍放行（BYOK 优先判定，陷阱③）。
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from muse.services import byok_service

    user = make_user("usage-byok@example.com")
    quota = get_settings().free_quota_tokens
    engine = create_async_engine(get_settings().database_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_maker() as session:
            # 先造超阈值的 hosted 流水（超过免费额度）。
            await usage_service.record_usage(
                session,
                user_id=user.id,
                billing_path="hosted",
                prompt_tokens=quota + 10_000,
                completion_tokens=0,
                total_tokens=quota + 10_000,
                cost=Decimal("2.0"),
            )
            # 再绑定 BYOK。
            await byok_service.bind_or_replace_key(
                session, user.id, "deepseek", "sk-byok-user-key-tailZZZZ"
            )

            # BYOK 优先短路：即便 hosted 已超阈值也放行（不占免费额度，AC4）。
            result = await usage_service.check_quota(session, user.id)
            assert result == {"quota_applies": False, "billing_path": "byok"}

            # 展示同样返 BYOK 豁免语义态：used/quota/remaining 为 null。
            view = await usage_service.get_usage_view(session, user.id)
            assert view["billing_path"] == "byok"
            assert view["quota_applies"] is False
            assert view["used"] is None
            assert view["quota"] is None
            assert view["remaining"] is None
    finally:
        await engine.dispose()


@requires_db
def test_get_usage_byok_view_returns_exempt_semantics(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # AC4：BYOK 用户 GET /api/usage → billingPath:"byok"/quotaApplies:false/其余字段 null。
    user = make_user("usage-byok-view@example.com")
    # 通过 API 绑定 BYOK。
    _client.put(
        "/api/byok",
        json={"apiKey": "sk-byok-view-key-tailWWWW", "provider": "claude"},
        headers=auth_headers(user),
    )
    resp = _client.get("/api/usage", headers=auth_headers(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["billingPath"] == "byok"
    assert body["quotaApplies"] is False
    assert body["used"] is None
    assert body["quota"] is None
    assert body["remaining"] is None


# ========== DB 端到端：租户隔离（NFR3，A 记账 B 不可见）==========


@requires_db
def test_tenant_isolation_usage_not_leaked(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
    db_engine: Engine,
) -> None:
    # A 记账后：B GET /api/usage 只见自己（used=0，看不到 A 的用量，NFR3 陷阱⑦）。
    alice = make_user("usage-tenant-a@example.com")
    bob = make_user("usage-tenant-b@example.com")
    with Session(db_engine) as session:
        session.add(
            UsageLedger(
                user_id=alice.id,
                billing_path="hosted",
                prompt_tokens=5000,
                completion_tokens=1000,
                total_tokens=6000,
                cost=Decimal("0.3"),
            )
        )
        session.commit()

    # B 只见自己：used=0，看不到 A 的 6000 tokens。
    bob_body = _client.get("/api/usage", headers=auth_headers(bob)).json()
    assert bob_body["used"] == 0

    # A 自己能看到自己的用量。
    alice_body = _client.get("/api/usage", headers=auth_headers(alice)).json()
    assert alice_body["used"] == 6000


# ========== DB 端到端：陷阱⑧ sum_hosted_usage 只累计 hosted、排除 byok 行 ==========


@requires_db
async def test_sum_hosted_usage_excludes_byok_rows(
    make_user: Callable[..., User],
) -> None:
    # 陷阱⑧/AC4/NFR5：同一用户同时有 hosted 行与 byok 行时，护栏聚合**只累计 hosted**、
    # byok 行不占托管额度。直查 repo.sum_hosted_usage（绕过 check_quota 的 BYOK 短路），
    # 否则该过滤条件（billing_path=="hosted"）被误删也无用例会失败——现有其它用例的 BYOK
    # 分支都在 _is_byok_user 提前 return、从不执行到这里的过滤判定。
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from muse.repositories import account_repo

    user = make_user("usage-mixed-billing@example.com")
    engine = create_async_engine(get_settings().database_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_maker() as session:
            # hosted 行：应计入护栏累计。
            await usage_service.record_usage(
                session,
                user_id=user.id,
                billing_path="hosted",
                prompt_tokens=800,
                completion_tokens=200,
                total_tokens=1000,
                cost=Decimal("0.05"),
            )
            # byok 行：不占托管额度，绝不计入。
            await usage_service.record_usage(
                session,
                user_id=user.id,
                billing_path="byok",
                prompt_tokens=7000,
                completion_tokens=3000,
                total_tokens=10_000,
                cost=Decimal("0.5"),
            )
            # 只累计 hosted 的 1000 tokens，byok 的 10000 被排除。
            used = await account_repo.sum_hosted_usage(session, user.id)
            assert used == 1000
    finally:
        await engine.dispose()
