"""Story 5.3：归档读路径与聚合 service 测试（@requires_db）。

repo 方法与 service 均通过应用 `async_session_maker` 执行；user/project/story_bible/
stage_plan/chapter_card 测试种子用同步 Session 落库，延续现有 repo 测试范式。
"""

import uuid

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from muse.core.db import async_session_maker
from muse.core.errors import ErrorEnvelope
from muse.models.account import User
from muse.models.chapter_card import ChapterCard
from muse.models.project import Project
from muse.models.stage_plan import StagePlan
from muse.models.story_bible import StoryBible
from muse.repositories import chapter_card_repo, stage_plan_repo
from muse.services import archive_service
from tests.conftest import requires_db


def _seed_user_and_project(engine: Engine) -> tuple[uuid.UUID, uuid.UUID]:
    """造一个 user + 其名下一个 project。"""
    with Session(engine) as session:
        user = User(email=f"archive-{uuid.uuid4()}@test.local", password_hash="x")
        session.add(user)
        session.flush()
        project = Project(user_id=user.id, title="归档测试作品", mode="guided")
        session.add(project)
        session.commit()
        return user.id, project.id


def _seed_card(
    engine: Engine,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    chapter_number: int,
    stage_number: int = 1,
) -> None:
    with Session(engine) as session:
        session.add(
            ChapterCard(
                user_id=user_id,
                project_id=project_id,
                chapter_number=chapter_number,
                stage_number=stage_number,
                what_happened=f"第{chapter_number}章发生的事",
                character_changes=f"第{chapter_number}章人物变化",
                new_facts_clues=f"第{chapter_number}章新线索",
                unresolved_hooks=f"第{chapter_number}章悬念",
                end_state=f"第{chapter_number}章末状态",
            )
        )
        session.commit()


def _seed_stage(
    engine: Engine,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    stage_number: int,
    chapter_count: int,
) -> None:
    with Session(engine) as session:
        session.add(
            StagePlan(
                user_id=user_id,
                project_id=project_id,
                stage_number=stage_number,
                goal=f"第 {stage_number} 阶段目标",
                chapters=[
                    {"title": f"阶段{stage_number}第{i}章", "brief": f"简介{i}"}
                    for i in range(1, chapter_count + 1)
                ],
            )
        )
        session.commit()


def _seed_confirmed_bible(
    engine: Engine,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    include_optional: bool = True,
) -> None:
    with Session(engine) as session:
        session.add(
            StoryBible(
                user_id=user_id,
                project_id=project_id,
                status="confirmed",
                genre="仙侠",
                core_appeal="逆袭与寻亲",
                protagonist="林凡，执拗而多疑",
                main_conflict="对抗篡改记忆的宗门",
                world_rules="记忆可被交换但不可凭空创造",
                overall_tone="紧张、克制",
                opening_hook="收到来自未来的信",
                power_system="九境",
                golden_finger="可保存一段真实记忆",
                romance_line="慢热",
                faction_landscape="三宗对峙",
                style_profile="短句、近距离视角",
            )
            if include_optional
            else StoryBible(
                user_id=user_id,
                project_id=project_id,
                status="confirmed",
                genre="都市悬疑",
                core_appeal="追查消失的人",
                protagonist="程野",
                main_conflict="城市不断改写过去",
                world_rules="记忆会在雨夜变化",
                overall_tone="潮湿压抑",
                opening_hook="未来来信",
            )
        )
        session.commit()


@requires_db
@pytest.mark.asyncio
async def test_list_chapter_cards_by_project_ascending_and_tenant_guard(
    db_engine: Engine,
) -> None:
    """全量章节卡按章号升序，且 user_id + project_id 双键隔离（AC2/AC4）。"""
    user_id, project_id = _seed_user_and_project(db_engine)
    other_user_id, other_project_id = _seed_user_and_project(db_engine)
    for chapter_number in (3, 1, 2):
        _seed_card(
            db_engine,
            user_id=user_id,
            project_id=project_id,
            chapter_number=chapter_number,
        )
    _seed_card(
        db_engine,
        user_id=other_user_id,
        project_id=other_project_id,
        chapter_number=9,
    )

    async with async_session_maker() as session:
        cards = await chapter_card_repo.list_by_project(
            session, user_id=user_id, project_id=project_id
        )
        cross_tenant = await chapter_card_repo.list_by_project(
            session, user_id=other_user_id, project_id=project_id
        )

    assert [card.chapter_number for card in cards] == [1, 2, 3]
    assert cross_tenant == []


