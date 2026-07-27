---
baseline_commit: 2b580580e8ba530b8a0ec912ae4193a587c8d8d0
---

# Story 2.1: LLMProvider 抽象 + DeepSeek 实现 + ARQ/SSE 异步底座

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a Muse 后端开发者，
I want 一层可换模型的 `LLMProvider`、DeepSeek 默认实现，以及支撑长时生成的 ARQ + SSE 异步底座，
so that 探索及后续所有 LLM 能力都在统一、可计量、不阻塞的运行时上开发（换模型 = 换实现、不改业务层）。

## Acceptance Criteria

1. **Given** 需要模型接入抽象（AR12/焦点一）
   **When** 定义 `LLMProvider` 接口（`chat` / `stream` / `count_tokens`）并落 DeepSeek 实现（OpenAI SDK 兼容、切 `base_url` 指向 `https://api.deepseek.com`；模型名 `deepseek-v4-pro` 思考档 / `deepseek-v4-flash` 快档，128K 上下文）
   **Then** 业务层只依赖 `LLMProvider` 抽象、**禁止直接 import/调用 openai SDK**（换模型 = 换实现不改业务层，Enforcement architecture.md:341/356）；`chat` 返回结构含 `content` + `reasoning`（双档均可能返 `reasoning_content`，见 spike 设计输入）+ `usage`（prompt/completion/total tokens）

2. **Given** 交互式探索对话需低延迟增量返回
   **When** 调用 `LLMProvider.stream`
   **Then** 以异步迭代产出增量文本块（`AsyncIterator`），可被 SSE 端点逐块推送；`reasoning`（思考过程）与 `content`（正文）在流中**可区分**（供前端「思考中」展示或丢弃，spike P1 设计输入），不假设只有 pro 档有 reasoning

3. **Given** 长时生成须异步、不同步阻塞、不前端轮询（NFR2/AR13）
   **When** 提交一个后台任务（本 story 用一个**最小内部示范任务**验证端到端，非真实生成——真实五段流水线在 Epic 4）
   **Then** 走 ARQ（Redis broker）`POST → 返回 taskId` + `GET /api/tasks/{taskId}/events` SSE 推送三事件：`progress`（payload 至少 `{step, percent}`，camelCase）× N → `result`；worker 内异常 → `error`（payload 复用错误 envelope `{code, message}`），失败后不再推 progress/result（architecture.md:335-336，spike P2 已端到端验证含 error 路径）

4. **Given** 客户端 SSE 订阅可能**晚于** worker 首个事件发布，或刷新/断线重连（spike P2 明确留的 Redis Pub/Sub 时序缺口）
   **When** SSE 端点 `GET /api/tasks/{taskId}/events` 建立连接
   **Then** 端点**先补发一次当前任务快照**（已完成的 step / 最新进度，从 Redis 快照键读）**再订阅 Pub/Sub 增量**——保证晚订阅/重连不丢早期进度（本 story 定档方案，见 Dev Notes「SSE 时序缺口定档」）；已终结（result/error）的任务重连能立即拿到终态

5. **Given** 每次 LLM 调用都要计量（AR14/NFR5，**兑现 Story 1.8 跨 epic 依赖**）
   **When** 任一 Provider 调用完成（`chat`/`stream` 结束拿到 usage）
   **Then** 在 **Provider 层**统一调 `usage_service.record_usage(...)` 记 tokens 与成本写 `usage_ledger`——`total_tokens` 用 **API 回报的 `usage.total_tokens`**（非本地预估，spike P1：本地估算偏差 +23.5%）；`billing_path` 依该账户 BYOK 绑定态传 `hosted`/`byok`（托管归 Muse 账、BYOK 归用户账）；`cost` 全程 `Decimal` 不转 float

6. **Given** 用户已绑定 BYOK Key（Story 1.7）
   **When** 该账户/作品发起 LLM 调用
   **Then** Provider 用 `byok_service.get_decrypted_key_for_user(session, user_id)` 取得的用户 Key 构造客户端（DeepSeek/OpenAI 兼容档）；计量记其自有账（`billing_path="byok"`）、**不占托管免费额度**；**生成前**调 `usage_service.check_quota(session, user_id)`——BYOK 放行、托管触顶 429（本 story 把 1.8 的护栏/记账接口首次接进 LLM 调用链路，兑现 1.8 接管清单）

7. **Given** BYOK 绑定的 provider 为 `claude` 或 `custom`（1.7 枚举含三值，但本 story 只实现 DeepSeek 档）
   **When** 该账户发起 LLM 调用
   **Then** Provider 工厂对未实现的 provider 抛**明确的** `ErrorEnvelope("provider_not_supported", ...)`（不静默失败、不误当 DeepSeek 调用）——ClaudeProvider 留到盲测 Story 4.1（Claude-vs-DeepSeek）；custom 的 base_url/model 数据模型补齐设计见 Dev Notes「custom provider 定档」

## Tasks / Subtasks

- [x] **Task 1：Provider 相关配置字段 + `.env.example`（AC1/AC6）**
  - [x] `core/settings.py` 新增（仿 `access_token_ttl_seconds` 的 `Field` 带约束风格，settings.py:47）：
    - `deepseek_api_key: str = ""`（**托管默认路径**用的 Muse 自有 Key；spike `SpikeSettings` 已验证从 `.env` 读取，正式挪进主 `Settings`。空串默认值——本地无 key 时 chat/stream 调用应报明确错误而非静默）
    - `deepseek_base_url: str = "https://api.deepseek.com"`（spike 实测确认，允许 `.env` 覆盖）
    - `deepseek_model_thinking: str = "deepseek-v4-pro"` / `deepseek_model_fast: str = "deepseek-v4-flash"`（**spike `models.list()` 已实测确认两档模型名与架构文档完全吻合**，architecture.md:196；配置化便于模型改名时不改代码）
    - **无 fail-fast**：DeepSeek key 是业务配置非安全密钥（空值只导致调用报错、不导致越权），**别加 model_validator 拒启动**（与 JWT/BYOK 主密钥相反，参照 1.8 `free_quota_tokens` 决策）
  - [x] `.env.example` 增补 `DEEPSEEK_API_KEY=` / `DEEPSEEK_BASE_URL=https://api.deepseek.com`（附注释「托管默认路径 Key」），仿 1.7/1.8 增补方式；`.env` 已有 `DEEPSEEK_API_KEY`（spike 用），确认主 Settings 能读到

- [x] **Task 2：`LLMProvider` 抽象接口（新建 `providers/base.py`，AC1/AC2）**
  - [x] `providers/base.py` 定义抽象基类（`abc.ABC` + `@abstractmethod`）与返回类型（用 `@dataclass` 或 Pydantic，**dataclass 更轻、Provider 内部结构无需 camelCase 边界**）：
    - `class ChatResult`：`content: str`、`reasoning: str`（双档均可能有，默认空串）、`prompt_tokens: int`、`completion_tokens: int`、`total_tokens: int`、`model: str`
    - `class StreamChunk`：`delta: str`、`kind: Literal["content", "reasoning"]`（AC2 区分思考 vs 正文）；流末尾如何回传总 usage 由 dev 定（推荐流结束后 Provider 内部直接记账，见 Task 6）
    - `async def chat(self, messages, *, model=None, max_tokens=None) -> ChatResult`
    - `async def stream(self, messages, *, model=None, max_tokens=None) -> AsyncIterator[StreamChunk]`
    - `def count_tokens(self, text: str) -> int`（AC1；**本地估算仅供调用前粗略提示，不作扣费/触顶准数**——扣费一律用 API 回报 usage，spike P1 定档）
  - [x] **禁止在 base.py import openai**——抽象层与实现层解耦（openai 只在 `providers/deepseek.py` import）

- [x] **Task 3：`DeepSeekProvider` 实现（新建 `providers/deepseek.py`，AC1/AC2/AC5/AC6）**
  - [x] 用 `openai` SDK 的 **async** 客户端（`AsyncOpenAI`，切 `base_url`）——spike 用同步 `OpenAI` 验证联通，正式实现须 async（全栈 async，勿在 async 路径跑同步阻塞调用）：
    - `chat`：`await client.chat.completions.create(..., stream=False)`；从 `resp.choices[0].message` 取 `content` + `getattr(msg, "reasoning_content", "")`（spike 已验证双档均有该字段）；从 `resp.usage` 取三分量 tokens
    - `stream`：`stream=True` 异步迭代 `resp`，逐 chunk 产出 `StreamChunk`——delta 分辨 `choices[0].delta.content` vs `.reasoning_content`（`kind` 标注）；流式 usage 通常在末 chunk（`stream_options={"include_usage": True}`，dev 验证 DeepSeek 是否支持，否则流末用 `count_tokens` 兜底估算并**在 Completion Notes 记明**该口径）
  - [x] `count_tokens`：spike 的「CJK×0.6+其余×0.3」本地估算可作 V1 实现（无官方离线 tokenizer），**注释标明是粗估、偏差约 +23.5%、不作扣费准据**（spike P1）
  - [x] **构造参数注入 key**：`__init__(self, api_key: str, base_url: str, ...)`——托管路径传 `settings.deepseek_api_key`，BYOK 路径传 `byok_service.get_decrypted_key_for_user(...)` 的明文（AC6）。**明文 key 只在内存传入、绝不 log/落库/出边界**（延续 1.7 安全红线）

