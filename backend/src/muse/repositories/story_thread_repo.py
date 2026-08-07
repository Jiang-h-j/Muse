"""归档域 DAO：story_thread（未回收伏笔/线索）的租户守卫读法 + 写路径（Story 5.1 读 / 5.2 写）。

延续 story_bible_repo / chapter_repo 约定：repo 只 flush/查询，事务边界（commit/
rollback）归 service。所有查询显式绑定 user_id 租户守卫（NFR3）——不提供任何
绕过 user_id 的全表查询入口。

**方法分层**：
- `list_open_by_project`（5.1）：按 (user_id, project_id) 列出 status='open' 的全部
  thread，按 last_touched_chapter_number 降序——5.6 RAG「N 章未回收伏笔」召回与
  5.3 归档页活跃度排序的主读法。
- `upsert_new_thread`（5.2）：新增 open thread；同内容已存在 open thread → 仅更新
  `last_touched_chapter_number` 为新值（取 max，单调不减防线），不新建行——防
  data-agent 重跑/断点续跑产生重复 thread（defer 台账 B2）。
- `resolve_thread_by_content`（5.2）：按内容匹配既有 open thread → UPDATE
  status='resolved' + resolved_chapter_number + last_touched_chapter_number；
  **显式校验 `resolved_chapter_number >= introduced_chapter_number`**（defer 台账
  E5 大小约束），违反时跳过 + `logger.warning` 不阻断投影。
- `touch_thread_by_content`（5.2）：按内容匹配既有 open thread → UPDATE
  `last_touched_chapter_number`；**显式校验单调不减**（defer 台账 E6），
  `new_value <= old_value` 时跳过 + `logger.warning`。

**写路径约定（5.2 新增）**：
- 不 commit（commit 边界归 `chapter_projection_service.chapter_commit` 统一事务）。
- status 硬编码为 'open' / 'resolved' 字面量（defer 台账 P3+E4 白名单防线：repo 层
  不开放 status 入参，service 无法写入非法值；'abandoned' 留 V2 手动放弃路径）。
- 内容匹配 V1 用 `strip().lower()` 精确匹配（受控决策 5）——LLM 产「程野决定离开」
  vs「程野选择了离开」会被当两条不同 thread；语义级去重归 5.6 RAG 召回时统一处理。
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from muse.models.story_thread import StoryThread

logger = logging.getLogger("muse")


def _normalize_content_for_match(content: str) -> str:
    """内容匹配归一化：strip + lower——V1 精确匹配的「同内容」判据（受控决策 5）。

    中文内容 lower() 不改变字符（无大小写），但对夹杂的英文/数字/标点有效；
    strip() 去掉首尾空白——防止 LLM 在重跑时产「同内容但首尾空格/大小写漂移」
    被当两条 thread（defer 台账 B2 防线的最小语义单位）。
    """
    return content.strip().lower()


async def list_open_by_project(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    limit: int = 0,
) -> list[StoryThread]:
    """列出本作品全部 `status='open'` 的 thread，按 last_touched_chapter_number 降序。

    user_id + project_id + status 三 cond 同 where 一次过滤（同 story_bible_repo.
    get_pending_by_project 先例）：跨租户/已 resolved / 已 abandoned 的 thread 都
    被滤掉——返回空列表表达「无可召回伏笔」（非错误）。降序意味最近活跃的 thread
    在前，5.6 RAG 召回按需截断、5.3 归档页按活跃度排序展示。

    limit=0 时返回全部 open threads（默认无上限）；limit>0 时取前 limit 条（SQL
    层截断——Story 5.6 写前上下文注入 10 条上限）。
    """
    stmt = (
        select(StoryThread)
        .where(
            StoryThread.user_id == user_id,
            StoryThread.project_id == project_id,
            StoryThread.status == "open",
        )
        .order_by(StoryThread.last_touched_chapter_number.desc())
    )
    if limit > 0:
        stmt = stmt.limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _find_open_thread_by_content(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    content: str,
) -> StoryThread | None:
    """按归一化内容匹配既有 open thread——三表写路径的内部 helper。

    返回第一个匹配的 open thread（同内容 open thread 理论至多一条，upsert_new_thread
    的防重防线保证；若历史脏数据存在多条，取 last_touched 最新的一条）。不匹配返 None。
    """
    normalized = _normalize_content_for_match(content)
    open_threads = await list_open_by_project(
        session, user_id=user_id, project_id=project_id
    )
    for thread in open_threads:
        if _normalize_content_for_match(thread.content) == normalized:
            return thread
    return None


async def upsert_new_thread(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    content: str,
    chapter_number: int,
) -> tuple[StoryThread, bool]:
    """新增 open thread（Story 5.2 chapter-commit 投影的落点）；防重——同内容已存在
    open thread → 仅更新 `last_touched_chapter_number` 为新值（取 max，单调不减防线），
    不新建行（defer 台账 B2）。

    - **新建**：status='open'、introduced_chapter_number=last_touched_chapter_number=
      chapter_number；返回 (thread, True)（True=本次新建）。
    - **重跑/断点续跑命中同内容 open thread**：仅当 `chapter_number > thread.
      last_touched_chapter_number` 时更新 last_touched（取 max）；返回 (thread, False)
      （False=未新建、可能更新了 last_touched）。

    status 硬编码 'open'（defer 台账 P3+E4 白名单防线——repo 不开放 status 入参）。
    不 commit（事务边界归 chapter_commit）。
    """
    existing = await _find_open_thread_by_content(
        session,
        user_id=user_id,
        project_id=project_id,
        content=content,
    )
    if existing is not None:
        # 同内容 open thread 已存在——只更新 last_touched（取 max，单调不减防线 E6）。
        if chapter_number > existing.last_touched_chapter_number:
            existing.last_touched_chapter_number = chapter_number
            await session.flush()
            await session.refresh(existing)
        return existing, False

    # 新建：status 硬编码 'open'、introduced=last_touched=chapter_number。
    thread = StoryThread(
        user_id=user_id,
        project_id=project_id,
        content=content,
        status="open",
        introduced_chapter_number=chapter_number,
        last_touched_chapter_number=chapter_number,
    )
    session.add(thread)
    await session.flush()
    await session.refresh(thread)
    return thread, True


async def resolve_thread_by_content(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    content: str,
    resolved_chapter_number: int,
) -> StoryThread | None:
    """按内容匹配既有 open thread → UPDATE status='resolved' + resolved_chapter_number
    + last_touched_chapter_number=resolved_chapter_number（Story 5.2 chapter-commit
    投影的「伏笔回收」落点）。

    **显式校验**：
    - `resolved_chapter_number >= introduced_chapter_number`（defer 台账 E5 大小约束），
      违反时跳过更新 + `logger.warning`（不阻断投影——LLM 产倒挂章号是 data-agent 提取
      噪声，投影整体不该为此回滚）。
    - 无匹配 open thread → 返回 None（调用方按「无需回收」处理，非错误）。

    status 硬编码 'resolved'（defer 台账 P3+E4 白名单防线）。不 commit。
    """
    thread = await _find_open_thread_by_content(
        session,
        user_id=user_id,
        project_id=project_id,
        content=content,
    )
    if thread is None:
        return None

    if resolved_chapter_number < thread.introduced_chapter_number:
        logger.warning(
            "resolve_thread 章号倒挂（跳过更新）：project=%s thread_id=%s "
            "introduced=%s resolved=%s",
            project_id,
            thread.id,
            thread.introduced_chapter_number,
            resolved_chapter_number,
        )
        return None

    thread.status = "resolved"
    thread.resolved_chapter_number = resolved_chapter_number
    thread.last_touched_chapter_number = resolved_chapter_number
    await session.flush()
    await session.refresh(thread)
    return thread


async def touch_thread_by_content(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    content: str,
    last_touched_chapter_number: int,
) -> StoryThread | None:
    """按内容匹配既有 open thread → UPDATE `last_touched_chapter_number`（Story 5.2
    chapter-commit 投影的「伏笔再提」落点）。

    **显式校验单调不减**（defer 台账 E6）：`last_touched_chapter_number <= thread.
    last_touched_chapter_number` 时跳过更新 + `logger.warning`（不阻断投影——LLM 产
    倒退章号是提取噪声；防御 ARQ 重试/断点续跑把 last_touched 回写为更旧章号导致
    RAG 召回排序优先级错降）。

    无匹配 open thread → 返回 None（调用方按「无需更新」处理，非错误）。不 commit。
    """
    thread = await _find_open_thread_by_content(
        session,
        user_id=user_id,
        project_id=project_id,
        content=content,
    )
    if thread is None:
        return None

    if last_touched_chapter_number <= thread.last_touched_chapter_number:
        logger.warning(
            "touch_thread 章号倒退（跳过更新）：project=%s thread_id=%s "
            "old_last_touched=%s new_last_touched=%s",
            project_id,
            thread.id,
            thread.last_touched_chapter_number,
            last_touched_chapter_number,
        )
        return None

    thread.last_touched_chapter_number = last_touched_chapter_number
    await session.flush()
    await session.refresh(thread)
    return thread
