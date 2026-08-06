"""阶段规划生成 service（Story 4.3，FR17/NFR4）：读 confirmed 设定圣经 → LLM 产出首个阶段
规划（阶段目标 + 该阶段各章骨架 title/brief）。

**与 4.2 四段流水线的关系**：4.2 写**整章正文**（context→drafter→reviewer→polisher，产出
整章文本）；本模块生成的是**更高层的阶段规划**（阶段目标 + 各章 title/brief 骨架，一次较轻的
LLM 调用），是 4.4 正文生成的**上游纲领**。二者不同产物、不同粒度——本模块不复用四段流水线，
只借其 service/记账/防御解析范式（同 story_settle_agent / orchestration.steps）。

**幕后异步**（AC1/AC6）：本 service 由 worker 的 `plan_first_stage` 任务在后台调用（confirm
成功后触发），confirm 端点/事务不被本 LLM 调用阻塞——用户体感直接进第一章（FR17）。

范式（照 story_settle_agent.settle_into_profile / orchestration.steps）：
- 独立 `async_session_maker()` 自管 session（陷阱⑩：调 provider 走 MeteredProvider 记账，
  finally 兜底记账须落在存活 session 上，不复用 worker ctx 的 session）。
- 租户守卫 `get_owned_project → None 抛二义合一 404`（NFR3）。
- 读 `status='confirmed'` bible（复用 story_bible_repo.get_confirmed_by_project）；无 →
  抛 bible_not_confirmed 400（复用 4.2 steps.py 语义，理论上 confirm 后必有，防御用）。
- `check_quota` 在 provider 调用之前（托管触顶抛 429）。
- `get_provider_for_user(session, uid, project_id=pid)` 拿 MeteredProvider 包裹的 provider
  （AC7：记账埋点在 Provider 层，绝不自建 DeepSeekProvider）。
- 非流式 `.chat()`（settle 范式）；**思考档 pro**（结构化纲领生成，避免快档把内容放进
  reasoning_content 致空产，见 4.2 Debug Log / story_settle_agent 陷阱⑥）。
- LLM 输出防御解析（逐行「标签：内容」+ 正则聚合章节）；空产（无阶段目标或无有效章）抛
  502 generate_failed。
- **落库持久化**（重进不重生成，AC2）：upsert 到 stage_plan 表，竞态兜底 rollback→UPDATE。

分层（architecture.md router→service→provider）：经 LLMProvider 抽象调 LLM（禁直调 openai，
陷阱①），Provider 层自动记账（AR14）。
"""

import logging
import re
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from muse.core.db import async_session_maker
from muse.core.errors import ErrorEnvelope
from muse.core.settings import get_settings
from muse.models.stage_plan import StagePlan
from muse.providers.base import ChatResult, Message
from muse.providers.factory import get_provider_for_user
from muse.repositories import project_repo, stage_plan_repo, story_bible_repo
from muse.services import exploration_service, usage_service

logger = logging.getLogger(__name__)

# 阶段规划=阶段目标（一段）+ N 章骨架（每章 title+brief）。产出比 12 字段凝练略重、比整章
# 正文轻；思考档是推理模型（reasoning_content 先吃预算，story_settle_agent.py:55-58 踩坑），
# 故 max_tokens 留足避免章骨架被挤空。骨架体量不大，3000 足够容纳阶段目标 + 若干章。
_MAX_TOKENS = 3000

# 首阶段编号（plan_first_stage 用）；plan_next_stage 用「上一阶段 + 1」，不写死本常量（Story 4.7）。
_FIRST_STAGE = 1

# 12 字段的 key ↔ 中文标签（与 story_bible 列名 / orchestration.steps._BIBLE_FIELDS 对齐）。
# 渲染 confirmed 设定为 prompt 的「设定」段——有值的字段才输出行。
_BIBLE_FIELDS: list[tuple[str, str]] = [
    ("genre", "题材"),
    ("core_appeal", "核心吸引力"),
    ("protagonist", "主角"),
    ("main_conflict", "主要冲突"),
    ("world_rules", "关键世界规则"),
    ("overall_tone", "整体气质"),
    ("opening_hook", "开篇钩子"),
    ("power_system", "力量体系"),
    ("golden_finger", "金手指"),
    ("romance_line", "感情线"),
    ("faction_landscape", "势力格局"),
]


