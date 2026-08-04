---
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8]
lastStep: 8
status: 'complete'
completedAt: '2026-07-22'
inputDocuments:
  - Muse-PRD-V1.md
  - Muse-PRD-V1-addendum.md
  - Muse-PRD-V1.decision-log.md
  - _bmad-output/planning-artifacts/prfaq-Muse.md
  - prototype/spec/prototype-spec.md
  - prototype/spec/exploration-pending-requirements.md
  - prototype/README.md
  - prototype/app/index.html
  - prototype/app/styles.css
  - prototype/app/app.js
workflowType: 'architecture'
project_name: 'Muse'
user_name: 'Jianghj'
date: '2026-07-20'
architectureFocus:
  - 模型接入层
  - 文风锚定
  - 多用户存储层
  - 一致性机制迁移（webnovel-writer Story System）
---

# Muse 架构决策文档

_本文档通过分步协作发现逐步构建。每个架构决策达成后，对应章节将被追加进来。_

## Project Context Analysis

### Requirements Overview

**Functional Requirements（按 6 开发模块归纳，聚焦 V1 Walking Skeleton）:**
PRD 不用传统 FR 编号，以「模块 × 能力版本」矩阵组织。V1 核心 = 逐页把原型 mock
替换为「真实 AI 能力 + 多用户持久化」，页面形态基本不动。
- 模块0 账户/作品：多租户身份、作品 CRUD、托管额度 + BYOK 设置页（原型无，须新增）
- 模块1 探索：引导/自由双模式、Explorer Agent 多轮对话、对话+线索持久化
- 模块2 故事设定：设定生成/编辑/确认/上下文注入、文风样本锚点（原型无，须新增）
- 模块3 创作：章节生成、批注/点评/改进/重生/定稿、幕后阶段规划、阶段交界方向输入
- 模块4 归档：章节卡片生成、上下文注入、故事档案统一入口
- 模块5 通读/交付：全本通读、只读分享链接、AI 辅助生成标识

**Non-Functional Requirements（主导架构决策）:**
- 文字质量红线（§七 launch blocker）：盲测须在模型接入层开发前完成，红线绑质量不绑模型
- 长时异步生成：写一章 = 5–10 次 LLM 调用叠加，非单次请求，需异步任务模型
- 多租户隔离：用户/作品级数据与 API 密钥隔离
- 长程一致性：几百章不设人为上限，状态/人物/伏笔不穿帮
- 成本/用量护栏：托管免费额度上限 + BYOK 卸载重度成本
- 合规：AI 强制标识（2025.9.1）、数据/版权政策（未定）、webnovel-writer GPL 许可证义务

**Scale & Complexity:**
- Primary domain: 全栈 Web（前端原型已锁契约）+ AI 编排后端（新建）
- Complexity level: 高
- Estimated architectural components: 身份/租户、作品域、探索会话、设定圣经、
  创作编排、归档投影、通读分享、模型接入层、文风锚定、RAG 召回、用量计量 —— 约 11 个主域

### Technical Constraints & Dependencies

- **页面即契约**：AI 编程开发，最小单元是页面；后端围绕原型页面逐页实现，形态不动。
- **前端既定**：vanilla JS + hash 路由 + localStorage 原型（5825 行），后端从零。
- **模型接入层须自建**：webnovel-writer 无任何正文生成 API 接入层，写作智能寄生宿主 Claude；
  Muse 须自建多 Agent 编排运行时 + 显式 LLM 调用 + 换模型后门。
- **存储层须重写**：源项目单机单书、文件系统当库；Muse 须多租户关系库 + 向量库。
- **文风锚定须自建**：源项目 style_sampler 只做本书自洽、网文套路化，基因相反。
- **DeepSeek 首选非唯一**：留换模型后门；盲测（Claude-vs-DeepSeek）为前置门禁。
- **GPL 许可证**：迁移代码前须评估义务与商业形态兼容性。
- **两处待定项**：数据/版权政策、商业模式定价——影响数据治理与用量计费设计。

### Cross-Cutting Concerns Identified

1. 模型接入层 / 多 Agent 编排运行时（模块 1/2/3/4 共用）
2. 文字质量红线（模块 2 文风锚定 → 3 正文生成 → 5 拿得出手分享，一条质量线）
3. 长程一致性机制（模块 2/4 提供骨架，模块 3 消费任务书）
4. 多租户身份与数据隔离（全模块）
5. 用量 / 成本记账与额度护栏（所有 LLM 调用路径）
6. 长时异步任务与状态回传（章节生成、探索整理）

## Starter Template Evaluation

### Primary Technology Domain

全栈 Web + AI 编排后端。前端原型已锁定形态（vanilla JS，页面即契约），
后端从零自建（多 Agent 编排 + RAG + LLM 接入）。**非典型 starter 场景**：
不套整体脚手架，采用轻量手工骨架 + 参考成熟模板的工程约定。

