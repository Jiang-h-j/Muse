"""Story Settle Agent：把探索内容真实凝练成 12 字段故事设定候选卡（Story 3.3）。

承接 Epic 2 Story 2.5（引导收尾）/ 2.7（自由「整理为故事设定」）触发的 ARQ settle 任务——
2.5/2.7 打通了「触发→ARQ→worker→SSE」全链路但 step 2「凝练」是占位（受控决策 B）；本模块
把占位替换为**真实 LLM 12 字段凝练**（FR12，epics.md:715-717「接 Epic 2 Story 2.5/2.7 的
ARQ 任务」）：按会话 mode 取探索材料 → LLM 凝练 → 12 字段设定候选卡，经 worker 的 SSE
`result` 事件返回。

**与 explorer_agent / free_explorer_agent / style_anchor_agent 职责独立**：那三者服务探索域
（理解自述 / 自由对话+线索整理）与设定域文风抽取；本模块服务设定域的「探索→设定卡凝练」。
延续「按 Agent 职责拆 service」的既定项目模式（同 3.2 决策），新建独立文件（受控决策 2）。

**落库（Story 3.4 起，替代 3.3 的 emit-only）**：候选卡凝练完成后 upsert 到 story_bible 行
（status='pending', revision=1），供刷新恢复（3.4 AC6）——**这是 3.3 受控决策 1「emit-only」
向 3.4 的受控演进**（3.3 defer 给 3.4 的下游交接兑现，deferred-work.md:176）。同时仍返回候选卡
dict 给 worker 推 SSE result（即时弹卡）：settle 现在**既落库又推 SSE**（落库供恢复、SSE 供即时
可见）。复用 3.2 已建的半成品行（style_profile 幂等写回同值、不覆盖）。

反馈升版本（revise_profile_card，3.4 AC3）：把「当前候选卡 + 用户反馈」喂同一凝练 Agent 重生成、
revision 递增、算变化字段——同步 REST（非 ARQ），性质是一次性重凝练（受控决策 2）。

session 生命周期（陷阱⑩，同 free_explorer_agent.extract_clues / style_anchor_agent 范式）：
凝练调 provider（走 MeteredProvider 记账），MeteredProvider 的 finally 兜底记账须落在存活
session 上——故用独立 `async_session_maker()` 自管 session，**不复用 worker ctx 的 session**。
落库 upsert 的首次并发竞态（撞 uq_story_bible_user_id_project_id）照 style_anchor_agent 先例
rollback→重查转 UPDATE 兜底。

分层（architecture.md router→service→provider）：经 LLMProvider 抽象调 LLM（**禁直调
openai**，陷阱①），生成前过 check_quota 护栏（陷阱②，skeleton 期无护栏对象、护栏随本 story
真实凝练落地），Provider 层自动记账（AR14）。
"""

import re
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from muse.core.db import async_session_maker
from muse.core.errors import ErrorEnvelope
from muse.core.settings import get_settings
from muse.models.exploration_message import ExplorationMessage
from muse.models.story_bible import StoryBible
from muse.models.story_clue import StoryClue
from muse.providers.base import ChatResult, Message
from muse.providers.factory import get_provider_for_user
from muse.repositories import (
    exploration_repo,
    project_repo,
    story_bible_repo,
    story_clue_repo,
)
from muse.services import exploration_service, usage_service

# 12 字段凝练比五维文风 / 4 槙位线索输出更长（12 行「标签：内容」+ 每行内容更实），快档是
# 推理模型（reasoning_content 先吃预算，2.1 Debug Log 实测 / 陷阱⑥），故 max_tokens 比
# style_anchor 的 1024 更宽裕，留足避免主干/特化多字段被挤空。
_MAX_TOKENS = 2048

