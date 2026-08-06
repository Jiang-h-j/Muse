---
baseline_commit: 854827cd5329ea6a28bf82c84be4616b4256f7dd
---

# Story 5.1: 归档核心表落地（chapter_card / story_thread / story_state）

Status: done

## Story

As a Muse 后端开发者，
I want 承载章节卡片、未回收线索、故事状态的三张一致性核心表，
so that 写后投影（Story 5.2 chapter-commit）有落点、长程一致性有数据根。

## Acceptance Criteria

**AC1（表结构落地）**
**Given** AR8 五张核心表（`story_bible` 已在 Epic 3 建、`embedding` 归 Story 5.5）
**When** 建表迁移执行
**Then** 建 `chapter_card`（章节卡片）、`story_thread`（未回收伏笔/线索）、`story_state`（主角状态/世界规则/当前阶段）三表，均带 `user_id` + `project_id`（NFR3 行级租户隔离）

**AC2（语义承载对齐）**
**Given** 三表都服务写后投影（Story 5.2 的直接落点）
**When** 设计表结构
**Then** `chapter_card` 存章节归档五要素（本章发生了什么/人物变化/新增事实与线索/未解决悬念/章末状态），`story_thread` 存伏笔状态，`story_state` 存主角与世界规则当前快照

**AC3（多租户守卫可写可查）**
**Given** 多租户隔离（NFR3）
**When** 任意读写三表
**Then** repository/DAO 层强制注入 `user_id` + `project_id` 租户过滤，不越权

**AC4（支撑单事务投影）**
**Given** 后续 Story（5.2 投影、5.3 归档展示）依赖三表
**When** 表就位
**Then** 结构支持单事务原子投影（为 Story 5.2 chapter-commit 做准备——本 story 只建表结构，不写投影逻辑；repo 仅 flush、commit 边界归上游 service）

## Tasks / Subtasks

- [x] Task 1 (AC: 1, 2) — 新建三张 ORM 模型文件
  - [x] Subtask 1.1：`backend/src/muse/models/chapter_card.py`，`__tablename__ = "chapter_card"`，类 `ChapterCard`，继承 `Base, UUIDPKMixin, TimestampMixin`；**复合唯一约束** `(user_id, project_id, chapter_number)` 名 `uq_chapter_card_user_project_chapter`（一章至多一张卡，投影 upsert 幂等键，对齐 `chapter` 表复合唯一先例 + Story 5.2 单事务原子投影重跑不产生副本）；`chapter_number: Integer NOT NULL`；五要素字段全部为 `Text NOT NULL server_default=""`（语义必备但允许空串，与 `story_bible` 主干列同先例）：`what_happened`、`character_changes`、`new_facts_clues`、`unresolved_hooks`、`end_state`
  - [x] Subtask 1.2：`backend/src/muse/models/story_thread.py`，`__tablename__ = "story_thread"`，类 `StoryThread`；字段：`content: Text NOT NULL server_default=""`（伏笔/线索描述）、`status: Text NOT NULL server_default="open"`（值域由 service 保证——`open` / `resolved` / `abandoned`，与 `chapter.status` / `story_bible.status` 同款不加 DB CHECK 的项目先例）、`introduced_chapter_number: Integer NOT NULL`（第几章埋的）、`resolved_chapter_number: Integer | None = mapped_column(Integer, nullable=True)`（第几章收的，未收 = NULL）、`last_touched_chapter_number: Integer NOT NULL`（最近一次推进/提及的章号，供 5.6 RAG 召回与「N 章未回收」优先级排序）；`user_id` / `project_id` 常规；**不加复合唯一约束**（一作品可同时存在多条 open thread，fragement 无自然幂等键，投影时由 5.2 用 `last_touched_chapter_number` + 内容哈希自行去重）
  - [x] Subtask 1.3：`backend/src/muse/models/story_state.py`，`__tablename__ = "story_state"`，类 `StoryState`；**复合唯一约束** `(user_id, project_id)` 名 `uq_story_state_user_id_project_id`（一作品一份当前快照，同行 UPDATE，对齐 `story_bible` 复合唯一先例——「当前快照」语义上唯一，多行无意义）；字段：`protagonist_state: Text NOT NULL server_default=""`（主角当前状态快照：心境/伤势/资源/关系网等 V1 全文）、`world_rules_state: Text NOT NULL server_default=""`（世界规则当前生效快照、含修订追加，V1 全文）、`current_stage: Text NOT NULL server_default=""`（当前所处阶段叙事位置简述；不用富类型 FK 到 `stage_plan.stage_number`——`stage_plan` 是编排中间态，而 `story_state.current_stage` 是叙事快照，由 data-agent 每章定稿时写入/演进，V1 不必与阶段规划表强耦合）
