"""章节写后投影服务（Story 5.2，AR17）：data-agent 提取结果 → 单事务 chapter-commit
原子投影回 story_state / chapter_card / story_thread。

**分层**：本 service 只做「DB 投影编排」，不调 LLM（data-agent 在 orchestration/steps.py
负责 LLM 提取）。`chapter_commit` 接收 data-agent 产出的结构化 dict，在同一 session
内依次 upsert 三张归档表——**单事务**（AC2）：任一步抛异常 → 上层 rollback 整体
回滚，不留半更新状态（NFR4 一致性投影原子性）。

**投影三类写操作**（data-agent 输出的结构化 schema）：
1. `chapter_card` 五要素（本章发生了什么/人物变化/新增事实与线索/未解决悬念/章末
   状态）——(user_id, project_id, chapter_number) 复合唯一，重跑覆盖同行。
2. `story_state` 三列快照（主角状态/世界规则/当前阶段）——(user_id, project_id)
   复合唯一，重跑覆盖同行。
3. `story_thread` 三类操作：
   - `new_threads`：新埋伏笔 → `upsert_new_thread`（同内容已存在 open thread → 仅
     更新 last_touched，不新建行——defer 台账 B2 防线）。
   - `resolved_threads`：本章回收的伏笔 → `resolve_thread_by_content`（按内容匹配
     既有 open thread → UPDATE status='resolved' + resolved_chapter_number；**校验
     `resolved >= introduced`**——defer 台账 E5，违反跳过+warning）。
   - `touched_threads`：本章再提的伏笔 → `touch_thread_by_content`（按内容匹配 →
     UPDATE last_touched；**校验单调不减**——defer 台账 E6，违反跳过+warning）。

**status 白名单防线（defer 台账 P3+E4）**：story_thread_repo 三个写方法 status
全部硬编码为 'open' / 'resolved' 字面量（repo 不开放 status 入参），LLM 无法经
data-agent → 本 service 写入非法 status（'abandoned' 留 V2 手动放弃路径）。

**session 边界**：本 service 不创建 session——session 由调用方
（`chapter_service.finalize_and_project_chapter`）传入；commit 也在调用方（本
service 不 commit），保证「三表投影 + 任何后续操作」与调用方的整体事务对齐。
"""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from muse.repositories import (
    chapter_card_repo,
    story_state_repo,
    story_thread_repo,
)

logger = logging.getLogger("muse")