- [x] **Task 4：Provider 工厂 + 用量记账/护栏包裹（新建 `providers/factory.py` 或 `providers/__init__.py`，AC5/AC6/AC7）**
  - [x] `get_provider_for_user(session, user_id) -> LLMProvider`：**决定走 BYOK 还是托管**——
    - 调 `byok_service.get_binding_status(session, user_id)` 判是否绑定（存在性查询、不解密，参照 usage_service `_is_byok_user` 范式，避免无谓解密 + KeyDecryptError 风险）
    - 已绑定：按 `byok.provider` 分派——`deepseek` → 用 `get_decrypted_key_for_user` 取明文构造 `DeepSeekProvider`，`billing_path="byok"`；`claude`/`custom` → 抛 `ErrorEnvelope("provider_not_supported", "该模型提供方尚未支持，敬请期待。", http_status=400)`（AC7，不静默失败）
    - 未绑定：托管 `DeepSeekProvider(settings.deepseek_api_key)`，`billing_path="hosted"`
  - [x] **记账埋点统一在 Provider 层**（AR14/Enforcement architecture.md:356）：Provider 的 `chat`/`stream` 完成拿到 usage 后 → 调 `usage_service.record_usage(session, user_id=..., billing_path=..., prompt_tokens=..., completion_tokens=..., total_tokens=<API usage>, cost=<Decimal 按模型单价算>, project_id=?, model_name=...)`。**cost 全程 Decimal 不转 float**（陷阱：钱不用浮点，1.8 陷阱②）。单价常量放 settings 或 provider 模块常量（DeepSeek 官方定价，dev 填当前值 + 注释来源/日期，便于调价）
  - [x] **生成前护栏**（AC6）：真实生成入口（Epic 2 探索整理 / Epic 4 章节生成）调用 provider 前先 `await usage_service.check_quota(session, user_id)`——触顶抛 429 不进生成。**本 story 无真实生成入口**，但须在**示范任务或一条集成测试**里演示「check_quota → 调 provider → record_usage」的完整串联，证明 1.8 接口可用（兑现 1.8 接管清单）
  - [x] **记账的事务/session 归属**（dev 决策点，记 Completion Notes）：Provider 在 ARQ worker 内调用时用 worker 自己的 async session；`record_usage` 内部 commit（1.8 已实现）。注意 worker session 与 web 请求 session 是不同生命周期，别跨用

- [x] **Task 5：`core/sse.py` SSE 事件封装（填实占位，AC3/AC4）**
  - [x] 现 `core/sse.py` 是空占位（1.1 建目录约定）。填实：
    - 三事件常量 `progress`/`result`/`error`；`format_sse_event(event, data: dict)` 把 camelCase payload 编码为 `sse-starlette` 的 `{event, data}` 结构（data 用 `json.dumps`）
    - Redis 频道命名 `task:{task_id}:events`（spike 已验证）+ **快照键** `task:{task_id}:snapshot`（本 story 新增，见 Task 7 AC4）
    - `publish_event(redis, task_id, event, data)`：`SET` 更新快照键（progress 覆盖最新、result/error 置终态）+ `PUBLISH` 增量（spike 只 publish，本 story 加快照写）
    - `event_stream(task_id)` 异步生成器：**先读快照键补发一次**（若存在），**再 subscribe** Pub/Sub 增量；收到 result/error 即结束流（AC4 时序缺口定档方案）

- [x] **Task 6：ARQ worker + 最小示范任务（新建 `tasks/worker.py` + `tasks/__init__.py` 填实，AC3）**
  - [x] `tasks/worker.py`：`WorkerSettings`（`functions`、`redis_settings = RedisSettings.from_dsn(settings.redis_url)`、`on_startup`/`on_shutdown` 建/释放 async DB engine 与 Redis 连接）——正式化 spike 的 `WorkerSettings`（spike 是 spike 内联类）
  - [x] **最小内部示范任务** `demo_generate(ctx, task_id)`（**明确标注是底座验证任务、非真实生成**，真实五段流水线 Epic 4）：分几 step、每 step `publish_event(progress)`、末 `result`；异常 `try/except` publish `error`（复用错误 envelope）。**可选**：让其中一 step 真调一次 `DeepSeekProvider.chat`（托管路径）串起「provider→record_usage」，若无 DEEPSEEK_API_KEY 则跳过真实调用只走 mock（保证 CI 无 key 也能跑）
  - [x] Provider 在 worker 内被调用：worker `on_startup` 备好 async session maker，任务内开 session 调 provider + 记账
  - [x] `Makefile`/README 补 worker 启动命令（`uv run arq muse.tasks.worker.WorkerSettings`），与 `make dev-up`（起 Redis）配套，记 Dev Notes

- [x] **Task 7：任务提交 + SSE router（新建 `routers/tasks.py` + main 注册，AC3/AC4）**
  - [x] `routers/tasks.py`（`prefix="/api/tasks"`, `tags=["tasks"]`），依赖 `CurrentUser` 鉴权：
    - `POST /api/tasks/demo`（→ `{taskId}`）：`create_pool` 入队 `demo_generate`，`_job_id=task_id`（stable id 作 pubsub 频道键，spike 范式）；返回 `TaskSubmitResponse(task_id=...)`（CamelModel，边界 `taskId`）。**本 story 只暴露示范提交端点**，真实生成端点（`POST /api/projects/{id}/chapters/{n}/generate` 等）在 Epic 2/4
    - `GET /api/tasks/{task_id}/events`（SSE）：`EventSourceResponse(event_stream(task_id))`（Task 5）。**鉴权 + 归属校验**：SSE 端点也须 `CurrentUser`，且校验该 task 属当前用户（防越权订阅他人任务进度——dev 决策校验方式：快照/任务元数据存 user_id，或 taskId 不可枚举 + 记 defer，见陷阱⑤）
  - [x] `main.py` `create_app()` 内 `app.include_router(tasks.router)`（与 auth/health/projects/byok/usage 并列，main.py:11 import 补 `tasks`、main.py:29 后补 include）
  - [x] **ARQ 连接池生命周期**：POST 每次 `create_pool` + `aclose`（spike 范式，简单）或应用级复用池（dev 定，注意 lifespan 清理，参照 db engine dispose main.py:18）

- [x] **Task 8：测试（新建 `tests/test_providers.py` + `tests/test_tasks_sse.py`，全 AC 覆盖）**
  - [x] **Provider 单元（离线，mock openai，不打真实 API）**：
    - `chat` 返回结构：mock `AsyncOpenAI` 的 response，断言 `ChatResult` 正确解析 content/reasoning/usage（含 reasoning_content 存在与缺失两种）
    - `stream` 增量：mock 流式 chunk，断言 `StreamChunk` 的 `kind` 正确区分 content/reasoning
    - `count_tokens` 本地估算：纯函数，断言 CJK/非 CJK 系数（**测试注释标明这是粗估非扣费准据**，别把它当精确 token 数固化）
    - 工厂分派：mock byok_service → 托管走 hosted、BYOK deepseek 走 byok、claude/custom 抛 `provider_not_supported`（AC7）
    - **记账串联**：mock provider usage → 断言 `record_usage` 被以 API usage 的 total_tokens、正确 billing_path、Decimal cost 调用（AC5）
  - [x] **可选真实契约测试** `@requires_deepseek`（仿 `@requires_db`，门禁 env `MUSE_DEEPSEEK_READY=1` + 有 key 才跑）：真打一次 DeepSeek chat，断言联通 + usage 非空。**CI 默认 skip**（无 key），本地可跑；参照 spike 但收进正式测试。**若不加此门禁则在 Completion Notes 说明**联通验证仅靠 spike 脚本
  - [x] **SSE + ARQ 端到端**（`@requires_db` 或新 `@requires_redis`，需 Redis）：
    - happy path：POST 提交 → 连 SSE → 收 progress×N + result（照 spike `_submit_and_collect` 结构，收进 pytest）
    - error path：示范任务 fail 分支 → progress + error（payload 含 code/message）
    - **AC4 时序**：先让任务发几个 progress 落快照键，**再**建 SSE 连接 → 断言补发了快照（晚订阅不丢早期进度）；终态任务重连拿到 result/error
  - [x] **conftest 增量**：SSE/ARQ 用例需 Redis——评估复用 `_sync_redis` 或加 `@requires_redis` 门禁（现 `_clean_tables` 已访问 Redis，参照）；若示范任务真调 provider，mock 或门禁 key。**新 provider/tasks 配置有安全默认**（deepseek_api_key 空串），conftest 顶部**无需**注入新 env（不像 BYOK_MASTER_KEY）

