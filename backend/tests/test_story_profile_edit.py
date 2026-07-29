"""Story 3.4 验证：设定候选卡编辑 + 反馈升版本（真实 Agent）（AC 全覆盖）。

3.3 是 emit-only，3.4 把候选卡落库（story_bible 加 status/revision/changed_fields 列）并补
编辑/反馈升版本/恢复：

- repo 单元（@requires_db）：
  - upsert_profile_card 首次建行（status/revision/changed_fields 落值、主干空串占位）。
  - upsert_profile_card 二次更新同行、不撞唯一约束、只写内容字段白名单。
  - get_pending_by_project：pending 返行 / confirmed 返 None / 无行 None。
  - update_card_fields：改字段值 revision 不变、清 changed_fields、仅 pending 行、白名单外键忽略。
- service 单元（离线，mock provider + check_quota + repos）：
  - revise_profile_card happy：重凝练 → revision+1 → changed_fields=变化列名。
  - revise 护栏 429 → 不调 provider。
  - revise 无 pending 卡 → 404 no_pending_card（不调 provider）。
  - revise 空产 502。
  - _compute_changed_fields：只有主角变 → ["protagonist"]；style_profile 不计入。
  - edit_profile_card 无 pending 卡 → 404。
  - 租户越权 404（先于一切）。
- API 端到端（@requires_db，provider mock）：GET 恢复（有卡 200 / 无 204）、PATCH 编辑落库、
  POST revise 升版本、schema 校验（空反馈 422）、鉴权 401、越权 404。

Story 3.5 追加（确认设定 → 只读圣经 + 回到探索丢弃）：
- repo 单元（@requires_db）：confirm_pending_card（pending→confirmed 只翻 status / 无 pending 返
  None）、delete_pending_card（删 pending 返 True / 无卡 False / 不误删 confirmed）、
  project_repo.advance_phase（explore→chapter）。
- service 单元（@requires_db）：confirm_profile_card happy（confirmed + phase=chapter 同事务）、
  无 pending 卡 404 且 phase 不变、租户越权 404、discard happy 删卡、discard 幂等（无卡不报错）。
- API 端到端（@requires_db）：POST confirm 200 + GET 204 + phase=chapter、confirm 无卡 404、
  POST discard 204 + GET 204、discard 幂等 204、只读契约（confirmed 后 PATCH/revise → 404）。
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
from muse.services import story_settle_agent
from tests.conftest import requires_db

_client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True, scope="module")
def _client_lifespan() -> "object":
    """上下文管理器模式跑 TestClient：所有请求共享同一持久事件循环（与 test_style_anchor 同源）。"""
    with _client:
        yield


def _fake_chat_result(content: str) -> ChatResult:
    return ChatResult(
        content=content,
        prompt_tokens=10,
        completion_tokens=10,
        total_tokens=20,
        model="deepseek-v4-flash",
    )


# 一段模型「理想」重凝练输出：都市题材主干 7 全填、无特化行。
_REVISED_OUTPUT = (
    "题材：都市\n"
    "核心吸引力：小人物职场逆袭\n"
    "主角：李明，想升职证明自己，但太在意别人眼光\n"
    "主要冲突：与压制他的上司暗斗；反派同样渴望上位却踩着别人\n"
    "关键世界规则：现代都市职场\n"
    "整体气质：热血\n"
    "开篇钩子：被裁员那天捡到一个神秘 U 盘"
)


def _card(**overrides: object) -> dict[str, str | None]:
    """构造一份合法 12 字段候选卡 dict（默认都市题材，特化/style_profile 为 None）。"""
    base: dict[str, str | None] = {
        "genre": "都市",
        "core_appeal": "职场爽感",
        "protagonist": "李明，想升职",
        "main_conflict": "与上司斗",
        "world_rules": "现代都市",
        "overall_tone": "轻松",
        "opening_hook": "被裁员那天",
        "power_system": None,
        "golden_finger": None,
        "romance_line": None,
        "faction_landscape": None,
        "style_profile": None,
    }
    base.update(overrides)
    return base


def _bible_mock(**overrides: object) -> MagicMock:
    """假 story_bible 行：12 内容字段 + revision/style_profile，供 revise/edit 读当前卡。"""
    m = MagicMock()
    card = _card()
    for key, value in card.items():
        setattr(m, key, value)
    m.revision = 1
    for key, value in overrides.items():
        setattr(m, key, value)
    return m


# ========== 离线：_compute_changed_fields / _card_from_bible ==========


def test_compute_changed_fields_only_changed() -> None:
    old = _card(protagonist="李明")
    new_card = _card(protagonist="李明，如今更冷酷")  # 只有主角变
    changed = story_settle_agent._compute_changed_fields(old, new_card)
    assert changed == ["protagonist"]


def test_compute_changed_fields_ignores_style_profile() -> None:
    # style_profile 不在 _LLM_FIELDS，恒不计入变化项（受控决策 4）。即便新卡改了它也不算变化。
    old = _card(style_profile="人称：第三人称")
    new_card = _card(style_profile="人称：第一人称")  # style 变了
    changed = story_settle_agent._compute_changed_fields(old, new_card)
    assert "style_profile" not in changed
    assert changed == []


def test_card_from_bible_extracts_12_fields() -> None:
    bible = _bible_mock(genre="修仙", power_system="练气-筑基")
    card = story_settle_agent._card_from_bible(bible)
    assert card["genre"] == "修仙"
    assert card["power_system"] == "练气-筑基"
    assert set(card.keys()) == set(story_bible_repo.PROFILE_CONTENT_FIELDS)


# ========== 离线：revise_profile_card 编排单元 ==========


class _FakeSessionCtx:
    async def __aenter__(self) -> "object":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


def _revise_stack(
    *,
    provider: object,
    pending: object,
    check_quota: object = None,
    get_provider: object = "__default__",
    get_owned_project: object = "__default__",
    upsert_return: object = "__default__",
):
    """patch revise_profile_card 依赖，返回 (ExitStack, upsert_mock)。"""
    from contextlib import ExitStack

    owned = MagicMock() if get_owned_project == "__default__" else get_owned_project
    provider_mock = (
        AsyncMock(return_value=provider)
        if get_provider == "__default__"
        else get_provider
    )
    upsert = AsyncMock(
        return_value=(_bible_mock() if upsert_return == "__default__" else upsert_return)
    )
    stack = ExitStack()
    for target, attr, val in [
        (
            story_settle_agent.project_repo,
            "get_owned_project",
            AsyncMock(return_value=owned),
        ),
        (
            story_settle_agent.story_bible_repo,
            "get_pending_by_project",
            AsyncMock(return_value=pending),
        ),
        (
            story_settle_agent.story_bible_repo,
            "upsert_profile_card",
            upsert,
        ),
        (
            story_settle_agent.usage_service,
            "check_quota",
            check_quota if check_quota is not None else AsyncMock(),
        ),
        (story_settle_agent, "get_provider_for_user", provider_mock),
        (story_settle_agent, "async_session_maker", lambda: _FakeSessionCtx()),
    ]:
        stack.enter_context(patch.object(target, attr, new=val))
    return stack, upsert


async def test_revise_happy_bumps_revision_and_marks_changes() -> None:
    uid, pid = uuid.uuid4(), uuid.uuid4()
    provider = AsyncMock()
    provider.chat = AsyncMock(return_value=_fake_chat_result(_REVISED_OUTPUT))
    pending = _bible_mock(protagonist="李明，想升职", revision=2)
    stack, upsert = _revise_stack(provider=provider, pending=pending)
    with stack:
        await story_settle_agent.revise_profile_card(
            user_id=uid, project_id=pid, feedback="让主角更冷酷一点"
        )
    upsert.assert_awaited_once()
    kwargs = upsert.await_args.kwargs
    assert kwargs["status"] == "pending"
    assert kwargs["revision"] == 3  # 旧 2 + 1
    # protagonist 变了 → 在 changed_fields
    assert "protagonist" in kwargs["changed_fields"]
    assert kwargs["card"]["protagonist"].startswith("李明，想升职证明自己")


async def test_revise_missing_field_falls_back_to_old_value() -> None:
    # code review 发现 2：LLM 漏输出某原有字段 → 回退旧值、不清空、不误标为变化。
    uid, pid = uuid.uuid4(), uuid.uuid4()
    # 只输出主角一行（其余主干字段全漏）——但至少有一个主干、不触发空产 502。
    partial_output = "主角：李明，如今更冷酷决绝"
    provider = AsyncMock()
    provider.chat = AsyncMock(return_value=_fake_chat_result(partial_output))
    pending = _bible_mock(
        genre="都市",
        core_appeal="职场爽感",
        protagonist="李明，想升职",
        world_rules="现代都市",
        revision=1,
    )
    stack, upsert = _revise_stack(provider=provider, pending=pending)
    with stack:
        await story_settle_agent.revise_profile_card(
            user_id=uid, project_id=pid, feedback="让主角更冷酷"
        )
    kwargs = upsert.await_args.kwargs
    card = kwargs["card"]
    # 主角被改（LLM 输出了）
    assert card["protagonist"] == "李明，如今更冷酷决绝"
    # 漏输出的字段回退旧值，**不被清空**
    assert card["genre"] == "都市"
    assert card["core_appeal"] == "职场爽感"
    assert card["world_rules"] == "现代都市"
    # 只有主角算变化，回退的字段不误标
    assert kwargs["changed_fields"] == ["protagonist"]


async def test_revise_quota_exceeded_blocks_provider() -> None:
    uid, pid = uuid.uuid4(), uuid.uuid4()
    quota_err = ErrorEnvelope(code="quota_exceeded", message="额度已用完", http_status=429)
    provider = AsyncMock()
    provider.chat = AsyncMock()
    get_provider = AsyncMock(return_value=provider)
    stack, upsert = _revise_stack(
        provider=provider,
        pending=_bible_mock(),
        check_quota=AsyncMock(side_effect=quota_err),
        get_provider=get_provider,
    )
    with stack:
        with pytest.raises(ErrorEnvelope) as exc:
            await story_settle_agent.revise_profile_card(
                user_id=uid, project_id=pid, feedback="改改"
            )
    assert exc.value.code == "quota_exceeded"
    get_provider.assert_not_awaited()
    provider.chat.assert_not_awaited()
    upsert.assert_not_awaited()


async def test_revise_no_pending_card_404() -> None:
    uid, pid = uuid.uuid4(), uuid.uuid4()
    provider = AsyncMock()
    provider.chat = AsyncMock()
    check_quota = AsyncMock()
    stack, upsert = _revise_stack(
        provider=provider, pending=None, check_quota=check_quota
    )
    with stack:
        with pytest.raises(ErrorEnvelope) as exc:
            await story_settle_agent.revise_profile_card(
                user_id=uid, project_id=pid, feedback="改改"
            )
    assert exc.value.code == "no_pending_card"
    assert exc.value.http_status == 404
    check_quota.assert_not_awaited()  # 无卡先于护栏
    provider.chat.assert_not_awaited()
    upsert.assert_not_awaited()


async def test_revise_empty_produce_502() -> None:
    uid, pid = uuid.uuid4(), uuid.uuid4()
    provider = AsyncMock()
    provider.chat = AsyncMock(return_value=_fake_chat_result("完全跑偏没有标签"))
    stack, _ = _revise_stack(provider=provider, pending=_bible_mock())
    with stack:
        with pytest.raises(ErrorEnvelope) as exc:
            await story_settle_agent.revise_profile_card(
                user_id=uid, project_id=pid, feedback="改改"
            )
    assert exc.value.code == "generate_failed"
    assert exc.value.http_status == 502


async def test_revise_tenant_guard_404_before_all() -> None:
    uid, pid = uuid.uuid4(), uuid.uuid4()
    provider = AsyncMock()
    provider.chat = AsyncMock()
    check_quota = AsyncMock()
    stack, _ = _revise_stack(
        provider=provider,
        pending=_bible_mock(),
        get_owned_project=None,
        check_quota=check_quota,
    )
    with stack:
        with pytest.raises(ErrorEnvelope) as exc:
            await story_settle_agent.revise_profile_card(
                user_id=uid, project_id=pid, feedback="改改"
            )
    assert exc.value.http_status == 404
    check_quota.assert_not_awaited()
    provider.chat.assert_not_awaited()


async def test_revise_prompt_carries_current_card_and_feedback() -> None:
    uid, pid = uuid.uuid4(), uuid.uuid4()
    captured: dict[str, object] = {}

    async def _capture_chat(messages, **kwargs):
        captured["messages"] = messages
        return _fake_chat_result(_REVISED_OUTPUT)

    provider = MagicMock()
    provider.chat = _capture_chat
    pending = _bible_mock(protagonist="李明，想升职")
    stack, _ = _revise_stack(provider=provider, pending=pending)
    with stack:
        await story_settle_agent.revise_profile_card(
            user_id=uid, project_id=pid, feedback="让主角更冷酷"
        )
    user_msg = captured["messages"][1]["content"]
    assert "李明，想升职" in user_msg  # 当前卡入 prompt
    assert "让主角更冷酷" in user_msg  # 反馈入 prompt


# ========== repo 单元（@requires_db）==========


def _seed_user_and_project(engine: Engine) -> tuple[uuid.UUID, uuid.UUID]:
    with Session(engine) as session:
        user = User(email=f"sp-{uuid.uuid4()}@test.local", password_hash="x")
        session.add(user)
        session.flush()
        project = Project(user_id=user.id, title="候选卡测试作品", mode="guided")
        session.add(project)
        session.commit()
        return user.id, project.id


@requires_db
async def test_upsert_profile_card_creates_pending_row(db_engine: Engine) -> None:
    """首次 upsert 候选卡：12 内容字段 + status='pending'、revision=1、changed_fields。"""
    from muse.core.db import async_session_maker

    user_id, project_id = _seed_user_and_project(db_engine)
    async with async_session_maker() as session:
        bible = await story_bible_repo.upsert_profile_card(
            session,
            user_id=user_id,
            project_id=project_id,
            card=_card(genre="修仙", power_system="练气-筑基"),
            status="pending",
            revision=1,
            changed_fields=None,
        )
        await session.commit()
        assert bible.status == "pending"
        assert bible.revision == 1

    with Session(db_engine) as s:
        row = s.scalar(select(StoryBible).where(StoryBible.project_id == project_id))
        assert row is not None
        assert row.genre == "修仙"
        assert row.power_system == "练气-筑基"
        assert row.romance_line is None  # 特化 None
        assert row.status == "pending"


@requires_db
async def test_upsert_profile_card_updates_same_row(db_engine: Engine) -> None:
    """二次 upsert 更新同行、不撞唯一约束、仍一行。"""
    from muse.core.db import async_session_maker

    user_id, project_id = _seed_user_and_project(db_engine)
    async with async_session_maker() as session:
        await story_bible_repo.upsert_profile_card(
            session,
            user_id=user_id,
            project_id=project_id,
            card=_card(genre="修仙"),
            status="pending",
            revision=1,
            changed_fields=None,
        )
        await session.commit()
    async with async_session_maker() as session:
        bible = await story_bible_repo.upsert_profile_card(
            session,
            user_id=user_id,
            project_id=project_id,
            card=_card(genre="都市"),
            status="pending",
            revision=2,
            changed_fields=["genre"],
        )
        await session.commit()
        assert bible.revision == 2
        assert bible.changed_fields == ["genre"]

    with Session(db_engine) as s:
        rows = list(
            s.scalars(select(StoryBible).where(StoryBible.project_id == project_id))
        )
        assert len(rows) == 1
        assert rows[0].genre == "都市"


@requires_db
async def test_get_pending_by_project_status_filter(db_engine: Engine) -> None:
    """get_pending_by_project：pending 返行 / confirmed 返 None / 无行 None。"""
    from muse.core.db import async_session_maker

    user_id, project_id = _seed_user_and_project(db_engine)
    # 无行 → None
    async with async_session_maker() as session:
        assert (
            await story_bible_repo.get_pending_by_project(
                session, user_id=user_id, project_id=project_id
            )
            is None
        )
    # pending → 返行
    async with async_session_maker() as session:
        await story_bible_repo.upsert_profile_card(
            session,
            user_id=user_id,
            project_id=project_id,
            card=_card(),
            status="pending",
            revision=1,
            changed_fields=None,
        )
        await session.commit()
    async with async_session_maker() as session:
        assert (
            await story_bible_repo.get_pending_by_project(
                session, user_id=user_id, project_id=project_id
            )
            is not None
        )
    # 翻 confirmed → get_pending 返 None（AC6：确认后无待确认卡）
    with Session(db_engine) as s:
        row = s.scalar(select(StoryBible).where(StoryBible.project_id == project_id))
        row.status = "confirmed"
        s.commit()
    async with async_session_maker() as session:
        assert (
            await story_bible_repo.get_pending_by_project(
                session, user_id=user_id, project_id=project_id
            )
            is None
        )


@requires_db
async def test_style_only_draft_row_not_returned_as_pending(db_engine: Engine) -> None:
    """code review 发现 1：只锚了文风（3.2 upsert_style_profile 建行）、还没 settle 的行是
    status='draft'，get_pending_by_project 不返回它——避免空白 backbone 卡被当候选卡弹出。"""
    from muse.core.db import async_session_maker

    user_id, project_id = _seed_user_and_project(db_engine)
    # 走 3.2 路径：只锚文风建行（不显式写 status → server_default='draft'）。
    async with async_session_maker() as session:
        row = await story_bible_repo.upsert_style_profile(
            session,
            user_id=user_id,
            project_id=project_id,
            style_profile="人称：第三人称",
        )
        await session.commit()
        assert row.status == "draft"  # 只锚文风不是候选卡
        assert row.genre == ""  # backbone 全空串（半成品行）

    # get_pending 不认 draft → None（GET /story-profile 会返 204，而非空白卡）。
    async with async_session_maker() as session:
        assert (
            await story_bible_repo.get_pending_by_project(
                session, user_id=user_id, project_id=project_id
            )
            is None
        )


@requires_db
async def test_settle_upserts_draft_row_to_pending(db_engine: Engine) -> None:
    """3.2 先锚文风建 draft 行，之后 settle 落库 upsert_profile_card 把它升 pending（同一行）。"""
    from muse.core.db import async_session_maker

    user_id, project_id = _seed_user_and_project(db_engine)
    async with async_session_maker() as session:
        await story_bible_repo.upsert_style_profile(
            session,
            user_id=user_id,
            project_id=project_id,
            style_profile="人称：第三人称",
        )
        await session.commit()
    # settle 落库：draft → pending（复用同行，不新建）。
    async with async_session_maker() as session:
        await story_bible_repo.upsert_profile_card(
            session,
            user_id=user_id,
            project_id=project_id,
            card=_card(genre="修仙", style_profile="人称：第三人称"),
            status="pending",
            revision=1,
            changed_fields=None,
        )
        await session.commit()
    with Session(db_engine) as s:
        rows = list(
            s.scalars(select(StoryBible).where(StoryBible.project_id == project_id))
        )
        assert len(rows) == 1  # 仍一行（升态非新建）
        assert rows[0].status == "pending"
        assert rows[0].genre == "修仙"
        assert rows[0].style_profile == "人称：第三人称"  # 文风保留


@requires_db
async def test_update_card_fields_pending_only_revision_unchanged(
    db_engine: Engine,
) -> None:
    """update_card_fields：改字段值、revision 不变、清 changed_fields、白名单外键忽略。"""
    from muse.core.db import async_session_maker

    user_id, project_id = _seed_user_and_project(db_engine)
    async with async_session_maker() as session:
        await story_bible_repo.upsert_profile_card(
            session,
            user_id=user_id,
            project_id=project_id,
            card=_card(protagonist="李明"),
            status="pending",
            revision=3,
            changed_fields=["genre"],
        )
        await session.commit()
    async with async_session_maker() as session:
        updated = await story_bible_repo.update_card_fields(
            session,
            user_id=user_id,
            project_id=project_id,
            # 含白名单外的键（status），须被忽略。
            fields={"protagonist": "李明（改）", "status": "confirmed"},
        )
        await session.commit()
        assert updated is not None
        assert updated.protagonist == "李明（改）"
        assert updated.revision == 3  # 直接编辑不 bump
        assert updated.changed_fields is None  # 清空
        assert updated.status == "pending"  # 白名单外的 status 未被改


@requires_db
async def test_update_card_fields_no_pending_returns_none(db_engine: Engine) -> None:
    """无 pending 行 → update_card_fields 返 None（confirmed 行也不匹配）。"""
    from muse.core.db import async_session_maker

    user_id, project_id = _seed_user_and_project(db_engine)
    async with async_session_maker() as session:
        # 建一个 confirmed 行（非 pending）。
        await story_bible_repo.upsert_profile_card(
            session,
            user_id=user_id,
            project_id=project_id,
            card=_card(),
            status="confirmed",
            revision=1,
            changed_fields=None,
        )
        await session.commit()
    async with async_session_maker() as session:
        result = await story_bible_repo.update_card_fields(
            session,
            user_id=user_id,
            project_id=project_id,
            fields={"genre": "修仙"},
        )
        assert result is None


# ========== 端点鉴权前置（无需 DB）==========


def _profile_url(project_id: object) -> str:
    return f"/api/projects/{project_id}/story-profile"


def _revise_url(project_id: object) -> str:
    return f"/api/projects/{project_id}/story-profile/revise"


def test_get_profile_without_token_401() -> None:
    resp = _client.get(_profile_url(uuid.uuid4()))
    assert resp.status_code == 401


def test_revise_expired_token_401() -> None:
    settings = get_settings()
    now = int(time.time())
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "type": "access", "iat": now - 100, "exp": now - 10},
        settings.jwt_secret,
        algorithm="HS256",
    )
    resp = _client.post(
        _revise_url(uuid.uuid4()),
        json={"feedback": "改改"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401


# ========== DB 端到端：API（provider mock）==========


def _create_project(headers: dict[str, str], mode: str = "guided") -> str:
    resp = _client.post("/api/projects", json={"mode": mode}, headers=headers)
    assert resp.status_code == 201
    return resp.json()["id"]


def _seed_pending_card(
    db_engine: Engine, user_id: uuid.UUID, project_id: uuid.UUID, **overrides: object
) -> None:
    """直接在 DB 落一份 pending 候选卡（模拟 settle 已跑完）。"""
    with Session(db_engine) as s:
        card = _card(**overrides)
        s.add(
            StoryBible(
                user_id=user_id,
                project_id=project_id,
                status="pending",
                revision=1,
                **card,
            )
        )
        s.commit()


def _user_id_of(db_engine: Engine, email: str) -> uuid.UUID:
    with Session(db_engine) as s:
        return s.scalar(select(User.id).where(User.email == email))


@requires_db
def test_get_pending_returns_204_when_none(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("sp-none@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)
    resp = _client.get(_profile_url(project_id), headers=headers)
    assert resp.status_code == 204


@requires_db
def test_get_pending_returns_card(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
    db_engine: Engine,
) -> None:
    user = make_user("sp-get@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)
    _seed_pending_card(
        db_engine, user.id, uuid.UUID(project_id), genre="修仙", power_system="练气-筑基"
    )
    resp = _client.get(_profile_url(project_id), headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["genre"] == "修仙"
    assert body["powerSystem"] == "练气-筑基"  # camelCase
    assert body["revision"] == 1
    assert body["status"] == "pending"


@requires_db
def test_patch_edits_field_revision_unchanged(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
    db_engine: Engine,
) -> None:
    user = make_user("sp-patch@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)
    _seed_pending_card(db_engine, user.id, uuid.UUID(project_id), protagonist="李明")
    resp = _client.patch(
        _profile_url(project_id),
        json={"protagonist": "李明（用户手改）"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["protagonist"] == "李明（用户手改）"
    assert body["revision"] == 1  # 直接编辑不 bump

    with Session(db_engine) as s:
        row = s.scalar(
            select(StoryBible).where(StoryBible.project_id == uuid.UUID(project_id))
        )
        assert row.protagonist == "李明（用户手改）"


@requires_db
def test_patch_no_pending_card_404(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("sp-patch404@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)
    resp = _client.patch(
        _profile_url(project_id), json={"genre": "修仙"}, headers=headers
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "no_pending_card"


@requires_db
def test_revise_happy_bumps_revision(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
    db_engine: Engine,
) -> None:
    user = make_user("sp-revise@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)
    _seed_pending_card(db_engine, user.id, uuid.UUID(project_id), protagonist="李明")
    fake_provider = AsyncMock()
    fake_provider.chat = AsyncMock(return_value=_fake_chat_result(_REVISED_OUTPUT))
    with patch.object(
        story_settle_agent,
        "get_provider_for_user",
        new=AsyncMock(return_value=fake_provider),
    ):
        resp = _client.post(
            _revise_url(project_id),
            json={"feedback": "让主角更冷酷一点"},
            headers=headers,
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["revision"] == 2  # 1 → 2
    assert "changedFields" in body
    assert body["protagonist"].startswith("李明，想升职证明自己")


@requires_db
def test_revise_empty_feedback_422(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("sp-revise422@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)
    resp = _client.post(
        _revise_url(project_id), json={"feedback": "   "}, headers=headers
    )
    assert resp.status_code == 422


@requires_db
def test_revise_no_pending_card_404_e2e(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("sp-revise404@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)
    resp = _client.post(
        _revise_url(project_id), json={"feedback": "改改"}, headers=headers
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "no_pending_card"


# ========== Story 3.5：confirm / discard / advance_phase ==========


def _confirm_url(project_id: object) -> str:
    return f"/api/projects/{project_id}/story-profile/confirm"


def _discard_url(project_id: object) -> str:
    return f"/api/projects/{project_id}/story-profile/discard"


def _phase_of(db_engine: Engine, project_id: uuid.UUID) -> str:
    with Session(db_engine) as s:
        return s.scalar(select(Project.phase).where(Project.id == project_id))


def _status_of(db_engine: Engine, project_id: uuid.UUID) -> str | None:
    with Session(db_engine) as s:
        return s.scalar(
            select(StoryBible.status).where(StoryBible.project_id == project_id)
        )


# ---------- repo 单元（@requires_db）----------


@requires_db
async def test_confirm_pending_card_flips_status_only(db_engine: Engine) -> None:
    """confirm_pending_card：pending → confirmed，只翻 status，12 字段/revision 不动。"""
    from muse.core.db import async_session_maker

    user_id, project_id = _seed_user_and_project(db_engine)
    async with async_session_maker() as session:
        await story_bible_repo.upsert_profile_card(
            session,
            user_id=user_id,
            project_id=project_id,
            card=_card(genre="修仙"),
            status="pending",
            revision=2,
            changed_fields=["genre"],
        )
        await session.commit()
    async with async_session_maker() as session:
        bible = await story_bible_repo.confirm_pending_card(
            session, user_id=user_id, project_id=project_id
        )
        await session.commit()
        assert bible is not None
        assert bible.status == "confirmed"
        assert bible.genre == "修仙"  # 内容不动
        assert bible.revision == 2  # 版本不动
        assert bible.changed_fields == ["genre"]  # 不动

    # 再 confirm → 无 pending 行 → None（已确认无待确认卡）。
    async with async_session_maker() as session:
        again = await story_bible_repo.confirm_pending_card(
            session, user_id=user_id, project_id=project_id
        )
        assert again is None


@requires_db
async def test_confirm_pending_card_no_pending_returns_none(db_engine: Engine) -> None:
    """无 pending 行（只有 draft）→ confirm_pending_card 返 None。"""
    from muse.core.db import async_session_maker

    user_id, project_id = _seed_user_and_project(db_engine)
    async with async_session_maker() as session:
        # draft 行（只锚文风）。
        await story_bible_repo.upsert_style_profile(
            session,
            user_id=user_id,
            project_id=project_id,
            style_profile="人称：第三人称",
        )
        await session.commit()
    async with async_session_maker() as session:
        assert (
            await story_bible_repo.confirm_pending_card(
                session, user_id=user_id, project_id=project_id
            )
            is None
        )
    # draft 行未被误翻 confirmed。
    assert _status_of(db_engine, project_id) == "draft"


@requires_db
async def test_delete_pending_card_removes_row(db_engine: Engine) -> None:
    """delete_pending_card：删 pending 行返 True，行消失。"""
    from muse.core.db import async_session_maker

    user_id, project_id = _seed_user_and_project(db_engine)
    async with async_session_maker() as session:
        await story_bible_repo.upsert_profile_card(
            session,
            user_id=user_id,
            project_id=project_id,
            card=_card(),
            status="pending",
            revision=1,
            changed_fields=None,
        )
        await session.commit()
    async with async_session_maker() as session:
        deleted = await story_bible_repo.delete_pending_card(
            session, user_id=user_id, project_id=project_id
        )
        await session.commit()
        assert deleted is True

    with Session(db_engine) as s:
        row = s.scalar(select(StoryBible).where(StoryBible.project_id == project_id))
        assert row is None


@requires_db
async def test_delete_pending_card_no_row_returns_false(db_engine: Engine) -> None:
    """无 pending 卡 → delete_pending_card 返 False（幂等）。"""
    from muse.core.db import async_session_maker

    user_id, project_id = _seed_user_and_project(db_engine)
    async with async_session_maker() as session:
        deleted = await story_bible_repo.delete_pending_card(
            session, user_id=user_id, project_id=project_id
        )
        assert deleted is False


@requires_db
async def test_delete_pending_card_does_not_touch_confirmed(db_engine: Engine) -> None:
    """confirmed 只读圣经不被 delete_pending_card 误删。"""
    from muse.core.db import async_session_maker

    user_id, project_id = _seed_user_and_project(db_engine)
    async with async_session_maker() as session:
        await story_bible_repo.upsert_profile_card(
            session,
            user_id=user_id,
            project_id=project_id,
            card=_card(),
            status="confirmed",
            revision=1,
            changed_fields=None,
        )
        await session.commit()
    async with async_session_maker() as session:
        deleted = await story_bible_repo.delete_pending_card(
            session, user_id=user_id, project_id=project_id
        )
        await session.commit()
        assert deleted is False  # confirmed 不匹配 pending

    assert _status_of(db_engine, project_id) == "confirmed"  # 仍在


@requires_db
async def test_advance_phase_explore_to_chapter(db_engine: Engine) -> None:
    """advance_phase：project.phase explore → chapter，flush 后持久化。"""
    from muse.core.db import async_session_maker
    from muse.repositories import project_repo

    user_id, project_id = _seed_user_and_project(db_engine)
    assert _phase_of(db_engine, project_id) == "explore"  # 建行初始
    async with async_session_maker() as session:
        project = await project_repo.get_owned_project(session, project_id, user_id)
        await project_repo.advance_phase(session, project, phase="chapter")
        await session.commit()
    assert _phase_of(db_engine, project_id) == "chapter"


# ---------- service 单元（@requires_db）----------


@requires_db
async def test_confirm_profile_card_confirms_and_advances_phase(
    db_engine: Engine,
) -> None:
    """confirm_profile_card happy：status=confirmed + phase=chapter 同一事务。"""
    from muse.core.db import async_session_maker

    user_id, project_id = _seed_user_and_project(db_engine)
    async with async_session_maker() as session:
        await story_bible_repo.upsert_profile_card(
            session,
            user_id=user_id,
            project_id=project_id,
            card=_card(genre="修仙"),
            status="pending",
            revision=1,
            changed_fields=None,
        )
        await session.commit()
    async with async_session_maker() as session:
        bible = await story_settle_agent.confirm_profile_card(
            session, user_id=user_id, project_id=project_id
        )
        assert bible.status == "confirmed"
    # 两处都落库。
    assert _status_of(db_engine, project_id) == "confirmed"
    assert _phase_of(db_engine, project_id) == "chapter"


@requires_db
async def test_confirm_no_pending_card_404_phase_unchanged(db_engine: Engine) -> None:
    """confirm 无 pending 卡 → 404 no_pending_card，phase 保持 explore（事务未提交）。"""
    from muse.core.db import async_session_maker

    user_id, project_id = _seed_user_and_project(db_engine)
    async with async_session_maker() as session:
        with pytest.raises(ErrorEnvelope) as exc:
            await story_settle_agent.confirm_profile_card(
                session, user_id=user_id, project_id=project_id
            )
    assert exc.value.code == "no_pending_card"
    assert exc.value.http_status == 404
    assert _phase_of(db_engine, project_id) == "explore"  # 未推进


@requires_db
async def test_confirm_tenant_guard_404(db_engine: Engine) -> None:
    """confirm 他人 project_id → 404 project_not_found（租户守卫先于一切）。

    seed owner 的 pending 卡 + 断言 code=project_not_found（而非只断 404）：确保租户守卫真被
    验证——若删掉 service 层 get_owned_project 守卫，attacker user_id 过滤不到 pending 会抛
    no_pending_card（也是 404）掩盖回归，故必须断到 code 区分「越权」与「无卡」。
    """
    from muse.core.db import async_session_maker

    user_id, project_id = _seed_user_and_project(db_engine)
    other_user, _ = _seed_user_and_project(db_engine)
    # owner 有一张 pending 卡：若租户守卫被删，attacker 会因过滤不到而返 no_pending_card。
    async with async_session_maker() as session:
        await story_bible_repo.upsert_profile_card(
            session,
            user_id=user_id,
            project_id=project_id,
            card=_card(),
            status="pending",
            revision=1,
            changed_fields=None,
        )
        await session.commit()
    async with async_session_maker() as session:
        with pytest.raises(ErrorEnvelope) as exc:
            await story_settle_agent.confirm_profile_card(
                session, user_id=other_user, project_id=project_id
            )
    assert exc.value.http_status == 404
    assert exc.value.code == "project_not_found"  # 租户守卫，非 no_pending_card


@requires_db
async def test_discard_profile_card_deletes(db_engine: Engine) -> None:
    """discard_profile_card happy：删 pending 卡。"""
    from muse.core.db import async_session_maker

    user_id, project_id = _seed_user_and_project(db_engine)
    async with async_session_maker() as session:
        await story_bible_repo.upsert_profile_card(
            session,
            user_id=user_id,
            project_id=project_id,
            card=_card(),
            status="pending",
            revision=1,
            changed_fields=None,
        )
        await session.commit()
    async with async_session_maker() as session:
        await story_settle_agent.discard_profile_card(
            session, user_id=user_id, project_id=project_id
        )
    assert _status_of(db_engine, project_id) is None  # 行已删


@requires_db
async def test_discard_idempotent_no_card(db_engine: Engine) -> None:
    """discard 无 pending 卡 → 幂等不报错。"""
    from muse.core.db import async_session_maker

    user_id, project_id = _seed_user_and_project(db_engine)
    async with async_session_maker() as session:
        # 不抛异常即通过。
        await story_settle_agent.discard_profile_card(
            session, user_id=user_id, project_id=project_id
        )


@requires_db
async def test_discard_tenant_guard_404(db_engine: Engine) -> None:
    """discard 他人 project_id → 404。"""
    from muse.core.db import async_session_maker

    user_id, project_id = _seed_user_and_project(db_engine)
    other_user, _ = _seed_user_and_project(db_engine)
    async with async_session_maker() as session:
        with pytest.raises(ErrorEnvelope) as exc:
            await story_settle_agent.discard_profile_card(
                session, user_id=other_user, project_id=project_id
            )
    assert exc.value.http_status == 404


# ---------- API 端到端（@requires_db）----------


@requires_db
def test_confirm_e2e_then_get_204_phase_chapter(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
    db_engine: Engine,
) -> None:
    """POST confirm → 200 + confirmed 卡；随后 GET → 204、project phase=chapter。"""
    user = make_user("sp-confirm@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)
    _seed_pending_card(db_engine, user.id, uuid.UUID(project_id), genre="修仙")
    resp = _client.post(_confirm_url(project_id), headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "confirmed"
    assert body["genre"] == "修仙"
    # 确认后待确认态已清。
    assert _client.get(_profile_url(project_id), headers=headers).status_code == 204
    # phase 已推进。
    assert _phase_of(db_engine, uuid.UUID(project_id)) == "chapter"


@requires_db
def test_confirm_e2e_no_pending_404(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("sp-confirm404@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)
    resp = _client.post(_confirm_url(project_id), headers=headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == "no_pending_card"


@requires_db
def test_discard_e2e_then_get_204(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
    db_engine: Engine,
) -> None:
    """POST discard → 204；随后 GET → 204（回到探索态）。"""
    user = make_user("sp-discard@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)
    _seed_pending_card(db_engine, user.id, uuid.UUID(project_id))
    resp = _client.post(_discard_url(project_id), headers=headers)
    assert resp.status_code == 204
    assert _client.get(_profile_url(project_id), headers=headers).status_code == 204


@requires_db
def test_discard_e2e_idempotent(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """discard 无卡也 204（幂等）；重复 discard 仍 204。"""
    user = make_user("sp-discard-idem@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)
    assert _client.post(_discard_url(project_id), headers=headers).status_code == 204
    assert _client.post(_discard_url(project_id), headers=headers).status_code == 204


@requires_db
def test_confirmed_card_is_readonly_patch_and_revise_404(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
    db_engine: Engine,
) -> None:
    """只读契约（AC2）：confirm 后 PATCH 编辑 / POST revise 均 404（confirmed 不可改）。"""
    user = make_user("sp-readonly@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)
    _seed_pending_card(db_engine, user.id, uuid.UUID(project_id))
    assert _client.post(_confirm_url(project_id), headers=headers).status_code == 200
    # confirmed 后编辑 → 404 no_pending_card。
    patch_resp = _client.patch(
        _profile_url(project_id), json={"genre": "都市"}, headers=headers
    )
    assert patch_resp.status_code == 404
    assert patch_resp.json()["code"] == "no_pending_card"
    # confirmed 后反馈升版本 → 404（不动 provider）。
    revise_resp = _client.post(
        _revise_url(project_id), json={"feedback": "改改"}, headers=headers
    )
    assert revise_resp.status_code == 404
    assert revise_resp.json()["code"] == "no_pending_card"


def test_confirm_without_token_401() -> None:
    resp = _client.post(_confirm_url(uuid.uuid4()))
    assert resp.status_code == 401


@requires_db
def test_confirm_cross_tenant_404(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
    db_engine: Engine,
) -> None:
    """他人作品 confirm → 404 project_not_found（越权二义合一）。

    owner 有 pending 卡：attacker 请求须因租户守卫返 project_not_found，而非因过滤不到卡返
    no_pending_card——断到 code 才能保护 service 层租户守卫不被回归掉。
    """
    owner = make_user("sp-owner@example.com")
    owner_headers = auth_headers(owner)
    project_id = _create_project(owner_headers)
    _seed_pending_card(db_engine, owner.id, uuid.UUID(project_id))
    attacker = make_user("sp-attacker@example.com")
    attacker_headers = auth_headers(attacker)
    resp = _client.post(_confirm_url(project_id), headers=attacker_headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == "project_not_found"


@requires_db
async def test_settle_blocked_after_confirm_guards_confirmed_card(
    db_engine: Engine,
) -> None:
    """code review High-1 修复：确认后（phase=chapter）重发 settle → 409 already_settled。

    确认设定推进 phase=chapter；此后 trigger_guided_settle 须在 mode 守卫后被 phase 门禁拦下，
    否则 worker settle 会把 confirmed 行覆写回 pending、绕过 AC2 只读。断言 409 发生在建 Redis
    池/入队之前（本测试不依赖 Redis），且 confirmed 行未被触碰。
    """
    from muse.core.db import async_session_maker
    from muse.services import exploration_service

    user_id, project_id = _seed_user_and_project(db_engine)  # mode=guided
    # 落 pending 卡并确认 → phase=chapter、status=confirmed。
    async with async_session_maker() as session:
        await story_bible_repo.upsert_profile_card(
            session,
            user_id=user_id,
            project_id=project_id,
            card=_card(genre="修仙"),
            status="pending",
            revision=1,
            changed_fields=None,
        )
        await session.commit()
    async with async_session_maker() as session:
        await story_settle_agent.confirm_profile_card(
            session, user_id=user_id, project_id=project_id
        )
    assert _phase_of(db_engine, project_id) == "chapter"
    # 确认后重发 settle → 409 already_settled（门禁先于建 Redis 池）。
    async with async_session_maker() as session:
        with pytest.raises(ErrorEnvelope) as exc:
            await exploration_service.trigger_guided_settle(
                session, user_id=user_id, project_id=project_id
            )
    assert exc.value.http_status == 409
    assert exc.value.code == "already_settled"
    # confirmed 行原封不动（未被覆写回 pending）。
    assert _status_of(db_engine, project_id) == "confirmed"
