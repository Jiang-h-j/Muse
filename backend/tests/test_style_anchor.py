"""Story 3.2 验证：文风锚点入口 + style_profile 真实抽取（AC 全覆盖）。

- schema 单元（离线）：sampleId/sampleText 互斥、都给/都不给/太短/超长 → 422；sampleId 空白归一化。
- 编排单元（离线，mock get_provider_for_user + check_quota，不打真实 API，CI 必过）：
  - extract_and_anchor_style happy：解析五维 → upsert（mock repo）→ 返回落库行。
  - check_quota 触顶（429）→ provider 未被构造/调用（护栏在抽取前，陷阱②）。
  - 租户守卫（get_owned_project 返 None）→ 404，provider/护栏均未触及。
  - upsert 撞唯一约束（IntegrityError）→ rollback → 重查转 UPDATE 兜底（竞态幂等，非 500）。
  - 空产兜底：provider 返回无有效维度 → 抛 generate_failed，不落库。
  - prompt 契约最小断言：messages 含 system prompt（五维标签）+ user 消息携样本原文。
  - _parse_style_profile 防御性解析：偏离格式行忽略、按五维固定顺序拼回。
  - resolve_sample_text：库选取预置原文、未知 id 抛 400、粘贴原样返回。
- repo 单元（@requires_db）：upsert 首次建行（主干空串/特化 NULL/style_profile 有值）、
  二次 upsert 更新同行不撞唯一约束、get_by_project 租户隔离。
- API 端到端（@requires_db，provider mock）：鉴权 401 / GET samples / happy 抽取 /
  422 校验 / 护栏 429 / 租户 404 / 未知 sampleId 400。
"""

import time
import uuid
from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from muse.core.errors import ErrorEnvelope
from muse.core.settings import get_settings
from muse.main import app
from muse.models.account import User
from muse.models.project import Project
from muse.models.story_bible import StoryBible
from muse.providers.base import ChatResult
from muse.repositories import story_bible_repo
from muse.schemas.story import StyleAnchorRequest
from muse.services import style_anchor_agent
from tests.conftest import requires_db

_client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True, scope="module")
def _client_lifespan() -> "object":
    """上下文管理器模式跑 TestClient：所有请求共享同一持久事件循环（与 test_exploration 同源）。"""
    with _client:
        yield


def _project(mode: str = "guided") -> MagicMock:
    """假 project 对象：文风锚点不做 mode 守卫，仅需一个非 None 对象表「作品存在且属我」。"""
    p = MagicMock()
    p.mode = mode
    return p


def _fake_chat_result(content: str) -> ChatResult:
    return ChatResult(
        content=content,
        prompt_tokens=10,
        completion_tokens=10,
        total_tokens=20,
        model="deepseek-v4-flash",
    )


# 一段模型「理想」输出：五维各一行「标签：内容」。
_GOOD_LLM_OUTPUT = (
    "人称：第三人称限知\n"
    "语气：冷峻、克制\n"
    "句式节奏：短句为主，偶有停顿\n"
    "意象密度：高（雨、旧城、光影）\n"
    "段落长度倾向：偏短，一段一景"
)


# ========== 离线：schema 校验 ==========


def test_schema_sample_id_only_ok() -> None:
    r = StyleAnchorRequest(sampleId="cold-rain")
    assert r.sample_id == "cold-rain"
    assert r.sample_text is None


def test_schema_sample_text_only_ok() -> None:
    r = StyleAnchorRequest(sampleText="这是一段足够长的用于测试文风抽取的范文内容示例文字。")
    assert r.sample_id is None
    assert r.sample_text is not None


def test_schema_both_provided_rejected() -> None:
    with pytest.raises(ValueError):
        StyleAnchorRequest(
            sampleId="cold-rain",
            sampleText="这是一段足够长的用于测试文风抽取的范文内容示例文字。",
        )


def test_schema_neither_provided_rejected() -> None:
    with pytest.raises(ValueError):
        StyleAnchorRequest()


def test_schema_sample_text_too_short_rejected() -> None:
    # < 20 字（原型 paste 门槛）→ 422。
    with pytest.raises(ValueError):
        StyleAnchorRequest(sampleText="太短了")


def test_schema_sample_text_too_long_rejected() -> None:
    # > 4000 字上界 → 422（拦超长样本挤爆 prompt）。
    with pytest.raises(ValueError):
        StyleAnchorRequest(sampleText="字" * 4001)


