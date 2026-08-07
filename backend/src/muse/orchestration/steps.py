"""五段流水线的 step 实现（Story 4.2 V1 四段 + Story 5.2 第五段 data-agent）。

每段是一个独立可重试的 async 函数，遵循 story_settle_agent 的成熟范式：
- 独立 `async_session_maker()` 自管 session（陷阱⑩：调 provider 走 MeteredProvider 记账，
  finally 兜底记账须落在存活 session 上，不复用编排器/worker 的 session）。
- 租户守卫：`get_owned_project → None 抛二义合一 404`（NFR3）。
- `check_quota` 在 provider 调用之前（托管触顶抛 429）。
- `get_provider_for_user` 拿被 MeteredProvider 包裹的 provider（AC7：每段记账，绝不自建
  DeepSeekProvider）。
- 空产（LLM 完全跑偏、正文为空）抛 502 generate_failed。

段职责：
- context-agent：读 confirmed story_bible（12 字段 + style_profile）→ 组装写作任务书。
  **不调 LLM**（纯组装），故不过 check_quota/provider。V1 写前上下文 = 全量设定
  （confirmed 12 字段 + style_profile 锚点 + 去 AI 味词表约束）；「最近定稿章节」注入点
  预留 TODO（无章节表，4.4/Epic5 接入，epics.md:859③）。
- drafter：收写作任务书 → LLM 起草整章正文。**思考档 pro**（写长正文比结构化凝练重，
  见 4.2 story「model 档决策」）。
- reviewer：收初稿 + 写作任务书 → LLM 审查（一致性/设定贴合/明显问题），产出审查意见。快档。
- polisher：收初稿 + 审查意见 + 词表约束 → 加载正式去 AI 味词表 analyze_axis_b 自查 →
  LLM 按词表 + style_profile 去 AI 味改写 → 终稿。**思考档 pro**（改写重）。是 NFR1 红线
  的兑现段（AR15）。
- data-agent（Story 5.2 新增，第五段写后段）：收定稿正文 + confirmed 设定 → LLM 提取
  结构化 JSON（事件/状态变化/新增实体/伏笔回收）→ 交 chapter_projection_service 单事务
  投影回 story_state/chapter_card/story_thread。**快档 flash**（结构化提取是轻任务，
  architecture.md:196「deepseek-v4-flash 快，提取/轻任务」；reviewer 已实测快档会跑偏
  是因为审查要写意见正文，提取 JSON 天然强约束不易跑偏）。**只在定稿时跑**（受控决策 1），
  非定稿路径（generate/revise）跳过。

分层（architecture.md router→service→provider）：经 LLMProvider 抽象调 LLM（禁直调 openai，
陷阱①），Provider 层自动记账（AR14）。
"""

import json
import logging
import re
import uuid

from muse.core.db import async_session_maker
from muse.core.errors import ErrorEnvelope
from muse.core.settings import get_settings
from muse.orchestration import ai_taste_lexicon
from muse.providers.base import ChatResult, Message
from muse.providers.factory import get_provider_for_user
from muse.rag.retrieval import RecallResult, recall_context_for_chapter
from muse.repositories import (
    chapter_card_repo,
    chapter_repo,
    project_repo,
    story_bible_repo,
    story_state_repo,
    story_thread_repo,
)
from muse.services import exploration_service, usage_service

logger = logging.getLogger("muse")

# drafter/polisher 写整章正文，章节体量较长；快档/思考档均为推理模型（reasoning_content 先吃
# 预算，story_settle_agent.py:55-58 踩坑），故 max_tokens 留足避免正文被挤空。
_DRAFT_MAX_TOKENS = 4000
# reviewer 用思考档 pro（architecture.md:196「deepseek-v4-pro 思考，起草/审查」）——装置实测
# 快档 flash 把审查内容全放进 reasoning_content、content 返空（审查段形同虚设）；思考档产出
# 稳定的审查意见正文。max_tokens 留足审查意见空间（reasoning 先吃预算，settle:55-58 踩坑）。
_REVIEW_MAX_TOKENS = 2048
_POLISH_MAX_TOKENS = 4000
# data-agent（Story 5.2）输出严格 JSON：五要素 + 三列快照 + 三类 thread 操作，结构化
# 凝练体量小；但 reasoning 模型先吃预算（settle:55-58 踩坑），故 max_tokens 留足。
_DATA_AGENT_MAX_TOKENS = 2048

# 写前上下文注入的前序章节数（AC4）：V1 默认取最近 1 章（前一章）。取太多会挤爆 128K 上下文
# （承 deferred-work.md:175 对话历史无上界顾虑）；单章正文约 1500-2500 字，1 章足够给 drafter
# 「前情提要」而不喧宾夺主。后续按 token 预算可调（Epic 5 RAG 三级召回会替代这套直接注入）。
_RECENT_CHAPTERS_FOR_CONTEXT = 1

