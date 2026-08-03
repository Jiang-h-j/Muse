"""Guidance Agent：自由探索的设定导航——完成度评估、当前追问字段、候选回复、跳过（Story 2.8）。

承接 Sprint Change Proposal 2026-07-31：把 EXP-P02「以设定结果覆盖度决定探索是否完成」的
最小能力从 V2 提前到 V1，替换 2.7「≥1 条用户消息」的近似门禁。本模块维护
`exploration_session.guidance_state`（JSONB）——7 项通用主干字段（题材/核心吸引力/主角/
主要冲突/关键世界规则/整体气质/开篇钩子）的完成度（missing/filled/skipped）、当前追问的
字段、`ready_to_settle` 布尔位。

**2026-08-03 合并重构（消费用户反馈：聊天正文与「当前具体问题」不一致）**：此前本模块
`refresh_guidance` 在每轮对话结束后**独立调一次 LLM**判定完成度 + 生成一句独立的「下一问」
文本，与 `free_explorer_agent.stream_free_chat` 的聊天回复是两次互不知情的调用，导致展示
给用户的两份文本经常对不上。现在完成度判定 + 候选回复生成已经**合并进聊天回复的同一次
LLM 调用**（`free_explorer_agent._parse_chat_response`），`refresh_guidance` 整个移除，
改由 `apply_chat_judgement` 承接「把已经解析好的判定结果合并进 `guidance_state`」这一步
（不再调用 LLM，纯粹是状态合并 + 落库）。`guidance_state` 相应**不再存储
`current_question`**——聊天记录本身就是唯一的问题事实源，不需要第二份独立文本；改存
`current_suggestions`（2-4 条候选回复，随聊天回复一起生成，供前端贴在最新一条 Agent
消息下方，默认收起，用户点「没想好？看看几个思路」才展开——不必再为此发一次网络请求）。

零对话四入口（`start_guidance`）与跳过后推进下一问（`skip_current_field`）**这两个入口
仍需要独立调用 LLM**（会话里还没有对应的聊天上下文可合并），但生成的问题不再只是一份
展示文本——**落库为真实的 agent 聊天消息**（复用 `exploration_repo.append_free_message`），
与用户后续在聊天框里看到的历史无缝衔接；同一次调用里一并生成候选回复写入
`current_suggestions`。

**与 `free_explorer_agent`/`story_settle_agent` 职责独立**：前者服务自由对话本身（多轮聊天
+ 依对话自动整理线索），后者服务「探索→12 字段候选卡」的凝练；本模块服务「探索过程中的
导航」——判断设定还缺什么、当前该追问哪个字段、处理跳过。延续「按 Agent 职责拆 service」
的既定项目模式（同 free_explorer_agent/style_anchor_agent/story_settle_agent 先例）。

**与 `guidance_state` 与 `story_clue` 不合并**（architecture.md L237 已定档）：`story_clue`
仍是用户可直接编辑的事实展示区（含 `user_edited` 优先保护），`guidance_state` 只服务完成度
与候选回复的后端事实源。跳过操作（`skip_current_field`）会同时触碰两个存储——这不违反「不
合并」原则，只是同一次用户操作的两个连带效果（仿 2.2 `enter_exploration` 同一事务内既建
会话又播种线索的先例）。

**字段集合单一事实源**：本模块直接 import `story_settle_agent._BACKBONE_FIELDS`（7 项 key+
中文标签），不重复定义——避免 `guidance_state.fields` 与 `story_bible` 主干列漂移。

分层（architecture.md router→service→provider）：经 LLMProvider 抽象调 LLM（禁直调
openai，陷阱①），生成前过 check_quota 护栏（陷阱②），Provider 层自动记账（AR14）。

session 生命周期：`apply_chat_judgement` 接收调用方（`free_explorer_agent.stream_free_chat`）
已开的独立 session——它是该函数流式对话落库后、同一独立 session 内的追加步骤，不另开
session、不调用 LLM（判定已经在调用方那次 LLM 调用里做完）。`start_guidance`/
`skip_current_field` 是独立的 HTTP 端点调用入口，各自 `async_session_maker()` 自管 session
（陷阱⑩，同 `extract_clues`/`extract_and_anchor_style` 范式——MeteredProvider 的 finally
兜底记账须落在存活 session 上）。
"""