def test_schema_sample_id_whitespace_stripped() -> None:
    # 带首尾空白的合法 id → 归一化去空白（否则 resolve 查库误命中不了、误 400）。
    r = StyleAnchorRequest(sampleId="  cold-rain  ")
    assert r.sample_id == "cold-rain"


def test_schema_blank_sample_id_treated_as_absent() -> None:
    # 空白 sampleId 视为未提供：与 sampleText 恰一即通过。
    r = StyleAnchorRequest(
        sampleId="   ",
        sampleText="这是一段足够长的用于测试文风抽取的范文内容示例文字。",
    )
    assert r.sample_id is None


# ========== 离线：_parse_style_profile / resolve_sample_text ==========


def test_parse_style_profile_happy() -> None:
    out = style_anchor_agent._parse_style_profile(_GOOD_LLM_OUTPUT)
    lines = out.split("\n")
    assert len(lines) == 5
    assert lines[0] == "人称：第三人称限知"
    assert lines[4].startswith("段落长度倾向：")


def test_parse_style_profile_ignores_garbage_and_keeps_order() -> None:
    # 偏离格式行（无分隔符/未知标签/空值）被忽略；已解析维度按五维固定顺序拼回。
    messy = (
        "好的以下是分析\n"  # 无「：」分隔的旁白，被忽略
        "段落长度倾向：偏短\n"  # 顺序打乱
        "人称：第一人称\n"
        "未知维度：应被忽略\n"
        "语气：\n"  # 空值忽略
    )
    out = style_anchor_agent._parse_style_profile(messy)
    lines = out.split("\n")
    # 人称应排在段落长度倾向之前（固定顺序）；空值的语气与未知维度不出现。
    assert lines[0] == "人称：第一人称"
    assert any(line.startswith("段落长度倾向：") for line in lines)
    assert all("未知维度" not in line for line in lines)
    assert all(not line.startswith("语气：") for line in lines)


def test_parse_style_profile_empty_when_no_valid_dimension() -> None:
    assert style_anchor_agent._parse_style_profile("完全不符合格式的一段话") == ""


def test_resolve_sample_text_library_returns_full_text() -> None:
    text = style_anchor_agent.resolve_sample_text(sample_id="cold-rain", sample_text=None)
    # 返回较完整原文（长于原型 excerpt 短摘）。
    assert "雨是在凌晨落下来的" in text
    assert len(text) > 50


def test_resolve_sample_text_paste_returns_as_is() -> None:
    pasted = "我自己粘贴的一段范文，长度足够用于抽取测试。"
    assert style_anchor_agent.resolve_sample_text(sample_id=None, sample_text=pasted) == pasted


def test_resolve_sample_text_unknown_id_400() -> None:
    with pytest.raises(ErrorEnvelope) as exc:
        style_anchor_agent.resolve_sample_text(sample_id="not-exist", sample_text=None)
    assert exc.value.code == "unknown_style_sample"
    assert exc.value.http_status == 400


# ========== 离线：extract_and_anchor_style 编排单元 ==========


class _FakeSessionCtx:
    """可 async with 的哑 session（repo/provider 均已 mock，session 本身不被真正使用）。"""

    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> "object":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


def _fake_session_maker() -> Callable[[], object]:
    return lambda: _FakeSessionCtx()


async def test_extract_happy_parses_and_upserts() -> None:
    uid, pid = uuid.uuid4(), uuid.uuid4()
    fake_provider = AsyncMock()
    fake_provider.chat = AsyncMock(return_value=_fake_chat_result(_GOOD_LLM_OUTPUT))
    fake_bible = MagicMock()
    fake_bible.style_profile = _GOOD_LLM_OUTPUT
    with (
        patch.object(
            style_anchor_agent.project_repo,
            "get_owned_project",
            new=AsyncMock(return_value=_project()),
        ),
        patch.object(style_anchor_agent.usage_service, "check_quota", new=AsyncMock()),
        patch.object(
            style_anchor_agent,
            "get_provider_for_user",
            new=AsyncMock(return_value=fake_provider),
        ),
        patch.object(
            style_anchor_agent.story_bible_repo,
            "upsert_style_profile",
            new=AsyncMock(return_value=fake_bible),
        ) as upsert,
        patch.object(style_anchor_agent, "async_session_maker", _fake_session_maker()),
    ):
        bible = await style_anchor_agent.extract_and_anchor_style(
            user_id=uid, project_id=pid, sample_text="一段足够长的范文示例内容用于抽取测试。"
        )
    assert bible is fake_bible
    # upsert 收到解析后的五维文本。
    _, kwargs = upsert.call_args
    assert "人称：第三人称限知" in kwargs["style_profile"]
    assert kwargs["user_id"] == uid
    assert kwargs["project_id"] == pid


