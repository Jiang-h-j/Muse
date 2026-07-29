"""Free Explorer Agent：自由探索的多轮对话 + 依对话自动整理线索（Story 2.6 AC2/AC5）。

**与 `explorer_agent.py`（2.3 引导 Agent）职责独立**：后者 docstring 明写"引导 Agent 的唯一
真实 LLM 职责"（理解自述、单轮凝练），本模块服务自由探索的两个不同职责——多轮上下文对话
（`stream_free_chat`）与依对话自动整理线索（`extract_clues`）。二者 system prompt、消息
组装逻辑、护栏调用时机均不同，拆两个模块避免条件分支缠绕，延续「引导 vs 自由两条链路
架构上独立」的既定项目基调（epics.md:454）。

分层（architecture.md router→service→provider）：本模块是探索域 service，经 LLMProvider
抽象调 LLM（禁直调 openai），生成前过 mode 守卫 + check_quota 护栏，Provider 层自动记账（AR14）。

session 生命周期（陷阱⑩，仿 explorer_agent.py 模块 docstring 论证）：任何"在 web 请求上跑
流式 + MeteredProvider 记账"的场景都用独立 `async_session_maker()` 自管 session——SSE 客户端
早断时 `MeteredProvider` 的 finally 兜底记账仍需要一个存活的 session，不能依赖请求注入 session
的生命周期。`extract_clues` 虽非流式，但同样调用 provider，为保持一致范式也用独立 session。
"""

import uuid
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from muse.core.db import async_session_maker
from muse.core.settings import get_settings
from muse.models.exploration_message import ExplorationMessage
from muse.models.project import Project
from muse.providers.base import ChatResult, Message, StreamChunk
from muse.providers.factory import get_provider_for_user
from muse.repositories import exploration_repo, project_repo, story_clue_repo
from muse.services import exploration_service, usage_service

# 自由对话是轻交互任务 → 快档（deepseek-v4-flash）。快档是推理模型（2.1 Debug Log 实测：
# reasoning_content 先吃 token 预算），留足余量避免正文被挤空（同 2.3 陷阱⑥考量）。
_CHAT_MAX_TOKENS = 1024
# 线索整理是一次性结构化提炼，同为轻任务，快档 + 稍大余量（需覆盖最多 4 槙位的输出）。
_EXTRACT_MAX_TOKENS = 1024

# 自由探索 Agent 人格（AC2，NFR1 去 AI 味红线 [[project_muse_quality_redline]]）。
# 只讨论、不代答、不直接改设定——呼应原型固定文案的语气（app.js:1044-1061「不会替你直接
# 改动设定」），面向大众网文读者口吻（非文学腔）。
_CHAT_SYSTEM_PROMPT = """你在陪一位读者自由聊他脑中的小说想法。

他想到哪聊到哪，你的任务是跟他讨论、帮他把念头往下延展——问一句启发性的问题，或者顺着
他的话往下接一句，让他自己继续想清楚人物、冲突、世界观。

要求：
- 只讨论，绝不替他直接改设定、绝不替他做决定，最终怎么定是他的事。
- 面向大众网文读者，说人话，语气自然像朋友聊天，不要文绉绉的书面腔。
- 每次回复简短（1-3 句话），不要长篇大论。

绝对不要：
- 说「作为 AI」「我理解您的意思是」之类的话。
- 用 Markdown、列表、标题等任何格式。
- 一次抛出很多个问题或建议——保持对话感，一次只接一个话头。

直接说你想说的话，不要任何前后缀。"""

# 4 个预设线索槙位的 key → 中文标签（Task 4 播种与本模块整理端点共用，供 prompt 报送）。
PRESET_CLUE_KEYS: dict[str, str] = {
    "opening": "最初的念头",
    "protagonist": "主角",
    "conflict": "核心冲突",
    "world": "世界与氛围",
}


