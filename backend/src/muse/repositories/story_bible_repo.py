"""故事设定域 DAO：story_bible 的读取、style_profile upsert（3.2）、候选卡读写（3.4）。

延续 project_repo/story_clue_repo 约定：repo 只 flush/查询，事务边界（commit/rollback）归
service。所有查询显式绑定 user_id 租户守卫（NFR3）——不提供任何绕过 user_id 的全表查询入口。

方法分层：
- get_by_project / upsert_style_profile（3.2）：文风锚点落 style_profile 一列。
- upsert_profile_card / get_pending_by_project / update_card_fields（3.4）：候选卡的凝练落库、
  待确认态恢复、字段直接编辑。
- confirm_pending_card / delete_pending_card（3.5）：确认（pending→confirmed 只读圣经）、
  回到探索丢弃（删 pending 行）。均只作用 status='pending' 行——confirmed 圣经不被误改/误删。
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from muse.models.story_bible import StoryBible

# 候选卡的 12 内容字段列名（主干 7 + 特化 4 + style_profile）——upsert 落库 / 直接编辑白名单
# 的单一事实源。与 StoryProfileCard 契约、story_settle_agent._LLM_FIELDS 对齐（勿漂移）。
# status/revision/changed_fields 是状态位、不在内容字段白名单（防直接编辑越权改状态/版本号）。
PROFILE_CONTENT_FIELDS: tuple[str, ...] = (
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
)


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


async def upsert_profile_card(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    card: dict[str, str | None],
    status: str,
    revision: int,
    changed_fields: list[str] | None,
) -> StoryBible:
    """get-or-create 落库候选卡（Story 3.4 AC1）：写 12 内容字段 + status/revision/changed_fields。

    - 已存在（3.2 半成品行 / 上一版候选卡）：更新 12 内容字段 + 状态位。**复用同行**——
      settle 凝练/反馈升版本都在 (user_id, project_id) 的唯一行上演进，不重复 insert。
    - 不存在：新建行（主干缺料靠 server_default="" 或本函数显式写空串、特化 None）。
    - `card` 只取 PROFILE_CONTENT_FIELDS 白名单键（防混入 status/revision 等状态位）；缺失的
      主干字段落空串（对齐 server_default 语义）、缺失特化字段落 None。
    - style_profile：settle 时 card 里已带 3.2 既有值（幂等写回同值、不覆盖为 None）。

    **不 commit**（事务边界归 service）。竞态兜底（首次并发 insert 撞唯一约束）由 service 处理
    （照 style_anchor_agent.extract_and_anchor_style 先例）。flush 后 refresh 回填时间戳
    （避免 MissingGreenlet，同 upsert_style_profile）。
    """
    bible = await get_by_project(session, user_id=user_id, project_id=project_id)
    if bible is None:
        bible = StoryBible(user_id=user_id, project_id=project_id)
        session.add(bible)
    for field in PROFILE_CONTENT_FIELDS:
        if field in card:
            setattr(bible, field, card[field])
    bible.status = status
    bible.revision = revision
    bible.changed_fields = changed_fields
    await session.flush()
    await session.refresh(bible)
    return bible


async def get_pending_by_project(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
) -> StoryBible | None:
    """取本作品的待确认候选卡（status='pending'，Story 3.4 AC6 恢复）。

    where 带 user_id+project_id+status（租户守卫二义合一 + 只收 pending）：无行 / 行已 confirmed
    → None（调用方按「无待确认卡」处理，非错误）。确认后（3.5 翻 confirmed）本查询自然返 None，
    表达「待确认态已清除」（AC6：确认后 GET pending 返回无待确认卡）。
    """
    stmt = select(StoryBible).where(
        StoryBible.user_id == user_id,
        StoryBible.project_id == project_id,
        StoryBible.status == "pending",
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def update_card_fields(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    fields: dict[str, str],
) -> StoryBible | None:
    """直接编辑候选卡字段值（Story 3.4 AC2）：仅改传入字段、revision 不变、清 changed_fields。

    - 仅作用于 status='pending' 行（confirmed 只读圣经不可直接编辑）：无 pending 行 → None
      （调用方转 404），confirmed 行也不匹配（get_pending_by_project 只取 pending）。
    - 只写 PROFILE_CONTENT_FIELDS 白名单键（防越权改 status/revision/changed_fields）；白名单外
      的键静默忽略（不报错，router schema 已用固定字段名 model 拦，此为 repo 侧二次防御）。
    - revision **不变**（直接编辑非「Agent 升版本」，受控决策 3）；changed_fields 清空（None）
      ——那是「Agent 改了哪些」的语义（AC4），用户手改不标高亮。

    **不 commit**（事务边界归 service）。flush 后 refresh 回填时间戳（避免 MissingGreenlet）。
    """
    bible = await get_pending_by_project(
        session, user_id=user_id, project_id=project_id
    )
    if bible is None:
        return None
    for field, value in fields.items():
        if field in PROFILE_CONTENT_FIELDS:
            setattr(bible, field, value)
    bible.changed_fields = None
    await session.flush()
    await session.refresh(bible)
    return bible


async def confirm_pending_card(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
) -> StoryBible | None:
    """确认待确认候选卡为只读设定圣经（Story 3.5 AC1）：pending 行 status→'confirmed'。

    - 仅作用 status='pending' 行（get_pending_by_project 过滤）：无 pending 行 → None
      （调用方转 404 no_pending_card——不能确认不存在的卡；已 confirmed 再确认也返 None）。
    - **只翻 status**：12 内容字段 / revision / style_profile / changed_fields 全不动——确认是
      「冻结当前 pending 卡为只读」、非重写内容（pending→confirmed 同行状态流转，不产生第二行、
      不拷贝，零竞态）。冻结后编辑/反馈端点（update_card_fields/revise）因只认 pending 行天然失效，
      confirmed 圣经由此只读（Story 3.5 AC2）。

    **不 commit**（事务边界归 service——确认与 project.phase 推进须在同一事务，见
    story_settle_agent.confirm_profile_card）。flush 后 refresh 回填 updated_at（避免
    MissingGreenlet，同 update_card_fields）。
    """
    bible = await get_pending_by_project(
        session, user_id=user_id, project_id=project_id
    )
    if bible is None:
        return None
    bible.status = "confirmed"
    await session.flush()
    await session.refresh(bible)
    return bible


async def delete_pending_card(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
) -> bool:
    """删除待确认候选卡（Story 3.5 AC3「回到探索页面」丢弃）：删 status='pending' 行。

    - 仅删 status='pending' 行（get_pending_by_project 过滤）：**confirmed 只读圣经绝不被误删**
      （不匹配 pending where）、draft 半成品行（只锚文风未 settle）也不在丢弃范围（只有 pending
      才是「当前待确认设定」）。删后用户可重新探索/整理再出新卡（settle get-or-create 新行）。
    - 返 True=删了一张 pending 卡；返 False=无 pending 卡可删（调用方按幂等处理，回探索仍成立）。

    **不 commit**（事务边界归 service，延续 project_repo.delete_project 只 delete 约定）。
    """
    bible = await get_pending_by_project(
        session, user_id=user_id, project_id=project_id
    )
    if bible is None:
        return False
    await session.delete(bible)
    await session.flush()
    return True
