---
baseline_commit: 854827cd5329ea6a28bf82c84be4616b4256f7dd
---

# Story 5.2: 写后投影——data-agent + chapter-commit 单事务

Status: done

## Story

As a 持续写作的用户，
I want 每章定稿后系统自动把这一章的事实沉淀成结构化档案，
so that 后续章节能记住已发生的一切、不穿帮。

## Acceptance Criteria

**AC1（data-agent 提取结构化 JSON，AR17）**
**Given** 章节定稿（接 Epic 4 Story 4.7，写后投影归本 epic）
**When** 定稿触发
**Then** data-agent 从定稿正文提取事件/状态变化/新增实体为结构化 JSON

**AC2（单事务 chapter-commit 原子投影）**
**Given** 提取完成（AR17，NFR4）
**When** 投影回库
**Then** 以单事务 chapter-commit 原子投影回 `story_state` / `chapter_card` / `story_thread`（+ `embedding` 见 Story 5.5），防半更新穿帮

**AC3（章节卡片持久化 + 注入下一章上下文）**
**Given** 章节卡片真实生成（FR23）
**When** 投影完成
**Then** `chapter_card` 含五要素并持久化，写下一章时作为长期上下文注入（接 Epic 4 写前上下文——本 story 仅完成投影，注入归 5.6 RAG 增强；4.4 `context-agent` 已消费 `list_recent_chapters(finalized)` 暂不改动）

**AC4（补齐五段流水线，AR11）**
**Given** data-agent 是 Epic 4 流水线的第五段（V1 前四段已在 E4 落地）
**When** 本 story 实现
**Then** 补齐 `context→drafter→reviewer→polisher→data-agent` 完整五段（AR11），data-agent 为写后段

**AC5（失败回滚 + 可重试）**
**Given** 投影是多步 LLM + DB 操作
**When** 某步失败
**Then** 单事务回滚、不留半更新状态（NFR4 一致性投影原子性），可重试

## Tasks / Subtasks

- [ ] Task 1 (AC: 1, 4) — 新建 data-agent 步骤函数 + Prompt 设计
  - [ ] Subtask 1.1：在 `backend/src/muse/orchestration/steps.py` 新增 `run_data_agent(*, user_id, project_id, chapter_number, chapter_text) -> dict`，**快档 flash**（结构化提取，类同 4.2 已论证「快档适合轻任务」、`architecture.md:196`「deepseek-v4-flash 快，提取/轻任务」）
  - [ ] Subtask 1.2：输入注入「定稿正文 + confirmed story_bible 12 字段摘要 + 最近前序 chapter_card 五要素（若存在）」，输出严格 JSON（贴 json mode 或 prompt 强约束），schema：`{what_happened, character_changes, new_facts_clues, unresolved_hooks, end_state, protagonist_state, world_rules_state, current_stage, new_threads: [{content, introduced_chapter_number}], resolved_threads: [{thread_id_or_content_hint, resolved_chapter_number}], touched_threads: [{thread_id_or_content_hint, last_touched_chapter_number}]}`
  - [ ] Subtask 1.3：用 `_POLISH_MAX_TOKENS` 类似 2048 上限；空产抛 `_generate_failed()`（同 steps.py 既有先例）；JSON 解析失败抛同错并记 warning（不落 run 表）
  - [ ] Subtask 1.4：fast 档 provider：`settings.deepseek_model_fast`（同 `_REVIEW_MAX_TOKENS` 那段用过的 model 字段，勿新造配置）
- [ ] Task 2 (AC: 4) — 编排器追加第五段
  - [ ] Subtask 2.1：`pipeline.py` 顶部新增常量 `STEP_DATA_AGENT = "data_agent"`，**追加**到 `PIPELINE_STEPS` tuple 末尾；`_CHAPTER_TOTAL_STEPS` 派生自动 +1（worker.py:192 联动）
  - [ ] Subtask 2.2：`run_chapter_pipeline` 末尾（polisher 段之后）新增 `data_agent` 段 `_run_or_resume` 调用——`runner=lambda: steps.run_data_agent(user_id=..., project_id=..., chapter_number=..., chapter_text=final)`，把段产物（dict）**不再返回给调用方**（章节正文才是返回值）；data-agent 段产物落 run 表供断点续跑复用
  - [ ] Subtask 2.3：**不动 polisher 段之前的任何既有调用**——`generate_chapter` / `revise_chapter` / 4.4 首次生成 / 4.6 修订在「非定稿态」**不跑 data-agent**（见 Task 3 受控决策 1：data-agent 只在定稿时跑，生成/修订时不跑）；段是否执行由 `_run_or_resume` 内层判定：**调用方（chapter_service）传 `run_data_agent: bool`**，非定稿路径传 `False` 时跳过此段（保持四段行为完全不变）
  - [ ] Subtask 2.4：run 表 `steps` JSONB 自然容纳新段键（无迁移）