def _generate_failed() -> ErrorEnvelope:
    """LLM 完全跑偏、产出为空（空产 → 502，承 story_settle_agent / steps 空产守卫先例）。"""
    return ErrorEnvelope(
        code="generate_failed",
        message="生成失败，请稍后重试。",
        http_status=502,
    )


def _format_bible_for_prompt(bible: object) -> str:
    """把 confirmed story_bible 的 12 字段渲染成 prompt 里的「设定」段（有值的字段才输出行）。"""
    lines: list[str] = []
    for key, label in _BIBLE_FIELDS:
        value = (getattr(bible, key, None) or "").strip()
        if value:
            lines.append(f"{label}：{value}")
    return "\n".join(lines)


def _build_plan_messages(bible: object) -> list[Message]:
    """组装阶段规划消息：注入 confirmed 设定 + style_profile，要求 LLM 产出首阶段规划。

    要求**只规划首个阶段**（FR22 循环归 4.7），章数**由 LLM 按剧情定、不写死上限**（NFR4，
    epics.md:935）。固定「标签：内容」逐行输出格式，便于防御解析（同 settle 范式）。
    """
    setting_block = _format_bible_for_prompt(bible)
    style_profile = (getattr(bible, "style_profile", None) or "").strip()
    style_block = (
        f"【文风锚点（规划时纳入考量）】\n{style_profile}"
        if style_profile
        else "【文风锚点】\n（未锚定文风，按题材气质自然规划。）"
    )
    system = """你在帮一位读者规划他的网文的第一个阶段。

一部长篇网文由若干「阶段」构成（每个阶段是一段相对完整的剧情弧）。现在只需要你规划**第一个\
阶段**：给出这个阶段的总体目标，以及这个阶段里各章要写什么（每章一个标题 + 一句话简介）。

严格按下面的格式逐行输出，标签必须一字不差：

阶段目标：（这个阶段整体要达成什么——推进到什么剧情节点、让读者获得什么体验，两三句话）
第1章标题：（第一章的标题）
第1章简介：（第一章大致写什么，一两句话）
第2章标题：（……）
第2章简介：（……）
……以此类推

要求：
- 章数**由剧情需要决定**，不要凑数、也不要硬砍——第一个阶段该有几章就写几章。
- 每一章都要有「第N章标题：」和「第N章简介：」两行，章号从 1 连续递增。
- 紧扣故事设定与文风，开篇钩子要在前几章体现。
- 说人话、面向大众网文读者，不要文绉绉的书面腔、不要 AI 味的套话。
- 只输出上面这些「标签：内容」行，不要输出任何其他文字、不要 Markdown、不要引号包裹。"""
    user = f"【故事设定（唯一规划依据）】\n{setting_block}\n\n{style_block}"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _build_next_stage_messages(
    bible: object, prev_stage: StagePlan, direction: str | None
) -> list[Message]:
    """组装下一阶段规划消息（Story 4.7）：注入设定 + style_profile + 上一阶段目标 + 读者方向。

    与 `_build_plan_messages` 差异：① 承接**上一阶段目标**（让 LLM 接着往下规划、不重复已写内容）；
    ② 注入读者在阶段交界处填的**方向意愿**（direction）——非空则作为下一阶段走向参考，空则让 LLM
    按设定+前文自然推进，收尾声明则规划收束主线的收尾阶段。章数仍由剧情定、不设上限（NFR4）。
    """
    setting_block = _format_bible_for_prompt(bible)
    style_profile = (getattr(bible, "style_profile", None) or "").strip()
    style_block = (
        f"【文风锚点（规划时纳入考量）】\n{style_profile}"
        if style_profile
        else "【文风锚点】\n（未锚定文风，按题材气质自然规划。）"
    )
    prev_goal = (prev_stage.goal or "").strip()
    prev_block = (
        f"【上一阶段的目标（本阶段要接着往下推进，不要重复已经写过的内容）】\n{prev_goal}"
        if prev_goal
        else "【上一阶段】\n（无明确目标记录，按故事设定自然承接。）"
    )
    direction_text = (direction or "").strip()
    direction_block = (
        f"【读者对这一阶段的走向意愿（务必参考）】\n{direction_text}"
        if direction_text
        else "【读者的走向意愿】\n（读者选择「直接继续」，未给具体方向——请按故事设定与上一阶段"
        "自然推进到下一阶段。）"
    )
    system = """你在帮一位读者规划他的网文的**下一个**阶段。

一部长篇网文由若干「阶段」构成（每个阶段是一段相对完整的剧情弧）。上一个阶段已经写完，现在要\
规划**紧接着的下一个阶段**：给出这个阶段的总体目标，以及这个阶段里各章要写什么（每章一个标题 \
+ 一句话简介）。

严格按下面的格式逐行输出，标签必须一字不差：

阶段目标：（这个阶段整体要达成什么——承接上一阶段推进到什么剧情节点、让读者获得什么体验，两三句话）
第1章标题：（这一阶段第一章的标题）
第1章简介：（这一阶段第一章大致写什么，一两句话）
第2章标题：（……）
第2章简介：（……）
……以此类推

要求：
- 这一阶段的章号从 1 重新开始（每个阶段内部各章从 1 连续递增）。
- 章数**由剧情需要决定**，不要凑数、也不要硬砍——这个阶段该有几章就写几章。
- 每一章都要有「第N章标题：」和「第N章简介：」两行。
- 紧扣故事设定与文风，自然承接上一阶段、不要重复上一阶段已经写过的情节。
- 如果读者表达了想收尾/进入结局，就规划一个能收束主线、走向结局的阶段。
- 说人话、面向大众网文读者，不要文绉绉的书面腔、不要 AI 味的套话。
- 只输出上面这些「标签：内容」行，不要输出任何其他文字、不要 Markdown、不要引号包裹。"""
    user = (
        f"【故事设定（唯一规划依据）】\n{setting_block}\n\n"
        f"{style_block}\n\n{prev_block}\n\n{direction_block}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


# 标签前/内常见的 markdown/编号装饰（LLM 违背「不要 Markdown」时会加）：加粗/斜体符、
# 列表符、圈号编号。解析前对标签侧剥离，避免 `**阶段目标**：X` / `- 第1章标题：X` 命中不了
# 标签 → 好内容误判空产 502（承 story_settle_agent._normalize_label 加固思路）。
_LABEL_PREFIX_RE = re.compile(r"^[\s>*_\-•·]*(?:[0-9]+[.)、]|[①-⑫])?\s*")
# 章行 / 目标行的标签匹配（在 partition 冒号 + 归一化 label 后对 label 侧匹配）：
# `第N章标题` / `第N章简介` / `阶段目标`。N 为阿拉伯数字，「章」与「标题/简介」间容空格。
_CHAPTER_TITLE_RE = re.compile(r"^第\s*(\d+)\s*章\s*标题$")
_CHAPTER_BRIEF_RE = re.compile(r"^第\s*(\d+)\s*章\s*简介$")
_GOAL_LABEL = "阶段目标"


def _normalize_label(label: str) -> str:
    """归一化标签：剥离首部 markdown/编号装饰 + 尾部星号/空白，供精确匹配（防御解析加固）。"""
    label = _LABEL_PREFIX_RE.sub("", label)
    return label.strip().strip("*_").strip()


def _parse_plan_response(content: str) -> tuple[str, list[dict[str, str]]]:
    """解析阶段规划响应为 (阶段目标, [{title, brief}])（防御性，仿 _parse_settle_response）。

    逐行 partition 冒号（中英文皆容），label 侧归一化剥装饰后匹配：`阶段目标` → goal；
    `第N章标题` / `第N章简介` → 按章号 N 聚合成章骨架。只收命中模式的行、静默跳过畸形行
    （模型偏离格式不崩溃）。章按章号升序输出；**只保留有标题的章**（title 非空才算有效章，
    brief 缺则空串）——无标题的孤立简介行丢弃。
    """
    goal = ""
    # 章号 → {"title": ..., "brief": ...}，最后按章号排序展平。
    chapters: dict[int, dict[str, str]] = {}
    for raw in content.splitlines():
        line = raw.strip()
        if "：" not in line and ":" not in line:
            continue
        sep = "：" if "：" in line else ":"
        raw_label, _, value = line.partition(sep)
        label = _normalize_label(raw_label)
        value = value.strip()
        if label == _GOAL_LABEL:
            if value:
                goal = value
            continue
        title_match = _CHAPTER_TITLE_RE.match(label)
        if title_match and value:
            num = int(title_match.group(1))
            chapters.setdefault(num, {"title": "", "brief": ""})["title"] = value
            continue
        brief_match = _CHAPTER_BRIEF_RE.match(label)
        if brief_match:
            num = int(brief_match.group(1))
            chapters.setdefault(num, {"title": "", "brief": ""})["brief"] = value

    ordered = [
        {"title": chapters[num]["title"], "brief": chapters[num]["brief"]}
        for num in sorted(chapters)
        if chapters[num]["title"]  # 只保留有标题的章（孤立简介行丢弃）
    ]
    return goal, ordered


async def plan_first_stage(
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
) -> StagePlan:
    """读 confirmed 设定 → LLM 生成首个阶段规划 → 落库，返回 StagePlan 行（AC2/AC7）。

    **独立 session 自管**（陷阱⑩，同 settle_into_profile / steps 范式）。流程：
    1. 租户守卫（`get_owned_project` → None 抛 404 二义合一）。
    2. 读 confirmed 设定圣经（`get_confirmed_by_project`）；无 → 抛 bible_not_confirmed 400
       （复用 4.2 steps 语义，理论上 confirm 后必有，防御用）。
    3. 护栏 check_quota（provider 前，陷阱②）。托管触顶抛 429。
    4. 构造 MeteredProvider（禁自 new，陷阱①）→ 非流式生成（思考档 pro + 足量 max_tokens）。
    5. 防御解析（阶段目标 + 章骨架）；无目标或无有效章（模型跑偏）→ 抛 502 generate_failed。
    6. upsert 落库 stage_plan（首阶段=1，竞态兜底 rollback→UPDATE）→ 返回 StagePlan 行。

    返回 StagePlan（含 goal + chapters[{title, brief}]），供 worker 组装 SSE result（转
    camelCase）+ 前端渲染第一章侧栏。
    """
    settings = get_settings()
    async with async_session_maker() as session:
        # 1. 租户守卫（陷阱①）：独立 session 上重校验 project 归属。二义合一 404。
        project = await project_repo.get_owned_project(session, project_id, user_id)
        if project is None:
            raise exploration_service._exploration_not_found()

        # 2. 读 confirmed 设定圣经（Epic 4 唯一创作依据）。无 → 400 提示先确认设定（防御，
        #    confirm 成功后触发本任务，理论上必有 confirmed 行）。
        bible = await story_bible_repo.get_confirmed_by_project(
            session, user_id=user_id, project_id=project_id
        )
        if bible is None:
            raise _bible_not_confirmed()

        # 3. 护栏（provider 前，陷阱②）。托管触顶抛 429。
        await usage_service.check_quota(session, user_id)

        # 4. 构造带记账 Provider（MeteredProvider）→ 非流式生成（思考档 pro + 足量 max_tokens）。
        provider = await get_provider_for_user(session, user_id, project_id=project_id)
        result: ChatResult = await provider.chat(
            _build_plan_messages(bible),
            model=settings.deepseek_model_thinking,
            max_tokens=_MAX_TOKENS,
        )

        # 5. 防御解析 + 空产守卫：无阶段目标或无有效章（模型完全跑偏）→ 抛 502 generate_failed
        #    （承 story_settle_agent / steps 空产不落先例；空规划无意义，抛错让 worker 推 error）。
        goal, chapters = _parse_plan_response(result.content)
        if not goal or not chapters:
            raise _generate_failed()

        # 6. upsert 落库（首阶段=1）。竞态兜底：并发首建撞唯一约束 → rollback 重查转 UPDATE
        #    （照 story_settle_agent._persist_card_with_race_guard / pipeline 先例）。
        return await _persist_plan_with_race_guard(
            session,
            user_id=user_id,
            project_id=project_id,
            goal=goal,
            chapters=chapters,
        )


async def plan_next_stage(
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    direction: str | None = None,
) -> StagePlan:
    """读上一阶段 + confirmed 设定 → LLM 生成**下一个**阶段规划 → 落库（Story 4.7 AC5，FR22）。

    **仿 plan_first_stage**（本文件上文），差异：
    - 读**当前最新阶段**（`get_latest_stage`）作承接依据；无任何阶段规划 → 抛 502（防御，正常
      流程首阶段 4.3 已生成、service.trigger_next_stage_planning 已前置校验 no_stage_plan 400）。
    - prompt 用 `_build_next_stage_messages`（注入上一阶段目标 + 读者方向 direction）。
    - upsert stage_number = 上一阶段 + 1（不写死 _FIRST_STAGE，支持无限阶段循环 NFR4）。

    `direction` = 阶段交界处用户填的走向意愿（可空=直接继续 / 收尾声明）。独立 session 自管
    （陷阱⑩）。返回新阶段 StagePlan（含 goal + chapters + 新 stage_number），供 worker 组装 result。
    """
    settings = get_settings()
    async with async_session_maker() as session:
        # 1. 租户守卫（陷阱①）：独立 session 上重校验 project 归属。二义合一 404。
        project = await project_repo.get_owned_project(session, project_id, user_id)
        if project is None:
            raise exploration_service._exploration_not_found()

        # 2. 读 confirmed 设定圣经（Epic 4 唯一创作依据）。无 → 400（防御）。
        bible = await story_bible_repo.get_confirmed_by_project(
            session, user_id=user_id, project_id=project_id
        )
        if bible is None:
            raise _bible_not_confirmed()

        # 3. 读当前最新阶段作承接。无 → 502（防御；service 层已前置 no_stage_plan 400，
        #    此处独立 session 重查兜底，正常不会命中）。
        prev_stage = await stage_plan_repo.get_latest_stage(
            session, user_id=user_id, project_id=project_id
        )
        if prev_stage is None:
            raise _generate_failed()
        next_stage_number = prev_stage.stage_number + 1

        # 4. 护栏（provider 前，陷阱②）。托管触顶抛 429。
        await usage_service.check_quota(session, user_id)

        # 5. 构造带记账 Provider（MeteredProvider）→ 非流式生成（思考档 pro + 足量 max_tokens）。
        provider = await get_provider_for_user(session, user_id, project_id=project_id)
        result: ChatResult = await provider.chat(
            _build_next_stage_messages(bible, prev_stage, direction),
            model=settings.deepseek_model_thinking,
            max_tokens=_MAX_TOKENS,
        )

        # 6. 防御解析 + 空产守卫（无目标或无有效章 → 502，同 plan_first_stage）。
        goal, chapters = _parse_plan_response(result.content)
        if not goal or not chapters:
            raise _generate_failed()

        # 7. upsert 落库（stage_number = 上一阶段 + 1）。竞态兜底同 plan_first_stage。
        return await _persist_plan_with_race_guard(
            session,
            user_id=user_id,
            project_id=project_id,
            goal=goal,
            chapters=chapters,
            stage_number=next_stage_number,
        )


def _bible_not_confirmed() -> ErrorEnvelope:
    """设定圣经未确认（规划前置未满足 → 400，复用 4.2 steps.py:64 语义）。

    Epic 4 创作唯一依据是 confirmed 设定圣经；无 confirmed 行说明还没确认设定，不能生成阶段
    规划。本 service 由 confirm 成功后触发，理论上必有 confirmed 行——此判据为防御（防直接
    调用本编排 / confirm 后被撤销确认的极端）。
    """
    return ErrorEnvelope(
        code="bible_not_confirmed",
        message="请先确认故事设定，再开始创作章节。",
        http_status=400,
    )


async def _persist_plan_with_race_guard(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    goal: str,
    chapters: list[dict[str, str]],
    stage_number: int = _FIRST_STAGE,
) -> StagePlan:
    """upsert 阶段规划 + commit，带首次并发 INSERT 竞态兜底（照 pipeline / settle 先例）。

    首次落库（stage_plan 行尚不存在）并发两请求都走 INSERT，第二条 commit 撞
    uq_stage_plan_user_project_stage → IntegrityError：rollback 后重查转 UPDATE
    （last-write-wins），而非冒泡 500。已存在行走 UPDATE 无此冲突。stage_number 默认首阶段
    （plan_first_stage）；plan_next_stage 传下一阶段号（上一阶段 + 1）。
    """
    try:
        plan = await stage_plan_repo.upsert_stage_plan(
            session,
            user_id=user_id,
            project_id=project_id,
            goal=goal,
            chapters=chapters,
            stage_number=stage_number,
        )
        await session.commit()
    except IntegrityError:
        # 并发 plan 撞唯一键（双 tab / 后端未启用 _job_id 去重的旧逻辑残留 / admin 干预）：
        # rollback 后重 upsert 走 UPDATE，last-write-wins 静默覆盖先写者的 chapters。
        # **F4a review patch**：补 warning 留审计痕迹（用户双 tab 看到不同章骨架的依据）；
        # 正常入口由 chapter_service.trigger_next_stage_planning 用 _job_id 去重，本分支兜底。
        logger.warning(
            "stage_plan 并发落库，last-write-wins 覆盖：user=%s project=%s stage=%s",
            user_id,
            project_id,
            stage_number,
        )
        await session.rollback()
        plan = await stage_plan_repo.upsert_stage_plan(
            session,
            user_id=user_id,
            project_id=project_id,
            goal=goal,
            chapters=chapters,
            stage_number=stage_number,
        )
        await session.commit()
    return plan
