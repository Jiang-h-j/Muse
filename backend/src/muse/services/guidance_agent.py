"""Guidance Agent：自由探索的设定导航——完成度评估、单项下一问、按需思路、跳过（Story 2.8）。

承接 Sprint Change Proposal 2026-07-31：把 EXP-P02「以设定结果覆盖度决定探索是否完成」的
最小能力从 V2 提前到 V1，替换 2.7「≥1 条用户消息」的近似门禁。本模块维护
`exploration_session.guidance_state`（JSONB）——7 项通用主干字段（题材/核心吸引力/主角/
主要冲突/关键世界规则/整体气质/开篇钩子）的完成度（missing/filled/skipped）、当前待补
字段、当前问题文本、`ready_to_settle` 布尔位。

**与 `free_explorer_agent`/`story_settle_agent` 职责独立**：前者服务自由对话本身（多轮聊天
+ 依对话自动整理线索），后者服务「探索→12 字段候选卡」的凝练；本模块服务「探索过程中的
导航」——判断设定还缺什么、每轮该问哪个具体问题、按需给思路、处理跳过。延续「按 Agent
职责拆 service」的既定项目模式（同 free_explorer_agent/style_anchor_agent/story_settle_agent
先例），新建独立文件。

**与 `guidance_state` 与 `story_clue` 不合并**（architecture.md L237 已定档）：`story_clue`
仍是用户可直接编辑的事实展示区（含 `user_edited` 优先保护），`guidance_state` 只服务完成度
与下一问的后端事实源。跳过操作（`skip_current_field`）会同时触碰两个存储——这不违反「不
合并」原则，只是同一次用户操作的两个连带效果（仿 2.2 `enter_exploration` 同一事务内既建
会话又播种线索的先例）。

**字段集合单一事实源**：本模块直接 import `story_settle_agent._BACKBONE_FIELDS`（7 项 key+
中文标签），不重复定义——避免 `guidance_state.fields` 与 `story_bible` 主干列漂移。

分层（architecture.md router→service→provider）：经 LLMProvider 抽象调 LLM（禁直调
openai，陷阱①），生成前过 check_quota 护栏（陷阱②），Provider 层自动记账（AR14）。

session 生命周期：`refresh_guidance` 接收调用方（`free_explorer_agent.stream_free_chat`）
已开的独立 session——它是该函数流式对话落库后、同一独立 session 内的追加步骤，不另开
session。`start_guidance`/`suggest_answers`/`skip_current_field` 是独立的 HTTP 端点调用
入口，各自 `async_session_maker()` 自管 session（陷阱⑩，同 `extract_clues`/
`extract_and_anchor_style` 范式——MeteredProvider 的 finally 兜底记账须落在存活 session 上）。
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

# 完成度判定/下一问生成/按需思路/跳过归纳都是轻量结构化任务 → 快档（deepseek-v4-flash）。
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
    """当前没有待答问题（Task 5/6 共用）：无 `current_field`（已就绪或未初始化）时抛出。

    400（前置条件未满足）——与 `_exploration_not_ready`（2.7/2.8 settle 门禁）同族但语义
    不同：那个是「还不能整理」，这个是「当前没有问题可看思路/可跳过」，不复用同一 code。
    """
    return ErrorEnvelope(
        code="no_current_question",
        message="当前没有待回答的问题。",
        http_status=400,
    )


async def _guard_free_session(
    session: AsyncSession, *, user_id: uuid.UUID, project_id: uuid.UUID
) -> ExplorationSession | None:
    """租户守卫 + mode 守卫（本模块 4 个入口共用前置校验）。

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
    """拼对话历史 + 有效线索为可读材料文本，供导航判定/生成消费。

    取材范式仿 `story_settle_agent._format_free_material`（对话按「用户/Agent：内容」逐行，
    线索区取 value 非空的），但不直接复用该私有函数——本模块的材料消费者（判定/生成/归纳）
    各自需要在同一文本基础上服务不同 prompt，独立维护更清晰、不与 3.3 的凝练 prompt 耦合。
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
    """取本会话全部自由对话 + 全部线索，拼成材料文本（Task 3/5/6 共用取材步骤）。"""
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

    供前端刷新/断线重连时读取完成度、当前问题与就绪位——本函数**不重新判定、不调
    LLM**，纯粹是「读取已持久化状态」（区别于 `refresh_guidance` 的判定+生成语义，
    Dev Notes 已论证二者用途不同）。用请求注入 session（同 `get_pending_card`/
    `list_free_messages` 等既有只读端点范式，无 provider 记账、无需独立 session）。

    无会话/`guidance_state` 为 `None`（guided 会话或异常路径）→ 返回全 `missing` 初始态
    （不 404，避免前端要额外处理 404 分支——Task 8 已定档倾向此选择）。
    """
    exploration_session = await _guard_free_session(
        session, user_id=user_id, project_id=project_id
    )
    if exploration_session is None or exploration_session.guidance_state is None:
        return exploration_service._initial_guidance_state()
    return exploration_session.guidance_state


