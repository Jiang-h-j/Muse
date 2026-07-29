---
baseline_commit: 9780f72bb583c62f641c70466eb6a428f2f68cfc
---
# Story 3.2: 文风锚点入口（全新 UI）+ style_profile 抽取

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a 在意文字质量的用户，
I want 从预置样本库选择或粘贴一段我爱读的文字来锚定文风，
so that 生成的正文能贴近我真正喜欢的笔触、而非通用 AI 腔。

## Acceptance Criteria

1. **[两种锚定方式]** 用户在设定阶段能通过两种方式锚定文风：**从预置样本库选择**，或**粘贴一段自己爱读的文字**。后端提供预置样本库（含样本原文），两条路径最终都进入同一条真实抽取链路。[Source: epics.md#Story-3.2 AC1（687-689）；FR16（62）；UX-DR1（149）；原型 app.js:1895-1938 styleSampleLibrary + tabs]
2. **[真实抽取 style_profile]** 用户选定/粘贴文风样本后，系统**真实调 LLM**（经 LLMProvider 抽象，禁直调 openai）抽取作品级 `style_profile`——含五维：人称、语气、句式节奏、意象密度、段落长度倾向。[Source: epics.md#Story-3.2 AC2（691-693）；AR15（架构 210-211）；原型 styleAnchorProfileMarkup 五维 app.js:1940-1954]
3. **[持久化到 story_bible]** 抽取完成后，`style_profile` 以 get-or-create 方式 upsert 到本作品的 `story_bible` 行（`style_profile` 列）；后续 Story 3.5 确认设定时该值已随圣经就位（3.3 出候选卡填第⑫字段时可读取本值）。[Source: epics.md#Story-3.2 AC3（695-697）；epics.md#Epic-3（651「3.3 出卡时消费 3.2 已抽取的 style_profile」）；架构 AR15（212）；story_bible.style_profile 列已由 3.1 建好]
4. **[跨 epic 依赖显式标注]** `style_profile` 抽取产物可用作 Epic 4 Story 4.1 盲测（AR19 launch blocker）的风格锚点输入——本 story 交付的抽取原语/存储形态须显式标注此下游消费点，避免后续改动破坏盲测输入契约。[Source: epics.md#Story-3.2 AC4（699-701）；epics.md#Story-4.1（809）；NFR1（85-89）]
5. **[未锚定可空、不阻塞]** 用户未锚定任何文风样本时，`style_profile` 保持可空（NULL）、系统用合理默认风格、不阻塞出设定；但因红线验收理想态需锚定，须以提示引导用户「锚定更佳」。[Source: epics.md#Story-3.2 AC5（703-705）；NFR1 理想态；story_bible.style_profile nullable=True]
6. **[分层与护栏合规]** 抽取端点遵循 router→service→provider 分层：router 仅校验入参 + 分发；抽取编排在 service 层，用**独立 session** 自管（陷阱⑩，仿 free_explorer_agent），调 provider **之前**过 `check_quota` 护栏（托管触顶抛 429、BYOK 短路放行），Provider 层自动记账（AR14）。租户守卫：project 不属当前 user 即 404 二义合一（不区分不存在/不属于我，NFR3）。[Source: architecture.md（router→service→provider）；free_explorer_agent.extract_clues 范式；2.1 AC6 护栏；exploration_service._exploration_not_found]

## Tasks / Subtasks

- [x] **Task 1：预置样本库常量（后端存全文）**（AC: 1）
  - [x] 在新建的 `services/style_anchor_agent.py` 内定义 `STYLE_SAMPLE_LIBRARY`：3 个预置样本，各含 `id`（稳定 slug）、`name`、`note`、`excerpt`（**较完整的样本原文，供真实抽取喂 LLM**——原型 excerpt 仅一两句是展示占位，后端须给足够长的原文让抽取有料可抽）。id 与原型对齐：`cold-rain`（冷峻夜雨）、`warm-dusk`（黄昏暖光）、`sharp-first`（凌厉第一人称）。[Source: 原型 app.js:1895-1938]
  - [x] **决策记录（受控，Jianghj 已授权自主选）**：库选与粘贴**统一走真实抽取**（不为 library 预烘焙 profile 常量）——理由：① 契约单一（两路径同一条 LLM 抽取链，无「库=假值 / 粘贴=真值」二义）；② 直接服务 NFR1 红线（盲测输入须是真实抽取产物）；③ 成本可控（抽取是一次性快档小调用，同 extract_clues）。代价：预置样本须存较完整原文（本 task 交付）。
- [x] **Task 2：style_bible repo 最小 upsert 原语**（AC: 3, 6）
  - [x] 新建 `repositories/story_bible_repo.py`（一表一文件，同 story_clue_repo 先例）。**本 story 只需两个方法**，不写完整 CRUD（3.3/3.5 各自按需扩）：
    - [x] `get_by_project(session, *, user_id, project_id) -> StoryBible | None`：照抄 `project_repo.get_owned_project` 的「id/user_id 同一 where」范式，按 `(user_id, project_id)` 一步过滤，取不到返 None（租户二义合一，陷阱①）。
    - [x] `upsert_style_profile(session, *, user_id, project_id, style_profile: str) -> StoryBible`：get-or-create——存在则更新 `style_profile` 列，不存在则新建一行（主干 7 列靠 `server_default=""` 自动填空串、特化 4 列留 NULL），返回该行。**不 commit**（commit 归 service，与既有 repo 约定一致）。
  - [x] **边界（务必守住）**：本 repo **不写** revision/status、不做设定卡生成/确认逻辑（那是 3.3/3.4/3.5）。本 story 只往 `story_bible.style_profile` 一列写值——`story_bible` 行此时可能是「仅有 style_profile 的半成品行」，这是 3.1「待确认项 2」下 3.2 提前建行的**受控结果**（见 Dev Notes 决策记录）。
- [x] **Task 3：style_anchor_agent service（真实抽取编排）**（AC: 2, 3, 5, 6）
  - [x] 在 `services/style_anchor_agent.py` 写 `extract_and_anchor_style(*, user_id, project_id, sample_text) -> StoryBible`（或返回 style_profile 文本 + 落库行）：**照 `free_explorer_agent.extract_clues` 范式**——
    - [x] 独立 `async_session_maker()` 自管 session（陷阱⑩，虽非流式但调 provider）。
    - [x] 重校验租户（`get_owned_project` → None 则 `_exploration_not_found`）。**mode 守卫**：文风锚点是设定阶段作品级操作、guided/free 两模式都可锚定文风，故**不加 mode 守卫**（与 interpret/free-chat 的模式专属端点不同——见 Dev Notes 决策）。
    - [x] `check_quota` 在调 provider **之前**（护栏，托管触顶 429、BYOK 短路）。
    - [x] `get_provider_for_user(session, user_id, project_id=project_id)` 构造带记账 Provider，`provider.chat(messages, model=deepseek_model_fast, max_tokens=...)`（非流式一次性结构化输出，同 extract_clues；快档需留足 max_tokens 避免推理档挤空正文，陷阱⑥，参考 `_EXTRACT_MAX_TOKENS=1024`）。
    - [x] system prompt 要求 LLM 按**固定五维格式**输出（人称/语气/句式节奏/意象密度/段落长度倾向），照 `_build_extract_messages` 的「标签：内容」固定前缀风格 + 面向大众网文向、去 AI 味口吻（NFR1，[[project_muse_quality_redline]]）。
    - [x] 解析响应为结构化 style_profile 文本（V1 存 Text，非 JSONB——见 Dev Notes 存储形态决策），防御性解析（模型偏离格式不崩，仿 `_parse_extract_response`）。
    - [x] 调 `story_bible_repo.upsert_style_profile` 落库 + `session.commit()`。
  - [x] **抽取模式选择（受控决策，已授权）**：用**同步 REST（provider.chat）**而非 ARQ+SSE——理由：文风抽取是「一次性结构化小提炼、非长时生成」，与 `free/clues/refresh` 同类（exploration.py:32-35 明写此类同步端点即可），不引入 Redis/worker。settle（ARQ）是批量后台任务模式，不适用。
- [x] **Task 4：API schema + router**（AC: 1, 2, 5, 6）
  - [x] 新建 `schemas/story.py`（story 域 schema 起点）：
    - [x] `StyleAnchorRequest(CamelModel)`：`sample_text: _NonBlankText`（复用/仿 exploration schema 的非空有界文本校验，min_length≥20 对齐原型 paste 门槛「至少 20 字」app.js:2238-2239、max_length 保守上界拦超长挤爆 prompt）。**库选路径**：前端把选中样本的原文（或后端按 sampleId 取原文）作为 sample_text 提交——见下方 sampleId vs sampleText 决策。
    - [x] `StyleProfileResponse(CamelModel)`：返回抽取后的 `style_profile`（文本）+ `anchored: bool`。字段 camelCase 自动转换。
  - [x] **sampleId vs sampleText 决策（受控，已授权）**：请求支持二选一——`sampleId`（库选，后端据 id 从 `STYLE_SAMPLE_LIBRARY` 取原文）**或** `sampleText`（粘贴）。二者互斥、至少一个（Pydantic model_validator 校验）。理由：库选不必把整段原文经网络回传（前端只需传 id）、粘贴才传全文；后端统一解析出 sample_text 喂抽取链，**契约仍单一**（Task 1 决策的落地）。
  - [x] 新建 `routers/story.py`，`prefix="/api/projects"`，`tags=["story"]`：
    - [x] `POST /{project_id}/style-anchor`：非流式（同步抽取，返 200 + StyleProfileResponse）。router 仅：取入参 → 调 `style_anchor_agent.extract_and_anchor_style` → model_validate 返回。**先做租户预检**（可选：若 service 内已重校验则 router 只透传，仿 refresh_clues 直接调 service）。project_id 非法 UUID 自动 422。
    - [x] （可选）`GET /{project_id}/style-anchor/samples`：返回预置样本库（id/name/note/excerpt）供前端渲染——**若前端接线本 story defer（见受控决策 A），可不建此端点、样本库暂由前端常量承载**；建议**建**（后端做样本库单一事实源，避免前后端样本漂移）。
  - [x] 在 `main.py` 注册 `story.router`（`app.include_router(story.router)`，仿现有 7 个 router 注册）。
- [x] **Task 5：测试**（AC: 2, 3, 5, 6）
  - [x] service 单测：mock provider（不打真实 LLM，同既有 explorer/free agent 测试范式），验证：① 抽取→upsert 后 `story_bible.style_profile` 落值；② `get_by_project` 已存在行时 upsert 走 UPDATE（不重复建行、不撞唯一约束）；③ check_quota 触顶（mock 抛 ErrorEnvelope 429）时不调 provider、不落库；④ 租户越权（他人 project_id）返 404。
  - [x] repo 单测（需真实 DB，`MUSE_DB_READY=1`）：`upsert_style_profile` 首次建行（主干列空串、特化列 NULL、style_profile 有值）、二次 upsert 更新同行不违反 `uq_story_bible_user_id_project_id`。
  - [x] schema 单测：sampleId/sampleText 互斥校验、sample_text < 20 字 422、二者皆空 422。
  - [x] 全量 `MUSE_DB_READY=1 MUSE_REDIS_READY=1 uv run pytest -q` 零回归；`uv run ruff check .` 干净。

### Review Findings

_（code review 2026-07-29：Blind Hunter + Edge Case Hunter + Acceptance Auditor 三层并行审查。6 条 AC 实质全满足、受控决策全一致、未越界。3 patch / 1 defer / 4 dismissed。）_

- [x] [Review][Patch] upsert_style_profile 首次并发插入撞唯一约束未兜底 → 500 [backend/src/muse/repositories/story_bible_repo.py:88-95] — 同一 (user_id, project_id) 首次锚定并发两请求（双击/重试/双标签页）都查不到行、都走 INSERT，第二条 flush 撞 `uq_story_bible_user_id_project_id` 抛 IntegrityError，冒泡为未包装 500。本 story 声称照抄 get-or-create 先例却漏抄竞态兜底。修法：照 `exploration_service.enter_exploration:108-132` 加 `try/except IntegrityError → rollback → 重查转 UPDATE`。blind+edge 双层命中。**[已修复]** `extract_and_anchor_style` upsert+commit 包 `try/except IntegrityError → rollback → get_by_project 重查 → 改 UPDATE → commit`；新增单测 `test_extract_upsert_race_recovers_to_update` 验证兜底路径。
- [x] [Review][Patch] resolve_sample_text 用 assert 承载运行期契约（-O 剥离风险）[backend/src/muse/services/style_anchor_agent.py:264] — `assert sample_text is not None` 在 `python -O` 下整行被剥离，届时若绕过 schema 直调本模块级公共函数且 sample_text 为 None，会 `return None` 违反 `-> str` 签名，下游 `_build_messages` 把字面量 "None" 喂 LLM。改为显式 `if sample_text is None: raise`。blind+edge+auditor 三层命中。**[已修复]** 改为显式 `if sample_text is None: raise ErrorEnvelope(unknown_style_sample, 400)`。
- [x] [Review][Patch] sample_id 未 strip 归一化，带首尾空白的合法 id 误判 400 [backend/src/muse/schemas/story.py:425-431 + services/style_anchor_agent.py:254] — 请求 `sampleId=" cold-rain"`：validator `has_id` 判 True（视为已提供、不归一），resolve 用未 strip 原值 `_SAMPLE_BY_ID.get(" cold-rain")` 命中不了 → 400 unknown_style_sample。对合法样本误 400。修法：validator 里把 `sample_id` strip 后再存（有值时 `self.sample_id = self.sample_id.strip()`）。blind 命中。**[已修复]** validator 归一化 `self.sample_id = self.sample_id.strip() if has_id else None`；新增单测 `test_schema_sample_id_whitespace_stripped`。另补 `test_schema_sample_text_too_long_rejected`（消除 Auditor 指出的超长 422 假覆盖）。
- [x] [Review][Defer] provider.chat 上游异常映射 500 而非 502/503 [backend/src/muse/services/style_anchor_agent.py:356-360] — deferred, pre-existing。provider.chat 抛异常（DeepSeek 5xx/超时/断连）无 try/except 冒泡为 500，与同函数空产路径的 502 状态码不一致。但这是照抄 `free_explorer_agent.extract_clues` 的**全项目共性行为**（非本 story 引入），统一到 502/503 应作跨 story 一致性改造。edge 命中。

## Dev Notes

### 本 story 的边界（务必守住，勿越界）

- **本 story 交付**：预置样本库（后端全文）+ style_profile 真实抽取编排（LLM）+ upsert 到 `story_bible.style_profile` 一列 + API schema/router + 测试。
- **不做**：不做 12 字段设定候选卡生成（3.3）、不做设定卡编辑/反馈升版本（3.4）、不做设定确认→只读圣经/回到探索丢弃（3.5）、不建 revision/status 列（3.1「待确认项 2」，仍未裁定）、不做前端页面接线（前端 defer，见受控决策 A——原型页 app.js:1890-2330 已是契约，前端集成切片单独排）。
- **不碰** drafter 注入（Epic 4）：本 story 只让 style_profile「就位可读」，注入 drafter 是 Epic 4 Story 4.4/4.2 的事（AR15），本 story 仅显式标注该下游消费点（AC4）。

### 受控决策记录（Jianghj 2026-07-29 已授权自主选最优，[[feedback_design_decision_delegation]]）

1. **持久化落点 = upsert 到 story_bible 行（选项 A）**：抽取值直接 upsert 到 `(user_id, project_id)` 的 story_bible 行 `style_profile` 列。理由：style_profile 是「独立作品级抽取」，与 12 字段卡内容正交（epics.md:653）；3.3「消费 3.2 已抽取值」在 DB 里有确定来源；3.5 确认时该值天然已就位。**连带影响（已想清）**：本 story 须把最小 story_bible repo（get + upsert_style_profile 两方法）从 3.3 提前到 3.2 建——这是 3.1「只建表、repo 留后续」的自然延续，不越界（不写 revision/status、不写卡生成逻辑）。此时 story_bible 行可能是「仅有 style_profile 的半成品」，是可接受的受控中间态（3.3/3.5 会补齐其余字段；主干列 server_default="" 保证半成品行合法）。
2. **抽取路径统一真实抽取（样本库选项 A）**：库选与粘贴都走同一条真实 LLM 抽取链，不为 library 预烘焙 profile 常量。理由见 Task 1。代价：预置样本存较完整原文（Task 1 交付）。
3. **抽取用同步 REST（非 ARQ+SSE）**：文风抽取属「一次性结构化小提炼」，同 free/clues/refresh 类（exploration.py:32-35），同步端点即可，不引入 Redis/worker。
4. **不加 mode 守卫**：文风锚点是设定阶段作品级操作、guided/free 两模式均可锚定，与 interpret/free-chat 的模式专属端点性质不同，故 service 内**不调** `_require_project_mode`（只做租户守卫 + 护栏）。
5. **style_profile 存 Text（非 JSONB）**：承 3.1「待确认项 3」与 architecture「V1 全文」原则——V1 存结构化文本（五维「标签：内容」多行文本），拆 JSONB 属 V2。若 Epic 4 drafter 注入需结构化读取，V2 再改（本 story 在待确认项登记）。
6. **前端接线 defer（受控决策 A，承 Epic 2 全 story + 3.1 先例）**：本 story 后端 only；原型页（app.js:1890-2330）为前端契约事实源，前端集成切片单独排。

### 关键实现模式（照抄现存先例，勿另造）

- **最贴近的抽取样板**：`services/free_explorer_agent.py` 的 `extract_clues`（backend/src/muse/services/free_explorer_agent.py:254-332）——独立 session 自管、check_quota 在调 provider 前、`provider.chat()` 非流式结构化提炼、固定前缀 system prompt（`_build_extract_messages`）、防御性解析（`_parse_extract_response`）。**本 story 的抽取编排基本是它的裁剪版**（去掉多槙位/user_edited 竞态，换成单一 style_profile 五维抽取）。
- **Provider 抽象**：只依赖 `providers/base.LLMProvider`（`chat`/`stream`/`count_tokens`），经 `providers/factory.get_provider_for_user(session, user_id, project_id=...)` 构造**带记账的 MeteredProvider**——**禁直接 new DeepSeekProvider / 直调 openai**（陷阱①，code review 硬卡点，architecture.md:341/356）。model 用 `settings.deepseek_model_fast`（快档）。
- **护栏**：`services/usage_service.check_quota(session, user_id)` 必须在构造/调用 provider **之前**（承 2.1 AC6 / demo_generate step 1 / extract_clues 步骤 4 范式）。托管触顶抛 `ErrorEnvelope(429)`、BYOK 短路放行。
- **租户守卫**：`repositories/project_repo.get_owned_project(session, project_id, user_id)` → None 则抛 `exploration_service._exploration_not_found()`（project_not_found 404，二义合一，NFR3 陷阱①）。**勿新造 code**、勿返 403。
- **repo 范式**：`repositories/story_clue_repo.py`（一表一文件、方法签名 kwargs-only user_id/project_id、不 commit）、`project_repo.get_owned_project`（id+user_id 同一 where）。新 `story_bible_repo.py` 是这两者组合。
- **schema 范式**：`schemas/base.CamelModel`（DB snake_case ↔ API camelCase 唯一转换点，AR4）+ `schemas/exploration.py` 的 `_NonBlankText`/`_BoundedText`（StringConstraints strip + min/max_length）。新 `schemas/story.py` 复用同款文本约束。
- **router 范式**：`routers/exploration.py`（prefix /api/projects、CurrentUser + SessionDep 依赖、router 仅校验+分发、越权 service 层 404、非流式返 response_model）。同步端点参照 `refresh_clues`（exploration.py:408-430）。

### session 生命周期（陷阱⑩，务必遵循）

任何「调 provider（走 MeteredProvider 记账）」的 service 都用**独立 `async_session_maker()` 自管 session**，不依赖请求注入的 web session——`MeteredProvider` 的 finally 兜底记账须落在存活 session 上。`extract_clues` 虽非流式也遵循此范式（free_explorer_agent.py:15）。本 story 抽取同属计费路径，照此办理。

### style_profile 五维（抽取输出契约，对齐原型）

原型 `styleAnchorProfileMarkup`（app.js:1940-1954）定义五维 + 示例值：

| 维度 | 原型示例（冷峻夜雨） | 说明 |
| --- | --- | --- |
| 人称 | 第三人称限知 | person |
| 语气 | 冷峻、克制 | tone |
| 句式节奏 | 短句为主，偶有停顿 | rhythm |
| 意象密度 | 高（雨、旧城、光影） | imagery |
| 段落长度倾向 | 偏短，一段一景 | paragraph |

抽取的 system prompt 须让 LLM 就这五维各输出一行（「维度：描述」固定前缀，仿 `_build_extract_messages`），存为多行文本 style_profile。这五维对齐 FR16/AR15「人称、语气、句式节奏、意象密度、段落长度倾向」。

### 前端契约（原型已是事实源，前端接线 defer）

- 原型文风锚点页：`prototype/app/app.js:1890-2330`（`renderStyleAnchor`、`styleSampleLibrary`、`styleAnchorProfileMarkup`）。路由 `#/projects/demo/style-anchor`（未锚定）与 `?state=anchored`（已锚定）。
- 双 tab：`从样本库选` / `粘贴我的范文`；paste 门槛「至少 20 字」（app.js:2238-2239）；抽取按钮 `data-style-extract`；已锚定后展示五维 profile + 「重新选择」`data-style-reset`。
- 前端 3 样本 id：`cold-rain` / `warm-dusk` / `sharp-first`（Task 1 后端库须对齐）。
- **本 story 不接线前端**（受控决策 A）；后端产出 API 契约（POST style-anchor、可选 GET samples），前端集成切片单独消费。

### Testing standards

- service 测试 **mock provider**（不打真实 LLM，同 explorer/free agent 既有测试）；`MUSE_DB_READY=1` 用于需真实 DB 的 repo/约束测试；`MUSE_REDIS_READY=1` 仅在涉 Redis 时（本 story 同步端点不涉 Redis）。
- 迁移可见性门禁 `tests/test_migrations_metadata.py` 无需改（本 story 不新增表——style_profile 列 3.1 已建）。
- 参照 `backend/tests/` 现有 repo/model/service 测试 fixture 风格；conftest 的 TRUNCATE...CASCADE 隔离，勿改 conftest。

### Project Structure Notes

- 新增：`services/style_anchor_agent.py`、`repositories/story_bible_repo.py`、`schemas/story.py`、`routers/story.py`、`backend/tests/` 下对应测试；改 `main.py`（注册 story.router）。
- **无新迁移**：`story_bible.style_profile` 列由 3.1 建好，本 story 只写值。
- architecture.md:406 曾建议 `services/story_service.py`（设定+文风锚点合并）；但本 story 遵循**代码库实际的「按 Agent 职责拆 service」模式**（explorer_agent / free_explorer_agent 各一文件），新建 `style_anchor_agent.py` 承文风抽取职责，与既有先例一致，不合并。设定生成/编辑/确认（3.3/3.4/3.5）届时各自建 service。

### 上游依赖状态（均已就绪）

- `story_bible` 表 + `style_profile` 列：Story 3.1（done），迁移 head `ffa52c6a4e27`。
- LLMProvider 抽象 + factory + MeteredProvider 记账：Story 2.1（done）。
- check_quota 护栏：Story 1.8（done），2.1/2.3/2.6 已多次真实消费。
- `get_owned_project` / `_exploration_not_found`：Story 1.5 / 2.2（done）。

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-3.2]（AC 原文，679-705）
- [Source: _bmad-output/planning-artifacts/epics.md#Epic-3]（依赖 3.1→3.2→…、3.3 消费 3.2 style_profile，647-653）
- [Source: _bmad-output/planning-artifacts/epics.md#FR16]（文风锚点独有卖点，62）
- [Source: _bmad-output/planning-artifacts/epics.md#Story-4.1]（盲测消费 style_profile，跨 epic 依赖，809）
- [Source: _bmad-output/planning-artifacts/architecture.md#焦点二-文风锚定机制]（203-217：样本锚点/五维抽取/写作注入/验收挂钩）
- [Source: _bmad-output/planning-artifacts/architecture.md#AR15]（文风锚定机制，129/212）
- [Source: _bmad-output/implementation-artifacts/3-1-story_bible表落地12字段schema-clean-room.md]（story_bible 表结构、style_profile 列、待确认项 2/3）
- [Source: backend/src/muse/services/free_explorer_agent.py]（extract_clues 抽取范式：独立 session/check_quota/provider.chat/固定前缀/防御性解析）
- [Source: backend/src/muse/services/explorer_agent.py]（LLM service 分层、护栏、session 生命周期陷阱⑩）
- [Source: backend/src/muse/providers/base.py + factory.py]（LLMProvider 抽象、get_provider_for_user、禁直调 openai 陷阱①）
- [Source: backend/src/muse/repositories/project_repo.py]（get_owned_project 二义合一租户守卫）
- [Source: backend/src/muse/repositories/story_clue_repo.py]（一表一文件 repo 范式）
- [Source: backend/src/muse/schemas/base.py + exploration.py]（CamelModel、_NonBlankText 文本约束）
- [Source: backend/src/muse/routers/exploration.py]（router 分层、同步端点 refresh_clues 范式）
- [Source: backend/src/muse/models/story_bible.py]（style_profile 列语义）
- [Source: prototype/app/app.js:1890-2330]（文风锚点页前端契约、五维 profile、3 样本 id）
- [Source: 记忆 project_muse_quality_redline]（NFR1 去 AI 味红线、风格锚定验收判据）
- [Source: 记忆 project_muse_setting_fields]（12 字段决策、style_profile 独有）
- [Source: 记忆 muse_local_dev_env]（uv / Colima / MUSE_DB_READY=1）
- [Source: 记忆 feedback_design_decision_delegation]（分歧点有先例可依时授权自主选最优）

## 待确认项（本 story 完成后交创始人/PM 裁定，不阻塞开发）

1. **【schema 形态】style_profile 存 Text vs JSONB**：本 story 按 V1 全文原则存结构化文本（五维多行）。若 Epic 4 drafter 注入需按维度结构化读取/拼装写作任务书，可能改 JSONB（承 3.1 待确认项 3）。请在 Epic 4 drafter 实现前确认。
2. **【半成品行】3.2 提前建 story_bible 行的影响**：本 story 为落 style_profile 提前 get-or-create story_bible 行（主干列空串占位）。3.3 生成候选卡时须妥善处理「已存在仅含 style_profile 的行」（update 而非重复 insert）。建议 3.3 开发前对齐 story_bible 的候选/确认状态模型（3.1 待确认项 2「revision/status 列归属」一并裁定）。
3. **【sampleId 契约】预置样本库单一事实源**：本 story 建议后端做样本库事实源（GET samples 端点）。若前端坚持用常量库，须保证前后端样本 id/原文不漂移——请在前端集成切片确认归属。
4. **【NFR7 合规硬门禁】**：承 3.1——webnovel-writer GPL 许可证义务评估仍是项目级未决门禁（本 story 的 style_profile 是 Muse 独有、webnovel-writer 无此字段，clean-room 风险较低，但项目级评估仍须创始人完成）。

## Dev Agent Record

### Agent Model Used

Claude-Opus-4.8-joybuilder[1M]（dev-story 工作流）

### Debug Log References

- `uv run python -c "from muse.main import app"` → app 装配 OK，story.router 注册成功，3 样本 id 对齐原型（cold-rain/warm-dusk/sharp-first）。
- schema 互斥校验手测：id-only / text-only 通过；both / none / <20字 均 422。
- `uv run pytest tests/test_style_anchor.py -k "schema or parse or resolve or extract or without_token or expired"` → 20 passed（离线，无 DB）。
- `MUSE_DB_READY=1 MUSE_REDIS_READY=1 uv run pytest tests/test_style_anchor.py -q` → 33 passed。
- `MUSE_DB_READY=1 MUSE_REDIS_READY=1 uv run pytest -q` → 269 passed, 2 skipped（DeepSeek 真实契约用例无 key 正常跳过），零回归（3.1 基线 236 → +33 本 story 新增）。
- `uv run ruff check`（新增/改动文件）→ All checks passed。

### Completion Notes List

- **Task 1+3**：新建 `services/style_anchor_agent.py`。`STYLE_SAMPLE_LIBRARY` 3 样本（id 对齐原型，各含较完整原文 text 供真实抽取，excerpt 供前端卡片展示）。`extract_and_anchor_style` 照 `free_explorer_agent.extract_clues` 范式：独立 `async_session_maker()` 自管 session（陷阱⑩）、租户守卫 → check_quota（provider 前）→ `get_provider_for_user`（MeteredProvider，禁直调 openai）→ `provider.chat`（快档 deepseek-v4-flash，max_tokens=1024）→ 五维「标签：内容」防御性解析 → `upsert_style_profile` + commit。空产（无有效维度）抛 generate_failed 不落库。**不加 mode 守卫**（受控决策 4：文风锚点作品级、两模式均可锚定）。
- **Task 2**：新建 `repositories/story_bible_repo.py`——`get_by_project`（(user_id,project_id) 同一 where 二义合一，仿 get_owned_project）+ `upsert_style_profile`（get-or-create，仅写 style_profile 一列、不覆盖其余字段；不 commit；flush 后 refresh 回填时间戳避免 MissingGreenlet，仿 story_clue_repo.update_clue）。
- **Task 4**：新建 `schemas/story.py`（`StyleAnchorRequest` sampleId/sampleText 互斥 model_validator、`_SampleText` min20/max4000；`StyleProfileResponse`；`StyleSampleResponse`）+ `routers/story.py`（GET samples 全局样本库、POST style-anchor 预检+resolve+抽取，非流式）+ `main.py` 注册 story.router。
- **Task 5**：新建 `tests/test_style_anchor.py` 33 用例——schema 6、解析/resolve 7、编排单元 5（happy/护栏/租户/空产/prompt 契约）、repo DB 4（建行/更新不撞唯一/不覆盖其余字段/租户隔离）、鉴权 3、端到端 API 8（samples/happy 库选+粘贴落库/422×2/未知id 400/429/越权+不存在 404）。
- **边界严守**：只交付样本库+抽取+upsert style_profile 一列+schema/router+测试；未写 revision/status、未做卡生成/编辑/确认（3.3/3.4/3.5）、未接前端（受控决策 A defer）、未碰 drafter 注入（Epic 4）。
- **无新迁移**：style_profile 列 3.1 已建，本 story 只写值。
- **未决门禁提醒**：4 项待确认项（style_profile Text vs JSONB、半成品行对 3.3 影响、样本库事实源归属、NFR7 GPL 门禁）已登记，交创始人/PM 裁定。

### File List

- `backend/src/muse/services/style_anchor_agent.py`（新增）
- `backend/src/muse/repositories/story_bible_repo.py`（新增）
- `backend/src/muse/schemas/story.py`（新增）
- `backend/src/muse/routers/story.py`（新增）
- `backend/src/muse/main.py`（修改：注册 story.router）
- `backend/tests/test_style_anchor.py`（新增）

### Change Log

- 2026-07-29：实现 Story 3.2——文风锚点预置样本库 + style_profile 真实 LLM 抽取（五维）+ upsert 到 story_bible.style_profile + API（GET samples / POST style-anchor）+ 33 测试；全量 269 通过、零回归。
- 2026-07-29：code review 修复 3 项 patch——① `upsert_style_profile` 竞态兜底（IntegrityError→rollback→重查转 UPDATE，照 enter_exploration 先例）；② `resolve_sample_text` assert 改显式 raise（去 -O 依赖）；③ schema `sample_id` strip 归一化（修带空白合法 id 误 400）。补 3 测试（竞态兜底 / sampleId 归一 / 超长 422 假覆盖）；全量 272 通过、零回归。1 项 defer（provider.chat 上游异常映射 500 → deferred-work.md，跨 story 共性）。

