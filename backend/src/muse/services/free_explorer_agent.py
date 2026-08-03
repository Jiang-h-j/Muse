"""Free Explorer Agent：自由探索的多轮对话 + 设定导航判定 + 依对话自动整理线索。

**2026-08-03 合并重构（消费用户反馈：聊天正文与「当前具体问题」不一致）**：此前
`stream_free_chat` 只产聊天正文，`guidance_agent.refresh_guidance` 在 `done` 后**再单独
调一次 LLM** 判定 7 项完成度 + 生成一句独立的「下一问」文本——两次调用互不知情，导致
聊天框里 Agent 已经问了 A、导航区显示的却是完全不相关的 B。本次把「聊天回复」与「判定
完成度 + 选下一问 + 生成候选回复」合并进**同一次 LLM 调用**：模型输出「聊天正文 +
分隔符 + 结构化判定块」，流式只把分隔符之前的正文推给前端（用户体验不变，仍是逐字流式
聊天），`done` 后解析分隔符之后的结构化块直接更新 `guidance_state`——不再有第二次独立
生成的问题文本，聊天框里的话本身就是唯一的「当前问题」事实源，从数据模型层面消除了
两次生成对不齐的可能性（而非只在 UI 层遮盖）。

`guidance_state` 相应不再存储 `current_question`（不需要独立展示区）；改存
`current_suggestions`——判定的同一次调用里一并生成 2-4 条针对当前追问方向的候选回复，
供前端贴在聊天框最新一条 Agent 消息下方（默认收起，用户点「没想好？看看几个思路」才
展开，不再需要为此单独发一次网络请求——候选内容已经在这次调用里生成好了）。

**与 `explorer_agent.py`（2.3 引导 Agent）职责独立**：后者 docstring 明写"引导 Agent 的唯一
真实 LLM 职责"（理解自述、单轮凝练），本模块服务自由探索的两个不同职责——多轮上下文对话
+ 设定导航判定（`stream_free_chat`）与依对话自动整理线索（`extract_clues`）。二者 system
prompt、消息组装逻辑、护栏调用时机均不同，拆两个模块避免条件分支缠绕，延续「引导 vs 自由
两条链路架构上独立」的既定项目基调（epics.md:454）。

分层（architecture.md router→service→provider）：本模块是探索域 service，经 LLMProvider
抽象调 LLM（禁直调 openai），生成前过 mode 守卫 + check_quota 护栏，Provider 层自动记账（AR14）。

session 生命周期（陷阱⑩，仿 explorer_agent.py 模块 docstring 论证）：任何"在 web 请求上跑
流式 + MeteredProvider 记账"的场景都用独立 `async_session_maker()` 自管 session——SSE 客户端
早断时 `MeteredProvider` 的 finally 兜底记账仍需要一个存活的 session，不能依赖请求注入 session
的生命周期。`extract_clues` 虽非流式，但同样调用 provider，为保持一致范式也用独立 session。
"""

import logging
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
from muse.services import exploration_service, guidance_agent, story_settle_agent, usage_service

logger = logging.getLogger("muse")

# 自由对话是轻交互任务 → 快档（deepseek-v4-flash）。快档是推理模型（2.1 Debug Log 实测：
# reasoning_content 先吃 token 预算），留足余量避免正文被挤空（同 2.3 陷阱⑥考量）。
_CHAT_MAX_TOKENS = 1024
# 线索整理是一次性结构化提炼，同为轻任务，快档 + 稍大余量（需覆盖最多 4 槙位的输出）。
_EXTRACT_MAX_TOKENS = 1024

# 自由探索 Agent 人格（AC2，NFR1 去 AI 味红线 [[project_muse_quality_redline]]）。
# 只讨论、不代答、不直接改设定——呼应原型固定文案的语气（app.js:1044-1061「不会替你直接
# 改动设定」），面向大众网文读者口吻（非文学腔）。
#
# 分隔符之后的结构化判定块**不会**流式推给前端（`stream_free_chat` 只转发分隔符之前的
# 正文），只用于本轮结束后原地解析、更新 `guidance_state`——聊天正文本身就是「当前问题」
# 的唯一事实源，不再有第二次独立调用去生成一份可能对不上的问题文本。
_GUIDANCE_SEPARATOR = "###GUIDANCE###"