### Starter Options Considered

1. **full-stack-fastapi-template（tiangolo 官方）** — 成熟、含 Alembic/JWT/测试布局。
   否决为整体套用：自带 React 前端，与 Muse 已锁的 vanilla 原型冲突；仅**借其后端工程约定**。
2. **fastapi-alembic-sqlmodel-async 模板** — 异步 CRUD 完整。
   否决：依赖 SQLModel，而 SQLModel 0.0.31 与 Pydantic V2 回归冲突（2026-01 已知），版本脆弱。
3. **轻量手工骨架（uv + FastAPI + SQLAlchemy 2.0 + Alembic）** — ✅ 选定。
   最贴合「页面即契约、逐页实现」；高度定制的 AI 编排不被模板的 CRUD 假设束缚。

### Selected Starter: 轻量 FastAPI 手工骨架

**Rationale for Selection:**
- 原型前端已是既定契约，无需前端 starter；后端 AI 编排定制度高，整体模板负价值。
- 参考 full-stack-fastapi-template 的**工程约定**（Alembic 迁移、依赖注入、settings 分层、
  pytest 布局），但不引入其 React 前端。
- 用 SQLAlchemy 2.0 + Pydantic V2（规避 SQLModel 版本坑），类型清晰、生产可控。

**联网核实的版本事实（2026-07）：**
- DeepSeek 兼容 OpenAI/Anthropic SDK（切 base_url 即可）；`deepseek-chat`/`deepseek-reasoner`
  于 2026/07/24 弃用，新名 `deepseek-v4-pro`（思考）/ `deepseek-v4-flash`（快），V3.2 系 128K 上下文。
- pgvector 0.8.x = 2026 标准：HNSW 索引 + RRF 纯 SQL 融合向量与关键词，对上附录 A 三级召回；
  阿里云/AWS RDS PostgreSQL 14/15+ 支持。
- SQLModel 0.0.31 破坏 Pydantic V2 → 采用 SQLAlchemy 2.0 + Pydantic V2 分离。
- 真 BM25 需 pg_search（ParadeDB）扩展，国内托管 RDS 未必装 → V1 先用 PG 原生 tsvector 近似。

**Initialization Command（后续实现的第一个 story）:**

```bash
# 后端骨架（uv 现代依赖管理）
uv init muse-backend && cd muse-backend
uv add "fastapi[standard]" "sqlalchemy>=2.0" alembic "pydantic-settings" \
       "psycopg[binary]" pgvector "openai" "python-jose[cryptography]" "passlib[bcrypt]"
uv add --dev pytest pytest-asyncio ruff mypy
alembic init -t async migrations

# 前端（保留原型，加 Vite 渐进增强）
cd ../prototype/app && npm create vite@latest . -- --template vanilla
```

### Architectural Decisions Provided by Starter

- **Language & Runtime:** Python 3.12+ / FastAPI（后端）；前端保留 vanilla JS + Vite。
- **依赖管理:** uv（后端）、npm/Vite（前端）。
- **ORM & 迁移:** SQLAlchemy 2.0（async）+ Alembic；**不用 SQLModel**（Pydantic V2 版本坑）。
- **数据层:** PostgreSQL + pgvector 0.8.x（HNSW + RRF 混合检索）；BM25 V1 先用 tsvector 近似。
- **LLM 接入:** OpenAI Python SDK（兼容 DeepSeek，切 base_url）；模型 deepseek-v4-pro/flash（128K）。
- **Styling/Build:** 沿用原型 styles.css；Vite 提供 HMR、打包、环境变量。
- **Testing:** pytest + pytest-asyncio（后端）。
- **Lint/Format:** ruff + mypy（后端）。
- **部署:** 国内云（阿里云/腾讯云），与 DeepSeek 同区、满足 ICP 备案与合规。

**待架构决策阶段（step-04）定夺**（不属基座）：异步任务队列（写一章 5–10 次调用叠加，
需 ARQ/Dramatiq/Celery 之一）、Agent 编排框架自建 vs 借库、向量 embedding 供应商。

**Note:** 上述初始化命令应作为第一个实现 story 执行。

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (Block Implementation):**
- 认证与多租户隔离、BYOK 密钥加密存储、API 风格与长时交互、
  模型接入层编排方式、任务队列、一致性机制迁移路径、存储层数据模型

**Important Decisions (Shape Architecture):**
- 文风锚定机制、embedding 供应商抽象、RAG 三级召回实现、用量计量与额度护栏

**Deferred Decisions (Post-MVP):**
- 动态选题（EXP-P01/P02，V2）、设定圣经实体化（V2）、局部重写（V2）、
  多格式导出与公开社区（V2）、多模型可选切换（V3）、真 BM25（pg_search，视需要）

---

