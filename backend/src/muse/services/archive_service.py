"""归档页业务编排（Story 5.3，FR24）。

读取已确认设定圣经与章节归档卡，构造成归档页聚合 payload。章节卡在首次写后投影时
持久化 `stage_number`；归档查询据该不可变历史归属分组，阶段计划重生成不会改变既有
章节归档位置。
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from muse.core.errors import ErrorEnvelope
from muse.models.chapter_card import ChapterCard
from muse.repositories import (
    chapter_card_repo,
    project_repo,
    stage_plan_repo,
    story_bible_repo,
)
from muse.schemas.archive import (
    PROFILE_LABELS,
    ArchiveProfileItem,
    ArchiveStageGroup,
    ArchiveSummaryResponse,
    ChapterCardSummary,
)

_UNCLASSIFIED_STAGE_NUMBER = 0


def _project_not_found() -> ErrorEnvelope:
    """越权与不存在共用同一 404，不泄露 project_id 是否真实存在。"""
    return ErrorEnvelope(
        code="project_not_found",
        message="作品不存在。",
        http_status=404,
    )


def _to_card_summary(card: ChapterCard) -> ChapterCardSummary:
    """以归档五要素构造稳定的已定稿章节展示摘要。"""
    chapter_number = card.chapter_number
    what_happened = card.what_happened
    return ChapterCardSummary(
        chapter_number=chapter_number,
        title=f"第 {chapter_number} 章",
        brief=what_happened,
        what_happened=what_happened,
        character_changes=card.character_changes,
        new_facts_clues=card.new_facts_clues,
        unresolved_hooks=card.unresolved_hooks,
        end_state=card.end_state,
    )


async def get_archive_summary(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
) -> ArchiveSummaryResponse:
    """读取归档页的已确认设定、阶段与章节卡片（AC1-AC4）。

    所有权先由 `get_owned_project` 二义合一校验；后续 repo 查询继续带 user_id +
    project_id 双条件。已确认圣经不存在时返回 profile 空态，不阻断页面渲染。

    `chapter_card.stage_number` 是定稿时固定的历史归属：
    - 有所属阶段的卡片按该值分组，阶段计划被重生成也不会移动它。
    - 迁移前无法可靠回填的 NULL 卡片放进 stage_number=0 的“未归类章节”组，绝不静默丢失。
    - 当前 `stage_plan.chapters` 仅用于计算每个阶段尚待完成数，不参与历史卡片归属判断。
    """
    project = await project_repo.get_owned_project(session, project_id, user_id)
    if project is None:
        raise _project_not_found()

    bible = await story_bible_repo.get_confirmed_by_project(
        session, user_id=user_id, project_id=project_id
    )
    profile_fields: list[ArchiveProfileItem] | None = None
    if bible is not None:
        profile_fields = []
        for field_name in story_bible_repo.PROFILE_CONTENT_FIELDS:
            value = getattr(bible, field_name)
            if value is None:
                continue
            profile_fields.append(
                ArchiveProfileItem(
                    field_name=field_name,
                    label=PROFILE_LABELS[field_name],
                    value=value,
                )
            )

    stage_plans = await stage_plan_repo.list_all_by_project(
        session, user_id=user_id, project_id=project_id
    )
    chapter_cards = await chapter_card_repo.list_by_project(
        session, user_id=user_id, project_id=project_id
    )

    cards_by_stage: dict[int, list[ChapterCardSummary]] = {}
    for card in chapter_cards:
        stage_number = card.stage_number
        if stage_number is None:
            stage_number = _UNCLASSIFIED_STAGE_NUMBER
        cards_by_stage.setdefault(stage_number, []).append(_to_card_summary(card))

    stages: list[ArchiveStageGroup] = []
    for plan in stage_plans:
        stage_cards = cards_by_stage.pop(plan.stage_number, [])
        stages.append(
            ArchiveStageGroup(
                stage_number=plan.stage_number,
                title=f"第 {plan.stage_number} 阶段",
                completed_count=len(stage_cards),
                chapter_cards=stage_cards,
                missing=max(0, len(plan.chapters or []) - len(stage_cards)),
            )
        )

    for stage_number, stage_cards in sorted(cards_by_stage.items()):
        title = (
            "未归类章节"
            if stage_number == _UNCLASSIFIED_STAGE_NUMBER
            else f"第 {stage_number} 阶段（历史归档）"
        )
        stages.append(
            ArchiveStageGroup(
                stage_number=stage_number,
                title=title,
                completed_count=len(stage_cards),
                chapter_cards=stage_cards,
                missing=0,
            )
        )

    return ArchiveSummaryResponse(
        profile_confirmed=bible is not None,
        profile_fields=profile_fields,
        stages=stages,
    )