# 12 字段的 key（= story_bible 列名 = 候选卡 camelCase 转换前 snake_case）↔ 中文标签。
# 单一事实源：prompt 生成输出格式要求 + 防御性解析 + 候选卡组装三处共用（避免漂移）。
# 顺序 = 原型/epics 的 ①-⑫ 编号顺序（主干 7 → 特化 4 → 文风 1）。
# ⑫ style_profile **不在 LLM 凝练输出里**（读 3.2 既有值，见 settle_into_profile），故不进
# _LLM_FIELDS / prompt / 解析——只在候选卡组装时补上。
_BACKBONE_FIELDS: list[tuple[str, str]] = [
    ("genre", "题材"),
    ("core_appeal", "核心吸引力"),
    ("protagonist", "主角"),
    ("main_conflict", "主要冲突"),
    ("world_rules", "关键世界规则"),
    ("overall_tone", "整体气质"),
    ("opening_hook", "开篇钩子"),
]
_SPECIALIZED_FIELDS: list[tuple[str, str]] = [
    ("power_system", "力量体系"),
    ("golden_finger", "金手指"),
    ("romance_line", "感情线"),
    ("faction_landscape", "势力格局"),
]
# LLM 凝练输出的 11 字段（主干 7 + 特化 4，不含 ⑫ style_profile）。
_LLM_FIELDS: list[tuple[str, str]] = _BACKBONE_FIELDS + _SPECIALIZED_FIELDS
_BACKBONE_KEYS = {key for key, _ in _BACKBONE_FIELDS}


def _settle_empty() -> ErrorEnvelope:
    """探索材料为空、不足以凝练成设定（前置条件未满足 → 400）。

    与 `_exploration_not_found`(404) / `_require_project_mode`(409) / `_exploration_not_ready`
    (2.7 的 400 门禁) 语义正交：本 code 表达「探索内容为空、无料可凝」。guided 无上游门禁
    （前端保证收尾态触发）、free 有 2.7 的 ≥1 用户消息门禁——本判据仍独立防御，不依赖上游。
    """
    return ErrorEnvelope(
        code="settle_empty",
        message="探索内容还不足以整理成设定，请先多聊几句。",
        http_status=400,
    )


def _no_pending_card() -> ErrorEnvelope:
    """无待确认候选卡（反馈升版本 / 直接编辑的前置条件未满足 → 404）。

    「待确认卡不存在」是存在性语义（还没整理出卡、或已确认清了 pending 态），与
    `_exploration_not_found`(404) 同族——用 404 而非 400/409。反馈/编辑/恢复端点在无 pending
    行时统一抛此，不泄露作品存在性（NFR3，同二义合一精神）。
    """
    return ErrorEnvelope(
        code="no_pending_card",
        message="没有待确认的设定卡，请先整理探索内容。",
        http_status=404,
    )


async def _persist_card_with_race_guard(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    card: dict[str, str | None],
    status: str,
    revision: int,
    changed_fields: list[str] | None,
) -> StoryBible:
    """upsert 候选卡 + commit，带首次并发 INSERT 竞态兜底（照 style_anchor_agent 先例）。

    首次落库（bible 行尚不存在）并发两请求都走 INSERT，第二条 commit 撞
    uq_story_bible_user_id_project_id → IntegrityError：rollback 后重查转 UPDATE
    （last-write-wins），而非冒泡 500。已存在行走 UPDATE 无此冲突。
    """
    try:
        bible = await story_bible_repo.upsert_profile_card(
            session,
            user_id=user_id,
            project_id=project_id,
            card=card,
            status=status,
            revision=revision,
            changed_fields=changed_fields,
        )
        await session.commit()
    except IntegrityError:
        await session.rollback()
        bible = await story_bible_repo.upsert_profile_card(
            session,
            user_id=user_id,
            project_id=project_id,
            card=card,
            status=status,
            revision=revision,
            changed_fields=changed_fields,
        )
        await session.commit()
    return bible


