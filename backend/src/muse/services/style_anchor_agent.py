"""Style Anchor Agent：文风锚点样本库 + style_profile 真实抽取（Story 3.2）。

文风锚点是 Muse 独有卖点（webnovel-writer 无）、NFR1 去 AI 味红线的验收前提
[[project_muse_quality_redline]]。用户从**预置样本库选择**或**粘贴一段爱读的文字**锚定文风，
系统经 LLMProvider 抽象真实抽取作品级 `style_profile`（人称、语气、句式节奏、意象密度、
段落长度倾向五维，FR16/AR15），upsert 到 story_bible.style_profile 列，成为后续每章生成的
风格锚点（AR15，Epic 4 drafter 注入）与 Epic 4 盲测（AR19 launch blocker）的风格输入。

**与 explorer_agent / free_explorer_agent 职责独立**：那两者服务探索域（理解自述 / 自由对话
+ 线索整理），本模块服务设定域的文风抽取。延续「按 Agent 职责拆 service」的既定项目模式，
新建独立文件而非合并进假想的 story_service（architecture.md:406 早期建议，实际代码库是按职责
拆分——见 story Dev Notes）。

分层（architecture.md router→service→provider）：本模块是设定域 service，经 LLMProvider 抽象
调 LLM（**禁直调 openai**，陷阱①），生成前过 check_quota 护栏（陷阱②），Provider 层自动记账
（AR14）。**不加 mode 守卫**：文风锚点是设定阶段作品级操作、guided/free 两模式均可锚定，与
interpret/free-chat 的模式专属端点性质不同（受控决策 4）。

session 生命周期（陷阱⑩，仿 free_explorer_agent.extract_clues）：抽取虽非流式但同样调
provider（走 MeteredProvider 记账），MeteredProvider 的 finally 兜底记账须落在存活 session
上——故用独立 `async_session_maker()` 自管 session，不依赖请求注入 session 的生命周期。
"""

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from muse.core.db import async_session_maker
from muse.core.errors import ErrorEnvelope
from muse.core.settings import get_settings
from muse.models.story_bible import StoryBible
from muse.providers.base import ChatResult
from muse.providers.factory import get_provider_for_user
from muse.repositories import project_repo, story_bible_repo
from muse.services import exploration_service, usage_service

# 文风抽取是一次性结构化提炼、轻任务 → 快档（deepseek-v4-flash）。快档是推理模型（2.1 Debug
# Log 实测：reasoning_content 先吃 token 预算），留足余量避免五维正文被挤空（同 2.3 陷阱⑥、
# free_explorer_agent._EXTRACT_MAX_TOKENS 考量）。
_MAX_TOKENS = 1024

# style_profile 五维（对齐 FR16/AR15 与原型 styleAnchorProfileMarkup app.js:1940-1954）。
# key 用于解析/组装，label 是 prompt 报送与落库文本的中文标签（与原型展示一字对齐）。
STYLE_DIMENSIONS: list[tuple[str, str]] = [
    ("person", "人称"),
    ("tone", "语气"),
    ("rhythm", "句式节奏"),
    ("imagery", "意象密度"),
    ("paragraph", "段落长度倾向"),
]


class StyleSample:
    """预置样本库一项：id（稳定 slug，与前端原型对齐）+ 展示元信息 + 抽取用原文。

    excerpt 是列表卡片展示的短摘（原型 app.js 用它做卡片预览）；text 是**较完整的样本原文**，
    供真实抽取喂 LLM（原型 excerpt 仅一两句是展示占位，后端须给足够长的原文让抽取有料可抽，
    见 story Task 1 决策——库选与粘贴统一走真实抽取，不预烘焙 profile 常量）。
    """

    def __init__(self, *, id: str, name: str, note: str, excerpt: str, text: str) -> None:
        self.id = id
        self.name = name
        self.note = note
        self.excerpt = excerpt
        self.text = text