### 通用类决策

#### Authentication & Security
- **认证：JWT 自建（python-jose），access + refresh 双 token**。无状态、原型 localStorage 已适配。
  Rationale：单人 MVP 最省，无需 session 基础设施。Affects：模块 0 全部、所有受保护 API。
- **多租户隔离：行级 tenant 隔离**，所有业务表带 `user_id`（+ `project_id`），
  查询强制注入租户过滤；DAO 层统一守卫，杜绝越权。
- **BYOK 密钥存储：应用层 AES-GCM 加密后存 PG**，主密钥放环境变量 / 云 KMS，随账户或作品绑定。
  Rationale：契合「绑定后该作品/账户走用户 Key」；不落明文；单人可运维。

#### API & Communication Patterns
- **REST + SSE**。常规 CRUD 用 REST（FastAPI 自动 OpenAPI）；
  长时生成用「POST 提交任务 → 返回 task_id → GET /events SSE 推送进度与结果」。
- **错误处理：统一 error envelope**（code / message / detail），前端原型已有 expired/invalid/locked 等状态位可对接。
- **限流：按用户 + 端点**（配合托管免费额度护栏），触顶返回明确提示。

#### Infrastructure & Deployment
- **国内云（阿里云 / 腾讯云）**，与 DeepSeek 同区、满足 ICP 备案与数据合规。
- **PostgreSQL 托管 RDS + pgvector**；Redis（ARQ broker + SSE/缓存）；对象存储（导出件/分享页）。
- **配置：pydantic-settings 分环境**；日志结构化；LLM 调用全链路 trace（成本审计刚需）。

---

### ⭐ 焦点一：模型接入层 / 多 Agent 编排运行时（自建）

**背景**：webnovel-writer 写作智能寄生宿主 Claude，无任何生成 API 接入层 → 从零自建。

- **编排：自建轻量编排运行时**（非 LangGraph）。五段流水线：
  `context-agent（组装写作任务书）→ drafter（起草正文）→ reviewer（审查）→
   polisher（去 AI 味）→ data-agent（提取事实投影）`。
  每段是一个可独立重试的 step，step 间状态落 PG（天然实现断点续跑）。
  Rationale：流水线不复杂、断点状态本就要存库、换模型后门自控最干净、零额外依赖、贴合逐页实现。
- **LLM Provider 抽象**：定义 `LLMProvider` 接口（chat / stream / count_tokens），
  DeepSeek 为默认实现（OpenAI SDK 兼容，切 base_url）；换模型 = 换实现，业务层不改。
  模型名用 `deepseek-v4-pro`（思考，起草/审查）/ `deepseek-v4-flash`（快，提取/轻任务），128K 上下文。
- **任务队列：ARQ**（async 原生 + Redis broker），承载「写一章 5–10 次调用叠加」的后台执行，
  经 SSE 回传进度；任务可重入、失败可重试、成本按 step 累计。
- **用量计量**：每次 LLM 调用记 tokens 与成本（托管归 Muse 账、BYOK 归用户），
  托管路径校验免费额度上限（额度数值待盲测出单章成本后定）。
- **换模型后门**：托管切贵模型 / BYOK 切 Claude 均只换 Provider 实现，重算额度线。

### ⭐ 焦点二：文风锚定机制（自建）

**背景**：源项目 style_sampler 只做本书自洽、网文套路化、未接入写章主链 → 从零自建。
这是 §七行为红线「像不像用户要的味道」的**验收前提**，V1 必须有。

- **文风样本锚点（V1）**：设定阶段（模块 2）用户从**预置样本库选**，或**粘贴一段自己爱读的文字**。
  Explorer/设定页原型无此入口 → **须新增**。
- **风格特征抽取**：对锚定样本用 LLM 抽出可复用的风格画像（人称、语气、句式节奏、意象密度、
  段落长度倾向），存为作品级 `style_profile`。
- **写作注入**：每章生成时，`style_profile` 作为写作任务书的风格锚点段注入 drafter，
  与复用自 webnovel-writer 的**去 AI 味词表**（polish-guide：200+ 词黑名单 + 7 层句式规则）叠加，
  由 polisher step 自查自改。
- **验收挂钩**：产出与 `style_profile` 的贴合度是 §七红线的行为判据；盲测（Claude-vs-DeepSeek）
  用同一 `style_profile` + 同一词表，仅换 Provider，验证 DeepSeek 达线否。
- **V2**：文风锁定系统化（人称/语气/句式升级为可维护条目），承接 V1 锚点。

### ⭐ 焦点三：多用户存储层（重写，非迁移）

**背景**：源项目单机单书、文件系统当库 → Muse 多租户关系库 + 向量库重写。
把其五个存储面从文件系统映射为多租户 PG 表：