def _build_chat_messages(
    history: list[ExplorationMessage], user_message: str
) -> list[Message]:
    """组装自由对话的 LLM 消息历史：system prompt + 历史消息（角色映射）+ 新用户消息。

    **角色映射（易错点）**：DB 里 role="agent" 的历史行须转换为 provider 消息的
    role="assistant"（`providers/base.py` Message 是 OpenAI 兼容格式，只认
    system/user/assistant），role="user" 原样保留。
    """
    messages: list[Message] = [{"role": "system", "content": _CHAT_SYSTEM_PROMPT}]
    for item in history:
        role = "assistant" if item.role == "agent" else "user"
        messages.append({"role": role, "content": item.content or ""})
    messages.append({"role": "user", "content": user_message})
    return messages


def _build_extract_messages(
    history: list[ExplorationMessage], pending_keys: list[str]
) -> list[Message]:
    """组装线索整理的 LLM 消息：system prompt（含固定输出格式要求）+ 完整对话历史。

    只为 `pending_keys`（未被用户编辑的槙位）生成输出要求——已编辑的槙位连"存在"都不
    告诉模型，从数据源头杜绝模型"顺手"改到不该碰的槙位（Dev Notes 双重防御的第一层）。

    对未知 key 用 `.get()` 跳过（防御：历史迁移/手工改库出现 PRESET_CLUE_KEYS 之外的
    clue_key 时不 KeyError 崩，调用方 extract_clues 已在数据源头过滤，此处是二重保险）。
    """
    labels = [PRESET_CLUE_KEYS[key] for key in pending_keys if key in PRESET_CLUE_KEYS]
    lines_hint = "\n".join(f"{label}：<内容>" for label in labels)
    system_prompt = f"""你在帮读者把和 Explorer Agent 的自由讨论整理成几条故事线索。

读下面完整的对话记录，为以下每一项各输出一行，严格用「标签：内容」的格式，标签必须
和下面列出的一字不差：
{lines_hint}

要求：
- 只根据对话里读者实际说过的内容提炼，绝不杜撰对话里没提到的信息。
- 某一项对话里完全没提及、没有新信息可提炼，就输出「标签：尚未确定」。
- 每项内容尽量简洁，一句话概括即可。
- 只输出这{len(labels)}行，不要输出任何其他文字、不要编号、不要 Markdown。"""

    messages: list[Message] = [{"role": "system", "content": system_prompt}]
    conversation_text = "\n".join(
        f"{'用户' if item.role == 'user' else 'Agent'}：{item.content or ''}"
        for item in history
    )
    messages.append(
        {
            "role": "user",
            "content": conversation_text or "（对话尚未开始，还没有任何内容。）",
        }
    )
    return messages


def _parse_extract_response(content: str, pending_keys: list[str]) -> dict[str, str]:
    """解析线索整理响应：按固定前缀逐行匹配，只接受本次请求报送过的槙位集合内的行。

    防御性设计（Dev Notes 双重防御的第二层）：模型偏离格式也不崩溃，未成功解析的槙位
    不出现在返回字典里（调用方保持原值不变）。「尚未确定」原样作为 value 落库（与
    story_clue 空串占位是两套语义——此处是模型明确表达"没有新信息"，不强行清空）。
    """
    label_to_key = {label: key for key, label in PRESET_CLUE_KEYS.items()}
    pending_labels = {
        PRESET_CLUE_KEYS[key] for key in pending_keys if key in PRESET_CLUE_KEYS
    }
    updates: dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if "：" not in line and ":" not in line:
            continue
        sep = "：" if "：" in line else ":"
        label, _, value = line.partition(sep)
        label = label.strip()
        value = value.strip()
        if label not in pending_labels or not value:
            continue
        updates[label_to_key[label]] = value
    return updates