- [x] Task 2 (AC: 1) — 生成 Alembic 迁移
  - [x] Subtask 2.1：`MUSE_DB_READY=1 uv run alembic revision --autogenerate -m "create chapter_card story_thread story_state"`，校对输出（三张新表 + 各 2 索引 `(ix_<table>_user_id, ix_<table>_project_id)` + 两个唯一约束 `uq_chapter_card_user_project_chapter`、`uq_story_state_user_id_project_id` + FK 齐全，无杂项漂移）；`down_revision = "55130c002b17"`（当前 head）
  - [x] Subtask 2.2：`MUSE_DB_READY=1 uv run alembic upgrade head` / `downgrade -1` / `upgrade head` 三向往返验证可逆；downgrade 补中文注释（纯删索引+删表，无 alter）
- [x] Task 3 (AC: 2) — 离线门禁：`backend/tests/test_migrations_metadata.py` 保持绿（自动发现，无需改）
  - [x] Subtask 3.1：`uv run pytest tests/test_migrations_metadata.py` 断言 3 张新表都进 `Base.metadata`
- [x] Task 4 (AC: 1, 2) — 新建 schema 单元测试文件
  - [x] Subtask 4.1：新建 `backend/tests/test_chapter_card.py`（同步 ORM Session 风格，照 `test_story_bible.py`）：插入五要素全填值 → 成功；不填任何五要素列 → 全 `""`（server_default）；同 `(user_id, project_id, chapter_number)` 二次插入抛 `IntegrityError`
  - [x] Subtask 4.2：新建 `backend/tests/test_story_thread.py`：插入填 `content` + `introduced_chapter_number=1` + `last_touched_chapter_number=1` → `status="open"` / `resolved_chapter_number IS NONE`（默认值）；可写 `resolved_chapter_number`；同一作品连续多行独立 thread 不撞约束（验证无复合唯一约束）
  - [x] Subtask 4.3：新建 `backend/tests/test_story_state.py`：插入仅填 `user_id+project_id` 一行 → 三列为 `""`；同 `(user_id, project_id)` 二次插入抛 `IntegrityError`
- [x] Task 5 (AC: 3) — 三张表的最小 repo 文件 + 租户守卫测试
  - [x] Subtask 5.1：新建 `backend/src/muse/repositories/chapter_card_repo.py`，只放 `get_by_chapter(session, *, user_id, project_id, chapter_number)`（返回 `ChapterCard | None`，二义合一）；不入 service 消费（5.3 才读），本 story 仅为「持锁证明租户守卫可用」
  - [x] Subtask 5.2：新建 `backend/src/muse/repositories/story_thread_repo.py`，只放 `list_open_by_project(session, *, user_id, project_id)` 返回 `list[StoryThread]`（按 `last_touched_chapter_number` 降序）
  - [x] Subtask 5.3：新建 `backend/src/muse/repositories/story_state_repo.py`，只放 `get_by_project(session, *, user_id, project_id)` 返回 `StoryState | None`
  - [x] Subtask 5.4：在 `backend/tests/` 新建三个 repo 测试（或用例并入 Task 4 同文件，照 `test_chapter_repo.py` / `test_stage_plan_repo.py` 既有风格），每表一个越权断言：A 用户建行 → B 用户 `get_*` 拿同一 project_id → 返回 `None` / `list` 为空（二义合一，与 `get_owned_project` 同款先例）；注意 repo 是 async（`AsyncSession`）——参照现有 async repo 测试的 async fixture 风格，不要写成同步 Session
  - [x] Subtask 5.5：**不做**任何 service / router / schema / upsert / update / delete——投影写路径归 5.2，归档读路径归 5.3/5.4；如发现确实需要，先回来与 Jianghj 对齐
- [x] Task 6 — 全量回归
  - [x] Subtask 6.1：`MUSE_DB_READY=1 MUSE_REDIS_READY=1 uv run pytest -q` → 之前 577 passed 全绿 + 新增用例
  - [x] Subtask 6.2：`uv run ruff check .` → All checks passed
  - [x] Subtask 6.3：README 不动；`deferred-work.md` 不动（本 story 无新增 defer）

## Dev Notes

### 关键实现模式（照抄现存先例，勿另造）