| 源存储面（文件系统） | Muse 表（多租户，均带 user_id + project_id） | 用途 |
|---|---|---|
| state | `story_state`（主角状态、世界规则、当前阶段） | 写前上下文 |
| index / contracts | `story_bible`（设定圣经条目：V1 全文 / V2 实体化） | 唯一创作依据 |
| summary | `chapter_cards`（章节卡片：事件/人物变化/新增事实/悬念/章末状态） | 长期上下文 |
| memory | `story_threads`（未回收伏笔 urgent_loops、线索） | 一致性防穿帮 |
| vector | `embeddings`（pgvector，chunk + 向量 + 元数据） | RAG 召回 |

- **数据模型：SQLAlchemy 2.0（async）+ Alembic 迁移**，不用 SQLModel（Pydantic V2 版本坑）。
- **向量：pgvector 0.8.x，HNSW 索引**；与关系数据同库，单人运维最省。
- **一致性投影事务**：章节定稿触发一次 `chapter-commit`，在**单事务**内投影回
  story_state / chapter_cards / story_threads / embeddings，保证多存储面原子一致（防半更新穿帮）。
- **探索会话**：`exploration_sessions` + `exploration_messages` + `story_clues`（对话与线索持久化）。
- **自由探索导航状态（2026-07-31 Correct Course 新增，Story 2.8）**：`exploration_session` 新增窄范围 `guidance_state`（JSONB）列，记录 7 项通用主干字段（题材/核心吸引力/主角/主要冲突/关键世界规则/整体气质/开篇钩子）的完成度（`missing`/`filled`/`skipped`）、当前待补字段、当前问题文本与 `readyToSettle` 布尔位。这是完成度与「下一问」的后端事实源，供 free settle 门禁与自由探索前端消费；**不与 `story_clues` 合并**——`story_clues` 仍是用户可直接编辑的事实展示区（含 `user_edited` 优先保护），`guidance_state` 只服务导航与门禁，两者职责边界不交叉。V1 不落完整置信度、证据来源或问题历史（EXP-P02 V2 范围）。

### ⭐ 焦点四：一致性机制迁移（借骨架 + 词表，丢网文审美）

**三段闭环**（照搬 webnovel-writer 机制，章数不设人为上限）：
1. **写前**：context-agent 把「story_bible + 最近 chapter_cards + 未回收 story_threads +
   世界规则 + 主角状态」压成写作任务书，喂给 drafter。
2. **写后**：data-agent 从定稿正文提取事件/状态变化/新增实体 → 结构化 JSON →
   一次 chapter-commit 投影回各存储面（见焦点三事务）。
3. **RAG 召回**：**向量 + tsvector 关键词 + RRF 融合 + rerank** 三级检索按相关性召回历史设定/情节，
   可选增强；无 embedding key 时退回纯关键词。真 BM25（pg_search）视需要 V2 引入。
- **embedding 供应商：国内（阿里 / 智谱），抽象为 `EmbeddingProvider` 接口**，数据不出境、与 DeepSeek 同区。
- **残留风险（写入文档）**：提取环节仍由 LLM（DeepSeek）完成，提取漏/错则后续穿帮 →
  一致性可靠性上限受模型质量牵制，绕回 §七红线，非独立可保。
- **GPL 合规护栏**：webnovel-writer 为 GPL。**采用 clean-room 重实现**——借机制思路、
  借 polish-guide 词表（作为数据/规则参考），**不直接复制其 GPL 源码**；
  正式实现前须创始人做许可证义务与商业形态兼容性评估（附录 A / E 待定项）。

---

### Decision Impact Analysis

**Implementation Sequence（依赖顺序）:**
1. 后端骨架 + 认证 + 多租户基础（模块 0）
2. 存储层数据模型 + Alembic 迁移（焦点三，五张核心表）
3. LLM Provider 抽象 + ARQ 任务框架（焦点一底座）
4. **【门禁】盲测 Claude-vs-DeepSeek（§七 Q2，必须在正文生成接入前）**
5. 探索 Explorer Agent（模块 1）→ 设定生成 + 文风锚点（模块 2 + 焦点二）
6. 创作编排五段流水线（模块 3，消费任务书）
7. 归档 data-agent + chapter-commit 投影（模块 4 + 焦点四写后段）
8. RAG 三级召回接入写前上下文（焦点四写前 + 召回）
9. 通读 + 只读分享 + AI 标识（模块 5）

**Cross-Component Dependencies:**
- 文风锚定（焦点二）依赖存储层的 style_profile + 编排的 polisher step；是红线验收前提。
- 一致性（焦点四）依赖存储层五表 + 编排的 context/data-agent；可靠性受 Provider 质量牵制。
- 用量计量横跨所有 LLM 调用；额度数值依赖盲测成本，是模块 0 用量能力的前置。
- 盲测门禁卡在「编排底座就绪」与「正文生成接入」之间，是 launch blocker 的硬时点。