# 预置样本库（3 个，id 与前端原型 styleSampleLibrary 对齐：cold-rain/warm-dusk/sharp-first）。
# text 给足原文让抽取有据；后端是样本库单一事实源（避免前后端漂移，story 待确认项 3）。
STYLE_SAMPLE_LIBRARY: list[StyleSample] = [
    StyleSample(
        id="cold-rain",
        name="冷峻夜雨",
        note="克制的短句、潮湿的旧城意象",
        excerpt="雨是在凌晨落下来的，比记忆里任何一场都更安静。",
        text=(
            "雨是在凌晨落下来的，比记忆里任何一场都更安静。他站在檐下，看水沿着旧招牌的裂缝"
            "往下走，没有点烟，也没有回头。街灯是坏的，只剩最远的一盏还亮，把积水照成一小片"
            "浑浊的金。有人从巷口经过，脚步很轻，像怕惊动什么。他没有动。他知道等的人不会来了，"
            "可还是又站了一会儿——雨里的时间总是走得慢些，慢到足够让人把一件早就想通的事，"
            "再想一遍。"
        ),
    ),
    StyleSample(
        id="warm-dusk",
        name="黄昏暖光",
        note="舒缓长句、细腻的情感铺陈",
        excerpt="黄昏的光是慢慢漫上来的，先是染红了她搁在窗台上的手背。",
        text=(
            "黄昏的光是慢慢漫上来的，先是染红了她搁在窗台上的手背，然后才一点一点爬满整间"
            "屋子，像怕惊动了谁似的，走得那样轻。她没有开灯，就那样任由暖橙色的光把桌上的"
            "旧照片、没喝完的茶、和摊开一半的信纸都镀上一层温柔的边，仿佛这一整个下午的沉默，"
            "都被这光轻轻接住了。她想起很多年前也是这样一个黄昏，那时候她还相信，只要肯等，"
            "所有走远的人都会在某个这样的傍晚，重新推开那扇门。"
        ),
    ),
    StyleSample(
        id="sharp-first",
        name="凌厉第一人称",
        note="紧凑口语、强推进感",
        excerpt="我没时间解释。门在身后合上的那一秒，我已经算好了三条路。",
        text=(
            "我没时间解释。门在身后合上的那一秒，我已经算好了三条路——两条是死的，剩下一条，"
            "我赌它还没被他们发现。走廊尽头的灯在闪，一下，两下，第三下的时候我已经贴到了墙角。"
            "脚步声从右边来，很稳，是受过训练的人。我摸了摸口袋里那张卡，还在。好。只要它还在，"
            "我就还有得玩。我数到三，然后往左——不是因为左边更安全，而是因为他们一定以为我会往右。"
        ),
    ),
]

# id → 样本的映射，供按 sampleId 取原文（库选路径），未知 id 由 service 转 404。
_SAMPLE_BY_ID: dict[str, StyleSample] = {s.id: s for s in STYLE_SAMPLE_LIBRARY}

# Style Anchor Agent system prompt（AC2，NFR1 去 AI 味红线 [[project_muse_quality_redline]]）。
# 职责单一：读一段样本原文 → 就五维各输出一行「标签：内容」（仿 free_explorer_agent 固定前缀
# 输出契约，便于防御性解析）。面向大众网文向、非文学腔 [[project_muse_target_user]]。
_DIMENSION_LINES_HINT = "\n".join(label for _, label in STYLE_DIMENSIONS)
_SYSTEM_PROMPT = f"""你在帮一位读者分析他爱读的一段文字的文风，好让之后写的小说贴着这个味道来。

读下面这段样本文字，从五个维度提炼它的文风特征，为以下每一项各输出一行，严格用「标签：内容」\
的格式，标签必须和下面列出的一字不差：
{_DIMENSION_LINES_HINT}

每一项的含义：
- 人称：叙事用第几人称、是否限知视角。
- 语气：整体情绪基调（如冷峻克制、温暖感伤、凌厉紧张）。
- 句式节奏：长句还是短句为主、节奏快慢。
- 意象密度：画面/意象堆叠的多少（高/中/低），可点出典型意象。
- 段落长度倾向：段落偏长还是偏短、铺陈方式。

要求：
- 只根据这段样本实际读到的特征提炼，不要杜撰样本里没有的东西。
- 每项内容简洁，一句话概括即可，说人话、不要文绉绉的书面腔。
- 只输出这五行，不要输出任何其他文字、不要编号、不要 Markdown、不要引号包裹。"""