# ---------- 完成度判定 + 下一问生成（Task 3/6 共用核心，AC1/AC2/AC7/AC9） ----------


def _missing_fields(guidance_state: dict) -> list[str]:
    """从 `guidance_state.fields` 中取出仍为 `missing` 的字段名（保持 `_BACKBONE_FIELDS` 顺序）。"""
    fields = guidance_state["fields"]
    return [
        key
        for key, _ in story_settle_agent._BACKBONE_FIELDS
        if fields.get(key) == "missing"
    ]


def _judge_system_prompt() -> str:
    """完成度判定 + 单项下一问生成的 system prompt（AC2）。

    只要求模型对「仍是 missing 的字段」二元判断是否已有足够材料（filled/仍缺），**不允许
    模型输出 `skipped`**——`skipped` 只能由用户主动跳过触发（Task 6），模型即便声称某项
    应跳过也会被防御性解析忽略（`_parse_judge_response` 只认「已清楚」这一种状态转移）。
    """
    backbone_hint = "\n".join(label for _, label in story_settle_agent._BACKBONE_FIELDS)
    return f"""你在帮一位读者判断他正在构思的网文小说，下面这些设定要点是否已经聊得足够清楚。

设定要点清单（只需判断下面列出的这些，按「标签：内容」输出，标签必须一字不差）：
{backbone_hint}

读下面的对话材料，对清单里每一项判断：
- 如果材料里已经有足够信息回答这一项，输出「标签：已清楚」。
- 如果材料完全没提到或信息太少，输出「标签：还缺」。

判断完所有项后，另起两行，从判为「还缺」的项里选**恰好一个**你觉得最该先问的，用这个
格式单独输出（标签必须和上面清单里的标签一字不差，用于标注你选中的是哪一项）：
追问项：<你选中的这一项的标签>
问题：<针对这一项、用一句自然的口语化提问>

要求：
- 只根据材料实际内容判断，不要因为「感觉应该有」就判「已清楚」。
- 「追问项」「问题」两行只能针对判为「还缺」的项之一，且必须是同一项；如果所有项都
  「已清楚」，不要输出这两行。
- 问题要具体、口语化，像朋友聊天一样问一句，不要泛泛地问「说说你的故事」。
- 不要输出任何其他文字、不要编号、不要 Markdown。"""


def _parse_judge_response(
    content: str,
) -> tuple[dict[str, str], str | None, str | None]:
    """解析判定响应：{被判为 filled 的字段 key: "filled"} + 选中的下一问文本 + 该问题
    对应的字段 key。

    防御性解析（仿 `story_settle_agent._parse_settle_response`）：以「已清楚」为前缀
    （`startswith`，而非严格 `==`）判定 → filled——容忍模型输出「已清楚。」「已清楚，但
    还可以更细」等带标点/修饰语的变体（code review 修复：严格相等曾导致这类变体被误判为
    未清楚，字段持续卡在 missing）；（「还缺」不产生任何 dict 项——维持 missing 是「不改」
    的默认态，调用方不需要显式写 missing）；「追问项：」行取其后标签解析出字段 key（未知/
    未命中标签 → `None`，交由调用方 fallback）；「问题：」行取其后文本作下一问；畩形/
    未命中标签不崩溃、静默跳过。
    """
    label_to_key = {label: key for key, label in story_settle_agent._BACKBONE_FIELDS}
    updates: dict[str, str] = {}
    question: str | None = None
    question_field: str | None = None
    for raw in content.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("追问项") and ("：" in line or ":" in line):
            sep = "：" if "：" in line else ":"
            _, _, label = line.partition(sep)
            question_field = label_to_key.get(label.strip())
            continue
        if line.startswith("问题") and ("：" in line or ":" in line):
            sep = "：" if "：" in line else ":"
            _, _, text = line.partition(sep)
            text = text.strip()
            if text:
                question = text
            continue
        if "：" not in line and ":" not in line:
            continue
        sep = "：" if "：" in line else ":"
        label, _, value = line.partition(sep)
        label, value = label.strip(), value.strip()
        if label not in label_to_key:
            continue
        if value.startswith("已清楚"):
            updates[label_to_key[label]] = "filled"
    return updates, question, question_field