## Implementation Patterns & Consistency Rules

### Pattern Categories Defined

**Critical Conflict Points Identified:** 15 处多 AI agent 可能各写各的地方，已逐条锁定。
**最高优先级张力**：前端原型已锁 **camelCase**（`allowCustom`/`changedFields`/`completedCount`），
后端 Step 4 已定 SQLAlchemy + PG（snake_case 惯例）——大小写边界必须钉死转换点，否则字段对不上。

### Naming Patterns

**JSON 字段大小写（跨端最关键）：DB=snake_case，API 边界转 camelCase。**
转换点唯一落在 Pydantic schema（`ConfigDict(alias_generator=to_camel, populate_by_name=True)`）。
- DB / ORM model / repository：snake_case（`user_id`, `chapter_card`, `changed_fields`）。
- API 出入参（前端可见）：camelCase（`userId`, `changedFields`）——与原型契约一致，前端零改动。
- Rationale：原型 5825 行 camelCase 不可动；PG 遵循自身惯例；两端各自地道，转换集中一处不散落。

**Database Naming Conventions：**
- 表名：**单数 snake_case**，沿用 Step 4 已写表名（`story_state`, `story_bible`, `chapter_card`,
  `story_thread`, `embedding`, `exploration_session`, `exploration_message`, `story_clue`）。
- 主键统一 `id`；外键 `<实体>_id`（`user_id`, `project_id`, `chapter_id`）。
- 索引 `idx_<表>_<列>`（`idx_chapter_card_project_id`）；所有业务表必带 `user_id` + `project_id`。

**API Naming Conventions：**
- 路径 RESTful 复数 + 层级，沿用原型：`/api/projects/{project_id}/chapters/{n}`、
  `/api/projects/{project_id}/explore`、`/api/projects/{project_id}/archive`。
- 路由参数 `{snake_case}`（`{project_id}`），与 Python/FastAPI 一致。
- 长时任务：`POST /api/.../chapters/{n}/generate → {taskId}`；`GET /api/tasks/{taskId}/events`（SSE）。

**Code Naming Conventions：**
- Python：交给 ruff 强制——函数/变量 snake_case、类 PascalCase、常量 UPPER_SNAKE。
- 前端 JS：沿用原型——变量/函数 camelCase；storage key **kebab-case 带 `muse-` 前缀**
  （`muse-exploration-mode`），且 V1 迁移后仅存 UI 态，业务数据一律走 API。

### Structure Patterns

**Project Organization（后端分层）：**
```
muse-backend/
  routers/         # FastAPI 路由，仅做入参校验 + 调 service，禁止直接查 model
  services/        # 业务编排
  repositories/    # 数据访问，DAO 层统一注入 user_id 租户守卫
  models/          # SQLAlchemy 2.0 ORM（snake_case）
  schemas/         # Pydantic V2（alias_generator=to_camel，边界转换点）
  orchestration/   # 五段流水线，每 step 一文件（context/drafter/reviewer/polisher/data_agent）
  providers/       # LLMProvider / EmbeddingProvider 抽象与实现
  core/            # settings、鉴权、错误封装、SSE
  migrations/      # Alembic（async）
tests/             # 镜像源码树的 pytest 布局
```
- 前端沿用原型 `prototype/app`（Vite 渐进增强），不重构目录。

### Format Patterns

**API Response Formats：**
- 成功：**直接返回资源体**（camelCase），不套 `{data:...}` 包装。
- 错误：统一 envelope `{code, message, detail}`（Step 4 已定），HTTP 状态码语义化（4xx/5xx）。
- 兼容原型状态位：登录/校验类错误在响应体附布尔位 `expired`/`invalid`/`locked`,对接原型既有分支。
- 时间：一律 ISO 8601 UTC 字符串（`2026-07-22T08:00:00Z`）；布尔用 `true/false`。

**Communication Patterns（SSE 事件）：**
- 事件名固定三类：`progress`（阶段进度）、`result`（最终结果）、`error`（失败）。
- payload 为 camelCase JSON；`progress` 至少含 `{step, percent}`,`error` 复用错误 envelope。

### Process Patterns

**LLM 调用（换模型后门 + 用量计量的生命线）：**
- **一律走 `LLMProvider` 接口**，业务层禁止直接 import/调用 openai SDK。
- tokens 与成本埋点统一在 Provider 层记账（托管归 Muse 账、BYOK 归用户账）。
- embedding 同理走 `EmbeddingProvider`；无 key 时 RAG 退回纯 tsvector 关键词。

**Error Handling & 编排可靠性：**
- 全局异常 → 统一 error envelope；用户可见文案与内部日志分离（日志结构化 + 全链路 trace）。
- 编排 step 幂等可重入，状态落 PG；失败由 ARQ 重试，成本按 step 累计（呼应断点续跑）。