def resolve_sample_text(*, sample_id: str | None, sample_text: str | None) -> str:
    """把「库选 sampleId」或「粘贴 sampleText」统一解析为待抽取的样本原文（AC1）。

    两路径最终喂同一条真实抽取链（契约单一，story Task 1 决策）：
    - sample_id 命中预置库 → 返回该样本较完整原文（text）。
    - sample_text（粘贴）→ 原样返回（长度/非空校验在 schema 层已做）。
    - sample_id 未命中预置库 → 400 unknown_style_sample（防伪造不存在的 id）。

    schema 层已保证二者恰有其一（互斥且至少一个），此处不重复校验存在性；对未知 id 明确拒绝。
    """
    if sample_id is not None:
        sample = _SAMPLE_BY_ID.get(sample_id)
        if sample is None:
            raise ErrorEnvelope(
                code="unknown_style_sample",
                message="所选文风样本不存在。",
                http_status=400,
            )
        return sample.text
    # schema 互斥校验保证：sample_id 为 None 时 sample_text 必非空。仍显式 raise 而非 assert
    # ——assert 在 python -O 下被剥离，不宜用于承载运行期不变量（模块级公共函数可能被绕过
    # schema 直接调用）。走 400：调用方未提供任何有效锚定来源。
    if sample_text is None:
        raise ErrorEnvelope(
            code="unknown_style_sample",
            message="未提供文风样本。",
            http_status=400,
        )
    return sample_text


def _build_messages(sample_text: str) -> list[dict[str, str]]:
    """组装抽取消息：system prompt（五维固定前缀输出要求）+ 携样本原文的 user 消息。"""
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": f"样本文字：\n{sample_text}"},
    ]


def _parse_style_profile(content: str) -> str:
    """解析五维抽取响应为规范化 style_profile 文本（防御性，仿 _parse_extract_response）。

    按「标签：内容」逐行匹配五维标签，只收本 story 五维集合内的行；模型偏离格式时不崩溃。
    落库形态：五维各一行「标签：内容」的多行文本（V1 存 Text，非 JSONB——story 待确认项 1）。
    缺失的维度不强行补，只输出成功解析到的行；调用方据「是否解析到任何维度」判空产兜底。
    """
    label_to_key = {label: key for key, label in STYLE_DIMENSIONS}
    parsed: dict[str, str] = {}
    for raw in content.splitlines():
        line = raw.strip()
        if "：" not in line and ":" not in line:
            continue
        sep = "：" if "：" in line else ":"
        label, _, value = line.partition(sep)
        label = label.strip()
        value = value.strip()
        if label in label_to_key and value:
            parsed[label_to_key[label]] = value
    # 按五维固定顺序拼回「标签：内容」多行文本（保序、便于前端按维度展示）。
    lines = [
        f"{label}：{parsed[key]}"
        for key, label in STYLE_DIMENSIONS
        if key in parsed
    ]
    return "\n".join(lines)


async def preflight_style_anchor(
    session: AsyncSession, *, user_id: uuid.UUID, project_id: uuid.UUID
) -> None:
    """抽取前的 HTTP 前置校验：租户守卫 + 护栏（仿 explorer_agent.preflight_interpret）。

    用请求注入的 web session 做只读校验（get_owned_project / check_quota 均不写库、无记账），
    与后续抽取用的独立 session（extract_and_anchor_style 内）职责分离——预检不触碰记账路径。

    - 租户守卫（陷阱①，二义合一 404）：project 不属当前 user 即 404 project_not_found，不区分
      「不属于我」与「不存在」、不写 403（复用 exploration_service 的 404，勿新造 code）。
    - **不加 mode 守卫**（受控决策 4）：文风锚点作品级、两模式均可锚定。
    - 护栏（陷阱②，承 2.1 AC6）：托管触顶抛 429 不进抽取、BYOK 短路放行。
    """
    project = await project_repo.get_owned_project(session, project_id, user_id)
    if project is None:
        raise exploration_service._exploration_not_found()
    await usage_service.check_quota(session, user_id)