import uuid
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from muse.core.db import async_session_maker
from muse.core.errors import ErrorEnvelope
from muse.core.settings import get_settings
from muse.models.exploration_message import ExplorationMessage
from muse.models.exploration_session import ExplorationSession
from muse.models.story_clue import StoryClue
from muse.providers.base import ChatResult, Message
from muse.providers.factory import get_provider_for_user
from muse.repositories import exploration_repo, project_repo, story_clue_repo
from muse.services import exploration_service, story_settle_agent, usage_service

# 开场问题生成/跳过后下一问生成/跳过归纳都是轻量结构化任务 → 快档（deepseek-v4-flash）。
_MAX_TOKENS = 1024

# 四个固定产品入口 → 对应主干字段（AC3）。story_idea 映射到 core_appeal——「先说一个故事
# 想法」对应的是「这故事最抓人的地方是什么」，比映射到 genre（题材）更贴合「想法」的语义
# （genre 往往能从想法里直接带出、无需单独开场问；core_appeal 才是需要用户先讲清楚的）。
_ENTRY_FIELD_MAP: dict[str, str] = {
    "story_idea": "core_appeal",
    "protagonist": "protagonist",
    "conflict": "main_conflict",
    "world": "world_rules",
}

EntryKind = Literal["story_idea", "protagonist", "conflict", "world"]


def _no_current_question() -> ErrorEnvelope:
    """当前没有待答问题（Task 6 跳过入口用）：无 `current_field`（已就绪或未初始化）时抛出。

    400（前置条件未满足）——与 `_exploration_not_ready`（2.7/2.8 settle 门禁）同族但语义
    不同：那个是「还不能整理」，这个是「当前没有问题可跳过」，不复用同一 code。
    """
    return ErrorEnvelope(
        code="no_current_question",
        message="当前没有待回答的问题。",
        http_status=400,
    )


async def _guard_free_session(
    session: AsyncSession, *, user_id: uuid.UUID, project_id: uuid.UUID
) -> ExplorationSession | None:
    """租户守卫 + mode 守卫（本模块入口共用前置校验）。

    返回该作品的探索会话（可能为 `None`——尚未进入探索）；project 不存在/不属于我抛 404，
    mode 非 free 抛 409。不做「无会话即报错」——各调用方按自身语义处理（多数应视为
    「无消息/无进度」的自然空态，而非错误）。
    """
    project = await project_repo.get_owned_project(session, project_id, user_id)
    if project is None:
        raise exploration_service._exploration_not_found()
    exploration_service._require_project_mode(project, "free")
    return await exploration_repo.get_session_by_project(session, user_id, project_id)