async def _judge_and_select_question(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    material_text: str,
) -> tuple[dict[str, str], str | None, str | None]:
    """一次 LLM 调用：对 7 项主干判定 filled/仍缺 + 从仍缺项中选一个生成下一问 + 其字段 key。

    调用方（`refresh_guidance`/`skip_current_field`）在各自的护栏/session 语境下调用本
    函数，本函数不做租户/护栏校验、不落库——纯粹是「一次 LLM 结构化调用 + 解析」的可复用
    单元，抽出为私有 helper 避免 Task 3（对话后刷新）与 Task 6（跳过后推进下一问）各自
    重复 prompt 组装与解析逻辑。
    """
    settings = get_settings()
    provider = await get_provider_for_user(session, user_id, project_id=project_id)
    messages: list[Message] = [
        {"role": "system", "content": _judge_system_prompt()},
        {"role": "user", "content": f"对话材料：\n{material_text}"},
    ]
    result: ChatResult = await provider.chat(
        messages, model=settings.deepseek_model_fast, max_tokens=_MAX_TOKENS
    )
    return _parse_judge_response(result.content)


def _apply_judge_result(
    guidance_state: dict,
    updates: dict[str, str],
    question: str | None,
    question_field: str | None = None,
) -> dict:
    """把判定结果合并进 `guidance_state`（AC2 单调性核心）：组装新结构、不原地改传入对象。

    - 已 `filled`/`skipped` 的项：保留原状态，不因本轮判定被打回 `missing`（AC2 硬约束、
      V1 无撤销机制、单向前进）。
    - 新判为 `filled` 的 `missing` 项：更新为 `filled`。
    - 其余仍 `missing` 的项：保持 `missing`。
    - 若判定后仍有 `missing` 项且给出了 `question`：写入 `current_field`/`current_question`
      ——`current_field` 优先取模型通过「追问项：」标注、且仍在 `still_missing` 里的字段
      （`question_field`），确保展示给用户的字段与问题文本实际针对的字段一致；只有当模型
      未标注/标注了未知标签/标注的字段已不在 `still_missing`（偏离格式）时，才 fallback
      到 `still_missing` 固定顺序的第一项（避免模型完全不配合格式时陷入无问题可问的
      空白态）。
    - 若判定后已无 `missing` 项：`current_field`/`current_question` 清空、`ready_to_settle`
      置真（AC7）。
    """
    fields = dict(guidance_state["fields"])
    for key, new_status in updates.items():
        if fields.get(key) == "missing":
            fields[key] = new_status

    still_missing = [
        key for key, _ in story_settle_agent._BACKBONE_FIELDS if fields.get(key) == "missing"
    ]
    if not still_missing:
        return {
            "fields": fields,
            "current_field": None,
            "current_question": None,
            "ready_to_settle": True,
        }
    # 仍有缺项：若本轮成功生成了问题，优先用模型标注的字段（question_field）作为
    # current_field——保证展示的字段与问题文本语义一致；标注缺失/失效时才 fallback 到
    # still_missing 固定顺序第一项。若本轮解析未拿到 question（模型偏离格式），保留上一轮
    # current_field/current_question 不变，避免无问题可问的空白态。
    if question is not None:
        current_field = (
            question_field if question_field in still_missing else still_missing[0]
        )
        return {
            "fields": fields,
            "current_field": current_field,
            "current_question": question,
            "ready_to_settle": False,
        }
    return {
        "fields": fields,
        "current_field": guidance_state.get("current_field"),
        "current_question": guidance_state.get("current_question"),
        "ready_to_settle": False,
    }