- **Base/Mixin**：`backend/src/muse/models/base.py` 提供 `Base` / `UUIDPKMixin` / `TimestampMixin`，直接继承，勿重复定义 `id` / `created_at` / `updated_at`
- **最贴近样板**：本章 Story 3.1 已用 `story_clue.py` + `exploration_session.py` 复合唯一先例建好 `story_bible.py`，本 story **三表基本照 `story_bible.py` 模板逐字段抄**（docstring 顶层格式、逐列中文注释、复合唯一约束 `__table_args__`、`ForeignKey(..., nullable=False, index=True)` 租户列）
- **模型自动发现**：`backend/src/muse/models/__init__.py:load_all_models()` 用 `pkgutil.iter_modules` 自动导入，**新建 3 个文件后无需改 `_NON_MODEL_MODULES`、无需动 `migrations/env.py`**；切勿把新模块加进排除名单
- **迁移模板**：`backend/migrations/versions/ffa52c6a4e27_create_story_bible.py`（最新建表迁移，与本 story 同为「仅新建三表」形态）；`d29ada3ce1b3_add_story_bible_status_revision_changed_.py`（最近的 alter 迁移参考，**本 story 不适用**——三表是新建不是 alter）
- **列类型选择**：
  - 必备但可空串 → `Text NOT NULL server_default=""`（`story_bible` 主干 7 列、`story_clue.value` 先例）——本 story 五要素 / `content` / `protagonist_state` / `world_rules_state` / `current_stage` 全走此
  - 「不适用 / 未激活 / 未发生」 → `nullable=True`（`story_bible` 特化 4 列先例）——本 story 仅 `story_thread.resolved_chapter_number`
  - 章节号 → `Integer NOT NULL`（`chapter.chapter_number` / `stage_plan.stage_number` 先例），**不 `server_default="1"`**——`chapter_card.chapter_number` 必须显式传入（投影时按定稿章号写），不设默认与首章绑定假象
- **状态字段**：`status` 用 `Text + 值域由 service 保证`，**不加 DB CHECK 枚举约束**——全项目既有先例（`story_bible.status` / `chapter.status` / `project.billing_path` 全为同款）
- **JSONB 不用**：本 story 三表全部用 `Text`，**不引入 JSONB**——Story 5.2 投影的 data-agent 产出结构化 JSON 由 service 解析后落到这五个 `Text` 列（每个要素一列），语义清晰、查询可视化、`pg_dump` 友好；结构化 JSONB 子列归 V2 实体化（与 `story_bible` 同判决）
- **幂等键选取**：`chapter_card` 用 `(user_id, project_id, chapter_number)`——与 `chapter` 表幂等键同键位（5.2 单事务 chapter-commit 重跑 / ARQ 重试 `max_tries=1` 不产生副本）；`story_state` 用 `(user_id, project_id)`（一作品一份当前快照、UPSERT 同行 UPDATE）；`story_thread` 故意**无自然幂等键**（多条 open thread 并存是常态，由 5.2 用 `last_touched_chapter_number` + 内容匹配自行识别重跑）

### 命名与大小写约定（architecture.md:283-295）

- DB / ORM / repository 一律 **snake_case**
- 表名**单数** snake_case（`chapter_card` / `story_thread` / `story_state`，**不是** `chapter_cards` / `story_threads`——架构文档权威命名 architecture.md:294）；architecture.md:225-229 焦点三表格中写复数 `chapter_cards` / `story_threads` 是表格概述口吻，与 architecture.md:294 单数硬规冲突时**以硬规为准**（与 `chapter` / `stage_plan` / `story_bible` / `story_clue` 全项目先例一致）
- 主键统一 `id`；外键 `<实体>_id`；索引由 SQLAlchemy `index=True` 自动生成 `ix_<表>_<列>`
- 本 story **不涉及 API 层**，无 camelCase 转换点（那是 Pydantic schema，归 5.3 归档页 / 5.6 RAG 消费）

### 五个受控决策（Jianghj 历史裁定沿用 + 本 story 显式拍板）

1. **五要素字段名：以 epics.md AC 为准，非原型 mock**：epics.md:1075 列出「本章发生了什么/人物变化/新增事实与线索/未解决悬念/章末状态」；前端原型 mock（`prototype/app/app.js:3775-3806`）写「尚未解决的悬念」是 UI 标签中文，不影响 DB 列名 `unresolved_hooks`——DB 取 snake 简洁语义，前端在 5.3 归档页消费时自行映射 UI 文案
2. **`story_state.current_stage` 用 `Text` 不 FK 到 `stage_plan.stage_number`**：`stage_plan` 是编排中间态（4.2/4.3 论证「基础设施表 vs 业务表」分层），`story_state.current_stage` 是叙事快照（「程野刚进入第七码头地下档案库」）由 data-agent 每章定稿写入演进，V1 不强耦合。V2 若做「阶段实体化」可再 FK
3. **不建 `style_profile` 类列**：`style_profile` 已挂在 `story_bible`（3.2 已落）；一致性快照三表不复读——drafter 注入时 `style_profile` 仍走 `story_bible.style_profile`（AR16 消费链不变）
4. **本 story 不建 embedding 表**：`embedding` 归 Story 5.5（pgvector + HNSW），与本 story 三张业务表分属不同迁移、不同 story，避免一次 PR 混 pgvector 启用与业务建表两个变更面
5. **本 story repo 只放「最小租户守卫读法」，不放 upsert / update / delete**：写路径归 5.2 chapter-commit 单事务 service 层（届时新增 `upsert_chapter_card` 等），本 story 不为 5.2 写「猜测中的写路径」——避免 5.2 dev 时返工重构 repo；读路径只为「持锁证明租户守卫可用」存在（AC3 字面要求 repo 层强制注入），5.3 归档页 dev 时按需扩展

