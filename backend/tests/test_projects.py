"""Story 1.4 验证：作品创建与列表持久化 + 空/失败态契约（全 AC 覆盖）。

- 离线用例：鉴权缺失 401、过期 token 401（不需 DB）。
- DB 用例（requires_db）：走完整 HTTP 栈 + 真实 DB——入参校验（mode 非法/缺失 422，
  因鉴权先于 body 校验需真实身份）、新建落库归属 user_id、未命名回落、列表按 updated_at
  倒序、租户隔离（他人作品查不到）、空列表返回 []、camelCase 边界。
"""

import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from muse.core.settings import get_settings
from muse.main import app
from muse.models.account import User
from tests.conftest import requires_db

_client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True, scope="module")
def _client_lifespan() -> "object":
    """以上下文管理器模式运行 TestClient：所有请求共享同一持久事件循环。

    应用的 async DB engine 是模块级单例，连接池绑定首个事件循环；非上下文模式下每请求起
    临时循环，同一用例内发两次请求（如 create+list）时第二次会撞上残留连接 → Event loop
    is closed。用 `with _client` 固定单一循环即解（与 test_auth_login 同源治理）。
    """
    with _client:
        yield


# ---------- 离线：鉴权缺失 + 入参校验（不需 DB） ----------


def test_create_project_without_token_401() -> None:
    # 未登录建作品 → 401 token_invalid（CurrentUser 依赖在鉴权入口挡下，AC1 前置）。
    resp = _client.post("/api/projects", json={"mode": "guided", "title": "测试"})
    assert resp.status_code == 401
    body = resp.json()
    assert set(body.keys()) == {"code", "message", "detail"}
    assert body["code"] == "token_invalid"


def test_list_projects_without_token_401() -> None:
    resp = _client.get("/api/projects")
    assert resp.status_code == 401
    assert resp.json()["code"] == "token_invalid"