**租户隔离（安全红线）：**
- 租户过滤在 repository 层强制注入 `user_id`,router/service 不得绕过直查 model。

### Enforcement Guidelines

**All AI Agents MUST：**
- 新增前端可见字段时，DB 写 snake_case、Pydantic schema 自动转 camelCase——**不得**在两端手写不一致字段名。
- 任何 LLM / embedding 调用只经 Provider 接口，附带用量记账。
- 任何业务查询经 repository 且携带 `user_id` + `project_id` 租户守卫。
- 长时生成一律「POST 返回 taskId + SSE 三事件」，不得用轮询或同步阻塞。

**Pattern Enforcement：**
- ruff + mypy 卡 Python 风格；schema 层 `alias_generator` 卡大小写；code review 卡租户守卫与 Provider 直调。

### Pattern Examples

**Good：** ORM `chapter_card.changed_fields`（snake）→ API 响应 `{"changedFields": [...]}`（camel），
前端原型直接读 `card.changedFields`,无需适配层。

**Anti-Pattern：** service 里 `openai.chat.completions.create(...)` 直调（绕过计量与后门）；
或 API 返回 `{"changed_fields": [...]}` 迫使前端改原型——**均禁止**。

## Project Structure & Boundaries

### Complete Project Directory Structure

```
muse/
├── README.md
├── docker-compose.yml              # PG(pgvector) + Redis 本地开发
├── prototype/                      # 前端契约（既定，Vite 渐进增强，不重构）
│   └── app/{index.html, styles.css, app.js, ...}
└── backend/                        # 从零自建
    ├── pyproject.toml              # uv 依赖管理
    ├── alembic.ini
    ├── .env.example
    ├── src/muse/
    │   ├── main.py                 # FastAPI 应用入口
    │   ├── core/                   # 横切基座
    │   │   ├── settings.py         # pydantic-settings 分环境
    │   │   ├── security.py         # JWT access+refresh、AES-GCM BYOK 加解密
    │   │   ├── errors.py           # 统一 error envelope {code,message,detail}
    │   │   ├── sse.py              # SSE 事件封装(progress/result/error)
    │   │   └── db.py               # async engine / session
    │   ├── models/                 # SQLAlchemy 2.0 ORM (snake_case)
    │   │   ├── base.py             # 带 id / user_id / project_id 的 Base mixin
    │   │   ├── account.py          # user、project、byok_key、usage_ledger
    │   │   ├── exploration.py      # exploration_session/message、story_clue
    │   │   ├── story.py            # story_state、story_bible、story_thread
    │   │   └── chapter.py          # chapter、chapter_card、embedding
    │   ├── schemas/                # Pydantic V2 (alias_generator=to_camel 边界)
    │   │   └── {account,exploration,story,chapter,task}.py
    │   ├── repositories/           # DAO：强制注入 user_id 租户守卫
    │   │   └── {base,account,exploration,story,chapter}_repo.py
    │   ├── services/               # 业务编排
    │   │   ├── auth_service.py
    │   │   ├── exploration_service.py
    │   │   ├── story_service.py    # 设定生成/文风锚点
    │   │   ├── chapter_service.py  # 批注/点评/改进/重生/定稿
    │   │   └── usage_service.py    # 额度护栏、计量
    │   ├── orchestration/          # 焦点一：五段流水线，每 step 一文件
    │   │   ├── pipeline.py         # 编排运行时（状态落 PG、可重入）
    │   │   ├── context_agent.py    # 写前：组装写作任务书
    │   │   ├── drafter.py          # 起草正文
    │   │   ├── reviewer.py         # 审查
    │   │   ├── polisher.py         # 去 AI 味（style_profile + polish-guide 词表）
    │   │   └── data_agent.py       # 写后：提取事实 → chapter-commit 投影
    │   ├── providers/              # 换模型后门 + 计量埋点唯一入口
    │   │   ├── llm.py              # LLMProvider 接口 + DeepSeek 实现
    │   │   └── embedding.py        # EmbeddingProvider 接口（阿里/智谱）
    │   ├── rag/                    # 焦点四：三级召回
    │   │   └── retrieval.py        # 向量 + tsvector + RRF 融合 + rerank
    │   ├── tasks/                  # ARQ 异步任务
    │   │   └── worker.py           # 章节生成、探索整理
    │   └── routers/                # 仅校验入参 + 调 service
    │       ├── auth.py, exploration.py, story.py, chapter.py
    │       ├── archive.py, share.py    # 归档、只读分享
    │       └── tasks.py                # POST 提交 + GET /events SSE
    ├── migrations/                 # Alembic async
    └── tests/                      # 镜像 src 树的 pytest 布局
```

### Architectural Boundaries