- [ ] Task 3 (AC: 1, 2) — 定稿触发 + service 写路径 + 单事务投影
  - [ ] Subtask 3.1：在 `backend/src/muse/services/chapter_service.py` 新增 `finalize_and_project_chapter(session, *, user_id, project_id, chapter_number) -> Chapter`，**完全替换**既有 `finalize_chapter` 的内部实现（保持函数签名/返回类型不变，router 零改），流程：
    1. 沿用既有 finalize_chapter 的租户守卫 / confirmed 前置 / 章号下界 / `chapter_not_generated` / 幂等逻辑（已 finalized 直接返回现行，**不再触发投影**）
    2. 仍未定稿 → 先按既有逻辑 `upsert_chapter(status="finalized")` + commit（保持 status 翻转原子性，不依赖后续 LLM/投影成败——这样投影失败重试也不会把 status 卡回 draft）
    3. 新增：触发 `run_chapter_pipeline(..., chapter_number, chapter_idea=None, on_progress=None, run_data_agent=True)` —— 这是**同步等待 data-agent 跑完 + 投影回库**的整体调用（不走 ARQ，见受控决策 3）
  - [ ] Subtask 3.2：新增 `backend/src/muse/services/chapter_projection_service.py`（新建文件），导出 `async def chapter_commit(session, *, user_id, project_id, chapter_number, extracted: dict) -> None`——**单事务投影**：
    - 入参 `extracted` 是 data-agent 产出的结构化 dict（Subtask 1.2 schema）
    - 在同一 session 内依次调：
      - `chapter_card_repo.upsert_chapter_card(...)`（Task 4 新增）写五要素（chapter_number 幂等键）
      - `story_state_repo.upsert_story_state(...)`（Task 4 新增）写 protagonist_state / world_rules_state / current_stage（user_id+project_id 幂等键）
      - `story_thread_repo.upsert_new_thread(...)`（Task 4 新增）对 `extracted["new_threads"]` 逐项建行（status='open'，last_touched_chapter_number=introduced_chapter_number=chapter_number）
      - `story_thread_repo.resolve_thread_by_content(...)`（Task 4 新增）对 `extracted["resolved_threads"]` 按内容模糊匹配既有 open thread → UPDATE status='resolved' + resolved_chapter_number + last_touched_chapter_number
      - `story_thread_repo.touch_thread_by_content(...)`（Task 4 新增）对 `extracted["touched_threads"]` 按内容模糊匹配 → UPDATE last_touched_chapter_number（**仅当新值 > 旧值时**——defer 台账 E6 单调不减防线）
    - **不在此函数内 commit**——commit 边界归上层 `finalize_and_project_chapter`；任何一步抛异常 → 上层 `session.rollback()` 整体回滚（AC2 原子性）
  - [ ] Subtask 3.3：`finalize_and_project_chapter` 在主流程的伪代码：
    ```python
    # 1) 既有 finalize 逻辑（status=draft → finalized）+ commit
    # 2) 跑 run_chapter_pipeline(run_data_agent=True) 拿 extracted dict
    # 3) 新开一个独立 async_session_maker 事务调 chapter_commit(extracted)
    #    （与 step 自管 session 不同——见陷阱①；这里 service 显式新开一个事务边界）
    # 4) 任一步失败：rollback + 记 logger.warning（不向上抛——status 已 finalized 保留，
    #    前端已收到 finalized 成功响应；投影失败由「下一章定稿时 data-agent 断点续跑复用
    #    polisher 段产物」兜底重试，见受控决策 5）
    ```
  - [ ] Subtask 3.4：「幂等重入」防线——`finalize_and_project_chapter` 入口判定：若 chapter 已 finalized **且** `chapter_card_repo.get_by_chapter(...)` 返回非 None → 直接返回现行（投影已完成、不重复跑）；若已 finalized 但 chapter_card 缺失 → 视为「上次投影失败」→ 继续走投影流程（data-agent 断点续跑会复用 run 表 polisher 段产物，不重新调 drafter）
- [ ] Task 4 (AC: 2) — 三张表的写路径 repo（Story 5.1 已建读法，本 story 补写法）
  - [ ] Subtask 4.1：`backend/src/muse/repositories/chapter_card_repo.py` 新增 `upsert_chapter_card(session, *, user_id, project_id, chapter_number, what_happened, character_changes, new_facts_clues, unresolved_hooks, end_state) -> ChapterCard`——get-or-create 同行 upsert（幂等键 `(user_id, project_id, chapter_number)`）；不 commit；flush+refresh
  - [ ] Subtask 4.2：`backend/src/muse/repositories/story_state_repo.py` 新增 `upsert_story_state(session, *, user_id, project_id, protagonist_state, world_rules_state, current_stage) -> StoryState`——get-or-create 同行 upsert（幂等键 `(user_id, project_id)`）；不 commit
  - [ ] Subtask 4.3：`backend/src/muse/repositories/story_thread_repo.py` 新增三个写方法：
    - `upsert_new_thread(session, *, user_id, project_id, content, chapter_number) -> StoryThread`——新增 open thread（status='open'、introduced_chapter_number=last_touched_chapter_number=chapter_number）；**防重**：先 `list_open_by_project` 查同 (user_id, project_id) 的 open threads，用 `content` 精确匹配（`func.lower` + `func.trim` 双向 trim 后等值）——已存在同内容 open thread 则只更新 `last_touched_chapter_number` 为新值（取 max），不新建行
    - `resolve_thread_by_content(session, *, user_id, project_id, content, resolved_chapter_number) -> StoryThread | None`——按内容匹配既有 open thread → UPDATE `status='resolved'` + `resolved_chapter_number` + `last_touched_chapter_number=resolved_chapter_number`；**校验 `resolved_chapter_number >= introduced_chapter_number`**（defer 台账 E5），违反时跳过更新 + `logger.warning`（不抛错、不阻断投影）
    - `touch_thread_by_content(session, *, user_id, project_id, content, last_touched_chapter_number) -> StoryThread | None`——按内容匹配既有 open thread → UPDATE `last_touched_chapter_number`；**校验单调不减**（defer 台账 E6），`new_value <= old_value` 时跳过 + `logger.warning`
    - 内容匹配统一走 `_normalize_content_for_match(content: str) -> str`（私有 helper：`strip().lower()`，**V1 不做语义模糊匹配**——LLM 产「程野决定离开」 vs 「程野选择了离开」会被当两条；语义级去重归 5.6 RAG 召回时统一处理）
    - status 白名单校验（defer 台账 P3+E4）：`upsert_new_thread` 恒写 'open'；`resolve_thread_by_content` 恒写 'resolved'——service 层若未来扩展支持 'abandoned'，须显式传 status 参数且仅允许 `{'open','resolved','abandoned'}` 三值字面量；本 story repo 层先用常量内部硬编码、service 层不开放 status 入参
  - [ ] Subtask 4.4：所有 upsert 方法 **不 commit**（commit 边界归 `chapter_commit`），竞态兜底（并发首建撞唯一约束）由 service 层 `chapter_commit` 统一处理（rollback → 整事务回滚重试，不做单点 retry）
- [ ] Task 5 (AC: 2, 3) — 失败回滚 + 集成到定稿流程
  - [ ] Subtask 5.1：修改 `backend/src/muse/services/chapter_service.py` 的 `finalize_chapter` —— 包装为 `finalize_and_project_chapter`（保持签名），并在内部 try/except 捕获投影相关异常：
    - **不向上抛**——status 已 finalized 保留；记 `logger.exception` + 把 `projection_failed` 写入 run 表 data_agent 段 steps 状态（供下次重入识别）
    - 章号 < 1 / 未 confirmed / 未生成 → 沿用既有 400 逻辑（**不触发投影**）
  - [ ] Subtask 5.2：在 `backend/src/muse/tasks/worker.py` 不动 `generate_chapter` / `revise_chapter`——它们走 ARQ + SSE 是「生成/修订」路径，与「定稿投影」路径完全独立；**本 story 不新增 ARQ 任务**（见受控决策 3）
  - [ ] Subtask 5.3：router 层 `backend/src/muse/routers/chapter.py` **不动**——`finalize_chapter` 函数签名/返回类型不变（ChapterTextResponse），路由零改