def _settle_system_prompt() -> str:
    """凝练/重凝练共用的 system prompt（genre 驱动 + 固定 11 字段格式 + 去 AI 味）。

    settle（首次凝练）与 revise（反馈重凝练）共用同一份字段契约与口吻要求（单一事实源）——
    差异只在 user 消息（settle 喂探索材料、revise 喂当前卡+反馈）。⑫ style_profile 不在输出
    要求里（读 3.2 既有值，避免 LLM 覆盖真实抽取产物，受控决策 4）。
    """
    backbone_hint = "\n".join(label for _, label in _BACKBONE_FIELDS)
    specialized_hint = "\n".join(label for _, label in _SPECIALIZED_FIELDS)
    return f"""你在帮一位读者把他探索出来的零散念头，整理成一份结构化的网文故事设定。

读下面的探索材料（可能是引导问答、也可能是自由对话和线索），提炼成一份故事设定候选卡。\
为以下每一项各输出一行，严格用「标签：内容」的格式，标签必须和下面列出的一字不差。

先判定这个故事的**题材**，再据题材决定哪些特化项要填。

通用主干（所有题材都要给，即使材料没提也据已有信息合理凝练；实在无从判断就留空）：
{backbone_hint}

题材特化（**只填和题材匹配的项**，不匹配的项这一行整行不要输出）：
{specialized_hint}

每一项的含义：
- 题材：这是什么类型的网文（如都市、修仙、玄幻、系统爽文、言情、悬疑等）。
- 核心吸引力：一句话讲清这故事最抓人的卖点、读者能获得的核心爽点或体验。
- 主角：主角是谁——姓名、他最想要的东西（核心欲望）、以及他致命的缺陷。
- 主要冲突：故事的核心矛盾；若能提炼出反派，点出反派与主角共享欲望却走了反路（反派镜像）。
- 关键世界规则：故事世界的规模与最重要的硬约束（什么能做、什么绝不能做）。
- 整体气质：整个故事的基调气氛（如热血、轻松、压抑、悬疑）。
- 开篇钩子：第一章用什么抓住读者、让人想追下去。
- 力量体系：修仙/玄幻类的境界链、能力等级体系。
- 金手指：系统爽文类主角开挂的核心外挂/系统。
- 感情线：言情类的情感关系走向。
- 势力格局：设定重的题材里各方势力的分布与关系。

要求：
- 只根据材料里实际读到的内容凝练，不要杜撰材料里完全没有的关键设定。
- 说人话、面向大众网文读者，不要文绉绉的书面腔、不要 AI 味的套话。
- 通用主干某项实在没有任何依据可凝练，就输出「标签：」（冒号后留空），不要硬编。
- 特化项只输出题材匹配的行，不匹配的行整行省略。
- 只输出这些「标签：内容」行，不要输出任何其他文字、不要编号、不要 Markdown、不要引号包裹。"""


def _build_settle_messages(material_text: str) -> list[Message]:
    """组装凝练消息：共用 system prompt + 携探索材料的 user 消息。"""
    return [
        {"role": "system", "content": _settle_system_prompt()},
        {"role": "user", "content": f"探索材料：\n{material_text}"},
    ]


def _format_card_for_prompt(card: dict[str, str | None]) -> str:
    """把当前候选卡渲染成「标签：内容」多行文本，喂给 revise 的 user 消息（供 LLM 在其上调整）。

    只渲染 11 个 LLM 字段（主干 7 + 特化 4，不含 ⑫ style_profile——它不参与重凝练，受控决策 4）；
    有值的字段才输出行（空串主干/None 特化省略，与 settle 输出格式一致）。
    """
    lines: list[str] = []
    for key, label in _LLM_FIELDS:
        value = (card.get(key) or "").strip()
        if value:
            lines.append(f"{label}：{value}")
    return "\n".join(lines)


def _build_revise_messages(
    card: dict[str, str | None], feedback: str
) -> list[Message]:
    """组装反馈重凝练消息（Story 3.4 AC3）：共用 system prompt + 携「当前卡 + 用户反馈」user 消息。

    要求 LLM **在现有卡基础上按反馈调整**（非从零重来）：未涉及的字段照抄、反馈涉及的按要求改，
    仍按固定 11 字段「标签：内容」格式全量输出（便于防御解析 + 算变化项）。
    """
    current = _format_card_for_prompt(card)
    user_content = (
        f"这是当前的故事设定候选卡：\n{current}\n\n"
        f"读者给出的调整意见：\n{feedback}\n\n"
        "请在上面这份候选卡的基础上，按读者的调整意见修改——没被提到的字段保持原样照抄、"
        "被提到的按要求改。仍然按上面要求的固定「标签：内容」格式，把 11 个字段完整输出一遍。"
    )
    return [
        {"role": "system", "content": _settle_system_prompt()},
        {"role": "user", "content": user_content},
    ]