**API Boundaries：**
- `/api/**` 全部经 JWT 鉴权（登录/注册除外）；OpenAPI 自动生成。
- 常规 CRUD 走 REST；长时生成 = `POST /api/projects/{project_id}/chapters/{n}/generate → {taskId}`
  + `GET /api/tasks/{taskId}/events`（SSE：progress/result/error）。
- 出入参 camelCase（原型契约），内部 snake_case，转换点唯一在 schemas 层。

**Component Boundaries：**
- 前端沿用原型（vanilla JS + hash 路由 + Vite），业务数据全走 `/api`,localStorage 仅存 UI 态。
- 后端严格分层：`routers`（仅校验+分发）→ `services`（业务）→ `repositories`（数据+租户守卫）。
- router 不得直查 model；service 不得绕过 repository。

**Service Boundaries：**
- `orchestration/` 与 `services/` 调模型只能经 `providers/`（换模型后门 + 计量埋点唯一入口）。
- 五段流水线每 step 独立、幂等可重入，状态落 PG，由 `tasks/worker`(ARQ) 驱动，经 `core/sse` 回传。

**Data Boundaries：**
- 所有业务查询经 repository 且携带 `user_id` + `project_id`（行级租户隔离）。
- 向量与关系数据同库（pgvector 0.8.x，HNSW）；BYOK 密钥 AES-GCM 加密后落 PG。
- 章节定稿触发**单事务** chapter-commit，原子投影回 story_state/chapter_card/story_thread/embedding。

### Requirements to Structure Mapping

**模块 → 结构映射：**
- 模块0 账户/作品：`routers/auth` + `services/{auth,usage}_service` + `models/account`（含 byok_key、usage_ledger）
- 模块1 探索：`routers/exploration` + `services/exploration_service`(Explorer Agent) + `models/exploration`
- 模块2 故事设定：`routers/story` + `services/story_service`(设定+文风锚点) + `models/story`(story_bible/state)
- 模块3 创作：`routers/chapter` + `routers/tasks` + `services/chapter_service` + `orchestration/*` + `models/chapter`
- 模块4 归档：`routers/archive` + `orchestration/data_agent`(chapter-commit) + `models/chapter`(chapter_card, story_thread)
- 模块5 通读/交付：`routers/share` + `services/story_service.readonly` + 对象存储（分享页/导出件）

**Cross-Cutting Concerns：**
- 认证/租户：`core/security` + `repositories/base_repo`(守卫) + 所有 router 依赖注入。
- 用量计量：`providers/*`(埋点) + `services/usage_service`(额度护栏) + `models/account.usage_ledger`。
- 文风红线：`services/story_service`(锚点抽取) → `orchestration/polisher`(注入+自查) → 盲测门禁。
- 一致性：`orchestration/{context_agent,data_agent}` + `rag/retrieval` + 焦点三五表。

### Integration Points

**Internal Communication：** router → service → repository 同步调用；长时任务经 ARQ 入队，
worker 执行五段流水线，进度/结果经 Redis + SSE 推前端。
**External Integrations：** DeepSeek(LLM，切 base_url)、阿里/智谱(embedding)、对象存储(导出/分享)；
均经 provider/adapter 抽象，数据不出境、与 DeepSeek 同区。
**Data Flow：** 探索对话 → 设定圣经 + 文风锚点 → 写前 context-agent 组装任务书（含 RAG 召回）→
五段流水线生成正文 → 定稿 chapter-commit 投影回各存储面 → 归档卡片 → 通读/只读分享。

### File Organization Patterns

**Configuration：** 根 `pyproject.toml`/`alembic.ini`/`.env.example`；运行期配置经 `core/settings`(分环境)。
**Source：** 按「层」组织（routers/services/repositories/models/schemas），编排与 provider 独立成域。
**Test：** `tests/` 镜像 `src/muse/` 树，pytest + pytest-asyncio。
**Asset：** 前端静态资源留在 `prototype/app`；导出件/分享页走对象存储。

### Development Workflow Integration

**Dev Server：** `docker-compose` 起 PG(pgvector)+Redis；`uv run` 起 FastAPI；Vite HMR 起前端。
**Build：** 后端 uv 锁依赖、ruff+mypy 卡关；前端 Vite 打包。
**Deploy：** 国内云（阿里/腾讯），与 DeepSeek 同区，满足 ICP 备案与数据合规。

## Architecture Validation Results

### Coherence Validation ✅

**Decision Compatibility:**
技术栈互相自洽且版本已联网核实：SQLAlchemy 2.0 + Pydantic V2 分离（规避 SQLModel 0.0.31 坑）、
pgvector 0.8.x（HNSW+RRF）、DeepSeek（OpenAI SDK 兼容切 base_url）、ARQ（async 原生 + Redis）。
无相互矛盾的决策。