async def extract_and_anchor_style(
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    sample_text: str,
) -> StoryBible:
    """真实抽取样本文风为 style_profile 并 upsert 到 story_bible（AC2/AC3/AC6）。

    **独立 session 自管**（陷阱⑩，同 free_explorer_agent.extract_clues 范式）。流程：
    1. 重校验租户（独立 session 上，保证直接调用本编排也受保护）。
    2. 护栏 check_quota（**在构造/调用 provider 之前**，陷阱②）。
    3. 构造带记账 Provider（MeteredProvider，禁自己 new DeepSeekProvider，陷阱①）。
    4. provider.chat 非流式一次性结构化抽取（快档 + 足量 max_tokens，陷阱⑥）。
    5. 防御性解析五维；空产（模型没吐任何有效维度）抛 generate_failed，调用方转 error/500，
       不落空 style_profile。
    6. upsert 到 story_bible.style_profile + commit。

    返回落库后的 StoryBible 行（含 style_profile），供端点组装响应。
    """
    settings = get_settings()
    async with async_session_maker() as session:
        # 1. 租户守卫（陷阱①）：独立 session 上重校验 project 归属。不加 mode 守卫（决策 4）。
        project = await project_repo.get_owned_project(session, project_id, user_id)
        if project is None:
            raise exploration_service._exploration_not_found()

        # 2. 护栏（陷阱②）：**必须在构造/调用 provider 之前**。托管触顶抛 429 不进抽取。
        await usage_service.check_quota(session, user_id)

        # 3. 构造带记账 Provider（MeteredProvider 包裹，记账自动、billing_path 按 BYOK 态定）。
        provider = await get_provider_for_user(session, user_id, project_id=project_id)

        # 4. 非流式一次性结构化抽取（同 extract_clues；快档 + 足量 max_tokens 防挤空，陷阱⑥）。
        result: ChatResult = await provider.chat(
            _build_messages(sample_text),
            model=settings.deepseek_model_fast,
            max_tokens=_MAX_TOKENS,
        )

        # 5. 防御性解析五维。空产兜底：一个维度都没解析到 → 不落空值、抛 generate_failed
        #    让调用方转错误（承 explorer/free 空产不落库先例）。
        style_profile = _parse_style_profile(result.content)
        if not style_profile.strip():
            raise ErrorEnvelope(
                code="generate_failed",
                message="文风抽取失败，请稍后重试。",
                http_status=502,
            )

        # 6. upsert style_profile 到 story_bible（get-or-create）+ commit（事务边界在 service）。
        #    首次锚定并发（bible 行尚不存在）时两请求都走 INSERT 分支，第二条 commit 撞
        #    (user_id, project_id) 唯一约束抛 IntegrityError——照 exploration_service.
        #    enter_exploration 竞态兜底范式：rollback 后改走 UPDATE 落先到者已建的行，兑现
        #    幂等 200（last-write-wins）而非冒泡 500。已存在行走 UPDATE 分支无此冲突。
        try:
            bible = await story_bible_repo.upsert_style_profile(
                session,
                user_id=user_id,
                project_id=project_id,
                style_profile=style_profile,
            )
            await session.commit()
        except IntegrityError:
            await session.rollback()
            bible = await story_bible_repo.get_by_project(
                session, user_id=user_id, project_id=project_id
            )
            if bible is None:
                # 唯一约束触发却重查不到：状态异常（非预期），交全局 handler 兜底 500。
                raise
            bible.style_profile = style_profile
            await session.commit()
        # commit 后 expire_on_commit=False（session_maker 配置）保对象属性仍可读，端点直接序列化。
        return bible