async def test_extract_quota_exceeded_blocks_before_provider() -> None:
    uid, pid = uuid.uuid4(), uuid.uuid4()
    quota_err = ErrorEnvelope(code="quota_exceeded", message="额度已用完", http_status=429)
    with (
        patch.object(
            style_anchor_agent.project_repo,
            "get_owned_project",
            new=AsyncMock(return_value=_project()),
        ),
        patch.object(
            style_anchor_agent.usage_service,
            "check_quota",
            new=AsyncMock(side_effect=quota_err),
        ),
        patch.object(
            style_anchor_agent, "get_provider_for_user", new=AsyncMock()
        ) as get_provider,
        patch.object(style_anchor_agent, "async_session_maker", _fake_session_maker()),
        pytest.raises(ErrorEnvelope) as exc,
    ):
        await style_anchor_agent.extract_and_anchor_style(
            user_id=uid, project_id=pid, sample_text="一段足够长的范文示例内容用于抽取测试。"
        )
    assert exc.value.code == "quota_exceeded"
    get_provider.assert_not_awaited()  # 护栏在前：provider 根本没被构造


async def test_extract_tenant_guard_404_before_quota_and_provider() -> None:
    uid, pid = uuid.uuid4(), uuid.uuid4()
    with (
        patch.object(
            style_anchor_agent.project_repo,
            "get_owned_project",
            new=AsyncMock(return_value=None),
        ),
        patch.object(
            style_anchor_agent.usage_service, "check_quota", new=AsyncMock()
        ) as check_quota,
        patch.object(
            style_anchor_agent, "get_provider_for_user", new=AsyncMock()
        ) as get_provider,
        patch.object(style_anchor_agent, "async_session_maker", _fake_session_maker()),
        pytest.raises(ErrorEnvelope) as exc,
    ):
        await style_anchor_agent.extract_and_anchor_style(
            user_id=uid, project_id=pid, sample_text="一段足够长的范文示例内容用于抽取测试。"
        )
    assert exc.value.code == "project_not_found"
    assert exc.value.http_status == 404
    check_quota.assert_not_awaited()
    get_provider.assert_not_awaited()


async def test_extract_empty_output_raises_and_does_not_upsert() -> None:
    # 模型没吐任何有效维度 → 抛 generate_failed、不 upsert（不落空 style_profile）。
    uid, pid = uuid.uuid4(), uuid.uuid4()
    fake_provider = AsyncMock()
    fake_provider.chat = AsyncMock(return_value=_fake_chat_result("完全跑题的一段废话"))
    with (
        patch.object(
            style_anchor_agent.project_repo,
            "get_owned_project",
            new=AsyncMock(return_value=_project()),
        ),
        patch.object(style_anchor_agent.usage_service, "check_quota", new=AsyncMock()),
        patch.object(
            style_anchor_agent,
            "get_provider_for_user",
            new=AsyncMock(return_value=fake_provider),
        ),
        patch.object(
            style_anchor_agent.story_bible_repo, "upsert_style_profile", new=AsyncMock()
        ) as upsert,
        patch.object(style_anchor_agent, "async_session_maker", _fake_session_maker()),
        pytest.raises(ErrorEnvelope) as exc,
    ):
        await style_anchor_agent.extract_and_anchor_style(
            user_id=uid, project_id=pid, sample_text="一段足够长的范文示例内容用于抽取测试。"
        )
    assert exc.value.code == "generate_failed"
    upsert.assert_not_awaited()