def _chat_system_prompt() -> str:
    backbone_hint = "\n".join(label for _, label in story_settle_agent._BACKBONE_FIELDS)
    return f"""你在陪一位读者自由聊他脑中的小说想法。

他想到哪聊到哪，你的任务是跟他讨论、帮他把念头往下延展——问一句启发性的问题，或者顺着
他的话往下接一句，让他自己继续想清楚人物、冲突、世界观。

要求：
- 只讨论，绝不替他直接改设定、绝不替他做决定，最终怎么定是他的事。
- 面向大众网文读者，说人话，语气自然像朋友聊天，不要文绉绉的书面腔。
- 每次回复简短（1-3 句话），不要长篇大论。
- 你的回复本身就是你想问他的下一个具体问题（或者先接一句他刚才说的话，再自然带出这个
  问题）——这句话会被当作「当前正在问的问题」直接展示，不要只是空泛地附和。

绝对不要：
- 说「作为 AI」「我理解您的意思是」之类的话。
- 用 Markdown、列表、标题等任何格式。
- 一次抛出很多个问题或建议——保持对话感，一次只接一个话头。

直接说你想说的话，不要任何前后缀。

写完这句聊天回复后，**另起一行**，输出分隔符 {_GUIDANCE_SEPARATOR}，然后在分隔符之后
输出下面这个结构化判定块。**这一部分是必须输出的，每次回复都要输出，不能省略**——即使
所有项都判为「还缺」，也要完整输出清单 + 追问项 + 候选。这部分只供内部记录、绝不会展示
给读者，不必顾及口语化：

设定要点清单（判断下面列出的这些是否已经聊得足够清楚，按「标签：内容」输出，标签必须
一字不差）：
{backbone_hint}

对清单里每一项判断：
- 如果材料里已经有足够信息回答这一项，输出「标签：已清楚」。
- 如果材料完全没提到或信息太少，输出「标签：还缺」。

判断完所有项后，另起一行，从判为「还缺」的项里选**恰好一个**——必须是你刚才那句聊天
回复实际正在追问的那一项——用这个格式输出（标签必须和上面清单里的标签一字不差）：
追问项：<你选中的这一项的标签>

然后再给出 2 到 4 个候选回答，帮读者应对你刚才那句聊天回复里问的问题，每个候选回答
独立一行，格式：
候选：<一句可以直接当作读者自己说的话的回答>

要求：
- 「追问项」必须和你刚才那句聊天回复实际问的内容一致，不要选另一个话题。
- 每一条「候选」都要针对聊天回复里刚问的这个具体问题，不要跑题、不要泛泛而谈。
- **无论所有项是否已清楚，都必须输出候选**（只要还有「还缺」的项就一定有追问项、也就
  一定有候选）。只有当 7 项全部「已清楚」时，才不输出追问项和候选。
- 分隔符之后的内容严格按上述「标签：内容」格式逐行输出，不要输出任何其他说明文字、
  不要 Markdown、不要编号。"""


# 7 个预设线索槙位的 key → 中文标签（Task 4 播种与本模块整理端点共用，供 prompt 报送；
# 2.8 扩容到 7 项，key/顺序对齐 exploration_service._PRESET_CLUES 与
# story_settle_agent._BACKBONE_FIELDS——三处各自维护但语义须对齐，勿改动顺序）。
PRESET_CLUE_KEYS: dict[str, str] = {
    "genre": "题材",
    "core_appeal": "核心吸引力",
    "protagonist": "主角",
    "main_conflict": "主要冲突",
    "world_rules": "关键世界规则",
    "overall_tone": "整体气质",
    "opening_hook": "开篇钩子",
}