# 标签前常见的 markdown/编号装饰前缀（LLM 违背「不要 Markdown/编号」时会加）：
# 加粗/斜体星号或下划线、列表符 `- `/`* `/`• `、阿拉伯数字编号 `1.`/`1)`、圈号 `①`。
# 解析前剥离，避免 `**题材**：X` / `1. 题材：X` 命中不了标签 → 好内容误判空产 502。
_LABEL_PREFIX_RE = re.compile(r"^[\s>*_\-•·]*(?:[0-9]+[.)、]|[①-⑫])?\s*")


def _normalize_label(label: str) -> str:
    """归一化标签：剥离首部 markdown/编号装饰 + 尾部星号/空白，供精确匹配（防御解析加固）。"""
    label = _LABEL_PREFIX_RE.sub("", label)
    return label.strip().strip("*_").strip()


def _parse_settle_response(content: str) -> dict[str, str]:
    """解析凝练响应为 {列名: 内容}（防御性，仿 style_anchor._parse_style_profile）。

    按「标签：内容」逐行匹配 11 字段标签，只收已知字段、静默跳过畸形行；模型偏离格式不崩溃。
    标签侧先过 `_normalize_label` 剥离 markdown/编号装饰（`**题材**`/`1. 题材`/`- 题材` 等），
    使 LLM 违背 prompt 加装饰时仍能命中，避免好内容被丢成空产 502（code review 加固）。
    空值（冒号后留空）不计入——主干留空 = story_bible 主干列空串语义、特化缺行 = NULL 语义，
    统一由调用方按「解析到与否」处理。⑫ style_profile 不在此解析（读既有值）。
    """
    label_to_key = {label: key for key, label in _LLM_FIELDS}
    parsed: dict[str, str] = {}
    for raw in content.splitlines():
        line = raw.strip()
        if "：" not in line and ":" not in line:
            continue
        sep = "：" if "：" in line else ":"
        label, _, value = line.partition(sep)
        label = _normalize_label(label)
        value = value.strip()
        if label in label_to_key and value:
            parsed[label_to_key[label]] = value
    return parsed


def _format_guided_material(answers: list[ExplorationMessage]) -> str:
    """把引导问答对拼成可读材料文本（问：… / 答：…）。"""
    blocks: list[str] = []
    for item in answers:
        question = (item.question or "").strip()
        answer = (item.answer or "").strip()
        if not answer:
            continue
        prefix = f"问：{question}\n" if question else ""
        blocks.append(f"{prefix}答：{answer}")
    return "\n\n".join(blocks)


def _format_free_material(
    messages: list[ExplorationMessage], clues: list[StoryClue]
) -> str:
    """把自由对话 + 有效线索拼成可读材料文本。

    对话按「用户/Agent：内容」逐行；线索区取 value.strip() 非空的（空串 preset 槽 = 未填，
    不算有效材料）。两段拼接，供 LLM 凝练更全。
    """
    parts: list[str] = []
    conversation = "\n".join(
        f"{'用户' if item.role == 'user' else 'Agent'}：{(item.content or '').strip()}"
        for item in messages
        if (item.content or "").strip()
    )
    if conversation:
        parts.append(f"【对话记录】\n{conversation}")
    clue_lines = "\n".join(
        f"{clue.label}：{clue.value.strip()}"
        for clue in clues
        if clue.value.strip()
    )
    if clue_lines:
        parts.append(f"【已整理的线索】\n{clue_lines}")
    return "\n\n".join(parts)