async def preflight_free_chat(
    session: AsyncSession, *, user_id: uuid.UUID, project_id: uuid.UUID
) -> Project:
    """流建立前的 HTTP 前置校验：租户守卫 + mode 守卫 + 护栏（AC2，仿 2.3 preflight_interpret）。

    SSE 端点在返回 EventSourceResponse **之前**调用本函数——流一旦建立即提交 HTTP 200，
    之后 generator 内抛错只能走 error 事件、无法再改状态码。用请求注入的 web session 做
    只读校验（不写库、无记账），与后续流式记账用的独立 session 职责分离。

    返回 project 供调用方复用，避免端点/生成两处各查一次。
    """
    project = await project_repo.get_owned_project(session, project_id, user_id)
    if project is None:
        raise exploration_service._exploration_not_found()
    exploration_service._require_project_mode(project, "free")
    await usage_service.check_quota(session, user_id)
    return project


async def stream_free_chat(
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    user_message: str,
) -> AsyncIterator[str]:
    """自由对话一轮：组装历史 → 流式产出 Agent 回复正文 → 生成成功后落库用户消息 + 回复（AC2/AC6）。

    **独立 session 自管**（陷阱⑩）：与 explorer_agent.interpret_guided_answer 同款理由。

    **生成成功后才落库（Jianghj 2026-07-29 code review 裁定）**：用户消息不在生成前落库，
    而是等 Agent 回复完整产出、确认非空后，才先 commit 用户消息（事务 A）、再 commit Agent
    回复（事务 B）。任何生成中断（客户端断连 CancelledError）、provider 异常、或空产都不落
    任何库——session 上下文退出时自动 rollback，杜绝"仅有用户消息无 Agent 回复"的孤儿对话
    （否则前端恢复时看到悬空用户消息，可能误判生成中卡死或重发致重复）。

    **两次独立 commit（关键技术陷阱，Dev Notes 已详细论证）**：用户消息与 Agent 回复分两次
    独立 commit——若共享同一事务，PostgreSQL 的 now() 在事务内恒返回事务开始时刻，两行会拿到
    完全相同的 created_at，破坏"按 created_at 升序恢复对话顺序"的前提。分两次 commit 天然保证
    不同事务时刻，无需引入额外的 sequence 列。

    产出 **content 正文文本块**（str）逐块 yield；reasoning 片段静默丢弃（同 2.3 范式）。
    空产兜底：流正常结束却无任何正文时不落任何库，交由调用方（SSE 端点）改发 error 事件、
    不发空 done。
    """
    settings = get_settings()
    async with async_session_maker() as session:
        # 1. 重校验租户 + mode + 护栏（独立 session 上，同 interpret_guided_answer 范式）。
        project = await project_repo.get_owned_project(session, project_id, user_id)
        if project is None:
            raise exploration_service._exploration_not_found()
        exploration_service._require_project_mode(project, "free")
        await usage_service.check_quota(session, user_id)

        # 2. get-or-create 会话，拿 session_id（mode 恒为 free，已由上面守卫保证）。
        exploration_session = await exploration_service.enter_exploration(
            session, user_id=user_id, project_id=project_id
        )

        # 3. 取本会话既有 free 消息组装历史 + 新用户消息。**用户消息此刻只在内存里、暂不落库**
        #    ——生成成功后（步骤 5）才落库，避免中断/异常/空产时留下孤儿用户消息。
        history = await exploration_repo.list_free_messages_by_session(
            session,
            user_id=user_id,
            project_id=project_id,
            session_id=exploration_session.id,
        )
        messages = _build_chat_messages(history, user_message)

        # 4. 构造带记账 Provider + 流式产出正文（reasoning 静默丢弃，同 2.3 范式）。
        provider = await get_provider_for_user(session, user_id, project_id=project_id)
        parts: list[str] = []
        async for event in provider.stream(
            messages,
            model=settings.deepseek_model_fast,
            max_tokens=_CHAT_MAX_TOKENS,
        ):
            if isinstance(event, StreamChunk) and event.kind == "content":
                parts.append(event.delta)
                yield event.delta

        # 5. 流正常结束且有正文后，先落用户消息（事务 A）、再落 Agent 回复（事务 B），两次
        #    独立 commit 保证 created_at 严格递增（保序）。空产不落任何库（调用方 SSE 端点据
        #    「累计正文是否为空」决定发 done 还是 error）。中断/异常在此之前发生 → 均不落库。
        answer = "".join(parts)
        if answer.strip():
            await exploration_repo.append_free_message(
                session,
                user_id=user_id,
                project_id=project_id,
                session_id=exploration_session.id,
                role="user",
                content=user_message,
            )
            await session.commit()
            await exploration_repo.append_free_message(
                session,
                user_id=user_id,
                project_id=project_id,
                session_id=exploration_session.id,
                role="agent",
                content=answer,
            )
            await session.commit()


