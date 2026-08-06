"""归档域 DAO：story_state（主角状态/世界规则/当前阶段快照）的租户守卫读法 + 写路径
（Story 5.1 读 / 5.2 写）。

延续 story_bible_repo / chapter_repo 约定：repo 只 flush/查询，事务边界（commit/
rollback）归 service。所有查询显式绑定 user_id 租户守卫（NFR3）——不提供任何
绕过 user_id 的全表查询入口。

**方法分层**：
- `get_by_project`（5.1）：按 (user_id, project_id) 读当前快照，二义合一。
- `upsert_story_state`（5.2）：按 (user_id, project_id) 幂等键 get-or-create 三列
  快照，重跑覆盖同行——是 5.2 chapter-commit 单事务投影的落点。

**写路径约定（5.2 新增）**：
- 不 commit（commit 边界归 `chapter_projection_service.chapter_commit` 统一事务）。
- 竞态兜底由 service 层 rollback → 整事务重试。
- flush + refresh 回填 id/时间戳（避免 MissingGreenlet）。
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from muse.models.story_state import StoryState


async def get_by_project(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
) -> StoryState | None:
    """按 (user_id, project_id) 一步取本作品的故事状态快照（二义合一）。

    user_id 与 project_id 写在同一 where 里一次过滤（同 story_bible_repo.
    get_by_project 先例）：取不到即 None——「未写任何章节、无快照」与「不属于我」
    二义合一，调用方（service）按需处理（写前上下文注入空块 / 返回归档空态）。
    对应 story_state 的 (user_id, project_id) 复合唯一约束，至多命中一行。
    """
    stmt = select(StoryState).where(
        StoryState.user_id == user_id,
        StoryState.project_id == project_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def upsert_story_state(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    protagonist_state: str,
    world_rules_state: str,
    current_stage: str,
) -> StoryState:
    """get-or-create 落库故事状态当前快照（Story 5.2 chapter-commit 投影的落点）。

    - 已存在：**覆盖三列快照**——「当前快照」语义上唯一，UPSERT 同行 UPDATE
      （(user_id, project_id) 复合唯一是幂等键，同 story_bible 先例）；重跑/断点
      续跑复用产物再次投影不产生第二行。
    - 不存在：新建行。

    三列全部必填但允许空串（对齐模型 `Text NOT NULL server_default=""` ——LLM 某列
    产空也能落库，由 service 上游空产守卫挡空产）。

    **不 commit**（事务边界归 `chapter_projection_service.chapter_commit`）。竞态
    兜底由 service 层 rollback → 整事务重试。flush 后 refresh 回填 id/时间戳。
    """
    state = await get_by_project(session, user_id=user_id, project_id=project_id)
    if state is None:
        state = StoryState(
            user_id=user_id,
            project_id=project_id,
            protagonist_state=protagonist_state,
            world_rules_state=world_rules_state,
            current_stage=current_stage,
        )
        session.add(state)
    else:
        state.protagonist_state = protagonist_state
        state.world_rules_state = world_rules_state
        state.current_stage = current_stage
    await session.flush()
    await session.refresh(state)
    return state