def test_create_project_expired_token_401() -> None:
    # 过期 access 建作品 → 401 token_expired（对接原型 #/login?state=expired）。
    settings = get_settings()
    now = int(time.time())
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "type": "access", "iat": now - 100, "exp": now - 10},
        settings.jwt_secret,
        algorithm="HS256",
    )
    resp = _client.post(
        "/api/projects",
        json={"mode": "guided"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "token_expired"


@requires_db
def test_create_project_invalid_mode_422(
    make_user: Callable[..., User], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    # mode 只接受 guided/free；其它值 Pydantic Literal 校验拒绝 → 422 validation_error。
    # 需真实身份（鉴权先于 body 校验），故走 DB 门禁。
    user = make_user("mode@example.com")
    resp = _client.post(
        "/api/projects", json={"mode": "invalid-mode"}, headers=auth_headers(user)
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


@requires_db
def test_create_project_missing_mode_422(
    make_user: Callable[..., User], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    # mode 必填，缺失 → 422。
    user = make_user("nomode@example.com")
    resp = _client.post("/api/projects", json={"title": "无模式"}, headers=auth_headers(user))
    assert resp.status_code == 422


# ---------- DB 端到端：AC1 新建真实落库归属 user_id ----------


@requires_db
def test_create_project_persists_and_returns_camel(
    make_user: Callable[..., User], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    user = make_user("alice@example.com")
    resp = _client.post(
        "/api/projects", json={"mode": "guided", "title": "雾港回声"}, headers=auth_headers(user)
    )
    assert resp.status_code == 201
    body = resp.json()
    # camelCase 边界（AR4）：id/title/mode/phase/updatedAt。
    assert set(body.keys()) == {"id", "title", "mode", "phase", "updatedAt"}
    assert body["title"] == "雾港回声"
    assert body["mode"] == "guided"
    assert body["phase"] == "explore"  # 新建初始 phase（AC1）
    assert body["updatedAt"].endswith("Z")  # UTCDateTime 带 Z 后缀（AR5）

    # 真实落库：再查列表能读到（不再是原型仅跳转不持久化）。
    listed = _client.get("/api/projects", headers=auth_headers(user)).json()
    assert len(listed) == 1
    assert listed[0]["id"] == body["id"]


@requires_db
def test_create_project_free_mode(
    make_user: Callable[..., User], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    user = make_user("freemode@example.com")
    resp = _client.post("/api/projects", json={"mode": "free"}, headers=auth_headers(user))
    assert resp.status_code == 201
    assert resp.json()["mode"] == "free"


@requires_db
@pytest.mark.parametrize("payload", [{"mode": "guided"}, {"mode": "guided", "title": "   "}])
def test_create_project_untitled_fallback(
    payload: dict[str, str],
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # 标题留空/纯空白回落「未命名小说」（原型 app.js:1745-1746），且这是合法提交非 422。
    user = make_user(f"untitled-{payload.get('title', 'none')}@example.com")
    resp = _client.post("/api/projects", json=payload, headers=auth_headers(user))
    assert resp.status_code == 201
    assert resp.json()["title"] == "未命名小说"


# ---------- DB 端到端：AC2 列表按 updated_at 倒序 ----------


@requires_db
def test_list_projects_ordered_by_updated_desc(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
    db_engine: Engine,
) -> None:
    user = make_user("order@example.com")
    headers = auth_headers(user)
    # 建三部后，显式把 updated_at 设成确定递增时间——不靠 sleep 制造时间差（脆弱且慢）。
    titles = ["第一部", "第二部", "第三部"]
    ids = [
        _client.post(
            "/api/projects", json={"mode": "guided", "title": t}, headers=headers
        ).json()["id"]
        for t in titles
    ]
    base = datetime(2026, 1, 1, tzinfo=UTC)
    with db_engine.begin() as conn:
        for i, pid in enumerate(ids):
            conn.execute(
                text("UPDATE project SET updated_at = :ts WHERE id = :id"),
                {"ts": base + timedelta(minutes=i), "id": pid},
            )

    listed = _client.get("/api/projects", headers=headers).json()
    assert [p["title"] for p in listed] == list(reversed(titles))


# ---------- DB 端到端：AC2 租户隔离（NFR3）----------


@requires_db
def test_list_projects_tenant_isolation(
    make_user: Callable[..., User], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    # A 建作品，B 查询只应看到自己的（空），杜绝跨租户越权读取。
    alice = make_user("owner-a@example.com")
    bob = make_user("owner-b@example.com")
    _client.post(
        "/api/projects", json={"mode": "guided", "title": "A 的小说"}, headers=auth_headers(alice)
    )

    bob_list = _client.get("/api/projects", headers=auth_headers(bob)).json()
    assert bob_list == []

    alice_list = _client.get("/api/projects", headers=auth_headers(alice)).json()
    assert len(alice_list) == 1
    assert alice_list[0]["title"] == "A 的小说"


# ---------- DB 端到端：AC3 空态 = 真实空列表 ----------


@requires_db
def test_list_projects_empty_returns_empty_array(
    make_user: Callable[..., User], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    # 一部作品都没有 → 返回 []（后端零特判，空态由前端渲染 empty-library）。
    user = make_user("empty@example.com")
    resp = _client.get("/api/projects", headers=auth_headers(user))
    assert resp.status_code == 200
    assert resp.json() == []


# ========== Story 1.5：作品重命名与删除 ==========

# ---------- 离线：鉴权前置（无 token 不需 DB） ----------


def test_rename_project_without_token_401() -> None:
    # 未登录改名 → 401 token_invalid（CurrentUser 依赖先于业务挡下，鉴权前置）。
    resp = _client.patch(f"/api/projects/{uuid.uuid4()}", json={"title": "新名"})
    assert resp.status_code == 401
    body = resp.json()
    assert set(body.keys()) == {"code", "message", "detail"}
    assert body["code"] == "token_invalid"


def test_delete_project_without_token_401() -> None:
    resp = _client.delete(f"/api/projects/{uuid.uuid4()}")
    assert resp.status_code == 401
    assert resp.json()["code"] == "token_invalid"


# ---------- DB 端到端：AC1 改名真实持久化 + updatedAt 刷新 ----------


@requires_db
def test_rename_project_persists_and_refreshes_updated_at(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
    db_engine: Engine,
) -> None:
    user = make_user("rename@example.com")
    headers = auth_headers(user)
    created = _client.post(
        "/api/projects", json={"mode": "guided", "title": "旧名"}, headers=headers
    ).json()
    # 把 updated_at 显式回拨到确定的早时间——不靠 sleep 赌两次请求落在不同时钟刻度。
    # 改名后新时间戳必然远大于此，确定性地验证「刷新确实发生」（陷阱②：漏 refresh 则时间不变）。
    old_ts = datetime(2020, 1, 1, tzinfo=UTC)
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE project SET updated_at = :ts WHERE id = :id"),
            {"ts": old_ts, "id": created["id"]},
        )

    resp = _client.patch(
        f"/api/projects/{created['id']}", json={"title": "新名"}, headers=headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"id", "title", "mode", "phase", "updatedAt"}
    assert body["id"] == created["id"]
    assert body["title"] == "新名"
    # 陷阱②：commit 后须 session.refresh 拉回 DB 计算的 updated_at，否则仍是旧值。
    # 断言新时间戳严格晚于回拨的早时间——漏 refresh 则响应仍是 2020 旧值，此断言翻红。
    assert datetime.fromisoformat(body["updatedAt"]) > old_ts

    # 真实持久化：再查列表读到的是新名（非原型仅改 DOM）。
    listed = _client.get("/api/projects", headers=headers).json()
    assert listed[0]["title"] == "新名"


@requires_db
@pytest.mark.parametrize("new_title", [None, "", "   "])
def test_rename_project_untitled_fallback(
    new_title: str | None,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # 改名留空/纯空白/缺省 → 回落「未命名小说」（复用 _normalize_title，AC1；陷阱③非 422）。
    user = make_user(f"rename-untitled-{new_title!r}@example.com")
    headers = auth_headers(user)
    created = _client.post(
        "/api/projects", json={"mode": "guided", "title": "有名字"}, headers=headers
    ).json()
    payload = {} if new_title is None else {"title": new_title}
    resp = _client.patch(f"/api/projects/{created['id']}", json=payload, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["title"] == "未命名小说"


# ---------- DB 端到端：AC2 删除真实生效 ----------


@requires_db
def test_delete_project_removes_from_list(
    make_user: Callable[..., User], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    user = make_user("delete@example.com")
    headers = auth_headers(user)
    created = _client.post(
        "/api/projects", json={"mode": "guided", "title": "待删除"}, headers=headers
    ).json()

    resp = _client.delete(f"/api/projects/{created['id']}", headers=headers)
    assert resp.status_code == 204
    assert resp.content == b""  # 204 No Content 无响应体（陷阱⑤）

    # 真实删除（非原型 row.remove() 刷新即恢复）：列表已移除该行。
    listed = _client.get("/api/projects", headers=headers).json()
    assert listed == []


# ---------- DB 端到端：AC4 租户隔离 + 不泄露存在性（越权=不存在=同 404，陷阱①）----------


@requires_db
def test_rename_others_project_returns_404_and_leaves_untouched(
    make_user: Callable[..., User], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    # A 建作品，B 改 A 的 → 404 project_not_found（与"不存在"同码，不泄露存在性，不返回 403）。
    alice = make_user("rename-owner-a@example.com")
    bob = make_user("rename-owner-b@example.com")
    created = _client.post(
        "/api/projects", json={"mode": "guided", "title": "A的作品"}, headers=auth_headers(alice)
    ).json()

    resp = _client.patch(
        f"/api/projects/{created['id']}", json={"title": "B篡改"}, headers=auth_headers(bob)
    )
    assert resp.status_code == 404
    body = resp.json()
    assert set(body.keys()) == {"code", "message", "detail"}  # AR5 envelope 三要素
    assert body["code"] == "project_not_found"

    # 越权未生效：A 的作品名分毫未动。
    alice_list = _client.get("/api/projects", headers=auth_headers(alice)).json()
    assert alice_list[0]["title"] == "A的作品"


@requires_db
def test_delete_others_project_returns_404_and_leaves_untouched(
    make_user: Callable[..., User], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    alice = make_user("delete-owner-a@example.com")
    bob = make_user("delete-owner-b@example.com")
    created = _client.post(
        "/api/projects", json={"mode": "guided", "title": "A的作品"}, headers=auth_headers(alice)
    ).json()

    resp = _client.delete(f"/api/projects/{created['id']}", headers=auth_headers(bob))
    assert resp.status_code == 404
    body = resp.json()
    assert set(body.keys()) == {"code", "message", "detail"}  # AR5 envelope 三要素
    assert body["code"] == "project_not_found"

    # 越权未生效：A 的作品仍在。
    alice_list = _client.get("/api/projects", headers=auth_headers(alice)).json()
    assert len(alice_list) == 1
    assert alice_list[0]["id"] == created["id"]


@requires_db
def test_rename_nonexistent_project_returns_404(
    make_user: Callable[..., User], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    # 随机 UUID（压根不存在）→ 与"越权"完全相同的 404 project_not_found（验证不泄露存在性）。
    user = make_user("rename-404@example.com")
    resp = _client.patch(
        f"/api/projects/{uuid.uuid4()}", json={"title": "x"}, headers=auth_headers(user)
    )
    assert resp.status_code == 404
    body = resp.json()
    assert set(body.keys()) == {"code", "message", "detail"}  # AR5 envelope 三要素
    assert body["code"] == "project_not_found"


@requires_db
def test_delete_nonexistent_project_returns_404(
    make_user: Callable[..., User], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    user = make_user("delete-404@example.com")
    resp = _client.delete(f"/api/projects/{uuid.uuid4()}", headers=auth_headers(user))
    assert resp.status_code == 404
    body = resp.json()
    assert set(body.keys()) == {"code", "message", "detail"}  # AR5 envelope 三要素
    assert body["code"] == "project_not_found"


# ---------- DB 端到端：非法路径参数 UUID 解析 ----------


@requires_db
def test_rename_project_invalid_uuid_422(
    make_user: Callable[..., User], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    # 非法 UUID 路径参数 → 422（FastAPI 类型解析）。需真实身份：本库鉴权先于参数校验
    # （同 test_create_project_invalid_mode_422），故走 DB 门禁而非离线。
    user = make_user("bad-uuid@example.com")
    resp = _client.patch(
        "/api/projects/not-a-uuid", json={"title": "x"}, headers=auth_headers(user)
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


@requires_db
def test_delete_project_invalid_uuid_422(
    make_user: Callable[..., User], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    # 非法 UUID 路径参数 → 422（FastAPI 类型解析）；与 PATCH 版对齐，守护 DELETE 路由的
    # project_id: uuid.UUID 解析。需真实身份：本库鉴权先于参数校验，故走 DB 门禁。
    user = make_user("bad-uuid-del@example.com")
    resp = _client.delete("/api/projects/not-a-uuid", headers=auth_headers(user))
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"
