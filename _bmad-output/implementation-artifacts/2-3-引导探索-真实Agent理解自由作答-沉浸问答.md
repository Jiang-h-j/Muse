---
baseline_commit: c22353dc930ca4f53550af5b37e9cf7da27df01f
---

# Story 2.3: 引导探索——真实 Agent 理解自由作答 + 沉浸问答

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a 选了引导探索的用户，
I want 一次只面对一道题、用选项或一句话作答，且我的自述能被真正理解，
so that 我能零负担地把脑中模糊的故事念头说清楚。

## Acceptance Criteria

> **净新增能力只有 AC4-后端。** AC1/AC2/AC3/AC5 是**原型已实现的沉浸问答交互契约**（UX-DR4，页面即契约），
> 本 story **不改 `app.js`、不回归这些契约**——它们的事实源是 `prototype/app/app.js`，本 story 只交付
> AC4 缺失的「真实 Explorer Agent 理解自述」后端能力。前端接线（消费本 story 的流式端点、把结果纳入该题
> 答案）与 token/fetch 鉴权基座 **defer 至专门的前端集成切片**（见 Dev Notes「受控决策 A」）。

1. **Given** 我在引导探索中（FR6，UX-DR4）
   **When** 页面渲染某一题
   **Then** 只呈现当前一题 + A/B/C/D 选项、不显示已答历史、无右侧线索区（原型 `isGuided` 分叉 app.js:801-803、纯选项式 stage app.js:883-889），进度条显示「引导探索 · 问题 NN / 06」（app.js:885 `问题 ${padStart(2,"0")} / ${totalLabel}`，totalLabel=06）。**本 story 后端 only，此契约由原型保持、不回归。**

2. **Given** V1 用有限问题集（非动态选题）
   **When** 我逐题作答
   **Then** 6 题顺序固定、题目不由 LLM 动态生成（原型 `explorationQuestions` 定长 6 题数组 app.js:5-62；动态选题属 V2 EXP-P01，明确不在本 story）。**Explorer Agent 的唯一 LLM 职责是「理解自述」，绝不生成/改写题目**（AC4）。

3. **Given** 我点选一个预设选项
   **When** 提交该题
   **Then** 走前端记录答案、**不调用 LLM**（原型 `submitGuidedAnswer(option.value)` app.js:985-990、纯前端写 `explorationHistory` app.js:454-478，无 fetch）。**只有自由文本作答才触发后端 Explorer Agent**（AC4）——选项作答零 LLM 成本，是护栏与体验的关键分界。

4. **Given** 第一题支持一句话自述（文案「或者，用一句话说出你的念头」app.js:868）或其余题选「都不是这些？用一句话自己回答」（app.js:875）
   **When** 我用自由文本作答并确认
   **Then** 调用**真实 Explorer Agent** 理解我这句话的意图（V1 引导 Agent 的唯一真实 LLM 职责），把它凝练为该题的一句话答案（口吻对齐预设选项的 `value` 全句风格），**作为该题答案纳入探索**。**本 story 交付此能力的后端**：`LLMProvider.stream` 流式 SSE 端点（Epic 2 异步模型：交互式对话/引导自述理解走 stream 流式，epics.md:457），生成前过 `check_quota` 护栏（AC 承 2.1 AC6）、Provider 层自动记账（AR14）。**产出去 AI 味、忠于用户原意**（NFR1 红线，见陷阱④）。

5. **Given** 我在任一题
   **When** 我查看作答出口
   **Then** 第一题常驻自述表单（`allowCustom` app.js:866-873）、第二题起为可折叠「都不是这些」出口（默认折叠 app.js:874-882，除非该题上次即自述作答则默认展开 `savedIsCustom ? "" : "hidden"` app.js:876）。**本 story 后端 only，此契约由原型保持、不回归。**

## Tasks / Subtasks

- [x] **Task 1：Explorer Agent 理解自述的业务编排（新建 `services/explorer_agent.py`，AC4）**
  - [x] `async def interpret_guided_answer(session, *, user_id, project_id, question, free_text) -> AsyncIterator[StreamEvent]`（异步生成器，逐块产出 Provider 的 `StreamEvent`）：
    1. **租户守卫**：先 `project_repo.get_owned_project(session, project_id, user_id)`——`None` 抛 `exploration_service._exploration_not_found()`（404，越权=不存在，复用 2.2 陷阱① 二义合一，勿新造 code / 勿写 403）。**session 存在性属 2.4 关注**，本 story 只守 project 归属（interpret 无需先建 message）。
    2. **护栏（承 2.1 AC6，兑现 1.8 护栏首次拦「面向用户的生成」）**：`await usage_service.check_quota(session, user_id)`——托管触顶抛 429 不进生成、BYOK 短路放行（usage_service.py:45）。**必须在构造/调用 provider 之前**。
    3. **构造带记账 Provider**：`provider = await get_provider_for_user(session, user_id, project_id=project_id)`（factory.py:152，返回 `MeteredProvider` 包裹 DeepSeek，记账自动、billing_path 按 BYOK 态定）。
    4. **组装 Explorer Agent 消息**：system prompt（见 Task 2）+ user 消息（携带「当前题干 + 用户自述」）。调 `provider.stream(messages, model=<快档>, max_tokens=<足量>)`——**逐 `StreamEvent` 透传**（`StreamChunk`/`StreamUsage`，base.py:69）。
    5. **模型档 + max_tokens**：理解自述是**轻任务**→用快档 `settings.deepseek_model_fast`（deepseek-v4-flash，architecture.md:196）。**⚠️ 快档是推理模型**（2.1 Debug Log 实测：`reasoning_content` 先吃 token 预算，max_tokens 过小会把正文挤空）——`max_tokens` 给足余量（≥512，dev 定并记 Completion Notes）。
  - [x] **不做**：不持久化（answer/message 落库归 2.4）、不生成设定卡（Epic 3）、不碰题库动态选题（V2 EXP-P01）。本模块只「理解一句话 → 流式返回凝练答案」。
  - [x] **命名/落点**：Explorer Agent 是探索域编排，不是焦点一五段流水线（那是 `orchestration/`，Epic 4）。放 `services/explorer_agent.py`（与 `exploration_service.py` 并列，2.6 自由对话可复用同款 stream 编排）；若 dev 判断并入 `exploration_service.py` 更内聚亦可（记 Completion Notes）。
  - [x] **⚠️ session 生命周期验证（dev 必做，记 Completion Notes）**：本 story 是**首次在 web 请求注入的 `SessionDep` 上跑流式记账**——`MeteredProvider` 收 web session（deps.py `get_session`，请求结束自动关闭 db.py:30-33），而 factory.py:47-49 docstring 警告「worker 内用 worker 自己的 session、勿跨用 web 请求 session」（2.1 记账全在 ARQ worker 自管 session）。风险：SSE 客户端**早断**→generator `aclose()`→`MeteredProvider.stream` 的 `finally` 兜底 `record_usage`（factory.py:133-145）执行时，若请求作用域已 teardown、session 已关，记账会抛错/丢账。**dev 须验证早断兜底记账路径**（EventSourceResponse 断连时 finally 是否在 session 存活期内执行），选一处置：① 确认 sse-starlette 的 disconnect 在依赖 teardown 前触发 finally（则安全，记明）；② 或 Explorer Agent 内用独立 session（`async_session_maker()` 自管，仿 worker 范式）跑流式 + 记账，不依赖请求 session 生命周期（更稳，推荐 dev 评估）。**选定即记 Completion Notes**，别让早断丢账悬空。