def _build_chat_messages(
    history: list[ExplorationMessage], user_message: str
) -> list[Message]:
    """组装自由对话的 LLM 消息历史：system prompt + 历史消息（角色映射）+ 新用户消息。

    **角色映射（易错点）**：DB 里 role="agent" 的历史行须转换为 provider 消息的
    role="assistant"（`providers/base.py` Message 是 OpenAI 兼容格式，只认
    system/user/assistant），role="user" 原样保留。历史里落库的 agent 消息内容已经是
    分隔符之前的纯聊天正文（`stream_free_chat` 落库时已切掉结构化判定块），本函数不需要
    再额外处理。
    """
    messages: list[Message] = [{"role": "system", "content": _chat_system_prompt()}]
    for item in history:
        role = "assistant" if item.role == "agent" else "user"
        messages.append({"role": role, "content": item.content or ""})
    messages.append({"role": "user", "content": user_message})
    return messages


# 结构化行前缀集合：用于流式转发时识别"这一行是判定块/候选块，不该流给用户看"。
# 与 _parse_chat_response 的逐行解析保持一致（候选/追问项/主干标签判定），避免两处漂移。
_BACKBONE_LABELS = {label for _, label in story_settle_agent._BACKBONE_FIELDS}
_STRUCTURED_LINE_PREFIXES = ("候选", "追问项", "###GUIDANCE###") + tuple(
    f"{label}：" for label in _BACKBONE_LABELS
) + tuple(f"{label}:" for label in _BACKBONE_LABELS)
# 流式转发时，未结束行需要保留的末尾字符数上限：覆盖最长结构化前缀（###GUIDANCE### 15 字符
# + 主干标签最长「关键世界规则」6 字 + 「：」1 = 7，取较大者 15）。pending_line 末尾这段
# 可能是结构化前缀的开头，未确定前不转发，避免候选行泄漏给用户。
_STRUCT_PREFIX_HOLD = max(len(p) for p in _STRUCTURED_LINE_PREFIXES)


def _is_structured_line(line: str) -> bool:
    """判断一行是否是结构化判定块/候选块的行（流式转发时须吞掉，不流给用户）。

    匹配 `候选`/`追问项`/`###GUIDANCE###`/`<主干标签>：` 任一前缀。主干标签判定容错：
    只要该行以「<主干标签>：」或「<主干标签>:」开头就算结构化行（无论后面是「已清楚」
    还是「还缺」），与 `_parse_chat_response` 的逐行解析口径一致。
    """
    stripped = line.lstrip()
    return stripped.startswith(_STRUCTURED_LINE_PREFIXES)