async def chapter_commit(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    chapter_number: int,
    extracted: dict,
    stage_number: int = 1,
) -> None:
    """单事务 chapter-commit 原子投影（Story 5.2 AC2，AR17，NFR4）。

    **不 commit**——commit 边界归调用方（`chapter_service.finalize_and_project_chapter`）。
    任一步抛异常 → 调用方 `session.rollback()` 整体回滚，三表全不落（防半更新穿帮）。

    入参 `extracted` 是 data-agent 产出的结构化 dict（schema 见
    `orchestration/steps.py:run_data_agent` docstring）：
    - 五要素：what_happened / character_changes / new_facts_clues / unresolved_hooks /
      end_state
    - 三列快照：protagonist_state / world_rules_state / current_stage
    - 三类 thread：new_threads / resolved_threads / touched_threads（各为 list[dict]，
      每项含 content + 对应章号字段）

    **幂等**：本函数可被重复调用（data-agent 断点续跑复用产物 / ARQ 重试 / 重入）——
    chapter_card 与 story_state 的复合唯一键 upsert 覆盖同行不产生副本；story_thread
    同内容 open thread 防重（B2 防线）；章号约束（E5/E6）违反时跳过+warning 不阻断。
    """
    # ---------- 1. chapter_card 五要素（一章一卡，重跑覆盖） ----------
    await chapter_card_repo.upsert_chapter_card(
        session,
        user_id=user_id,
        project_id=project_id,
        chapter_number=chapter_number,
        stage_number=stage_number,
        what_happened=extracted["what_happened"],
        character_changes=extracted["character_changes"],
        new_facts_clues=extracted["new_facts_clues"],
        unresolved_hooks=extracted["unresolved_hooks"],
        end_state=extracted["end_state"],
    )

    # ---------- 2. story_state 三列快照（一作品一份，重跑覆盖） ----------
    await story_state_repo.upsert_story_state(
        session,
        user_id=user_id,
        project_id=project_id,
        protagonist_state=extracted["protagonist_state"],
        world_rules_state=extracted["world_rules_state"],
        current_stage=extracted["current_stage"],
    )

    # ---------- 3. story_thread 三类操作（新埋 / 回收 / 再提） ----------
    # 3a. 新埋伏笔：同内容已存在 open thread → 仅更新 last_touched（防重，B2）。
    for thread_input in extracted["new_threads"]:
        # E4 patch：类型防御——LLM 可能产 `"new_threads": ["不是 dict"]`（字符串列表），
        # `thread_input.get("content")` 会抛 AttributeError；跳过非 dict 项并记 warning。
        if not isinstance(thread_input, dict):
            logger.warning(
                "chapter-commit 新埋伏笔跳过（thread_input 非 dict）：project=%s "
                "chapter=%s type=%s",
                project_id,
                chapter_number,
                type(thread_input).__name__,
            )
            continue
        content = (thread_input.get("content") or "").strip()
        if not content:
            continue
        # E5 patch：章号下界校验——LLM 可能产 0/负数/非 int；违反时回退 chapter_number 参数。
        introduced = thread_input.get("introduced_chapter_number")
        if not isinstance(introduced, int) or introduced < 1:
            logger.warning(
                "chapter-commit 新埋伏笔章号越界（回退本章章号）：project=%s "
                "chapter=%s introduced=%s",
                project_id,
                chapter_number,
                introduced,
            )
            introduced = chapter_number
        thread, created = await story_thread_repo.upsert_new_thread(
            session,
            user_id=user_id,
            project_id=project_id,
            content=content,
            chapter_number=introduced,
        )
        if created:
            logger.info(
                "chapter-commit 新埋伏笔：project=%s chapter=%s thread_id=%s",
                project_id,
                chapter_number,
                thread.id,
            )

    # 3b. 回收伏笔：按内容匹配既有 open thread → UPDATE resolved；章号倒挂跳过（E5）。
    for thread_input in extracted["resolved_threads"]:
        if not isinstance(thread_input, dict):
            logger.warning(
                "chapter-commit 回收伏笔跳过（thread_input 非 dict）：project=%s "
                "chapter=%s type=%s",
                project_id,
                chapter_number,
                type(thread_input).__name__,
            )
            continue
        content = (thread_input.get("content") or "").strip()
        if not content:
            continue
        resolved = thread_input.get("resolved_chapter_number")
        if not isinstance(resolved, int) or resolved < 1:
            logger.warning(
                "chapter-commit 回收伏笔章号越界（回退本章章号）：project=%s "
                "chapter=%s resolved=%s",
                project_id,
                chapter_number,
                resolved,
            )
            resolved = chapter_number
        thread = await story_thread_repo.resolve_thread_by_content(
            session,
            user_id=user_id,
            project_id=project_id,
            content=content,
            resolved_chapter_number=resolved,
        )
        if thread is not None:
            logger.info(
                "chapter-commit 回收伏笔：project=%s chapter=%s thread_id=%s",
                project_id,
                chapter_number,
                thread.id,
            )

    # 3c. 再提伏笔：按内容匹配既有 open thread → UPDATE last_touched；章号倒退跳过（E6）。
    for thread_input in extracted["touched_threads"]:
        if not isinstance(thread_input, dict):
            logger.warning(
                "chapter-commit 再提伏笔跳过（thread_input 非 dict）：project=%s "
                "chapter=%s type=%s",
                project_id,
                chapter_number,
                type(thread_input).__name__,
            )
            continue
        content = (thread_input.get("content") or "").strip()
        if not content:
            continue
        last_touched = thread_input.get("last_touched_chapter_number")
        if not isinstance(last_touched, int) or last_touched < 1:
            logger.warning(
                "chapter-commit 再提伏笔章号越界（回退本章章号）：project=%s "
                "chapter=%s last_touched=%s",
                project_id,
                chapter_number,
                last_touched,
            )
            last_touched = chapter_number
        thread = await story_thread_repo.touch_thread_by_content(
            session,
            user_id=user_id,
            project_id=project_id,
            content=content,
            last_touched_chapter_number=last_touched,
        )
        if thread is not None:
            logger.info(
                "chapter-commit 再提伏笔：project=%s chapter=%s thread_id=%s",
                project_id,
                chapter_number,
                thread.id,
            )