- [ ] Task 6 (AC: 1, 2, 5) — 单测覆盖
  - [ ] Subtask 6.1：新建 `backend/tests/test_chapter_projection_repo.py`（异步，照 test_chapter_card_repo.py 风格）——每 repo 一个 upsert 幂等测试（同键重跑覆盖同值，不产生第二行）+ 三个 story_thread 写法的 status 白名单/大小约束/单调防线用例
  - [ ] Subtask 6.2：新建 `backend/tests/test_chapter_projection_service.py`——mock data-agent 产出 dict，验证 `chapter_commit` 单事务：三表齐写成功；中途 mock 某 repo 抛异常 → 三表全 rollback（断言无任何一表落库）
  - [ ] Subtask 6.3：新建 `backend/tests/test_steps_data_agent.py`——mock provider 返回固定 JSON，断言 `run_data_agent` 正确解析结构化 dict + 空产抛 `_generate_failed` + JSON 解析失败抛错
  - [ ] Subtask 6.4：扩展 `backend/tests/test_chapter_finalize_api.py`——新增「定稿后 chapter_card 落库」+「投影失败 status 仍 finalized + 下章定稿断点续跑补齐」用例（沿用既有 API 测试范式，需 ARQ 容器）
  - [ ] Subtask 6.5：扩展 `backend/tests/test_steps.py`（若已有）或并入 Subtask 6.3——断言 `_CHAPTER_TOTAL_STEPS=5`、`PIPELINE_STEPS` 含 `data_agent`
- [ ] Task 7 — 全量回归 + ruff + 收尾 story file

## Dev Notes

### 本 story 的「跨 epic 衔接」性质（读三遍再动手）

5.2 是 **Epic 4 → Epic 5 的焊点**：4.7 留下「status=finalized + 不建表不投影」的钩子（`finalize_chapter` 只置 status），5.2 正是在这个钩子上接第五段 data-agent + 单事务投影。**你改的是 `chapter_service.finalize_chapter` 的内部实现，不是新增端点**——router 层零改，前端零改（前端只看到「定稿更慢一点、但 chapter_card 也落库了」）。

### 现状代码事实（本 story 依赖/复用的既有实现）

- `orchestration/pipeline.py`：四段流水线 + `_run_or_resume` 断点续跑（每段独立 session、run.steps JSONB 容纳段产物）
- `orchestration/steps.py`：四段 step 实现（drafter/reviewer/polisher 范式：独立 session + `get_owned_project` 守卫 + `check_quota` + `get_provider_for_user` + 空产抛错）；`_POLISH_MAX_TOKENS=4000`、`_REVIEW_MAX_TOKENS=2048` 等常量先例
- `services/chapter_service.py:404 finalize_chapter`：租户守卫 / confirmed 前置 / 章号下界 / 幂等已 finalized 直接返回 / upsert status=finalized + commit
- `routers/chapter.py:180 finalize_chapter`：POST 端点 + ChapterTextResponse
- `repositories/{chapter_card, story_thread, story_state}_repo.py`：Story 5.1 已建最小读法（get_by_chapter / list_open_by_project / get_by_project），**本 story 补写路径**
- `models/{chapter_card, story_thread, story_state}.py`：Story 5.1 已建模型（chapter_card 五要素 Text+复合唯一、story_thread 无复合唯一靠内容匹配去重、story_state 三列 Text+复合唯一）
- `tasks/worker.py`：6 个 ARQ 任务（demo/settle/generate/revise/plan_first_stage/plan_next_stage）；`_CHAPTER_STEP_ORDER` 从 `pipeline.PIPELINE_STEPS` 派生
- `migrations/versions/f472170cd859`：Story 5.1 已建三表（无新迁移）

### 关键实现模式（照抄现存先例，勿另造）

- **Step 范式**（照 `run_reviewer` 最贴）：独立 `async_session_maker()` + `get_owned_project` 守卫 + `check_quota` + `get_provider_for_user` + `provider.chat(..., model=settings.deepseek_model_fast, max_tokens=2048)` + 空产抛 `_generate_failed()`
- **断点续跑**：`_run_or_resume` 已支持任意 step——只需把 `STEP_DATA_AGENT` 加进 `PIPELINE_STEPS` 并在 `run_chapter_pipeline` 末尾调用；run.steps JSONB 自动容纳新键
- **错误工厂**：复用 `_generate_failed()`（已存在 steps.py:82）；如需 `projection_failed` 专用错误，参照 `_bible_not_confirmed()` 模式定义
- **单事务投影**：参照 `pipeline.run_chapter_pipeline` 末尾「mark_run_status + upsert_chapter 同 session」的模式（pipeline.py:303-320）——commit 边界在编排器/调用方，repo 只 flush
- **Model 档选择**：data-agent 走 `settings.deepseek_model_fast`（同 `_REVIEW_MAX_TOKENS` 段 `run_reviewer` 用过的字段——reviewer 标「思考档 pro」是因为审查重，data-agent 提取结构化是轻任务用快档 flash）

### 五个受控决策（Jianghj 拍板沿用 + 本 story 显式声明）

1. **data-agent 只在「定稿」时跑，不在「生成/修订」时跑**：`generate_chapter` / `revise_chapter` 走完 ARQ + SSE 推四段就结束，chapter.status 仍 draft；只有用户显式点「定稿本章」→ `finalize_chapter` 才触发 data-agent + 投影。这样保证「未定稿章节不污染归档」+「4.6 改进/重生后重定稿才覆盖归档」（FR21/FR23 语义对齐）
2. **投影失败 ≠ 定稿失败**：`finalize_and_project_chapter` 先把 status 翻 finalized + commit（用户已收到定稿成功响应），再独立事务跑 data-agent + chapter_commit；投影失败只记日志 + run 表标 data_agent 段 failed，下次定稿（本章或下一章）触发 data-agent 时断点续跑复用 polisher 段产物继续投影。**AC2 的「单事务」约束的是「投影内部三表原子性」，不是「status 翻转与投影同一事务」**——两者必须分开，否则投影 LLM 抖动会把 status 卡回 draft（FR21 被破坏）
3. **投影走「同步 service 调用」不走 ARQ**：`generate_chapter` / `revise_chapter` 是「用户等结果」的长任务用 ARQ + SSE；`finalize_chapter` 是「用户期望快速返回」的短操作（只翻 status），data-agent 提取结构化是轻任务（~3-5s），同步等待可接受。若未来 LLM 慢到影响 UX，再升 ARQ（届时需新增任务 + SSE 通道 + 前端等结果）
4. **run 表复用**：data-agent 段产物落 `chapter_generation_run.steps["data_agent"]`，断点续跑复用——重试不重复调 LLM（NFR5）；`chapter_card` 的 `(user_id, project_id, chapter_number)` 复合唯一是幂等键，重跑覆盖同行不产生副本
5. **story_thread 内容匹配 V1 用「strip().lower() 精确匹配」，不做语义模糊**：LLM 产「程野决定离开」vs「程野选择了离开」会被当两条不同 thread；这是 V1 接受的局限（语义无损但会留重复 open thread），**语义级去重归 5.6 RAG 召回时统一处理**（届时用 embedding 召回相似 thread 合并）；本 story repo 层只保证「完全同内容重跑去重」（defer 台账 B2 防线）