# 12 字段的 key ↔ 中文标签（与 story_bible 列名 / story_settle_agent._LLM_FIELDS 对齐）。
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


def _bible_not_confirmed() -> ErrorEnvelope:
    """设定圣经未确认（创作前置未满足 → 400）。

    Epic 4 创作唯一依据是 confirmed 设定圣经（story_bible.py:99）；无 confirmed 行说明用户
    还没确认设定，不能进入创作。与 settle_empty(400)/exploration_not_found(404) 语义正交。
    """
    return ErrorEnvelope(
        code="bible_not_confirmed",
        message="请先确认故事设定，再开始创作章节。",
        http_status=400,
    )


def _generate_failed() -> ErrorEnvelope:
    """LLM 完全跑偏、产出为空（空产 → 502，承 story_settle_agent 空产守卫先例）。"""
    return ErrorEnvelope(
        code="generate_failed",
        message="生成失败，请稍后重试。",
        http_status=502,
    )


def _format_bible_for_brief(bible: object) -> str:
    """把 confirmed story_bible 的 12 字段渲染成写作任务书里的「设定」段（有值的字段才输出行）。"""
    lines: list[str] = []
    for key, label in _BIBLE_FIELDS:
        value = (getattr(bible, key, None) or "").strip()
        if value:
            lines.append(f"{label}：{value}")
    return "\n".join(lines)


def _format_recent_chapters_block(chapters: list) -> str:
    """把最近前序章节正文渲染成写作任务书里的「前情提要」段（AC4）。

    chapters 已按 chapter_number 降序（最近在前，chapter_repo.list_recent_chapters）——这里反转
    为正序（旧→新）供阅读连贯。区分两种「无正文」：
    - chapters 为空列表 = 确实是第一章（无前序行）→ 提示「这是第一章」。
    - chapters 非空但正文皆空/空白（异常/占位，如前序章 upsert 了空正文）→ 不能骗 LLM「这是第一
      章」（会导致 drafter 不做承接、破坏连续性），而是明确提示「前序章节正文缺失」，让 drafter
      知道确有前序、按设定谨慎承接。
    """
    ordered = sorted(chapters, key=lambda c: c.chapter_number)
    parts: list[str] = []
    for chapter in ordered:
        text = (getattr(chapter, "text", None) or "").strip()
        if text:
            parts.append(f"【第 {chapter.chapter_number} 章正文】\n{text}")
    if parts:
        body = "\n\n".join(parts)
        return f"【前情提要（最近前序章节正文，务必与之衔接、不穿帮）】\n{body}"
    if not chapters:
        # 无前序行 = 确实是第一章。
        return "【前情提要】\n（这是第一章，暂无前序内容。）"
    # 有前序章但正文皆空（异常）：不谎称第一章，提示缺失让 drafter 谨慎承接。
    return (
        "【前情提要】\n（已有前序章节但正文暂缺，请依据故事设定谨慎承接、"
        "不要当作第一章从头起笔。）"
    )


def _format_revision_block(revision_input: dict | None) -> str:
    """把 Story 4.6 修订上下文渲染成写作任务书里的「修订」段（改进/重生注入，首次生成返空串）。

    - 首次生成（revision_input=None）：返回 ""（不追加任何修订段，与 4.4 一致）。
    - 改进（action=improve）：注入上一版正文（保留基础）+ 整体点评 + 逐条段落批注 + 保留指令。
      drafter 据此在旧正文上按反馈精修、尽量保留现有内容与结构（FR20「尽量保留现有内容」）。
    - 重生（action=regenerate）：注入可空重写方向 + 大改指令，**不注入旧正文作保留基础**
      （允许替换整章，FR20「替换整章」）。
    """
    if not revision_input:
        return ""
    action = revision_input.get("action")
    feedback = (revision_input.get("feedback") or "").strip()
    annotations = revision_input.get("annotations") or []
    previous_text = (revision_input.get("previous_text") or "").strip()

    if action == "regenerate":
        direction = (
            f"【重写方向（读者补充，务必参考）】\n{feedback}"
            if feedback
            else "【重写方向】\n（读者未补充方向，按故事设定与前文重新构思本章、写出全新一版。）"
        )
        return (
            "【本次任务：重新生成整章】\n"
            "读者对上一版不满意、要求重写整章。请重新规划本章内容、写出全新的一版，"
            "可大幅调整情节、结构与写法，不必保留上一版的具体写法。\n\n"
            f"{direction}"
        )

    # 改进（默认）：保留旧正文为基础，逐条回应点评与批注。
    parts: list[str] = ["【本次任务：改进本章】"]
    parts.append(
        "读者对上一版正文提出了具体意见。请在**上一版正文的基础上按意见改进、"
        "尽量保留读者认可的现有内容与结构**，只针对下面的点评与批注做修改，不要推翻重写。"
    )
    if previous_text:
        parts.append(f"【上一版正文（在此基础上改进）】\n{previous_text}")
    if feedback:
        parts.append(f"【读者的整体点评（针对全章）】\n{feedback}")
    if annotations:
        anno_lines: list[str] = []
        for i, anno in enumerate(annotations, start=1):
            comment = (anno.get("comment") or "").strip()
            if not comment:
                continue
            paragraph = (anno.get("paragraph") or "").strip()
            if paragraph:
                # 段落原文可能很长，截断给锚点即可（避免任务书过长挤爆上下文）。
                snippet = paragraph[:120]
                anno_lines.append(
                    f"{i}. 针对段落「{snippet}…」：{comment}"
                    if len(paragraph) > 120
                    else f"{i}. 针对段落「{paragraph}」：{comment}"
                )
            else:
                anno_lines.append(f"{i}. {comment}")
        if anno_lines:
            parts.append(
                "【读者的段落批注（逐条针对具体段落，务必逐条回应）】\n"
                + "\n".join(anno_lines)
            )
    return "\n\n".join(parts)