@requires_db
@pytest.mark.asyncio
async def test_list_all_stage_plans_ascending_and_tenant_guard(
    db_engine: Engine,
) -> None:
    """全部阶段按 stage_number 升序，且跨租户查询返回空列表。"""
    user_id, project_id = _seed_user_and_project(db_engine)
    other_user_id, _ = _seed_user_and_project(db_engine)
    _seed_stage(
        db_engine,
        user_id=user_id,
        project_id=project_id,
        stage_number=2,
        chapter_count=1,
    )
    _seed_stage(
        db_engine,
        user_id=user_id,
        project_id=project_id,
        stage_number=1,
        chapter_count=2,
    )

    async with async_session_maker() as session:
        plans = await stage_plan_repo.list_all_by_project(
            session, user_id=user_id, project_id=project_id
        )
        cross_tenant = await stage_plan_repo.list_all_by_project(
            session, user_id=other_user_id, project_id=project_id
        )

    assert [plan.stage_number for plan in plans] == [1, 2]
    assert cross_tenant == []


@requires_db
@pytest.mark.asyncio
async def test_archive_summary_without_confirmed_bible_returns_profile_empty_state(
    db_engine: Engine,
) -> None:
    """无 confirmed 圣经时不阻断归档页，返回明确空态（AC1/AC3）。"""
    user_id, project_id = _seed_user_and_project(db_engine)

    async with async_session_maker() as session:
        summary = await archive_service.get_archive_summary(
            session, user_id=user_id, project_id=project_id
        )

    assert summary.profile_confirmed is False
    assert summary.profile_fields is None
    assert summary.stages == []


@requires_db
@pytest.mark.asyncio
async def test_archive_summary_returns_confirmed_profile_in_canonical_order(
    db_engine: Engine,
) -> None:
    """已确认且 12 项均有值时，按主干→特化→文风顺序返回全部字段（AC3）。"""
    user_id, project_id = _seed_user_and_project(db_engine)
    _seed_confirmed_bible(
        db_engine, user_id=user_id, project_id=project_id, include_optional=True
    )

    async with async_session_maker() as session:
        summary = await archive_service.get_archive_summary(
            session, user_id=user_id, project_id=project_id
        )

    assert summary.profile_confirmed is True
    assert summary.profile_fields is not None
    assert [item.field_name for item in summary.profile_fields] == [
        "genre",
        "core_appeal",
        "protagonist",
        "main_conflict",
        "world_rules",
        "overall_tone",
        "opening_hook",
        "power_system",
        "golden_finger",
        "romance_line",
        "faction_landscape",
        "style_profile",
    ]
    assert summary.profile_fields[0].label == "题材"


@requires_db
@pytest.mark.asyncio
async def test_archive_summary_skips_null_optional_profile_fields(
    db_engine: Engine,
) -> None:
    """未激活的特化字段和未锚定文风为 None 时不显示空白项。"""
    user_id, project_id = _seed_user_and_project(db_engine)
    _seed_confirmed_bible(
        db_engine, user_id=user_id, project_id=project_id, include_optional=False
    )

    async with async_session_maker() as session:
        summary = await archive_service.get_archive_summary(
            session, user_id=user_id, project_id=project_id
        )

    assert summary.profile_fields is not None
    assert [item.field_name for item in summary.profile_fields] == [
        "genre",
        "core_appeal",
        "protagonist",
        "main_conflict",
        "world_rules",
        "overall_tone",
        "opening_hook",
    ]