async def settle_into_profile(
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
) -> dict[str, str | None]:
    """把探索内容真实凝练成 12 字段设定候选卡（AC1-AC5），落库 pending 卡 + 返回候选卡 dict。

    **独立 session 自管**（陷阱⑩，同 extract_clues / extract_and_anchor_style 范式）。流程：
    1. 重校验租户（`get_owned_project` → None 抛 404 二义合一）。
    2. 取会话 + 按 mode 分支取材料（guided=引导答案；free=对话+有效线索）。
    3. 空态短路（材料为空）：抛 400 settle_empty，**不过护栏、不调 provider**（省成本，仿
       extract_clues 空转 return；guided 无门禁但前端保证收尾态触发、free 有 2.7 门禁——本判
       据仍独立防御）。
    4. 读 3.2 已抽取的 style_profile（story_bible.style_profile，可空，AC2⑫）。
    5. 护栏 check_quota（**在确定要调 provider 之后、调用之前**，陷阱②）。托管触顶抛 429。
    6. 构造带记账 Provider（MeteredProvider，禁自 new，陷阱①）→ 非流式凝练（快档 + 足量
       max_tokens 防挤空，陷阱⑥）。
    7. 防御性解析 11 字段；主干全空（模型完全跑偏）→ 抛 502 generate_failed（承空产不落先例）。
    8. 组装 12 字段候选卡 dict（含 ⑫=既有 style_profile）→ **upsert 落库为 pending 卡**
       （status='pending', revision=1, changed_fields=None，Story 3.4 AC1；复用 3.2 半成品行、
       style_profile 幂等写回同值不覆盖；竞态兜底 rollback→UPDATE）→ 返回候选卡 dict 给 worker
       推 SSE result。既落库（供刷新恢复）又推 SSE（供即时弹卡）。

    返回 {snake_case 列名: 值 | None}：主干 7 恒有键（缺料为空串）、特化 4 + style_profile
    可为 None（未激活/未锚定）。worker 用它组装 SSE result payload（转 camelCase）。
    """
    settings = get_settings()
    async with async_session_maker() as session:
        # 1. 租户守卫（陷阱①）：独立 session 上重校验 project 归属（属主已在触发端点校验，
        #    此处防御直接调用本编排）。二义合一 404。
        project = await project_repo.get_owned_project(session, project_id, user_id)
        if project is None:
            raise exploration_service._exploration_not_found()

        # 2. 取会话 + 按 mode 分支取材料。无会话 → 材料为空（step 3 短路）。
        exploration_session = await exploration_repo.get_session_by_project(
            session, user_id, project_id
        )
        material_text = ""
        if exploration_session is not None:
            if exploration_session.mode == "guided":
                answers = await exploration_repo.list_guided_answers_by_session(
                    session,
                    user_id=user_id,
                    project_id=project_id,
                    session_id=exploration_session.id,
                )
                material_text = _format_guided_material(answers)
            else:  # free
                messages = await exploration_repo.list_free_messages_by_session(
                    session,
                    user_id=user_id,
                    project_id=project_id,
                    session_id=exploration_session.id,
                )
                clues = await story_clue_repo.list_clues_by_session(
                    session,
                    user_id=user_id,
                    project_id=project_id,
                    session_id=exploration_session.id,
                )
                material_text = _format_free_material(messages, clues)

        # 3. 空态短路（省成本）：材料为空则不过护栏、不调 provider（陷阱：空串 preset 槽已在
        #    _format_free_material 过滤，不会漏过；guided 空答案同理为空）。
        if not material_text.strip():
            raise _settle_empty()

        # 4. 读 3.2 已抽取的 style_profile（AC2⑫，只读不写）。story_bible 行可能不存在
        #    （未锚定文风）/ style_profile 为 None → ⑫ 可空（AC 允许，不阻塞出卡）。
        bible = await story_bible_repo.get_by_project(
            session, user_id=user_id, project_id=project_id
        )
        existing_style = bible.style_profile if bible is not None else None

        # 5. 护栏（陷阱②）：**在确定要调 provider 之后、调用之前**（空态短路已在 step 3 return，
        #    无需过闸——同 extract_clues:302-303 放置逻辑）。托管触顶抛 429。
        await usage_service.check_quota(session, user_id)

        # 6. 构造带记账 Provider（MeteredProvider）→ 非流式凝练（快档 + 足量 max_tokens）。
        provider = await get_provider_for_user(session, user_id, project_id=project_id)
        result: ChatResult = await provider.chat(
            _build_settle_messages(material_text),
            model=settings.deepseek_model_fast,
            max_tokens=_MAX_TOKENS,
        )

        # 7. 防御性解析 11 字段。空产兜底：主干一个都没解析到（模型完全跑偏）→ 抛 502
        #    generate_failed（承 style_anchor/free 空产不落先例；空卡无意义、抛错让 worker
        #    推 error 而非落空卡）。
        parsed = _parse_settle_response(result.content)
        if not any(key in parsed for key in _BACKBONE_KEYS):
            raise ErrorEnvelope(
                code="generate_failed",
                message="整理失败，请稍后重试。",
                http_status=502,
            )

        # 8. 组装 12 字段候选卡 dict。主干 7 恒有键（缺料空串、对齐 story_bible 主干列
        #    server_default="" 语义）；特化 4 缺则 None（对齐 NULL 语义）；⑫ = step 4 读到的
        #    既有 style_profile（可 None，幂等写回不覆盖）。
        card: dict[str, str | None] = {}
        for key, _ in _BACKBONE_FIELDS:
            card[key] = parsed.get(key, "")
        for key, _ in _SPECIALIZED_FIELDS:
            card[key] = parsed.get(key)  # 缺 → None（特化未激活）
        card["style_profile"] = existing_style

        # 落库 pending 卡（Story 3.4 AC1，替代 3.3 emit-only）：status='pending'、首版 revision=1、
        # changed_fields=None。复用 3.2 半成品行（style_profile 幂等写回同值）。竞态兜底见 helper。
        await _persist_card_with_race_guard(
            session,
            user_id=user_id,
            project_id=project_id,
            card=card,
            status="pending",
            revision=1,
            changed_fields=None,
        )
        # 仍返回候选卡 dict 给 worker 推 SSE result（即时弹卡）——settle 既落库又推 SSE。
        return card