# ========== Story 5.6：写前上下文升级（3 个新块格式化函数） ==========


def _format_story_threads_block(threads: list) -> str:
    """把未回收 story_threads 渲染为写作任务书里的「未回收伏笔/线索」段。

    按 `last_touched_chapter_number DESC` 取最近活跃的若干条（默认 10 条上限），
    渲染为「【未回收伏笔/线索（需在本章关注或回收）】」块。

    threads 为空或降级时：写入空提示（同类体例与 _format_recent_chapters_block
    的「这是第一章」/「暂缺」空提示范式一致）。
    """
    if not threads:
        return "【未回收伏笔/线索】\n（当前无未回收伏笔与线索，可自然推进。）"
    parts: list[str] = []
    for thread in threads:
        content = (getattr(thread, "content", None) or "").strip()
        if not content:
            continue
        # 截断 200 字防上下文暴涨（受控决策 5）
        snippet = content[:200]
        if len(content) > 200:
            snippet += "…"
        ch_num = getattr(thread, "last_touched_chapter_number", None)
        parts.append(
            f"（第 {ch_num} 章未回收）{snippet}"
            if ch_num is not None
            else f"（未回收）{snippet}"
        )
    if parts:
        body = "\n".join(parts)
        return f"【未回收伏笔/线索（需在本章关注或回收）】\n{body}"
    return "【未回收伏笔/线索】\n（当前无未回收伏笔与线索，可自然推进。）"


def _format_story_state_block(state) -> str:
    """把 story_state 当前快照渲染为写作任务书里的「当前故事状态」段。

    取 protagonist_state / world_rules_state / current_stage 三列快照，
    渲染为「【当前故事状态（主角状态/世界规则/叙事位置）】」块。

    state 为 None 或三列皆空时：写入空提示（同 _format_recent_chapters_block 的
    空提示范式）。
    """
    if state is None:
        return "【当前故事状态】\n（暂无故事状态快照，请依据故事设定自然推进。）"
    protag = (getattr(state, "protagonist_state", None) or "").strip()
    world = (getattr(state, "world_rules_state", None) or "").strip()
    stage = (getattr(state, "current_stage", None) or "").strip()
    if not protag and not world and not stage:
        return "【当前故事状态】\n（暂无故事状态快照，请依据故事设定自然推进。）"
    parts = []
    if protag:
        parts.append(f"主角状态：{protag}")
    if world:
        parts.append(f"世界规则：{world}")
    if stage:
        parts.append(f"叙事位置：{stage}")
    body = "\n".join(parts)
    return f"【当前故事状态（主角状态/世界规则/叙事位置）】\n{body}"


def _format_recalled_block(recalled: RecallResult) -> str:
    """把 RAG 召回结果渲染为写作任务书里的「相关历史设定」段（AC2）。

    每条：`{source}[章{chapter_number}](score={score:.2f})：{content[:200]}...`
    （截断 200 字防上下文暴涨）。

    召回为空或降级时输出「（当前无相关历史设定召回）」提示。上限防超 3000 字
    （≈ 15 条 × 200 字平均，受控决策 5）。
    """
    if not recalled.items:
        return "【相关历史设定（RAG 召回，供本章参考）】\n（当前无相关历史设定召回。）"
    lines: list[str] = []
    total_chars = 0
    max_chars = 3000  # 受控决策 5：上限防上下文暴涨
    for item in recalled.items:
        content = (getattr(item, "content", None) or "").strip()
        if not content:
            continue
        truncated = content[:200]
        ch_num = getattr(item, "chapter_number", None) or "?"
        score = getattr(item, "score", 0.0)
        line = f"{item.source}[章{ch_num}](score={score:.2f})：{truncated}"
        if total_chars + len(line) > max_chars:
            lines.append("（RAG 召回结果已超过写作任务书上限，后续条省略）")
            break
        lines.append(line)
        total_chars += len(line)
    body = "\n".join(lines)
    return f"【相关历史设定（RAG 召回，供本章参考）】\n{body}"


