"""故事设定域 DAO：story_bible 的读取与 style_profile upsert（Story 3.2）。

延续 project_repo/story_clue_repo 约定：repo 只 flush/查询，事务边界（commit/rollback）归
service。所有查询显式绑定 user_id 租户守卫（NFR3）——不提供任何绕过 user_id 的全表查询入口。

**本 story 只需两个方法**（文风锚点抽取落 style_profile 一列）：get_by_project 与
upsert_style_profile。设定候选卡的完整读写（3.3 生成、3.4 编辑升版本、3.5 确认）在后续
story 按需扩本 repo，本 story 不提前写 revision/status 或多字段写入逻辑（边界见 story Dev
Notes 受控决策 1）。
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from muse.models.story_bible import StoryBible


async def get_by_project(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
) -> StoryBible | None:
    """按 (user_id, project_id) 一步取本作品的设定圣经行（二义合一，仿 get_owned_project）。

    user_id 与 project_id 写在同一 where 里一次过滤（陷阱①）：取不到即 None——「设定圣经不
    存在」与「不属于我」二义合一，调用方（service）统一转同一 404，不泄露作品存在性（NFR3）。
    对应 story_bible 的 (user_id, project_id) 复合唯一约束，至多命中一行。
    """
    stmt = select(StoryBible).where(
        StoryBible.user_id == user_id,
        StoryBible.project_id == project_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def upsert_style_profile(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    style_profile: str,
) -> StoryBible:
    """get-or-create 写入 style_profile 列（Story 3.2 AC3）：存在则更新、不存在则新建行。

    - 已存在：更新该行 style_profile，其余 11 字段保持原值（可能是 3.3 已填的候选卡内容，
      也可能仍是空态）——文风抽取只碰 style_profile 一列，不覆盖设定卡内容（正交，见 story
      Dev Notes 受控决策 1）。
    - 不存在：新建一行，主干 7 列靠 server_default="" 自动填空串、题材特化 4 列留 NULL、只
      显式写 style_profile。此时是「仅有 style_profile 的半成品行」——3.3/3.5 后续补齐其余
      字段（story 待确认项 2 已登记该中间态）。

    **不 commit**（事务边界归 service，与既有 repo 约定一致）。flush 后 refresh 回填
    created_at/updated_at（TimestampMixin 的 server_default/onupdate 走 DB 端 func.now()，
    flush 后属性被标记 expired，若下游同步序列化触发懒加载会抛 MissingGreenlet——仿
    story_clue_repo.update_clue 的 refresh 处理）。
    """
    bible = await get_by_project(session, user_id=user_id, project_id=project_id)
    if bible is None:
        bible = StoryBible(
            user_id=user_id,
            project_id=project_id,
            style_profile=style_profile,
        )
        session.add(bible)
    else:
        bible.style_profile = style_profile
    await session.flush()
    await session.refresh(bible)
    return bible