async def refresh_guidance(
    session: AsyncSession, *, user_id: uuid.UUID, project_id: uuid.UUID
) -> dict:
    """一轮自由对话结束后刷新导航状态（AC2/AC7/AC9 核心）：判完成度 + 选一个下一问。

    **由 `free_explorer_agent.stream_free_chat` 在该轮 `done` 后调用**（同一独立 session
    内，紧邻两次消息 commit 之后）——完成度刷新是「每轮对话的副作用」，不是用户主动触发
    的操作，故本函数不独立暴露 HTTP 端点（Dev Notes 已论证）。

    1. 租户守卫 + mode 守卫（`_guard_free_session`）。
    2. 无会话（理论上 `enter_exploration` 已保证存在，此处防御性兜底）→ 返回初始 `missing`
       态，不调 LLM。
    3. 已是 `skipped` 的项本轮不重新判定（AC2 硬约束）：只把仍 `missing` 的项喂给模型。
       若已无 `missing` 项（判定发生在 `ready_to_settle` 已真之后，理论不该被调用，防御性
       短路），直接返回当前态，不调 LLM。
    4. 护栏 `check_quota`（**在确定要调 provider 之前**，陷阱②）——**触顶时静默降级**：
       返回当前已持久化的 `guidance_state`（不重新判定、不更新 current_question），让对话
       主链路的成功不被这个「追问逻辑」的增值步骤连累（Dev Notes「护栏降级处理」已详述
       取舍：`stream_free_chat` 是用户能直接感知的主链路，本函数是它 done 之后的副作用，
       两者失败容忍策略的粒度不同）。
    5. 一次 LLM 调用判定 + 选下一问（`_judge_and_select_question`）；解析失败（无任何字段
       判定、也无 question）→ 保留上一轮 `guidance_state` 不变（不因单次解析失败误判倒退）。
    6. 合并结果（`_apply_judge_result`）→ 落库（`update_guidance_state`）+ commit。

    返回最新的 `guidance_state`（内部 snake_case 结构，供调用方/router 转 schema）。
    """
    exploration_session = await _guard_free_session(
        session, user_id=user_id, project_id=project_id
    )
    if exploration_session is None or exploration_session.guidance_state is None:
        return exploration_service._initial_guidance_state()

    guidance_state = exploration_session.guidance_state
    missing_keys = _missing_fields(guidance_state)
    if not missing_keys:
        return guidance_state

    try:
        await usage_service.check_quota(session, user_id)
    except ErrorEnvelope:
        # 护栏触顶：静默降级，不重新判定、不更新 current_question（Dev Notes 已论证）。
        return guidance_state

    material_text = await _gather_material(
        session,
        user_id=user_id,
        project_id=project_id,
        session_id=exploration_session.id,
    )
    updates, question, question_field = await _judge_and_select_question(
        session, user_id=user_id, project_id=project_id, material_text=material_text
    )
    if not updates and question is None:
        # 解析失败兜底：模型偏离格式、一个字段判定和 question 都没拿到——保留上一轮态，
        # 不因单次解析失败误判倒退（同 story_clue_repo.update_clue_value 的保守写入精神）。
        return guidance_state

    new_state = _apply_judge_result(guidance_state, updates, question, question_field)
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

    比 `_judge_system_prompt` 更收窄——零对话时没有材料可判定完成度（7 项恒 missing），
    本 prompt 不要求判定，只要求生成开场问题，故不复用同一份 prompt（Dev Notes/Task 4
    已明确二者不同）。
    """
    return f"""你在陪一位读者聊他脑中的小说想法，他刚选了想先聊「{field_label}」这个方向。

请针对「{field_label}」，用一句自然、口语化的问题开场，帮他把这个方向的念头说清楚。

要求：
- 只输出这一句问题，不要输出任何其他文字、不要编号、不要引号包裹、不要 Markdown。
- 问题要具体、像朋友聊天一样问，不要泛泛地问「说说你的故事」。"""


def _next_question_system_prompt(field_label: str) -> str:
    """针对已知的单个字段生成下一问的 system prompt（Task 6 跳过后推进用）。

    与 `_judge_system_prompt` 不同：本 prompt **不做 7 项判定**，字段已由调用方确定
    （`skip_current_field` 从 `still_missing` 里选出），只要求结合已有对话材料针对这一
    个字段生成一句自然的追问——比全量判定更轻量，避免"跳过 + 立刻生成新问题"承担两次
    结构化判定调用（Task 6 原文已明确这一点）。
    """
    return f"""你在陪一位读者聊他脑中的小说想法，接下来想聊「{field_label}」这个方向。