- [x] **Task 9：质量门禁 + 验证（ready → done 前必过）**
  - [x] `uv run ruff check .` + `uv run mypy`（新增 `providers/*`/`tasks/*`/`routers/tasks.py`/`core/sse.py` 类型标注完整；`AsyncIterator`/`AsyncOpenAI`/`Decimal` 类型正确；**业务层无直接 import openai**——grep 校验只有 `providers/deepseek.py` import）
  - [x] `MUSE_DB_READY=1 uv run pytest`（+ Redis 起）全绿；离线 provider 单元不设 DB/Redis 也过；**全量回归无既有用例回归**（1.8 收尾时全量约 107 用例，本 story 只增不改既有）
  - [x] **迁移**：本 story **不建新表**（复用 `usage_ledger`；exploration 表在 2.2+）——确认 `alembic upgrade head` 无新 revision、`alembic check` 无未捕获的 model 漂移（Provider/tasks 不含 ORM 模型）
  - [x] **`prototype/app/app.js` 一字节不改**（`git status prototype/` 应为空，`grep -c "fetch(" prototype/app/app.js` 仍为 0）——本 story 零前端接线（后端底座 story，SSE 前端消费在探索/章节接线切片）
  - [x] 全链路人工核对：worker 起得来、POST demo 提交返 taskId、SSE 三事件到达、（有 key 时）真实 chat 记账落 `usage_ledger`（直查 DB 见 hosted 行、total_tokens = API usage、cost Decimal）

## Dev Notes

### 🔑 本 story 的性质：Epic 2 底座 story（第一个真正调用 LLM 的地方），`app.js` 零改动
2.1 是 **Epic 2 首个 story**，也是**实施顺序第 3 步「LLMProvider + ARQ 底座」**（AR20，architecture.md:261），卡在「存储层」之后、「盲测门禁 4.1」之前。它不做任何面向用户的探索/生成功能（那是 2.2+/Epic 4），只交付**运行时底座**：可换模型的 Provider 抽象 + DeepSeek 实现 + ARQ 异步任务 + SSE 回传 + 用量记账/护栏的**首次真实接入**。与 1.7/1.8 同款——后端做实、`app.js` 零改动，SSE 的前端消费留给探索/章节接线切片。

**范围边界（本 story 做 / 不做）**：
| 做 | 不做（越界 / 属别的 story） |
|---|---|
| `LLMProvider` 抽象 + `DeepSeekProvider`（chat/stream/count_tokens，Task 2/3） | ClaudeProvider（盲测 Story 4.1，AC7 先返 `provider_not_supported`） |
| ARQ worker + SSE 三事件 + 最小**示范**任务（Task 5/6/7） | 真实五段流水线 context→drafter→reviewer→polisher→data-agent（Epic 4，AR11） |
| Provider 层记账埋点 + 生成前 check_quota 接入（Task 4，兑现 1.8） | 真实生成入口（探索整理 2.5/2.7、章节生成 4.4）——本 story 只用示范任务演示串联 |
| BYOK/托管 Key 分派（Task 4，接 1.7 `get_decrypted_key_for_user`） | custom provider 的 base_url/model 表结构补齐（见「custom provider 定档」——本 story 只在抽象层预留，不改表/schema） |
| SSE 时序缺口的快照补发方案（Task 5，AC4） | exploration_session/message/story_clue 建表（2.2/2.4/2.6 按需建表） |
| `providers/*`/`tasks/*`/`routers/tasks.py`/`core/sse.py` 填实 + 测试 | 前端 SSE 消费 / EventSource 接线（探索/章节接线切片） |

### 🔑 兑现 Story 1.8 跨 epic 依赖：本 story 把记账 + 护栏首次接进 LLM 调用链路（最重要的交接闭合点）
1.8 交付了三个**空转的接口**（表 + `record_usage` + `check_quota`），当时**无任何调用方**（1.8 Completion Notes「Epic 2 接管清单」、deferred-work.md:55-56）。**本 story 是它们的第一个真实消费方**，必须闭合 1.8 登记的接管清单：
1. **记账埋点**（AC5）：`DeepSeekProvider` 每次 `chat`/`stream` 完成 → 调 `usage_service.record_usage(...)`。`billing_path` 依 BYOK 绑定态传 `hosted`/`byok`（判据 `byok_service.get_binding_status`）；`total_tokens` 用 **API 回报的 `usage.total_tokens`**（**不是本地 count_tokens 预估**——spike P1 实测本地估算偏差 +23.5%，只可作调用前粗略拦截，不可作扣费/触顶准数）；`cost` 按 DeepSeek 模型单价算、**全程 Decimal**。
2. **护栏接入**（AC6）：生成入口调 provider 前先 `check_quota` → 触顶抛 429 不进生成。本 story 无真实生成入口，但**示范任务或集成测试须演示完整串联**「check_quota → provider.chat → record_usage」，证明 1.8 接口可用（否则 1.8 的接口到 Epic 4 才第一次被验证，风险后移）。
3. **1.8 defer 的并发护栏（check_quota TOCTOU）**：1.8 Review 明确「Jianghj 2026-07-27 裁定 defer，Epic 2 Story 2.1 接入生成链路时连同并发控制一起做」（deferred-work.md:56）。**本 story 是那个「接入生成链路」的时点**——dev 须评估：示范任务/未来生成入口的并发面下，`check_quota`「读累计→判定→调用后才 record」的时间窗是否需要现在加原子递增/`SELECT FOR UPDATE`/预留额度。**若本 story 仍无真实并发生成面（只有示范任务），可继续 defer 但须在 Completion Notes 重新登记「真实生成入口落地时（4.4）必须做」**，不要让这条 defer 悬空丢失。

### 🔑 三项定档决策（用户 2026-07-27 授权 dev 定档，此处记录 —— 对齐 1.8「计量口径 dev 定档」写法）
开工前就三个范围分叉征询过用户，用户授权按最佳方案定档，均有权威依据：

**① SSE 时序缺口 → 快照键补发 + Pub/Sub 增量（AC4/Task 5）**
- **背景**：spike P2 明确留缺口（deferred-work.md:72）——Redis Pub/Sub 不留历史，客户端订阅晚于首个 progress、或刷新/断线重连会丢早期进度。spike 因 worker 有 0.3s/step 延迟天然错开未暴露。
- **定档方案**：SSE 端点**先读 Redis 快照键（`task:{id}:snapshot`）补发一次当前 step，再 subscribe 增量**。`publish_event` 每次同时 `SET` 快照 + `PUBLISH` 增量。终态（result/error）也写快照，重连能立即拿终态。
- **为何不用 Redis Stream**：Stream 可回放+消费位点更稳健，但引入消费组/裁剪复杂度，2.1 是底座 story、宜轻。快照方案覆盖「晚订阅/单次重连」这个 V1 实际场景（单用户看自己任务），足够；若未来需「多消费者+精确断点续读」再升级 Stream（平滑超集）。**dev 若实现中发现快照方案对多 step 细粒度进度不足，可在 Completion Notes 提议 V2 转 Stream。**

**② Provider 实现范围 → 只做 DeepSeek，claude/custom 返 `provider_not_supported`（AC7/Task 4）**
- **依据**：epics 2.1 标题即「DeepSeek 实现」、AR12「DeepSeek 为默认实现」；盲测 4.1 才是 Claude-vs-DeepSeek（AR19），此刻做 ClaudeProvider 既超范围、又与盲测时点错配。
- **定档**：Provider 工厂对 `claude`/`custom` 抛明确 `ErrorEnvelope("provider_not_supported")`（**不静默失败**，延续项目「不静默」红线）。ClaudeProvider 留 4.1。**注意**：1.7 的 BYOK 枚举已允许用户绑 claude/custom（能存），本 story 让「绑了但用」时返明确错误——这是诚实的占位，不是 bug。