async def run_context_agent(
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    chapter_number: int,
    chapter_idea: str | None = None,
    revision_input: dict | None = None,
) -> str:
    """context-agent（AR16）：读 confirmed 设定 → 组装写作任务书（system + user 合并为一段文本）。

    **不调 LLM**（纯组装），故不过 check_quota/provider。返回写作任务书全文（供 drafter 消费、
    落 run 表 context 段产物）。

    V1 写前上下文 = 全量设定（confirmed 12 字段 + style_profile 风格锚点 + 去 AI 味词表约束）
    + 最近前序章节正文（Story 4.4 接入，取最近 _RECENT_CHAPTERS_FOR_CONTEXT 章）。前序章节含
    draft（4.7 定稿未实现前唯一保证多章连续性的做法，Jianghj 2026-08-05 决议）。RAG 三级召回 +
    归档 chapter_cards 是 Epic 5 增强（epics.md:859③）。

    **Story 5.6：写前上下文升级**——在现有「全量设定 + 最近前序章节」的基础上追加
    3 个新块：未回收伏笔/线索（story_threads）、当前故事状态（story_state）、
    RAG 召回的相关历史设定（recall_context_for_chapter）。不替换任何现有块——只追加。

    **Story 4.6 修订注入**：revision_input（dict，含 action/feedback/annotations/previous_text）
    非 None 时追加修订段——改进（action=improve）注入「上一版正文（保留基础）+ 整体点评 + 段落
    批注 + 保留指令」，让 drafter 在旧正文上按反馈精修、尽量保留现有内容；重生（regenerate）注入
    「可空重写方向 + 大改指令」，不注入旧正文作保留基础（允许替换整章）。revision_input=None 时
    行为与 4.4 完全一致（首次生成，向后兼容）。
    """
    async with async_session_maker() as session:
        # 租户守卫（二义合一 404，story_settle_agent.py:350-352 范式）。
        project = await project_repo.get_owned_project(session, project_id, user_id)
        if project is None:
            raise exploration_service._exploration_not_found()

        # 读 confirmed 设定圣经（Epic 4 唯一创作依据）。无 → 400 提示先确认设定。
        bible = await story_bible_repo.get_confirmed_by_project(
            session, user_id=user_id, project_id=project_id
        )
        if bible is None:
            raise _bible_not_confirmed()

        # 读最近前序章节正文（AC4 写前上下文）。第一章无前序 → 空列表 → 空提示块。同 session
        # 内读完，块文本在下方拼装（session 关闭后 chapter ORM 属性已 expire，故先取文本）。
        recent_chapters = await chapter_repo.list_recent_chapters(
            session,
            user_id=user_id,
            project_id=project_id,
            before_number=chapter_number,
            limit=_RECENT_CHAPTERS_FOR_CONTEXT,
        )
        recent_block = _format_recent_chapters_block(recent_chapters)

        # Story 5.6：读 story_state 当前快照 + story_threads 未回收伏笔
        # （同 session 内读完，块文本在下方拼装）。
        state_row = await story_state_repo.get_by_project(
            session, user_id=user_id, project_id=project_id
        )
        state_block_raw = _format_story_state_block(state_row)

        open_threads = await story_thread_repo.list_open_by_project(
            session, user_id=user_id, project_id=project_id
        )
        # Story 5.6：取最近活跃的若干条未回收 thread（上限 10 条防上下文暴涨）。
        recent_threads_block_raw = _format_story_threads_block(open_threads[:10])

    # 组装写作任务书（session 已可关闭，纯文本拼装）。
    setting_block = _format_bible_for_brief(bible)
    style_profile = (getattr(bible, "style_profile", None) or "").strip()
    style_block = (
        f"【文风锚点（务必贴合以下文风写作）】\n{style_profile}"
        if style_profile
        else "【文风锚点】\n（未锚定文风，用与题材气质相称的自然网文文风，避免翻译腔与 AI 味。）"
    )
    lexicon_block = ai_taste_lexicon.format_lexicon_constraints()
    idea_block = (
        f"【本章想法（读者补充，务必在本章体现）】\n{chapter_idea.strip()}"
        if chapter_idea and chapter_idea.strip()
        else "【本章想法】\n（读者未补充，按设定与前文自然推进本章剧情。）"
    )
    # Story 4.6 修订段（改进/重生注入，首次生成为空串不占位）。放在写作要求前，作为本次最强指令。
    revision_block = _format_revision_block(revision_input)
    revision_section = f"\n{revision_block}\n" if revision_block else ""

    # Story 5.6：RAG 召回——开独立 session 调 recall_context_for_chapter，
    # 不阻断（受控决策 4）。try/except 包裹：异常时只 logger.warning，任务书无 RAG 块
    # （等效 4.4 基线行为）。
    recalled_block_raw: str | None = None
    try:
        async with async_session_maker() as rag_session:
            recalled = await recall_context_for_chapter(
                rag_session,
                user_id=user_id,
                project_id=project_id,
                current_chapter=chapter_number,
                limit=20,  # 受控决策 5：上限防上下文暴涨
            )
            recalled_block_raw = _format_recalled_block(recalled)
    except Exception:
        logger.warning(
            "RAG 召回异常（跳过，不阻断写前上下文组装）：user=%s project=%s "
            "chapter=%s",
            user_id,
            project_id,
            chapter_number,
            exc_info=True,
        )
        # 不抛错——RAG 是增强非必备，降级后仍有三表基础上下文（受控决策 4）。
        recalled_block_raw = None

    # 三块拼接——空/降级时写入空提示（同 _format_recent_chapters_block 的典范做法）。
    recalled_section = (
        f"\n{recalled_block_raw}\n"
        if recalled_block_raw
        else "\n【相关历史设定（RAG 召回）】\n（当前无相关历史设定召回。）\n"
    )
    threads_section = (
        f"\n{recent_threads_block_raw}\n"
        if recent_threads_block_raw
        else "\n【未回收伏笔/线索】\n（当前无未回收伏笔与线索，可自然推进。）\n"
    )
    state_section = (
        f"\n{state_block_raw}\n"
        if state_block_raw
        else "\n【当前故事状态】\n（暂无故事状态快照，请依据故事设定自然推进。）\n"
    )

    brief = f"""你是一位专业的网文作者，正在为一部连载作品写第 {chapter_number} 章的正文。

【故事设定（唯一创作依据）】
{setting_block}

{style_block}

{recent_block}
{state_section}
{threads_section}
{idea_block}
{revision_section}
{recalled_section}
{lexicon_block}

【写作要求】
- 写出完整的一章正文（约 1500-2500 字），有场景、有动作、有对白、有细节。
- 紧扣故事设定与文风锚点，人物言行符合设定。
- 若有前情提要，本章须与之自然衔接、不与既有情节/人物状态矛盾。
- 面向大众网文读者，说人话；杜绝上面列出的 AI 味词与句式套路。
- 只输出章节正文本身，不要输出标题、章节号、大纲、注释或任何正文之外的文字。"""
    return brief