### 一个边界提示（防 review 争议）

- **`story_thread.last_touched_chapter_number` 与 `chapter.chapter_number` 类型对齐**：都是 `Integer NOT NULL`、不设 `server_default`。写入由 5.2 service 显式赋值，建表时无默认。映射「最近一次推进/提及的章号」——新增时 = `introduced_chapter_number`，后续每章定稿 data-agent 重提及时同步推到此章号；为 5.6 RAG「N 章未回收伏笔」召回做指标

### Project Structure Notes

- 新增：`backend/src/muse/models/{chapter_card, story_thread, story_state}.py`（一表一文件，与 `story_bible.py` / `story_clue.py` 同模式——本 story 遵循代码库实际，不引入 architecture.md:397 曾建议的 `models/story.py` 合并文件，与 Story 3.1 同判决）
- 新增：`backend/migrations/versions/<hash>_create_chapter_card_story_thread_story_state.py`（**一次迁移建三表**，避免拆三次——它们都是 Epic 5 一致性核心表、同一建表迁移事务天然原子；若 autogenerate 拆出三份请合并为一份）
- 新增：`backend/src/muse/repositories/{chapter_card_repo, story_thread_repo, story_state_repo}.py`
- 新增：`backend/tests/{test_chapter_card.py, test_story_thread.py, test_story_state.py}`（或合并测试文件，保持与 `test_story_bible.py` 同步 ORM 风格）；repo 越权测试并入或独立 `test_chapter_card_repo.py` 等（参照 `test_chapter_repo.py` / `test_stage_plan_repo.py` async fixture 风格）
- **不改**：`models/__init__.py`（自动发现）、`migrations/env.py`、`README.md`、`deferred-work.md`、任何 service / router / schema / orchestration / 前端
- 无结构性冲突：models 包一表一文件、repositories 包按表分文件均为既有惯例

### 上游依赖状态（均已就绪）

- `user` 表（Story 1.2 done）、`project` 表（Story 1.4 done）—— FK 目标就位、无悬空
- `chapter` 表（Story 4.4 done）—— 提供 `chapter_number` 类型对齐范本
- `story_bible` 表（Story 3.1 done）—— 复合唯一 / 主干空串 / 状态无 CHECK 先例就位
- 当前迁移 head：`55130c002b17`（Story 4.4 `create_chapter`，4.5/4.6/4.7 均为零迁移）

### Testing Standards

- `backend/tests/test_migrations_metadata.py` 离线门禁必须保持绿（无需改，自动发现天然覆盖 3 张新表）
- DB 用例沿用 conftest 约定：需起容器并设 `MUSE_DB_READY=1`，否则 skip；`requires_db` 装饰器来自 `tests/conftest.py`；异步 repo 测试参考 `test_chapter_repo.py` 的 async fixture 风格
- 模型用例用**同步 ORM Session**（`test_story_bible.py` 先例，本 story 无 API 层不走 HTTP 栈直接造行）
- conftest 的 `TRUNCATE ... CASCADE` 经 FK 连带清理隔离：本 story 三表 FK `user` / `project`，seed 出 user+project 后测试结束自动清，**无需另加 teardown**

### 本机开发环境备忘（muse_local_dev_env 记忆）

- 命令统一 `uv run ...`（在 `backend/` 目录下）
- **DB 相关操作须带 `MUSE_DB_READY=1`**（迁移跑通、DB 用例跑通）；Redis 相关再追加 `MUSE_REDIS_READY=1`（本 story 无 ARQ 新任务，但全量回归带上保险）
- 容器用 Colima（非 Docker 桌面），pip 源走清华镜像（`backend/pyproject.toml:tool.uv.index`）
- 迁移日常命令：`uv run alembic revision --autogenerate -m "..."`（生成）、`uv run alembic upgrade head` / `downgrade -1`（运行）

### 与上一个 story（4.7）衔接说明

