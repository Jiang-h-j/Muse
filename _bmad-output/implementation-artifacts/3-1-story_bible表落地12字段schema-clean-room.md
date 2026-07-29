---
baseline_commit: a7550823439972f1761616e22e9120e0a93aa740
---
# Story 3.1: story_bible 表落地（12 字段 schema，clean-room）

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a Muse 后端开发者，
I want 一张承载 12 字段设定圣经的 `story_bible` 表，一次建全 schema、特化字段可空，
so that 设定圣经能真实持久化、多租户隔离，并作为全项目一致性的数据根。

## Acceptance Criteria

1. **[建表]** 执行建表迁移后，`story_bible` 表存在，含：通用主干 7 项为**必备列**、题材特化 4 项为**可空列**、`style_profile` 列（webnovel-writer 无），并带 `user_id` + `project_id` 两个租户外键列（NFR3 行级隔离）。[Source: epics.md#Story-3.1 AC1；architecture.md:224-230,295]
2. **[clean-room 合规]** 表结构作为「数据模型参考」clean-room 重实现，**不复制 webnovel-writer 的 GPL 源码**；本 story 交付物须以注释显式标注 clean-room 依据，并在「待确认项」保留「创始人做许可证义务评估（NFR7）」这一未决门禁。[Source: epics.md#Story-3.1 AC2；architecture.md:250-252,532]
3. **[特化字段可空]** `genre` 决定特化字段激活（FR12）：存储某作品设定时 genre 已知、特化字段按需填，不匹配的特化列存 NULL、不报错（DB 层不强制特化列有值）。[Source: epics.md#Story-3.1 AC3；project_muse_setting_fields 记忆]
4. **[供后续读写]** 表就位后，能以 V1 全文形式存储设定圣经条目，供 Epic 4 创作上下文与 Epic 5 归档页读取；后续 Story 3.3（生成候选卡）、3.5（确认写入）在此表上写入。[Source: epics.md#Story-3.1 AC4；architecture.md:227]
5. **[迁移可逆 + 门禁]** 迁移 `upgrade()`/`downgrade()` 均可执行；新模型被 `load_all_models()` 自动发现（`test_migrations_metadata.py` 门禁绿）；`(user_id, project_id)` 复合唯一约束落地（一作品一圣经）。

## Tasks / Subtasks

- [x] **Task 1：新建 `StoryBible` ORM 模型**（AC: 1, 3, 5）
  - [x] 新建 `backend/src/muse/models/story_bible.py`（**一表一文件**，与 `story_clue.py`/`project.py`/`exploration_session.py` 现存先例一致；不采用 architecture.md:397 早期「合并进 story.py」的建议——现有代码库实际是一表一文件）
  - [x] 继承 `Base, UUIDPKMixin, TimestampMixin`（`from muse.models.base import ...`），`__tablename__ = "story_bible"`（单数 snake_case，architecture.md:292）
  - [x] 租户列：`user_id` → `ForeignKey("user.id")`, `nullable=False, index=True`；`project_id` → `ForeignKey("project.id")`, `nullable=False, index=True`（照抄 story_clue.py:42-49 模式）
  - [x] **通用主干 7 列**（必备语义，采用 story_clue.value 先例 `Text, nullable=False, server_default=""`——语义「必备但可存空串」，解决「探索没凑齐主干字段时 3.3 写入不报错」）：`genre`、`core_appeal`、`protagonist`、`main_conflict`、`world_rules`、`overall_tone`、`opening_hook`（列语义见 Dev Notes 字段表）
  - [x] **题材特化 4 列**（`Text, nullable=True`——用 NULL 表达「该题材不适用/未激活」，语义区别于主干空串「适用但未填」）：`power_system`、`golden_finger`、`romance_line`、`faction_landscape`
  - [x] **文风锚点列**：`style_profile` → `Text, nullable=True`（Story 3.2 抽取后写入；未锚定时为 NULL，AC 允许可空用默认风格）
  - [x] `__table_args__` 加 `UniqueConstraint("user_id", "project_id", name="uq_story_bible_user_id_project_id")`（一作品一圣经，照抄 exploration_session.py:36-39 模式与理由）
  - [x] 每列写中文注释，主干/特化列说明取值语义（对照 Dev Notes 字段表）；模块 docstring 写明 clean-room 依据（AC2）
- [x] **Task 2：生成并校对 Alembic 迁移**（AC: 1, 5）
  - [x] `cd backend && uv run alembic revision --autogenerate -m "create story_bible"`（down_revision 应自动指向当前 head `687df87a3cb1`）
  - [x] 校对生成的迁移：确认 `create_table('story_bible', ...)` 含全部 12 业务列 + id/时间戳、3 个 FK、`uq_story_bible_user_id_project_id`、`ix_story_bible_user_id`/`ix_story_bible_project_id` 两索引（对照 687df87a3cb1 迁移 story_clue 的产物形态）
  - [x] 校对 `downgrade()`：`drop_index` ×2 + `drop_table('story_bible')`（本 story 是纯新增表，无 alter，downgrade 直接删表即可、无数据清理特例）
- [x] **Task 3：迁移执行与门禁验证**（AC: 4, 5）
  - [x] `MUSE_DB_READY=1 uv run alembic upgrade head` 应成功建表（本机 DB 环境见 Dev Notes）
  - [x] `uv run alembic downgrade -1` 再 `upgrade head` 往返一次，验证可逆
  - [x] `uv run pytest tests/test_migrations_metadata.py` 绿（验证 `StoryBible` 已进 `Base.metadata`、模块未被误排除）
- [x] **Task 4：模型单元测试**（AC: 1, 3, 5）
  - [x] 新建 `backend/tests/` 下对应测试（参照现有 model/repo 测试风格）：验证插入一行（主干填值、特化列留 NULL、style_profile 留 NULL）成功；验证同 `(user_id, project_id)` 二次插入撞唯一约束抛 IntegrityError
  - [x] 若测试需真实 DB，遵循 `MUSE_DB_READY=1` 门禁约定（见 Dev Notes）

### Review Findings

_（code review 2026-07-29：Blind Hunter + Edge Case Hunter + Acceptance Auditor 三层并行审查；5 条独立发现，1 patch / 2 defer / 2 dismissed。Acceptance Auditor 确认 5 条 AC 全部满足、边界守住。）_

- [x] [Review][Patch] 测试内联注释与代码矛盾 [backend/tests/test_story_bible.py:58] — 注释写「world_rules 之外的主干全填；此处故意不给 opening_hook 之外任何特化列」，但用例实际把 7 个主干列全部填了值（含 world_rules），且 opening_hook 是主干列非特化列，措辞自相矛盾。断言本身正确，仅注释误导。已修正为「主干 7 列全填、特化 4 列 + style_profile 全部留空」。
- [x] [Review][Defer] 外键无 ON DELETE，project/user 删除时若已有 story_bible 子行会被 FK 阻塞 [backend/src/muse/models/story_bible.py:50-57] — deferred, pre-existing。全体业务子表通病（story_clue/exploration_session/usage_ledger/byok_key 迁移均无 ondelete，project_service.delete_project 也无级联清理），本 story 照抄先例、未引入新不一致；删除链路的既有隐患属跨 story 问题。
- [x] [Review][Defer] user_id 与 project.user_id 可漂移，模型层无 (user_id, project_id)→project 交叉校验 [backend/src/muse/models/story_bible.py:50-57] — deferred, pre-existing。与所有既有业务表一致，租户守卫在 repo 层落地；本 story 明确不写 repo（边界内），当前无 API 入口不可外部利用。提示：Epic 3 后续写 repo 时须补 (user_id, project_id) 租户守卫、勿信客户端传入组合。


## Dev Notes

### 本 story 的边界（务必守住，勿越界）

- **本 story 只建表 + 模型 + 迁移**，是 Epic 3 的 enablement 先行项（epics.md:653「3.1 建表 enablement 先行」）。
- **不做**：不写 repository、不写 service、不写 router、不做任何设定生成/编辑/确认逻辑——那些分别属于 Story 3.3（生成候选卡）、3.4（编辑+反馈升版本）、3.5（确认写入）。
- **不建 revision / status 列**：候选卡版本号（`revision` 递增，3.4）与「待确认卡 vs 已确认圣经」的状态区分（3.5）不在本 story 的「12 字段 schema」范畴内。AC1 明确列举的是 12 个内容字段 + 租户列，未含 revision/status。**详见「待确认项」——此归属需创始人/PM 确认后再决定是否并入本迁移。** 本 story 默认按 AC 字面只建 12 字段 + 租户 + 唯一约束。

### 12 字段 schema（列名 ← → 语义映射，权威来源见 References）

**通用主干 7（必备列，`Text NOT NULL server_default=""`）：**

| 列名              | 中文语义     | 说明                                              |
| --------------- | -------- | ----------------------------------------------- |
| `genre`         | ① 题材     | **判别列**：决定下方特化字段是否激活（FR12）                      |
| `core_appeal`   | ② 核心吸引力  | 一句话 + 核心卖点 + 目标阅读体验（并入原型三项）                     |
| `protagonist`   | ③ 主角     | 姓名 + 核心欲望 + **致命缺陷 flaw**，V1 全文单列（不拆子列，实体化属 V2） |
| `main_conflict` | ④ 主要冲突   | + **反派镜像**（反派与主角共享欲望却走反路），V1 全文单列               |
| `world_rules`   | ⑤ 关键世界规则 | 世界规模 + 硬约束                                      |
| `overall_tone`  | ⑥ 整体气质   |                                                 |
| `opening_hook`  | ⑦ 开篇钩子   |                                                 |

**题材特化 4（可空列，`Text NULL`，按 genre 激活、不匹配存 NULL）：**

| 列名                  | 中文语义       | 适用题材  |
| ------------------- | ---------- | ----- |
| `power_system`      | ⑧ 力量体系/境界链 | 修仙玄幻  |
| `golden_finger`     | ⑨ 金手指      | 系统爽文  |
| `romance_line`      | ⑩ 感情线      | 言情    |
| `faction_landscape` | ⑪ 势力格局     | 设定重题材 |

**Muse 独有 1（可空列，`Text NULL`）：**

| 列名              | 中文语义   | 说明                                                                                                            |
| --------------- | ------ | ------------------------------------------------------------------------------------------------------------- |
| `style_profile` | ⑫ 文风锚点 | webnovel-writer **完全没有**；Story 3.2 抽取作品级 style_profile 后写入；本 story 只建列。V1 以全文/文本形式存（不拆 JSONB，实体化属 V2，见「待确认项」） |

> **必备列为何用 `NOT NULL server_default=""` 而非 `nullable=True`：** 主干字段语义上必备，但 V1 探索用有限问题集、不保证凑齐（epics.md:723-725「某字段留空即可、不阻塞出卡」）。若设 `NOT NULL` 无默认值，3.3 写部分字段会违反约束；若设 `nullable=True` 则丢失「必备」语义。项目既有先例 `story_clue.value`（story_clue.py:62）正是用 `Text NOT NULL server_default=""` 表达「必备但可空串」——本 story 沿用，保持列恒非 NULL 且写入不报错。
> 
> **特化列为何用 `nullable=True`（NULL）而非空串：** 特化列需区分「该题材不适用/未激活」（NULL）与「适用但未填」。NULL 语义更贴 AC3「不匹配的特化列存空、不报错」，也便于 3.3 按 genre 判定是否填充。

### 关键实现模式（照抄现存先例，勿另造）

- **Base/Mixin**：`backend/src/muse/models/base.py` 提供 `Base`、`UUIDPKMixin`（UUID 主键，`default=uuid.uuid4` 应用侧生成）、`TimestampMixin`（`created_at`/`updated_at`，DB 侧 `func.now()`）。直接继承，勿重复定义 id/时间戳。
- **最贴近的样板**：`backend/src/muse/models/story_clue.py`（租户列、`server_default=""`、`__table_args__` 唯一约束、逐列中文注释）与 `backend/src/muse/models/exploration_session.py`（`(user_id, project_id)` 复合唯一约束及其并发理由）。**新模型基本是这两者的组合。**
- **模型自动发现**：`backend/src/muse/models/__init__.py` 的 `load_all_models()` 用 `pkgutil.iter_modules` 遍历包目录自动注册到 `Base.metadata`。**新建 `story_bible.py` 后无需改任何 import 列表、无需改 `migrations/env.py`**——放进 models 包即被发现。切勿把新模块加进 `_NON_MODEL_MODULES` 排除名单（那是给 base.py 这类无表模块用的）。
- **迁移形态参照**：`backend/migrations/versions/687df87a3cb1_extend_exploration_message_and_create_.py`（story_clue 的建表迁移）是最新、最贴近的模板——`op.create_table` 列顺序、`ForeignKeyConstraint`、`UniqueConstraint`、`op.create_index(op.f('ix_...'))` 命名全部对照它。

### 命名与大小写约定（architecture.md:283-295）

- DB / ORM / repository 一律 **snake_case**（`user_id`, `story_bible`, `style_profile`）。
- 表名**单数** snake_case。主键统一 `id`；外键 `<实体>_id`。索引由 SQLAlchemy `index=True` 自动生成 `ix_<表>_<列>`。
- 本 story **不涉及 API 层**，故无 camelCase 转换点（那在 Pydantic schema，属 3.3+）。

### 本机开发环境（muse_local_dev_env 记忆）

- 命令统一用 `uv run ...`（在 `backend/` 目录下）。
- **DB 相关操作（迁移执行、需真实 DB 的测试）须带 `MUSE_DB_READY=1` 环境变量**；容器用 Colima（非 Docker 桌面），pip 源走清华镜像。
- 迁移日常命令：`uv run alembic revision --autogenerate -m "..."`（生成）、`uv run alembic upgrade head` / `downgrade -1`（运行）。README: `backend/README.md`。

### Testing standards

- 迁移可见性门禁 `backend/tests/test_migrations_metadata.py` 必须保持绿——它是离线契约（无需 DB），断言声明的表都进了 `Base.metadata`。新模型天然被覆盖，无需改门禁本身。
- 需真实 DB 的模型/约束测试遵循 `MUSE_DB_READY=1` 约定；参照 `backend/tests/` 下现有 repo/model 测试的 fixture 风格。

### Project Structure Notes

- 新增：`backend/src/muse/models/story_bible.py`、`backend/migrations/versions/<hash>_create_story_bible.py`、`backend/tests/` 下一个测试文件。
- **变量说明**：architecture.md:397 曾建议 `models/story.py` 合并 story_state/story_bible/story_thread；但当前代码库实际是**一表一文件**（story_clue.py 等）。本 story 遵循**代码库实际模式**（一表一文件 → `story_bible.py`），与既有先例一致，不引入合并文件。story_state/story_thread 归 Epic 5、届时各自建文件。

### 上游依赖状态（均已就绪）

- `user` 表（Story 1.2，done）、`project` 表（Story 1.4，done）已存在，FK 目标就位、无悬空。
- 当前迁移 head：`687df87a3cb1`（sprint-status.yaml 与 versions 目录佐证 Epic 1/2 全部迁移已落地）。

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-3.1]（AC 原文）
- [Source: _bmad-output/planning-artifacts/epics.md#Epic-3]（依赖 3.1→3.2→…→3.5、按需建表说明 epics.md:647-653）
- [Source: _bmad-output/planning-artifacts/architecture.md#焦点三-多用户存储层]（五表映射、story_bible V1 全文/V2 实体化，224-236）
- [Source: _bmad-output/planning-artifacts/architecture.md#Naming-Patterns]（表名/大小写/索引约定，283-295）
- [Source: _bmad-output/planning-artifacts/architecture.md#焦点四]（clean-room GPL 护栏、许可证义务评估待定，250-252,532）
- [Source: backend/src/muse/models/story_clue.py]（server_default="" + 租户列 + 唯一约束样板）
- [Source: backend/src/muse/models/exploration_session.py]（(user_id, project_id) 复合唯一约束理由）
- [Source: backend/src/muse/models/base.py]（Base/UUIDPKMixin/TimestampMixin）
- [Source: backend/src/muse/models/__init__.py]（load_all_models 自动发现契约）
- [Source: backend/migrations/versions/687df87a3cb1_*.py]（最新建表迁移模板）
- [Source: 记忆 project_muse_setting_fields]（12 字段决策、clean-room、webnovel-writer 权威字段来源路径）
- [Source: 记忆 muse_local_dev_env]（uv / Colima / MUSE_DB_READY=1）

## 待确认项（本 story 完成后交创始人/PM 裁定，不阻塞建表）

1. **【合规硬门禁】NFR7 许可证义务评估**：webnovel-writer 为 GPL，字段结构作为「数据模型参考」clean-room 重实现。正式实现前须**创始人做许可证义务与商业形态兼容性评估**（architecture.md:532 附录待定项）。本 story 已用 clean-room 方式（不复制源码）交付，但该评估作为项目级门禁**仍未完成**，须显式追踪。
2. **【schema 边界】revision / status 列归属**：3.4 需 `revision` 递增、3.5 需区分「待确认候选卡 vs 只读圣经」。这两列是否应在本 story「一次建全 schema」时并入 `story_bible`，还是留待 3.3/3.4 按需 alter（或另设候选卡态表）？本 story 默认**不建**（按 AC1 字面只列 12 内容字段 + 租户），建议 3.3 创建前确认。
3. **【存储形态】`style_profile` 用 Text 还是 JSONB**：style_profile 有明确子结构（人称/语气/句式节奏/意象密度/段落长度，AR15）。本 story 按 architecture「V1 全文」原则保守选 **Text**（与其他字段一致、实体化属 V2）。若 Epic 4 drafter 注入需要结构化读取，可能改 JSONB——请在 3.2 抽取实现前确认。
4. **【复合字段拆分】主角/主要冲突**：V1 单 Text 列全文存（姓名+欲望+缺陷 / 冲突+反派镜像未拆子列）。V2 实体化时再拆——确认 V1 不需要子字段级查询。

## Dev Agent Record

### Agent Model Used

Claude-Opus-4.8-joybuilder[1M]（dev-story 工作流）

### Debug Log References

- `MUSE_DB_READY=1 uv run alembic revision --autogenerate -m "create story_bible"` → 仅检测到 story_bible 新表 + 2 索引，无杂项漂移。
- `MUSE_DB_READY=1 uv run alembic upgrade head` / `downgrade -1` / `upgrade head` 往返成功，迁移可逆，DB 停在 head `ffa52c6a4e27`。
- `uv run pytest tests/test_migrations_metadata.py` → 2 passed（StoryBible 已进 Base.metadata）。
- `MUSE_DB_READY=1 uv run pytest tests/test_story_bible.py -v` → 4 passed。
- `MUSE_DB_READY=1 MUSE_REDIS_READY=1 uv run pytest -q` → 236 passed, 2 skipped（DeepSeek 真实契约用例无 key 正常跳过），零回归。
- `uv run ruff check .` → All checks passed（migrations/versions 按 pyproject `extend-exclude` 既定约定豁免；模型与测试文件独立跑 ruff 亦全干净）。

### Completion Notes List

- **Task 1**：新建 `models/story_bible.py`，`StoryBible` 继承 Base/UUIDPKMixin/TimestampMixin。7 主干列 `Text NOT NULL server_default=""`（照 story_clue.value 先例，「必备但可空串」）、4 特化列 + style_profile `nullable=True`（NULL 表「不适用/未激活」），`(user_id, project_id)` 复合唯一约束（照 exploration_session）。模型被 `load_all_models()` 自动发现，未改 env.py。
- **Task 2**：autogenerate 迁移 `ffa52c6a4e27_create_story_bible.py`，down_revision 自动指向 head `687df87a3cb1`。校对确认 12 业务列 + id/时间戳、2 FK、复合唯一约束、2 索引齐全；downgrade 纯删索引+删表（无 alter），补了中文注释。
- **Task 3**：迁移 upgrade→downgrade→upgrade 往返验证可逆；门禁测试绿。
- **Task 4**：`tests/test_story_bible.py` 4 个用例——主干填值+特化留 NULL、7 主干列 server_default 空串生效、特化列可写值、复合唯一约束二次插入抛 IntegrityError。用同步 ORM Session 造 user+project+story_bible（本 story 无 API 层）；靠 conftest 的 TRUNCATE...CASCADE 经 FK 连带清理隔离，未改 conftest。
- **边界严守**：只建表+模型+迁移+测试，未写 repository/service/router；未建 revision/status 列（留待「待确认项 2」裁定）。
- **未决门禁提醒**：待确认项 1（NFR7 GPL 许可证义务评估）是项目级门禁，本 story 以 clean-room 方式交付但该评估仍需创始人完成。

### File List

- `backend/src/muse/models/story_bible.py`（新增）
- `backend/migrations/versions/ffa52c6a4e27_create_story_bible.py`（新增）
- `backend/tests/test_story_bible.py`（新增）

### Change Log

- 2026-07-29：实现 Story 3.1——新建 story_bible 表（12 字段 schema + 租户列 + 复合唯一约束）、ORM 模型、Alembic 迁移与模型单元测试；全量 236 测试通过、零回归。
