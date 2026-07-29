"""Explorer Agent：引导探索「理解用户自述」的业务编排（Story 2.3 AC4）。

引导 Agent 的**唯一**真实 LLM 职责——读「一道题 + 用户一句话自述」，把它凝练为该题的
一句话答案（口吻对齐预设选项 value 的全句风格），忠于用户原意、去 AI 味（NFR1 红线）。
**绝不生成/改写题目**（题库是前端定长常量，动态选题属 V2 EXP-P01，不在本 story）。

分层（architecture.md router→service→provider）：本模块是探索域 service，经 LLMProvider
抽象调 LLM（**禁直调 openai**，陷阱①），生成前过 check_quota 护栏（陷阱②）、Provider 层自动
记账（AR14）。**不持久化**（answer/message 落库归 2.4）、**不生成设定卡**（Epic 3）。

session 生命周期（陷阱⑩，dev 定档②）：本模块是首个「在 web 请求上跑流式记账」的场景。
`MeteredProvider` 的 finally 兜底记账（factory.py:133-145）在 SSE 客户端早断时执行——若届时
依赖注入的 web 请求 session 已 teardown，则记账落在已关闭 session 上会抛错/丢账。故本模块
**用独立 `async_session_maker()` 自管 session** 跑护栏 + 流式 + 记账（仿 ARQ worker 范式），
不依赖请求 session 生命周期：`async with` 的 session 作用域整个覆盖 generator 存活期，
早断（generator aclose）时 finally 兜底记账仍有存活 session，连接释放与记账都不悬空。
"""

import uuid
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from muse.core.db import async_session_maker
from muse.core.settings import get_settings
from muse.providers.base import StreamChunk
from muse.providers.factory import get_provider_for_user
from muse.repositories import project_repo
from muse.services import exploration_service, usage_service

# 理解自述是轻任务 → 快档（deepseek-v4-flash）。**快档是推理模型**（2.1 Debug Log 实测：
# reasoning_content 先吃 token 预算，max_tokens 过小会把正文挤空 done.text 为空串，陷阱⑥）——
# 理解自述虽是短输出也须留余量。取 1024：一句话答案绰绰有余，又给推理档留足预算不挤空正文。
_MAX_TOKENS = 1024

# Explorer Agent system prompt（AC4，NFR1 去 AI 味红线 [[project_muse_quality_redline]]）。
# 职责单一：读「一道题 + 用户一句话自述」→ 输出该题的一句话答案。口吻对齐预设选项 value 全句
# 风格（如「一个在雨夜里独自收到陌生人来信的人。」），广谱网文向、非文学腔
# [[project_muse_target_user]]。明确禁元话语/复述题目/发散建议/Markdown/书面套话，不越界生成
# 新题、不替用户决定故事走向（呼应自由模式「不会替你直接改动设定」的同源克制）。
_SYSTEM_PROMPT = """你在帮一位读者把脑中模糊的故事念头说清楚。

现在他正在回答一道关于故事的问题，并且没有选预设选项，而是用一句话自己作答。\
你的任务是：读懂他这句话想表达的意思，把它凝练成**这道题的一句话答案**。

要求：
- 忠于他的原意，只做澄清和补足画面感，绝不替他扩写、改设定、加他没说的东西。
- 输出**一句话**，就像他自己想清楚后会说出的那句话。参考这种口吻：\
「一个在雨夜里独自收到陌生人来信的人。」「核心冲突来自主角内心——他最大的敌人是自己的记忆。」
- 面向大众网文读者，说人话，不要文绉绉的书面腔。

绝对不要：
- 说「作为 AI」「我理解您的意思是」「根据您的描述」之类的话。
- 复述或点评题目，不要给建议、不要发散、不要反问。
- 用 Markdown、列表、引号包裹、标题等任何格式。
- 生成新的问题，或替他决定故事该怎么走。

直接输出那一句话本身，不要任何前后缀。"""


def _build_messages(question: str, free_text: str) -> list[dict[str, str]]:
    """组装 Explorer Agent 消息：system prompt + 携「题干 + 用户自述」的 user 消息。

    题干与自述都进 user 消息、职责边界靠 system prompt 约束——Agent 只「理解并凝练这一句」。
    """
    user_content = f"问题：{question}\n\n他的回答：{free_text}"
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