读下面已有的对话材料（如果有），针对「{field_label}」，用一句自然、口语化的问题接着问，
帮他把这个方向的念头说清楚。

要求：
- 只输出这一句问题，不要输出任何其他文字、不要编号、不要引号包裹、不要 Markdown。
- 问题要具体、像朋友聊天一样问，不要泛泛地问「说说你的故事」，也不要重复材料里已经问过
  的内容。"""


async def _generate_question_for_field(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    field_key: str,
    material_text: str,
) -> str | None:
    """针对一个已确定的字段生成一句追问（Task 6 跳过后推进复用）。不做判定、不落库。

    调用方（`skip_current_field`）负责护栏与落库；本函数只负责一次 LLM 调用 + 取值，
    空产返回 `None` 交由调用方决定降级策略（保留原 `current_field=None` 空白态）。
    """
    field_label = dict(story_settle_agent._BACKBONE_FIELDS)[field_key]
    settings = get_settings()
    provider = await get_provider_for_user(session, user_id, project_id=project_id)
    messages: list[Message] = [
        {"role": "system", "content": _next_question_system_prompt(field_label)},
        {"role": "user", "content": f"对话材料：\n{material_text}"},
    ]
    result: ChatResult = await provider.chat(
        messages, model=settings.deepseek_model_fast, max_tokens=_MAX_TOKENS
    )
    return result.content.strip() or None


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
       前端流程保证的调用时机而非用户可直接触发的破坏性操作，Task 4 已定档）。
    3. 无会话（尚未 `enter_exploration`）→ 视为「还没有材料」，先返回初始态（不建会话——
       建会话是 `enter_exploration`/`stream_free_chat` 的职责，本函数不越权）。
    4. **单调性防护（code review 修复）**：`entry` 映射到的字段若已是 `filled`/`skipped`
       （例如零消息状态下 `start→skip` 后再次对同一 entry 调用 `start`），直接幂等返回
       当前态、不重新生成问题——与 `_apply_judge_result` 对「单向前进、无撤销」的保证
       对齐，避免把已跳过/已完成的字段重新打开成 `current_field`。
    5. 护栏 `check_quota`（provider 前，陷阱②）——托管触顶抛 429（本操作是零对话开场的
       首次调用，用户尚未投入任何对话内容，直接报错让前端提示重试是合理的，不做静默降级）。
    6. 一次 LLM 调用生成开场问题 → 写入 `current_field`/`current_question`（其余 6 项仍
       `missing`）→ 落库 + commit。
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
            # 幂等返回当前态，不重新打开已解决的字段（单调性，同 _apply_judge_result）。
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
        question = result.content.strip() or f"想先聊聊「{field_label}」，你有什么想法？"

        new_state = {
            "fields": dict(guidance_state["fields"]),
            "current_field": field_key,
            "current_question": question,
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


# ---------- 按需回答思路（Task 5，AC4） ----------


def _suggest_system_prompt(field_label: str, question: str) -> str:
    """按需回答思路的 system prompt（AC4）：生成 2-4 个与当前问题相关的候选回答。"""
    return f"""你在帮一位读者想「{field_label}」这个问题可能怎么回答，他被下面这个问题卡住了：
{question}

结合已有的对话材料（如果有），给出 2 到 4 个不同角度的候选回答，帮他打开思路。每个候选
回答独立一行，不要编号、不要标签前缀，就是可以直接当作他自己说的话。