async def run_drafter(
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    writing_brief: str,
) -> str:
    """drafter：收写作任务书 → LLM 起草整章正文（思考档 pro）。返回初稿正文。"""
    settings = get_settings()
    async with async_session_maker() as session:
        # 租户守卫 + 护栏（provider 前）。
        project = await project_repo.get_owned_project(session, project_id, user_id)
        if project is None:
            raise exploration_service._exploration_not_found()
        await usage_service.check_quota(session, user_id)

        provider = await get_provider_for_user(session, user_id, project_id=project_id)
        messages: list[Message] = [
            {"role": "user", "content": writing_brief},
        ]
        result: ChatResult = await provider.chat(
            messages,
            model=settings.deepseek_model_thinking,
            max_tokens=_DRAFT_MAX_TOKENS,
        )
    draft = result.content.strip()
    if not draft:
        raise _generate_failed()
    return draft


async def run_reviewer(
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    writing_brief: str,
    draft: str,
) -> str:
    """reviewer：收初稿 + 写作任务书 → LLM 审查（一致性/设定贴合/明显问题）。返回审查意见文本。

    V1 最小可用：审查产出**意见文本**（附给 polisher 参考），不做「不合格回炉重写」的回环
    （不过度设计）。**思考档 pro**（architecture.md:196「起草/审查」用 pro；装置实测快档 flash
    把审查内容放进 reasoning、content 返空）。空产不视为致命——审查意见为空则返回空串，
    polisher 仍可只据词表 + 文风自查（审查是增强、非阻断）。
    """
    settings = get_settings()
    async with async_session_maker() as session:
        project = await project_repo.get_owned_project(session, project_id, user_id)
        if project is None:
            raise exploration_service._exploration_not_found()
        await usage_service.check_quota(session, user_id)

        provider = await get_provider_for_user(session, user_id, project_id=project_id)
        messages: list[Message] = [
            {
                "role": "system",
                "content": (
                    "你是一位严格的网文编辑。读下面的写作任务书和据此写出的章节初稿，"
                    "指出初稿在【设定一致性】【人物行为是否符合设定】【剧情硬伤】【文风是否贴合】"
                    "四方面的具体问题，逐条列出（有就列、没有就说这方面没问题）。"
                    "只列问题与修改建议，不要重写正文、不要复述初稿。"
                ),
            },
            {
                "role": "user",
                "content": f"【写作任务书】\n{writing_brief}\n\n【章节初稿】\n{draft}",
            },
        ]
        result: ChatResult = await provider.chat(
            messages,
            model=settings.deepseek_model_thinking,
            max_tokens=_REVIEW_MAX_TOKENS,
        )
    return result.content.strip()


