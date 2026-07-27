"""Story 2.2 验证：探索会话根 get-or-create + 模式独立（全 AC 覆盖）。

- 离线用例：鉴权缺失 401、过期 token 401（不需 DB）。
- DB 用例（requires_db）：走完整 HTTP 栈 + 真实 DB——get-or-create 首建落库、幂等重入
  返同一会话、mode 取自 project.mode（接口无 mode 入参）、租户隔离（他人 project 404）、
  project 不存在 404、并发兜底（唯一约束 + 重查）、camelCase 边界。
"""

import time
import uuid
from collections.abc import Callable

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from muse.core.settings import get_settings
from muse.main import app
from muse.models.account import User
from muse.repositories import exploration_repo
from tests.conftest import requires_db

_client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True, scope="module")
def _client_lifespan() -> "object":
    """以上下文管理器模式运行 TestClient：所有请求共享同一持久事件循环。

    应用的 async DB engine 是模块级单例，连接池绑定首个事件循环；非上下文模式下每请求起
    临时循环，同一用例内发两次请求（如连 POST 两次验幂等）时第二次会撞残留连接 →
    Event loop is closed。用 `with _client` 固定单一循环即解（与 test_projects 同源治理）。
    """
    with _client:
        yield


def _create_project(user: User, headers: dict[str, str], mode: str = "guided") -> str:
    """建一部作品并返回其 id（探索会话挂在 project 下，用例前置）。"""
    resp = _client.post("/api/projects", json={"mode": mode}, headers=headers)
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------- 离线：鉴权前置（无 token / 过期 token 不需 DB） ----------


def test_enter_exploration_without_token_401() -> None:
    # 未登录进入探索 → 401 token_invalid（CurrentUser 依赖在鉴权入口挡下，AC1 前置）。
    resp = _client.post(f"/api/projects/{uuid.uuid4()}/explore")
    assert resp.status_code == 401
    body = resp.json()
    assert set(body.keys()) == {"code", "message", "detail"}
    assert body["code"] == "token_invalid"


def test_enter_exploration_expired_token_401() -> None:
    # 过期 access → 401 token_expired（对接原型 #/login?state=expired）。
    settings = get_settings()
    now = int(time.time())
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "type": "access", "iat": now - 100, "exp": now - 10},
        settings.jwt_secret,
        algorithm="HS256",
    )
    resp = _client.post(
        f"/api/projects/{uuid.uuid4()}/explore",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "token_expired"


# ---------- DB 端到端：AC1 get-or-create 首建真实落库 + camelCase 边界 ----------


@requires_db
def test_enter_exploration_creates_and_returns_camel(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
    db_engine: Engine,
) -> None:
    user = make_user("explore-create@example.com")
    headers = auth_headers(user)
    project_id = _create_project(user, headers, mode="guided")

    resp = _client.post(f"/api/projects/{project_id}/explore", headers=headers)
    assert resp.status_code == 200  # 幂等 get-or-create 返 200，非恒新建的 201（陷阱⑦）
    body = resp.json()
    # camelCase 边界（AR4）：id/projectId/mode/updatedAt。
    assert set(body.keys()) == {"id", "projectId", "mode", "updatedAt"}
    assert body["projectId"] == project_id
    assert body["mode"] == "guided"
    assert body["updatedAt"].endswith("Z")  # UTCDateTime 带 Z 后缀（AR5）

    # 真实落库：DB 恰有一条属该 project 的会话。
    with db_engine.begin() as conn:
        count = conn.execute(
            text(
                "SELECT count(*) FROM exploration_session WHERE project_id = :pid"
            ),
            {"pid": project_id},
        ).scalar_one()
    assert count == 1


# ---------- DB 端到端：AC1/AC3 幂等重入返同一会话、不重复建 ----------


@requires_db
def test_enter_exploration_idempotent_returns_same_session(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
    db_engine: Engine,
) -> None:
    user = make_user("explore-idem@example.com")
    headers = auth_headers(user)
    project_id = _create_project(user, headers, mode="guided")

    first = _client.post(f"/api/projects/{project_id}/explore", headers=headers).json()
    second = _client.post(f"/api/projects/{project_id}/explore", headers=headers).json()

    # 幂等：两次返回同一 session id（AC1），已存在会话不重复建（AC3）。
    assert first["id"] == second["id"]
    with db_engine.begin() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM exploration_session WHERE project_id = :pid"),
            {"pid": project_id},
        ).scalar_one()
    assert count == 1


# ---------- DB 端到端：AC2 mode 取自 project.mode（接口无 mode 入参） ----------