def _build_material_text(
    messages: list[ExplorationMessage], clues: list[StoryClue]
) -> str:
    """拼对话历史 + 有效线索为可读材料文本，供开场/跳过后下一问生成消费。

    取材范式仿 `story_settle_agent._format_free_material`（对话按「用户/Agent：内容」逐行，
    线索区取 value 非空的），但不直接复用该私有函数——本模块的材料消费者各自需要在同一
    文本基础上服务不同 prompt，独立维护更清晰、不与 3.3 的凝练 prompt 耦合。
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
        f"{clue.label}：{clue.value.strip()}" for clue in clues if clue.value.strip()
    )
    if clue_lines:
        parts.append(f"【已整理的线索】\n{clue_lines}")
    return "\n\n".join(parts) if parts else "（对话尚未开始，还没有任何内容。）"


async def _gather_material(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    session_id: uuid.UUID,
) -> str:
    """取本会话全部自由对话 + 全部线索，拼成材料文本（Task 4/6 共用取材步骤）。"""
    messages = await exploration_repo.list_free_messages_by_session(
        session, user_id=user_id, project_id=project_id, session_id=session_id
    )
    clues = await story_clue_repo.list_clues_by_session(
        session, user_id=user_id, project_id=project_id, session_id=session_id
    )
    return _build_material_text(messages, clues)


async def get_guidance(
    session: AsyncSession, *, user_id: uuid.UUID, project_id: uuid.UUID
) -> dict:
    """恢复当前导航状态（Task 8 `GET /free/guidance`）：只读，用请求注入 session。

    供前端刷新/断线重连时读取完成度、当前追问字段与就绪位——本函数**不调 LLM**，纯粹是
    「读取已持久化状态」。用请求注入 session（同 `get_pending_card`/`list_free_messages`
    等既有只读端点范式，无 provider 记账、无需独立 session）。

    无会话/`guidance_state` 为 `None`（guided 会话或异常路径）→ 返回全 `missing` 初始态
    （不 404，避免前端要额外处理 404 分支）。
    """
    exploration_session = await _guard_free_session(
        session, user_id=user_id, project_id=project_id
    )
    if exploration_session is None or exploration_session.guidance_state is None:
        return exploration_service._initial_guidance_state()
    return exploration_session.guidance_state


def _still_missing(fields: dict[str, str]) -> list[str]:
    """按 `_BACKBONE_FIELDS` 固定顺序取出仍为 `missing` 的字段名（Task 3/6 共用）。"""
    return [
        key for key, _ in story_settle_agent._BACKBONE_FIELDS if fields.get(key) == "missing"
    ]


def _merge_field_updates(
    guidance_state: dict, field_updates: dict[str, str]
) -> dict[str, str]:
    """把本轮判定的字段更新合并进现有 `fields`（AC2 单调性核心）。

    - 已 `filled`/`skipped` 的项：保留原状态，不因本轮判定被打回 `missing`（AC2 硬约束、
      V1 无撤销机制、单向前进）。
    - 新判为 `filled` 的 `missing` 项：更新为 `filled`。
    - 其余仍 `missing` 的项：保持 `missing`。
    """
    fields = dict(guidance_state["fields"])
    for key, new_status in field_updates.items():
        if fields.get(key) == "missing":
            fields[key] = new_status
    return fields


async def _generate_fallback_suggestions(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    session_id: uuid.UUID,
    chat_text: str,
) -> list[str]:
    """合并调用漏掉候选时的兜底：单独补一次候选生成。

    修复间歇性空候选 + 候选与问题不一致（2026-08-03）：模型在合并调用里约 30% 概率不输出
    候选行（即使 prompt 强制要求）。本函数单独补一次 LLM 生成 2-4 条候选——比"每次都调
    两次"成本低（大多数时候合并调用就够，只有偶尔空了才补第二次）。护栏触顶/空产时返回
    空列表（不阻塞主流程——候选是增值项，聊天正文本身已经是问题）。

    **以 chat_text 为锚点**：兜底绝不再依赖 `current_field` 的字段标签去描述「该问什么」——
    `current_field` 在 fallback 路径里可能已经 fallback 到 `still_missing[0]`（与 Agent
    实际问的未必一致），拿「题材」这种标签当主语会让模型产出题材类型候选，与 Agent 聊天
    框里问的具体情境化问题彻底脱节。改为把 Agent 刚问的那句 chat_text 作为唯一锚点，要求
    候选必须针对这句话作答。对话历史只作背景。
    """
    try:
        await usage_service.check_quota(session, user_id)
    except ErrorEnvelope:
        return []
    material_text = await _gather_material(
        session, user_id=user_id, project_id=project_id, session_id=session_id
    )
    settings = get_settings()
    provider = await get_provider_for_user(session, user_id, project_id=project_id)
    messages: list[Message] = [
        {
            "role": "system",
            "content": (
                "你在帮一位读者想「刚才 Agent 问他的那个问题」可能怎么回答。Agent 刚问的"
                "那句话会单独给你——候选必须**针对这句话**作答，不要泛泛地按题材/类型去列。"
                "下面的对话历史只作为背景参考。给出 2 到 4 个不同角度的候选回答，帮他打开"
                "思路，每个候选回答独立一行，格式：候选：<一句可以直接当作读者自己说的话"
                "的回答>。只输出候选行，不要输出任何其他文字。"
            ),
        },
        {
            "role": "user",
            "content": f"Agent 刚问的问题是：\n{chat_text}\n\n对话历史（背景）：\n{material_text}",
        },
    ]
    result: ChatResult = await provider.chat(
        messages, model=settings.deepseek_model_fast, max_tokens=_MAX_TOKENS
    )
    suggestions: list[str] = []
    for raw in result.content.splitlines():
        line = raw.strip()
        if line.startswith("候选") and ("：" in line or ":" in line):
            sep = "：" if "：" in line else ":"
            _, _, text = line.partition(sep)
            text = text.strip()
            if text:
                suggestions.append(text)
    return suggestions[:4]


async def apply_chat_judgement(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    field_updates: dict[str, str],
    question_field: str | None,
    suggestions: list[str],
    chat_text: str,
) -> dict:
    """把一轮聊天里已经解析好的判定结果合并进 `guidance_state`（AC2/AC7/AC9 核心）。

    **2026-08-03 合并重构核心**：完成度判定 + 追问字段选择 + 候选回复生成已经在
    `free_explorer_agent.stream_free_chat` 的同一次 LLM 调用里做完
    （`free_explorer_agent._parse_chat_response`），本函数**不再调用 LLM**，纯粹是「把
    已解析的结果合并进持久化状态」——由调用方（同一独立 session）在该轮对话落库后
    紧邻调用。

    `chat_text` 是本轮 Agent 聊天正文——兜底补调候选时的唯一锚点（见
    `_generate_fallback_suggestions`）：合并调用漏掉候选时，用它而非可能 fallback 到
    `still_missing[0]` 的 `current_field` 标签去生成候选，避免候选与聊天问题脱节。

    1. 租户守卫 + mode 守卫（`_guard_free_session`）。
    2. 无会话（理论上 `enter_exploration` 已保证存在，此处防御性兜底）→ 返回初始 `missing`
       态，不写库。
    3. 已无 `missing` 项（判定发生在 `ready_to_settle` 已真之后，理论不该被调用，防御性
       短路）→ 直接返回当前态。
    4. 合并 `field_updates` → 算出 `still_missing`：
       - 若已无 `missing` 项：`current_field` 清空、`current_suggestions` 清空、
         `ready_to_settle` 置真（AC7）。
       - 若仍有缺项：`current_field` 优先取模型标注的 `question_field`（若仍在
         `still_missing` 里）；标注缺失/失效时 fallback 到 `still_missing` 固定顺序第一项
         （避免模型偏离格式时陷入无字段可追问的空白态）。`current_suggestions` 直接取本轮
         `suggestions`（可能为空列表——聊天正文本身已经是问题，候选回复是增值项，不是
         必需项）。
    5. 落库（`update_guidance_state`）+ commit。

    返回最新的 `guidance_state`（内部 snake_case 结构，供调用方/router 转 schema）。
    """
    exploration_session = await _guard_free_session(
        session, user_id=user_id, project_id=project_id
    )
    if exploration_session is None or exploration_session.guidance_state is None:
        return exploration_service._initial_guidance_state()

    guidance_state = exploration_session.guidance_state
    if not _still_missing(guidance_state["fields"]):
        return guidance_state

    fields = _merge_field_updates(guidance_state, field_updates)
    still_missing = _still_missing(fields)

    if not still_missing:
        new_state = {
            "fields": fields,
            "current_field": None,
            "current_suggestions": [],
            "ready_to_settle": True,
        }
    else:
        current_field = (
            question_field if question_field in still_missing else still_missing[0]
        )
        # 兜底（2026-08-03）：合并调用约 30% 概率漏掉候选行，此时单独补一次候选生成，
        # 避免用户看到「暂时没想到合适的思路」。候选以 Agent 刚问的 chat_text 为锚点
        # （而非 current_field 标签——后者在 fallback 路径里可能已 fallback 到
        # still_missing[0]，与实际问的未必一致，会把候选带偏）。护栏触顶/空产时
        # suggestions 仍为空——前端有兜底文案，不阻塞主流程。
        final_suggestions = suggestions
        if not final_suggestions:
            final_suggestions = await _generate_fallback_suggestions(
                session,
                user_id=user_id,
                project_id=project_id,
                session_id=exploration_session.id,
                chat_text=chat_text,
            )
        new_state = {
            "fields": fields,
            "current_field": current_field,
            "current_suggestions": final_suggestions,
            "ready_to_settle": False,
        }

    await exploration_repo.update_guidance_state(
        session,
        user_id=user_id,
        project_id=project_id,
        session_id=exploration_session.id,
        guidance_state=new_state,
    )
    await session.commit()
    return new_state


# ---------- 零对话四入口首问生成（Task 4，AC3） ----------


def _start_system_prompt(field_label: str) -> str:
    """零对话开场问题的 system prompt（AC3）：只生成一句围绕指定字段的开场问题。

    零对话时没有材料可判定完成度（7 项恒 missing），本 prompt 不要求判定，只要求生成
    开场问题；候选回复紧跟在后面用同一次调用生成（合并重构后同 `_suggest_system_prompt`
    语义合并进本 prompt，避免「开场问题 + 候选回复」拆两次调用）。
    """
    return f"""你在陪一位读者聊他脑中的小说想法，他刚选了想先聊「{field_label}」这个方向。