async def run_polisher(
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    draft: str,
    review_notes: str,
) -> str:
    """polisher（AR15，NFR1 兑现段）：词表自查 + style_profile 文风锚点 + LLM 去 AI 味改写。

    返回终稿正文（思考档 pro）。流程：先用正式去 AI 味词表 analyze_axis_b 统计初稿的黑名单
    词频 + 句式套路命中（客观信号），把命中项作为**改写输入信号**（宁可多报、交 LLM 据语义
    决定改不改，延续 4.1 判据局限说明）；同时读 confirmed story_bible 的 style_profile 作
    **风格锚点段**注入（AC4：style_profile 与词表叠加、由 polisher 自查自改，共同兑现 NFR1
    ——drafter 注入了锚点，polisher 改写时同样须持有锚点，否则改写易偏离文风）。连同审查
    意见、词表约束喂 LLM，产出去 AI 味终稿。
    """
    settings = get_settings()
    # 词表自查（纯函数、无 IO）：产出命中信号供改写参考。
    stats = ai_taste_lexicon.analyze_axis_b(draft)
    hit_words = "、".join(h.word for h in stats.blacklist_hits[:20]) or "（无）"
    hit_patterns = (
        "；".join(f"{h.note}：{'／'.join(h.snippets[:3])}" for h in stats.pattern_hits)
        or "（无）"
    )
    lexicon_block = ai_taste_lexicon.format_lexicon_constraints()

    async with async_session_maker() as session:
        project = await project_repo.get_owned_project(session, project_id, user_id)
        if project is None:
            raise exploration_service._exploration_not_found()
        # 读 confirmed story_bible 取 style_profile 作风格锚点（AC4）。与 context-agent 同源；
        # context-agent 段已保证 confirmed 行存在（无则先抛 bible_not_confirmed），此处 None
        # 属极端（创作中被取消确认）→ 用默认风格段不阻塞（与 context-agent 同款语义）。
        bible = await story_bible_repo.get_confirmed_by_project(
            session, user_id=user_id, project_id=project_id
        )
        style_profile = (
            getattr(bible, "style_profile", None) or ""
        ).strip()
        await usage_service.check_quota(session, user_id)

        provider = await get_provider_for_user(session, user_id, project_id=project_id)
        review_block = review_notes.strip() or "（审查未提出问题）"
        style_block = (
            f"【文风锚点（改写时务必贴合，不得偏离）】\n{style_profile}"
            if style_profile
            else "【文风锚点】\n（未锚定文风，保持原稿语气节奏，仅去 AI 味。）"
        )
        messages: list[Message] = [
            {
                "role": "system",
                "content": (
                    "你是一位擅长去 AI 味的润色编辑。在**尽量保留原文情节、人物、篇幅、文风**的"
                    "前提下，把下面的章节初稿改写得更像人写的网文：删掉空洞抽象的套话、翻译腔、"
                    "万能修饰、煽情套路句式，换成具体的动作、场景、对白与细节，同时**严格贴合"
                    "给定的文风锚点**。"
                    "只输出改写后的完整章节正文，不要输出说明、注释或标题。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"{style_block}\n\n"
                    f"{lexicon_block}\n\n"
                    f"【词表自查命中（供参考，可据语义判断是否真需修改）】\n"
                    f"黑名单词：{hit_words}\n句式套路：{hit_patterns}\n\n"
                    f"【编辑审查意见】\n{review_block}\n\n"
                    f"【待润色的章节初稿】\n{draft}"
                ),
            },
        ]
        result: ChatResult = await provider.chat(
            messages,
            model=settings.deepseek_model_thinking,
            max_tokens=_POLISH_MAX_TOKENS,
        )
    polished = result.content.strip()
    if not polished:
        raise _generate_failed()
    return polished


# ---------- Story 5.2 第五段：data-agent（写后投影，AR17） ----------


def _projection_failed() -> ErrorEnvelope:
    """data-agent 投影失败（LLM 产空 / JSON 解析失败 → 502，与 _generate_failed 同语义
    但专用 code 便于运维区分）。

    AC5「失败回滚可重试」配合 chapter_projection_service 单事务——step 抛错即触发
    run.steps.data_agent 标 failed + run 标 failed，下次重入断点续跑。
    """
    return ErrorEnvelope(
        code="projection_failed",
        message="章节归档失败，请稍后重试。",
        http_status=502,
    )