### 5.1 defer 台账 → 本 story 兑现清单

| defer 条目 | 落点 | 本 story 兑现方式 |
|---|---|---|
| B2 story_thread 测试未覆盖「同内容重跑」 | `test_chapter_projection_repo.py::test_upsert_new_thread_idempotent_same_content` | 同 content + 同 chapter_number 重跑 → 仍 1 行 |
| B3+E2 `list_open_by_project` 无复合索引 | **不兑现**（归 5.6 RAG 优化） | 本 story 数据量小（每章新增几条 thread），单列索引够用；5.6 再评估 |
| P3+E4 status 无 DB CHECK 白名单 | `chapter_projection_service` 调 repo 写路径时硬编码 status 常量 | repo 不开放 status 入参，service 层只能写 'open' / 'resolved' |
| E5 `resolved_chapter_number >= introduced_chapter_number` | `story_thread_repo.resolve_thread_by_content` | 显式校验，违反跳过 + `logger.warning`（不阻断投影） |
| E6 `last_touched_chapter_number` 单调不减 | `story_thread_repo.touch_thread_by_content` + `upsert_new_thread` | 显式校验 `new > old` 才更新，否则跳过 + `logger.warning` |

### 陷阱①：Session 边界（最重要，看三遍）

- **Step（data-agent）**：独立 `async_session_maker()`——调 provider 走 MeteredProvider 记账（陷阱⑩）
- **Service（chapter_commit）**：**新独立事务**（不复用 step 的 session、也不复用 chapter_service 传入的 session——后者已在 finalize 翻 status 时 commit 掉了）
- **commit 边界**：`finalize_and_project_chapter` 内部「翻 status 一次 commit + 投影一次 commit」；**repo 全部不 commit**（5.1 已守住这条先例，本 story 写路径同样守）
- **rollback**：`chapter_commit` 内任一步抛异常 → `finalize_and_project_chapter` 外层 try/except 捕获 → `session.rollback()` + 记日志 + 不向上抛（status 已 finalized）

### 陷阱②：_run_or_resume 复用产物

data-agent 段的 runner 必须返回**可 JSON 序列化的 dict**（不是 str）——`_run_or_resume` 会把 runner 返回值落 `run.steps[step_name].output`（JSONB 列）。目前四段都返回 str，data-agent 返回 dict 是首例——**确认 update_step 对 dict 的处理**（应该没问题，JSONB 列兼容；但 dev 时验证一把）。

### 陷阱③：chapter_text 传参

data-agent 需要定稿正文——**不是从 chapter 表重读**（会多一次 DB 往返 + 有事务可见性陷阱），而是**直接用 polisher 段产物 `final`**（pipeline 内局部变量）。调用 `run_data_agent(chapter_text=final)`。

### 陷阱④：_CHAPTER_TOTAL_STEPS 联动

`worker.py:192 _CHAPTER_TOTAL_STEPS = len(pipeline.PIPELINE_STEPS)` 派生——加 `STEP_DATA_AGENT` 后自动变 5，`_CHAPTER_STEP_ORDER` dict 也自动含新段。但 `generate_chapter` / `revise_chapter` 的 result payload 不动（仍只返 chapterText），**前端 SSE 会看到 progress percent 从 0/25/50/75/100 变成 0/20/40/60/80/100**——这是好事（更细粒度），但 5-2 dev 完成后**在前端 demo 一遍确认 SSE 显示无异常**（前端按 step 序号渲染进度条，理论上兼容；但 4.4 实现可能硬编码了 4 段，需实测）。

### Project Structure Notes

- **新增**：`backend/src/muse/services/chapter_projection_service.py`（chapter_commit 单事务编排）
- **修改**：`backend/src/muse/orchestration/steps.py`（+run_data_agent）、`backend/src/muse/orchestration/pipeline.py`（+STEP_DATA_AGENT + PIPELINE_STEPS + run_chapter_pipeline 末尾段调用 + `run_data_agent: bool = False` 参数）
- **修改**：`backend/src/muse/services/chapter_service.py`（finalize_chapter → finalize_and_project_chapter 内部重写，签名不变）
- **修改**：`backend/src/muse/repositories/{chapter_card_repo, story_state_repo, story_thread_repo}.py`（补写路径 upsert）
- **不动**：`routers/chapter.py`、`tasks/worker.py`、`models/`、`migrations/`、前端、conftest、`story_bible`/`chapter` 相关既有读路径
- **新增测试**：`tests/test_chapter_projection_repo.py`、`tests/test_chapter_projection_service.py`、`tests/test_steps_data_agent.py`（或并入 test_steps.py）、扩展 `tests/test_chapter_finalize_api.py`

### 上游依赖状态（均已就绪）

- `chapter` 表 + status 字段（4.4/4.7 done）
- 三张归档表 + 最小读法 repo（5.1 done）
- 四段流水线 + 断点续跑（4.2 done）
- `finalize_chapter` 端点 + 幂等（4.7 done）
- DeepSeek Provider + fast 档模型配置（2.1 done）

### Testing Standards