- [x] **Task 2：Explorer Agent system prompt（AC4，NFR1 去 AI 味红线）**
  - [x] 写「引导自述理解」的 system prompt（放 `services/explorer_agent.py` 模块常量或 `prompts/` 若已有约定；当前无 prompts 目录，就地常量即可）。**职责单一**：读「一道题 + 用户一句话自述」，输出**该题的一句话答案**，忠实用户原意、补足画面感，**口吻对齐预设选项 `value` 的全句风格**（如 app.js:11「一个在雨夜里独自收到陌生人来信的人。」）。
  - [x] **去 AI 味红线（NFR1，[[project_muse_quality_redline]]）**：prompt 明确禁止——元话语（「作为 AI / 我理解您的意思是」）、复述题目、发散建议、Markdown 结构化、书面套话。**只产出凝练后的一句话答案本身**，像用户自己想清楚后说出的那句话。**广谱网文向、非文学腔**（[[project_muse_target_user]]）。
  - [x] **不越界**：prompt 不得让 Agent 生成新题、不替用户决定故事走向（呼应自由模式「不会替你直接改动设定」app.js:1088 的同源克制），只「理解并凝练这一句」。

- [x] **Task 3：流式 SSE 端点（扩展 `routers/exploration.py`，AC4，Epic 2 交互式异步模型）**
  - [x] **端点形态定档**：交互式对话走**直连流式 SSE**（`provider.stream` 逐块推），**不走 2.1 的 ARQ `POST→taskId→GET /events` 那套**（那是「整理为故事设定」等**批量后台任务**的模式，2.5/2.7 用；交互式对话是 token 级增量，两种模态不同——epics.md:457 明确二分）。故**不复用** `core/sse.py` 的 `event_stream`（Redis Pub/Sub + worker 快照，为 ARQ 设计）。
  - [x] 新端点（挂在探索 project 层级下，与 `POST /{project_id}/explore` 并列，prefix 已是 `/api/projects`）：
    - **`POST /api/projects/{project_id}/explore/guided/interpret`** → `EventSourceResponse`（sse-starlette，与 tasks.py:74 同款响应类型）。依赖 `CurrentUser` + `SessionDep`（deps.py:24/55，自动鉴权 + 注入 async session）。
    - **Request schema**（新增 `GuidedInterpretRequest(CamelModel)`，schemas/exploration.py）：`question: str`（当前题干，前端从 `explorationQuestions[view].question` 传）+ `free_text: str`（用户自述，边界 camelCase `freeText`）。**dev 决策点**：题库归属——V1 题库是前端常量（app.js:5-62），端点收 `question` 文本即可、后端不镜像题库（记 Completion Notes）；若判断后端应拥有「有限问题集」则可改为收 `questionIndex` 后端查表（更集中，但需把题库搬后端，超出本切片，建议 defer）。
    - **入参校验**：`free_text` 空/纯空白 → 422（Pydantic `min_length=1` 或 service 层校验，仿原型 `if (!answer) return` app.js:456）；`project_id` 非法 UUID FastAPI 自动 422。
  - [x] **SSE 事件契约（交互式流式，dev 定档并记 Completion Notes）**：推荐 `delta`（正文增量，payload `{text}`）× N → 终态 `done`（payload `{text: <完整凝练答案>}`，供前端把该题答案纳入探索）→ 失败 `error`（payload 复用错误 envelope `{code, message}`）。**camelCase payload**（architecture.md:336）。可复用 `sse.format_sse_event`（core/sse.py:75，纯 JSON 编码、模态无关，可复用）。**reasoning 片段**（`StreamChunk.kind=="reasoning"`）：引导理解只需最终答案，**静默丢弃不前推**（不做「思考中」展示，保持简洁；2.6 若需再评估）。
  - [x] **错误映射**：`check_quota` 触顶的 `ErrorEnvelope(429)`、租户 404、provider `generate_failed`/`provider_not_supported`——在**建立 SSE 流之前**发生的（校验/护栏阶段）走正常 HTTP 错误响应（全局 handler 转 envelope）；**流已开始后**的 provider 异常经 `error` 事件推送（错误文案**泛化**、原始 exc 只 `logger.exception`，承 2.1 patch「内部信息不外泄」）。
  - [x] `main.py` **无需改**：`exploration.router` 已注册（main.py:28），新端点挂同一 router 自动生效。

- [x] **Task 4：硬化 DeepSeek 流式生命周期 + 兑现 2.1 流式 defer（`providers/deepseek.py`，闭合 deferred-work.md:81）**
  - [x] **闭合 2.1 defer①「OpenAI 流式未 async with/显式 close」**（deferred-work.md:81，明确归「Epic 2 探索对话接线切片」=本 story）：`deepseek.py stream()` 现 `create(stream=True)` 后直接 `async for`（deepseek.py:140-151），中途 break/异常时底层 httpx 流可能不归还连接池。改为 `async with await self._client.chat.completions.create(...) as stream:` 或 `try/finally: await stream.close()`——保证消费方早断（SSE 客户端断连 → generator `aclose`）时连接释放。**与 MeteredProvider.stream 已有的 try/finally 兜底记账（factory.py:114-145）配套**：底层 close + 上层兜底记账，早断路径既不漏连接也不漏账。
  - [x] **闭合 2.1 defer②「流式 include_usage 真实验证」**（2.1 Completion Notes L280 + deferred-work.md:81，归本切片）：本 story stream 首次真实接线——加 `@requires_deepseek` 契约测试（见 Task 5）真打一次 DeepSeek stream，断言末尾 `StreamUsage` 非空且 `estimated=False`（服务端确回 usage），坐实 `stream_options={"include_usage": True}` 在真实 API 生效（2.1 只离线 mock 验过两分支）。
  - [x] **不改** stream 的事件产出逻辑（StreamChunk/StreamUsage 契约 base.py:39-65 已定，2.1 稳定）——本 task 只加生命周期硬化 + 真实验证，不动数据形状。
  - [x] **⚠️ 必须同步重构 2.1 既有 stream 单测 mock（否则必回归红）**：`tests/test_providers.py:135,155` 的两个 stream 用例用 `_aiter(chunks)`（tests/test_providers.py:118-120）作 mock——那是**纯 async generator**，只有 `aclose()`、**无 `close()`、无 `__aenter__`**；而真实 OpenAI `AsyncStream` 恰相反（有 `close()`/`__aenter__`、无 `aclose()`）。故无论 dev 选 `async with` 还是 `try/finally: await stream.close()`，这两个既有用例**必然 TypeError/AttributeError 回归红**。**修正**：把 mock 重构为模拟 `AsyncStream` 的 fake（同时支持 `__aenter__`/`__aexit__`/`__aiter__`/`close`），使新生命周期写法与既有断言都通过。**`tests/test_providers.py` 因此纳入本 story 扩展文件**（见 Project Structure Notes）。