**③ custom provider 补齐程度 → 仅 Provider 抽象层预留，不改表/schema（Task 4）**
- **背景**：1.7 明确把「custom 缺 base_url/model_name（+ API 兼容风格）」归到 2.1（deferred-work.md:46）——光一把 Key 无法调用未预置模型。
- **定档**：本 story **只在 `LLMProvider` 抽象设计里预留「配置来源」的形状**（Provider 构造接受 base_url/model 参数，DeepSeek 从 settings 填），**不改 `byok_key` 表、不改 `ByokBindRequest`、不碰 app.js custom 输入框**。
- **理由**：custom 本 story **无真实用例**（只做 DeepSeek），现在给表加 base_url/model 列是无 AC 验证的超前建模（违反 YAGNI，参照 1.8「不建 usage_summary」）。但抽象层预留形状可消解 1.7 担心的「Provider 建完发现数据模型不够、二次返工」——**Provider 契约已含这些参数，未来 custom 真正启用时只需补表列 + schema 字段 + 原型输入框，Provider 层零改动**。**在 Completion Notes 明确登记「custom 真正可用仍需补 byok_key.base_url/model_name 列 + ByokBindRequest 字段 + app.js 输入框，归 custom 启用切片」**，不让 1.7 这条留茬悬空。

### spike 设计输入（P1/P2 已实测，直接采用，勿重复退风险）
> 两个 spike 是本 story 的**正向设计输入**（deferred-work.md:58-72），非留茬。可复跑凭证：`backend/scripts/spike_deepseek.py`（P1）、`backend/scripts/spike_arq_sse.py`（P2）。**spike 脚本刻意不碰 `src/muse` 主代码**——正式实现在本 story 从零写进 `providers/`/`tasks/`/`core/sse.py`，但可照搬 spike 已验证的结构与结论。

- **双档模型名已实测确认** [spike P1]：`models.list()` 探得账号可用恰为 `deepseek-v4-pro`（思考，起草/审查）+ `deepseek-v4-flash`（快，提取/轻任务），与 architecture.md:196 完全吻合。实测 flash（~2.9s）延迟约 pro（~5.6s）一半、token 用量相当。**直接按这两名写，无需再探。**
- **护栏计量必须信 API `usage.total_tokens`** [spike P1]：本地「CJK×0.6+其余×0.3」估算同一 prompt 得 13 tokens，API 实际 17，**偏差 +23.5%（低估）**。印证 1.8 以 `SUM(total_tokens)` 为触顶源正确。**记账落库用 API usage，本地 count_tokens 只作调用前粗略提示**（Task 3/AC5）。
- **双档均返 `reasoning_content`（含 flash）** [spike P1]：flash 快档也带思考字段（非仅 pro）。`ChatResult`/`StreamChunk` 两档都要处理 reasoning、不能假设只有 pro 有；SSE stream 须区分 reasoning vs content（AC2）。
- **ARQ + sse-starlette + Redis Pub/Sub 已端到端跑通** [spike P2]：`arq==0.25.0` + `sse-starlette==3.4.6`（已入 pyproject.toml/uv.lock）+ Redis Pub/Sub 推模型。两轮（happy + error）全绿。**`tasks/worker.py`/`core/sse.py`/`routers/tasks.py` 照此骨架**，但正式化（async 客户端、WorkerSettings on_startup/shutdown、SSE 快照补发）。
- **三事件契约含 error 路径已验证** [spike P2]：`progress{step,percent}` camelCase × N → `result`；worker 异常经 try/except 推 `error{code,message}`，失败后无 progress/result。**error 是长时任务最需保证的路径**——五段流水线每 step 失败都走此 error 事件（本 story 示范任务须覆盖 fail 分支）。

### 关键实现陷阱（务必规避）
- **陷阱①：业务层禁止直接 import/调用 openai SDK（架构最硬红线）。** Enforcement architecture.md:341/356「一律走 `LLMProvider` 接口」「code review 卡 Provider 直调」。openai 只允许出现在 `providers/deepseek.py`。Task 9 用 grep 校验。换模型 = 换 Provider 实现，业务层零改动——这是整个焦点一的立身之本。
- **陷阱②：cost 全程 Decimal，绝不转 float（1.8 陷阱②同源）。** 成本是钱，浮点累加漂移。Provider 算 cost（tokens × 单价）用 `Decimal`，传给 `record_usage` 的 `cost` 是 `Decimal`，落库 `Numeric(12,6)`（1.8 已建）。单价常量也用 `Decimal("0.xxx")` 字面量，别 `float * int`。
- **陷阱③：BYOK 判定用 `get_binding_status`（存在性）而非 `get_decrypted_key_for_user`（解密）——除非真要调用。** 判「走 BYOK 还是托管」只需布尔存在性，用 `get_binding_status`（不解密、无 `KeyDecryptError` 风险，参照 usage_service `_is_byok_user` 的教训，1.8 Review patch1+2）。**只有确定走 BYOK deepseek、真要构造客户端时**才调 `get_decrypted_key_for_user` 取明文。取到的明文**绝不 log/落库/出边界**（1.7 安全红线）。
- **陷阱④：async 到底，别在 async 路径混同步阻塞调用。** 全栈 async（FastAPI + SQLAlchemy async + ARQ async）。Provider 用 `AsyncOpenAI` 不是 `OpenAI`（spike 用同步仅为快速验证）。worker 内 DB 用 async session。同步阻塞（如同步 openai 调用、`time.sleep`）会卡事件循环拖垮并发。
- **陷阱⑤：SSE 端点须鉴权 + 任务归属校验，别让人订阅他人任务进度。** `GET /api/tasks/{taskId}/events` 也要 `CurrentUser`；且校验 taskId 属当前用户（否则枚举 taskId 可偷看他人生成进度/内容——IDOR 面）。dev 定校验方式：任务元数据/快照存 user_id 比对，或（弱方案）taskId 用不可枚举 uuid + 记 defer。**选定即记 Completion Notes**，别裸奔。
- **陷阱⑥：Redis Pub/Sub「先订阅后发布」时序（本 story 定档要解，AC4）。** 见「定档①」。**别照搬 spike 的纯 Pub/Sub**（spike 自己标了这是留给正式设计的缺口）——必须加快照补发，否则刷新页面/断线就丢进度。
- **陷阱⑦：worker 与 web 请求的 session/连接生命周期不同，别跨用。** ARQ worker 是独立进程/事件循环，须自己的 async engine（`WorkerSettings.on_startup` 建、`on_shutdown` dispose）。别把 web 请求的 session 传进 worker 任务，别复用 `core/db.py` 的请求级 `get_session`（那是 FastAPI 依赖）。
- **陷阱⑧：本 story 不建表——别手痒建 exploration_session。** 迁移 head 停在 `8cafe7161b60`（usage_ledger）。Provider/tasks/sse 都不含 ORM 模型。exploration 表是 2.2/2.4/2.6「按需建表」（epics.md:455）。Task 9 确认 `alembic check` 无漂移。