请针对「{field_label}」，用一句自然、口语化的问题开场，帮他把这个方向的念头说清楚。

要求：
- 问题要具体、像朋友聊天一样问，不要泛泛地问「说说你的故事」。
- 只输出这一句问题，不要引号包裹、不要 Markdown。

写完这句问题后，另起一行，输出分隔符 ###SUGGESTIONS###，然后给出 2 到 4 个候选回答，
帮读者应对你刚才这句开场问题，每个候选回答独立一行，格式：
候选：<一句可以直接当作读者自己说的话的回答>

要求：
- 每一条「候选」都要针对你刚才那句开场问题，不要跑题。
- 分隔符之后严格按「候选：内容」格式逐行输出，不要输出任何其他文字、不要编号、
  不要 Markdown。"""


def _next_question_system_prompt(field_label: str) -> str:
    """针对已知的单个字段生成下一问的 system prompt（Task 6 跳过后推进用）。

    字段已由调用方确定（`skip_current_field` 从 `still_missing` 里选出），只要求结合
    已有对话材料针对这一个字段生成一句自然的追问，同一次调用附带生成候选回复（合并
    重构后与 `_start_system_prompt` 同款结构）。
    """
    return f"""你在陪一位读者聊他脑中的小说想法，接下来想聊「{field_label}」这个方向。

