"""Story 2.4 验证：引导答案真实持久化后端（存/取 API 全 AC 覆盖）。

- 离线用例：鉴权缺失 401、过期 token 401（不需 DB）。
- DB 用例（requires_db）：走完整 HTTP 栈 + 真实 DB——首次保存落库 + camelCase、重选覆盖
  同题位（UNIQUE + upsert + updated_at 刷新）、不同题位并存、恢复按题位升序、GET 空态 []、
  custom 路径往返、租户隔离 404、project 不存在 404、非法 UUID 422、入参校验 422。

本 story 无 LLM / 无流式 / 无 Redis（纯 CRUD，陷阱⑨）——不需 requires_redis/requires_deepseek。
"""

import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

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
    临时循环，同一用例内发两次请求（如连 POST 两次验重选覆盖）时第二次会撞残留连接 →
    Event loop is closed。用 `with _client` 固定单一循环即解（与 test_exploration 同源治理）。
    """
    with _client:
        yield


def _create_project(user: User, headers: dict[str, str], mode: str = "guided") -> str:
    """建一部作品并返回其 id（探索答案挂在 project 下，用例前置）。"""
    resp = _client.post("/api/projects", json={"mode": mode}, headers=headers)
    assert resp.status_code == 201
    return resp.json()["id"]


def _answers_url(project_id: str) -> str:
    return f"/api/projects/{project_id}/explore/guided/answers"


# ---------- 离线：鉴权前置（无 token / 过期 token 不需 DB） ----------


def test_save_answer_without_token_401() -> None:
    # 未登录保存答案 → 401 token_invalid（CurrentUser 依赖在鉴权入口挡下）。
    resp = _client.post(
        _answers_url(str(uuid.uuid4())),
        json={"questionIndex": 0, "question": "q", "answer": "a", "answerType": "option"},
    )
    assert resp.status_code == 401
    body = resp.json()
    assert set(body.keys()) == {"code", "message", "detail"}
    assert body["code"] == "token_invalid"


def test_list_answers_without_token_401() -> None:
    # 未登录恢复答案 → 401 token_invalid。
    resp = _client.get(_answers_url(str(uuid.uuid4())))
    assert resp.status_code == 401
    assert resp.json()["code"] == "token_invalid"


def test_save_answer_expired_token_401() -> None:
    # 过期 access → 401 token_expired（对接原型 #/login?state=expired）。
    settings = get_settings()
    now = int(time.time())
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "type": "access", "iat": now - 100, "exp": now - 10},
        settings.jwt_secret,
        algorithm="HS256",
    )
    resp = _client.post(
        _answers_url(str(uuid.uuid4())),
        json={"questionIndex": 0, "question": "q", "answer": "a", "answerType": "option"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "token_expired"


# ---------- DB 端到端：AC5 首次保存真实落库 + camelCase 边界 ----------


@requires_db
def test_save_answer_persists_and_returns_camel(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
    db_engine: Engine,
) -> None:
    user = make_user("answer-save@example.com")
    headers = auth_headers(user)
    project_id = _create_project(user, headers, mode="guided")

    resp = _client.post(
        _answers_url(project_id),
        json={
            "questionIndex": 0,
            "question": "你更爱看什么类型的故事？",
            "answer": "偏爱悬疑推理",
            "answerType": "option",
        },
        headers=headers,
    )
    assert resp.status_code == 200  # 幂等 upsert 返 200，非恒新建的 201（陷阱⑦）
    body = resp.json()
    # camelCase 边界（AR4）：id/questionIndex/question/answer/answerType/updatedAt。
    assert set(body.keys()) == {
        "id",
        "questionIndex",
        "question",
        "answer",
        "answerType",
        "updatedAt",
    }
    assert body["questionIndex"] == 0
    assert body["answer"] == "偏爱悬疑推理"
    assert body["answerType"] == "option"
    assert body["updatedAt"].endswith("Z")  # UTCDateTime 带 Z 后缀（AR5）

    # 真实落库：DB 恰有一条属该 project 的答案。
    with db_engine.begin() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM exploration_message WHERE project_id = :pid"),
            {"pid": project_id},
        ).scalar_one()
    assert count == 1


# ---------- DB 端到端：AC4/AC5 重选覆盖同题位（UNIQUE + upsert + updated_at 刷新） ----------


@requires_db
def test_resubmit_same_index_overwrites_and_refreshes_updated_at(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
    db_engine: Engine,
) -> None:
    """重选同题位：DB 仍 1 条、answer 为第二次值、updated_at 刷新、created_at 不变（陷阱②③）。

    时间戳断言用确定性手段（陷阱⑫，不用 sleep）：首答后把 created_at/updated_at 显式回拨到
    确定的早时间（2020），改答后新 updated_at 必然远晚于此，确定性验证「刷新确实发生」——
    若漏写 upsert set_ 里的 updated_at=func.now()（陷阱②），DO UPDATE 不动 updated_at，它会
    停在回拨值 2020，断言翻红。created_at 未被 set_ 覆盖（陷阱③），仍是回拨值。
    """
    user = make_user("answer-overwrite@example.com")
    headers = auth_headers(user)
    project_id = _create_project(user, headers, mode="guided")

    first = _client.post(
        _answers_url(project_id),
        json={"questionIndex": 0, "question": "q", "answer": "第一次答案", "answerType": "option"},
        headers=headers,
    )
    assert first.status_code == 200
    first_id = first.json()["id"]

    # 回拨首答时间戳到确定早时间——不靠 sleep 赌两次请求落在不同时钟刻度。
    old_ts = datetime(2020, 1, 1, tzinfo=UTC)
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE exploration_message SET created_at = :ts, updated_at = :ts "
                "WHERE id = :id"
            ),
            {"ts": old_ts, "id": first_id},
        )

    second = _client.post(
        _answers_url(project_id),
        json={"questionIndex": 0, "question": "q", "answer": "第二次答案", "answerType": "custom"},
        headers=headers,
    )
    assert second.status_code == 200
    # 同题位覆盖：主键 id 不变（upsert 命中同一行）、answer/answerType 更新为第二次。
    assert second.json()["id"] == first_id
    assert second.json()["answer"] == "第二次答案"
    assert second.json()["answerType"] == "custom"
    # 陷阱②：改答刷新 updated_at——响应新时间戳严格晚于回拨的 2020（漏刷则仍是 2020，翻红）。
    assert datetime.fromisoformat(second.json()["updatedAt"]) > old_ts

    # DB 仍 1 条（UNIQUE(session_id, question_index) 挡住第二次插入 → 走 DO UPDATE）。
    with db_engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT count(*) OVER () AS n, answer, created_at, updated_at "
                "FROM exploration_message WHERE project_id = :pid AND question_index = 0"
            ),
            {"pid": project_id},
        ).one()
    assert row.n == 1
    assert row.answer == "第二次答案"
    # 陷阱③：created_at 未被 set_ 覆盖，仍是回拨的 2020（保留首答时间）。
    assert row.created_at.replace(tzinfo=UTC) == old_ts
    # 陷阱②：updated_at 已刷新到远晚于 2020。
    assert row.updated_at.replace(tzinfo=UTC) > old_ts


# ---------- DB 端到端：不同题位并存 ----------


@requires_db
def test_different_indices_coexist(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
    db_engine: Engine,
) -> None:
    user = make_user("answer-multi@example.com")
    headers = auth_headers(user)
    project_id = _create_project(user, headers, mode="guided")

    for idx in (0, 1):
        resp = _client.post(
            _answers_url(project_id),
            json={
                "questionIndex": idx,
                "question": f"q{idx}",
                "answer": f"a{idx}",
                "answerType": "option",
            },
            headers=headers,
        )
        assert resp.status_code == 200

    with db_engine.begin() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM exploration_message WHERE project_id = :pid"),
            {"pid": project_id},
        ).scalar_one()
    assert count == 2


# ---------- DB 端到端：AC5 恢复查询按题位升序 ----------


@requires_db
def test_list_answers_returns_sorted_by_index(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # 乱序 POST（2→0→1）→ GET 返回按 questionIndex 升序 [0,1,2]，各字段 camelCase。
    user = make_user("answer-sorted@example.com")
    headers = auth_headers(user)
    project_id = _create_project(user, headers, mode="guided")

    for idx in (2, 0, 1):
        _client.post(
            _answers_url(project_id),
            json={
                "questionIndex": idx,
                "question": f"q{idx}",
                "answer": f"a{idx}",
                "answerType": "option",
            },
            headers=headers,
        )

    resp = _client.get(_answers_url(project_id), headers=headers)
    assert resp.status_code == 200
    items = resp.json()
    assert [item["questionIndex"] for item in items] == [0, 1, 2]
    # camelCase + 各字段随题位对应。
    for item in items:
        assert set(item.keys()) == {
            "id",
            "questionIndex",
            "question",
            "answer",
            "answerType",
            "updatedAt",
        }
        assert item["answer"] == f"a{item['questionIndex']}"


# ---------- DB 端到端：GET 空态 [] （非 404，陷阱⑥/⑨） ----------


@requires_db
def test_list_answers_empty_returns_empty_list(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # 新建 project 未答（甚至没进探索）→ GET 返 [] （200，自然空态，非 404）。
    user = make_user("answer-empty@example.com")
    headers = auth_headers(user)
    project_id = _create_project(user, headers, mode="guided")

    resp = _client.get(_answers_url(project_id), headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


# ---------- DB 端到端：answer_type=custom 自述路径往返 ----------


@requires_db
def test_custom_answer_type_roundtrip(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # 自述作答（custom）保存 + 恢复往返，answer_type 与 answer 原样。
    user = make_user("answer-custom@example.com")
    headers = auth_headers(user)
    project_id = _create_project(user, headers, mode="guided")

    _client.post(
        _answers_url(project_id),
        json={
            "questionIndex": 3,
            "question": "主角是什么样的人？",
            "answer": "一个背负秘密的退伍军人",
            "answerType": "custom",
        },
        headers=headers,
    )
    resp = _client.get(_answers_url(project_id), headers=headers)
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["answerType"] == "custom"
    assert items[0]["answer"] == "一个背负秘密的退伍军人"


# ---------- DB 端到端：租户隔离（他人 project 404，越权=不存在，陷阱①） ----------


@requires_db
def test_save_answer_others_project_returns_404(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
    db_engine: Engine,
) -> None:
    # B 对 A 的 project 保存答案 → 404 project_not_found（与"不存在"同码，不泄露存在性，不 403）。
    alice = make_user("answer-owner-a@example.com")
    bob = make_user("answer-owner-b@example.com")
    project_id = _create_project(alice, auth_headers(alice), mode="guided")

    resp = _client.post(
        _answers_url(project_id),
        json={"questionIndex": 0, "question": "q", "answer": "a", "answerType": "option"},
        headers=auth_headers(bob),
    )
    assert resp.status_code == 404
    body = resp.json()
    assert set(body.keys()) == {"code", "message", "detail"}  # AR5 envelope 三要素
    assert body["code"] == "project_not_found"

    # 越权未生效：A 的 project 没有被 B 写入答案。
    with db_engine.begin() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM exploration_message WHERE project_id = :pid"),
            {"pid": project_id},
        ).scalar_one()
    assert count == 0


@requires_db
def test_list_answers_others_project_returns_404(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # B 对 A 的 project 恢复答案 → 404 project_not_found（读端点同样租户守卫）。
    alice = make_user("answer-list-a@example.com")
    bob = make_user("answer-list-b@example.com")
    project_id = _create_project(alice, auth_headers(alice), mode="guided")

    resp = _client.get(_answers_url(project_id), headers=auth_headers(bob))
    assert resp.status_code == 404
    assert resp.json()["code"] == "project_not_found"


# ---------- DB 端到端：project 不存在 404（不泄露存在性） ----------


@requires_db
def test_answers_nonexistent_project_returns_404(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("answer-404@example.com")
    headers = auth_headers(user)
    random_id = str(uuid.uuid4())

    save = _client.post(
        _answers_url(random_id),
        json={"questionIndex": 0, "question": "q", "answer": "a", "answerType": "option"},
        headers=headers,
    )
    assert save.status_code == 404
    assert save.json()["code"] == "project_not_found"

    get = _client.get(_answers_url(random_id), headers=headers)
    assert get.status_code == 404
    assert get.json()["code"] == "project_not_found"


# ---------- DB 端到端：非法路径参数 UUID 解析 422 ----------


@requires_db
def test_answers_invalid_uuid_422(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # 非法 UUID 路径参数 → 422（FastAPI 类型解析）。需真实身份：本库鉴权先于参数校验。
    user = make_user("answer-bad-uuid@example.com")
    headers = auth_headers(user)
    resp = _client.post(
        "/api/projects/not-a-uuid/explore/guided/answers",
        json={"questionIndex": 0, "question": "q", "answer": "a", "answerType": "option"},
        headers=headers,
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


# ---------- DB 端到端：入参校验 422（陷阱⑧） ----------


@requires_db
@pytest.mark.parametrize(
    "payload",
    [
        {"questionIndex": 0, "question": "q", "answer": "a", "answerType": "invalid"},  # 非法枚举
        {"questionIndex": -1, "question": "q", "answer": "a", "answerType": "option"},  # 负 index
        {"questionIndex": 0, "question": "q", "answer": "   ", "answerType": "option"},  # 纯空白
        {"questionIndex": 0, "question": "q", "answer": "x" * 2001, "answerType": "option"},  # 超长
        {"questionIndex": 2**31, "question": "q", "answer": "a", "answerType": "option"},  # 超int4
    ],
)
def test_save_answer_validation_422(
    payload: dict[str, object],
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # answerType 非法枚举 / questionIndex 负 / answer 纯空白 / answer 超长（2001）/ questionIndex
    # 超 int4 上界（2**31）→ 422。末条锁定 review patch：questionIndex 是 PG int4，超上界值若不在
    # 入参层（Field lt=2**31）拦下，会在 INSERT 抛 DataError → 无专用 handler → 通用 500；加界后
    # 统一收敛成 422 validation_error，脏 index 挡在 DB 之前。
    user = make_user("answer-validation@example.com")
    headers = auth_headers(user)
    project_id = _create_project(user, headers, mode="guided")

    resp = _client.post(_answers_url(project_id), json=payload, headers=headers)
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"