- [x] **Task 5：测试（新建 `tests/test_explorer_agent.py`，AC4 全覆盖）**
  - [x] **Provider/编排单元（离线，mock `provider.stream`，不打真实 API）**：
    - `interpret_guided_answer` happy：mock `get_provider_for_user` 返回吐 `StreamChunk×N + StreamUsage` 的假 provider → 断言逐块透传、reasoning 片段被丢弃/正文保留（按 Task 3 契约）。
    - **护栏拦截（承 2.1 AC6）**：mock `check_quota` 抛 `ErrorEnvelope(quota_exceeded, 429)` → 断言**在调用 provider 之前**抛出、provider.stream **未被调用**（护栏在生成前，关键：别先生成再判额度）。
    - **租户隔离（AC4 承 2.2 陷阱①）**：mock `get_owned_project` 返 None → 抛 404 `project_not_found`；provider 未被构造。
    - **去 AI 味/单一职责**：断言组装的 messages 含 system prompt 且 user 消息携带题干 + 自述（prompt 内容契约的最小断言，防未来误删约束）。
  - [x] **SSE 端点（`@requires_db`，走完整 HTTP 栈 + 真实 DB 建 user/project；provider 仍 mock）**：
    - **鉴权（离线，仿 test_exploration.py 鉴权段）**：无 token / 过期 token `POST .../interpret` → 401。
    - **端到端 happy**：建 project → mock provider.stream → `POST .../interpret {question, freeText}` → 收 SSE `delta×N → done`（done.text = 完整答案）；断言 camelCase payload。
    - **422**：`freeText` 空 → 422。
    - **护栏 429**：mock check_quota 触顶 → 端点返 429（流建立前的错误走 HTTP 状态，非 error 事件）。
    - **租户 404**：用户 B 对用户 A 的 project interpret → 404。
  - [x] **真实契约（`@requires_deepseek`，CI 默认 skip，闭合 2.1 流式 defer，Task 4）**：真打一次 DeepSeek stream 的 interpret → 断言收到正文 delta + 末尾 usage 非空且 `estimated=False`；给足 max_tokens 避免推理档挤空正文（2.1 Debug Log 教训）。**若不加则 Completion Notes 说明流式真实 usage 仍未验证**（不建议——本切片正是该 defer 的归属点）。
  - [x] **conftest 无需改**：复用 `@requires_db`/`@requires_redis`（SSE 端点本身不需 Redis——直连流式非 ARQ）/`@requires_deepseek`/`make_user`/`auth_headers`；无新门禁。

- [x] **Task 6：质量门禁 + 验证（ready → done 前必过）**
  - [x] `cd backend && uv run ruff check .` + `uv run mypy`（新增 `services/explorer_agent.py`、`schemas/exploration.py` 扩展、`routers/exploration.py` 扩展类型标注完整；`AsyncIterator[StreamEvent]` 类型正确）。
  - [x] **业务层无直接 import openai**（架构最硬红线，architecture.md:341）：`grep -rn "import openai\|from openai" backend/src/muse` 仍只 `providers/deepseek.py` 命中——Explorer Agent 走 `LLMProvider` 抽象，禁直调。
  - [x] `MUSE_DB_READY=1 MUSE_REDIS_READY=1 uv run pytest` 全绿；**全量回归无既有用例回归**（2-2 收尾 144 passed/1 skipped）。**注意**：Task 4 改 `deepseek.py stream()` 生命周期**必然要求同步重构 `test_providers.py` 两个 stream mock**（纯 generator → 支持 async context manager 的 fake，见 Task 4 ⚠️）——这是本 story 唯一「改既有」处，改后须确认这两个 stream 用例 + 全量回归仍绿。
  - [x] **迁移**：本 story **不建表**（interpret 不持久化，message 表归 2.4）——确认 `alembic upgrade head` 无新 revision、`alembic check` 无 model 漂移（Explorer Agent/端点不含 ORM 模型）。
  - [x] **`prototype/app/app.js` 一字节不改**（`git status prototype/` 应为空、`grep -c "fetch(" prototype/app/app.js` 仍为 0）——**受控决策 A：本 story 后端 only**，引导页前端接线 + token/fetch 基座 defer 至前端集成切片（见 Dev Notes）。
  - [x] **租户守卫 grep 自查**：interpret 路径的 project 校验含 `user_id`（经 `get_owned_project`）；无绕过 user_id 的查询（Enforcement architecture.md:357）。

## Dev Notes

### 🔑 本 story 的性质：Epic 2 引导链首个「真实 LLM 交互」story——净新增只有 AC4-后端，`app.js` 零改动

2.3 是引导链 `2.2 → 2.3 → 2.4 → 2.5` 的第一环（epics.md:454），也是**全项目第一次「面向用户的 LLM 交互接线」**。但**沉浸问答的交互形态原型早已实现**：单题聚焦、A/B/C/D 选项、无历史/无线索区、进度条、第一题自述、其余题「都不是这些」折叠出口、翻回高亮回填——全在 `prototype/app/app.js` 里（AC1/AC2/AC3/AC5 的事实源）。**本 story 唯一缺失并交付的是 AC4：把「用户一句话自述」送进真实 Explorer Agent 理解**（引导 Agent 的**唯一** LLM 职责）。形态上是**又一个后端切片**：Explorer Agent 编排 + 流式 SSE 端点 + 护栏/记账接入 + 测试，`app.js` 零改动（延续 1.7/1.8/2.1/2.2 的后端优先节奏）。

**范围边界（本 story 做 / 不做）**：
| 做 | 不做（越界 / 属别的 story） |
|---|---|
| Explorer Agent「理解自述」编排（Task 1/2） | 动态选题 / 题库原型库（V2 EXP-P01）；生成/改写题目（Agent 禁做） |
| `LLMProvider.stream` 流式 SSE 端点（Task 3，交互式异步模型 epics.md:457） | ARQ 批量「整理为故事设定」任务（2.5/2.7 用 2.1 的 ARQ 底座） |
| 护栏 `check_quota` 首次拦「面向用户生成」+ Provider 记账（承 2.1 AC6/AR14） | 额度并发 TOCTOU 加固（2.1 defer 至 4.4，本 story 非并发批量生成面，续 defer） |
| 闭合 2.1 流式 defer：stream 生命周期硬化 + 真实 usage 验证（Task 4） | ClaudeProvider（盲测 4.1）；custom provider 补齐（custom 启用切片） |
| 后端契约 + pytest（Task 5） | **前端接线**：引导页消费路由 id、调 interpret 流式端点、把结果纳入该题答案、token/fetch/401 跳转基座（**受控决策 A，defer 至前端集成切片**） |
| project 归属租户守卫（复用 2.2 二义合一 404） | 探索答案/对话**持久化**（2.4 建 `exploration_message` 落库）；「整理中」过渡态 + 整理任务（2.5） |

### 🔑 受控决策 A（用户 2026-07-27 授权「You choose whatever is best」）：本 story 后端 only，前端接线 defer

**背景**：原型 `app.js` 当前 **100% mock——全站零 `fetch`、登录是假 `setTimeout → #/projects`（app.js:1717-1719）、无任何 token 携带 / 鉴权失败跳转 / error envelope 前端分支**。2.2 Dev Notes 写「前端接线 defer 至 2.3/2.6」，但 1.7 deferred-work.md:45 明确把前端 fetch/token 横切基座列为**独立的「统一前端接线切片」**职责（「拖入即引入 fetch/token 横切基础设施……属独立前端接线 story 职责」）。两处措辞张力。