def _card_from_bible(bible: StoryBible) -> dict[str, str | None]:
    """把 story_bible 行的 12 内容字段抽成候选卡 dict（供 revise 重凝练前读当前卡 / 算变化项）。"""
    return {
        field: getattr(bible, field)
        for field in story_bible_repo.PROFILE_CONTENT_FIELDS
    }


def _compute_changed_fields(
    old_card: dict[str, str | None], new_card: dict[str, str | None]
) -> list[str]:
    """算反馈升版本的变化字段（AC4）：比对旧卡与新卡的 11 个 LLM 字段，收集值变化的列名。

    只比 11 个 LLM 字段（主干 7 + 特化 4）——⑫ style_profile 不参与重凝练、恒不变，不计入
    （受控决策 4）。规范化比较：None/空串归一后比（主干旧值空串 / 特化旧值 None 对齐）。
    传入的 new_card 是**已回退漏字段的最终卡**（非原始 parsed）——LLM 漏输出的字段回退成旧值后
    与旧值相同、不会被误标为「变化」（code review 发现 2）。
    """
    changed: list[str] = []
    for key, _ in _LLM_FIELDS:
        old_value = (old_card.get(key) or "").strip()
        new_value = (new_card.get(key) or "").strip()
        if old_value != new_value:
            changed.append(key)
    return changed