async def preflight_interpret(
    session: AsyncSession, *, user_id: uuid.UUID, project_id: uuid.UUID
) -> None:
    """流建立前的 HTTP 前置校验：租户守卫 + 护栏（AC4，陷阱②/③）。

    SSE 端点在返回 `EventSourceResponse` **之前**调用本函数——因为 `EventSourceResponse`
    一旦返回即提交 HTTP 200 头、之后 generator 内抛错只能走 error 事件、无法再改状态码。故
    「流建立前」的错误（租户 404 / 护栏 429）必须在此预检阶段抛出，交全局 handler 转正确 HTTP
    状态（Task 3 错误映射：流建立前走 HTTP 状态，流已开始后才走 error 事件）。

    用**请求注入的 web session** 做只读校验（get_owned_project / check_quota 均不写库、无记账），
    与后续流式记账用的独立 session（interpret_guided_answer 内）职责分离——预检不触碰记账路径，
    故不受陷阱⑩早断丢账约束。

    - 租户守卫（陷阱③，承 2.2 二义合一 404）：project 不属当前 user 即 404，不区分「不属于我」
      与「不存在」、不写 403，复用 exploration_service 的 404，勿新造 code。
    - mode 守卫（AC7，2.4 code review defer 至 2.6 定档）：project.mode 须为 guided，否则 409
      mode_mismatch——自由探索项目调引导专属端点直接拦，不再静默放行。
    - 护栏（陷阱②，承 2.1 AC6）：托管触顶抛 429 不进生成、BYOK 短路放行。
    """
    project = await project_repo.get_owned_project(session, project_id, user_id)
    if project is None:
        raise exploration_service._exploration_not_found()
    exploration_service._require_project_mode(project, "guided")
    await usage_service.check_quota(session, user_id)


async def interpret_guided_answer(
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    question: str,
    free_text: str,
) -> AsyncIterator[str]:
    """理解用户自述，流式产出凝练后答案的正文增量（AC4）。

    产出 **content 正文文本块**（str）逐块 yield；reasoning 片段静默丢弃（引导理解只需最终
    答案，不做「思考中」展示，Task 3 契约）；末尾 StreamUsage 被 MeteredProvider 内部消费记账、
    不外产。调用方（SSE 端点）把 yield 的文本拼成 delta 事件、累计为 done.text。

    **护栏与租户守卫在生成前再校验一次**（陷阱②/③）：本函数用**独立 session**（见模块 docstring
    定档②），与端点预检的 web session 相互独立；在独立 session 上重跑守卫既保证「直接调用本编排的
    其它调用方（如 2.6）也受同样保护」，又保证记账全程落在本函数自管的存活 session 上、不受请求
    session 早断影响。async generator 体在首次 anext 前不执行，端点已预检过、正常路径此处守卫必过、
    无重复副作用（get_owned_project/check_quota 皆只读幂等）。
    """
    settings = get_settings()
    async with async_session_maker() as session:
        # 1. 租户守卫（陷阱③）：独立 session 上重校验 project 归属。
        project = await project_repo.get_owned_project(session, project_id, user_id)
        if project is None:
            raise exploration_service._exploration_not_found()
        exploration_service._require_project_mode(project, "guided")

        # 2. 护栏（陷阱②）：**必须在构造/调用 provider 之前**。托管触顶抛 429 不进生成。
        await usage_service.check_quota(session, user_id)

        # 3. 构造带记账 Provider（MeteredProvider 包裹，记账自动、billing_path 按 BYOK 态定）。
        #    勿自己 new DeepSeekProvider（否则丢记账 + BYOK 分派）。
        provider = await get_provider_for_user(session, user_id, project_id=project_id)

        # 4. 流式：逐 StreamEvent 消费——content 正文 yield 给上层，reasoning 静默丢弃，
        #    StreamUsage 由 MeteredProvider 内部记账（本层不见）。快档 + 足量 max_tokens（陷阱⑥）。
        messages = _build_messages(question, free_text)
        async for event in provider.stream(
            messages,
            model=settings.deepseek_model_fast,
            max_tokens=_MAX_TOKENS,
        ):
            if isinstance(event, StreamChunk) and event.kind == "content":
                yield event.delta