async def test_extract_upsert_race_recovers_to_update() -> None:
    # 竞态兜底：首次并发插入撞唯一约束（upsert 抛 IntegrityError）→ service rollback →
    # 重查 get_by_project 拿到先到者已建的行 → 改走 UPDATE → commit，兑现幂等而非 500。
    from sqlalchemy.exc import IntegrityError

    uid, pid = uuid.uuid4(), uuid.uuid4()
    fake_provider = AsyncMock()
    fake_provider.chat = AsyncMock(return_value=_fake_chat_result(_GOOD_LLM_OUTPUT))
    # 先到者已落库的行（重查返回它），style_profile 待被本请求覆盖。
    winner_row = MagicMock()
    winner_row.style_profile = "先到者的旧文风"
    session_holder: dict[str, _FakeSessionCtx] = {}

    def _capturing_maker() -> Callable[[], object]:
        def _make() -> _FakeSessionCtx:
            ctx = _FakeSessionCtx()
            session_holder["ctx"] = ctx
            return ctx

        return _make

    with (
        patch.object(
            style_anchor_agent.project_repo,
            "get_owned_project",
            new=AsyncMock(return_value=_project()),
        ),
        patch.object(style_anchor_agent.usage_service, "check_quota", new=AsyncMock()),
        patch.object(
            style_anchor_agent,
            "get_provider_for_user",
            new=AsyncMock(return_value=fake_provider),
        ),
        patch.object(
            style_anchor_agent.story_bible_repo,
            "upsert_style_profile",
            new=AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("uq"))),
        ),
        patch.object(
            style_anchor_agent.story_bible_repo,
            "get_by_project",
            new=AsyncMock(return_value=winner_row),
        ) as get_by_project,
        patch.object(style_anchor_agent, "async_session_maker", _capturing_maker()),
    ):
        bible = await style_anchor_agent.extract_and_anchor_style(
            user_id=uid, project_id=pid, sample_text="一段足够长的范文示例内容用于抽取测试。"
        )
    # 兜底路径：rollback 发生、重查命中先到者行、其 style_profile 被本请求覆盖为新抽取值。
    assert session_holder["ctx"].rolled_back is True
    get_by_project.assert_awaited()
    assert bible is winner_row
    assert "人称：第三人称限知" in winner_row.style_profile


async def test_extract_builds_messages_with_system_prompt_and_sample() -> None:
    uid, pid = uuid.uuid4(), uuid.uuid4()
    captured: dict[str, object] = {}

    async def _capturing_chat(messages: list[dict[str, str]], **kwargs: object):
        captured["messages"] = messages
        captured["kwargs"] = kwargs
        return _fake_chat_result(_GOOD_LLM_OUTPUT)

    fake_provider = MagicMock()
    fake_provider.chat = _capturing_chat
    with (
        patch.object(
            style_anchor_agent.project_repo,
            "get_owned_project",
            new=AsyncMock(return_value=_project()),
        ),
        patch.object(style_anchor_agent.usage_service, "check_quota", new=AsyncMock()),
        patch.object(
            style_anchor_agent,
            "get_provider_for_user",
            new=AsyncMock(return_value=fake_provider),
        ),
        patch.object(
            style_anchor_agent.story_bible_repo,
            "upsert_style_profile",
            new=AsyncMock(return_value=MagicMock()),
        ),
        patch.object(style_anchor_agent, "async_session_maker", _fake_session_maker()),
    ):
        await style_anchor_agent.extract_and_anchor_style(
            user_id=uid, project_id=pid, sample_text="雨夜里的一段范文，用于文风抽取测试。"
        )
    messages = captured["messages"]
    assert messages[0]["role"] == "system"
    # system prompt 保留五维标签（防未来误删）。
    assert "人称" in messages[0]["content"]
    assert "意象密度" in messages[0]["content"]
    assert messages[1]["role"] == "user"
    assert "雨夜里的一段范文" in messages[1]["content"]
    # 快档 + 足量 max_tokens（陷阱⑥）。
    assert captured["kwargs"]["model"] == get_settings().deepseek_model_fast
    assert captured["kwargs"]["max_tokens"] >= 512


# ========== DB：story_bible_repo upsert ==========


def _seed_user_and_project(engine: Engine) -> tuple[uuid.UUID, uuid.UUID]:
    with Session(engine) as session:
        user = User(email=f"sa-{uuid.uuid4()}@test.local", password_hash="x")
        session.add(user)
        session.flush()
        project = Project(user_id=user.id, title="文风测试作品", mode="guided")
        session.add(project)
        session.commit()
        return user.id, project.id