async def revise_profile_card(
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    feedback: str,
) -> StoryBible:
    """反馈升版本（Story 3.4 AC3/AC4）：真实同一凝练 Agent 按反馈重生成候选卡、revision 递增。

    **独立 session 自管**（陷阱⑩，同 settle_into_profile 范式）。流程：
    1. 重校验租户（`get_owned_project` → None 抛 404 二义合一）。
    2. 取当前 pending 卡（`get_pending_by_project` → None 抛 404 no_pending_card——无卡不能改）。
    3. 护栏 check_quota（provider 前，陷阱②）。托管触顶抛 429。
    4. 构造 MeteredProvider → 非流式重凝练（当前卡 + 反馈 → LLM 全量 11 字段输出）。
    5. 防御解析 11 字段；主干全空 → 抛 502 generate_failed（同 settle 空产守卫）。
    6. 算变化字段（新旧 11 字段 diff，⑫ 不计）；组装新卡（⑫ 沿用旧 style_profile 不重凝练）。
    7. upsert 落库：revision = 旧 +1、status 保持 pending、changed_fields=变化列表；竞态兜底。

    返回更新后的 story_bible 行（含新 revision + changed_fields），router 序列化为响应。
    """
    settings = get_settings()
    async with async_session_maker() as session:
        # 1. 租户守卫（陷阱①）。
        project = await project_repo.get_owned_project(session, project_id, user_id)
        if project is None:
            raise exploration_service._exploration_not_found()

        # 2. 取当前 pending 卡（无 → 404 no_pending_card，不调 provider）。
        bible = await story_bible_repo.get_pending_by_project(
            session, user_id=user_id, project_id=project_id
        )
        if bible is None:
            raise _no_pending_card()
        old_card = _card_from_bible(bible)
        old_revision = bible.revision
        existing_style = bible.style_profile

        # 3. 护栏（provider 前，陷阱②）。托管触顶抛 429。
        await usage_service.check_quota(session, user_id)

        # 4. 构造带记账 Provider（MeteredProvider，禁自 new，陷阱①）→ 非流式重凝练。
        provider = await get_provider_for_user(session, user_id, project_id=project_id)
        result: ChatResult = await provider.chat(
            _build_revise_messages(old_card, feedback),
            model=settings.deepseek_model_fast,
            max_tokens=_MAX_TOKENS,
        )

        # 5. 防御解析 + 空产守卫（同 settle）。
        parsed = _parse_settle_response(result.content)
        if not any(key in parsed for key in _BACKBONE_KEYS):
            raise ErrorEnvelope(
                code="generate_failed",
                message="整理失败，请稍后重试。",
                http_status=502,
            )

        # 6. 组装新卡（⑫ 沿用旧 style_profile 不重凝练，受控决策 4）。
        #    **漏字段回退原值**（code review 发现 2）：revise 是「在现有卡上按反馈调整」，LLM 若
        #    漏输出某字段（解析不到），保留 old_card 原值而非清空——避免单字段漏输出静默丢数据。
        #    主干缺 → 用旧值（旧值可能是空串）；特化缺 → 用旧值（旧值可能是 None）。
        card: dict[str, str | None] = {}
        for key, _ in _BACKBONE_FIELDS:
            card[key] = parsed[key] if key in parsed else (old_card.get(key) or "")
        for key, _ in _SPECIALIZED_FIELDS:
            card[key] = parsed[key] if key in parsed else old_card.get(key)
        card["style_profile"] = existing_style

        # 算变化字段（AC4）：比对旧卡与**最终新卡**（已回退漏字段），漏输出的字段回退后与旧值
        #    相同、不会被误标为变化。style_profile 不参与（受控决策 4）。
        changed_fields = _compute_changed_fields(old_card, card)

        # 7. 落库升版本：revision +1、status 仍 pending、changed_fields=变化列表。竞态兜底见
        #    helper（已存在行走 UPDATE 无 IntegrityError，兜底仅防御性一致）。
        return await _persist_card_with_race_guard(
            session,
            user_id=user_id,
            project_id=project_id,
            card=card,
            status="pending",
            revision=old_revision + 1,
            changed_fields=changed_fields,
        )


async def edit_profile_card(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    fields: dict[str, str],
) -> StoryBible:
    """直接编辑候选卡字段（Story 3.4 AC2）：无 LLM、无护栏，仅改传入字段、revision 不变。

    用请求注入 session（无 provider 记账，无需独立 session，同 exploration_service CRUD 端点
    save_guided_answer/edit_clue 范式）。流程：租户守卫 → update_card_fields（仅 pending 行、
    仅白名单 12 字段）→ commit。无 pending 卡 → 404 no_pending_card。
    """
    project = await project_repo.get_owned_project(session, project_id, user_id)
    if project is None:
        raise exploration_service._exploration_not_found()

    bible = await story_bible_repo.update_card_fields(
        session, user_id=user_id, project_id=project_id, fields=fields
    )
    if bible is None:
        raise _no_pending_card()
    await session.commit()
    return bible


async def get_pending_card(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
) -> StoryBible | None:
    """取待确认候选卡（Story 3.4 AC6 恢复）：租户守卫 → get_pending_by_project。

    用请求注入 session（只读，无 provider）。返 None = 无待确认卡（正常空态，非错误）——
    router 转 204。确认后（3.5 翻 confirmed）本查询自然返 None（AC6：确认后无待确认卡）。
    """
    project = await project_repo.get_owned_project(session, project_id, user_id)
    if project is None:
        raise exploration_service._exploration_not_found()
    return await story_bible_repo.get_pending_by_project(
        session, user_id=user_id, project_id=project_id
    )