**Pattern Consistency:**
camelCase ↔ snake_case 转换点唯一收敛在 Pydantic schema 层，与原型 camelCase 契约零冲突；
`LLMProvider` 唯一入口同时满足「换模型后门」与「用量计量」两个决策，不散落。命名/结构/通信约定一致。

**Structure Alignment:**
分层目录（routers→services→repositories）支撑行级租户守卫；orchestration 每 step 独立支撑断点续跑；
models/chapter + 单事务 chapter-commit 支撑多存储面原子一致。边界闭合，无悬空集成点。

### Requirements Coverage Validation

**模块 Coverage:** 6 个开发模块全部有结构落点（见「Requirements to Structure Mapping」）✅
**Functional Requirements Coverage:** 各模块能力版本矩阵均映射到 router/service/model ✅
**Non-Functional Requirements Coverage:**
- 文字质量红线 → 盲测门禁 + 文风锚定（焦点二）+ polisher 词表 ✅
- 长时异步 → ARQ + SSE（progress/result/error）✅
- 多租户隔离 → 行级 user_id + DAO 层守卫 ✅
- 长程一致性 → 焦点三五表 + 焦点四三段闭环 ✅
- 成本护栏 → Provider 计量 + usage_ledger + 额度校验 ✅
- 合规：AI 强制标识有落点 ✅；数据/版权政策、GPL 义务评估仍为 PRD 待定项 ⚠️

### Implementation Readiness Validation

**Decision Completeness:** 关键决策均含版本与 rationale；换模型/计量/租户等约束可执行。
**Structure Completeness:** 完整目录树到文件级；边界与集成点明确。
**Pattern Completeness:** 15 处冲突点逐条锁定，含正/反例与强制项。

### Gap Analysis Results

**Critical Gaps（0）：** 无阻塞实现的硬缺口。

**Important Gaps（3，多为 PRD 既有待定项，非本次架构疏漏）：**
1. **盲测未执行** → 单章成本未知，托管免费额度数值无法定。已列为实施顺序第 4 步门禁（launch blocker 硬时点）。
2. **GPL 许可证义务评估未做** → 焦点四 clean-room 重实现的合规边界需创始人拍板（PRD 附录待定项）。
3. **数据/版权政策未定** → 影响数据治理与用户内容归属条款（PRD 待定项）。

**Nice-to-Have Gaps：** 真 BM25(pg_search) V1 用 tsvector 近似；embedding 供应商（阿里 vs 智谱）具体选型待定。

### Validation Issues Addressed
3 个重要缺口本质为业务/合规决策（需创始人拍板盲测与合规），非架构层可补；
架构已为其预留门禁（盲测第 4 步）与抽象（EmbeddingProvider、clean-room 护栏），不阻塞骨架实现。

### Architecture Completeness Checklist

**Requirements Analysis**
- [x] Project context thoroughly analyzed
- [x] Scale and complexity assessed
- [x] Technical constraints identified
- [x] Cross-cutting concerns mapped

**Architectural Decisions**
- [x] Critical decisions documented with versions
- [x] Technology stack fully specified
- [x] Integration patterns defined
- [x] Performance considerations addressed

**Implementation Patterns**
- [x] Naming conventions established
- [x] Structure patterns defined
- [x] Communication patterns specified
- [x] Process patterns documented

**Project Structure**
- [x] Complete directory structure defined
- [x] Component boundaries established
- [x] Integration points mapped
- [x] Requirements to structure mapping complete

### Architecture Readiness Assessment

**Overall Status:** READY WITH MINOR GAPS
（16 项清单全绿、无 Critical Gap；但盲测门禁未过、两项合规待定，故不标满级 READY FOR IMPLEMENTATION。
后端骨架至编排底座可立即开工，正文生成接入须待盲测门禁通过。）

**Confidence Level:** High

**Key Strengths:**
- 页面即契约，前端不确定性低，后端逐页实现路径清晰。
- Provider 抽象把「换模型 / 计量 / 合规区域」三件事收敛到单一入口。
- 断点续跑（step 落 PG）+ 单事务 chapter-commit，从结构上防长程穿帮与半更新。

**Areas for Future Enhancement:**
- 盲测出单章成本后回填托管免费额度线。
- 合规评估完成后解锁焦点四正式实现；embedding 选型定档。
- V2：设定圣经实体化、文风锁定系统化、真 BM25。

### Implementation Handoff

**AI Agent Guidelines:**
- 严格遵循本文档所有架构决策与一致性规则。
- LLM/embedding 调用只经 Provider；业务查询只经 repository 且带租户守卫。
- 尊重目录结构与边界；架构问题一律回查本文档。

**First Implementation Priority:**
执行 Starter 章节的初始化命令（`uv init muse-backend` + FastAPI/SQLAlchemy/Alembic 骨架），
按 Decision Impact Analysis 的 9 步实施顺序推进；第 4 步盲测门禁为正文生成接入的硬前置。