async def extract_clues(
    *, user_id: uuid.UUID, project_id: uuid.UUID
) -> dict[str, str]:
    """Agent 依对话自动整理线索（AC5，硬 AC）：只更新未被用户编辑的预设槙位。

    **独立 session 自管**（同 stream_free_chat/陷阱⑩一致范式，虽非流式但同样调用 provider）。

    1. 重校验租户 + mode。
    2. 取本会话 kind="preset" 且 user_edited=false 的槙位——已编辑的槙位不出现在待整理
       集合里，从数据源头杜绝模型"顺手"改到不该碰的槙位（Dev Notes 双重防御第一层）。
    3. 若无待整理槙位（全部已被用户编辑），直接返回空字典、不调用 provider（省成本）。
    4. 护栏 check_quota（在确定要调 provider 之后、调用之前）——refresh 每次都真实调 LLM，
       与 stream_free_chat 同属计费路径，托管额度触顶须同样拦下（否则触顶用户仍可高频刷
       refresh 无限消费）。放在步骤 3 之后：全部已编辑的空转分支本就不调 provider、无需过闸。
    5. 取本会话全部 free 对话历史，组装 system prompt 要求固定前缀输出。
    6. provider.chat()（非流式，一次性小结构化输出）。
    7. 解析响应（防御性，第二层防御），只更新成功解析的槙位 value，不改 user_edited
       （保持 false，仍可被后续整理继续覆盖，直到用户真正手动编辑一次）。

    返回更新后的 {clue_key: value} 映射供响应体。
    """
    settings = get_settings()
    async with async_session_maker() as session:
        project = await project_repo.get_owned_project(session, project_id, user_id)
        if project is None:
            raise exploration_service._exploration_not_found()
        exploration_service._require_project_mode(project, "free")

        exploration_session = await exploration_service.enter_exploration(
            session, user_id=user_id, project_id=project_id
        )

        all_clues = await story_clue_repo.list_clues_by_session(
            session,
            user_id=user_id,
            project_id=project_id,
            session_id=exploration_session.id,
        )
        pending_clues = {
            clue.clue_key: clue
            for clue in all_clues
            if clue.kind == "preset"
            and not clue.user_edited
            and clue.clue_key in PRESET_CLUE_KEYS
        }
        if not pending_clues:
            return {}

        # 确定要调 provider 才过护栏（空转分支已在上面 return，无需过闸）。托管触顶 429。
        await usage_service.check_quota(session, user_id)

        history = await exploration_repo.list_free_messages_by_session(
            session,
            user_id=user_id,
            project_id=project_id,
            session_id=exploration_session.id,
        )
        pending_keys = list(pending_clues.keys())
        messages = _build_extract_messages(history, pending_keys)

        provider = await get_provider_for_user(session, user_id, project_id=project_id)
        result: ChatResult = await provider.chat(
            messages,
            model=settings.deepseek_model_fast,
            max_tokens=_EXTRACT_MAX_TOKENS,
        )
        updates = _parse_extract_response(result.content, pending_keys)

        # 条件 UPDATE：整理期间用户若已手动编辑某槙位，该行 user_edited=true → 命中 0 行、
        # 跳过（AC5 竞态防护）。applied 只收真正写入的槙位，供响应如实汇报。
        applied: dict[str, str] = {}
        for clue_key, value in updates.items():
            written = await story_clue_repo.update_clue_value(
                session, clue=pending_clues[clue_key], value=value
            )
            if written:
                applied[clue_key] = value
        await session.commit()
        return applied