要求：
- 每行是一个完整、可以直接采用的回答，不是零散的关键词。
- 尽量贴合已有材料里透出的调性，不要跑题到完全无关的方向。
- 只输出候选回答本身，不要输出任何其他说明文字、不要 Markdown。"""


def _parse_suggestions(content: str) -> list[str]:
    """解析按需思路响应：逐行取非空文本，最多取前 4 行（AC4「2-4 个」上界防御）。"""
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    return lines[:4]


async def suggest_answers(
    *, user_id: uuid.UUID, project_id: uuid.UUID
) -> list[str]:
    """按需生成当前问题的 2-4 个候选回答（AC4）：只读建议，不落库、不改 `guidance_state`。

    **独立 session 自管**（陷阱⑩，同上）。

    1. 租户守卫 + mode 守卫。
    2. 无 `current_field`（已就绪或未初始化）→ 400 `no_current_question`。
    3. 取材 + 一次 LLM 调用生成候选回答。
    4. 下限兜底：解析到的候选数 < 2（AC4 要求"2-4 个"）→ 502 `generate_failed`（同
       `settle_into_profile`/`style_anchor_agent` 空产先例；code review 修复：此前只
       在 0 个时报错，未强制 AC4 字面下限）。
    5. 护栏 `check_quota`（provider 前，陷阱②）——触顶直接报错（用户主动点击「看看思路」
       这个增值操作，失败了大不了不看，无副作用可容忍，与 Task 6 跳过动作的取舍不同）。

    **不落库**（AC4 核心）：本操作是只读建议，用户可以看了不选，不产生任何持久化副作用。
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
        field_label = dict(story_settle_agent._BACKBONE_FIELDS)[field_key]
        question = guidance_state["current_question"] or ""

        await usage_service.check_quota(session, user_id)

        material_text = await _gather_material(
            session,
            user_id=user_id,
            project_id=project_id,
            session_id=exploration_session.id,
        )
        settings = get_settings()
        provider = await get_provider_for_user(session, user_id, project_id=project_id)
        messages: list[Message] = [
            {"role": "system", "content": _suggest_system_prompt(field_label, question)},
            {"role": "user", "content": f"对话材料：\n{material_text}"},
        ]
        result: ChatResult = await provider.chat(
            messages, model=settings.deepseek_model_fast, max_tokens=_MAX_TOKENS
        )
        suggestions = _parse_suggestions(result.content)
        if len(suggestions) < 2:
            # AC4 要求"2-4 个"候选——code review 修复：此前只在 0 个时才报错，模型偏离
            # 格式只解析出 1 个候选也会以 200 放行，未强制字面下限。
            raise ErrorEnvelope(
                code="generate_failed",
                message="生成失败，请稍后重试。",
                http_status=502,
            )
        return suggestions


# ---------- 跳过 + 谨慎归纳（Task 6，AC6） ----------


def _skip_summary_system_prompt(field_label: str) -> str:
    """跳过归纳的 system prompt（AC6）：比判定/建议更保守，允许合法地「什么都不说」。"""
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
    3. **状态转移优先生效**（Dev 判断，Task 6 二选一）：先把 `fields[current_field]` 标记
       `skipped`、算出 `still_missing`、落库 + commit——这一步不依赖 LLM，用户明确要跳过
       是确定性动作，不该被额度门禁挡住。
    4. **跳过后立即推进下一问**（Task 6 原文要求「直接推进到下一个缺失项」，code review
       修复：此前只是清空为空白态、要等下一轮对话才推进）——若 `still_missing` 非空，
       护栏 `check_quota` 通过后针对 `still_missing` 固定顺序第一项调用
       `_generate_question_for_field`（**不复用 `_judge_and_select_question` 的 7 项
       判定**——`fields` 状态本身已知，只需为已选定的字段生成一句问题，Task 6 原文明确
       "不必额外调用 LLM 结构化判定 7 项"）；生成成功则第二次落库写入
       `current_field`/`current_question`。护栏 429 或生成为空时静默保持上一步已提交的
       空白态（`current_field=None`）——不影响已生效的 `skipped` 状态转移，前端据此展示
       「已跳过，继续聊聊其他方面」的过渡态、等下一轮对话自然推进（与谨慎归纳同款失败
       容忍粒度）。
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
        still_missing = [
            key
            for key, _ in story_settle_agent._BACKBONE_FIELDS
            if fields.get(key) == "missing"
        ]
        ready_to_settle = not still_missing
        new_state: dict[str, object] = {
            "fields": fields,
            "current_field": None,
            "current_question": None,
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

        # 4. 跳过后立即推进下一问（Task 6 原文要求，code review 修复）：still_missing
        #    非空时护栏通过后为固定顺序第一项生成一句追问，成功才二次落库覆盖
        #    current_field/current_question；护栏 429/生成为空则保留步骤 3 已提交的
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
                next_question = await _generate_question_for_field(
                    session,
                    user_id=user_id,
                    project_id=project_id,
                    field_key=next_field,
                    material_text=material_text,
                )
                if next_question is not None:
                    new_state = {
                        "fields": fields,
                        "current_field": next_field,
                        "current_question": next_question,
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
        messages: list[Message] = [
            {"role": "system", "content": _skip_summary_system_prompt(field_label)},
            {"role": "user", "content": f"对话材料：\n{material_text}"},
        ]
        result: ChatResult = await provider.chat(
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