@requires_db
async def test_upsert_creates_row_with_defaults(db_engine: Engine) -> None:
    """首次 upsert 建行：主干 7 列空串、特化 4 列 NULL、style_profile 有值。"""
    from muse.core.db import async_session_maker

    user_id, project_id = _seed_user_and_project(db_engine)
    async with async_session_maker() as session:
        bible = await story_bible_repo.upsert_style_profile(
            session, user_id=user_id, project_id=project_id, style_profile="人称：第一人称"
        )
        await session.commit()
        assert bible.style_profile == "人称：第一人称"

    with Session(db_engine) as s:
        row = s.scalar(select(StoryBible).where(StoryBible.project_id == project_id))
        assert row is not None
        assert row.style_profile == "人称：第一人称"
        assert row.genre == ""  # 主干 server_default 空串
        assert row.power_system is None  # 特化 NULL


@requires_db
async def test_upsert_updates_existing_row_no_unique_violation(db_engine: Engine) -> None:
    """二次 upsert 更新同行、不撞 (user_id, project_id) 唯一约束、不重复建行。"""
    from muse.core.db import async_session_maker

    user_id, project_id = _seed_user_and_project(db_engine)
    async with async_session_maker() as session:
        await story_bible_repo.upsert_style_profile(
            session, user_id=user_id, project_id=project_id, style_profile="旧文风"
        )
        await session.commit()
    async with async_session_maker() as session:
        bible = await story_bible_repo.upsert_style_profile(
            session, user_id=user_id, project_id=project_id, style_profile="新文风"
        )
        await session.commit()
        assert bible.style_profile == "新文风"

    with Session(db_engine) as s:
        rows = list(s.scalars(select(StoryBible).where(StoryBible.project_id == project_id)))
        assert len(rows) == 1  # 仍只有一行
        assert rows[0].style_profile == "新文风"


@requires_db
async def test_upsert_preserves_other_fields(db_engine: Engine) -> None:
    """upsert style_profile 不覆盖其余字段（模拟 3.3 已填卡内容后再锚定文风）。"""
    from muse.core.db import async_session_maker

    user_id, project_id = _seed_user_and_project(db_engine)
    # 先造一行含 genre（模拟 3.3 已写入部分设定）。
    with Session(db_engine) as s:
        s.add(StoryBible(user_id=user_id, project_id=project_id, genre="修仙"))
        s.commit()
    async with async_session_maker() as session:
        await story_bible_repo.upsert_style_profile(
            session, user_id=user_id, project_id=project_id, style_profile="人称：第三人称"
        )
        await session.commit()
    with Session(db_engine) as s:
        row = s.scalar(select(StoryBible).where(StoryBible.project_id == project_id))
        assert row.genre == "修仙"  # 未被覆盖
        assert row.style_profile == "人称：第三人称"


@requires_db
async def test_get_by_project_tenant_isolation(db_engine: Engine) -> None:
    """get_by_project 按 (user_id, project_id) 过滤：他人 user_id 取不到本作品行。"""
    from muse.core.db import async_session_maker

    user_id, project_id = _seed_user_and_project(db_engine)
    other_user_id, _ = _seed_user_and_project(db_engine)
    async with async_session_maker() as session:
        await story_bible_repo.upsert_style_profile(
            session, user_id=user_id, project_id=project_id, style_profile="x"
        )
        await session.commit()
    async with async_session_maker() as session:
        mine = await story_bible_repo.get_by_project(
            session, user_id=user_id, project_id=project_id
        )
        assert mine is not None
        # 他人 user_id + 同 project_id → None（租户隔离）。
        theirs = await story_bible_repo.get_by_project(
            session, user_id=other_user_id, project_id=project_id
        )
        assert theirs is None


# ========== 离线：端点鉴权前置（无需 DB）==========


def _anchor_url(project_id: object) -> str:
    return f"/api/projects/{project_id}/style-anchor"


def _samples_url(project_id: object) -> str:
    return f"/api/projects/{project_id}/style-anchor/samples"