读下面已有的对话材料（如果有），针对「{field_label}」，用一句自然、口语化的问题接着问，
帮他把这个方向的念头说清楚。

要求：
- 问题要具体、像朋友聊天一样问，不要泛泛地问「说说你的故事」，也不要重复材料里已经问过
  的内容。
- 只输出这一句问题，不要引号包裹、不要 Markdown。

写完这句问题后，另起一行，输出分隔符 ###SUGGESTIONS###，然后给出 2 到 4 个候选回答，
帮读者应对你刚才这句问题，每个候选回答独立一行，格式：
候选：<一句可以直接当作读者自己说的话的回答>

要求：
- 每一条「候选」都要针对你刚才那句问题，不要跑题。
- 分隔符之后严格按「候选：内容」格式逐行输出，不要输出任何其他文字、不要编号、
  不要 Markdown。"""


def _parse_question_with_suggestions(content: str) -> tuple[str, list[str]]:
    """解析「开场问题/下一问 + 候选回复」合并输出：分隔符之前是问题正文，之后是候选。

    分隔符缺失（模型偏离格式）→ 整段视为问题正文，候选回复返回空列表（不阻塞主流程，
    候选回复是增值项）。
    """
    separator = "###SUGGESTIONS###"
    idx = content.find(separator)
    if idx == -1:
        return content.strip(), []
    question = content[:idx].strip()
    suggestions: list[str] = []
    for raw in content[idx + len(separator) :].splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("候选") and ("：" in line or ":" in line):
            sep = "：" if "：" in line else ":"
            _, _, text = line.partition(sep)
            text = text.strip()
            if text:
                suggestions.append(text)
    return question, suggestions[:4]


async def start_guidance(
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    entry: EntryKind,
) -> dict:
    """零对话四入口生成对应开场问题（AC3）：仅当会话尚无任何对话时才真正生成新问题。

    **独立 session 自管**（陷阱⑩，同 `extract_and_anchor_style`/`extract_clues` 范式——
    调 provider 走 MeteredProvider 记账，finally 兜底记账须落在存活 session 上）。

    1. 租户守卫 + mode 守卫。
    2. **幂等防护**：若本会话已有 free 用户消息（`has_free_user_message`），说明前端误
       调用/重放——直接返回当前 `guidance_state`，不重新生成开场问题（不抛错，因为这是
       前端流程保证的调用时机而非用户可直接触发的破坏性操作）。
    3. 无会话（尚未 `enter_exploration`）→ 视为「还没有材料」，先返回初始态（不建会话——
       建会话是 `enter_exploration`/`stream_free_chat` 的职责，本函数不越权）。
    4. **单调性防护**：`entry` 映射到的字段若已是 `filled`/`skipped`（例如零消息状态下
       `start→skip` 后再次对同一 entry 调用 `start`），直接幂等返回当前态、不重新生成问题
       ——与「单向前进、无撤销」的保证对齐，避免把已跳过/已完成的字段重新打开成
       `current_field`。
    5. 护栏 `check_quota`（provider 前，陷阱②）——托管触顶抛 429（本操作是零对话开场的
       首次调用，用户尚未投入任何对话内容，直接报错让前端提示重试是合理的，不做静默降级）。
    6. 一次 LLM 调用生成开场问题 + 候选回复 → **落库为真实 agent 聊天消息**（复用
       `exploration_repo.append_free_message`，与用户后续在聊天框看到的历史无缝衔接，
       2026-08-03 合并重构新增）→ 写入 `current_field`/`current_suggestions`（其余 6 项
       仍 `missing`）→ 落库 + commit。
    """
    async with async_session_maker() as session:
        exploration_session = await _guard_free_session(
            session, user_id=user_id, project_id=project_id
        )
        if exploration_session is None or exploration_session.guidance_state is None:
            return exploration_service._initial_guidance_state()

        guidance_state = exploration_session.guidance_state
        already_started = await exploration_repo.has_free_user_message(
            session,
            user_id=user_id,
            project_id=project_id,
            session_id=exploration_session.id,
        )
        if already_started:
            return guidance_state

        field_key = _ENTRY_FIELD_MAP[entry]
        if guidance_state["fields"].get(field_key) != "missing":
            # 该字段已 filled/skipped（如零消息下 start→skip 后重复调用同一 entry）——
            # 幂等返回当前态，不重新打开已解决的字段（单调性，同 apply_chat_judgement）。
            return guidance_state

        await usage_service.check_quota(session, user_id)

        field_label = dict(story_settle_agent._BACKBONE_FIELDS)[field_key]
        settings = get_settings()
        provider = await get_provider_for_user(session, user_id, project_id=project_id)
        messages: list[Message] = [
            {"role": "system", "content": _start_system_prompt(field_label)},
        ]
        result: ChatResult = await provider.chat(
            messages, model=settings.deepseek_model_fast, max_tokens=_MAX_TOKENS
        )
        question, suggestions = _parse_question_with_suggestions(result.content)
        if not question:
            question = f"想先聊聊「{field_label}」，你有什么想法？"

        # 落库为真实 agent 聊天消息（2026-08-03 合并重构新增）：零对话时没有用户消息，
        # 只落一条 agent 消息——与 stream_free_chat「用户+agent 两条」不同，这里没有对应
        # 的用户发言可落。
        await exploration_repo.append_free_message(
            session,
            user_id=user_id,
            project_id=project_id,
            session_id=exploration_session.id,
            role="agent",
            content=question,
        )
        await session.commit()

        new_state = {
            "fields": dict(guidance_state["fields"]),
            "current_field": field_key,
            "current_suggestions": suggestions,
            "ready_to_settle": False,
        }
        await exploration_repo.update_guidance_state(
            session,
            user_id=user_id,
            project_id=project_id,
            session_id=exploration_session.id,
            guidance_state=new_state,
        )
        await session.commit()
        return new_state


# ---------- 跳过 + 谨慎归纳（Task 6，AC6） ----------


def _skip_summary_system_prompt(field_label: str) -> str:
    """跳过归纳的 system prompt（AC6）：比问题生成更保守，允许合法地「什么都不说」。"""
    return f"""你在帮一位读者整理关于「{field_label}」的线索，但他决定先跳过这个问题不细说了。

