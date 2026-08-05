"""五段流水线的四段 step 实现（Story 4.2，V1 四段：context→drafter→reviewer→polisher）。

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

分层（architecture.md router→service→provider）：经 LLMProvider 抽象调 LLM（禁直调 openai，
陷阱①），Provider 层自动记账（AR14）。
"""

import uuid

from muse.core.db import async_session_maker
from muse.core.errors import ErrorEnvelope
from muse.core.settings import get_settings
from muse.orchestration import ai_taste_lexicon
from muse.providers.base import ChatResult, Message
from muse.providers.factory import get_provider_for_user
from muse.repositories import chapter_repo, project_repo, story_bible_repo
from muse.services import exploration_service, usage_service

# drafter/polisher 写整章正文，章节体量较长；快档/思考档均为推理模型（reasoning_content 先吃
# 预算，story_settle_agent.py:55-58 踩坑），故 max_tokens 留足避免正文被挤空。
_DRAFT_MAX_TOKENS = 4000
# reviewer 用思考档 pro（architecture.md:196「deepseek-v4-pro 思考，起草/审查」）——装置实测
# 快档 flash 把审查内容全放进 reasoning_content、content 返空（审查段形同虚设）；思考档产出
# 稳定的审查意见正文。max_tokens 留足审查意见空间（reasoning 先吃预算，settle:55-58 踩坑）。
_REVIEW_MAX_TOKENS = 2048
_POLISH_MAX_TOKENS = 4000

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


async def run_context_agent(
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    chapter_number: int,
    chapter_idea: str | None = None,
) -> str:
    """context-agent（AR16）：读 confirmed 设定 → 组装写作任务书（system + user 合并为一段文本）。

    **不调 LLM**（纯组装），故不过 check_quota/provider。返回写作任务书全文（供 drafter 消费、
    落 run 表 context 段产物）。

    V1 写前上下文 = 全量设定（confirmed 12 字段 + style_profile 风格锚点 + 去 AI 味词表约束）
    + 最近前序章节正文（Story 4.4 接入，取最近 _RECENT_CHAPTERS_FOR_CONTEXT 章）。前序章节含
    draft（4.7 定稿未实现前唯一保证多章连续性的做法，Jianghj 2026-08-05 决议）。RAG 三级召回 +
    归档 chapter_cards 是 Epic 5 增强（epics.md:859③）。
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

    brief = f"""你是一位专业的网文作者，正在为一部连载作品写第 {chapter_number} 章的正文。

【故事设定（唯一创作依据）】
{setting_block}

{style_block}

{recent_block}

{idea_block}

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