def _format_recent_chapter_cards_block(chapter_cards: list) -> str:
    """把最近前序章节卡五要素渲染成 data-agent 输入的「前章归档」段（A7 patch）。

    chapter_cards 已按 chapter_number 降序（最近在前，chapter_card_repo.
    list_recent_chapter_cards）——这里反转为正序（旧→新）供阅读连贯。区分两种「无卡」：
    - chapter_cards 为空列表 = 确实是第一章（无前序卡）→ 提示「这是第一章」。
    - chapter_cards 非空但五要素皆空/空白（异常/占位）→ 不能骗 LLM「这是第一章」，
      而是明确提示「前序章节归档缺失」，让 data-agent 知道确有前序、按设定谨慎提取。
    """
    ordered = sorted(chapter_cards, key=lambda c: c.chapter_number)
    parts: list[str] = []
    for card in ordered:
        what_happened = (getattr(card, "what_happened", None) or "").strip()
        end_state = (getattr(card, "end_state", None) or "").strip()
        unresolved_hooks = (getattr(card, "unresolved_hooks", None) or "").strip()
        if what_happened:
            parts.append(
                f"【第 {card.chapter_number} 章归档】\n"
                f"发生了什么：{what_happened}\n"
                f"章末状态：{end_state or '（空）'}\n"
                f"未解决悬念：{unresolved_hooks or '（空）'}"
            )
    if parts:
        body = "\n\n".join(parts)
        return f"【前章归档卡片（务必对照识别本章新增事实/状态变化/伏笔回收）】\n{body}"
    if not chapter_cards:
        # 无前序卡 = 确实是第一章。
        return "【前章归档卡片】\n（这是第一章，暂无前序归档。）"
    # 有前序卡但五要素皆空（异常）：不谎称第一章，提示缺失让 data-agent 谨慎提取。
    return (
        "【前章归档卡片】\n（已有前序章节但归档缺失，请依据故事设定谨慎提取、"
        "不要当作第一章从头提取。）"
    )