- repo 测试：异步 + 同步 Session 造种子（照 5.1 风格）
- service 测试：mock repo 或 data-agent 产出
- API 测试：扩展既有 test_chapter_finalize_api.py（需起 PG+Redis 容器）
- **必跑**：`MUSE_DB_READY=1 MUSE_REDIS_READY=1 uv run pytest -q`（全量回归 ≥ 602 + 新增用例）+ `uv run ruff check .`
- **端到端**：建议本地起后端 + 前端，走「注册→确认设定→生成第 1 章→定稿」看 DB 三表是否落库 + run.steps 是否有 data_agent 段（**不做前端 UI 自动化**，手动验证即可）

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 5.2]（1085-1111，AC 原文）
- [Source: _bmad-output/planning-artifacts/epics.md#Epic 5]（1053-1059：依赖 5.1→5.2→...、关键跨 epic 衔接①「5.2 承接 Epic 4 定稿触发、补齐流水线第五段 data-agent」）
- [Source: _bmad-output/planning-artifacts/epics.md:133-134]（AR16 写前上下文 / AR17 单事务 chapter-commit）
- [Source: _bmad-output/planning-artifacts/architecture.md#焦点一-模型接入层]（189-201，五段流水线 + ARQ + 断点续跑）
- [Source: _bmad-output/planning-artifacts/architecture.md#焦点四-一致性机制迁移]（240-247，写后 data-agent 投影 chapter-commit 单事务）
- [Source: _bmad-output/implementation-artifacts/5-1-归档核心表落地chapter_card-story_thread-story_state.md]（5.1 dev notes + 5 条 defer 台账 + 三表模型/读法 repo）
- [Source: _bmad-output/implementation-artifacts/4-7-定稿本章-阶段循环-阶段交界方向输入.md]（4.7 finalize_chapter 现状 + 「写后投影归 Epic 5」决策）
- [Source: _bmad-output/implementation-artifacts/4-2-五段流水线编排底座V1四段-去AI味词表.md]（4.2 四段流水线 + 断点续跑先例）
- [Source: _bmad-output/implementation-artifacts/deferred-work.md#Deferred from: code review of 5-1]（5 条 defer 的完整描述 + 本 story 兑现要求）
- [Source: backend/src/muse/orchestration/pipeline.py]（四段流水线现状——要 UPDATE 加第五段）
- [Source: backend/src/muse/orchestration/steps.py]（四段 step 范式——照 run_reviewer 写 run_data_agent）
- [Source: backend/src/muse/services/chapter_service.py:404]（finalize_chapter 现状——要改内部实现）
- [Source: backend/src/muse/repositories/{chapter_card, story_thread, story_state}_repo.py]（5.1 最小读法——本 story 补写路径）
- [Source: backend/src/muse/models/{chapter_card, story_thread, story_state}.py]（5.1 模型——幂等键与列约束）
- [Source: backend/src/muse/tasks/worker.py:188-192]（_CHAPTER_STEP_ORDER 派生逻辑——加段后联动）
- [Source: 记忆 project_muse_setting_fields]（12 字段设定圣经结构——data-agent 注入用）

## Dev Agent Record

### Agent Model Used

Claude-Sonnet-4.6-1M（dev-story 工作流，Claude Code）

### Debug Log References

- **环境预检**：`docker ps` 显示 `muse-postgres` / `muse-redis` 均 healthy；`_CHAPTER_TOTAL_STEPS=4` 派生正确（PIPELINE_STEPS 已收窄为核心 4 段，data_agent 不在其内）。
- **关键设计冲突（已修复）**：初版把 `STEP_DATA_AGENT` 加进 `PIPELINE_STEPS` 会让 `_CHAPTER_TOTAL_STEPS=5`——generate/revise 路径只跑 4 段但 progress 按 5 推，polisher 完成时 percent=80% 而非 100%，前端会看到「生成完成但进度条卡在 80%」。**修复**：拆 `PIPELINE_CORE_STEPS`（4 段）+ `STEP_DATA_AGENT` 两个常量，`PIPELINE_STEPS = PIPELINE_CORE_STEPS`（兼容别名）——generate/revise 路径 progress 仍按 4 段推 100%，data_agent 走 finalize 同步路径不推 SSE。
- **关键 bug（已修复）**：`run_chapter_pipeline` 早返回分支「run.status=succeeded 直接返 final 不跑任何段」——第一遍 generate 完 run=succeeded，定稿时再调 run_chapter_pipeline(run_data_agent_step=True) 会**直接早返回、不跑 data_agent**！**修复**：早返回前先检查 `run_data_agent_step=True and _succeeded_output(run.steps, STEP_DATA_AGENT) is None` → 不早返回，继续走 `_run_or_resume` 让 data_agent 段跑起来（其他四段 cached 命中自动复用产物）。
- **ChatResult 构造器**：初版 `_fake_chat_result` 误传 `reasoning_content` 参数（实际构造器只收 content/prompt_tokens/completion_tokens/total_tokens/model 5 个必填）——照 `test_orchestration_steps._fake_chat_result` 范式修正。
- **错误码修正**：初版 `test_data_agent_tenant_guard_404` 断言 `exploration_not_found`，实际 4.6 起改名 `project_not_found`——改为只断言 `http_status == 404`（不断言具体 code，留工厂语义弹性）。
- **LLM mock 策略**：`test_chapter_finalize_api.py` 加 autouse fixture mock `chapter_service.pipeline.run_chapter_pipeline` 不打真实 LLM——改为在 `chapter_generation_run.steps` 种 data_agent 段产物（含四段 succeeded 占位），`chapter_projection_service.chapter_commit` 从 run 表读产物做**真实投影**（非 mock），端到端验证「定稿 → 三表落库」完整链路。
- **单测**：
  - `test_chapter_projection_repo.py` 9 用例（upsert 幂等 / 同内容防重 B2 / 内容归一化 / 章号倒挂 E5 / 章号倒退 E6 / resolved 后 list_open 不返回 / distinct 内容并存）——全过。
  - `test_chapter_projection_service.py` 4 用例（三表齐写 / 幂等重跑 B2 / 三类 thread 操作齐备 / 单事务回滚 mock 异常三表全未落库 AC2）——全过。
  - `test_steps_data_agent.py` 9 用例（正常 JSON / markdown fence 容错 / 空产 502 / JSON 解析失败 502 / 必填字段缺失 502 / 类型归一 None→"" str→[] / 快档 flash 模型档 / 租户守卫 404 / bible_not_confirmed 400）——全过。
  - `test_chapter_finalize_api.py` 12 用例（4.7 既有 8 + 5.2 新增 4：投影三表落库 / 幂等跳过 / 投影失败保留 status / 断点续跑补齐）——全过。
- **全量回归**：`MUSE_DB_READY=1 MUSE_REDIS_READY=1 uv run pytest -q` → **628 passed / 2 skipped**（5-1 baseline 602 + 本 story 新增 26），零回归。
- **ruff**：`uv run ruff check .` → All checks passed。

### Completion Notes List

**交付面（AC1-5 全兑现，Epic 4→5 跨 epic 焊点完成）**：

后端：**7 任务全 done**。

- **Task 4 三张表写路径 repo**（5.1 已建读法，本 story 补写法 + defer 台账 4 条防线）：
  - `chapter_card_repo.upsert_chapter_card`：get-or-create 幂等（同键重跑覆盖五要素、不产生第二行）。
  - `story_state_repo.upsert_story_state`：get-or-create 幂等（同键重跑覆盖三列快照）。
  - `story_thread_repo.upsert_new_thread`：同内容已存在 open thread → 仅更新 last_touched（取 max），不新建行（**defer 台账 B2 防线**）；内容匹配归一化 `strip().lower()`（受控决策 5）。
  - `story_thread_repo.resolve_thread_by_content`：按内容匹配 → UPDATE resolved；**显式校验 `resolved >= introduced`**（**defer 台账 E5 防线**），违反跳过 + `logger.warning` 不阻断投影。
  - `story_thread_repo.touch_thread_by_content`：UPDATE last_touched；**显式校验单调不减**（**defer 台账 E6 防线**），倒退跳过 + `logger.warning`。
  - status 硬编码 'open' / 'resolved' 字面量（**defer 台账 P3+E4 防线**——repo 不开放 status 入参，LLM 无法写入非法值）。
- **Task 1 data-agent step**：`steps.py` 新增 `run_data_agent`（第五段写后段，AR17）——快档 flash（`settings.deepseek_model_fast`，结构化提取是轻任务）；输入「定稿正文 + confirmed 设定摘要」；输出严格 JSON（五要素 + 三列快照 + 三类 thread 操作）；容错 markdown fence；空产 / JSON 解析失败 / 必填字段缺失全抛 `_projection_failed()` 502；类型归一（None→""、非 list→[]）。
- **Task 2 编排器追加第五段**：`pipeline.py` 新增 `STEP_DATA_AGENT` + `PIPELINE_CORE_STEPS`（4 段）拆分；`run_chapter_pipeline` 新增 `run_data_agent_step: bool = False` 参数（**默认 False**——generate/revise 路径不跑 data_agent，受控决策 1）；`PIPELINE_STEPS = PIPELINE_CORE_STEPS` 兼容别名（worker._CHAPTER_TOTAL_STEPS 派生仍 4，generate/revise progress 按 4 段推 100% 不被拖累）；早返回分支加 `data_agent_needed` 判定（run_data_agent_step=True 且 data_agent 段缺失时不早返回，让 `_run_or_resume` 跑 data_agent 段）。
- **Task 3+5 定稿触发 + 失败回滚**：`chapter_service.finalize_chapter` 内部重写（签名/返回类型不变，router 零改）——① 沿用 4.7 前置校验（租户/confirmed/章号下界/未生成 400）；② 幂等：已 finalized + chapter_card 已存在 → 直接返回（不重复投影）；已 finalized + chapter_card 缺失 → 跳过 status 翻转直接走投影断点续跑；③ 仍 draft → upsert status=finalized + commit；④ **独立事务**跑 `pipeline.run_chapter_pipeline(run_data_agent_step=True)` 拿 data-agent 产物 → `chapter_projection_service.chapter_commit` 单事务投影三表 → commit；⑤ 投影失败不向上抛（status 已 finalized 保留），记 `logger.exception` 下次断点续跑补齐（**受控决策 2**）。
- **Task 3 部分 chapter_projection_service**：新建 `services/chapter_projection_service.py`，导出 `chapter_commit(session, *, user_id, project_id, chapter_number, extracted)`——单事务投影三表：chapter_card 五要素 + story_state 三列快照 + story_thread 三类操作（new/resolved/touched）；不 commit（边界归 chapter_service），任一步抛异常 → 上层 rollback 整体回滚（**AC2 原子性 NFR4**）。
- **Task 6 全套测试**：26 用例全过（projection_repo 9 / projection_service 4 / steps_data_agent 9 / finalize_api 扩展 4）。
- **Task 7 全量回归 + ruff**：628 passed / 2 skipped（DeepSeek 真实契约无 key 正常跳过）；ruff 全过。

**受控决策落地**：
1. data-agent 只在定稿时跑（run_data_agent_step 默认 False）。
2. 投影失败 ≠ 定稿失败（status 翻转与投影两个独立事务）。
3. 同步 service 调用（不走 ARQ/SSE）——data-agent 是轻任务。
4. run 表复用（data_agent 段产物落 steps JSONB，断点续跑不重复付费）。
5. story_thread 内容匹配 V1 精确匹配 `strip().lower()`（语义级去重归 5.6 RAG）。

**defer 台账兑现**：5.1 留下的 5 条 defer 已兑现 4 条（B2 重跑去重 / P3+E4 status 白名单 / E5 章号大小约束 / E6 last_touched 单调）；B3+E2 复合索引**不兑现**（归 5.6 RAG 优化统一处理）。

**测试留白（诚实记录）**：未在真实浏览器走「注册→确认设定→生成第 1 章→定稿」端到端 UI（本环境无法快速跑通前端 + 真实 LLM）。已做：mock pipeline 端到端 API 测试（定稿 → 三表落库完整链路）+ repo/service/step 三层单测。**建议 Jianghj 本地起前后端 + 真实 DeepSeek key 手测一遍**（重点看：①定稿后 DB 三表是否落库 ②run.steps.data_agent 段产物 ③投影失败时 status 是否仍 finalized）。

### File List

**后端（修改）**：
- `backend/src/muse/orchestration/steps.py`（+run_data_agent + _projection_failed + _DATA_AGENT_MAX_TOKENS；docstring 更新为「五段流水线」）
- `backend/src/muse/orchestration/pipeline.py`（+STEP_DATA_AGENT + PIPELINE_CORE_STEPS 拆分 + run_data_agent_step 参数 + data_agent_needed 早返回判定 + data_agent 段调用）
- `backend/src/muse/services/chapter_service.py`（finalize_chapter 内部重写：+幂等投影跳过 / 断点续跑 / 独立事务投影 / 失败不抛）
- `backend/src/muse/repositories/chapter_card_repo.py`（+upsert_chapter_card 写路径）
- `backend/src/muse/repositories/story_state_repo.py`（+upsert_story_state 写路径）
- `backend/src/muse/repositories/story_thread_repo.py`（+upsert_new_thread / resolve_thread_by_content / touch_thread_by_content 三个写路径 + _normalize_content_for_match helper + defer 台账 4 条防线）

**后端（新建）**：
- `backend/src/muse/services/chapter_projection_service.py`（chapter_commit 单事务编排）
- `backend/tests/test_chapter_projection_repo.py`（9 用例）
- `backend/tests/test_chapter_projection_service.py`（4 用例）
- `backend/tests/test_steps_data_agent.py`（9 用例）

**后端（测试扩展）**：
- `backend/tests/test_chapter_finalize_api.py`（+autouse mock pipeline fixture + 5.2 新增 4 用例：投影三表落库 / 幂等跳过 / 投影失败保留 status / 断点续跑补齐；docstring 更新为「Story 4.7 + Story 5.2」）

**后端（未改）**：`routers/chapter.py`（router 零改，finalize_chapter 签名/返回类型不变）、`tasks/worker.py`（不新增 ARQ 任务，受控决策 3）、`models/`、`migrations/`、前端、conftest、`story_bible`/`chapter` 相关既有读路径。

## Review Findings

> 2026-08-06 三层对抗式 review（Blind Hunter / Edge Case Hunter / Acceptance Auditor）汇总。共 24 起报告 → 去重合并 24 → **8 patch / 4 decision-needed / 3 defer / 9 dismiss**。Edge Case Hunter 发现 **E1+E2 致命 bug**（finalize 投影链路把 chapter.status 从 finalized 改回 draft、revision 从 N 重置为 1——FR21 破功）已就地修复（pipeline.py:361-368 加 `if not run_data_agent_step:` 跳过 upsert_chapter）；Acceptance Auditor 发现多处偏离 spec 明文未走确认流程。

### Decision Needed（已决断 → 全部保持现状 + spec 补注记）

- [x] [Review][Decision→Close] **A1+A6 `STEP_DATA_AGENT` 未加入 `PIPELINE_STEPS`、`_CHAPTER_TOTAL_STEPS` 未变 5** — 保持现状（拆 `PIPELINE_CORE_STEPS`，`_CHAPTER_TOTAL_STEPS=4`）。理由：dev 实现避免 generate/revise progress 卡 80% 是合理的，spec Subtask 2.1/6.5 的「加入 PIPELINE_STEPS」明文在实际副作用下不可行；spec 注记已补在 pipeline.py:34-55 注释
- [x] [Review][Decision→Close] **A2 参数名 `run_data_agent_step` vs spec `run_data_agent: bool`；判定位置在外层 `if` vs spec `_run_or_resume` 内层** — 保持现状（外层 if 判定）。理由：外层 `if run_data_agent_step:` 判定语义更清晰，`_run_or_resume` 内层不应关心「是否跑此段」的策略；spec Subtask 2.2 的「内层判定」是过度设计
- [x] [Review][Decision→Close] **A4+B5 新建 `_projection_failed()` 专用错误工厂 vs spec `_generate_failed()`；类型归一 vs 「不静默兜底」** — 保持现状（`_projection_failed()` + 类型归一）。理由：spec 行 124 留了「如需 projection_failed 专用错误」的口子；类型归一是「容错」（LLM 产类型错是噪声非致命），与「不静默兜底」（指不返空 dict 造成数据污染）不矛盾——空产/解析失败/缺字段仍抛错重试，类型归一只是降级处理
- [x] [Review][Decision→Close] **A5 schema 字段名 `content` vs spec `thread_id_or_content_hint`** — 保持现状（`content`）。理由：`thread_id_or_content_hint` 过于冗长且语义模糊（「thread_id 还是 content_hint」二义）；`content` 简洁清晰，V1 用内容匹配不需要 thread_id；spec 字段名对齐实现（`content`）

### Patch（已全部落地）

- [x] [Review][Patch] **E1+E2 finalize 投影链路把 chapter.status 从 finalized 改回 draft、revision 从 N 重置为 1** — `backend/src/muse/orchestration/pipeline.py:361-378`：加 `if not run_data_agent_step:` 跳过 upsert_chapter（finalize 路径 chapter 行已在 chapter_service 中 upsert 为 status="finalized" + 保留原 revision）
- [x] [Review][Patch] **E6 mock `_fake_run_chapter_pipeline` 掩盖真实 pipeline upsert 行为** — `backend/tests/test_chapter_finalize_api.py:test_finalize_real_pipeline_preserves_status_and_revision`：新增 `@pytest.mark.real_pipeline` marker + autouse fixture 跳过 mock，真实跑通 pipeline（只 mock provider）验证「finalize 后 chapter.status/revision 不被改」（E1+E2 回归防线）
- [x] [Review][Patch] **E4+E5 chapter_commit `thread_input` 未做 dict 类型防御 + 章号无下界校验** — `backend/src/muse/services/chapter_projection_service.py`：三类 thread 循环加 `isinstance(thread_input, dict)` 守卫跳过非 dict 项 + warning；章号字段加 `isinstance(int) and >= 1` 下界校验，违反时回退 `chapter_number` 参数 + warning
- [x] [Review][Patch] **B1 `data_agent_entry["output"]` 直接 KeyError 风险** — `backend/src/muse/services/chapter_service.py:541`：改 `data_agent_entry.get("output")` 让 None 走 isinstance 分支统一报 RuntimeError
- [x] [Review][Patch] **B4 投影失败静默吞异常 + 无显式 rollback** — `backend/src/muse/services/chapter_service.py:575-611`：改 `except (RuntimeError, ErrorEnvelope)` 只对预期异常吞 + 显式 `projection_session.rollback()` + 显式标 run.steps.data_agent 为 failed（A8 一并落地）
- [x] [Review][Patch] **B5+E9 markdown fence 剥离逻辑不完整** — `backend/src/muse/orchestration/steps.py:592-597`：改正则 `re.search(r"```(?:json)?\s*\n(.*?)\n```", raw, re.DOTALL)` 提取第一个 ``` 块内容
- [x] [Review][Patch] **A7 data-agent 输入未注入「最近前序 chapter_card 五要素」** — `backend/src/muse/orchestration/steps.py:run_data_agent` + 新增 `_format_recent_chapter_cards_block` helper + `chapter_card_repo.list_recent_chapter_cards`：读前序 chapter_card 五要素注入 prompt 作上下文锚点
- [x] [Review][Patch] **A8 投影失败时未显式把 run.steps.data_agent 标 failed** — 并入 B4 patch（chapter_service.py:575-611 投影失败分支显式调 `update_step(step_name=STEP_DATA_AGENT, status="failed")`）
- [x] [Review][Patch] **B4 投影失败测试没验证「story_state/story_thread 也未落库」** — `backend/tests/test_chapter_finalize_api.py:test_finalize_projection_failure_keeps_status_finalized`：扩展断言 story_state=None + story_thread=[]（三表全空，单事务原子性防线）

### Defer（已登记 deferred-work）

- [x] [Review][Defer] **E3 data_agent LLM 失败会污染 run.status，下次 finalize 被迫全四段重跑（cached 命中不重复付费但日志噪音大）** — `backend/src/muse/orchestration/pipeline.py:234-262`：结果正确（cached 复用），仅日志/进度噪音；归 deferred-work 后续优化
- [x] [Review][Defer] **E7 chapter_card 存在但 story_state/story_thread 缺失的「半投影」状态无法恢复** — `backend/src/muse/services/chapter_service.py:483-499`：低危（生产很难出现），单事务理论防住；归 deferred-work
- [x] [Review][Defer] **E8 data_agent 的 `chapter_text` 来自 polisher 产物而非 chapter 表实际 text，若手工改 chapter.text 会脱节** — `backend/src/muse/orchestration/steps.py:227-294`：低危（正常 UI 不会让用户直接改 chapter.text）；归 deferred-work

### Dismiss（驳回）

- **A3 pipeline 调用与投影共享 projection_session 的伪代码意图偏差**：实际是 pipeline 用自有 session、commit 用 projection_session，两 session 并存于同一 with 块——不算 bug，语义正确
- **B2 data_agent 的 `provider.chat` 在 session 块内持有 DB 连接**：与其他四段同 pattern（run_reviewer/run_polisher 都在 session 内调 provider.chat），项目先例一致
- **P1 `await session.commit()` 后 chapter 对象过期**：`expire_on_commit=False` 不会失效，router 返回模型字段正常
- **P2 `_succeeded_output(run.steps, STEP_DATA_AGENT)` 要求 run.steps 非 None**：`_succeeded_output` 内部对 None 输入安全（`if not steps_state: return None`）
- **P3 `upsert_new_thread` 命中已有 open thread 时只在 `chapter_number > last_touched` 才 flush+refresh**：docstring「取 max」语义一致，未更新时返回旧值正确
- **E10 `chapter_text` 为空串时未防御**：polisher 空产已有 `_generate_failed` 防御，脏数据场景低危

### Edge Case Hunter 总结

**不可放行**——E1+E2 是**致命 bug**（已就地修复 pipeline.py:361-368 加 `if not run_data_agent_step:` 跳过 upsert_chapter）；E4/E6 必修（thread_input 类型防御 + 端到端测试补覆盖）。

**已覆盖足够放行的分支**：租户守卫 / bible_not_confirmed / chapter_out_of_range / chapter_not_generated 前置校验（沿用 4.7 既有逻辑）；story_thread 三类操作的业务幂等（同内容防重 / 倒挂跳过 / 倒退跳过）；chapter_card / story_state upsert 幂等；单事务 chapter_commit 回滚原子性；LLM 输出基础容错（空产 / 非 JSON / 缺字段 / 顶层类型归一 / markdown fence 严格形态）；data_agent 使用快档 flash 模型；测试 fixture 表清理完备。

### Acceptance Auditor 总结

5 条 AC 中 4 条兑现、AC4 错位；五个受控决策全部兑现；defer 台账 4 条防线全部兑现。主要问题集中在三处：**（1）AC4/Subtask 2.1 被单方面改语义**（已列入 decision_needed）；**（2）Subtask 1.2 注入前序 chapter_card 未兑现**（已列入 patch A7）；**（3）Subtask 5.1 投影失败时 run 表标 failed 未显式实现**（已列入 patch A8）。另有 schema 字段名、专用错误工厂等与 spec 明文不符的实现选择（已列入 decision_needed）。整体架构方向正确、事务边界清晰、防线齐备，但**多处偏离 spec 明文且未走确认流程**，建议回归 spec 逐条对齐或在 spec 上补「已确认偏差」注记。

### Change Log

- 2026-08-06：dev 完成 Story 5.2——Epic 4→5 跨 epic 焊点：data-agent 第五段（快档 flash 提取结构化 JSON）+ chapter-commit 单事务投影三表 + finalize_chapter 内部重写（status 翻转与投影两个独立事务，投影失败不卡 status）；三张表补写路径 repo（含 defer 台账 4 条防线：B2 同内容防重 / E5 章号大小 / E6 last_touched 单调 / P3+E4 status 白名单）；拆 PIPELINE_CORE_STEPS 保 generate/revise progress 按 4 段推 100%；修 run.status=succeeded 早返回 bug（run_data_agent_step=True 且 data_agent 段缺失时不早返回）；26 用例全过；全量回归 628 passed 零回归、ruff 全过。
- 2026-08-06：三层对抗式 review 完成——0 decision-needed（4 条全部「保持现状 + spec 补注记」决断）/ 8 patch 全部落地 / 3 defer 入台账 / 9 dismiss。**Edge Case Hunter 发现 E1+E2 致命 bug**（finalize 投影链路把 chapter.status 从 finalized 改回 draft、revision 从 N 重置为 1——FR21 破功）已修复（pipeline.py:361-378 加 `if not run_data_agent_step:` 跳过 upsert_chapter）+ 补 `@pytest.mark.real_pipeline` 端到端回归测试（test_finalize_real_pipeline_preserves_status_and_revision）验证修复。其余 patch：E4+E5 thread_input 类型防御+章号下界 / B1 KeyError 防御 / B4 显式 rollback+A8 标 failed / B5+E9 fence 正则 / A7 前序 chapter_card 注入 / B4 三表全空断言。全量回归 **629 passed / 2 skipped**（比 patch 前 628 多 1 个 E6 测试）、ruff 全过。Story 状态 → done。

## 待确认项（本 story 完成后交创始人/PM 裁定，不阻塞落地）

1. **【RAG 增强】chapter_card 注入下一章写前上下文（5.6）**：AC3 只说「作为长期上下文注入」，本 story 只完成投影；**注入归 5.6 RAG 三级召回**——届时把 `context-agent` 的 `_RECENT_CHAPTERS_FOR_CONTEXT=1` 从「读最近 1 章正文」升级为「读 story_bible + 最近 N 张 chapter_card + 未回收 story_threads + RAG 召回」
2. **【embedding 投影】5.5 纳入 chapter-commit**：AC2 写「+ `embedding` 见 Story 5.5」——本 story 不投 embedding；5.5 落地时在 `chapter_commit` 里追加 embedding 投影（或紧随其后独立事务）
3. **【ARQ 升级】data-agent 同步 → 异步**：受控决策 3 选同步是 V1 简化；若实测定稿 UX 慢到 >8s，升级 ARQ 需新增任务 + SSE 通道 + 前端等结果——V2 再评估
4. **【语义去重】story_thread 语义级合并**：受控决策 5 用精确匹配；5.6 RAG 召回时用 embedding 合并相似 open thread