### 强制复用 / 对齐的既有事实（照现状，勿另起炉灶）
- **providers/ 落点已在架构预留**：architecture.md:319「`providers/` LLMProvider/EmbeddingProvider 抽象与实现」、:261「LLM Provider 抽象 + ARQ 任务框架（焦点一底座）」。就建 `providers/base.py` + `providers/deepseek.py` + 工厂，勿塞进 services。
- **tasks/ + core/sse.py 落点已预留**：architecture.md:320「core/ … SSE」、AR13「ARQ」。`core/sse.py` 现为空占位（1.1 建，注释明写「实际实现：Epic 2 LLM/编排底座」）；`tasks/__init__.py` 空占位。填实即可。
- **usage_service 记账/护栏接口（1.8 交付）**：`record_usage(session, *, user_id, billing_path, prompt_tokens, completion_tokens, total_tokens, cost, project_id=None, model_name=None)`（usage_service.py:109，内部 commit）、`check_quota(session, user_id)`（usage_service.py:45，BYOK 短路 + 托管触顶 429）。**Provider 层直接调这两个，别重写记账/护栏逻辑。**
- **byok_service 取 Key 接口（1.7 交付）**：`get_binding_status(session, user_id)`（byok_service.py:119，存在性/不解密）判是否 BYOK；`get_decrypted_key_for_user(session, user_id)`（byok_service.py:137，返明文或 None，解密失败抛 `KeyDecryptError`）取明文构造客户端。
- **ErrorEnvelope + 全局 handler**：`core/errors.py:17` `ErrorEnvelope(code, message, detail, http_status)`——`provider_not_supported`（AC7）、`quota_exceeded`（护栏，1.8 已抛）都走它。全局 handler 自动转 `{code,message,detail}`。
- **CurrentUser + SessionDep 鉴权/会话依赖**：`core/deps.py:24/55`——`routers/tasks.py` 端点参数标注即自动 access token 校验 + 注入 async session（参照 routers/byok.py、routers/usage.py）。
- **CamelModel 边界基类**：`schemas/base.py:29` `CamelModel`（`alias_generator=to_camel`）——`TaskSubmitResponse` 的 `task_id` 自动出 `taskId`。SSE payload 手工保证 camelCase（`{step, percent}`，Communication Patterns architecture.md:336）。
- **settings 可配置字段范式**：`core/settings.py:47` `Field(default=..., gt=0)`——deepseek 配置照此，**无 fail-fast**（业务配置非安全密钥，参照 1.8 `free_quota_tokens` settings.py:62）。
- **main.py router 注册**：`main.py:11` import 补 `tasks`、`create_app()`（main.py:29 后）`app.include_router(tasks.router)`，与 auth/health/projects/byok/usage 并列。
- **依赖已就位**：`arq>=0.25.0`、`sse-starlette>=3.4.6`、`openai`、`redis>=8.0.1` 均在 pyproject.toml（P2 spike 已入 arq/sse-starlette 到 uv.lock）。**无新依赖**。
- **conftest 测试基建**：`load_all_models()` 自动发现模型（本 story 无新模型，无需改）；`@requires_db`（conftest.py:36）、`make_user`/`auth_headers` fixture 复用；新增 `@requires_deepseek`/`@requires_redis` 门禁仿 `@requires_db` 写法（conftest.py:36-38）。

### Project Structure Notes
- **新增文件**：`providers/base.py`、`providers/deepseek.py`、`providers/factory.py`（或工厂放 `providers/__init__.py`）、`tasks/worker.py`、`routers/tasks.py`、`schemas/task.py`（`TaskSubmitResponse`，或复用 account.py）、`tests/test_providers.py`、`tests/test_tasks_sse.py`。
- **填实占位**：`core/sse.py`（空→SSE 封装 + 快照补发）、`tasks/__init__.py`（空→可留空或放示范任务）。
- **扩展文件**：`core/settings.py`（+deepseek_* 字段）、`main.py`（+include_router tasks）、`.env.example`（+DEEPSEEK_*）、可能 `Makefile`/README（+worker 启动命令）、`tests/conftest.py`（+`@requires_deepseek`/`@requires_redis` 门禁，若需）。
- **不建迁移**：本 story 无新 ORM 模型（复用 usage_ledger）；迁移 head 保持 `8cafe7161b60`。
- **依赖零新增**：arq/sse-starlette/openai/redis 均已就位。
- **无偏差**：严格遵循 architecture.md 分层（routers→services→providers；worker 独立域）、camelCase 边界、Provider 唯一 LLM 出口、用量记账在 Provider 层、租户守卫。

### 测试形态
- 后端 pytest + pytest-asyncio（`asyncio_mode=auto`）。**Provider 单元离线**（mock `AsyncOpenAI`，不打真实 API，CI 必过）。
- **真实 DeepSeek 契约**：`@requires_deepseek`（`MUSE_DEEPSEEK_READY=1` + key），CI 默认 skip、本地可跑（仿 `@requires_db` 门禁）。
- **SSE + ARQ 端到端**：需 Redis（`make dev-up`），照 spike `_submit_and_collect` 结构收进 pytest；覆盖 happy + error + AC4 时序（快照补发）。
- DB 用例 `@requires_db`（记账落库直查 usage_ledger），复用 conftest `make_user`/`auth_headers`。

### 待澄清（保存至末尾，请用户确认）
- **无阻塞性疑问。** 三项范围分叉（SSE 时序方案、Provider 只做 DeepSeek、custom 补齐程度）已于 2026-07-27 征询，用户授权 dev 定档，本 story 已按最佳方案定档并记录依据（见「三项定档决策」）。
- **供用户知悉的受控决策**（非阻塞，dev 照此执行）：
  1. **SSE 时序缺口**定档为「Redis 快照键补发 + Pub/Sub 增量」（非 Redis Stream）——覆盖 V1「晚订阅/单次重连」场景，未来需多消费者精确断点再升 Stream。
  2. **Provider 只实现 DeepSeek**——claude/custom BYOK 返 `provider_not_supported`（不静默）；ClaudeProvider 归盲测 Story 4.1。
  3. **custom provider 仅在抽象层预留 base_url/model 参数形状**，不改 byok_key 表/ByokBindRequest/app.js——custom 真正启用仍需补表列+schema+原型输入框（归 custom 启用切片，1.7 deferred-work.md:46 这条留茬本 story 不完全闭合、只降风险）。
  4. **1.8 的 check_quota TOCTOU 并发 defer**：本 story 若仍无真实并发生成面（只有示范任务），可继续 defer，但须在 Completion Notes 重新登记「真实生成入口（4.4）落地时必须做并发控制」，不让 defer 悬空。
  5. **本 story 护栏/记账首次接入 LLM 链路但仍非「面向用户的生成」**——真实探索整理（2.5/2.7）、章节生成（4.4）才是护栏真正拦用户的地方；本 story 用示范任务证明接口串联可用。