@requires_db
@pytest.mark.parametrize("mode", ["guided", "free"])
def test_enter_exploration_mode_from_project(
    mode: str,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # 会话 mode 恒等于 project.mode（AC2 单一事实源）：free 作品 → free、guided → guided。
    user = make_user(f"explore-mode-{mode}@example.com")
    headers = auth_headers(user)
    project_id = _create_project(user, headers, mode=mode)

    resp = _client.post(f"/api/projects/{project_id}/explore", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["mode"] == mode


@requires_db
def test_enter_exploration_ignores_client_mode_in_body(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # AC2/AC3 技术底线：接口无 mode 入参——即使客户端在 body 塞 mode，也被忽略，
    # 会话 mode 恒取 project.mode。根除「前端改参数即切模式」的数据通道（陷阱③）。
    user = make_user("explore-body-mode@example.com")
    headers = auth_headers(user)
    project_id = _create_project(user, headers, mode="guided")

    # guided 作品，body 妄图传 free —— 结果仍是 guided（body 里的 mode 无效）。
    resp = _client.post(
        f"/api/projects/{project_id}/explore", json={"mode": "free"}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["mode"] == "guided"


# ---------- DB 端到端：AC5 租户隔离（他人 project 404，越权=不存在，陷阱①） ----------


@requires_db
def test_enter_exploration_others_project_returns_404(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
    db_engine: Engine,
) -> None:
    # B 对 A 的 project 进入探索 → 404 project_not_found（与"不存在"同码，不泄露存在性，不 403）。
    alice = make_user("explore-owner-a@example.com")
    bob = make_user("explore-owner-b@example.com")
    project_id = _create_project(alice, auth_headers(alice), mode="guided")

    resp = _client.post(
        f"/api/projects/{project_id}/explore", headers=auth_headers(bob)
    )
    assert resp.status_code == 404
    body = resp.json()
    assert set(body.keys()) == {"code", "message", "detail"}  # AR5 envelope 三要素
    assert body["code"] == "project_not_found"

    # 越权未生效：A 的 project 没有被 B 建出会话。
    with db_engine.begin() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM exploration_session WHERE project_id = :pid"),
            {"pid": project_id},
        ).scalar_one()
    assert count == 0


@requires_db
def test_enter_exploration_nonexistent_project_returns_404(
    make_user: Callable[..., User], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    # 随机 UUID（压根不存在）→ 与"越权"完全相同的 404 project_not_found（不泄露存在性）。
    user = make_user("explore-404@example.com")
    resp = _client.post(
        f"/api/projects/{uuid.uuid4()}/explore", headers=auth_headers(user)
    )
    assert resp.status_code == 404
    body = resp.json()
    assert set(body.keys()) == {"code", "message", "detail"}
    assert body["code"] == "project_not_found"


# ---------- DB 端到端：非法路径参数 UUID 解析 ----------


@requires_db
def test_enter_exploration_invalid_uuid_422(
    make_user: Callable[..., User], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    # 非法 UUID 路径参数 → 422（FastAPI 类型解析）。需真实身份：本库鉴权先于参数校验，
    # 故走 DB 门禁（与 test_projects 的 invalid_uuid 用例对齐）。
    user = make_user("explore-bad-uuid@example.com")
    resp = _client.post("/api/projects/not-a-uuid/explore", headers=auth_headers(user))
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


# ---------- DB 端到端：AC1 并发兜底（唯一约束 IntegrityError → rollback → 重查） ----------


@requires_db
def test_enter_exploration_concurrent_fallback_returns_existing(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
    db_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """确定性验证陷阱②兜底：强制 get 步 miss → create 撞唯一约束 → 兜底重查返已存在。

    真实并发（两请求同时 miss→双 insert）单测难稳定复现，故用 monkeypatch 模拟「get 步
    看不到已存在会话」：先正常建一条会话，再让 get_session_by_project 首次返回 None，
    service 遂走 create → 撞 (user_id, project_id) 唯一约束 IntegrityError → rollback →
    重查（第二次调用走真实查询）→ 返回已存在会话。验证接口最终仍幂等、DB 不重复建。
    """
    user = make_user("explore-race@example.com")
    headers = auth_headers(user)
    project_id = _create_project(user, headers, mode="guided")

    # 先正常建立会话（此刻 DB 已有一条）。
    first = _client.post(f"/api/projects/{project_id}/explore", headers=headers).json()

    # 让 get_session_by_project 首次返回 None（模拟并发 miss），后续调用走真实查询。
    real_get = exploration_repo.get_session_by_project
    calls = {"n": 0}

    async def _fake_get(session: object, user_id: object, project_id: object) -> object:
        calls["n"] += 1
        if calls["n"] == 1:
            return None  # 强制 miss → 走 create 分支
        return await real_get(session, user_id, project_id)  # 重查用真实查询

    monkeypatch.setattr(exploration_repo, "get_session_by_project", _fake_get)

    resp = _client.post(f"/api/projects/{project_id}/explore", headers=headers)
    assert resp.status_code == 200
    # 兜底返回先到者建的同一会话（幂等未被破坏）。
    assert resp.json()["id"] == first["id"]

    # DB 仍只一条：唯一约束挡住了第二次插入。
    with db_engine.begin() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM exploration_session WHERE project_id = :pid"),
            {"pid": project_id},
        ).scalar_one()
    assert count == 1