@requires_db
@pytest.mark.asyncio
async def test_archive_summary_groups_global_chapter_numbers_by_stage_offsets(
    db_engine: Engine,
) -> None:
    """按前序阶段计划章数累加 offset，将真实章节卡分进正确阶段（AC1/AC2）。"""
    user_id, project_id = _seed_user_and_project(db_engine)
    _seed_stage(
        db_engine,
        user_id=user_id,
        project_id=project_id,
        stage_number=1,
        chapter_count=2,
    )
    _seed_stage(
        db_engine,
        user_id=user_id,
        project_id=project_id,
        stage_number=2,
        chapter_count=2,
    )
    # 第 2 章尚未定稿；第 4 章尚未定稿。阶段归属在投影时固定。
    for chapter_number, stage_number in ((1, 1), (3, 2)):
        _seed_card(
            db_engine,
            user_id=user_id,
            project_id=project_id,
            chapter_number=chapter_number,
            stage_number=stage_number,
        )

    async with async_session_maker() as session:
        summary = await archive_service.get_archive_summary(
            session, user_id=user_id, project_id=project_id
        )

    assert [stage.stage_number for stage in summary.stages] == [1, 2]
    assert summary.stages[0].title == "第 1 阶段"
    assert [card.chapter_number for card in summary.stages[0].chapter_cards] == [1]
    assert summary.stages[0].chapter_cards[0].title == "第 1 章"
    assert summary.stages[0].chapter_cards[0].brief == "第1章发生的事"
    assert summary.stages[0].completed_count == 1
    assert summary.stages[0].missing == 1
    assert [card.chapter_number for card in summary.stages[1].chapter_cards] == [3]
    assert summary.stages[1].completed_count == 1
    assert summary.stages[1].missing == 1


@requires_db
@pytest.mark.asyncio
async def test_archive_summary_keeps_historical_stage_after_plan_regeneration(
    db_engine: Engine,
) -> None:
    """阶段计划改章数后，已定稿卡仍按投影时 stage_number 留在原阶段。"""
    user_id, project_id = _seed_user_and_project(db_engine)
    _seed_stage(
        db_engine,
        user_id=user_id,
        project_id=project_id,
        stage_number=1,
        chapter_count=2,
    )
    _seed_stage(
        db_engine,
        user_id=user_id,
        project_id=project_id,
        stage_number=2,
        chapter_count=2,
    )
    _seed_card(
        db_engine,
        user_id=user_id,
        project_id=project_id,
        chapter_number=3,
        stage_number=2,
    )

    # 重规划第一阶段：计划从 2 章改为 3 章。历史卡的 stage_number 不应被重映射。
    async with async_session_maker() as session:
        await stage_plan_repo.upsert_stage_plan(
            session,
            user_id=user_id,
            project_id=project_id,
            stage_number=1,
            goal="第一阶段重规划",
            chapters=[
                {"title": "章1", "brief": "..."},
                {"title": "章2", "brief": "..."},
                {"title": "章3", "brief": "新增章"},
            ],
        )
        await session.commit()

    async with async_session_maker() as session:
        summary = await archive_service.get_archive_summary(
            session, user_id=user_id, project_id=project_id
        )

    assert summary.stages[0].completed_count == 0
    assert [card.chapter_number for card in summary.stages[1].chapter_cards] == [3]


@requires_db
@pytest.mark.asyncio
async def test_archive_summary_keeps_unclassified_legacy_cards_visible(
    db_engine: Engine,
) -> None:
    """无法回填阶段的旧卡以未归类阶段返回，不能在归档页静默消失。"""
    user_id, project_id = _seed_user_and_project(db_engine)
    _seed_card(
        db_engine,
        user_id=user_id,
        project_id=project_id,
        chapter_number=1,
        stage_number=None,
    )

    async with async_session_maker() as session:
        summary = await archive_service.get_archive_summary(
            session, user_id=user_id, project_id=project_id
        )

    assert len(summary.stages) == 1
    assert summary.stages[0].stage_number == 0
    assert summary.stages[0].title == "未归类章节"
    assert [card.chapter_number for card in summary.stages[0].chapter_cards] == [1]
    """他人 user_id 访问真实 project_id 统一返回 project_not_found 404（AC4）。"""
    owner_id, project_id = _seed_user_and_project(db_engine)
    other_user_id, _ = _seed_user_and_project(db_engine)
    assert owner_id != other_user_id

    async with async_session_maker() as session:
        with pytest.raises(ErrorEnvelope) as raised:
            await archive_service.get_archive_summary(
                session, user_id=other_user_id, project_id=project_id
            )

    assert raised.value.code == "project_not_found"
    assert raised.value.http_status == 404