- 4.7 的 Dev Notes 明确写「写后投影三表归 Epic 5、本 story 不建（决策 1）」+「`chapter.status` 只写 finalized」——4.7 留下的**正是本 story 的入口**（定稿后 Epic 5 Story 5.2 把事实投影进这三张表）
- 4.7 review 发现 F1（已 finalized 拒 revise/regenerate）已落地——本 story 三表**不感知章节状态**，定稿与否的流转控制在 `chapter.status`，三表只是「数据沉淀面」
- 4.7 全量回归 = `577 passed / 2 skipped`；本 story 完成后预期 ≥ 577 + 新增 16 用例 = 593+ passed

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 5.1]（1061-1083，AC 原文）
- [Source: _bmad-output/planning-artifacts/epics.md#Epic 5]（1053-1059：依赖 5.1→5.2→...、按需建表、关键跨 epic 衔接）
- [Source: _bmad-output/planning-artifacts/epics.md:115]（AR8 五张核心表权威命名）
- [Source: _bmad-output/planning-artifacts/epics.md:133-134]（AR16 写前上下文 / AR17 单事务 chapter-commit）
- [Source: _bmad-output/planning-artifacts/epics.md:1075]（章节卡片五要素：DB 列名以本段为准）
- [Source: _bmad-output/planning-artifacts/architecture.md#焦点三-多用户存储层]（224-236，五表映射 + chapter-commit 单事务投影）
- [Source: _bmad-output/planning-artifacts/architecture.md#Naming-Patterns]（283-295，snake/单数表名/复合唯一前缀 uq_）
- [Source: _bmad-output/planning-artifacts/architecture.md#焦点四-一致性机制迁移]（240-247，三段闭环 + chapter-commit 单事务）
- [Source: _bmad-output/implementation-artifacts/3-1-story_bible表落地12字段schema-clean-room.md]（最贴近的建表先例——docstring 结构 / 主干空串 / 特化 NULL / 复合唯一 / 迁移往返 / 测试风格 全照抄）
- [Source: _bmad-output/implementation-artifacts/4-7-定稿本章-阶段循环-阶段交界方向输入.md]（Dev Notes 决策 1「三表归 Epic 5」+ 全量测试基线 577）
- [Source: _bmad-output/implementation-artifacts/deferred-work.md:381-382]（阶段循环 / 归档衔接 defer 台账——本 story 不动该文件）
- [Source: backend/src/muse/models/story_bible.py]（最贴近样板：复合唯一 + 主干空串 + 特化 NULL）
- [Source: backend/src/muse/models/story_clue.py]（`Text NOT NULL server_default=""` 先例）
- [Source: backend/src/muse/models/exploration_session.py]（复合唯一约束理由：贴租户语义、与查询守卫列一致）
- [Source: backend/src/muse/models/chapter.py]（`chapter_number: Integer NOT NULL` + 复合唯一先例）
- [Source: backend/src/muse/models/base.py]（Base / UUIDPKMixin / TimestampMixin）
- [Source: backend/src/muse/models/__init__.py]（`load_all_models` 自动发现契约 + `_NON_MODEL_MODULES` 不要误加）
- [Source: backend/src/muse/repositories/story_bible_repo.py]（同类建表 repo 模板；本 story 只需「get/list 最小读法」，不必复制 upsert/update/delete）
- [Source: backend/src/muse/repositories/base_repo.py]（租户守卫约定 docstring：「每个业务 repo 的查询/写入都必须显式绑定 user_id」）
- [Source: backend/migrations/versions/ffa52c6a4e27_create_story_bible.py]（最新建表迁移模板——列顺序 / FK / 索引 / uq 命名）
- [Source: backend/tests/test_story_bible.py]（schema 单测模板——同步 ORM Session / server_default 断言 / IntegrityError 唯一约束断言）
- [Source: prototype/app/app.js:3775-3806]（原型章节卡 mock——五要素 UI 标签「尚未解决的悬念」与 epics.md AC「未解决悬念」的文案差异，以 AC 为准）
- [Source: 记忆 project_muse_setting_fields]（12 字段 clean-room 判决——本 story 三表与 story_bible 同属 clean-room 重实现产出，GPL 义务评估仍挂）
- [Source: 记忆 muse_local_dev_env]（uv / Colima / MUSE_DB_READY=1）

## Dev Agent Record

### Agent Model Used

Claude-Sonnet-4.6-1M（dev-story 工作流，Claude Code）

### Debug Log References

- **环境预检**：`docker ps` 显示 `muse-postgres` / `muse-redis` 均 healthy（避免 Epic 1 误以为是容器坑的排查）→ 直接进入 Task 1。
- **离线门禁**：`uv run pytest tests/test_migrations_metadata.py -v` → 2 passed（三张新表自动发现，无需改 `models/__init__.py`、`migrations/env.py`）。
- **autogenerate 的「DB 副作用」教训**：首次 autogenerate 得到**空 upgrade**——排查发现 conftest 的 `_sync_engine` 在 `create_all(checkfirst=True)` 时已用 `Base.metadata` 提前建出三表（test_migrations_metadata 一跑副作用即产生）。处理：drop DB 里三张表 + 删除空迁移 + 重新 autogenerate，得到真实 `f472170cd859_create_chapter_card_story_thread_story_.py`（3 表 + 6 索引 + 2 唯一约束 + 6 FK 齐全，无杂项漂移）。
- **迁移往返**：`MUSE_DB_READY=1 uv run alembic upgrade head` / `downgrade -1` / `upgrade head` 三向通过，`alembic current` = `f472170cd859 (head)`。
- **schema 测试**：`MUSE_DB_READY=1 uv run pytest tests/test_chapter_card.py tests/test_story_thread.py tests/test_story_state.py -v` → 11 passed（五要素 / 全空串默认 / 唯一约束 IntegrityError / story_thread 无约束并存）。
- **repo 测试**：`MUSE_DB_READY=1 uv run pytest tests/test_chapter_card_repo.py tests/test_story_thread_repo.py tests/test_story_state_repo.py -v` → 13 passed（含 get/list 主读法、absent → None、租户守卫 None/[]、cross-project 隔离）。中间踩一次笔误（字符串错配单引号）已修。
- **全量回归**：`MUSE_DB_READY=1 MUSE_REDIS_READY=1 uv run pytest -q` → **601 passed / 2 skipped**（4.7 baseline 577 + 本 story 新增 24），零回归。
- **ruff**：`uv run ruff check .` → All checks passed（含 migrations/versions 按 pyproject `extend-exclude` 既定豁免）。

### Completion Notes List

**交付面（AC1-4 全兑现，Story 5.1 是 Epic 5 第一张表）**：

后端：**6 任务全 done、零既有代码改动**（只新增）。

- **Task 1 三张 ORM 模型**（一表一文件，照 `story_bible.py` 先例）：
  - `models/chapter_card.py`：`ChapterCard`，复合唯一 `(user_id, project_id, chapter_number)`（`uq_chapter_card_user_project_chapter`），五要素 `what_happened` / `character_changes` / `new_facts_clues` / `unresolved_hooks` / `end_state` 全 `Text NOT NULL server_default=""`——DB 列名以 epics.md AC 为准（`unresolved_hooks` 不是原型 mock 的「尚未解决的悬念」），前端 5.3 消费时自行映射 UI 文案。
  - `models/story_thread.py`：`StoryThread`，**无复合唯一约束**（open thread 片段级无自然幂等键，由 5.2 service 用 `last_touched_chapter_number` + 内容匹配自行去重）；字段 `content` / `status`（默认 `"open"`，值域由 service 保证，无 DB CHECK）、`introduced_chapter_number` / `resolved_chapter_number`（`nullable=True` 表「未回收」）/ `last_touched_chapter_number`（供 5.6 RAG「N 章未回收」召回与 5.3 归档页活跃度排序）。
  - `models/story_state.py`：`StoryState`，复合唯一 `(user_id, project_id)`（`uq_story_state_user_id_project_id`）——「一作品一份当前快照」语义上唯一，data-agent 投影 UPSERT 同行 UPDATE；`protagonist_state` / `world_rules_state` / `current_stage` 三列全 `Text NOT NULL server_default=""`；`current_stage` 选 `Text` 不 FK 到 `stage_plan.stage_number`（受控决策 2——叙事快照 ≠ 编排状态）。
- **Task 2 Alembic 迁移**：`f472170cd859_create_chapter_card_story_thread_story_.py` 一次迁移建三表（同迁移事务天然原子），`down_revision = '55130c002b17'`（4.4 `chapter` 表 head，4.5/4.6/4.7 均为零迁移）；upgrade/downgrade 各补中文 docstring 说明（升级原子性 + 降级数据损失仅限开发场景）。
- **Task 3 离线门禁**：`test_migrations_metadata.py` 2 passed——`load_all_models()` 自动发现三张新表，未改 `_NON_MODEL_MODULES`、未改 `migrations/env.py`。
- **Task 4 schema 测试（11 用例）**：`test_chapter_card.py` 4（五要素全填 / 五要素全空串默认 / 唯一约束 / 多章并存）；`test_story_thread.py` 4（默认值 open+resolved=None / content 空串 / resolved 状态流转 / 多 open thread 并存）；`test_story_state.py` 3（默认空串 / 全填值 / 唯一约束）。
- **Task 5 repo 最小读法 + 越权测试（13 用例）**：
  - `repositories/chapter_card_repo.py:get_by_chapter`（按幂等键一步取本，二义合一）。
  - `repositories/story_thread_repo.py:list_open_by_project`（按 `last_touched_chapter_number` 降序——为 5.6 RAG「N 章未回收伏笔」召回与 5.3 归档页活跃度排序预留）。
  - `repositories/story_state_repo.py:get_by_project`（二义合一）。
  - 测试：每表「主读法 + absent → None/[] + 租户守卫 + cross-project 隔离」5+4+4=13；async fixture 照 `test_chapter_repo.py`，user/project/数据用同步 Session 造种子、repo 调用走 `async_session_maker`。
  - **严守边界**：三个 repo 均**未写** upsert / update / delete / 任何 service / router / schema / orchestration / 前端——投影写路径归 5.2 chapter-commit、归档读路径归 5.3/5.4，本 story 不预判 5.2 接口。
- **Task 6 全量回归 + ruff**：601 passed / 2 skipped（DeepSeek 真实契约无 key 正常跳过）；`uv run ruff check .` All checks passed；`README.md` / `deferred-work.md` 未动（本 story 无新增 defer）。

**关键拍板已内嵌**：① 五要素 DB 列名以 epics AC 为准（`unresolved_hooks`）② `story_state.current_stage` 用 Text 不 FK 到 `stage_plan` ③ 不建 `style_profile`/`embedding` ④ 一次迁移建三表 ⑤ repo 不写路径。

**留痕**：conftest 的 `_sync_engine.create_all(checkfirst=True)` 会在 DB 里副作用建出新模型表——dev 后续跑纯离线测试（如 `test_migrations_metadata`）也会触发。本 story 在 autogenerate 前手动 drop 了三张副作用表才得到真实迁移 diff。若后续再有同类 story，autogenerate 前先 `DROP TABLE` 或先在隔离 schema/库跑 autogenerate，以免再踩「空 upgrade」坑。

### File List

**后端（新增）**：
- `backend/src/muse/models/chapter_card.py`（新建）
- `backend/src/muse/models/story_thread.py`（新建）
- `backend/src/muse/models/story_state.py`（新建）
- `backend/src/muse/repositories/chapter_card_repo.py`（新建，仅 get_by_chapter）
- `backend/src/muse/repositories/story_thread_repo.py`（新建，仅 list_open_by_project）
- `backend/src/muse/repositories/story_state_repo.py`（新建，仅 get_by_project）
- `backend/migrations/versions/f472170cd859_create_chapter_card_story_thread_story_.py`（新建，含中文 docstring）
- `backend/tests/test_chapter_card.py`（新建，4 用例）
- `backend/tests/test_story_thread.py`（新建，4 用例）
- `backend/tests/test_story_state.py`（新建，3 用例）
- `backend/tests/test_chapter_card_repo.py`（新建，5 用例）
- `backend/tests/test_story_thread_repo.py`（新建，4 用例）
- `backend/tests/test_story_state_repo.py`（新建，4 用例）

**后端（未改）**：`models/__init__.py`（load_all_models 自动发现）、`migrations/env.py`、`README.md`、`deferred-work.md`、任何 service / router / schema / orchestration / 前端文件。

## Review Findings

> 2026-08-06 三层对抗式 review（Blind Hunter / Edge Case Hunter / Acceptance Auditor）汇总。共 12 起报告 → 去重合并 12 → 0 decision-needed / 2 patch / 5 defer / 5 dismiss。Acceptance Auditor：AC1-4 全兑现，5 受控决策逐项落实，6 任务全部落地，零越界。

### Patch（已落地）

- [x] [Review][Patch] **E1 `list_open_by_project` 未测 `abandoned` 也被滤** — `backend/tests/test_story_thread_repo.py:test_list_open_filters_abandoned`：新增用例插入 1 条 open + 1 条 abandoned thread，断言返回仅 open（变异防线：若 where 改成 status != "resolved"，abandoned 会泄漏——本用例会红）
- [x] [Review][Patch] **E3 conftest TRUNCATE 未显式列三张新表** — `backend/tests/conftest.py:_clean_tables`：TRUNCATE 列表显式追加 `chapter_card, story_thread, story_state`——防御性更稳、契约更显式（不依赖 CASCADE 隐式传播）

### Defer（已登记 deferred-work）

- [x] [Review][Defer] **B2 story_thread 测试未覆盖「同内容重跑」镜像插入** — `backend/tests/test_story_thread.py`：真正测「同 content+同 last_touched 重跑去重」归 5.2 service 落地时；本 story 只证「DB 层无兜底唯一约束」，已是受控决策
- [x] [Review][Defer] **B3+E2 `list_open_by_project` 无 `(project_id, status, last_touched_chapter_number DESC)` 复合索引** — `backend/migrations/versions/f472170cd859_*.py`：V1 数据量小（内测单作品 thread < 100），5.2 落地前按预估量评估；NFR4「几百章不穿帮」目标下千级 thread 是合理预估，届时必加
- [x] [Review][Defer] **P3+E4 story_thread「无幂等键+依赖 LLM 内容稳定」+ status 无 DB CHECK 枚举** — `backend/src/muse/models/story_thread.py`：对齐全项目无 CHECK 先例（story_bible/chapter/billing_path）；受控风险。**5.2 service 写路径必须做白名单校验（open/resolved/abandoned）**
- [x] [Review][Defer] **E5 `resolved_chapter_number >= introduced_chapter_number` 无约束** — 5.2 service 写路径加显式校验，DB 层 V1 不加
- [x] [Review][Defer] **E6 `last_touched_chapter_number` 单调不减无约束** — 同上，5.2 service 校验

### Dismiss（驳回）

- **B1 `server_default=''` 非法 DDL**：项目 4 个既有迁移（story_bible/chapter/stage_plan/story_clue）同写法生产跑通；Alembic 对 Python str 自动做 SQL 字面量转义
- **P1 `Mapped[int | None]` PEP 604 兼容性**：项目 SQLAlchemy 2.0.51 完全支持
- **P2 `other_user_id, _ = ...` 会泄漏 project**：conftest `TRUNCATE ... CASCADE` 每个用例前清 user 连带所有 FK 表
- **E7 `current_stage` 与 stage_plan 脱钩**：受控决策 2 的故意设计（spec Dev Notes 明写「叙事快照 ≠ 编排状态」）
- **E8 absent 测试未覆盖「不存在 UUID」**：已被 4 个租户守卫用例间接覆盖（repo 仅 WHERE user_id==X，对 FK 不敏感）

### Acceptance Auditor 结论

**4 条 AC 全兑现、5 个受控决策逐项落实、6 任务全部落地、零越界**——建议直接通过。

### Change Log

- 2026-08-06：dev 完成 Story 5.1——新建 Epic 5 三张归档域核心表（chapter_card 五要素 / story_thread 伏笔线索 / story_state 三列快照）+ 一次 Alembic 迁移建三表 + 三个最小读法 repo + 24 用例（schema 11 + repo 13）；全量回归 601 passed 零回归、ruff 全过；迁移往返可逆；模型自动发现、env.py 未改；边界守住：无 service / router / schema / 写路径 / 跨表 FK / 前端改动。
- 2026-08-06：三层对抗式 review 完成——0 decision-needed / 2 patch（E1 abandoned 过滤用例 + E3 conftest TRUNCATE 显式列名） / 5 defer（B2 重跑去重、B3+E2 复合索引、P3+E4 status 白名单、E5 章号大小约束、E6 last_touched 单调） / 5 dismiss（B1 server_default 误报、P1 PEP604、P2 测试泄漏、E7 受控决策、E8 重复覆盖）。Acceptance Auditor：AC 全兑现零越界，建议通过。
- 2026-08-06：2 个 patch 落地——`test_story_thread_repo.py` 新增 `test_list_open_filters_abandoned`（变异防线）；`tests/conftest.py` TRUNCATE 显式列三张归档新表。全量回归 **602 passed / 2 skipped**（比 patch 前 601 多 1 用例）、ruff 全过。Story 状态 → done。

## 待确认项（本 story 完成后交创始人/PM 裁定，不阻塞建表）

1. **【合规硬门禁，沿用】NFR7 许可证义务评估**：webnovel-writer 为 GPL，本 story 三表与其 chapter_card / story_thread / story_state 五表映射架构同为 clean-room 重实现产出（借字段语义，不复制 GPL 源码）。**创始人许可证义务评估仍未完成**（Story 3.1 / 4.2 等已多次挂账），本 story 未新增负担但顺手复挂，Epic 5 收尾（5.6 后）前须正式闭环
2. **【RAG 召回字段补全】`story_thread` 是否需优先级/紧急度列**：5.6 RAG「N 章未回收」按 `last_touched_chapter_number` 距离当前章节号即可推断，本 story 不加独立 `urgency` 列；若 RAG dev 实测发现召回排序不足，可能加 `priority: Integer`，请在 5.6 实现前评估
3. **【current_stage 语义边界】**：本 story 选 `Text NOT NULL server_default=""` 由 data-agent 每章自由写叙事快照；若 5.6 RAG 或后续 V2「阶段实体化」需要结构化（FK 到 `stage_plan` 或独立 `stage_number` 列），届时再 alter——V1 保持弱绑
4. **【chapter_card 与 chapter 行的关系】**：本 story 不建 `chapter_id` FK（`chapter.id` 是 `(user_id, project_id, chapter_number)` 复合唯一的代理，但 data-agent 投影时按章号定位更直观）；选择 `(user_id, project_id, chapter_number)` 复合唯一作为幂等键。若后续有跨表 JOIN 需求（5.3 归档页拼正文？）可考虑补 FK，V1 用章号定位已够