**定档：2.3 只交付 AC4 后端（Explorer Agent 理解 + 流式端点 + 测试），`app.js` 零改动；引导页前端接线（消费 interpret 流、把凝练答案纳入该题、token/fetch/401 基座）defer 至专门的前端集成切片。**
- **依据**：① 4/5 AC 已由原型 mock 满足（沉浸问答交互契约 UX-DR4 是「页面即契约」的既有事实，非本 story 新建）；② 全项目 1.7→2.2 一路后端优先、`app.js` 零改动，前端 fetch/token 基座从未落地——2.3 拖入它 = 一个 story 塞下「首个前端鉴权基座 + 首个 LLM 交互 + 引导页接线」，体量爆炸且违背既定节奏；③ 1.7 已把前端接线定性为独立关注点。
- **落地**：本 story 后端契约做实做透（流式端点就绪、护栏/记账串通、真实 usage 验证），为前端集成切片 + 2.4 持久化**铺好路**；`git status prototype/` 须为空（Task 6 门禁）。
- **不让 defer 悬空**：前端集成切片须做——引导页 `renderExploration` 的自述提交（app.js:1016-1023 `submitGuidedAnswer(customInput)`）改为调 `POST .../interpret` 消费流、把 `done.text` 作为该题答案写入 `explorationHistory`；连同 token 携带 / 401 跳转 / error envelope 分支一次性引入（1.6/1.7 已论证的「前端 API 接线是独立关注点」方法论）。**登记于 Completion Notes + deferred-work.md**。

### 🔑 受控决策 B（用户授权 dev 定档）：理解自述走 `LLMProvider.stream` 流式 SSE（非同步 chat、非 ARQ）

- **依据**：Epic 2 异步模型明文——「**交互式对话（自由聊天、引导自述理解）走 `LLMProvider.stream` 流式 SSE**；『整理为故事设定』等凝练走 ARQ 后台任务 POST→taskId→GET /events」（epics.md:457）。引导自述理解是**交互式**，落 stream 流式端点，**不落 ARQ**。
- **额外收益**：本切片是 2.1 两条流式 defer 的**指定归属点**——「流式 include_usage 真实验证」（2.1 Completion Notes L280）+「OpenAI stream 生命周期硬化」（deferred-work.md:81「归 Epic 2 探索对话接线切片」）。2.3 是第一个真实用 stream 的地方，顺带闭合（Task 4）。
- **模态区分（勿混）**：交互式流式 = 直连 `provider.stream` 逐块推、**无 Redis Pub/Sub、无 worker、无快照补发**（那套 `core/sse.py`/`routers/tasks.py` 是 ARQ 批量任务专用）。interactive 端点只需 `EventSourceResponse(<async gen over provider.stream>)`，`format_sse_event` 可复用（纯 JSON 编码）。
- **为 2.6 铺垫**：自由探索多轮对话（2.6，FR9）也走 stream 流式——本 story 定的 interactive SSE 契约（delta/done/error）与编排范式，2.6 可直接复用同款。

### 🔑 强制复用 / 对齐的既有事实（照现状，勿另起炉灶）

- **Provider 抽象 + 工厂（2.1 交付，直接消费）**：
  - `providers/base.py`：`LLMProvider.stream(messages, *, model, max_tokens) -> AsyncIterator[StreamEvent]`；`StreamEvent = StreamChunk | StreamUsage`（base.py:69）；`StreamChunk{delta, kind}`（kind: content/reasoning，base.py:39-48）；`StreamUsage{prompt/completion/total_tokens, model, estimated}`（base.py:51-65）。`Message = dict[str,str]`（OpenAI 兼容 role/content，base.py:19）。
  - `providers/factory.py`：`get_provider_for_user(session, user_id, *, project_id=None) -> LLMProvider`（factory.py:152）返回 `MeteredProvider`——**记账自动**（stream 末尾 StreamUsage 到达即 record_usage，早断经 try/finally 兜底记账 factory.py:114-145）。**Explorer Agent 直接用工厂拿 provider，勿自己 new DeepSeekProvider**（否则丢记账 + BYOK 分派）。
  - `providers/deepseek.py`：`stream()` 已 `stream_options={"include_usage": True}`（deepseek.py:145）、区分 reasoning/content、末尾产 StreamUsage（API 回报或本地兜底 estimated=True）。**本 story Task 4 只加生命周期 close 硬化，不改数据产出。**
- **护栏 + 记账接口（1.8 交付、2.1 首接）**：`usage_service.check_quota(session, user_id)`（usage_service.py:45，托管触顶 429 / BYOK 短路）——**生成前调**；`record_usage` 由 MeteredProvider 内部调（不手写）。**本 story 是护栏首次拦「面向用户的生成」**（2.1 只示范任务演示串联，非真实用户面）。
- **探索域分层（2.2 交付，直接扩展）**：
  - `routers/exploration.py`：`APIRouter(prefix="/api/projects")` + `CurrentUser`/`SessionDep`——interpret 端点挂同一 router（main.py 无需改，已注册 main.py:28）。
  - `services/exploration_service.py`：`_exploration_not_found()`（404 二义合一，exploration_service.py:24-38）——**interpret 租户守卫复用它**，勿新造 code。
  - `repositories/exploration_repo.py` / `project_repo.get_owned_project`：租户守卫黄金范式（id+user_id 同一 where）。
- **SSE 编码复用**：`core/sse.py:75 format_sse_event(event, data) -> {event, data(JSON)}`——纯编码、模态无关，interactive 端点可复用（但**不用** `event_stream`/`publish_event`，那是 Redis Pub/Sub for ARQ）。
- **schema 边界**：`schemas/base.py` `CamelModel`（alias_generator=to_camel，边界唯一转换点）——`GuidedInterpretRequest` 继承它（`freeText`↔`free_text`）。
- **错误 envelope**：`core/errors.py:17 ErrorEnvelope(code, message, detail, http_status)` + 全局 handler——429/404/generate_failed/provider_not_supported 均走它。
- **鉴权依赖**：`core/deps.py` `CurrentUser`（:55）+ `SessionDep`（:24）。
- **测试基建**：`tests/conftest.py` `@requires_db`（:36）/`@requires_redis`（:43）/`@requires_deepseek`（:50）+ `make_user`/`auth_headers`；`tests/test_exploration.py` 鉴权/租户隔离用例结构可照搬；`tests/test_providers.py` stream mock 范式可照搬。
- **无新依赖**：openai（仅 deepseek.py）、sse-starlette（EventSourceResponse，已用于 tasks.py）、FastAPI/SQLAlchemy/Pydantic 全就位。**不引入新库**。

### 🔑 原型行号勘误（页面即契约，核对 baseline c22353d）

epics.md Story 2.3 AC 引用了旧行号（如「app.js:772」「app.js:835」「app.js:844」「app.js:845」），dev 请以下表**核实后的真实行号**为准（原型全长 2374 行、`fetch(` 计数 0=纯 mock）：

| epics 描述引用 | 真实行号（baseline c22353d） | 内容 |
|---|---|---|
| 「只呈现当前一题、无右侧线索区，app.js:772」 | **app.js:801-803** | `if (isGuided) { ... 不显示右侧故事线索侧边栏 }` |
| 「进度条 问题 NN / 06」 | **app.js:885** | `引导探索 · 问题 ${padStart(2,"0")} / ${totalLabel}`（totalLabel=06） |
| 「选项作答走前端记录不调 LLM」 | **app.js:985-990 + 454-478** | `submitGuidedAnswer(option.value)` 纯前端写 `explorationHistory` |
| 「第一题自述 或者用一句话说出你的念头，app.js:835」 | **app.js:866-873** | `allowCustom` 常驻自述表单 |
| 「其余题 都不是这些，app.js:844」 | **app.js:874-882** | 折叠「都不是这些？用一句话自己回答」出口 |
| 「上次自述则默认展开，app.js:845」 | **app.js:862-864,876** | `savedIsCustom ? "" : "hidden"` |
| 「自述提交 → 该题答案」 | **app.js:1016-1023** | `data-guided-custom-form` submit → `submitGuidedAnswer(customInput)`（**前端接线切片在此改为调 interpret 端点**） |