### References
- [Source: _bmad-output/planning-artifacts/epics.md#Story-2.1（L459-485）] — 用户故事、5 条 GWT AC（Provider 抽象+DeepSeek、stream SSE、ARQ 异步、Provider 层记账、BYOK 记自有账）。
- [Source: _bmad-output/planning-artifacts/epics.md#Epic-2（L450-457）] — Epic 2 概述：本 epic 顺带落地 LLMProvider + ARQ 底座（第一个真正调 LLM 处）；「异步模型：交互对话走 stream SSE、整理走 ARQ 后台任务」；Story 依赖 2.1→2.2；按需建表（2.2 exploration_session 起，本 story 不建表）。
- [Source: _bmad-output/planning-artifacts/architecture.md#焦点一（L185-201）] — 编排五段流水线（Epic 4）、LLMProvider 抽象（chat/stream/count_tokens）、DeepSeek 默认实现切 base_url、双档模型名、ARQ 任务队列、用量计量在 Provider 层、换模型后门。
- [Source: _bmad-output/planning-artifacts/architecture.md#Implementation-Sequence（L258-267）] — 实施顺序第 3 步「LLM Provider + ARQ 任务框架（焦点一底座）」，卡在存储层之后、盲测门禁 4.1 之前。
- [Source: _bmad-output/planning-artifacts/architecture.md#API通信模式（L172-176,301,334-336）] — REST+SSE、长时生成 POST→taskId + GET /events；SSE 三事件 progress/result/error、payload camelCase、progress 至少 {step,percent}、error 复用错误 envelope。
- [Source: _bmad-output/planning-artifacts/architecture.md#Process-Patterns+Enforcement（L340-361）] — LLM 调用一律走 Provider 接口、业务层禁直调 openai；tokens/成本埋点在 Provider 层；长时生成禁轮询/同步阻塞；code review 卡 Provider 直调（陷阱①依据）。
- [Source: _bmad-output/implementation-artifacts/deferred-work.md（L44-46）] — 1.7 留茬：`get_decrypted_key_for_user` 供本 story 消费（AC6）；custom provider 缺 base_url/model_name 归本 story（定档③）。
- [Source: _bmad-output/implementation-artifacts/deferred-work.md（L55-56）] — 1.8 留茬归本 story：record_usage 输入契约（tokens≥0/billing_path 白名单/复合索引）、check_quota TOCTOU 并发（接入生成链路时做，定档④）。
- [Source: _bmad-output/implementation-artifacts/deferred-work.md（L58-72）] — **P1/P2 spike 设计输入**：双档模型名实测、护栏信 API usage 非本地估算、双档均返 reasoning_content、ARQ+sse-starlette+Pub/Sub 跑通、三事件含 error 路径、Pub/Sub 时序缺口（定档①依据）。
- [Source: backend/scripts/spike_deepseek.py] — P1 联调 spike：OpenAI SDK 切 base_url、双档 chat、count_tokens 本地估算 vs API usage 偏差、reasoning_content 探测（可复跑凭证，正式实现照此结论但从零写进 providers/）。
- [Source: backend/scripts/spike_arq_sse.py] — P2 骨架 spike：ARQ WorkerSettings、Redis Pub/Sub 频道 `task:{id}:events`、SSE EventSourceResponse、三事件 happy+error 端到端断言（tasks/worker.py、core/sse.py、routers/tasks.py 照此骨架 + 加快照补发）。
- [Source: backend/src/muse/services/usage_service.py（L45-72,109-140）] — `check_quota`（BYOK 短路+托管触顶 429，AC6）、`record_usage`（记账写入编排，内部 commit，AC5）——Provider 层直接调用，勿重写。
- [Source: backend/src/muse/services/byok_service.py（L119-124,137-150）] — `get_binding_status`（存在性判 BYOK，陷阱③）、`get_decrypted_key_for_user`（取明文构造客户端、失败抛 KeyDecryptError，AC6）。
- [Source: backend/src/muse/core/security.py（L141-198）] — `KeyDecryptError`、`decrypt_api_key`（BYOK 明文只在内存、篡改/轮转抛异常不返空串，陷阱③）。
- [Source: backend/src/muse/core/errors.py（L17-46）] — `ErrorEnvelope(code,message,detail,http_status)` + 全局 handler（provider_not_supported/quota_exceeded 走它，AC7）。
- [Source: backend/src/muse/core/sse.py] — 空占位（1.1 建目录约定，注释明写「实际实现：Epic 2 SSE 异步回传」）——本 story 填实（Task 5）。
- [Source: backend/src/muse/tasks/__init__.py] — 空占位——本 story 建 worker.py（Task 6）。
- [Source: backend/src/muse/providers/__init__.py] — 空占位（1.7 deferred-work.md:44「providers/ 当前仅空 __init__.py」）——本 story 建 base.py/deepseek.py/工厂（Task 2/3/4）。
- [Source: backend/src/muse/core/settings.py（L44-62,111-113）] — 可配置字段带约束范式（deepseek_* 照此，无 fail-fast）；`get_settings` lru_cache。
- [Source: backend/src/muse/core/deps.py（L24,38-56）] — `SessionDep`/`get_current_user`/`CurrentUser`（routers/tasks.py 鉴权+会话注入依赖，SSE 端点也须鉴权，陷阱⑤）。
- [Source: backend/src/muse/core/db.py（L18-33）] — async engine + `async_session_maker`（web 请求级 `get_session`）；worker 须自建独立 engine（陷阱⑦）。
- [Source: backend/src/muse/schemas/base.py（L29-34）] — `CamelModel`（alias_generator=to_camel，TaskSubmitResponse 的 taskId 边界）。
- [Source: backend/src/muse/routers/byok.py] + [routers/usage.py] — router 仅校验分发 + `CurrentUser` + prefix `/api/xxx`（routers/tasks.py 照此，prefix `/api/tasks`）。
- [Source: backend/src/muse/main.py（L11,21-30）] — router 注册点（+`tasks` import、+`include_router(tasks.router)`）；lifespan engine.dispose 范式（worker/pool 生命周期参照）。
- [Source: backend/src/muse/models/account.py（L90-129）] — `UsageLedger`（本 story 复用记账，字段 total_tokens/cost Numeric(12,6)/billing_path，AC5）；本 story 不加 ORM 模型。
- [Source: backend/pyproject.toml（L6-19）] — 依赖已含 arq>=0.25.0/sse-starlette>=3.4.6/openai/redis>=8.0.1（无新依赖）。
- [Source: backend/tests/conftest.py（L35-38,111-146）] — `@requires_db` 门禁（`@requires_deepseek`/`@requires_redis` 仿此）、`load_all_models`（无新模型无需改）、`make_user`/`auth_headers` fixture。
- [Source: backend/tests/test_usage.py] + [test_byok.py] — 离线 mock 单元 + `@requires_db` DB 端到端 + 独立引擎直查结构（test_providers.py/test_tasks_sse.py 照此）。
- [Source: _bmad-output/implementation-artifacts/1-8-托管免费额度护栏与用量展示.md#Completion-Notes] — 1.8「Epic 2 Story 2.1 接管清单」（记账埋点/护栏接入/计量口径对齐）——本 story 兑现的对侧。
- [Source: _bmad-output/implementation-artifacts/sprint-status.yaml（MUSE SEQUENCING NOTES）] — 「1-8 护栏真正生效依赖 Epic 2 Provider 层埋点（AR14）」「盲测 4-1 是硬门禁、依赖 Epic 2 LLM 底座 2-1」（本 story 是 2-1 底座）。

## Dev Agent Record

### Agent Model Used

Claude Opus 4.8 (claude-opus-4-8, joybuilder)

### Debug Log References

- **SSE Pub/Sub「先订阅后发布」时序（AC4 定档① + 陷阱⑥）根因定位与修复**：初次跑 SSE/ARQ 端到端用例，`_drain_pubsub` 收到空事件列表（happy/error/arq 三例失败）。最小复现确认：redis-py asyncio 的 `pubsub.subscribe()` 只把 SUBSCRIBE 命令写进 socket、**不等服务端确认**，若随即在另一连接 `publish()`，PUBLISH 可能先于 SUBSCRIBE 被服务端处理 → 增量丢失。修复：`subscribe()` 后**读掉一次 subscribe 确认消息**强制 round-trip，保证订阅已注册。此修复同时硬化了**生产 `core/sse.event_stream`**（不止测试）——把「①先订阅并读确认 → ②读快照补发 → ③听增量」的 ordering 落实，补发窗口后零丢失。测试侧同源加 `_subscribe` helper。
- **真实 DeepSeek 契约测试 max_tokens 过小暴露推理档特性**：`test_real_deepseek_chat_contract` 初设 `max_tokens=100`，flash 档返回 `content=''`（空正文）。查明 `deepseek-v4-flash` 是**推理模型**，`reasoning_content` 先吃 token 预算——100 tokens 被思考占满、正文无预算。`usage` 非空（total=111）、`reasoning` 正常捕获，Provider 逻辑无误。改 `max_tokens=512` 后正文非空。**口径记录**：调用推理档时须给足 max_tokens 余量，否则正文可能被思考挤空（Epic 4 真实生成须注意）。

### Completion Notes List

**实现摘要**：交付 Epic 2 运行时底座——可换模型的 `LLMProvider` 抽象 + `DeepSeekProvider`（async）+ Provider 工厂（BYOK/托管分派）+ ARQ worker + 示范任务 + SSE 三事件（含快照补发）+ 用量记账/护栏**首次真实接入 LLM 调用链路**。`app.js` 零改动、不建表、无新依赖。全量 133 passed / 1 skipped（真实契约门禁 CI 默认 skip）。ruff + mypy 全绿。

**✅ 兑现 Story 1.8 跨 epic 依赖（最重要闭合点）**：`record_usage` / `check_quota` 首次获得真实运行时消费方。全链路人工核对（真实 DeepSeek key）：worker `demo_generate` 托管路径跑通「check_quota → provider.chat（真实 DeepSeek）→ record_usage」，`usage_ledger` 落库 `billing_path=hosted`、`total_tokens=84`（**API 回报值非本地估算**）、`cost=0.000156`（**Decimal 类型**，非 float）、`model=deepseek-v4-flash`；SSE 收 `progress×3 → result`。

**三项定档决策（用户 2026-07-27 授权，已按最佳方案落地）**：
1. **SSE 时序缺口 → 快照键补发 + Pub/Sub 增量**（非 Redis Stream）：`publish_event` 同时 `SET task:{id}:snapshot` + `PUBLISH`；`event_stream` 先订阅（读确认）→ 读快照补发一次 → 听增量。覆盖 V1「晚订阅/单次重连」；终态任务重连立即拿 result/error。**V2 若需多消费者+精确断点续读再升 Stream**（平滑超集）。
2. **Provider 只实现 DeepSeek**：工厂对 `claude`/`custom` 抛 `provider_not_supported`（400，不静默失败）。ClaudeProvider 归盲测 Story 4.1。
3. **custom provider 仅抽象层预留形状**：`DeepSeekProvider.__init__` 已接受 `api_key`/`base_url`/`default_model`/`fast_model` 参数（Provider 契约含配置来源形状），**未改 `byok_key` 表 / `ByokBindRequest` / `app.js`**。

**dev 决策点记录**：
- **记账埋点位置**：用 `MeteredProvider` 包裹器（provider-agnostic），记账逻辑与具体模型解耦——换模型（新增 Provider 子类）无需重写记账，只要子类如实返回 usage。工厂对不同 Provider 传对应 `cost_fn`。
- **流式 usage 口径**：`stream()` 请求 `stream_options={"include_usage": True}`，优先用 API 末 chunk 回报的 usage；若服务端未回，用 `count_tokens` 本地兜底估算并在 `StreamUsage.estimated=True` 标记（记账可辨识口径）。DeepSeek 实际支持 include_usage（真实契约测试的 chat 路径已验 usage 非空；stream 的 include_usage 未在真实 API 下单独验证，留 Epic 2 探索对话接线时确认）。
- **worker session/连接生命周期（陷阱⑦）**：`on_startup` 建 worker 独立 async engine + session_maker + 独立发布用 Redis 连接，`on_shutdown` 释放；任务内每次开新 session 调 provider（record_usage 内部 commit）。绝不复用 web 请求 session。
- **SSE 端点 IDOR 防护（陷阱⑤）**：taskId = 不可枚举 uuid4 hex；提交时 `SET task:{id}:owner` 存属主 user_id（**入队前**登记，防 worker 抢先发事件时鉴权读不到属主），SSE 端点 `CurrentUser` + 比对属主，非本人/不存在**一律 404 task_not_found**（不区分，防存在性探测）。
- **DeepSeek 单价常量**（`providers/deepseek.py` `_PRICE_PER_MILLION_TOKENS`）：`deepseek-v4-pro=(4,16)`、`deepseek-v4-flash=(1,2)` 元/1M token，**dev 2026-07-27 填的占位值**。**⚠️ 上线前须核对 DeepSeek 官方定价并更新此常量**（改常量即可、不动逻辑）。未知模型名兜底 0 成本（配置漂移时便于审计发现，不静默虚计费）。

**⚠️ 仍需登记的 defer（不让悬空）**：
- **1.8 check_quota TOCTOU 并发护栏 → 继续 defer 至 Story 4.4**：本 story 无真实并发生成面（只有示范任务），`check_quota`「读累计→判定→调用后才 record」的时间窗风险未现实化。**真实生成入口（4.4 章节生成）落地时必须做并发控制**（原子递增 / SELECT FOR UPDATE / 预留额度择一），不得再 defer。
- **custom provider 真正可用仍需补齐 → 归 custom 启用切片**：需补 `byok_key.base_url`/`model_name` 列 + `ByokBindRequest` 字段 + `app.js` custom 输入框（Provider 层已预留参数、届时零改动）。本 story 只降风险、未完全闭合 1.7 deferred-work.md:46 这条。
- **流式 include_usage 真实验证 → Epic 2 探索对话接线切片**：本 story 的 stream 真实 API usage 回传未单独契约验证（离线 mock 已覆盖两分支：API usage / 本地兜底），探索对话真正用 stream 时确认 DeepSeek 流式 usage 行为。

**受控决策（非阻塞，供用户知悉）**：本 story 护栏/记账首次接入 LLM 链路但仍非「面向用户的生成」——真实探索整理（2.5/2.7）、章节生成（4.4）才是护栏真正拦用户处；本 story 用示范任务证明接口串联可用。worker 启动命令 `make dev-worker`（= `uv run arq muse.tasks.worker.WorkerSettings`），与 `make dev-up` 配套。

### File List

**新增**：
- `backend/src/muse/providers/base.py` — LLMProvider 抽象 + ChatResult/StreamChunk/StreamUsage/LLMError dataclass（禁 import openai）
- `backend/src/muse/providers/deepseek.py` — DeepSeekProvider（AsyncOpenAI，唯一 openai 出口）+ compute_cost（Decimal 单价）
- `backend/src/muse/providers/factory.py` — get_provider_for_user（BYOK/托管分派）+ MeteredProvider（记账包裹）
- `backend/src/muse/tasks/worker.py` — ARQ WorkerSettings + demo_generate 示范任务（串 check_quota→provider→record_usage）
- `backend/src/muse/routers/tasks.py` — POST /api/tasks/demo + GET /api/tasks/{id}/events（SSE + IDOR 归属校验）
- `backend/src/muse/schemas/task.py` — TaskSubmitResponse（taskId camelCase 边界）
- `backend/tests/test_providers.py` — Provider 单元离线 mock + 工厂分派 + 记账串联 + 真实契约门禁（14 用例）
- `backend/tests/test_tasks_sse.py` — SSE 快照补发/终态重连 + demo_generate happy/error + ARQ 端到端 + IDOR 校验（11 用例）

**填实占位**：
- `backend/src/muse/core/sse.py` — 三事件封装 + publish_event（快照+发布）+ event_stream（订阅确认→补发→增量）+ 任务归属键

**扩展**：
- `backend/src/muse/core/settings.py` — +deepseek_api_key/base_url/model_thinking/model_fast（无 fail-fast）
- `backend/src/muse/main.py` — +import tasks + include_router(tasks.router)
- `backend/.env.example` — +DEEPSEEK_API_KEY/DEEPSEEK_BASE_URL
- `backend/tests/conftest.py` — +@requires_redis / @requires_deepseek 门禁
- `Makefile` — +dev-api / dev-worker 目标（worker 启动命令）

### Change Log

| 日期 | 变更 | 作者 |
|---|---|---|
| 2026-07-27 | 实现 Story 2.1：LLMProvider 抽象 + DeepSeek 实现 + ARQ/SSE 异步底座 + 用量记账/护栏首次接入（兑现 1.8 跨 epic 依赖）。9 Tasks 全完成，133 passed/1 skipped，ruff+mypy 绿，全链路真实 DeepSeek 核对通过。Status → review。 | Dev (Opus 4.8) |

## Review Findings

> 三层对抗式代码审查（Blind Hunter / Edge Case Hunter / Acceptance Auditor，2026-07-27），主审已逐条核验代码事实（含 ARQ 0.25.0 重试语义源码、`.env` key 状态、各文件真实实现）。分类：0 decision-needed / 6 patch / 6 defer / 3 dismissed。
>
> **2026-07-27 处置：6 条 patch 已全部就地修复并通过验证**（ruff + mypy 干净；全量 133 passed / 1 skipped；并模拟干净 CI 空 `DEEPSEEK_API_KEY` 环境复验 happy-path 由 FAIL 转 PASS）。6 条 defer 归后续 story（见 deferred-work.md），3 条 dismissed 不计入。

### Patch（可直接修复，无需决策）

- [x] [Review][Patch] happy-path 记账测试耦合本机 `.env` 的 `DEEPSEEK_API_KEY`，干净 CI 会 FAIL 而非 skip [backend/tests/test_tasks_sse.py:201-253 + backend/src/muse/tasks/worker.py:64] — `test_demo_generate_happy_path_publishes_and_records_usage` 只 patch 了 `AsyncOpenAI`，未注入 `settings.deepseek_api_key`；demo_generate 用 `if settings.deepseek_api_key:` 作真实生成门槛。dev 本机 `.env` key 非空（已核实）→ 分支被走到、断言通过、「133 passed」成立；但在 `MUSE_DB_READY=1 MUSE_REDIS_READY=1` 且 key 为空的环境（全新 CI checkout），分支跳过→不 record_usage→`assert row is not None` **失败**。「兑现 1.8 最重要闭合点」的旗舰验证非确定性。修复：测试内 `monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")` 或直接 patch `settings.deepseek_api_key`，使记账分支恒定被测。（Auditor + Edge 独立指出）✅ **已修复**：测试内加 `patch.object(get_settings(), "deepseek_api_key", "test-key")` 强制走记账分支；已模拟空 key 环境复验由 FAIL 转 PASS。
- [x] [Review][Patch] `MeteredProvider.stream` 在消费方提前断开或流中途异常时跳过 record_usage，已消耗 token 不计费 [backend/src/muse/providers/factory.py:110-118] — 记账仅在末尾 `StreamUsage` 到达时发生。SSE 消费方中途断连（generator `aclose()` → `GeneratorExit`）或内层 stream 在产出 StreamUsage 前抛异常（OpenAI 中途 5xx），`_record` 永不执行——LLM 已计费 token 未落库（托管收入漏计；用户可早断流白嫖）。修复：用 `try/finally` 或捕获中断，在流终止时用已累计的兜底 usage 记账。（Blind 独立指出）✅ **已修复**：改用 `try/finally` + `recorded` 标记；正常路径拿到 StreamUsage 精确记账，早断/异常路径在 finally 用已累计输出本地估算兜底记一次，两路径互斥不双记。
- [x] [Review][Patch] worker 通用异常 `str(exc)` 原文经 SSE error 事件回传前端，内部信息泄漏 [backend/src/muse/tasks/worker.py:91-94] — `except Exception` 分支把 `str(exc)` 塞进 error payload 的 message 推给终端用户。DB `OperationalError`、连接串片段、SQLAlchemy 驱动错误、内部路径等可外泄。修复：通用异常回统一泛化 message（如「生成失败，请稍后重试」），原始 exc 仅 `logger.exception` 落日志；`ErrorEnvelope` 分支（已是受控 code/message）保持不变。（Blind 独立指出）✅ **已修复**：通用 except 改推固定文案「生成失败，请稍后重试。」，原始 exc 经 `logger.exception` 落日志；ErrorEnvelope 分支不变。
- [x] [Review][Patch] `event_stream` 的 Redis 连接创建在 try 之外，subscribe/get_message 抛错则连接泄漏 [backend/src/muse/core/sse.py:106-114] — `sub = Redis.from_url(...)`、`pubsub.subscribe()`、`get_message()` 均在 `try:` 之前，仅 try 内的 finally 才 aclose。Redis 抖动/超时使 subscribe 抛错时 finally 不执行，`sub` 连接及连接池泄漏；每个失败的 SSE 连接漏一个，累积耗尽。修复：把连接创建纳入 try，或 setup 段单独 try/except 兜底关闭。（Blind + Edge 独立指出）✅ **已修复**：`subscribe`/`get_message` 纳入 try；finally 中 `unsubscribe` 用嵌套 try 包裹，保证连接已断时 `aclose` 仍执行、连接不泄漏。
- [x] [Review][Patch] `DeepSeekProvider.chat` 未防空 `choices`，空响应触发裸 IndexError [backend/src/muse/providers/deepseek.py:98] — `chat` 直接 `resp.choices[0]`，而同文件 `stream` 已防御 `if not chunk.choices: continue`。OpenAI/DeepSeek 在内容过滤/异常态可返回空 choices。worker 路径被 `except Exception` 兜住但错误消息含内部细节（`list index out of range`）；未来真实生成端点直调 chat 会 500。修复：`if not resp.choices: raise ErrorEnvelope("generate_failed", ...)`（或类同 usage 的防御兜底），与 stream 一致。（Blind + Edge 独立指出）✅ **已修复**：`choices` 为空时抛 `ErrorEnvelope("generate_failed", http_status=502)`，与 stream 防御一致，替代裸 IndexError。
- [x] [Review][Patch] 归属键 TTL 与快照键相等且不续期，注释声称「略长于快照」的不变量被违反 [backend/src/muse/core/sse.py:35-37] — `_OWNER_TTL_SECONDS = _SNAPSHOT_TTL_SECONDS = 3600`，owner 键仅提交时写一次、snapshot 每次 publish 续期，故 owner **先**过期。任务终结近 1 小时后重连，owner 已过期但快照仍在 → SSE 端点校验 owner 得 None → 误返 404，合法属主拿不到本该可读的终态。修复：`_OWNER_TTL_SECONDS` 取实质更大值（如 7200），或 publish 终态时一并续期 owner 键。（Blind + Edge 独立指出）✅ **已修复**：`_OWNER_TTL_SECONDS = _SNAPSHOT_TTL_SECONDS * 2`（2 小时），确保 owner 覆盖整个快照可读窗口；注释同步更正不变式说明。

### Defer（真实但非本切片必修 / 归后续 story）

- [x] [Review][Defer] worker 被取消（SIGTERM/关闭）且已 record_usage 之后，ARQ 重跑任务致重复计费 [backend/src/muse/tasks/worker.py:118-128] — deferred。经核实 ARQ 0.25.0 源码：普通 `Exception` 落 `else` 分支**不重试**（Blind「任何 raise 都重试」表述过重）；仅 `CancelledError`/`Retry` 重跑（`retry_jobs=True`、`max_tries=5` 默认）。真实风险窗口：worker 消费任务、`record_usage` 已 commit，但 job 未登记完成时被 SIGTERM 取消 → CancelledError → 重跑 → 第二条 usage_ledger 行。demo 任务非幂等。本 story 只有示范任务、无真实并发生成面，与下条 TOCTOU 同属「真实生成入口（4.4）落地时」加固。归 Story 4.4：`WorkerSettings.max_tries=1` 或任务级幂等键（record_usage 带 task_id 去重）。
- [x] [Review][Defer] `check_quota` → `record_usage` 之间 TOCTOU，托管额度并发可超发 [backend/src/muse/tasks/worker.py:53-73] — deferred，**1.8 已登记同一条**（deferred-work.md:56，Jianghj 2026-07-27 裁定 defer 至接入生成链路时做）。本 story 是「接入生成链路」时点但仍无真实并发生成面（只示范任务），Completion Notes（L278）已重新登记「真实生成入口 4.4 落地时必须做并发控制」。归 Story 4.4，不再 defer。
- [x] [Review][Defer] `demo_generate` 用 `settings.deepseek_api_key` 作真实生成门槛，BYOK 用户被跳过记账链路 [backend/src/muse/tasks/worker.py:64] — deferred。已绑定 deepseek 的 BYOK 用户走自己的 Key（不依赖托管 key），但 worker 用「托管 key 是否配置」作唯一门槛，导致托管 key 空但已配 BYOK 的用户走进「跳过真实生成」分支，BYOK 记账路径未被示范任务覆盖。本 story 为底座示范任务、非真实生成入口，BYOK 路径由 factory 单元测试覆盖（已验 byok 分派）。归真实生成入口切片（4.4）：以「用户是否有可用 provider」而非「托管 key 是否配置」为门槛。
- [x] [Review][Defer] OpenAI 流式响应未用 `async with`/显式 close，中途异常/早断可能不释放连接 [backend/src/muse/providers/deepseek.py:130-141] — deferred。`stream = await client.chat.completions.create(stream=True)` 后直接 `async for`，无 `async with`/`finally: await stream.close()`。中途 break/异常时底层 httpx 流响应可能不归还连接池。与上「MeteredProvider.stream 早断不计费」的 patch 同源场景，宜在流式真实接线（Epic 2 探索对话，Completion Notes L280 已登记流式 include_usage 待验）时连同 stream 生命周期一起硬化。归 Epic 2 探索对话接线切片。
- [x] [Review][Defer] SSE `event_stream` 的 `listen()` 无服务端超时，worker 崩溃/永不推终态时流永久挂起 [backend/src/muse/core/sse.py:126] — deferred。快照为 None（任务入队但 worker 未起/已崩）或快照非终态（发完 progress 就崩）时进入 `pubsub.listen()` 无 watchdog；worker `except Exception` 不捕获 `CancelledError`（SIGTERM 时不推 error）。客户端 UI 永久「生成中」，靠 sse-starlette 15s ping 保活直到客户端放弃。本 story 示范任务不会主动崩，真实长时生成（Epic 4）才现实化此风险。归 Epic 4：加任务级看门狗/整体超时，或 worker 信号处理器捕获 CancelledError 推 error 终态。（Blind + Edge 独立指出）
- [x] [Review][Defer] AC4/Task5/定档① 原文「先补发快照再订阅」与代码「先订阅再补发快照」矛盾（spec 可追溯性缺陷）[spec L33/L87/L149 vs backend/src/muse/core/sse.py:113-126] — deferred（文档修正，非代码问题）。代码顺序**更正确**：dev 在实现中发现原顺序有竞态（Debug Log L256 + 模块 docstring 已论证 subscribe-first 消除「读快照与订阅间丢终态」），Completion Notes 定档①（L266）已是 subscribe-first。AC4 的 Then-意图（晚订阅/重连不丢进度、终态立即拿）由代码达成且测试佐证。属同一文档内前文（AC/Task/定档）陈旧措辞与后文（Completion Notes）+ 代码打架。归文档收尾：回改 AC4/Task5/定档① 的 snapshot-first 措辞为 subscribe-first，保持验收契约字面与实现一致。（Auditor 独立指出）

### Dismissed（噪音 / 已他处处理，不计入）

- `_fast_model` 死字段（Blind#10）——dismiss：`DeepSeekProvider.__init__` 接受 `fast_model` 是定档③「custom provider 抽象层预留配置形状」的一部分（Completion Notes 明载 Provider 契约含配置来源），非死代码；worker 显式传 `model=settings.deepseek_model_fast` 是既定用法。
- `json.loads(...)["event"]` 无防御（Blind#11）——dismiss：快照键/频道载荷完全由 `publish_event` 受控生成（本 story 无外部写入面），格式恒定合法；防御性解析属过度设计，与项目「不为不可能场景加防御」一致。
- 并发解绑致空 key 构造 / KeyDecryptError 未显式处理（Edge#9）——dismiss：并发解绑窗口极窄且降级为不透明鉴权错误（已被 worker except 转 generate_failed），KeyDecryptError 同样被兜住且不泄漏明文（已核实 security.py）；与既有 1.5/1.7 check-then-act 同风险级，无独立加固价值。