def _parse_chat_response(
    content: str,
) -> tuple[str, dict[str, str], str | None, list[str]]:
    """解析合并调用的完整响应：聊天正文 + 分隔符 + 结构化判定块（本次合并重构核心）。

    返回 (chat_text, field_updates, question_field, suggestions)：
    - chat_text：聊天正文（去首尾空白、剔除结构化行）——唯一落库的 agent 消息内容，
      也是唯一的「当前问题」事实源。
    - field_updates：{被判为已清楚的字段 key: "filled"}。
    - question_field：模型标注的「追问项」对应字段 key（未命中 → None，交由调用方 fallback）。
    - suggestions：候选回答列表（最多 4 条）。

    **容错策略（2026-08-03 修复间歇性空候选）**：模型经常不输出 `###GUIDANCE###` 分隔符
    （实测约 30-50% 概率漏掉），但候选行（`候选：xxx`）、追问项行、判定行其实散落在
    「聊天正文」里。若分隔符缺失就把整段当聊天正文，这些结构化行会被当聊天内容展示给
    用户、且候选解析不到。故改为：无论分隔符是否存在，都对**全文**逐行扫描——以行首前缀
    （`候选：`/`追问项：`/`<主干标签>：已清楚`）识别结构化行并解析，**剔除**它们后剩下
    的才是聊天正文。这样模型漏分隔符时也能拿到候选与判定，且聊天正文不会混进结构化残留。
    """
    idx = content.find(_GUIDANCE_SEPARATOR)
    # chat_lines 收集「非结构化」的行（剔除候选/追问项/判定行后剩下），用于组装聊天正文。
    chat_lines: list[str] = []
    guidance_block = content if idx == -1 else content[idx + len(_GUIDANCE_SEPARATOR) :]
    # 分隔符之前的部分若存在，默认全部是聊天正文（模型在分隔符之前一般不会混结构化行）。
    if idx != -1:
        chat_lines.append(content[:idx])

    label_to_key = {label: key for key, label in story_settle_agent._BACKBONE_FIELDS}
    updates: dict[str, str] = {}
    question_field: str | None = None
    suggestions: list[str] = []
    for raw in guidance_block.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("追问项") and ("：" in line or ":" in line):
            sep = "：" if "：" in line else ":"
            _, _, label = line.partition(sep)
            question_field = label_to_key.get(label.strip())
            continue
        if line.startswith("候选") and ("：" in line or ":" in line):
            sep = "：" if "：" in line else ":"
            _, _, text = line.partition(sep)
            text = text.strip()
            if text:
                suggestions.append(text)
            continue
        if "：" not in line and ":" not in line:
            # 非结构化行：归入聊天正文（模型漏分隔符时，聊天内容会跟结构化行混在一起）。
            chat_lines.append(line)
            continue
        label, _, value = line.partition("：" if "：" in line else ":")
        label, value = label.strip(), value.strip()
        if label in label_to_key:
            # 主干标签行（无论值是「已清楚」还是「还缺」）都算结构化行——剔除、不归入
            # 聊天正文。「已清楚」才产生 filled 更新，「还缺」只是不更新（维持 missing）。
            if value.startswith("已清楚"):
                updates[label_to_key[label]] = "filled"
            continue
        # 既不是候选/追问项/主干标签行，就当作普通聊天正文（可能是模型输出的对话内容里
        # 恰好带冒号的句子，不该被吞掉）。
        chat_lines.append(line)

    chat_text = "\n".join(part.strip() for part in chat_lines if part.strip()).strip()
    return chat_text, updates, question_field, suggestions[:4]


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
    """自由对话一轮：组装历史 → 流式产出 Agent 回复正文 → 生成成功后落库 + 更新导航状态。

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

    **2026-08-03 合并重构**：模型一次调用同时产出「聊天正文 + 分隔符 + 结构化判定块」。
    产出 **content 正文文本块**（str）逐块 yield，但只转发分隔符 `_GUIDANCE_SEPARATOR` 之前
    的部分——用滚动缓冲区做「流式安全分隔符检测」：分隔符可能被拆到两个 delta 之间，故每次
    只转发「确定不属于分隔符前缀」的那一段（保留末尾 `len(_GUIDANCE_SEPARATOR) - 1` 个字符
    不发，直到能确认它们不是分隔符开头或分隔符已完整出现）。reasoning 片段仍静默丢弃（同
    2.3 范式）。空产兜底：流正常结束却无任何聊天正文时不落任何库，交由调用方（SSE 端点）
    改发 error 事件、不发空 done。

    落库的 agent 消息内容是**分隔符之前的聊天正文**（不含结构化判定块，用户/前端永远看不到
    判定块原文）。判定块解析后直接更新 `guidance_state`（`guidance_agent.apply_chat_judgement`
    ），不再调用旧版 `refresh_guidance` 二次 LLM——完成度判定与候选回复现在和聊天正文出自
    同一次调用，天然对齐。
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
        #    raw_buffer 累积**完整**响应（含分隔符之后的判定块，供步骤 5 解析）。
        #    流式转发用**行级缓冲**（2026-08-03 修复间歇性空候选时的流式泄漏）：以行为单位
        #    累积，完整行判断是否结构化行（候选/追问项/主干标签判定/分隔符）——是则吞掉不
        #    转发、否则转发；遇到分隔符或首个结构化行即整体停止转发（此后都是判定块）。
        #    这样即使模型漏掉分隔符（实测约 30-50% 概率），候选行也不会流给用户看到。
        provider = await get_provider_for_user(session, user_id, project_id=project_id)
        raw_buffer = ""
        pending_line = ""
        stopped = False
        async for event in provider.stream(
            messages,
            model=settings.deepseek_model_fast,
            max_tokens=_CHAT_MAX_TOKENS,
        ):
            if not (isinstance(event, StreamChunk) and event.kind == "content"):
                continue
            raw_buffer += event.delta
            if stopped:
                continue
            # 把新 delta 追加到 pending_line，按换行符切分；每条完整行判断是否结构化。
            pending_line += event.delta
            while "\n" in pending_line:
                line, pending_line = pending_line.split("\n", 1)
                full_line = line + "\n"
                sep_idx = full_line.find(_GUIDANCE_SEPARATOR)
                is_struct = _is_structured_line(line)
                if sep_idx != -1:
                    # 分隔符出现：补发它之前的聊天正文残留（不丢字），此后停止转发。
                    head = full_line[:sep_idx].rstrip()
                    if head:
                        yield head
                    stopped = True
                    pending_line = ""
                    break
                if is_struct:
                    # 结构化行（候选/追问项/主干标签判定）：整行吞掉不转发，停止后续转发。
                    # 不补发任何内容——这一行本身就是结构化数据，不是聊天正文。
                    stopped = True
                    pending_line = ""
                    break
                yield full_line
            else:
                # 没有 \n 时，pending_line 是当前未结束的行。它的开头若已是结构化前缀，
                # 整行不转发（等下一个 delta 收完再判断）；否则转发"安全部分"——保留末尾
                # _STRUCT_PREFIX_HOLD 个字符不发（可能是结构化前缀的开头），其余转发。
                # 这样聊天正文仍能近实时流式可见，只有每行末尾最后十几字符延迟到行结束。
                if _is_structured_line(pending_line) or _GUIDANCE_SEPARATOR in pending_line:
                    continue
                safe = pending_line[: max(0, len(pending_line) - _STRUCT_PREFIX_HOLD)]
                if safe:
                    yield safe
                    pending_line = pending_line[len(safe):]

        # 5. 解析完整响应：无论分隔符是否存在，_parse_chat_response 都能从全文逐行
        #    提取结构化信息（2026-08-03 容错修复）。若流末尾仍有未转发的非结构化
        #    pending_line（最后一行无换行符结尾），补发保证聊天正文不丢字。
        if not stopped and pending_line and not _is_structured_line(pending_line):
            if _GUIDANCE_SEPARATOR not in pending_line:
                yield pending_line
        chat_text, field_updates, question_field, suggestions = _parse_chat_response(
            raw_buffer
        )

        # 6. 流正常结束且有聊天正文后，先落用户消息（事务 A）、再落 Agent 回复（事务 B），
        #    两次独立 commit 保证 created_at 严格递增（保序）。空产不落任何库（调用方 SSE
        #    端点据「累计正文是否为空」决定发 done 还是 error）。中断/异常在此之前发生 →
        #    均不落库。
        if chat_text.strip():
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
                content=chat_text,
            )
            await session.commit()

            # 7. 一轮对话落库成功后，把本次调用解析出的判定结果合并进 guidance_state
            #    （2.8 AC2/AC9，合并重构后不再二次调用 LLM）。这是「本轮对话的副作用」，
            #    同一独立 session 内追加调用。**本轮对话已成功落库**，故这里对任何异常
            #    一律吞掉只记日志——绝不让副作用失败冒泡到调用方 SSE 端点、把已成功的对话
            #    误报为 error（同旧版 refresh_guidance 副作用的失败容忍粒度）。
            try:
                await guidance_agent.apply_chat_judgement(
                    session,
                    user_id=user_id,
                    project_id=project_id,
                    field_updates=field_updates,
                    question_field=question_field,
                    suggestions=suggestions,
                    chat_text=chat_text,
                )
            except Exception:
                logger.exception(
                    "apply_chat_judgement 副作用失败，不影响本轮对话已成功落库的结果"
                )


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