### 关键实现陷阱（务必规避）

- **陷阱①：业务层禁止直接 import/调用 openai（架构最硬红线，architecture.md:341/356）。** Explorer Agent 一律经 `LLMProvider`（工厂注入），openai 只允许在 `providers/deepseek.py`。Task 6 grep 校验。
- **陷阱②：护栏必须在生成前（`check_quota` → 才 `provider.stream`），别先生成再判额度。** 顺序错则托管用户触顶后仍先烧一次 token 才被拦，护栏形同虚设。单测须断言 check_quota 抛 429 时 provider.stream **未被调用**（Task 5）。
- **陷阱③：租户守卫二义合一（承 2.2 陷阱①）。** interpret 先 `get_owned_project(session, project_id, user_id)`——None 即 404 `project_not_found`，**不写 403、不区分「不属于我」与「不存在」**（IDOR 侦察面，NFR3）。复用 `_exploration_not_found()`，勿新造 code。
- **陷阱④：Explorer Agent 输出去 AI 味、忠于原意（NFR1 红线，上线拦路石，[[project_muse_quality_redline]]）。** prompt 禁元话语/复述题目/发散建议/Markdown/书面套话——只产「用户想清楚后会说的那一句」，口吻对齐预设选项 value 全句风格、广谱网文向（[[project_muse_target_user]]）。这是 §七红线的行为判据，不是可选润色。
- **陷阱⑤：交互式流式 ≠ ARQ 任务，别复用 `core/sse.py` 的 Redis Pub/Sub 那套。** interactive 直连 `provider.stream` 逐块推（`EventSourceResponse(async_gen)`），无 worker/无 Pub/Sub/无快照补发。误用 ARQ 那套会凭空引入 Redis 依赖 + worker 进程（本端点根本不需要，测试也不该要 `@requires_redis`）。
- **陷阱⑥：推理档 max_tokens 给足（2.1 Debug Log 实测教训）。** 快档 deepseek-v4-flash 是推理模型，`reasoning_content` 先吃预算——max_tokens 过小（如 100）会把正文挤空、`done.text` 为空串。理解自述虽是短输出也须留余量（≥512，dev 定）。
- **陷阱⑦：流式生命周期——早断须释放连接（闭合 2.1 defer，Task 4）。** SSE 客户端断连 → generator `aclose()` → provider.stream 应 `async with`/`finally close` 底层 httpx 流，否则连接泄漏累积。与 MeteredProvider 已有的 try/finally 兜底记账（factory.py:114）配套：连接释放 + 不漏账。
- **陷阱⑧：本 story 不建表、不持久化。** interpret 只「理解 → 流式返回」，answer/message 落库归 2.4（`exploration_message` 按需建表 epics.md:455）。`alembic check` 无漂移（Task 6）。手别痒提前建 message 表。
- **陷阱⑨：`app.js` 一字节不改（受控决策 A）。** 引导页接线 + token/fetch 基座 defer 至前端集成切片。`git status prototype/` 须为空、`fetch(` 计数保持 0。
- **陷阱⑩：web 请求 session 上跑流式记账的早断丢账风险（首次出现）。** `MeteredProvider` 的 finally 兜底 `record_usage`（factory.py:133-145）在 SSE 客户端早断时执行，若届时 web 请求 session 已 teardown 则记账失败。2.1 记账全在 worker 自管 session，本 story 首次落在 web session 上——dev 须验证或改用独立 session（见 Task 1 ⚠️）。

### Project Structure Notes

- **新增文件**：`services/explorer_agent.py`（Explorer Agent 理解自述编排 + system prompt）、`tests/test_explorer_agent.py`。
- **扩展文件**：`schemas/exploration.py`（+`GuidedInterpretRequest`）、`routers/exploration.py`（+`POST /{project_id}/explore/guided/interpret` 流式端点）、`providers/deepseek.py`（stream 生命周期硬化，Task 4）、`tests/test_providers.py`（Task 4 连带：两个 stream mock 重构为支持 async context manager 的 fake，本 story 唯一「改既有」处）。
- **不改**：`main.py`（exploration.router 已注册）、`core/sse.py`（interactive 不用 Pub/Sub 那套，仅复用 format_sse_event）、`prototype/app/*`（后端 only，受控决策 A）、`conftest.py`（无新门禁）、`models/*`（不建表）。
- **迁移**：无新表、无新 revision（interpret 不持久化）。
- **依赖零新增**：openai/sse-starlette/FastAPI/SQLAlchemy/Pydantic 全就位。
- **无偏差**：严格遵循 architecture.md 分层（router→service→provider）、camelCase 边界、Provider 唯一 LLM 出口、Provider 层记账、user_id 租户守卫、交互式 stream 流式（epics.md:457）。

### 测试形态

- 后端 pytest + pytest-asyncio（`asyncio_mode=auto`）。
- **Explorer Agent 编排单元离线**（mock `get_provider_for_user` + `check_quota`，不打真实 API，CI 必过）：happy 透传、护栏 429 前置拦截、租户 404、prompt 契约最小断言。
- **SSE 端点 `@requires_db`**（完整 HTTP 栈 + 真实 DB 建 user/project，provider mock）：鉴权 401 / happy delta→done / 422 空 freeText / 护栏 429 / 租户 404。**不需 `@requires_redis`**（直连流式非 ARQ，陷阱⑤）。
- **真实 DeepSeek 契约 `@requires_deepseek`**（CI 默认 skip）：闭合 2.1 流式 usage defer——真打 stream，断言末尾 StreamUsage 非空且 estimated=False。
- 全量回归：2-2 收尾 144 passed/1 skipped，本 story 只增（Task 4 改 deepseek.py stream 生命周期须确认 2.1 test_providers stream 用例仍绿）。

### 待澄清（保存至末尾，请用户确认）