def test_anchor_without_token_401() -> None:
    resp = _client.post(_anchor_url(uuid.uuid4()), json={"sampleId": "cold-rain"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "token_invalid"


def test_samples_without_token_401() -> None:
    resp = _client.get(_samples_url(uuid.uuid4()))
    assert resp.status_code == 401


def test_anchor_expired_token_401() -> None:
    settings = get_settings()
    now = int(time.time())
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "type": "access", "iat": now - 100, "exp": now - 10},
        settings.jwt_secret,
        algorithm="HS256",
    )
    resp = _client.post(
        _anchor_url(uuid.uuid4()),
        json={"sampleId": "cold-rain"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "token_expired"


# ========== DB 端到端：API（provider mock）==========


def _create_project(headers: dict[str, str], mode: str = "guided") -> str:
    resp = _client.post("/api/projects", json={"mode": mode}, headers=headers)
    assert resp.status_code == 201
    return resp.json()["id"]


def _patch_provider(content: str) -> object:
    fake_provider = AsyncMock()
    fake_provider.chat = AsyncMock(return_value=_fake_chat_result(content))
    return patch.object(
        style_anchor_agent,
        "get_provider_for_user",
        new=AsyncMock(return_value=fake_provider),
    )


@requires_db
def test_list_samples_returns_library(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("style-samples@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)
    resp = _client.get(_samples_url(project_id), headers=headers)
    assert resp.status_code == 200
    samples = resp.json()
    assert [s["id"] for s in samples] == ["cold-rain", "warm-dusk", "sharp-first"]
    # camelCase 字段、含展示元信息、不含完整原文。
    assert set(samples[0].keys()) == {"id", "name", "note", "excerpt"}


@requires_db
def test_anchor_happy_library_choice(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("style-lib@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)
    with _patch_provider(_GOOD_LLM_OUTPUT):
        resp = _client.post(
            _anchor_url(project_id), json={"sampleId": "cold-rain"}, headers=headers
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["anchored"] is True
    assert "人称：第三人称限知" in body["styleProfile"]


@requires_db
def test_anchor_happy_paste_persists_to_story_bible(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
    db_engine: Engine,
) -> None:
    user = make_user("style-paste@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)
    with _patch_provider(_GOOD_LLM_OUTPUT):
        resp = _client.post(
            _anchor_url(project_id),
            json={"sampleText": "我自己爱读的一段范文，长度足够进行文风抽取测试用途。"},
            headers=headers,
        )
    assert resp.status_code == 200
    # 落库校验：story_bible.style_profile 已写入。
    with Session(db_engine) as s:
        row = s.scalar(
            select(StoryBible).where(StoryBible.project_id == uuid.UUID(project_id))
        )
        assert row is not None
        assert "语气：冷峻、克制" in row.style_profile


@requires_db
def test_anchor_both_fields_422(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("style-422-both@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)
    resp = _client.post(
        _anchor_url(project_id),
        json={"sampleId": "cold-rain", "sampleText": "同时给了两个来源，长度也足够触发校验。"},
        headers=headers,
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


@requires_db
def test_anchor_short_text_422(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("style-422-short@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)
    resp = _client.post(
        _anchor_url(project_id), json={"sampleText": "太短"}, headers=headers
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


@requires_db
def test_anchor_unknown_sample_id_400(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("style-unknown@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)
    resp = _client.post(
        _anchor_url(project_id), json={"sampleId": "not-a-real-sample"}, headers=headers
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "unknown_style_sample"


@requires_db
def test_anchor_quota_exceeded_429(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("style-429@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)
    quota_err = ErrorEnvelope(
        code="quota_exceeded",
        message="免费额度已用完，绑定自己的 API Key 即可继续创作。",
        http_status=429,
    )
    # 预检阶段 check_quota 抛 429（用请求 session 拦在抽取之前）。
    with patch.object(
        style_anchor_agent.usage_service, "check_quota", new=AsyncMock(side_effect=quota_err)
    ):
        resp = _client.post(
            _anchor_url(project_id), json={"sampleId": "cold-rain"}, headers=headers
        )
    assert resp.status_code == 429
    assert resp.json()["code"] == "quota_exceeded"


@requires_db
def test_anchor_others_project_404(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    alice = make_user("style-owner-a@example.com")
    bob = make_user("style-owner-b@example.com")
    project_id = _create_project(auth_headers(alice))
    resp = _client.post(
        _anchor_url(project_id), json={"sampleId": "cold-rain"}, headers=auth_headers(bob)
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "project_not_found"


@requires_db
def test_anchor_nonexistent_project_404(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("style-404@example.com")
    resp = _client.post(
        _anchor_url(uuid.uuid4()), json={"sampleId": "cold-rain"}, headers=auth_headers(user)
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "project_not_found"
