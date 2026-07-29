---
baseline_commit: ae14ef9
---
# Story 3.4: 设定候选卡编辑 + 反馈升版本（真实 Agent）

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a 拿到候选设定卡的用户，
I want 直接编辑字段、或让 Agent 按我的反馈调整并看到版本变化，
so that 我能把设定打磨到满意再定稿。

## Acceptance Criteria

> **本 story = 把 3.3 的 emit-only 候选卡「落到后端持久化」，并在其上补三件事：① 字段直接编辑（无 LLM 同步 PATCH）；② 反馈→真实同一探索 Agent 重凝练升版本（有 LLM，同步 REST）；③ 待确认卡刷新/断线可恢复。** 3.3 受控决策 1 是 emit-only（候选卡只经 SSE result 返回、不写 story_bible、SSE snapshot TTL 1h 后消失，deferred-work.md:176）；**本 story 是 3.1/3.2/3.3 反复 defer 的「待确认项 2（revision/status 列归属）」的落地点**——须先裁定候选卡如何落库（见受控决策 1），再实现编辑/反馈/恢复。后端 only（延续 1.7→3.3 一路受控决策 A：`app.js` 零改动、前端接线 defer 到「探索前端集成切片」）。

1. **[候选卡持久化 = story_bible 加 status/revision/changed_fields 列]** 引入设定卡的「待确认（pending）vs 已确认（confirmed）」状态与版本号：`story_bible` 表**加 3 列**——`status`（`Text NOT NULL server_default='pending'`）、`revision`（`Integer NOT NULL server_default='1'`）、`changed_fields`（`JSONB NULL`，存本轮变化字段名列表）。3.3 的 settle 凝练产物**从 emit-only 改为落库**：settle 完成时 upsert 一行 `status='pending', revision=1` 的待确认卡（含 12 字段 + 3.2 已写的 style_profile）。[Source: epics.md#Story-3.4 AC5（759-761）；3-1 story#待确认项 2（149）；3-2 story#待确认项 2（166）；deferred-work.md:176（3.3 emit-only 下游交接）；受控决策 1]
2. **[字段直接编辑 → 同步持久化]** 用户在待确认卡直接编辑某字段（原型 contenteditable，app.js:547 `data-final-profile-field`），该字段值更新并**持久化到待确认卡**（原型 `data-final-profile-field` input→persist，app.js:671-676）。后端提供**无 LLM 的同步 PATCH 端点**改单个/多个字段值，只写 `status='pending'` 的行、`revision` 不变（直接编辑非「Agent 升版本」）。租户守卫 404、mode 无关（设定阶段作品级，同 3.2 style-anchor 不加 mode 守卫）。[Source: epics.md#Story-3.4 AC1（743-745）；FR13（178）；3-2 story#受控决策 4（不加 mode 守卫）]
3. **[反馈 → 真实同一探索 Agent 升版本]** 用户在「你想调整什么？」填反馈并提交（原型 app.js:558-562），后端**真实调同一探索凝练 Agent**（替代原型关键词匹配 mock `applyStoryProfileFeedback`，app.js:638-668）生成新版本：把「当前候选卡 12 字段 + 用户反馈」喂 LLM 重凝练，`revision` 递增、持久化新卡。经 LLMProvider 抽象（禁直调 openai）、调 provider 前过 `check_quota` 护栏（托管触顶 429、BYOK 短路）、Provider 层自动记账（AR14）。[Source: epics.md#Story-3.4 AC2（747-749）；FR13（178）；3-3 story#story_settle_agent（凝练范式）；受控决策 2（同步 REST）]
4. **[变化项高亮]** 反馈升版本后返回的新卡须标出**本轮变化的字段**（原型 `is-updated` 高亮，app.js:545/`lastProfileChangedFields`）：后端算新旧卡的字段差集写入 `changed_fields`（字段名列表），随卡返回，供前端高亮「Agent 改了哪些」。直接编辑（AC2）不算「Agent 改动」、不写 changed_fields（或清空）。[Source: epics.md#Story-3.4 AC3（751-753）；原型 app.js:689 `lastProfileChangedFields = applyStoryProfileFeedback(...)`]
5. **[处理中状态]** 反馈提交后到新版本返回前，前端能表达「处理中」（原型「调整中…」status，app.js:687/`profileFeedbackStatus`）。**同步 REST 下**：处理中 = HTTP 请求在途（前端 disable 按钮 + 文案），后端**无需**额外「处理中」态字段——请求返回即新版本就绪。[Source: epics.md#Story-3.4 AC4（755-757）；受控决策 2；原型 app.js:686-694 同步 setTimeout 模拟]
6. **[待确认卡真实持久化 + 恢复]** 待确认卡（含 profile / revision / changed_fields）真实持久化到后端（补原型 sessionStorage→后端，app.js:191-203/183-189）；用户编辑/反馈后刷新或断线重连，能**从后端恢复**待确认卡（GET 端点读 `status='pending'` 的行），刷新不回退到探索主界面（原型 pending 恢复逻辑 app.js:980）。确认（3.5）后该行 `status='confirmed'`、GET pending 返回「无待确认卡」。[Source: epics.md#Story-3.4 AC5（759-761）；FR11 延续；原型 app.js:167-172 restoredStoryProfile / 980 mountStoryProfileDialog]

**关于前端渲染契约（原型 `storyProfileDialogMarkup` app.js:539-568）**：候选卡弹卡、头部「Story profile / v{revision}」、字段 `NN / 字段名` 编号、contenteditable 编辑、反馈框、`is-updated` 高亮、确认/回到探索按钮——这是**前端渲染契约**（事实源是原型），前端接线 defer（受控决策 A）。本 story 后端交付**候选卡持久化的数据契约 + 编辑/反馈/恢复 API**；前端接线在「探索前端集成切片」消费，本 story 不改 `app.js`、不回归此渲染契约。

**边界（本 story 不做，归 3.5）**：不做「确认故事设定 → status='confirmed' 只读圣经 + phase 推进」（3.5 AC，epics.md:771-773）、不做「回到探索页面二次确认 → 丢弃待确认卡」（3.5 AC，epics.md:779-781）、不做幕后阶段规划（Epic 4）。本 story 只到「待确认卡可编辑/反馈/恢复」，确认与丢弃的**状态流转**归 3.5——但 AC1 建的 `status` 列 + 恢复端点「confirmed 不返 pending」为 3.5 预留了状态位（3.5 只翻 status，不再动 schema）。

## Tasks / Subtasks

- [x] **Task 1：`story_bible` 加 status/revision/changed_fields 列 + 迁移**（AC: 1）（受控决策 1 落地）
  - [x] 改 `backend/src/muse/models/story_bible.py`：加 3 列（**照现有列注释风格 + server_default 语义**，勿改既有 12 列）：
    - `status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")`——`pending`（待确认候选卡）/ `confirmed`（3.5 确认后的只读圣经）。V1 不加 DB CHECK 约束（同项目既有无枚举 CHECK 先例，billing_path 亦无——deferred-work.md:55；值域由 service 保证）。
    - `revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")`——候选卡版本号，反馈升版本 +1（AC3）。用 `from sqlalchemy import Integer`。
    - `changed_fields: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)`——本轮变化字段名列表（snake_case 列名，如 `["protagonist","main_conflict"]`），供前端 `is-updated` 高亮（AC4）。用 `from sqlalchemy.dialects.postgresql import JSONB`（项目 PG-only，architecture.md）。首版/直接编辑为 NULL 或 `[]`。
  - [x] `cd backend && MUSE_DB_READY=1 uv run alembic revision --autogenerate -m "add story_bible status revision changed_fields"`（down_revision 自动指向当前 head `ffa52c6a4e27`）。
  - [x] 校对生成的迁移：`op.add_column` ×3（**非建表**，本 story 是 alter 既有表）、`server_default` 落在迁移里（保证既有行——3.2 已建的半成品行——回填 `status='pending'`/`revision=1` 不为 NULL）；`downgrade()` 为 `op.drop_column` ×3。补中文注释。
  - [x] `MUSE_DB_READY=1 uv run alembic upgrade head` / `downgrade -1` / `upgrade head` 往返验证可逆；`uv run pytest tests/test_migrations_metadata.py` 绿。
  - [x] **边界**：只加这 3 列，不动既有 12 列、不改唯一约束（仍是 `(user_id, project_id)` 一作品一行——pending 与 confirmed 是同一行的状态流转，不是两行；见受控决策 1 理由）。

- [x] **Task 2：`story_settle_agent` 从 emit-only 改为落库 pending 卡**（AC: 1）
  - [x] 改 `backend/src/muse/services/story_settle_agent.py` `settle_into_profile`：step 8 组装候选卡 dict 后，**新增 upsert 落库**——把 12 字段 + `status='pending'`、`revision=1`、`changed_fields=None` 写入 `story_bible` 行（**复用 3.2 已建的半成品行**：get-or-create，存在则更新 12 字段 + 置 status/revision，不存在则新建）。**关键：不覆盖 3.2 已写的 `style_profile`**——settle 的⑫本就是读 3.2 既有值（受控决策 4，3.3），upsert 时 style_profile 写回同值即可（幂等）。
    - upsert 逻辑放 **`story_bible_repo` 新增方法**（Task 3），service 调用 + `session.commit()`。
    - **竞态兜底**（照 3.2 `extract_and_anchor_style` 的 IntegrityError→rollback→重查转 UPDATE 先例，story_bible_repo 首次并发 insert 撞 `uq_story_bible_user_id_project_id`）：settle 落库若首次 insert 撞唯一约束 → rollback → get_by_project 重查 → 改 UPDATE。**放 service 层**（同 3.2 的兜底放在 extract_and_anchor_style，非 repo）。
  - [x] **改动波及 3.3 的「emit-only」边界注释/docstring**：模块 docstring（story_settle_agent.py:13-16）「emit-only、不写 story_bible」的表述须更新为「3.4 起落库 pending 卡」，Completion Notes 说明这是 3.3→3.4 的受控演进（3.3 defer 给 3.4 的下游交接兑现，deferred-work.md:176）。
  - [x] **worker 端零改动或极小改**：`tasks/worker.py settle_exploration` 仍调 `settle_into_profile` 拿 card dict 推 SSE result（前端接线时用 SSE result 弹卡）——**settle 现在既落库又推 SSE**（落库供恢复、SSE 供即时弹卡）。SSE result payload 形态不变（`{taskId, status:"settle_ready", profile}`）。确认 `settle_into_profile` 返回值签名不变（仍返 card dict），worker 无需改。

- [x] **Task 3：`story_bible_repo` 扩展——pending 卡读写**（AC: 1, 2, 4, 6）
  - [x] 在 `backend/src/muse/repositories/story_bible_repo.py` 新增（**延续既有约定：repo 只 flush/查询、显式 user_id/project_id 租户守卫、不 commit**）：
    - `upsert_profile_card(session, *, user_id, project_id, card: dict[str, str | None], status: str, revision: int, changed_fields: list[str] | None) -> StoryBible`：get-or-create——写 12 字段（含 style_profile）+ status/revision/changed_fields。存在则 UPDATE，不存在则 INSERT（主干缺料空串、特化 None）。**不 commit**、flush 后 refresh（同 `upsert_style_profile` 的 MissingGreenlet 处理）。
    - `get_pending_by_project(session, *, user_id, project_id) -> StoryBible | None`：取 `status='pending'` 的行（AC6 恢复：无 pending 行 / 行是 confirmed → None）。where 带 user_id+project_id+status（租户守卫，二义合一）。
    - `update_card_fields(session, *, user_id, project_id, fields: dict[str, str]) -> StoryBible | None`（AC2 直接编辑）：只更新传入的字段值、`revision` 不变、`changed_fields` 清空或不动；仅作用于 `status='pending'` 行（confirmed 不可编辑，返 None 让 service 转 404/409）。**只允许改 12 内容字段中的 key**（防越权改 status/revision——白名单校验放 service 或 repo，见 Task 4）。**不 commit**。
  - [x] **边界**：repo 不做「确认 status→confirmed」（3.5）、不做丢弃删行（3.5）。本 story repo 只服务 pending 卡的生成落库/读取/字段编辑。

- [x] **Task 4：反馈升版本编排（真实 Agent 重凝练，同步 REST）**（AC: 3, 4, 5）（受控决策 2）
  - [x] 在 `story_settle_agent.py` 新增 `async def revise_profile_card(*, user_id, project_id, feedback: str) -> StoryBible`（**照 `settle_into_profile` / `style_anchor_agent.extract_and_anchor_style` 范式**）：
    1. 独立 `async_session_maker()` 自管 session（陷阱⑩，调 provider）。
    2. 租户守卫（`get_owned_project` → None 抛 `_exploration_not_found` 404）。
    3. 取当前 pending 卡（`get_pending_by_project` → None 抛新 helper `_no_pending_card()` 400/404——无待确认卡不能改，见 Task 5）。
    4. `check_quota`（provider 前，护栏）。
    5. 构造 provider（`get_provider_for_user`，MeteredProvider）→ `provider.chat(_build_revise_messages(current_card, feedback), model=deepseek_model_fast, max_tokens=_MAX_TOKENS)`。
    6. 防御性解析 11 字段（复用 `_parse_settle_response`）；空产守卫（主干全空 → 502 generate_failed）。
    7. **算变化项**：新旧卡逐字段比对（12 字段中值变化的 snake_case 列名列表；⑫ style_profile 不参与重凝练、不算变化）。
    8. upsert 落库：`revision = old.revision + 1`、`status='pending'`、`changed_fields=<变化项列表>`（`upsert_profile_card`）→ `session.commit()`（含竞态兜底，同 Task 2）。
    9. 返回更新后的行。
  - [x] `_build_revise_messages(current_card: dict, feedback: str) -> list[Message]`：system prompt 复用 settle 的「先判 genre + 固定 11 字段格式 + 去 AI 味 + 主角含缺陷/冲突含反派镜像」契约，**user 消息把「当前 12 字段卡 + 用户反馈」结构化拼入**，要求 LLM **在现有卡基础上按反馈调整**（非从零重来）、输出完整 11 字段（未变字段照抄、变的按反馈改）。⑫ style_profile 不进 LLM 输出（读既有值不覆盖，同 settle 受控决策 4）。
  - [x] **变化项算法**：仅对 11 个 LLM 字段 + 主干比对（`old.value != new.value` 收集列名）；style_profile 恒不变不计入。空反馈由 schema 拦（Task 6 非空校验），service 无需再判。

- [x] **Task 5：service helper + 直接编辑编排**（AC: 2, 6）
  - [x] 在 `story_settle_agent.py`（或复用 exploration_service helper 风格）加 `_no_pending_card() -> ErrorEnvelope`：`code="no_pending_card"`, `message="没有待确认的设定卡，请先整理探索内容。"`, `http_status=404`（无 pending 卡时反馈/编辑/恢复的语义——同 `_exploration_not_found` 的 helper 风格；用 404 因「待确认卡不存在」是存在性语义，与 style anchor 的 `_exploration_not_found` 一致）。
  - [x] `async def edit_profile_card(*, user_id, project_id, fields: dict[str, str]) -> StoryBible`（AC2 直接编辑，**无 LLM、无护栏**）：独立 session（一致性；虽无 provider 但保持 service 自管 session 约定，或用请求 session——**dev 判断**：直接编辑无 provider 记账，可用请求注入 session，仿 exploration_service 的 CRUD 端点 save_guided_answer 用请求 session）。租户守卫 → `update_card_fields`（仅 pending 行、仅白名单 12 字段 key）→ commit。字段 key 不在 12 白名单 → 忽略或 422（dev 判断，建议 schema 层用固定字段名 model 拦，见 Task 6）。
  - [x] `async def get_pending_card(*, user_id, project_id) -> StoryBible | None`（AC6 恢复）：租户守卫 → `get_pending_by_project`。返 None 时 router 返 204 或空体 200（dev 判断，见 Task 6）——「无待确认卡」是正常空态、非错误。

- [x] **Task 6：API schema + router**（AC: 2, 3, 4, 5, 6）
  - [x] 在 `schemas/story.py` 新增（复用 `StoryProfileCard` 12 字段契约 + CamelModel）：
    - `StoryProfileCardResponse(CamelModel)`：`StoryProfileCard` 12 字段 + `revision: int` + `changed_fields: list[str] | None`（camelCase `changedFields`）+ `status: str`（可选，前端可据此判 pending/confirmed）。**这是编辑/反馈/恢复三端点的统一响应契约**。或直接给 `StoryProfileCard` 加 `revision/changed_fields/status` 字段（dev 判断，建议新 response 类避免污染 3.3 emit 契约——但 SSE result 若也要带 revision 则统一更好；**倾向扩 `StoryProfileCard` 加 3 字段可选**，SSE result 与 REST 响应共用一个契约，revision=1/changedFields=null 默认省略兼容 3.3）。
    - `ProfileFeedbackRequest(CamelModel)`：`feedback: _NonBlankText`（非空有界，min_length 建议 ≥1、max_length 保守上界拦超长挤爆 prompt，仿 `_SampleText`/exploration schema）。
    - `ProfileCardEditRequest(CamelModel)`：12 内容字段**全可选**（`str | None`，只改传入的）——用固定字段名 model（genre/coreAppeal/.../ 不含 style_profile？**style_profile 用户可否直接编辑**：原型第⑫字段亦 contenteditable，dev 判断——建议**允许编辑 style_profile 文本**，它也是卡的一部分；但反馈重凝练不动它）。model 只暴露 12 内容字段，天然防越权改 status/revision。
  - [x] 在 `routers/story.py` 新增（prefix `/api/projects`，同 style-anchor 分层：router 校验+分发、业务在 service、越权 service 层 404）：
    - `GET /{project_id}/story-profile`（AC6 恢复）：调 `get_pending_card` → 有则 200 + card response、无则 **204 No Content**（或 200 + null，dev 判断，建议 204 表「无待确认卡」）。
    - `PATCH /{project_id}/story-profile`（AC2 直接编辑）：`ProfileCardEditRequest` → `edit_profile_card` → 200 + card response。
    - `POST /{project_id}/story-profile/revise`（AC3 反馈升版本）：`ProfileFeedbackRequest` → 预检租户/护栏（同 style-anchor 的 preflight 范式：router 用请求 session 预检租户 404 + 护栏 429，再调 service 独立 session 重凝练）→ `revise_profile_card` → 200 + card response（含新 revision + changedFields）。
  - [x] **端点命名**：用 `story-profile`（对齐原型「Story profile」语义 + 已有 `style-anchor` 兄弟端点风格），非 `story-bible`（那是 DB 内部名，对外 REST 用领域名）。project_id 非法 UUID 自动 422。
  - [x] router 无需改 `main.py`（story.router 3.2 已注册）。

- [x] **Task 7：测试**（AC: 1, 2, 3, 4, 5, 6）
  - [x] **迁移/模型测试**（`MUSE_DB_READY=1`，扩 `tests/test_story_bible.py` 或新建）：新 3 列插入默认值（status='pending'/revision=1/changed_fields=NULL）、既有行迁移后回填 default、JSONB 列存取列表。
  - [x] **repo 测试**（`MUSE_DB_READY=1`）：`upsert_profile_card` 首次 insert（12 字段+status/revision）、二次 update 同行不撞唯一约束、`get_pending_by_project`（pending 返行 / confirmed 返 None / 无行 None）、`update_card_fields`（改字段值 revision 不变、仅作用 pending 行、白名单外 key 不生效）。
  - [x] **service 测试**（mock provider，同 3.3 `test_story_settle.py` 范式）：
    - `settle_into_profile` 现落库：settle happy → 落一行 status='pending' revision=1（**扩 test_story_settle.py 既有 happy 用例断言落库**，非只断返回值）；复用 3.2 半成品行（先有 style_profile 行 → settle update 不重复 insert、不覆盖 style_profile）。
    - `revise_profile_card` happy：mock provider 返回改后 11 字段 → revision+1、changed_fields=变化列名、persist。
    - revise 护栏 429（mock check_quota 抛）→ 不调 provider、不改卡。
    - revise 无 pending 卡 → 404 no_pending_card（不调 provider）。
    - revise 空产 502（主干全空）。
    - revise 变化项算法：只有主角变 → changed_fields=["protagonist"]；style_profile 不计入。
    - `edit_profile_card`：改字段值 revision 不变、changed_fields 清空；无 pending 卡 → 404；confirmed 行不可编辑。
    - 租户越权 404（他人 project_id，先于一切）。
  - [x] **端到端 API 测试**（`MUSE_DB_READY=1`，无需 Redis——本 story 三端点均同步 REST 非 ARQ；仅 settle 落库那条若测端到端需 `MUSE_REDIS_READY=1`，但 settle 端到端 3.3 已覆盖，本 story 可只测 service 层落库）：GET 恢复（有 pending 返卡 / 无返 204）、PATCH 编辑落库、POST revise 升版本、schema 校验（空反馈 422、越权 404、护栏 429）。
  - [x] **既有测试零回归**：`test_story_settle.py`（3.3——settle 从 emit-only 改落库后，happy 用例若断言「不写库」须更新为「落 pending 行」；SSE result 形态不变故 worker e2e 不变）、`test_style_anchor.py`（3.2——style_profile upsert 半成品行现被 settle 复用，验证 settle 不覆盖 style_profile）、`test_story_bible.py`（3.1——加列后既有 4 用例须适配新列默认值）、`test_migrations_metadata.py`（加列不影响）。
  - [x] `MUSE_DB_READY=1 MUSE_REDIS_READY=1 uv run pytest` 全量通过零回归；`uv run ruff check src tests` / `uv run mypy src` 全绿（mypy 允许 3.2 基线既有 2 error，本 story 零新增）。

- [x] **Task 8：收尾**（AC: all）
  - [x] `git status prototype/` 为空（`app.js` 零改动，受控决策 A）。
  - [x] **登记 `deferred-work.md`**（新增 3.4 章节，对齐既有「问题+位置+影响+归属批次」格式）：① 候选卡编辑/反馈/恢复前端接线未做，并入「探索前端集成切片」（GET 恢复 → 弹卡、PATCH 编辑 contenteditable、POST revise → 升版本重渲 is-updated 高亮）；② revise 端点零幂等+无限流（承 settle/refresh_clues 一路 defer，接真实 LLM 有成本，归开放注册前加固批次，与 3.3#L174 同批）；③ settle 落库后确认写 status='confirmed'（3.5）/ 回到探索丢弃删 pending 行（3.5）为下游交接；④ 若 Epic 4 drafter 注入需结构化读候选卡，V2 改 JSONB（承 3.1 待确认项 3 / 3.2 待确认项 1）。
  - [x] 更新 `_bmad-output/implementation-artifacts/sprint-status.yaml`：`3-4-设定候选卡编辑-反馈升版本真实Agent` 状态流转 `backlog` → `review`（dev 完成后）。

### Review Findings

_（code review 2026-07-29：Blind Hunter + Edge Case Hunter + Acceptance Auditor 三层并行对抗审查，均派独立子 agent 与实现视角隔离。Acceptance Auditor 判 PASS——6 AC + 4 受控决策全兑现、边界严守（3.5 不越界、app.js 零改动、唯一约束不动）、Completion Notes/File List 诚实。Edge Case Hunter 以真实 repo 访问证伪 4 条假阳性（SessionDep MissingGreenlet / 白名单越权 / worker 需改动 / revise preflight 范式）。1 decision-needed / 1 patch / 1 defer / 6 dismiss。）_

- [x] [Review][Patch] 只锚文风未 settle 的行被当候选卡返回（blind+edge，Med；原 decision-needed，Jianghj 2026-07-29 因转向「前后端一起走」裁定当下修复） — `upsert_style_profile`（3.2，story_bible_repo.py:79-91）建行不写 status → 落 `server_default`；本 story 迁移回填既有半成品行同理。用户「先锚文风、还没 settle」时，`get_pending_by_project` 命中该行 → GET `/story-profile` 返 200 + backbone 全空串的候选卡（应 204）、且该行可被 PATCH/revise（对空卡白烧一次 LLM）。因 Epic 顺序 3.2→3.3 使这是**正常流程可复现**。**✅ 2026-07-29 已修复**：status `server_default` 从 `pending` 改为 `draft`（引入三态 draft→pending→confirmed，见 story_bible.py 注释）；迁移回填默认改 `draft`（既有行都是只锚文风的半成品，标 draft）；settle 落库 `upsert_profile_card` 显式写 `status='pending'` 把 draft 升 pending（同行升态、非新建）；`get_pending_by_project` 语义不变（只认 pending）。新增测试 `test_style_only_draft_row_not_returned_as_pending`（3.2 建的 draft 行 get_pending 返 None）+ `test_settle_upserts_draft_row_to_pending`（settle 升态复用同行、保留 style_profile），改 `test_status_revision_changed_fields_defaults` 断言默认 draft。全量 315 tests 零回归。
- [x] [Review][Patch] revise 全量重写漏字段被静默清空 [backend/src/muse/services/story_settle_agent.py] — revise 组卡原 `card[key]=parsed.get(key,"")`，LLM 重凝练若漏输出某原有主干字段 → 清成空串（特化漏则 None）、原值丢失；空产守卫只在「主干全空」才拦，漏 1 个字段不触发。**✅ 2026-07-29 已修复**：组卡改为「漏字段回退 old_card 原值」——`card[key] = parsed[key] if key in parsed else (old_card.get(key) or "")`（特化同理回退旧值），LLM 漏输出的字段保留原值而非清空；`_compute_changed_fields` 改为比对旧卡与**最终新卡**（已回退），漏字段回退后与旧值相同、不误标为变化。新增测试 `test_revise_missing_field_falls_back_to_old_value`（部分输出 → 漏字段保留原值、只有真改的字段进 changed_fields）。（blind+edge，Med）
- [x] [Review][Defer] 并发 revise 的 revision 丢失更新 [backend/src/muse/services/story_settle_agent.py:746-754] — deferred, pre-existing。竞态兜底 `_persist_card_with_race_guard` 只处理首次 INSERT 的 IntegrityError；已存在行走 UPDATE，两并发 revise 各读同一 old_revision 后都写 +1，last-write-wins 丢一次自增。单用户 + 前端 revise 时 disable 按钮，且项目既有惯例即接受 check-then-act last-write-wins（无乐观锁列，同 1.5/1.7/3.3 一路 defer）。归开放注册/多端并发前加固批次。（blind+edge，Low）

## Dev Notes

### 本 story 的边界（务必守住，勿越界）

- **本 story 交付**：`story_bible` 加 3 列（status/revision/changed_fields）+ 迁移；settle 凝练从 emit-only 改落库 pending 卡；`story_bible_repo` 扩 3 方法（upsert 卡 / 取 pending / 编辑字段）；反馈升版本编排（真实 Agent 重凝练，同步 REST）+ 变化项算法；直接编辑 + 恢复 service + 3 个 REST 端点 + schema + 测试。
- **不做**（归 3.5）：不做「确认 → status='confirmed' 只读圣经 + phase 推进」（epics.md:771-773）、不做「回到探索二次确认 → 丢弃待确认卡」（epics.md:779-781）、不做幕后阶段规划（Epic 4）。本 story 建 `status` 列并让恢复端点「只返 pending」，为 3.5 预留状态位——3.5 只翻 status/删行，不再动 schema。
- **不碰** drafter 注入（Epic 4）、不碰前端（`app.js` 零改动，受控决策 A）。

### 受控决策记录（Jianghj 2026-07-29 已授权分歧点有先例可依时自主选最优，[[feedback_design_decision_delegation]]；本 story 两问再次授权「你选最优」）

1. **候选卡持久化 = `story_bible` 加 status/revision/changed_fields 列（不另建候选态表）**。3.3 emit-only 把「待确认项 2（revision/status 列归属）」defer 到本 story，此处裁定：在 `story_bible` 同一行上用 `status` 表达 pending/confirmed 状态流转、`revision` 表版本、`changed_fields` 表变化项。**理由**：① **复用 3.2 已建的半成品行**——3.2 为落 style_profile 已 get-or-create 了 `(user_id, project_id)` 的 story_bible 行（3-2 story#受控决策 1「半成品行是受控中间态」），settle/编辑/确认都在这一行演进，无跨表 style_profile 搬运、无「候选表→圣经表」拷贝一致性风险；② **一作品一行的唯一约束天然吻合**——`uq_story_bible_user_id_project_id` 已保证一作品至多一行，pending→confirmed 是状态流转不是两行，3.5 确认只 `UPDATE status`（零拷贝、零竞态）；③ **schema 增量最小**——ALTER ADD COLUMN ×3（带 server_default 回填既有行），非新建表 + 迁移双表；④ **3.1/3.2/3.3 已铺垫**——3.1 主干列 `server_default=""` + 特化列 NULL 的半成品语义、3.2 半成品行、3.3 12 字段契约，全为「同一行渐进填充」设计，加 status/revision 是自然收口。**代价/交接**：`story_bible` 行在 confirmed 前是「待确认态」，Epic 4/5 读设定圣经须过滤 `status='confirmed'`（3.5 落地确认后，Epic 4 drafter 注入读 confirmed 行；本 story 恢复端点已示范按 status 过滤）。**另建 draft 表**方案（备选）被否：跨表 style_profile 读写 + 确认时整行拷贝 + 12 字段 schema 两表漂移风险，比加 3 列复杂，无收益。
2. **反馈升版本 = 同步 REST 端点（非 ARQ+SSE）**。反馈重凝练走 `POST /story-profile/revise` 同步端点（provider.chat 一次性重凝练 → 200 带新卡），不引 Redis/worker/SSE。**理由**：① **性质是「一次性结构化重凝练」**——与 3.2 style-anchor 抽取、free/clues/refresh 同类（exploration.py 明写此类同步端点即可），非 settle 那种「多步长时后台生成」；② **处理中态天然由 HTTP 在途表达**（AC5）——同步请求返回即新版本就绪，前端 disable 按钮+文案即「调整中…」，无需 SSE progress、无需额外「处理中」状态字段；③ **避免 ARQ 那套重装**——属主键/幂等/连接池颠簸/max_tries 全是 settle 已 defer 的负担（deferred-work.md 多处），revise 走同步 REST 一概规避；④ **settle 用 ARQ 是因为它是探索收尾的批量触发**（前端点按钮→后台跑→SSE 弹卡），revise 是「已在看卡时的即时调整」，交互形态不同。**代价**：revise 期间 HTTP 连接保持（provider.chat 快档 ~3s，可接受，同 style-anchor）。
3. **直接编辑字段 = 无 LLM 同步 PATCH，revision 不变**。字段直接编辑（contenteditable）是用户手改、非 Agent 生成，故 `PATCH /story-profile` 只写字段值、`revision` 不动、`changed_fields` 不标（那是「Agent 改了哪些」的语义，AC4）。区别于反馈升版本（AC3 才 bump revision + 标变化项）。
4. **⑫ style_profile 在 revise 中不重凝练**（承 3.3 受控决策 4）。反馈升版本只重凝练 11 个 LLM 字段，style_profile 是 3.2 的独立抽取产物，revise 不动它、不计入变化项。用户若要改文风，走 3.2 的 style-anchor 重锚定（或直接编辑该字段文本，AC2）。

### 关键实现模式（照抄现存先例，勿另造）

- **最贴近的落库 + 竞态兜底样板 = `style_anchor_agent.extract_and_anchor_style`（`services/style_anchor_agent.py`）**：独立 session、租户守卫、check_quota 在 provider 前、provider.chat、防御解析、**upsert + commit 包 `try/except IntegrityError → rollback → get_by_project 重查 → 改 UPDATE`**（3-2 story Review Findings patch 1）。本 story 的 settle 落库 + revise 落库照此竞态兜底。
- **最贴近的重凝练样板 = `story_settle_agent.settle_into_profile`（3.3，本 story 同文件）**：`revise_profile_card` 基本是它的「带当前卡 + 反馈」变体——同款独立 session/租户/check_quota/provider.chat/`_parse_settle_response` 防御解析/空产 502/`_build_settle_messages` 的 prompt 契约。复用 `_LLM_FIELDS`/`_BACKBONE_KEYS`/`_MAX_TOKENS`/`_parse_settle_response`/`_normalize_label` 常量与 helper（勿重造）。
- **同步 REST + 预检范式 = `routers/story.py` 的 `anchor_style`（3.2）**：router 先用请求 session `preflight_*`（租户 404 + 护栏 429）→ 再调 service 独立 session 自管抽取。revise 端点照此（预检 + service 独立 session 重凝练）。
- **无 LLM 同步 CRUD 范式 = `exploration_service.save_guided_answer`/`edit_clue`（2.4/2.6）**：租户守卫 → repo upsert/update → commit，用请求注入 session（无 provider 记账，无需独立 session）。`edit_profile_card` 照此。
- **Provider 抽象**：只依赖 `providers/base.LLMProvider`，经 `providers/factory.get_provider_for_user(session, user_id, project_id=...)` 构造 MeteredProvider——**禁直 new / 直调 openai**（陷阱①硬卡点）。model 用 `settings.deepseek_model_fast`（"deepseek-v4-flash"，settings.py:76）。
- **护栏**：`services/usage_service.check_quota(session, user_id)` 必须在 provider 调用**之前**（承 2.1/3.2/3.3 范式）。托管触顶抛 429、BYOK 短路。**仅 revise（有 LLM）过护栏**；直接编辑/恢复无 LLM 不过护栏。
- **租户守卫**：`repositories/project_repo.get_owned_project(session, project_id, user_id)` → None 抛 `exploration_service._exploration_not_found()`（404 二义合一，NFR3）。勿新造、勿返 403。
- **repo 范式**：`story_bible_repo`（3.2 建）现有 `get_by_project`/`upsert_style_profile`——本 story 加的方法同款：kwargs-only user_id/project_id、显式租户 where、不 commit、flush 后 refresh（MissingGreenlet 处理，仿 `upsert_style_profile`）。
- **schema 范式**：`schemas/base.CamelModel`（snake_case↔camelCase 唯一转换点，AR4）；`schemas/story.py` 已有 `StoryProfileCard`（12 字段）+ `_SampleText` 文本约束——复用/仿造。

### story_bible 加列后的字段全景（本 story 交付）

| 列 | 类型 | 语义 | 本 story 写入点 |
| --- | --- | --- | --- |
| 12 内容字段 | Text（主干 NOT NULL ""）/（特化+style NULL） | 3.1 建、3.2 写 style_profile、3.3 契约 | settle 落库 / revise 升版本 / 直接编辑（前 11 内容字段 + 可选 style_profile） |
| `status` | Text NOT NULL default 'pending' | pending（待确认卡）/ confirmed（3.5 只读圣经） | settle 落 'pending'；3.5 翻 'confirmed'（本 story 不做，预留） |
| `revision` | Integer NOT NULL default 1 | 候选卡版本号 | settle=1；revise +1；直接编辑不变 |
| `changed_fields` | JSONB NULL | 本轮变化字段名列表（snake_case 列名） | revise 写变化项；settle/直接编辑 NULL/[] |

> `genre` 仍是判别列（决定⑧⑨⑩⑪激活，FR12）。一作品一行（`uq_story_bible_user_id_project_id`），pending→confirmed 状态流转不产生第二行。

### session 生命周期（陷阱⑩，务必遵循）

- **revise（有 provider 记账）**：用独立 `async_session_maker()` 自管 session（同 settle/extract_clues/extract_and_anchor_style）——MeteredProvider finally 兜底记账须落存活 session。
- **直接编辑 / 恢复（无 provider）**：可用请求注入 session（同 exploration_service CRUD 端点），无记账无需独立 session。dev 保持一致即可。

### 前端契约（原型已是事实源，前端接线 defer）

- 候选卡弹卡：原型 `storyProfileDialogMarkup`（app.js:539-568，**已核对当前原型**）——头部「Story profile / v{revision}」（app.js:554）、字段 `NN / 字段名` 编号（app.js:546）、`contenteditable` 字段 `data-final-profile-field`（app.js:547，AC2 编辑）、反馈框 `data-profile-feedback`（app.js:558，AC3）、`is-updated` 高亮（app.js:545 读 `lastProfileChangedFields`，AC4）、确认 `data-confirm-profile`/回到探索 `data-request-profile-return`（app.js:563，归 3.5）。
- 待确认卡持久化/恢复：原型用 sessionStorage（`persistPendingStoryProfile` app.js:191-203 / `readPendingStoryProfile` app.js:183-189 / 进页 `mountStoryProfileDialog` app.js:980）——本 story 补后端持久化（story_bible pending 行）+ GET 恢复端点，前端接线切片把 sessionStorage 换成后端。
- 反馈升版本原型 mock：`applyStoryProfileFeedback`（app.js:638-668，关键词匹配 changed set + bump revision）——本 story 用真实 Agent 重凝练替代，前端接线时 `POST revise` 拿新卡渲染。
- **本 story 不接线、不改 `app.js`**——归「探索前端集成切片」（deferred-work.md 已登记，本 story 追加 3.4 接线项）。

### 上游依赖状态（均已就绪）

- `story_bible` 表 + 12 列 + style_profile：Story 3.1（表，done，迁移 head `ffa52c6a4e27`）+ 3.2（style_profile 写入 + 半成品行 + `story_bible_repo` get/upsert，done）。
- 12 字段凝练 + `StoryProfileCard` 契约 + `story_settle_agent`：Story 3.3（done）——本 story 在其上加落库 + revise。
- LLMProvider + factory + MeteredProvider 记账：Story 2.1（done）。`check_quota` 护栏：Story 1.8（done），2.1/2.3/2.6/3.2/3.3 已多次真实消费。
- settle 触发端点 + worker `settle_exploration` + SSE 消费：Story 2.5/2.7/3.3（done）。
- 竞态兜底先例：`style_anchor_agent.extract_and_anchor_style`（3.2 Review patch 1，done）。

### Testing standards

- service 测试 **mock provider**（不打真实 LLM，同 explorer/free/style/settle 既有测试）；`MUSE_DB_READY=1` 用于需真实 DB 的 repo/迁移/落库测试；本 story 三端点同步 REST 不涉 Redis（settle 落库端到端 3.3 已覆盖）。
- 迁移可见性门禁 `tests/test_migrations_metadata.py`：本 story ALTER 加列不新增表，门禁天然覆盖、无需改。
- 参照 `backend/tests/test_story_settle.py`（3.3 service+worker 范式）、`test_style_anchor.py`（3.2 service+repo+端到端 + 竞态兜底范式）、`test_story_bible.py`（3.1 模型/约束）；conftest 的 TRUNCATE...CASCADE 隔离，勿改 conftest。

### Project Structure Notes

- 改：`models/story_bible.py`（加 3 列）、`services/story_settle_agent.py`（settle 落库 + revise 编排 + helper + revise prompt）、`repositories/story_bible_repo.py`（加 3 方法）、`schemas/story.py`（加 request/response schema）、`routers/story.py`（加 3 端点）；新增迁移 `migrations/versions/<hash>_add_story_bible_status_revision_changed_fields.py`、`tests/` 下扩/新增测试。
- **新迁移是 ALTER（加列），非建表**——down_revision 指向 `ffa52c6a4e27`（3.1 建表）。server_default 保证 3.2 已建的既有半成品行回填 status='pending'/revision=1。
- architecture.md:406 曾建议合并 `story_service.py`；本 story 遵循**代码库实际「按 Agent 职责拆 service」**（同 3.2/3.3），revise 凝练归 `story_settle_agent`（与 settle 同域同 Agent 职责），编辑/恢复的薄 CRUD 亦放该 service（或视体量 dev 判断是否新拆——建议同文件，与 settle 内聚）。

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-3.4]（AC 原文 735-761）
- [Source: _bmad-output/planning-artifacts/epics.md#Story-3.5]（确认/丢弃状态流转归 3.5，763-789——本 story 预留 status 位）
- [Source: _bmad-output/planning-artifacts/epics.md#FR13]（设定卡可编辑、反馈升版本号+标变化项，178）
- [Source: _bmad-output/planning-artifacts/epics.md#Epic-3]（依赖 3.1→3.2→3.3→3.4→3.5，647-653）
- [Source: backend/src/muse/models/story_bible.py]（12 列 + server_default/NULL 语义 + `uq_story_bible_user_id_project_id`——本 story 加 3 列）
- [Source: backend/src/muse/services/story_settle_agent.py]（settle_into_profile 凝练范式 + `_parse_settle_response`/`_LLM_FIELDS`/`_MAX_TOKENS`/`_build_settle_messages`——本 story 复用 + 加 revise）
- [Source: backend/src/muse/services/style_anchor_agent.py]（extract_and_anchor_style upsert + IntegrityError 竞态兜底先例）
- [Source: backend/src/muse/repositories/story_bible_repo.py]（get_by_project/upsert_style_profile——本 story 加 upsert_profile_card/get_pending_by_project/update_card_fields）
- [Source: backend/src/muse/schemas/story.py]（StoryProfileCard 12 字段契约 + _SampleText + CamelModel——本 story 加 request/response）
- [Source: backend/src/muse/routers/story.py]（anchor_style 同步 REST + preflight 范式——本 story 加 3 端点，router 已注册无需改 main.py）
- [Source: backend/src/muse/services/exploration_service.py:42-51,135-173,376-411]（_exploration_not_found 404 helper；save_guided_answer/edit_clue 无 LLM CRUD 范式——直接编辑照此）
- [Source: backend/src/muse/services/usage_service.py:45]（check_quota 护栏——仅 revise 过）
- [Source: backend/src/muse/providers/factory.py（get_provider_for_user）+ base.py（ChatResult.content）]（MeteredProvider、禁直调 openai 陷阱①）
- [Source: backend/src/muse/core/settings.py:75-76]（deepseek_model_fast）
- [Source: backend/src/muse/schemas/base.py]（CamelModel snake↔camel 唯一转换点 AR4）
- [Source: backend/src/muse/tasks/worker.py:118-184]（settle_exploration——本 story 后 settle 既落库又推 SSE，worker 零改动）
- [Source: prototype/app/app.js:539-568]（storyProfileDialogMarkup 前端契约：编辑/反馈/revision/is-updated/确认/回到探索）
- [Source: prototype/app/app.js:638-694]（applyStoryProfileFeedback mock 关键词匹配 + 反馈 submit bump revision——本 story 真实 Agent 替代）
- [Source: prototype/app/app.js:183-207,980]（pending 卡 sessionStorage 持久化/恢复——本 story 补后端）
- [Source: _bmad-output/implementation-artifacts/3-1-story_bible表落地12字段schema-clean-room.md]（待确认项 2 revision/status 列归属——本 story 落地点）
- [Source: _bmad-output/implementation-artifacts/3-2-文风锚点入口全新UI-style_profile抽取.md]（半成品行 + 待确认项 2 + upsert 竞态兜底先例 + 不加 mode 守卫决策）
- [Source: _bmad-output/implementation-artifacts/3-3-探索整理为12字段故事设定候选卡.md]（12 字段凝练 + emit-only 受控决策 1 + 下游交接给 3.4）
- [Source: _bmad-output/implementation-artifacts/deferred-work.md:171-181]（3.3 emit-only 下游交接 + settle 触发零幂等/无 max_tries defer——revise 端点同批 defer）
- [[project_muse_setting_fields]] — 12 字段决策（借结构非采集、clean-room GPL 护栏）
- [[project_muse_quality_redline]] — NFR1 去 AI 味红线（revise prompt 口吻依据）
- [[feedback_design_decision_delegation]] — 授权分歧点有先例可依时自主选最优（受控决策 1/2/3 依据）
- [[muse_local_dev_env]] — uv / Colima / MUSE_DB_READY=1 / MUSE_REDIS_READY=1

## 待确认项（本 story 完成后交创始人/PM 裁定，不阻塞开发）

1. **【核心 schema 裁定】候选卡持久化用 story_bible 加列（受控决策 1）**：本 story 裁定「待确认项 2（revision/status 列归属）」为**在 story_bible 加 status/revision/changed_fields 列**（复用 3.2 半成品行、一作品一行状态流转）。若创始人/PM 认为应另建候选态表（如为审计保留历史版本、或 pending/confirmed 须并存两行），须在 3.5 开发前推翻本决策——但代价是跨表拷贝 + 12 字段 schema 双表维护。**建议维持加列方案**（3.1/3.2/3.3 全为「同一行渐进填充」设计）。
2. **【revision 语义边界】revision 是否需保留历史版本**：本 story revision 只是「当前卡的版本计数」（升版本覆盖同行、不留历史）。若产品需「回退到上一版设定」，须改为版本历史表（append-only）——V1 无此需求（原型 revision 也只显示号、不可回退）。请在需要版本回溯功能时确认。
3. **【幂等/限流】revise 端点接真实 LLM 有成本**：`POST /story-profile/revise` 每次一次真实 provider.chat（双击/重试=双倍计费+连续升版本）。承 settle/refresh_clues 一路 defer（deferred-work.md:174/181），归开放注册前加固批次（触发去重 + 限流）。请在开放注册/前端集成切片前确认。
4. **【NFR7 合规硬门禁】**：承 3.1/3.2/3.3——webnovel-writer GPL 许可证义务评估仍是项目级未决门禁（本 story revise 逻辑是 Muse 自建、clean-room 风险低，但项目级评估仍须创始人完成）。
5. **【style_profile 可编辑性】直接编辑是否允许改⑫**：本 story 建议 PATCH 允许编辑 style_profile 文本（它是卡的一部分、原型第⑫字段亦 contenteditable），但反馈重凝练不动它。若产品认为 style_profile 只能经 3.2 style-anchor 重锚定、不可手改，须在 schema 层从 PATCH 白名单剔除 style_profile。请确认。

## Dev Agent Record

### Agent Model Used

Claude-Opus-4.8-joybuilder[1M]（dev-story 工作流）

### Debug Log References

- `MUSE_DB_READY=1 uv run alembic revision --autogenerate -m "add story_bible status revision changed_fields"` → 仅检测到 story_bible 3 新列（status/revision/changed_fields），无杂项漂移；迁移 `d29ada3ce1b3`，down_revision 自动指向 head `ffa52c6a4e27`。
- `MUSE_DB_READY=1 uv run alembic upgrade head` / `downgrade -1` / `upgrade head` 往返成功，加列迁移可逆，DB 停在 head `d29ada3ce1b3`。
- `uv run pytest tests/test_migrations_metadata.py` → 2 passed（加列不影响元数据门禁）。
- `uv run python -c "from muse.main import app"` → app 装配 OK，story.router 3 个新端点（GET/PATCH `/story-profile`、POST `/story-profile/revise`）注册成功。
- `uv run pytest tests/test_story_profile_edit.py tests/test_story_settle.py -q -k "not requires and not worker"` → 27 passed, 12 skipped（DB/Redis 用例离线跳过），离线单元全绿。
- `uv run ruff check src tests` → All checks passed。
- `uv run mypy src` → 2 errors，均为 3.2 基线既有（story.py:43 StyleAnchorRequest validator union-attr、style_anchor_agent.py:289 竞态处理器 assignment）；本 story 零新增 mypy 错误。
- `MUSE_DB_READY=1 MUSE_REDIS_READY=1 uv run pytest -q` → **312 passed, 2 skipped**（DeepSeek 真实契约用例无 key 正常跳过），零回归（3.3 基线 288 + 本 story 新增/适配用例）。
- `git status prototype/` 为空（app.js 零改动，受控决策 A）。

### Completion Notes List

- **Task 1（加列 + 迁移，受控决策 1 落地）**：`models/story_bible.py` 加 3 列——`status`（Text NOT NULL server_default="pending"）、`revision`（Integer NOT NULL server_default="1"）、`changed_fields`（JSONB nullable）。落地 3.1/3.2/3.3 反复 defer 的「待确认项 2（revision/status 列归属）」= 同一行状态位（pending→confirmed 状态流转、非另建候选态表）。ALTER 加列迁移（非建表），server_default 保证 3.2 已建的半成品行回填。
- **Task 2（settle 落库，替代 emit-only）**：`story_settle_agent.settle_into_profile` step 8 组装候选卡后新增 `_persist_card_with_race_guard` upsert 落库（status='pending', revision=1, changed_fields=None）；复用 3.2 半成品行、style_profile 幂等写回不覆盖；竞态兜底 IntegrityError→rollback→重试 UPDATE（照 style_anchor 先例）。仍返回 card dict 给 worker 推 SSE result——settle 现在既落库又推 SSE。模块 docstring 从「emit-only」更新为「3.4 起落库 pending 卡」。**worker 零改动**（返回值签名不变）。
- **Task 3（repo 扩展）**：`story_bible_repo` 加 `upsert_profile_card`（写 12 内容字段白名单 `PROFILE_CONTENT_FIELDS` + 状态位）/ `get_pending_by_project`（status='pending' 过滤，confirmed/无行返 None）/ `update_card_fields`（仅 pending 行、白名单字段、revision 不变、清 changed_fields）。延续 kwargs-only 租户守卫 + 不 commit + flush/refresh 约定。
- **Task 4（反馈升版本，受控决策 2 同步 REST）**：`revise_profile_card`——独立 session、租户守卫 → 取 pending 卡（无 → 404 no_pending_card，先于护栏）→ check_quota → provider.chat 重凝练（当前卡 + 反馈，复用 settle 的 `_parse_settle_response`/空产 502）→ `_compute_changed_fields` 算变化项（只比 11 LLM 字段、style_profile 不计）→ upsert 升版本（revision+1、changed_fields=变化列表）。共用 system prompt 提取为 `_settle_system_prompt`（settle/revise 单一事实源）；`_build_revise_messages` 携当前卡 + 反馈要求「在现有卡基础上调整」。
- **Task 5（直接编辑 + 恢复）**：`edit_profile_card`（无 LLM、请求 session、仅 pending 行、白名单字段、revision 不变 → 404 无卡）+ `get_pending_card`（租户守卫 → get_pending_by_project，返 None = 无待确认卡）。`_no_pending_card` helper（404）。
- **Task 6（schema + router）**：`schemas/story.py` 加 `StoryProfileCardResponse`（12 字段 + revision/changedFields/status，从 ORM 序列化，独立于 3.3 的 `StoryProfileCard` emit 契约不污染）+ `ProfileFeedbackRequest`（非空有界反馈）+ `ProfileCardEditRequest`（12 字段全可选、`to_fields()` 收集非 None、天然防越权改状态位）。`routers/story.py` 加 GET `/story-profile`（有卡 200 / 无 204）、PATCH `/story-profile`（编辑）、POST `/story-profile/revise`（升版本，同步）；均非流式，story.router 3.2 已注册无需改 main.py。
- **Task 7（测试）**：新建 `tests/test_story_profile_edit.py`（离线：`_compute_changed_fields`/`_card_from_bible`、revise 编排 6 用例[happy/护栏 429/无卡 404/空产 502/租户 404/prompt 契约]、端点鉴权 2；DB：repo 5 用例[upsert 建行/更新同行/get_pending status 过滤/update_card_fields 白名单+revision 不变/无 pending 返 None]、端到端 7 用例[GET 204/GET 卡/PATCH 编辑/PATCH 404/revise 升版本/空反馈 422/revise 404]）；扩 `test_story_settle.py`（settle happy 断言落库 upsert status='pending'/revision=1，`_FakeSessionCtx` 加 commit/rollback，`_orchestration` patch upsert_profile_card）；扩 `test_story_bible.py`（新 3 列默认值 + JSONB 存列表）。全量 312 passed 零回归。
- **边界严守**：只交付加列 + settle 落库 + 编辑/反馈/恢复 service + 3 端点 + 测试；**未做确认→confirmed 只读圣经 / 回到探索丢弃（3.5）**（但 status 列 + 恢复端点只返 pending 已为 3.5 预留状态位）、未碰 drafter 注入（Epic 4）、未接前端（app.js 零改动，受控决策 A）、未改唯一约束（一作品一行状态流转）。
- **受控决策**：① 候选卡持久化 = story_bible 加列（非另建表，复用半成品行）；② 反馈升版本 = 同步 REST（非 ARQ+SSE）；③ 直接编辑无 LLM、revision 不变；④ ⑫ style_profile 不重凝练。
- **未决门禁提醒**：5 项待确认项（加列 vs 另建表 schema 裁定、revision 是否留历史、revise 幂等/限流、NFR7 GPL、style_profile 可编辑性）已登记，交创始人/PM 裁定。

### File List

**新增**：
- `backend/migrations/versions/d29ada3ce1b3_add_story_bible_status_revision_changed_.py`（story_bible 加 3 列迁移）
- `backend/tests/test_story_profile_edit.py`（3.4 repo + service + e2e 测试）

**修改**：
- `backend/src/muse/models/story_bible.py`（加 status/revision/changed_fields 3 列 + docstring 更新）
- `backend/src/muse/repositories/story_bible_repo.py`（加 upsert_profile_card/get_pending_by_project/update_card_fields + PROFILE_CONTENT_FIELDS 常量）
- `backend/src/muse/services/story_settle_agent.py`（settle 落库 pending 卡 + revise_profile_card/edit_profile_card/get_pending_card + `_no_pending_card`/`_persist_card_with_race_guard`/`_settle_system_prompt`/`_build_revise_messages`/`_card_from_bible`/`_compute_changed_fields` + docstring 从 emit-only 更新为落库）
- `backend/src/muse/schemas/story.py`（加 StoryProfileCardResponse/ProfileFeedbackRequest/ProfileCardEditRequest + docstring 更新）
- `backend/src/muse/routers/story.py`（加 GET/PATCH `/story-profile` + POST `/story-profile/revise` 3 端点 + docstring 更新）
- `backend/tests/test_story_settle.py`（settle happy 断言落库 + `_FakeSessionCtx` 加 commit/rollback + `_orchestration` patch upsert + docstring 更新）
- `backend/tests/test_story_bible.py`（加新 3 列默认值 + JSONB 用例）
- `_bmad-output/implementation-artifacts/deferred-work.md`（新增 3.4 章节：前端接线 / revise 幂等限流 / confirmed 流转归 3.5 / revision 无历史 / 内容字段 Text 未结构化）
- `_bmad-output/implementation-artifacts/sprint-status.yaml`（3-4 状态流转）

### Change Log

- 2026-07-29：Story 3.4 上下文工程创建：设定候选卡编辑 + 反馈升版本（真实 Agent）。核心裁定 3.1/3.2/3.3 反复 defer 的「待确认项 2（revision/status 列归属）」= story_bible 加 status/revision/changed_fields 三列（受控决策 1，复用 3.2 半成品行、一作品一行状态流转）；3.3 settle 从 emit-only 改落库 pending 卡；反馈升版本走同步 REST 端点真实 Agent 重凝练（受控决策 2，非 ARQ+SSE）；直接编辑无 LLM 同步 PATCH revision 不变（受控决策 3）；⑫ style_profile 不重凝练（受控决策 4）。后端 only、app.js 零改动、加列迁移（非建表）。确认/丢弃状态流转归 3.5。 | Bmad Create-Story
- 2026-07-29：Story 3.4 后端切片实现完成：story_bible 加 status/revision/changed_fields 3 列（ALTER 加列迁移 `d29ada3ce1b3` 可逆）；settle_into_profile 从 emit-only 改落库 pending 卡（复用 3.2 半成品行 + 竞态兜底，worker 零改动）；story_bible_repo 加 upsert_profile_card/get_pending_by_project/update_card_fields；revise_profile_card 真实 Agent 重凝练升版本 + `_compute_changed_fields` 变化项算法（同步 REST）；edit_profile_card 无 LLM 直接编辑 + get_pending_card 恢复；schema（StoryProfileCardResponse/ProfileFeedbackRequest/ProfileCardEditRequest）+ 3 REST 端点（GET/PATCH/POST revise）。新建 test_story_profile_edit.py + 适配 test_story_settle/test_story_bible。全量 312 passed 零回归、ruff 全绿、mypy 零新增、app.js 零改动。状态 → review。 | Claude Opus 4 | Bmad Dev-Story
- 2026-07-29：三层 adversarial code review（Blind/Edge/Auditor，均独立子 agent 与实现视角隔离）后处理：Acceptance Auditor 判 PASS（6 AC + 4 受控决策全兑现、边界严守、Completion Notes/File List 诚实）；Edge Case Hunter 以真实 repo 证伪 4 条假阳性（SessionDep MissingGreenlet / 白名单越权 / worker 需改动 / revise preflight 范式）。因 Jianghj 裁定项目转向「前后端一起走」（不再后端先行），2 条就地修复（① status 默认 `pending`→`draft` 引入三态，避免只锚文风的半成品行被当候选卡返回、迁移回填改 draft、settle 升 pending；② revise 漏字段回退 old_card 原值防静默清空 + changed_fields 比对最终新卡）；1 条 Low defer（并发 revise revision 丢失更新，归开放注册前并发加固批次，已登记 deferred-work）；6 条 dismiss。新增 3 测试，全量 315 passed 零回归、ruff 全绿、mypy 零新增。状态 → done。 | Claude Opus 4 | Bmad Code-Review