- **无阻塞性疑问。** 两处范围分叉已于 2026-07-27 征询，用户授权「You choose whatever is best」，本 story 按最佳方案定档（见受控决策 A/B），依据均有权威出处。以下为 **dev 定档的受控决策**（非阻塞，dev 照此执行，实现后记 Completion Notes）：
  1. **后端 only、前端接线 defer**（受控决策 A）——`app.js` 零改动；引导页接线 + token/fetch 基座归前端集成切片，登记 deferred-work.md 不悬空。
  2. **理解自述走 `provider.stream` 流式 SSE**（受控决策 B）——非同步 chat、非 ARQ；顺带闭合 2.1 两条流式 defer（Task 4）。
  3. **interpret 端点契约**：`POST /api/projects/{project_id}/explore/guided/interpret`，body `{question, freeText}`，SSE `delta×N → done → error`；题库仍前端常量、端点收 question 文本（后端不镜像题库，若需集中化归后续切片）。
  4. **模型档 = 快档（deepseek-v4-flash）+ 足量 max_tokens**（≥512，推理档余量，2.1 教训）。
  5. **不持久化、不建表**——answer/message 落库归 2.4；「整理中」过渡态 + 整理任务归 2.5。
  6. **护栏 TOCTOU 并发续 defer 至 4.4**：本 story 是交互式单次流式、非并发批量生成面，`check_quota` 时间窗风险未现实化（延续 2.1/1.8 defer 裁定，不新增并发面）。
  7. **web session 上跑流式记账的早断丢账**（陷阱⑩/Task 1 ⚠️）：首次在请求注入 session 上记账，dev 须验证 SSE 早断兜底记账路径或改用独立 session；选定记 Completion Notes。

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-2.3（L511-537）] — 用户故事、5 条 GWT AC（单题沉浸/有限问题集/选项不调 LLM/自述走真实 Agent/自述出口）。
- [Source: _bmad-output/planning-artifacts/epics.md#Epic-2（L450-457）] — Epic 2 概述、Story 依赖链 2.2→2.3→2.4→2.5、**异步模型二分「交互式对话/引导自述理解走 LLMProvider.stream 流式 SSE；整理走 ARQ」（L457，受控决策 B 依据）**、按需建表（message 归 2.4）、边界（整理归 E2、设定卡归 E3）。
- [Source: _bmad-output/planning-artifacts/epics.md#FR6（L45,171）] + [#UX-DR4（L155）] — 引导接入真实 Explorer Agent（有限问题集非动态选题）、纯选项式沉浸问答一次一题、第一题自述其余题「都不是这些」出口——AC1-5 契约事实源。
- [Source: _bmad-output/planning-artifacts/architecture.md#焦点一（L194-201）] — LLMProvider 抽象（chat/stream/count_tokens）、DeepSeek 双档（v4-pro 思考 / v4-flash 快，128K）、用量计量在 Provider 层、换模型后门。
- [Source: _bmad-output/planning-artifacts/architecture.md#Communication-Patterns（L334-336）] — SSE 三事件 progress/result/error、payload camelCase（interactive 端点的 delta/done/error 契约参照其 camelCase + error 复用 envelope 原则）。
- [Source: _bmad-output/planning-artifacts/architecture.md#Process-Patterns+Enforcement（L340-361）] — LLM 一律走 Provider 接口、业务层禁直调 openai（陷阱①）；记账在 Provider 层；租户守卫在 repository 携 user_id；长时生成 POST+SSE 禁轮询。
- [Source: prototype/app/app.js:5-62] — `explorationQuestions` 定长 6 题数组（AC2 有限问题集、题目非 LLM 生成的事实源）。
- [Source: prototype/app/app.js:785-898] — `renderExploration` 引导分叉：单题聚焦、选项卡、进度条、自述表单/都不是折叠出口（AC1/AC5 契约，行号勘误见 Dev Notes）。
- [Source: prototype/app/app.js:454-478,985-1023] — `submitGuidedAnswer` 纯前端写 `explorationHistory`（AC3 选项不调 LLM）；`data-guided-custom-form` submit → 自述提交（AC4 前端接线点，前端集成切片在此改调 interpret 端点）。
- [Source: prototype/app/app.js:1717-1719] — 登录假 `setTimeout → #/projects`（受控决策 A 依据：前端全 mock、无 token/fetch 基座）。
- [Source: backend/src/muse/providers/base.py（L19,39-69,103-117）] — `Message`、`StreamChunk{delta,kind}`、`StreamUsage{tokens,model,estimated}`、`StreamEvent` 联合、`LLMProvider.stream` 签名（Explorer Agent 消费契约）。
- [Source: backend/src/muse/providers/factory.py（L40-149,152-205）] — `MeteredProvider`（stream 末尾/早断兜底自动记账，L114-145）、`get_provider_for_user(session, user_id, *, project_id)`（BYOK/托管分派，Explorer Agent 用它拿 provider）。
- [Source: backend/src/muse/providers/deepseek.py（L126-181）] — `stream()` include_usage + reasoning/content 区分 + 末尾 StreamUsage（Task 4 加生命周期 close 硬化、真实 usage 验证的对象；deepseek.py 是唯一 openai 出口）。
- [Source: backend/src/muse/services/usage_service.py（L45）] — `check_quota(session, user_id)`（托管触顶 429 / BYOK 短路，生成前调，陷阱②；本 story 护栏首次拦真实用户生成）。
- [Source: backend/src/muse/routers/exploration.py（全）] — 探索 router（prefix `/api/projects`、CurrentUser/SessionDep），interpret 端点挂此、main.py 无需改。
- [Source: backend/src/muse/services/exploration_service.py（L24-38）] — `_exploration_not_found()`（404 二义合一，interpret 租户守卫复用，陷阱③）。
- [Source: backend/src/muse/repositories/exploration_repo.py（L19-33）] + [project_repo.get_owned_project] — 租户守卫范式（id+user_id 同一 where）。
- [Source: backend/src/muse/routers/tasks.py（L54-74）] — `EventSourceResponse` 用法参照（**但 interactive 不用其 Redis Pub/Sub event_stream**，陷阱⑤）。
- [Source: backend/src/muse/core/sse.py（L75-81）] — `format_sse_event`（纯 JSON 编码，interactive 可复用）；**event_stream/publish_event 不复用**（ARQ 专用）。
- [Source: backend/src/muse/schemas/base.py（L29-34）] — `CamelModel`（GuidedInterpretRequest 边界 freeText↔free_text）。
- [Source: backend/src/muse/core/deps.py（L24,55）] + [core/errors.py（L17）] — `SessionDep`/`CurrentUser` 鉴权；`ErrorEnvelope`（404/429/generate_failed）。
- [Source: backend/tests/conftest.py（L36,43,50）] + [test_exploration.py] + [test_providers.py] — `@requires_db`/`@requires_redis`/`@requires_deepseek` 门禁、`make_user`/`auth_headers`；鉴权/租户隔离 + stream mock 用例结构照搬。
- [Source: _bmad-output/implementation-artifacts/2-1-LLMProvider抽象-DeepSeek实现-ARQ-SSE异步底座.md#Completion-Notes（L272,280）] — 2.1 流式两 defer 归本切片：「流式 include_usage 真实验证」+ stream 生命周期（Task 4 闭合）；推理档 max_tokens 教训（陷阱⑥）。
- [Source: _bmad-output/implementation-artifacts/deferred-work.md（L81）] — 2.1 defer「OpenAI 流式未 async with/close → 归 Epic 2 探索对话接线切片」（=本 story，Task 4 闭合）。
- [Source: _bmad-output/implementation-artifacts/deferred-work.md（L44-45,56,79）] — 1.7 前端接线独立切片定性（受控决策 A 依据）；1.8/2.1 护栏 TOCTOU defer 至 4.4（本 story 续 defer 依据）。
- [Source: _bmad-output/implementation-artifacts/2-2-探索会话根与模式分叉模式独立.md#Dev-Notes] — 会话根 get-or-create、租户二义合一 404、探索分层范式（interpret 复用）。

## Dev Agent Record

### Agent Model Used

Claude Opus 4.8 (claude-opus-4-8, joybuilder) — bmad-dev-story workflow。

### Debug Log References

- 全量回归：`MUSE_DB_READY=1 MUSE_REDIS_READY=1 uv run pytest` → **157 passed, 2 skipped**（2 skip = 两个 `@requires_deepseek` 真实契约用例，无 key 时 CI 默认 skip）。较 2-2 收尾（144 passed/1 skipped）净增 13 passed + 1 skipped（新增 test_explorer_agent 10 用例 + test_providers stream 生命周期 3 用例 + 1 个新 `@requires_deepseek` stream 契约）。
- `uv run ruff check .` → All checks passed；`uv run mypy` → Success: no issues found in 54 source files。
- `MUSE_DB_READY=1 uv run alembic check` → No new upgrade operations detected（不建表、无 model 漂移，陷阱⑧）。
- 架构红线 grep：`grep -rn "import openai\|from openai" backend/src/muse` 仅 `providers/deepseek.py:17-18` 真实 import 命中（base.py/deepseek.py 另两处为 docstring 文本）。`git status prototype/` 为空、`grep -c "fetch(" prototype/app/app.js` = 0（app.js 一字节未改，受控决策 A）。

### Completion Notes List

**受控决策落地确认**：
- **受控决策 A（后端 only、前端接线 defer）**：`app.js` 零改动，`git status prototype/` 为空、`fetch(` 计数 0。引导页接线（自述提交调 interpret 流、把 done.text 写入 explorationHistory）+ token/fetch/401 基座 **defer 至前端集成切片**——已登记 deferred-work.md，不悬空。
- **受控决策 B（理解自述走 provider.stream 流式 SSE，非 ARQ）**：interpret 端点直连 `provider.stream` 逐块推，`EventSourceResponse` over async gen，不引入 Redis/worker、测试不需 `@requires_redis`（陷阱⑤规避）。仅复用 `core/sse.format_sse_event` 纯 JSON 编码，未碰 `event_stream`/`publish_event`（ARQ 专用）。

**dev 定档点（story 授权 dev 决策）**：
1. **陷阱⑩ session 生命周期——选处置②（独立 session，推荐项）**：`interpret_guided_answer` 内用 `async with async_session_maker() as session:` **自管 session**（仿 ARQ worker 范式）跑租户守卫 + 护栏 + `provider.stream` + 记账，**不依赖 web 请求 session 生命周期**。理由：`MeteredProvider.stream` 的 `finally` 兜底记账（factory.py:133-145）在 SSE 客户端早断（generator `aclose`）时执行；若用请求注入 session，早断时请求作用域可能已 teardown、session 已关，记账抛错/丢账。独立 session 的 `async with` 作用域完整覆盖 generator 存活期，早断兜底记账仍有存活 session——连接释放（Task 4 deepseek `async with`）+ 兜底记账（factory）+ 存活 session 三者配套，早断路径既不漏连接也不漏账。
2. **HTTP 状态 vs SSE error 事件的分界**：`EventSourceResponse` 一旦返回即提交 HTTP 200 头，之后无法改状态码。故新增 `preflight_interpret(session, ...)`——端点在返回 SSE 响应**之前**用请求 session 跑租户守卫 + 护栏，租户 404 / 护栏 429 走**正常 HTTP 状态**（全局 handler 转 envelope）；`interpret_guided_answer`（独立 session）内**再校验一次**守卫，作为直接复用本编排的其它调用方（如 2.6）的防御 + 记账全程落在存活 session 上的保证。正常路径预检已过、独立 session 内守卫必过、皆只读幂等无重复副作用。流已开始后的 provider 异常才走 SSE `error` 事件（泛化文案，原始 exc 只 `logger.exception`）。
3. **命名/落点**：Explorer Agent 编排放 `services/explorer_agent.py`（与 `exploration_service.py` 并列），未并入——探索域 stream 编排与会话 get-or-create 关注点不同，2.6 自由对话可复用同款 stream 范式。
4. **模型档 + max_tokens**：快档 `settings.deepseek_model_fast`（deepseek-v4-flash）+ `max_tokens=1024`（≥512 下限，推理档余量，规避陷阱⑥「reasoning 先吃预算挤空正文」）。
5. **题库归属**：端点收 `question` 文本（前端从 `explorationQuestions[view].question` 传），**后端不镜像题库**——V1 题库是前端定长常量，后端镜像超出本切片（若需集中化归后续切片）。
6. **SSE 事件契约定档**：`delta`（payload `{text: <增量>}`）× N → `done`（payload `{text: <完整凝练答案>}`）→ 失败 `error`（payload `{code, message}`）。camelCase payload（此处键 text 本无下划线）。reasoning 片段（`StreamChunk.kind=="reasoning"`）在 explorer_agent 内**静默丢弃**，不前推（引导理解只需最终答案，不做「思考中」展示）。
7. **入参校验**：`GuidedInterpretRequest` 的 `question`/`free_text` 用 `_NonBlankText`（`StringConstraints(strip_whitespace=True, min_length=1)`）——纯空白 strip 后为空即 422，兑现 AC4「free_text 空/纯空白 → 422」，且送 LLM 的题干/自述已去首尾空白。

**闭合 2.1 流式两 defer（Task 4）**：
- **defer①（流式生命周期硬化）**：`deepseek.py stream()` 改为 `async with await self._client.chat.completions.create(...) as stream:`——早断/异常时 `__aexit__` close 底层 httpx 流、连接归还池。新增两离线用例（`test_stream_closes_underlying_stream_on_full_consume` / `_on_early_break`）断言正常收尾与早断路径 close 均被调。deferred-work.md:81 该条闭合。
- **defer②（流式 include_usage 真实验证）**：新增 `test_real_deepseek_stream_contract`（`@requires_deepseek`）真打 stream，断言末尾 StreamUsage 非空且 `estimated=False`。**注意**：CI 无 key 默认 skip——本机需 `MUSE_DEEPSEEK_READY=1` + 真实 key 跑该用例坐实真实 API 回 usage（本次 dev 环境无 key，该 skip 项待有 key 时执行；离线 mock 两分支已在 2.1 验过）。
- **连带改既有（本 story 唯一「改既有」处）**：`test_providers.py` 两个 stream mock 从纯 async generator（`_aiter`，只有 `aclose`）重构为 `_FakeAsyncStream`（支持 `__aenter__`/`__aexit__`/`__aiter__`/`close`，模拟真实 `AsyncStream`）——否则新 `async with` 写法必 AttributeError 回归红。改后两用例 + 全量回归仍绿。

**续 defer（不在本 story 范围）**：
- **护栏 `check_quota` → 生成 TOCTOU 并发超发**（1.8/2.1 已登记，Jianghj 2026-07-27 裁定）：本 story 是交互式单次流式、**非并发批量生成面**，时间窗风险未现实化，续 defer 至 **Story 4.4**（接入真实生成入口时连同并发控制一起做）。
- **前端引导页接线 + token/fetch/401 基座**：受控决策 A，归前端集成切片（deferred-work.md 已登记）。

### File List

新增：
- `backend/src/muse/services/explorer_agent.py`（Explorer Agent 理解自述编排：`preflight_interpret` + `interpret_guided_answer` + 去 AI 味 system prompt 常量 + 消息组装）
- `backend/tests/test_explorer_agent.py`（编排单元 4 + SSE 端点鉴权/DB 端到端 6 + 复用 test_providers 的真实契约）

修改：
- `backend/src/muse/schemas/exploration.py`（+`GuidedInterpretRequest`、`_NonBlankText`）
- `backend/src/muse/routers/exploration.py`（+`POST /{project_id}/explore/guided/interpret` 流式端点 + `_interpret_event_stream` SSE 编码）
- `backend/src/muse/providers/deepseek.py`（`stream()` 生命周期硬化：`async with` 包裹 AsyncStream，Task 4）
- `backend/tests/test_providers.py`（stream mock 重构为 `_FakeAsyncStream` + 2 个 close 生命周期用例 + 1 个 `@requires_deepseek` stream 契约用例，Task 4）
- `_bmad-output/implementation-artifacts/sprint-status.yaml`（2-3 状态流转 → review）

### Change Log

| 日期 | 变更 | 说明 |
|---|---|---|
| 2026-07-28 | 创建 Story 2.3 | 引导探索真实 Agent 理解自述后端切片：Explorer Agent 编排 + `provider.stream` 流式 SSE 端点 + 护栏/记账接入 + 闭合 2.1 流式 defer；受控决策 A（后端 only、前端接线 defer）+ B（stream 流式非 ARQ）。ready-for-dev |
| 2026-07-28 | 实现 Story 2.3 | 交付 AC4 后端：`services/explorer_agent.py`（preflight 守卫 + interpret 独立 session 流式编排 + 去 AI 味 prompt）、`POST /explore/guided/interpret` 流式 SSE 端点（delta→done→error）、`GuidedInterpretRequest`；闭合 2.1 流式两 defer（deepseek stream `async with` 硬化 + include_usage 真实契约用例）。陷阱⑩定档独立 session。ruff/mypy 绿、157 passed/2 skipped、alembic 无漂移、app.js 零改动。→ review |

## Review Findings

> 代码审查（2026-07-28，三层对抗式：Blind Hunter / Edge Case Hunter / Acceptance Auditor）。
> 归一化去重后 17 条独立发现 → 1 decision-needed / 5 patch / 3 defer / 10 dismissed。
> **已实测证伪 Blind#10**：openai 2.47.0 的 `AsyncStream` 确实实现 `__aenter__/__aexit__/close`，`async with await create(...)` 生产安全，非致命 bug（降级为测试保真度小问题，见 defer）。

### [Decision] 已裁定

- [x] [Review][Decision→Patch] LLM 端点入参缺 `max_length` 上界（成本/DoS 面） — **Jianghj 2026-07-28 裁定：`max_length=2000`（保守上界）**。`question`/`free_text` 均 `_NonBlankText`（只 `min_length=1`、无上界），客户端可送任意长文本直灌 LLM，放大 token 成本、成 DoS 面。已转为下方 patch 执行。来源 blind+edge。[backend/src/muse/schemas/exploration.py:16,31-32]

### [Patch] 可直接修复

- [x] [Review][Patch] 给 `_NonBlankText` 加 `max_length=2000` 上界（裁定值） — 客户端可送任意长文本直灌 LLM，成本/DoS 面。改 `StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)`，超长 → 422。来源 blind+edge（decision 裁定）。[backend/src/muse/schemas/exploration.py:16] — **已修（Jianghj 2026-07-28 全部应用）**：`_NonBlankText` 加 `max_length=2000`；补 `test_interpret_overlong_free_text_422`（2001 字 → 422，挡在建流前）。

- [x] [Review][Patch] 空凝练答案（`done.text=""`）无兜底会污染探索状态 — 流只吐 reasoning、零 content 块时 `done.text` 为空串，前端会把空答案纳入该题。应在收尾判 `if not parts` 走 error 事件（`generate_failed`）而非发空 done。来源 blind+edge。[backend/src/muse/routers/exploration.py:64-66] — **已修**：收尾 `if not answer.strip()` → 发 `generate_failed` error（logger.warning）并 return，不发空 done；补 `test_interpret_empty_output_emits_error_not_done`（零产出 → 仅 error 事件）。
- [x] [Review][Patch] `error` 事件泄 `ErrorEnvelope.code/message` 与 docstring「泛化文案」自相矛盾 — `except ErrorEnvelope` 分支把 `exc.code`/`exc.message` 原样推给客户端，与同文件「错误文案泛化、不外泄」的注释直接打架。应统一泛化（或明确该分支意图并改注释）。来源 blind+auditor。[backend/src/muse/routers/exploration.py:70-73] — **已修（走"明确意图"路线）**：透传 `ErrorEnvelope.{code,message}` 是正确行为（message 是面向用户的三要素、与 HTTP envelope 同源，不含内部细节；code 供前端按 `quota_exceeded` 分支引导），真正该泛化的只有 `except Exception`（原始 exc 不外泄）。重写 docstring 三分类澄清此意图，消除矛盾。
- [x] [Review][Patch] 预期业务错误（429/404）用 `logger.exception` 打 ERROR 级堆栈污染日志 — `except ErrorEnvelope` 里 `logger.exception` 会给正常护栏/租户流打完整 traceback，干扰真实告警。应降 warning/info 且不带 traceback。来源 blind。[backend/src/muse/routers/exploration.py:69] — **已修**：`except ErrorEnvelope` 降为 `logger.warning`（仅记 code、无 traceback）；`except Exception` 保留 `logger.exception`（未预期错误需完整堆栈排查）。
- [x] [Review][Patch] SSE error 路径零测试（假绿）——两条 error 分支从未被触发验证 — 端到端测试把 `interpret_guided_answer` 整个 mock 掉，happy/422/429/404 都不经过流内 `except` 编码路径；error 事件的产出、泛化文案、不外泄若回归，CI 全绿也发现不了。应加「流开始后抛异常 → 断言 error 事件 + 泛化」用例。来源 blind+auditor。[backend/tests/test_explorer_agent.py:276-286] — **已修**：加 `_patch_interpret_raises` helper + 两用例——`test_interpret_unexpected_error_after_stream_emits_generic_error`（RuntimeError → delta 保留 + 泛化 error，断言原始 exc 不外泄）、`test_interpret_business_error_after_stream_passes_envelope`（ErrorEnvelope → 透传 code+用户文案）。
- [x] [Review][Patch] happy 端点测试 `_fake(**kwargs)` 吞掉全部入参，未锁 question/free_text 透传契约 — 假生成器忽略所有参数只吐固定 deltas，端点漏传/传错 `question`/`freeText` 测试照样绿。应断言透传的关键字参数。来源 blind。[backend/tests/test_explorer_agent.py:282-286] — **已修**：`_patch_interpret_stream` 加 `captured` 出参；happy 用例断言 `project_id/user_id/question/free_text` 四字段原样透传。

### [Defer] 既有问题 / 非本次改动引入

- [x] [Review][Defer] `MeteredProvider.stream` 的 `"".join(m.get("content",""))` 在 content 为 None/list 时 TypeError [backend/src/muse/providers/factory.py:116] — deferred，既有代码（2.1 引入），本 story 只搬动 deepseek.py 同款行；内部消息恒为 str，边界已收窄。
- [x] [Review][Defer] 流式无整体超时，上游 stall 时独立 session + httpx 连接可长时间占用 [backend/src/muse/providers/deepseek.py:stream] — deferred，属 provider 层横切超时策略，非本切片单点；与 4.4 生成入口并发/超时控制一并做。
- [x] [Review][Defer] `_FakeAsyncStream.__aiter__` 用 async-gen 实现、偏离真实 AsyncStream 协议（`__aiter__` 应返回 self）；离线三用例全 mock，真实 SDK 的 `async with` 支持仅靠 CI 默认 skip 的 `@requires_deepseek` 覆盖 [backend/tests/test_providers.py:118-140] — deferred，已实测 openai 2.47 支持 `async with`（生产安全），此为测试保真度而非缺陷；有 key 时跑一次真实契约即坐实。