读下面的对话材料，只根据材料里实际提到的内容，判断能不能为「{field_label}」写一句简短的
线索结论：
- 如果材料里有相关内容，即使不完整，也可以谨慎地写一句简短概括，输出：
  结论：<一句话概括>
- 如果材料里完全没有任何相关信息可以归纳，就只输出：
  结论：
（冒号后留空，不要编造材料里没有的内容。）

要求：
- 只输出这一行，不要输出任何其他文字、不要编号、不要 Markdown。
- 宁可留空也不要杜撰。"""


def _parse_skip_summary(content: str) -> str | None:
    """解析跳过归纳响应：取「结论：」后的文本；空/未命中格式 → `None`（不归纳）。"""
    for raw in content.splitlines():
        line = raw.strip()
        if line.startswith("结论") and ("：" in line or ":" in line):
            sep = "：" if "：" in line else ":"
            _, _, text = line.partition(sep)
            text = text.strip()
            return text or None
    return None


async def skip_current_field(
    *, user_id: uuid.UUID, project_id: uuid.UUID
) -> dict:
    """跳过当前问题（AC6）：标记 `skipped` + 立即推进下一问/收束 + 谨慎归纳写线索。

    **独立 session 自管**（陷阱⑩，同上）。

    1. 租户守卫 + mode 守卫。
    2. 无 `current_field`（已就绪或未初始化）→ 400 `no_current_question`（跳过操作在无
       当前问题时同样无意义）。
    3. **状态转移优先生效**（不依赖 LLM）：先把 `fields[current_field]` 标记 `skipped`、
       算出 `still_missing`、落库 + commit——用户明确要跳过是确定性动作，不该被额度门禁
       挡住。
    4. **跳过后立即推进下一问**——若 `still_missing` 非空，护栏 `check_quota` 通过后针对
       `still_missing` 固定顺序第一项调用 `_generate_question_for_field`（一次调用同时
       生成问题正文 + 候选回复）；生成成功则**落库为真实 agent 聊天消息**（2026-08-03
       合并重构新增，与 `start_guidance` 同款处理）并二次落库写入
       `current_field`/`current_suggestions`。护栏 429 或生成为空时静默保持上一步已提交的
       空白态（`current_field=None`）——不影响已生效的 `skipped` 状态转移，前端据此展示
       「已跳过，继续聊聊其他方面」的过渡态、等下一轮对话自然推进。
    5. **谨慎归纳写线索是独立的后续步骤**，护栏 429 时静默跳过归纳（不影响上面已生效的
       状态转移）：调一次 LLM 判断能否为该字段归纳出一句结论；归纳出内容则
       `story_clue_repo.update_clue_value`（条件 UPDATE `user_edited=false` 才写，2.6 既有
       原语直接复用，AC10 硬约束）写入对应 preset 槙位；归纳为空、或该槙位已被用户编辑
       （条件更新命中 0 行）都静默跳过、不报错。

    返回最终的 `guidance_state`（含步骤 4 的推进结果——归纳失败/跳过不影响本次返回值）。
    """
    async with async_session_maker() as session:
        exploration_session = await _guard_free_session(
            session, user_id=user_id, project_id=project_id
        )
        if (
            exploration_session is None
            or exploration_session.guidance_state is None
            or exploration_session.guidance_state.get("current_field") is None
        ):
            raise _no_current_question()

        guidance_state = exploration_session.guidance_state
        field_key = guidance_state["current_field"]

        # 3. 状态转移优先生效（不依赖 LLM）。
        fields = dict(guidance_state["fields"])
        fields[field_key] = "skipped"
        still_missing = _still_missing(fields)
        ready_to_settle = not still_missing
        new_state: dict[str, object] = {
            "fields": fields,
            "current_field": None,
            "current_suggestions": [],
            "ready_to_settle": ready_to_settle,
        }
        await exploration_repo.update_guidance_state(
            session,
            user_id=user_id,
            project_id=project_id,
            session_id=exploration_session.id,
            guidance_state=new_state,
        )
        await session.commit()

        # 4. 跳过后立即推进下一问：still_missing 非空时护栏通过后为固定顺序第一项生成
        #    一句追问 + 候选回复，成功才落库为真实聊天消息 + 二次落库覆盖
        #    current_field/current_suggestions；护栏 429/生成为空则保留步骤 3 已提交的
        #    空白态，不影响已生效的 skipped 状态转移。
        if still_missing:
            next_field = still_missing[0]
            try:
                await usage_service.check_quota(session, user_id)
            except ErrorEnvelope:
                pass
            else:
                material_text = await _gather_material(
                    session,
                    user_id=user_id,
                    project_id=project_id,
                    session_id=exploration_session.id,
                )
                next_field_label = dict(story_settle_agent._BACKBONE_FIELDS)[next_field]
                settings = get_settings()
                provider = await get_provider_for_user(
                    session, user_id, project_id=project_id
                )
                messages: list[Message] = [
                    {
                        "role": "system",
                        "content": _next_question_system_prompt(next_field_label),
                    },
                    {"role": "user", "content": f"对话材料：\n{material_text}"},
                ]
                result: ChatResult = await provider.chat(
                    messages, model=settings.deepseek_model_fast, max_tokens=_MAX_TOKENS
                )
                next_question, next_suggestions = _parse_question_with_suggestions(
                    result.content
                )
                if next_question:
                    await exploration_repo.append_free_message(
                        session,
                        user_id=user_id,
                        project_id=project_id,
                        session_id=exploration_session.id,
                        role="agent",
                        content=next_question,
                    )
                    await session.commit()
                    new_state = {
                        "fields": fields,
                        "current_field": next_field,
                        "current_suggestions": next_suggestions,
                        "ready_to_settle": False,
                    }
                    await exploration_repo.update_guidance_state(
                        session,
                        user_id=user_id,
                        project_id=project_id,
                        session_id=exploration_session.id,
                        guidance_state=new_state,
                    )
                    await session.commit()

        # 5. 谨慎归纳写线索（独立步骤，护栏/生成失败均不影响上面已生效的状态转移）。
        try:
            await usage_service.check_quota(session, user_id)
        except ErrorEnvelope:
            return new_state

        material_text = await _gather_material(
            session,
            user_id=user_id,
            project_id=project_id,
            session_id=exploration_session.id,
        )
        field_label = dict(story_settle_agent._BACKBONE_FIELDS)[field_key]
        settings = get_settings()
        provider = await get_provider_for_user(session, user_id, project_id=project_id)
        messages = [
            {"role": "system", "content": _skip_summary_system_prompt(field_label)},
            {"role": "user", "content": f"对话材料：\n{material_text}"},
        ]
        result = await provider.chat(
            messages, model=settings.deepseek_model_fast, max_tokens=_MAX_TOKENS
        )
        summary = _parse_skip_summary(result.content)
        if summary:
            clues = await story_clue_repo.list_clues_by_session(
                session,
                user_id=user_id,
                project_id=project_id,
                session_id=exploration_session.id,
            )
            clue = next((c for c in clues if c.clue_key == field_key), None)
            if clue is not None:
                await story_clue_repo.update_clue_value(session, clue=clue, value=summary)
                await session.commit()

        return new_state