async def run_data_agent(
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    chapter_number: int,
    chapter_text: str,
) -> dict:
    """data-agent（Story 5.2，第五段写后段，AR17）：从定稿正文提取结构化 JSON。

    **只在定稿时跑**（受控决策 1，FR23）——不在 generate/revise 时跑（那两路径只翻
    status 不落归档）。**快档 flash**（结构化提取是轻任务，architecture.md:196；
    reviewer 已实测快档会跑偏是因为「写意见正文」的自由文本任务，JSON 强约束提取
    不易跑偏）。**不调 reviewer**——data-agent 拿的是 polisher 段已定稿正文。

    **输入注入**：定稿正文 + confirmed story_bible 12 字段摘要（上下文锚点）。
    **输出 schema**（严格 JSON，prompt 强约束 + json.loads 解析 + 必填字段守卫）：

    ```json
    {
      "what_happened": "...",           // chapter_card 五要素 ①
      "character_changes": "...",       // ②
      "new_facts_clues": "...",         // ③
      "unresolved_hooks": "...",        // ④
      "end_state": "...",               // ⑤
      "protagonist_state": "...",       // story_state 三列 ①
      "world_rules_state": "...",       // ②
      "current_stage": "...",           // ③
      "new_threads": [                  // 新埋伏笔（→ story_thread_repo.upsert_new_thread）
        {"content": "...", "introduced_chapter_number": 1}
      ],
      "resolved_threads": [             // 本章回收的伏笔（→ resolve_thread_by_content）
        {"content": "...", "resolved_chapter_number": 1}
      ],
      "touched_threads": [              // 本章再提的伏笔（→ touch_thread_by_content）
        {"content": "...", "last_touched_chapter_number": 1}
      ]
    }
    ```

    **空产/解析失败抛 `_projection_failed()`**（不静默兜底——AC5「失败回滚可重试」
    须让 run.steps.data_agent 显式标 failed，下次重入断点续跑；若静默返空 dict，
    chapter_projection_service 会写三表空快照造成数据污染）。
    **返回 dict**（非 str）——run.steps 是 JSONB 列，可序列化 dict 直接落库；
    本 step 是五段中唯一返回 dict 的段（其他四段返回 str），update_step 需兼容。
    """
    settings = get_settings()
    async with async_session_maker() as session:
        project = await project_repo.get_owned_project(session, project_id, user_id)
        if project is None:
            raise exploration_service._exploration_not_found()

        # 读 confirmed 设定圣经作上下文锚点（同 context-agent 数据源）——LLM 需要
        # 「既有设定」对照才能识别「本章新增事实/状态变化/伏笔回收」。
        bible = await story_bible_repo.get_confirmed_by_project(
            session, user_id=user_id, project_id=project_id
        )
        if bible is None:
            # 极端防御：正常流程 confirmed 已前置（context-agent 已校验），此处 None
            # 属「创作中被取消确认」——复用 bible_not_confirmed 语义。
            raise _bible_not_confirmed()

        # A7 patch：读最近前序 chapter_card 五要素作上下文锚点（spec Subtask 1.2 明文）——
        # LLM 需要「前章已沉淀的事实」对照才能识别「本章新增事实/状态变化/伏笔回收」。
        # 第一章无前序 → 空列表 → 空提示块。
        recent_chapter_cards = await chapter_card_repo.list_recent_chapter_cards(
            session,
            user_id=user_id,
            project_id=project_id,
            before_number=chapter_number,
            limit=_RECENT_CHAPTERS_FOR_CONTEXT,
        )
        recent_cards_block = _format_recent_chapter_cards_block(recent_chapter_cards)

        await usage_service.check_quota(session, user_id)
        provider = await get_provider_for_user(session, user_id, project_id=project_id)

        # 设定摘要注入（12 字段有值的才列）。
        setting_block = _format_bible_for_brief(bible)

        messages: list[Message] = [
            {
                "role": "system",
                "content": (
                    "你是一位严谨的网文事实提取员。读下面的故事设定、前章归档卡片与一章定稿正文，"
                    "提取这一章发生的事实、人物变化、新增伏笔与回收伏笔，输出**严格 JSON**"
                    "（不要任何额外说明、markdown 代码块或注释）。"
                    "每个字段的取值必须是**整段散文式中文**（不是关键词列表），"
                    "未发生的类别填空字符串 \"\"；new_threads / resolved_threads / "
                    "touched_threads 三类列表若本章无对应操作填空列表 []。"
                    "章号字段（introduced_chapter_number / resolved_chapter_number / "
                    "last_touched_chapter_number）必须填本章章号。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"【故事设定（既有创作依据）】\n{setting_block}\n\n"
                    f"{recent_cards_block}\n\n"
                    f"【第 {chapter_number} 章定稿正文】\n{chapter_text}\n\n"
                    "请提取并输出严格 JSON，schema 如下（所有字段必填，未发生填空串/空列表）：\n"
                    "{\n"
                    '  "what_happened": "本章发生了什么（散文一段）",\n'
                    '  "character_changes": "人物变化（散文一段）",\n'
                    '  "new_facts_clues": "新增事实与线索（散文一段）",\n'
                    '  "unresolved_hooks": "未解决悬念（散文一段）",\n'
                    '  "end_state": "章末状态（散文一段）",\n'
                    '  "protagonist_state": "主角当前状态快照（心境/伤势/资源/关系）",\n'
                    '  "world_rules_state": "世界规则当前生效快照（含本章修订追加）",\n'
                    '  "current_stage": "当前叙事位置简述（如『程野刚进入第七码头地下档案库』）",\n'
                    '  "new_threads": [{"content": "...", "introduced_chapter_number": '
                    f"{chapter_number}"
                    "}],\n"
                    '  "resolved_threads": [{"content": "...", "resolved_chapter_number": '
                    f"{chapter_number}"
                    "}],\n"
                    '  "touched_threads": [{"content": "...", "last_touched_chapter_number": '
                    f"{chapter_number}"
                    "}]\n"
                    "}"
                ),
            },
        ]
        result: ChatResult = await provider.chat(
            messages,
            model=settings.deepseek_model_fast,
            max_tokens=_DATA_AGENT_MAX_TOKENS,
        )

    raw = result.content.strip()
    if not raw:
        logger.warning(
            "data-agent LLM 产空：project=%s chapter=%s", project_id, chapter_number
        )
        raise _projection_failed()

    # 容错：LLM 偶发返回 ```json ... ``` 包装——用正则剥 fence（B5+E9 patch：
    # 原「首行 ``` + 末行 ```」严格形态太狭隘，遇「fence 后有空格」「首尾换行异常」
    # 「同尾行多 fence」会剥失败；改正则提取第一个 ``` 块内容，失败再 fallback 原串）。
    fence_match = re.search(r"```(?:json)?\s*\n(.*?)\n```", raw, re.DOTALL)
    if fence_match:
        raw = fence_match.group(1).strip()

    try:
        extracted = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning(
            "data-agent JSON 解析失败：project=%s chapter=%s raw=%s",
            project_id,
            chapter_number,
            raw[:500],
            exc_info=exc,
        )
        raise _projection_failed() from exc

    # 必填字段守卫：五要素 + 三列快照 + 三类 thread 列表，缺任一视为不完整。
    required_keys = (
        "what_happened",
        "character_changes",
        "new_facts_clues",
        "unresolved_hooks",
        "end_state",
        "protagonist_state",
        "world_rules_state",
        "current_stage",
        "new_threads",
        "resolved_threads",
        "touched_threads",
    )
    missing = [k for k in required_keys if k not in extracted]
    if missing:
        logger.warning(
            "data-agent JSON 缺必填字段 %s：project=%s chapter=%s",
            missing,
            project_id,
            chapter_number,
        )
        raise _projection_failed()

    # 类型归一：LLM 可能把三类 thread 列表产为非 list（如 str/dict），强制归一为 list。
    for key in ("new_threads", "resolved_threads", "touched_threads"):
        if not isinstance(extracted[key], list):
            extracted[key] = []
    # 五要素/三列快照强制 str（LLM 可能产 None/list）。
    for key in (
        "what_happened",
        "character_changes",
        "new_facts_clues",
        "unresolved_hooks",
        "end_state",
        "protagonist_state",
        "world_rules_state",
        "current_stage",
    ):
        if not isinstance(extracted[key], str):
            extracted[key] = ""

    return extracted
