---
stepsCompleted: [1, 2, 3, 4]
inputDocuments:
  - Muse-PRD-V1.md
  - Muse-PRD-V1-addendum.md
  - _bmad-output/planning-artifacts/architecture.md
  - prototype/spec/prototype-spec.md
  - prototype/spec/exploration-pending-requirements.md
  - prototype/README.md
  - prototype/app/index.html
  - prototype/app/styles.css
  - prototype/app/app.js
scope: 'V1 · 打通（Walking Skeleton）'
project_name: 'Muse'
---

# Muse - Epic 分解

## 概述

本文档把 Muse **V1（打通 · Walking Skeleton）** 的需求，从 PRD 主文档、技术附录、架构决策与原型规格（页面即契约）分解为可实现的 Story。

**范围声明**：仅覆盖 V1 能力档。V2/V3 能力不在本文档，待 V1 跑通与盲测门禁验证后另立。
**产品定位（2026-07-22 澄清）**：Muse 面向**广谱网文**创作（修仙/都市/言情/悬疑/游戏等），核心卖点是「锁用户爱读的文风」——不是无脑套通用爪点。注意：PRD 附录、architecture、prfaq 有多处旧措辞写「文学向」（如 addendum:42、architecture:238、prfaq:260），均属笔误，以本条「广谱网文 + 锁文风」为准，上游文档待统一回改。此定位不推翻记忆里的目标用户画像（被烂尾气到想重写的重度读者，本就是网文读者）。
**设定字段来源**：故事设定字段集借鉴 webnovel-writer（`init-collection-schema.md`，40 字段/6 组）重塑为广谱网文向，但**只借「产出物字段结构」，不借「表单式采集流程」**——Muse 探索是对话渐进发掘（PRD 模块 1、EXP-P01），非逐格填表。详见 FR12 / AR8。
**方法论前提**：AI 编程、页面即契约，开发最小单元是页面；V1 本质 = 逐页把原型 mock 替换为「真实 AI 能力 + 多用户持久化」，页面形态基本不动。原型代码（`prototype/app/`）为契约的最终事实基准。**交付节奏（2026-07-30 修订）**：放弃早期「后端先行、前端 later 统一接」的旧节奏（该节奏导致 Epic 1-3 后端全 done 但 `app.js` 至今零 fetch、API 从未经真实前端验证），转向**前后端一起走**——新 story 默认前后端一起交付，不再默认「后端 only、app.js 零改动」；Epic 1-3 积压的接线债由 **Epic 7** 集中偿还。
**能力版本说明**：本文所有 FR/NFR/需求默认限定在 PRD 定义的 V1 档；V2/V3 增强不重复列出。

## 需求清单（V1）

### 功能需求（FR）

> PRD 以「6 开发模块 × 能力版本」矩阵组织，不用传统 FR 编号。以下按开发模块归纳 V1 能力为可测试的 FR。

**模块 0 · 账户与作品管理**

- **FR1**：用户可用邮箱 + 密码注册（需邀请码）与登录，系统签发并维持真实会话（access + refresh）。
- **FR2**：用户可新建、重命名、删除作品，作品列表真实持久化；支持空状态与列表加载失败状态。
- **FR3**：作品行主操作「继续创作」跳转到该作品当前所处的创作步骤（探索 / 章节 / 归档）。
- **FR4**：用户可在设置页绑定自己的 API Key（BYOK），绑定后该账户/作品的生成走用户 Key；托管默认路径受免费额度护栏约束（设置页与用量入口原型无，须新增）。

**模块 1 · 探索**

- **FR5**：新建作品时在「引导探索」与「自由探索」间二选一；进入后模式独立、不在探索途中切换；两模式产出同一套故事设定。
- **FR6**：引导探索接入真实 Explorer Agent（V1 用有限问题集，非动态选题），纯选项式沉浸问答、一次聚焦一题；第一题可用一句话自述作答，其余题提供「都不是这些」自答出口。
- **FR7**：引导探索支持问卷式前后翻页（底部导航按可用性显示、两端留空占位）；翻页不清除答案；翻回已答题高亮上次所选、回填自述内容；重选只更新该题、不影响其后答案。
- **FR8**：引导探索答完最后一题先进入「整理中」过渡态（约 1.2 秒），再弹出故事设定卡；中途「回到探索」则过渡态复位、回到可翻页修改的收尾态。
- **FR9**（2026-07-31 Correct Course 修订）：用户可从故事想法、主角、核心冲突、世界与氛围任一入口开始自由探索；系统依据已有材料主导补齐设定主干缺项，每轮只提出一个具体问题（连续只读对话记录，不折叠不拆分）。用户可自行输入，卡住时可按需查看 AI 生成的 2–4 个回答思路并直接选择，也可跳过当前项；Agent 不替用户决定故事。右侧「故事线索」区可直接编辑，用户编辑优先、不被自动整理覆盖。
- **FR10**（2026-07-31 Correct Course 修订）：自由探索的「整理为故事设定」仅当题材、核心吸引力、主角、主要冲突、关键世界规则、整体气质、开篇钩子 7 项通用主干均已补齐（`filled`）或经用户跳过后由系统谨慎归纳（`skipped`），且用户主动点击时才开放；题材特化字段与文风锚点不阻塞该门禁。
- **FR11**：探索对话与故事线索真实持久化；待确认设定卡在浏览器会话内恢复，刷新不回退到探索主界面，确认后清除待确认状态。

**模块 2 · 故事设定（设定圣经）**

- **FR12**：探索结束真实生成故事设定候选卡，字段集对齐 webnovel-writer 的设定结构并按 Muse 广谱网文定位重塑（**借字段结构，不借表单式采集——设定由探索对话渐进聊出，非逐格填表**）。定稿字段集（12 项，V1 一次建全 schema、特化字段可空）：
  - **通用主干（7，所有题材必备）**：① 题材 genre（决定下方特化字段是否激活）② 核心吸引力（并入「一句话故事 + 核心卖点 + 目标阅读体验」）③ 主角（姓名 + 核心欲望 + **致命缺陷 flaw**）④ 主要冲突（核心对抗 + **反派镜像**：与主角共享欲望却走反路）⑤ 关键世界规则（世界规模 + 硬约束）⑥ 整体气质 ⑦ **开篇钩子**（第一章拿什么抓住人，网文命脉）。
  - **题材特化（4，按 genre 激活，不匹配则不问 / 可空）**：⑧ 力量体系（境界链 / 升级规则，修仙玄幻）⑨ 金手指（类型 / 可见度 / 不可逆代价 / 成长节奏，系统爽文）⑩ 感情线（男女主配置 / 感情节奏，言情）⑪ 势力格局（宗门 / 阵营，设定重题材）。
  - **Muse 独有卖点（1）**：⑫ 文风锚点 `style_profile`（见 FR16，webnovel-writer 无）。
  - 说明：原型六项（核心吸引力 / 主角与欲望 / 主要冲突 / 关键世界规则 / 整体气质 / 目标阅读体验）为暂定未定稿，本 FR 以上表替换；「目标阅读体验」并入②核心吸引力不单列（对齐 webnovel-writer 做法，避免与⑥整体气质重叠）。V1 探索用有限问题集，不保证凑齐特化字段；覆盖度驱动的「必须凑齐才放行」属 EXP-P02（V2）。
- **FR13**：设定候选卡可直接编辑；向同一探索 Agent 反馈后生成新版本，提升版本号并标出本轮变化项。
- **FR14**：用户确认设定后，设定成为只读的全文指导上下文，注入后续所有创作。
- **FR15**：「回到探索」需二次确认，确认后丢弃当前设定内容与修改记录。
- **FR16**：设定阶段用户可锚定文风——从预置样本库选择或粘贴一段自己爱读的文字，系统抽取作品级 `style_profile`（人称、语气、句式节奏、意象密度、段落长度倾向）（入口原型无，须新增）。即 FR12 字段⑫，是 webnovel-writer 完全没有的 Muse 独有卖点（锁用户文风），也是 NFR1 红线验收前提。

**模块 3 · 创作**

- **FR17**：确认设定后，首个阶段规划（阶段目标 + 章节骨架）全程幕后完成，不展示、无确认弹窗，用户体感直接进入第一章。
- **FR18**：真实生成章节正文，消费「故事设定 + 已定稿章节 + 归档卡片」作上下文；用户可选填「本章想法」引导本章。
- **FR19**：章节正文支持分页阅读；支持段落批注与整体点评。
- **FR20**：「改进本章」要求具体反馈并尽量保留现有内容；「重新生成整章」允许不填反馈、替换整章并清除旧批注；段落批注 + 整体点评共同作为「改进本章」的输入。
- **FR21**：「定稿本章」后，当前版本成为后续章节创作的正式上下文。
- **FR22**：阶段循环幕后推进（用户无感）；阶段交界处提供一个极轻、可跳过的方向输入（「这一段想往哪走？/ 直接继续」），是用户主动表达进入收尾的唯一控制点，不可省略。

**模块 4 · 归档（故事档案统一入口）**

- **FR23**：章节定稿后真实生成章节卡片（本章发生了什么 / 人物变化 / 新增事实与线索 / 未解决悬念 / 章末状态）并持久化；写下一章时作为长期上下文注入。
- **FR24**：归档页作为故事档案统一入口——顶部展示已确认的设定圣经，下方是分阶段的章节归档，一处即可查阅「我定下的规则 + 我已写下的事实」。
- **FR25**：归档页首屏为清爽概览，设定圣经与各阶段默认收起，点击行标题展开/收起（带高度动画），状态互相独立、由用户自由控制。

**模块 5 · 通读与交付**

- **FR26**：提供全本连续通读视图，按顺序连续呈现已定稿章节，让用户从头读一遍自己的书。

### 非功能需求（NFR）

- **NFR1 · 文字质量红线（launch blocker）**：正文须通过「去 AI 味」行为红线，验收判据为**风格锚定**（是否像用户锚定的文风），采用三档判据（不及格 / 及格线 / 理想）。判据落在两根正交轴上（对齐 PRD §7.1）：
  - **轴 A · 风格贴合（正向，主判据）**：产出像不像用户锚定样本的味道。以**创始人单人盲评**量化——对 N 篇匿名对照样本（不同 Provider 产出混同、评测者不知来源）逐篇三级打分：不像=0 / 出戏=1 / 像=2。
  - **轴 B · 去 AI 味（负向，硬底线）**：以复用 webnovel-writer `polish-guide`（200+ 词黑名单 + 7 层句式规则）量化两项——**黑名单词频**（每千字命中数）与**重度句式套路数**（万能金句结尾 / 强行排比 / 「不是 X 而是 Y」对仗滥用等）。
  - **及格线（上线门槛）= 以下三条同时满足**：① 风格贴合判「像」（≥1 分且多为 2 分）篇数 **≥ 2/3**；② 重度句式套路 **= 0 处**；③ 黑名单词频 **≤ 锚定样本自身的 1.5 倍**（无样本基准时兜底 ≤ 3 词/千字）。风格贴合是硬条件但只要求多数（≥2/3）通过，去 AI 味两项为不可破硬底线。**单人盲评无「多人多数决」，稳健性从「多人」迁到「多篇」**——以「判像篇数比例 ≥2/3」替代多数决，作为客观触发条件。
  - 盲测（Claude-vs-DeepSeek，同一 `style_profile` + 同一去 AI 味词表，仅换 Provider）须在**正文生成接入前**完成（见 Story 4.1）。这是全项目头号未验证生死假设。
- **NFR2 · 长时异步生成**：写一章 = context→drafter→reviewer→polisher→data-agent 多次 LLM 调用叠加（按 5–10 次/章量级），须异步任务模型：`POST 提交 → 返回 taskId → GET /events SSE 推送`，不得同步阻塞或前端轮询。
- **NFR3 · 多租户隔离**：所有业务数据带 `user_id`（+ `project_id`）行级隔离，repository/DAO 层强制注入租户守卫；BYOK 密钥按账户/作品隔离，杜绝越权。
- **NFR4 · 长程一致性**：一致性机制按「几百章」设计，**不设人为章数上限**（不得砍成 20–50 章）；状态 / 人物 / 世界规则 / 时间线 / 伏笔不穿帮。
- **NFR5 · 成本 / 用量护栏**：每次 LLM 调用记 tokens 与成本（托管归 Muse 账、BYOK 归用户账）；托管路径校验免费额度上限（具体数值待盲测出单章真实成本后定）；BYOK 卸载重度用户成本。
- **NFR6 · 安全**：JWT access + refresh 双 token；BYOK 密钥应用层 AES-GCM 加密后存 PG，主密钥放环境变量 / 云 KMS。
- **NFR7 · 合规**：（a）AI 辅助生成内容强制标识（2025.9.1 起），V1 须在通读视图标注「AI 辅助生成」；（b）webnovel-writer 为 GPL，一致性机制须 **clean-room 重实现**（借思路 + 借 polish-guide 词表作规则参考，不直接复制 GPL 源码），正式实现前须创始人做许可证义务评估；（c）数据 / 版权政策未定（创始人待拍板）。
- **NFR8 · 数据不出境 / 部署合规**：LLM（DeepSeek）与 embedding（阿里 / 智谱）同区，部署国内云（阿里 / 腾讯），满足 ICP 备案与数据合规。

### 附加需求（来自架构决策）

**Starter / 基座（对应 Epic 1 Story 1）**

- **AR1 · Starter 模板**：采用**轻量 FastAPI 手工骨架**（非整体脚手架）。初始化命令作为第一个实现 Story 执行：`uv init muse-backend` + `fastapi[standard]` / `sqlalchemy>=2.0` / `alembic` / `pydantic-settings` / `psycopg` / `pgvector` / `openai` / `python-jose` / `passlib`；`alembic init -t async`；前端保留原型 + Vite 渐进增强。
- **AR2 · 后端分层结构**：`routers`（仅校验 + 分发）→ `services`（业务编排）→ `repositories`（数据 + 租户守卫）→ `models`（SQLAlchemy 2.0）/ `schemas`（Pydantic V2）；`orchestration` / `providers` / `rag` / `tasks` / `core` 独立成域。

**通用类决策**

- **AR3 · 认证**：JWT 自建（python-jose）access + refresh 双 token。
- **AR4 · 命名与大小写边界**：DB = snake_case，API 边界转 camelCase（与原型 5825 行 camelCase 契约一致）；转换点唯一收敛在 Pydantic schema（`alias_generator=to_camel, populate_by_name=True`）；前端 storage key = kebab-case 带 `muse-` 前缀且仅存 UI 态。
- **AR5 · API 风格**：REST + SSE。常规 CRUD 走 REST（FastAPI 自动 OpenAPI）；长时生成走 `POST → taskId` + `GET /events`（SSE 三事件 `progress` / `result` / `error`）；错误统一 envelope `{code, message, detail}`，兼容原型 `expired` / `invalid` / `locked` 布尔位；成功直接返回资源体（camelCase，不套 `data` 包装）；时间用 ISO 8601 UTC。
- **AR6 · 限流**：按用户 + 端点限流，配合托管免费额度护栏，触顶返回明确提示。

**存储层（焦点三，五张核心表 + 会话/账户表）**

- **AR7 · 数据模型**：SQLAlchemy 2.0（async）+ Alembic 迁移，**不用 SQLModel**（Pydantic V2 版本坑）。
- **AR8 · 五张一致性核心表**（均带 `user_id` + `project_id`）：`story_state`（主角状态/世界规则/当前阶段）、`story_bible`（设定圣经条目，V1 全文）、`chapter_card`（章节卡片）、`story_thread`（未回收伏笔/线索）、`embedding`（pgvector chunk + 向量 + 元数据）。
  - **`story_bible` 字段结构（V1 一次建全、特化字段可空，见 FR12）**：字段集参照 webnovel-writer `init-collection-schema.md` 的 6 组结构（`project`/`protagonist`/`relationship`/`golden_finger`/`world`/`constraints`）**重塑为广谱网文向**——通用主干 7 项（genre / 核心吸引力 / 主角[name+desire+flaw] / 冲突[+反派镜像] / 世界规则 / 整体气质 / 开篇钩子）为必备列；题材特化 4 项（力量体系 / 金手指 / 感情线 / 势力格局）按 genre 可空；另加 Muse 独有 `style_profile`（webnovel-writer 无）。**采集方式不照搬**：webnovel-writer 是表单式逐格填 + 充分性闸门，Muse 是探索对话渐进产出（模块 1）。**GPL 护栏**：字段结构作为「数据模型参考」clean-room 重实现，不复制其 GPL 源码（见 NFR7）。
- **AR9 · 账户 / 探索表**：`account`（user / project / byok_key / usage_ledger）；`exploration_session` / `exploration_message` / `story_clue`。
- **AR10 · 向量库**：pgvector 0.8.x，HNSW 索引，与关系数据同库；BYOK 密钥 AES-GCM 加密后落 PG。

**模型接入层 / 编排（焦点一）**

- **AR11 · 编排运行时**：自建轻量五段流水线（非 LangGraph）：`context-agent → drafter → reviewer → polisher → data-agent`；每 step 幂等可重入、状态落 PG（天然断点续跑），失败由 ARQ 重试、成本按 step 累计。
- **AR12 · LLMProvider 抽象**：定义 `LLMProvider` 接口（chat / stream / count_tokens），DeepSeek 为默认实现（OpenAI SDK 兼容，切 base_url；`deepseek-v4-pro` 思考档 / `deepseek-v4-flash` 快档，128K）；**业务层禁止直接 import/调用 openai SDK**，换模型 = 换实现。
- **AR13 · 任务队列**：ARQ（async 原生 + Redis broker），承载章节生成、探索整理等后台任务，经 SSE 回传进度。
- **AR14 · 用量计量**：tokens 与成本埋点统一在 Provider 层记账；`usage_service` 校验托管免费额度护栏。

**文风锚定（焦点二）**

- **AR15 · 文风锚定机制**：设定阶段抽取 `style_profile` → 每章生成时作为写作任务书的风格锚点段注入 drafter，与复用自 webnovel-writer 的去 AI 味词表（polish-guide：200+ 词黑名单 + 7 层句式规则）叠加，由 polisher step 自查自改。是 NFR1 红线的验收前提。

**一致性机制（焦点四）**

- **AR16 · 写前上下文组装**：context-agent 把「story_bible + 最近 chapter_cards + 未回收 story_threads + 世界规则 + 主角状态」压成写作任务书喂给 drafter。
- **AR17 · 写后投影（chapter-commit）**：data-agent 从定稿正文提取事件 / 状态变化 / 新增实体 → 结构化 JSON → **单事务** chapter-commit 原子投影回 story_state / chapter_card / story_thread / embedding（防半更新穿帮）。
- **AR18 · RAG 三级召回**：向量（pgvector HNSW）+ tsvector 关键词 + RRF 融合 + rerank；`EmbeddingProvider` 抽象（阿里 / 智谱），无 embedding key 时退回纯 tsvector 关键词。真 BM25（pg_search）V1 用 tsvector 近似，视需要 V2 引入。

**实施门禁与顺序**

- **AR19 · 盲测门禁（硬时点）**：Claude-vs-DeepSeek 盲测 = 实施顺序第 4 步，卡在「编排底座就绪」与「正文生成接入」之间，是 launch blocker 的硬时点。后端骨架至编排底座可先行开工，正文生成接入须待盲测通过。
- **AR20 · 依赖实施顺序**：① 骨架 + 认证 + 多租户 → ② 存储层五表 + 迁移 → ③ LLMProvider + ARQ 底座 → ④【门禁】盲测 → ⑤ 探索 Explorer → 设定 + 文风锚点 → ⑥ 创作五段流水线 → ⑦ 归档 data-agent + chapter-commit → ⑧ RAG 三级召回接入写前 → ⑨ 通读 + AI 标识。
- **AR21 · 部署基础设施**：国内云（阿里 / 腾讯）；PostgreSQL 托管 RDS + pgvector、Redis（ARQ broker + SSE/缓存）、对象存储；`docker-compose` 起本地 PG + Redis。

### UX 设计需求（原型规格 = 页面即契约）

> 在「页面即契约、形态基本不动」的方法论下，UX 工作分两类：（A）原型**无、V1 须新增**的入口；（B）逐页替换 mock 时**须严格保持**的关键交互契约（作为各 Story 的 AC 事实来源）。

**A 类 · 原型须新增的 UI**

- **UX-DR1 · 文风样本锚点入口**：在设定阶段（模块 2）新增「从预置样本库选择 / 粘贴一段自己爱读的文字」的锚点入口；Explorer / 设定页原型均无此入口。是 NFR1 红线验收的前提。
- **UX-DR2 · BYOK 设置页 + 托管用量入口**：账户层新增 API Key 绑定页与托管用量 / 剩余免费额度展示；原型无。
- **UX-DR3 · AI 辅助生成标识**：通读视图（V1）须标注「AI 辅助生成」，满足强制标识合规。

**B 类 · 须严格保持的关键交互契约**

- **UX-DR4 · 引导探索交互契约**：只呈现当前一题 + 选项，不显示已答历史、无右侧线索区；第一题一句话自述、其余题「都不是这些」出口；底部导航翻页按可用性显示（首题无「上一题」、进度外无「下一题」，该侧留空占位）；翻页不清除答案、翻回高亮回填、重选只更新该题；答完进「整理中」过渡态再弹设定卡。
- **UX-DR5 · 自由探索交互契约**（2026-07-31 Correct Course 修订，V1 EXP-P02 最小能力，见 Story 2.8）：只读连续对话记录不折叠不拆分；右侧线索区直接编辑、用户编辑优先不被自动整理覆盖。五态交互取代原「给我一些方向」固定文案：① **零对话起点**——展示「你想从哪里开始？」四个产品入口（故事想法 / 主角 / 核心冲突 / 世界与氛围），点击后 Agent 生成对应第一问，入口本身不是 AI 建议；② **当前具体问题**——Agent 每轮只围绕一个最缺的通用主干项提出一句具体问题，置于对话流内；③ **按需回答思路**——用户点「没想好？看看几个思路」才生成当前问题相关的 2–4 个 AI 回答选项，点击任一选项即直接提交为本轮回答；④ **跳过**——用户点「先跳过这个问题」，该项标记为已处理、系统据已有材料谨慎归纳，不再反复追问；⑤ **完成收束**——7 项主干（题材/核心吸引力/主角/主要冲突/关键世界规则/整体气质/开篇钩子）均已补齐或跳过后，Agent 给出明确收束提示，「整理为故事设定」按钮才开放。
- **UX-DR6 · 设定卡交互契约**：候选卡可直接编辑；反馈后升版本号 + 标变化项；「回到探索」二次确认后丢弃设定与修改记录；待确认卡会话内恢复、刷新不回退、确认后清除待确认态。
- **UX-DR7 · 章节创作交互契约**：可选填本章想法 → 生成 → 分页阅读 → 段落批注 + 整体点评 → 改进本章 / 重新生成整章 → 定稿；改进要具体反馈并保留内容、重生可空反馈替换整章并清旧批注；阶段交界极轻可跳过方向输入（收尾控制点，不可省略）。
- **UX-DR8 · 归档页交互契约**：故事档案统一入口；顶部设定圣经 + 下方分阶段章节归档；首屏默认收起、点击行标题展开/收起带高度动画、状态互相独立。
- **UX-DR9 · 错误 / 边界状态对接**：登录 `expired` / `invalid` / `locked`、作品库 `empty` / `error` 等原型状态位对接后端 error envelope 的布尔位分支。

### FR 覆盖图

| FR | Epic | 说明 |
|---|---|---|
| FR1 | Epic 1 | 邮箱+密码注册（邀请码）与登录，真实会话 |
| FR2 | Epic 1 | 作品新建/重命名/删除 + 持久化 + 空/失败状态 |
| FR3 | Epic 1 | 「继续创作」跳转到当前所处创作步骤 |
| FR4 | Epic 1 | BYOK 绑定 Key + 托管免费额度护栏 |
| FR5 | Epic 2 | 新建时引导/自由二选一，模式独立、产出同一套设定 |
| FR6 | Epic 2 | 引导探索接入真实 Explorer Agent（有限问题集）+ 沉浸问答 |
| FR7 | Epic 2 | 引导探索问卷式前后翻页、翻回高亮回填、重选只更新该题 |
| FR8 | Epic 2 | 引导探索答完进「整理中」过渡态再弹设定卡 |
| FR9 | Epic 2 | 自由探索真实对话 + 系统主导补齐设定主干 + 按需 AI 回答思路，不代答（2026-07-31 修订，见 Story 2.8/UX-DR5） |
| FR10 | Epic 2 | 自由探索「整理为故事设定」须 7 项主干全部补齐/跳过后才开放（2026-07-31 修订，见 Story 2.8） |
| FR11 | Epic 2 | 探索对话与线索持久化、待确认卡会话内恢复 |
| FR12 | Epic 3 | 真实生成 12 字段设定候选卡（广谱网文向，借 webnovel-writer 结构） |
| FR13 | Epic 3 | 设定卡可编辑、反馈后升版本号+标变化项 |
| FR14 | Epic 3 | 确认后成只读全文指导上下文，注入后续创作 |
| FR15 | Epic 3 | 「回到探索」二次确认后丢弃设定与修改记录 |
| FR16 | Epic 3 | 文风锚点：选/粘样本 → 抽 style_profile（独有卖点） |
| FR17 | Epic 4 | 首个阶段规划全程幕后，用户体感直接进第一章 |
| FR18 | Epic 4 | 真实生成章节正文，消费设定+已定稿章节+归档卡片；可选填本章想法 |
| FR19 | Epic 4 | 分页阅读 + 段落批注 + 整体点评 |
| FR20 | Epic 4 | 改进本章（要反馈保留内容）/ 重生整章（可空反馈清旧批注） |
| FR21 | Epic 4 | 定稿本章 → 成后续章节正式上下文 |
| FR22 | Epic 4 | 阶段循环幕后推进 + 阶段交界可跳过方向输入（收尾控制点） |
| FR23 | Epic 5 | 定稿后真实生成章节卡片 + 持久化 + 下一章上下文注入 |
| FR24 | Epic 5 | 归档页 = 故事档案统一入口（设定圣经+分阶段章节归档） |
| FR25 | Epic 5 | 归档页首屏清爽概览、点击行标题展开/收起带动画、状态独立 |
| FR26 | Epic 6 | 全本连续通读视图（+AI 辅助生成标识） |

**校验：FR1–FR26 全部映射到 6 个 epic，无遗漏、无一 FR 跨 epic 重复。**

> **Epic 7 备注（2026-07-30 Correct Course 新增）**：Epic 7 前端集成不新增 FR，兑现 FR1–FR16 的**前端侧**（此前仅后端验证）；不改变上表 FR→Epic 的归属映射。

## Epic 列表

> **分组原则**：按用户旅程站点（PRD §3.1）分 epic，技术基座随第一个需要它的 epic 走，不单独立「技术层 epic」；架构 9 步依赖链（AR20）与盲测门禁（AR19）作为 epic 内 story 排序与前置约束体现，不打散用户价值分组。

### Epic 1: 账户与作品管理（含后端基座）
用户能注册登录、集中管理多部作品、随时继续创作，并可绑定自己的 API Key（BYOK）。本 epic 顺带落地整个后端的工程基座（骨架 + 认证 + 多租户守卫），为后续所有 epic 铺底。
**FRs covered:** FR1, FR2, FR3, FR4
**基座/架构落点:** AR1（轻量 FastAPI 骨架初始化，首个 story）、AR2（分层结构）、AR3（JWT 双 token）、AR4（camelCase↔snake_case 边界）、AR5（REST+SSE / error envelope）、AR6（限流）、AR7（SQLAlchemy 2.0+Alembic）、AR9（account 表：user/project/byok_key/usage_ledger）、AR10（PG+pgvector 启用）、AR21（部署基础设施 docker-compose）、NFR3（多租户隔离）、NFR6（JWT+AES-GCM BYOK）、NFR8（国内云部署）、UX-DR2（BYOK 设置页+用量入口）、UX-DR9（登录/作品库错误状态对接）

### Epic 2: 探索（含 LLM / 编排底座）
用户新建作品后选引导或自由模式，与真实 Explorer Agent 多轮对话，聊出并持久化故事线索。本 epic 顺带落地 LLMProvider 抽象 + ARQ 异步任务底座（第一个真正调用 LLM 的地方）。
**FRs covered:** FR5, FR6, FR7, FR8, FR9, FR10, FR11
**基座/架构落点:** AR12（LLMProvider 抽象 + DeepSeek 实现，前置 story）、AR13（ARQ 任务队列）、AR14（用量计量埋点）、AR9（exploration_session/message、story_clue 表）、NFR2（长时异步 POST+SSE）、NFR5（成本计量）、UX-DR4（引导探索交互契约）、UX-DR5（自由探索交互契约）

### Epic 3: 故事设定与文风锚点
用户把探索线索整理成可编辑的故事设定卡（12 字段，广谱网文向），锚定爱读的文风，确认后成为只读的设定圣经、注入后续所有创作。
**FRs covered:** FR12, FR13, FR14, FR15, FR16
**基座/架构落点:** AR8（story_bible 表，V1 定全 12 字段 schema、特化字段可空）、AR15（文风锚定机制 style_profile 抽取）、焦点二、UX-DR1（文风样本锚点入口，须新增）、UX-DR6（设定卡交互契约）、NFR1 前提（style_profile 是红线验收前提）、NFR7b（story_bible 字段结构 clean-room 重实现）

### Epic 4: 章节创作（含盲测门禁）
用户确认设定后无缝进第一章，可选填想法生成正文、分页阅读、批注点评、改进/重生、定稿，阶段循环幕后推进，阶段交界可跳过方向输入。这是 Muse 的核心创作闭环。**盲测门禁（launch blocker）作为本 epic 首个 story，卡在正文生成接入之前。**
**FRs covered:** FR17, FR18, FR19, FR20, FR21, FR22
**基座/架构落点:** AR19（Claude-vs-DeepSeek 盲测门禁，Story 1；可在 E2 底座就绪后用手工样本提前启动）、AR11（五段流水线 context→drafter→reviewer→polisher→data-agent，V1 写前上下文先用「全量设定+最近定稿章节」直接注入，不阻塞 RAG）、AR16（context-agent 写前组装）、焦点一、NFR1（文字质量红线，本 epic 兑现）、NFR2（章节生成异步）、NFR4（长程一致性，不设章数上限）、UX-DR7（章节创作交互契约）
**依赖说明:** Story 1 盲测依赖 E2 的 LLM 底座 + E3 的 style_profile + 去 AI 味词表；正文生成接入（后续 story）须待盲测通过。

### Epic 5: 故事档案与归档（含 RAG）
章节定稿后自动凝练成章节卡片并持久化，归档页作为故事档案统一入口（设定圣经 + 分阶段章节归档一处呈现）；RAG 三级召回回头增强创作的写前上下文，防长篇跑偏穿帮。
**FRs covered:** FR23, FR24, FR25
**基座/架构落点:** AR8（chapter_card、story_thread、embedding 表）、AR17（chapter-commit 单事务投影）、AR18（RAG 三级召回 + EmbeddingProvider，接回 E4 写前上下文）、焦点三、焦点四、NFR4（一致性投影原子性）、NFR7b（GPL clean-room）、UX-DR8（归档页交互契约）

### Epic 6: 通读与交付
用户拿到「一本真正的小说」——全本连续通读视图，按顺序呈现已定稿章节，并标注「AI 辅助生成」满足合规。
**FRs covered:** FR26
**基座/架构落点:** AR21（对象存储承载分享页/导出件底座）、NFR7a（AI 辅助生成强制标识）、UX-DR3（AI 标识）

### Epic 7: 前端真实接线与端到端集成（2026-07-30 Correct Course 新增）
用户能在真实浏览器里走通「注册登录→管理作品→探索→出设定圣经」全闭环，所有数据来自后端而非 mock。本 epic 把 Epic 1-3 已 done 的后端 API 首次接上前端原型（`app.js` 至今零 fetch），偿还 1.6–3.5 积压的接线债。
**FRs covered:** 无新增 FR（兑现 FR1–FR16 的前端侧，此前仅后端验证）
**基座/架构落点:** AR3（JWT 双 token，前端 token 存取/刷新）、AR4（camelCase↔snake_case 边界收敛在请求工具层）、AR5（error envelope 统一解包）、NFR2（长时生成 POST+SSE 前端消费）、NFR3（多租户前端只见本人数据）、UX-DR9（登录/作品库错误位对接）、UX-DR2（BYOK 页+用量入口须新增）、UX-DR1（文风锚点入口须新增）、UX-DR4/DR5/DR6（探索/设定交互契约严格保持）
**执行时序:** 逻辑上介于 Epic 3 与 Epic 4 之间——先还债跑通 E1–E3 闭环，再进入 E4 创作；编号取 7 仅为不打乱已 done 条目与 sprint-status 引用。与 Epic 4-1 盲测门禁（纯后端评测）互不阻塞、可并行。

**Epic 总数：7** ｜ **FR 覆盖：FR1–FR26 全覆盖，无遗漏、无重复（Epic 7 不新增 FR，兑现 FR1–FR16 前端侧）** ｜ **自然依赖：E1→E2→E3→E4→E5→E6 顺序推进，每个 epic 独立可验证（E1 登录管作品 / E2 探索存线索 / E3 出设定圣经 / E4 写章定稿=核心闭环 / E5 归档防跑偏 / E6 通读全本）；E7 前端集成执行时序介于 E3/E4 之间，偿还 E1-3 接线债，与 E4-1 盲测门禁可并行**

---

# Epic 详情（含 Story）

> 每个 Story 单 dev agent 可完成，依赖只向后不向前，按需建表。AC 事实来源：FR / NFR / AR / UX-DR + 原型页面契约（`prototype/app/`，页面即契约）。

## Epic 1: 账户与作品管理（含后端基座）

用户能注册登录、集中管理多部作品、随时继续创作，并可绑定自己的 API Key（BYOK）。本 epic 顺带落地整个后端的工程基座（骨架 + 认证 + 多租户守卫），为后续所有 epic 铺底。

**Story 依赖**：1.1 →1.2 →1.3 →{1.4, 1.7}；1.4 →{1.5, 1.6}；1.7 →1.8。
**按需建表**：1.1 迁移框架 · 1.2 `user`/`invite_code` · 1.3 refresh 会话 · 1.4 `project` · 1.6 project 加 `phase` · 1.7 `byok_key` · 1.8 `usage_ledger`。

### Story 1.1: 后端工程基座与本地开发环境

As a Muse 后端开发者，
I want 一套可运行的 FastAPI 分层骨架、迁移框架与本地依赖环境，
So that 后续所有账户/作品/创作能力都能在统一、可迁移、多租户就绪的地基上开发。

**Acceptance Criteria:**

**Given** 一台装好 uv、Docker 的开发机
**When** 按 README 执行初始化（`uv init muse-backend` + 安装 `fastapi[standard]`/`sqlalchemy>=2.0`/`alembic`/`pydantic-settings`/`psycopg`/`pgvector`/`openai`/`python-jose`/`passlib`）并 `docker-compose up`
**Then** 本地起得来 PostgreSQL（启用 pgvector 扩展）+ Redis 两个容器（AR10/AR21）
**And** 应用启动后 `GET /health` 返回 200 且能连通 DB

**Given** 已初始化的后端仓库
**When** 查看目录结构
**Then** 存在 `routers`/`services`/`repositories`/`models`/`schemas` 分层与 `orchestration`/`providers`/`rag`/`tasks`/`core` 独立域（AR2），且 `routers` 仅做校验+分发、业务不写在 router 内

**Given** 分层骨架已就位
**When** 定义任一 Pydantic response schema 并通过接口返回
**Then** DB 层字段为 snake_case、API 边界自动转 camelCase（`alias_generator=to_camel, populate_by_name=True`），转换只收敛在 schema 层（AR4）
**And** 任一接口报错时返回统一 error envelope `{code, message, detail}`，时间字段为 ISO 8601 UTC（AR5）

**Given** Alembic 已按 async 模板初始化（`alembic init -t async`，AR7）
**When** 执行 `alembic upgrade head`（此时尚无业务表）
**Then** 迁移链可空跑通过，`alembic revision --autogenerate` 能正常生成迁移文件
**And** 前端原型目录保持可静态访问，预留 Vite 渐进增强入口（AR1），原型页面形态不变

### Story 1.2: 用户注册（邀请码）

As a 被邀请的早期创作者，
I want 用邀请码 + 邮箱 + 密码创建账号，
So that 我能拥有一个隔离的、属于我自己的创作空间。

**Acceptance Criteria:**

**Given** 我在注册页（`#/register`），邀请码字段必填、密码 `minlength=8`（原型 app.js:294-296）
**When** 我填入有效未使用的邀请码 + 合法邮箱 + ≥8 位密码并提交
**Then** 系统创建 `user` 记录（密码经 passlib 哈希存储，绝不明文）、标记该邀请码为已使用，并按原型行为跳转到 `#/projects`

**Given** 我提交注册
**When** 邀请码无效、已使用或已过期
**Then** 接口返回 error envelope，前端呈现注册模式 `invalid` 文案「邀请码无效、已使用或已过期。」（原型 app.js:249-252），账号不被创建

**Given** 我提交注册
**When** 邮箱已被注册
**Then** 返回明确冲突错误、不创建重复账号，不泄露多余信息

**Given** 前端做了 HTML5 校验（`reportValidity()`，原型 app.js:1681）
**When** 邮箱格式非法或密码 <8 位绕过前端直达后端
**Then** 后端独立校验并拒绝（不信任前端校验），返回 error envelope

**Given** 新账号创建成功
**When** 该用户后续访问任何业务数据
**Then** 所有数据以 `user_id` 行级隔离为前提（NFR3），`user` 表结构为后续 `project`/`byok_key`/`usage_ledger` 的租户根

### Story 1.3: 用户登录与 JWT 双 token 会话

As a 已注册用户，
I want 用邮箱密码登录并获得可持续的真实会话，
So that 我能安全地回到创作空间且会话过期能被正确处理。

**Acceptance Criteria:**

**Given** 我在登录页（`#/login`）
**When** 我用正确的邮箱 + 密码登录
**Then** 系统校验通过并签发 JWT access + refresh 双 token（AR3/FR1），按原型行为进入 `#/projects`

**Given** 我持有的 access token 已过期
**When** 我用 refresh token 请求刷新
**Then** 系统签发新的 access token 且会话不中断；若 refresh 亦失效，前端跳 `#/login?state=expired`，呈现文案「会话已过期，请重新登录。登录后会返回你的创作空间。」（原型 app.js:246）

**Given** 我在登录页
**When** 邮箱或密码错误
**Then** 返回 error envelope，前端呈现登录模式 `invalid` 文案「邮箱或密码错误，请检查后重试。」（原型 app.js:247-248），不签发 token

**Given** 同一账号/IP 登录失败次数超过阈值（AR6 限流）
**When** 我继续尝试登录
**Then** 触发锁定，前端呈现 `locked` 文案「登录尝试次数过多，请稍后再试。」（原型 app.js:253），锁定窗口内拒绝登录

**Given** 我已登录
**When** 我点击作品库 header 的「退出」（原型 app.js:374）
**Then** 当前会话失效（refresh token 作废），再次访问受保护接口需重新登录

### Story 1.4: 作品创建与列表持久化（空 / 失败状态）

As a 登录用户，
I want 新建作品并看到真实持久化、按更新时间排序的作品列表，
So that 我能集中管理自己的多部小说。

**Acceptance Criteria:**

**Given** 我已登录且点「开始一本新小说」
**When** 我走完两步弹窗——先选 `guided`（引导探索）/ `free`（自由探索），再填小说名（留空则「未命名小说」，原型 app.js:1730-1789）
**Then** 系统创建归属当前 `user_id` 的 `project` 记录（字段含 `id/title/mode/phase/attention/detail/updated`，对齐原型 app.js:198-229），`mode` 存所选模式、`phase` 初始为 `explore`
**And** 与原型不同，新建真实落库，不再是仅跳转不持久化

**Given** 我有 N 部作品
**When** 我打开作品库（`#/projects`）
**Then** 仅返回属于我的作品（NFR3 租户隔离），按 `updated` 倒序排列，header kicker 显示 `Library / NN novels`（数量补零两位，原型 app.js:378）

**Given** 我的账号一部作品都没有
**When** 作品列表返回空
**Then** 前端呈现 `empty` 空状态区块 `empty-library`（大标题「你的第一本小说，从这里开始。」+ 主按钮「开始一本新小说 →」，原型 app.js:381），kicker 显示 `00`

**Given** 作品列表接口请求失败
**When** 前端拿到错误
**Then** 呈现 `error` 失败区块 `library-error`（标题「暂时无法读取你的作品。」+ 说明「连接恢复后可以重新加载，不会影响已经保存的内容。」+「重新加载」按钮，原型 app.js:381），点「重新加载」重新拉取

### Story 1.5: 作品重命名与删除

As a 作品所有者，
I want 重命名或删除我的作品，
So that 我能保持作品库整洁、纠正命名。

**Acceptance Criteria:**

**Given** 我在作品库某行打开 `•••` 菜单点「重命名」（原型内联编辑，app.js:1801-1810）
**When** 我输入新名（留空则回落「未命名小说」）并保存
**Then** 系统更新该作品 `title` 并真实持久化（与原型仅改 DOM 不同），仅作品所有者可改（NFR3）

**Given** 我点某行「删除」
**When** 出现内联二次确认（文案「删除后无法恢复。」+「确认删除」/「取消」，原型 app.js:1811-1822）且我点「确认删除」
**Then** 系统真实删除该作品（与原型仅 `row.remove()` 刷新即恢复不同），列表移除该行

**Given** 删除二次确认出现
**When** 我点「取消」
**Then** 确认条消失、作品保留，无任何变更

**Given** 我尝试重命名/删除某作品
**When** 该作品不属于当前 `user_id`
**Then** 后端拒绝（租户守卫，NFR3），返回 error envelope，不泄露他人作品是否存在

### Story 1.6: 继续创作——按 phase 跳转当前步骤

As a 有在写作品的用户，
I want 点「继续创作」直接回到该作品当前所处的创作步骤，
So that 我不必手动找自己写到哪了。

**Acceptance Criteria:**

**Given** `project` 记录带 `phase` 字段，取值 `explore`/`chapter`/`archive`
**When** 我在作品行点主操作按钮（原型 `data-continue`，app.js:1824-1830）
**Then** 系统按 `phase` 路由——`explore`→探索页、`chapter`→章节页、`archive`→归档页（替代原型仅 `id===nameless` 特例），跳转逻辑对所有作品完整可测

**Given** 目标创作页在后续 Epic（2/4/5）才真正建成
**When** 本 story 阶段跳转到尚未完工的目标页
**Then** 跳转 URL/路由正确、可被后续 Epic 无缝接管（本 story 只保证路由正确，不要求目标页功能完整）

**Given** 作品行主操作文案（原型 `action` 字段：如「阅读草稿」「继续设定」）
**When** 渲染作品行
**Then** 按钮文案与该作品 `phase` 语义一致，不再出现原型「目标页面待设计」占位

### Story 1.7: BYOK API Key 绑定（全新设置页）

As a 想用自己额度的用户，
I want 在设置页绑定我自己的 API Key，
So that 我的生成走我自己的 Key、不受托管免费额度限制。

**Acceptance Criteria:**

**Given** 原型没有设置页（全新页面，UX-DR2）
**When** 我从账户入口进入设置页
**Then** 存在 API Key 绑定区，可输入并保存我的 Key

**Given** 我提交要绑定的 API Key
**When** 后端接收
**Then** Key 经应用层 AES-GCM 加密后存 PG（`byok_key`，主密钥放环境变量/KMS，NFR6），响应及后续展示只回显掩码（如尾 4 位），绝不明文返回

**Given** 我已绑定 Key
**When** 该账户/作品发起生成
**Then** 走用户自己的 Key（FR4）；Key 按账户/作品隔离，杜绝越权读取他人 Key（NFR3）

**Given** 我已绑定 Key
**When** 我在设置页解绑/替换
**Then** 旧密文被覆盖/删除，后续生成回落托管路径或使用新 Key

**Given** 我提交的 Key 格式非法或为空
**When** 后端校验
**Then** 拒绝并返回 error envelope，不写入无效密钥

### Story 1.8: 托管免费额度护栏与用量展示

As a 走托管默认路径的用户，
I want 看到自己的用量与剩余免费额度、并在触顶时得到明确提示，
So that 我清楚免费边界、不会莫名被拒。

**Acceptance Criteria:**

**Given** 需要按账户累计用量（建 `usage_ledger` 表，AR9/AR14）
**When** 本 story 建立表结构与 `usage_service` 护栏校验框架
**Then** 表可记录每账户 tokens/成本累计；实际用量写入的埋点由 Epic 2 Provider 层填（AR14 跨 epic 依赖，本 story 只建表+校验框架+展示）

**Given** 我走托管路径发起生成（未绑定 BYOK）
**When** `usage_service` 校验免费额度
**Then** 未触顶正常放行；触顶按 AR6 返回明确提示（error envelope），不静默失败
**And** 免费额度具体阈值可配置，默认值待 Epic 4 盲测出单章真实成本后再定（本 story 用可配置占位阈值）

**Given** 我进入设置页/用量入口（UX-DR2，原型无，全新）
**When** 页面加载
**Then** 展示我的托管用量与剩余免费额度；BYOK 用户展示「走自有 Key、不占免费额度」

**Given** 我已绑定 BYOK（Story 1.7）
**When** 我发起生成
**Then** 用量记我自己账（不计入托管免费额度，NFR5），额度护栏不拦截

## Epic 2: 探索（含 LLM / 编排底座）

用户新建作品后选引导或自由模式，与真实 Explorer Agent 多轮对话，聊出并持久化故事线索。本 epic 顺带落地 LLMProvider 抽象 + ARQ 异步任务底座（第一个真正调用 LLM 的地方）。

**Story 依赖**：2.1 →2.2 →{2.3 →2.4 →2.5（引导链）, 2.6 →2.7 →2.8（自由链）}；两链在 2.2 后并行、互不向前依赖。
**按需建表**：2.2 `exploration_session` · 2.4 `exploration_message` · 2.6 `story_clue` · 2.8 `exploration_session.guidance_state`（JSONB 列，不新建表）。
**边界（Epic 2/3）**：整理任务的触发与「整理中」过渡态归本 epic；设定候选卡的生成、会话内恢复、确认/丢弃归 Epic 3。
**异步模型**：交互式对话（自由聊天、引导自述理解）走 `LLMProvider.stream` 流式 SSE；「整理为故事设定」等凝练走 ARQ 后台任务 `POST→taskId→GET /events`。

### Story 2.1: LLMProvider 抽象 + DeepSeek 实现 + ARQ/SSE 异步底座

As a Muse 后端开发者，
I want 一层可换模型的 LLMProvider、DeepSeek 默认实现，以及支撑长时生成的 ARQ + SSE 异步底座，
So that 探索及后续所有 LLM 能力都在统一、可计量、不阻塞的运行时上开发。

**Acceptance Criteria:**

**Given** 需要模型接入抽象（AR12）
**When** 定义 `LLMProvider` 接口（`chat` / `stream` / `count_tokens`）并实现 DeepSeek（OpenAI SDK 兼容、切 `base_url`，`deepseek-v4-pro` 思考档 / `deepseek-v4-flash` 快档，128K）
**Then** 业务层只依赖 `LLMProvider` 接口、禁止直接 import/调用 openai SDK，换模型 = 换实现不改业务层

**Given** 交互式探索对话需低延迟返回
**When** 调用 `LLMProvider.stream`
**Then** 通过 SSE 流式增量返回文本，适配自由对话/引导自述理解等交互场景

**Given** 长时生成需异步（NFR2）
**When** 提交一个后台任务（如「整理为故事设定」）
**Then** 走 ARQ（Redis broker）`POST → 返回 taskId` + `GET /events` SSE 三事件（`progress` / `result` / `error`），不同步阻塞、不前端轮询

**Given** 每次 LLM 调用都要计量（AR14/NFR5，兑现 Story 1.8 跨 epic 依赖）
**When** 任一 Provider 调用完成
**Then** 在 Provider 层统一记 tokens 与成本写入 `usage_ledger`——托管路径归 Muse 账、BYOK 归用户账

**Given** 用户已绑定 BYOK Key（Story 1.7）
**When** 该账户/作品发起 LLM 调用
**Then** Provider 用该用户的 Key，计量记其自有账、不占托管免费额度

### Story 2.2: 探索会话根与模式分叉（模式独立）

As a 新建作品的用户，
I want 在引导/自由二选一后进入一个独立、不会中途被切换的探索会话，
So that 我能专注在一种探索方式里、且两种方式最终产出同一套故事设定。

**Acceptance Criteria:**

**Given** 我新建作品时选了 `guided` 或 `free`（原型创建时定死 `explorationEntryMode`，app.js:1739）
**When** 我进入探索页
**Then** 系统创建归属当前 `user_id` + `project_id` 的 `exploration_session` 记录、记下 `mode`，页面按 mode 渲染对应界面（原型 `isGuided` 分叉，app.js:761）

**Given** 我已在某一探索模式中
**When** 我在探索页寻找切换模式的入口
**Then** 不存在中途切换入口（原型无切换 UI、`explorationEntryMode` 仅创建时赋值），模式独立到本次探索结束（FR5）

**Given** 引导与自由两模式
**When** 各自完成探索并进入整理
**Then** 两者产出对齐同一套故事设定字段 schema（FR5，为 Epic 3 的 12 字段设定卡统一入口）

**Given** 探索会话数据
**When** 任意读写
**Then** 以 `user_id` + `project_id` 行级隔离（NFR3），不越权访问他人会话

### Story 2.3: 引导探索——真实 Agent 理解自由作答 + 沉浸问答

As a 选了引导探索的用户，
I want 一次只面对一道题、用选项或一句话作答，且我的自述能被真正理解，
So that 我能零负担地把脑中模糊的故事念头说清楚。

**Acceptance Criteria:**

**Given** 我在引导探索中（FR6，UX-DR4）
**When** 页面渲染某一题
**Then** 只呈现当前一题 + A/B/C/D 选项、不显示已答历史、无右侧线索区（原型 app.js:772），进度条显示「引导探索 · 问题 NN / 06」

**Given** V1 用有限问题集（非动态选题）
**When** 我逐题作答
**Then** 6 题顺序固定、题目不由 LLM 动态生成（动态选题属 V2 EXP-P01）

**Given** 我点选一个预设选项
**When** 提交该题
**Then** 走前端记录答案、不调用 LLM

**Given** 第一题支持一句话自述（文案「或者，用一句话说出你的念头」，app.js:835）或其余题选「都不是这些？用一句话自己回答」（app.js:844）
**When** 我用自由文本作答并确认
**Then** 调用真实 Explorer Agent 理解我这句话的意图（V1 引导 Agent 的唯一真实 LLM 职责），作为该题答案纳入探索

**Given** 我在任一题
**When** 我查看作答出口
**Then** 第一题常驻自述表单、第二题起为可折叠「都不是这些」出口（默认折叠，除非该题上次即自述作答则默认展开，app.js:845）

### Story 2.4: 引导探索——翻页与答案真实持久化

As a 引导探索中的用户，
I want 前后翻看并修改已答题、且我的答案不会丢，
So that 我能反复斟酌、不怕刷新或中断丢失进度。

**Acceptance Criteria:**

**Given** 我在引导探索翻页（FR7，UX-DR4）
**When** 底部导航渲染
**Then** 「← 上一题」「下一题 →」按可用性显示（`canPrev = view>0`，`canNext = view<已答数`）；首题左侧、末已答题右侧以 spacer 留空占位（原型 app.js:789）

**Given** 我翻到别的题
**When** 前翻或后翻
**Then** 不清除任何已答答案（原型纯翻页，app.js:962）

**Given** 我翻回一道已答题
**When** 页面渲染该题
**Then** 高亮我上次所选项（`is-chosen` + `✓`，app.js:817-825）；若上次是自述作答则回填自述文本（app.js:831-833）

**Given** 我在已答题重选答案
**When** 提交
**Then** 只更新该题答案（定点写 `history[view]`，app.js:427-430）、不影响其后任何题

**Given** FR11 要求探索答案真实持久化（补原型「内存态、刷新即丢」落差）
**When** 我作答或修改后刷新/断线重连
**Then** 答案已落库 `exploration_message`（带 `user_id`+`project_id`）、可恢复，不丢失进度

### Story 2.5: 引导探索——收尾「整理中」过渡态

As a 答完引导全部问题的用户，
I want 看到系统正在把我的回答整理成故事设定的过渡反馈，
So that 我对「接下来会生成什么」有明确预期、且能反悔回去改。

**Acceptance Criteria:**

**Given** 我作答完最后一题（FR8）
**When** 提交末题
**Then** 进入「整理中」过渡态（约 1.2 秒，原型 1200ms，app.js:441），显示文案「正在把你的回答整理成一份故事设定……」+ spinner（app.js:795）

**Given** 进入整理中过渡态
**When** 过渡态触发
**Then** 后台以 ARQ 任务启动「整理为故事设定」（异步），不阻塞前端

**Given** 我在收尾态（引导完成 06/06）选择「回到探索」而非继续
**When** 我返回
**Then** 过渡态复位（`guidedSettling=false`，app.js:551），回到可翻页修改的收尾态（仍可点「上一题」改答案）

**Given** 边界（Epic 2/3）
**When** 整理任务完成
**Then** 本 story 职责到「触发整理任务 + 过渡态」为止；设定候选卡的生成、弹出、会话内恢复、确认/丢弃由 Epic 3 承接

### Story 2.6: 自由探索——对话 + 线索区 + 给方向 + 持久化

As a 选了自由探索的用户，
I want 和 Agent 自由多轮讨论、Agent 帮我自动整理线索而我仍能自己掌控，
So that 我能按自己的节奏聊出故事、且主导权始终在我手上。

**Acceptance Criteria:**

**Given** 我在自由探索（FR9，UX-DR5）
**When** 对话渲染
**Then** 连续只读呈现全部对话、不折叠不拆分（原型 app.js:892-901），新消息自动滚到底

**Given** 我发送一条消息
**When** Agent 回复
**Then** 接入真实 Explorer Agent 多轮对话（流式 SSE），替代原型固定文案；Agent 只讨论、不替我决定或直接改设定（原型明确「不会替你直接改动设定」，app.js:1044-1061）

**Given** 右侧「故事线索」区
**When** 我编辑线索
**Then** 支持内联直接编辑（contenteditable，空值占位「尚未确定」，app.js:389-396），并可增删自定义线索（app.js:1001-1029）

**Given** 「给我一些讨论方向」复选与三个方向选项
**When** 我勾选并点某个方向
**Then** 只把预设句写入输入框、不代答不替我决定（app.js:1037-1043）；勾选为会话级持续偏好、直到我主动取消（`showInspirationDirections`，app.js:1030）

**Given** V1 自由模式要求 Agent 依对话自动整理线索（用户明确要求，硬 AC，非可选增强）
**When** 对话推进
**Then** Agent 依对话内容自动生成/更新右侧故事线索；用户已手动编辑的线索优先、不被自动整理覆盖；自动整理与手动编辑并存

**Given** FR11 要求对话与线索真实持久化（补原型「内存态、刷新即丢」落差）
**When** 我对话/编辑线索后刷新或断线重连
**Then** 对话落 `exploration_message`、线索落 `story_clue`（均带 `user_id`+`project_id`）、可恢复

### Story 2.7: 自由探索——「整理为故事设定」开放门禁

As a 自由探索中的用户，
I want 只有在真正聊出内容后才能整理成故事设定，
So that 我不会在信息不足时得到一份空洞的设定。

**Acceptance Criteria:**

**Given** 我刚进入自由探索、只有开场白（FR10，UX-DR5）
**When** 页面渲染「整理为故事设定」按钮
**Then** 按钮首屏不可用（`disabled`），提示「继续和 Agent 讨论，线索足够时就能整理为故事设定。」（app.js:871-873,888）

**Given** 我已至少发送一条消息（`canFinish = 有 user 消息`，app.js:870）
**When** 按钮状态刷新
**Then** 按钮开放可点，提示转「故事线索已经足够，可以整理成一份故事设定。」

**Given** 我点开放后的「整理为故事设定」
**When** 触发整理
**Then** 以 ARQ 后台任务启动整理（异步），交接 Epic 3 承接设定候选卡（方案 A 边界）

**Given** 边界说明
**When** 界定 V1 开放条件
**Then** V1 用「≥1 条用户消息 + 主动点按钮」近似（2026-07-31 Correct Course 修订：真正的 7 项主干覆盖度门禁已提前到 V1，由 Story 2.8 承接并取代本近似判据；完整置信度/证据来源/交叉验证仍属 EXP-P02 V2）

### Story 2.8: 自由探索——设定导航、按需回答思路与 7 项完成度门禁

> **2026-07-31 Correct Course 新增**（Sprint Change Proposal 2026-07-31）：把 EXP-P02「以设定结果覆盖度决定探索是否完成」的最小能力从 V2 提前到 V1，替换 2.7 的「≥1 条用户消息」近似门禁。不回滚 2.6/2.7 已交付的真实聊天/线索/初版门禁，本 story 在其基础上新增导航能力。

As a 自由探索中的用户，
I want 系统主动判断故事设定还缺什么、每轮只问一个具体问题，并在我卡住时给出可选思路、允许我跳过，
So that 我不会被同一个话题无限追问，也不会在设定还没聊清楚前就被允许草草整理。

**Acceptance Criteria:**

**Given** 自由探索需要判断「设定整理所需信息是否已经充分形成」（FR10，EXP-P02 V1 最小能力）
**When** 会话建立
**Then** `exploration_session` 持久化一份 7 项通用主干（题材/核心吸引力/主角/主要冲突/关键世界规则/整体气质/开篇钩子）的完成度状态，每项取值 `missing`/`filled`/`skipped`，随对话与线索刷新，不依赖前端本地态作为真相源

**Given** 用户已有对话与线索材料
**When** 一轮自由对话结束
**Then** 系统按当前材料更新 7 项状态、只选择一个当前最缺的项、生成围绕该项的一句具体问题；已 `filled` 或 `skipped` 的项本轮不重复提问

**Given** 用户尚无任何对话（FR9 起点）
**When** 用户选择「先说一个故事想法 / 先聊主角 / 先定核心冲突 / 先想世界与氛围」四个入口之一
**Then** 系统据该入口生成对应维度的第一个具体问题，作为本轮对话的开场；四个入口是固定产品入口，不是 AI 生成的建议

**Given** 用户面对当前具体问题不知道怎么答
**When** 用户点击「没想好？看看几个思路」
**Then** 系统按需调用一次 LLM，生成 2–4 个与当前问题、已有线索和缺失字段相关的回答选项；不在每轮自动生成，避免不必要的调用成本

**Given** 用户点击某个 AI 回答思路
**When** 该选项被选中
**Then** 系统把它直接作为本轮用户回答提交（等价于用户自己发送该消息），立即触发完成度与线索的刷新

**Given** 用户对当前问题选择「先跳过这个问题」
**When** 跳过被触发
**Then** 该项标记为 `skipped`；系统据已有材料做一次谨慎归纳写入线索（不杜撰），随后不再围绕该项重复追问，直接推进到下一个缺失项或收束

**Given** 7 项主干均已 `filled` 或 `skipped`
**When** 状态刷新完成
**Then** `readyToSettle` 置真，Agent 在对话流中给出明确收束提示（如「这本故事的骨架已经够清楚了，现在可以整理成一份设定卡」），系统不再主动抛出新问题

**Given** 「整理为故事设定」触发端点（复用 2.7 的 `POST .../free/settle`）
**When** 请求到达且 7 项主干尚未全部 `filled`/`skipped`
**Then** 后端硬校验拒绝（400，语义与既有 `exploration_not_ready` 一致或扩展同一错误族），不入队、不消耗整理任务；前端 disabled + 后端硬校验双防线（延续 2.6/2.7 既定方法论）

**Given** 题材特化字段（力量体系/金手指/感情线/势力格局）与文风锚点
**When** 判断 7 项主干完成度
**Then** 特化字段与文风锚点不计入本门禁、不阻塞整理（FR10）

**Given** 右侧「故事线索」区与 `story_clue.user_edited`（2.6 既有硬约束）
**When** 系统基于导航生成的问答更新线索或做跳过归纳
**Then** 已被用户手动编辑（`user_edited=true`）的线索行不被覆盖；导航状态与线索区各自持久化、职责边界不合并——`story_clue` 仍是用户可编辑事实源，导航状态只是完成度与下一问的后端事实源

**Given** 探索会话数据（NFR3）
**When** 任意读写导航状态
**Then** 以 `user_id` + `project_id` 行级隔离，不越权访问他人会话；结构化生成与建议均经 `LLMProvider` 抽象，禁止直接调用 openai SDK（AR12）

## Epic 3: 故事设定与文风锚点

用户把探索线索整理成可编辑的故事设定卡（12 字段，广谱网文向），锚定爱读的文风，确认后成为只读的设定圣经、注入后续所有创作。

**Story 依赖**：3.1 →3.2 →3.3 →3.4 →3.5；3.3 出卡时消费 3.2 已抽取的 `style_profile` 填第⑫字段。
**按需建表**：3.1 `story_bible`（含 style_profile 列，12 字段一次建全、特化字段可空）。
**排序说明**：3.1 建表 enablement 先行；3.2 文风锚点提前到设定卡生成之前——`style_profile` 是独立的作品级抽取，且是 Epic 4 盲测门禁（AR19 launch blocker）的前置输入，须在盲测前必然就绪。

### Story 3.1: story_bible 表落地（12 字段 schema，clean-room）

As a Muse 后端开发者，
I want 一张承载 12 字段设定圣经的 story_bible 表，一次建全 schema、特化字段可空，
So that 设定圣经能真实持久化、多租户隔离，并作为全项目一致性的数据根。

**Acceptance Criteria:**

**Given** AR8 要求 story_bible 表 V1 一次建全 schema
**When** 建表迁移执行
**Then** 表含通用主干 7 项为必备列、题材特化 4 项可空列、style_profile 列（webnovel-writer 无），带 `user_id`+`project_id`（NFR3）

**Given** 字段结构参照 webnovel-writer（NFR7b GPL 护栏）
**When** 设计表结构
**Then** 作为「数据模型参考」clean-room 重实现、不复制其 GPL 源码；正式实现前须创始人做许可证义务评估（NFR7）

**Given** genre 字段决定特化字段激活（FR12）
**When** 存储某作品设定
**Then** genre 已知、特化字段按需填，不匹配的特化列存空、不报错

**Given** 后续 story（3.3 生成、3.5 确认）要写入设定
**When** 表就位
**Then** 以 V1 全文形式存储设定圣经条目，供 Epic 4 创作上下文与 Epic 5 归档页读取

### Story 3.2: 文风锚点入口（全新 UI）+ style_profile 抽取

As a 在意文字质量的用户，
I want 从预置样本库选择或粘贴一段我爱读的文字来锚定文风，
So that 生成的正文能贴近我真正喜欢的笔触、而非通用 AI 腔。

**Acceptance Criteria:**

**Given** 原型无文风锚点入口（全新 UI，UX-DR1；仅有「叙事风格」只读字段 app.js:493）
**When** 我在设定阶段进入文风锚点入口
**Then** 提供两种锚定方式：从预置样本库选择，或粘贴一段自己爱读的文字（FR16）

**Given** 我选定/粘贴了文风样本
**When** 系统处理
**Then** 抽取作品级 `style_profile`（人称、语气、句式节奏、意象密度、段落长度倾向，FR16/AR15）

**Given** style_profile 抽取完成
**When** 设定被确认（Story 3.5）
**Then** style_profile 随设定圣经持久化（story_bible 字段⑫），成为后续每章生成的风格锚点（AR15，为 Epic 4 drafter 注入做准备）

**Given** style_profile 是 NFR1 红线验收前提、且 Epic 4 盲测门禁（AR19）依赖它
**When** 本 story 完成
**Then** style_profile 抽取产物可用作 Epic 4 Story 1 盲测的风格锚点输入（跨 epic 依赖，显式标注）

**Given** 我未锚定任何文风样本
**When** 进入后续创作
**Then** style_profile 可空、系统用合理默认风格（不阻塞出设定；但红线验收理想态需锚定，提示用户锚定更佳）

### Story 3.3: 探索整理为 12 字段故事设定候选卡

As a 完成探索的用户，
I want 系统把我的探索内容真实整理成一份结构化的故事设定候选卡，
So that 我能看到自己模糊的念头被凝练成一份可用的设定圣经雏形。

**Acceptance Criteria:**

**Given** 我在引导收尾/自由「整理为故事设定」触发了整理任务（接 Epic 2 Story 2.5/2.7 的 ARQ 任务）
**When** 整理任务执行
**Then** 真实调用 LLM 把探索对话/线索/引导答案凝练成 12 字段设定候选卡（FR12），经 SSE `result` 事件返回

**Given** 12 字段 schema
**When** 生成候选卡
**Then** 含通用主干 7 项（①题材 genre ②核心吸引力 ③主角[姓名+核心欲望+致命缺陷] ④主要冲突[+反派镜像] ⑤关键世界规则 ⑥整体气质 ⑦开篇钩子）、题材特化 4 项（⑧力量体系 ⑨金手指 ⑩感情线 ⑪势力格局，按 genre 激活、不匹配可空）、⑫文风锚点 style_profile（消费 Story 3.2 已抽取值）

**Given** V1 探索用有限问题集、不保证凑齐特化字段
**When** 某题材特化字段无对应信息
**Then** 该字段留空即可，不阻塞出卡（覆盖度驱动的「凑齐才放行」属 EXP-P02/V2）

**Given** 候选卡生成后（接 Epic 2 方案 A 边界）
**When** 整理任务完成
**Then** 候选卡挂出为待确认设定卡（头部「Story profile / v1」，原型 app.js:523），字段以 `NN / 字段名` 编号呈现（app.js:515）

**Given** genre 字段决定特化字段是否激活（FR12）
**When** 探索识别出题材（如修仙/言情）
**Then** 对应特化字段被激活填充、不匹配的特化字段不强制填

### Story 3.4: 设定候选卡编辑 + 反馈升版本（真实 Agent）

As a 拿到候选设定卡的用户，
I want 直接编辑字段、或让 Agent 按我的反馈调整并看到版本变化，
So that 我能把设定打磨到满意再定稿。

**Acceptance Criteria:**

**Given** 待确认设定卡（FR13，UX-DR6）
**When** 我直接编辑某字段（contenteditable，原型 app.js:516）
**Then** 该字段值更新并持久化到待确认卡（原型 `data-final-profile-field` 写回 + persist，app.js:640-645）

**Given** 我在「你想调整什么？」填写反馈并提交（原型 app.js:527-530）
**When** 反馈提交
**Then** 调用真实同一探索 Agent（替代原型关键词匹配 mock，app.js:607-632）生成新版本，`revision` 递增（头部 `v{revision}`，app.js:589）

**Given** 新版本生成
**When** 卡片重渲
**Then** 本轮变化的字段以 `is-updated` 高亮标出（原型 app.js:514），让我一眼看到 Agent 改了哪些

**Given** 反馈处理中
**When** 我提交反馈后等待
**Then** 显示处理中状态反馈（原型「调整中…」status，app.js:530/663），完成后展示新版本

**Given** 待确认卡真实持久化（FR11 延续，补原型 sessionStorage→后端）
**When** 我编辑/反馈后刷新或断线重连
**Then** 待确认卡（含 profile/revision/变化项）从后端恢复，刷新不回退到探索主界面（原型 pending 恢复逻辑，app.js:949），确认后清除待确认态

### Story 3.5: 确认设定 → 只读设定圣经 + 回到探索丢弃

As a 对设定满意的用户，
I want 确认后设定成为注入后续创作的只读依据、或明确丢弃重来，
So that 我的创作有稳定一致的设定地基、且反悔有明确代价提示。

**Acceptance Criteria:**

**Given** 我在设定卡点「确认故事设定 →」（FR14，原型 app.js:532）
**When** 确认
**Then** 设定成为只读的全文指导上下文、真实持久化到 story_bible（替代原型 `confirmedStoryProfile` sessionStorage，app.js:562-566），作品 `phase` 推进（为 Epic 1 Story 1.6 的 phase 跳转提供真实状态）

**Given** 确认成功
**When** 后续任何创作（章节生成等）执行
**Then** 该设定圣经作为只读上下文注入（FR14），不可在创作阶段被随意改写

**Given** 我在设定卡点「回到探索页面」（FR15，原型 app.js:532）
**When** 出现二次确认（标题「回到探索页面？」+ 正文「返回后，当前设定内容和修改记录都会丢失。」+「取消」/「确定返回」，原型 app.js:533）且我点「确定返回」
**Then** 丢弃当前设定内容与修改记录（原型 `discardStoryProfileAndReturn`，app.js:544-553），回到可继续探索的状态

**Given** 二次确认出现
**When** 我点「取消」
**Then** 保留当前设定卡与修改、无变更

**Given** 确认后（原型幕后行为）
**When** 进入创作
**Then** 幕后生成首个阶段规划、用户体感直接进第一章（此仅 phase 衔接，阶段规划本体属 Epic 4 FR17）

## Epic 4: 章节创作（含盲测门禁）

用户确认设定后无缝进第一章，可选填想法生成正文、分页阅读、批注点评、改进/重生、定稿，阶段循环幕后推进，阶段交界可跳过方向输入。这是 Muse 的核心创作闭环。盲测门禁（launch blocker）作为本 epic 首个 story，卡在正文生成接入之前。

**Story 依赖**：4.1 →4.2 →4.3 →4.4 →4.5 →4.6 →4.7，严格线性（盲测是硬门禁，未通过阻断 4.4 正文接入）。
**按需建表**：无（消费 Epic 3 `story_bible` + 复用编排状态落 PG）。
**关键边界**：① 4.1 盲测未通过则阻断 4.4；盲测用临时去 AI 味词表，正式词表随 4.2 落地。② V1 流水线仅 `context→drafter→reviewer→polisher` 四段，data-agent 写后投影 + 章节卡片归 Epic 5。③ V1 写前上下文用「全量设定 + 最近定稿章节」直接注入，RAG 三级召回归 Epic 5 回头增强。④ FR22 阶段交界方向输入是原型完全缺失的新增项。

### Story 4.1: 盲测门禁——Claude-vs-DeepSeek（launch blocker）

As a Muse 创始人/技术负责人，
I want 在正文生成接入前验证 DeepSeek 能否达到文字质量红线，
So that 我不会在一个写不出好文字的模型上建整个产品——这是全项目头号生死假设。

**Acceptance Criteria:**

**Given** 这是实施顺序第 4 步、卡在「编排底座就绪」与「正文生成接入」之间（AR19/AR20）
**When** 执行盲测
**Then** 用同一 style_profile（消费 Epic 3 Story 3.2 产物）+ 同一去 AI 味词表（临时版）、仅切换 Provider（Claude vs DeepSeek）产出对照样本

**Given** NFR1 文字质量红线采用三档判据（不及格 / 及格线 / 理想），及格线 = 三条量化条件同时满足
**When** 盲测样本按「风格锚定」（是否像用户锚定的文风）逐篇盲评
**Then** 按 NFR1 判据客观判定并记录 DeepSeek 是否达及格线：① 轴 A 风格贴合——创始人对 N 篇匿名样本三级打分（不像=0/出戏=1/像=2），判「像」（≥1 分且多为 2 分）篇数 **≥ 2/3**；② 轴 B 重度句式套路 **= 0 处**；③ 轴 B 黑名单词频 **≤ 锚定样本自身 1.5 倍**（无基准兜底 ≤3 词/千字）。**三条同时满足** = 及格线以上（放行）；任一不满足 = 不及格（阻断）

**Given** 这是 launch blocker 的硬时点
**When** 盲测未通过
**Then** 阻断 Story 4.4 正文生成接入（门禁不放行），须调整方案（换 Provider / 调 prompt / 调词表）重测

**Given** 盲测通过
**When** 门禁放行
**Then** 解锁 Story 4.4 正文接入；盲测结论与所用 style_profile / 临时词表 / prompt 记录留档

**Given** 本 story 是验证活动、非交付功能
**When** 界定范围
**Then** 只搭最小盲测装置产出结论，不实现完整流水线（流水线属 4.2）；正式去 AI 味词表随 4.2 落地

### Story 4.2: 五段流水线编排底座（V1 四段 + 去 AI 味词表）

As a Muse 后端开发者，
I want 一条自建的、可断点续跑的章节生成流水线与正式去 AI 味词表，
So that 章节正文能在可控、可重入、成本可计的运行时上真实生成并自查文风。

**Acceptance Criteria:**

**Given** 盲测已通过（4.1 门禁放行）
**When** 搭建编排运行时（AR11）
**Then** 实现自建轻量流水线 V1 四段：`context-agent → drafter → reviewer → polisher`（data-agent 写后投影归 Epic 5）

**Given** AR11 要求每 step 幂等可重入、状态落 PG
**When** 流水线执行中某 step 失败
**Then** 天然断点续跑（状态在 PG）、由 ARQ 重试，成本按 step 累计（NFR5）

**Given** 正式去 AI 味词表随本 story 落地（复用自 webnovel-writer polish-guide）
**When** 实现 polisher step
**Then** 加载 200+ 词黑名单 + 7 层句式规则、由 polisher 自查自改；词表作规则参考 clean-room 重实现、不复制 GPL 源码（NFR7b）

**Given** style_profile 是每章生成的风格锚点（AR15）
**When** drafter 生成正文
**Then** style_profile 作为风格锚点段注入 drafter，与去 AI 味词表叠加（polisher 自查），共同兑现 NFR1 红线

**Given** 章节生成是多次 LLM 调用叠加（5–10 次/章，NFR2）
**When** 流水线运行
**Then** 走异步任务模型（`POST→taskId→GET /events` SSE），不同步阻塞、不前端轮询

### Story 4.3: 首章无缝进入 + 幕后阶段规划

As a 刚确认设定的用户，
I want 直接进入第一章创作，不被阶段规划的过程打扰，
So that 我的注意力始终在「写我的故事」而非管理流程。

**Acceptance Criteria:**

**Given** 我确认了故事设定（接 Epic 3 Story 3.5）
**When** 进入创作
**Then** 首个阶段规划（阶段目标 + 章节骨架）全程幕后完成、不展示、无确认弹窗（FR17，原型 `buildCurrentStagePlan` 幕后，app.js:568），我体感直接进第一章（`chapters/1`）

**Given** 阶段计划幕后生成
**When** 章节页渲染
**Then** 阶段计划仅作右侧 `chapter-context` 侧栏参考展示（无确认按钮，原型 app.js:1120-1129），文案「阶段计划提供每章的方向；详细章节计划只在准备创作当前章时生成。」

**Given** 原型阶段计划是 mock（章数恒缺省 5、侧栏标题恒「第一阶段」，`stagePlanningDraft` 恒空）
**When** V1 实现
**Then** 阶段规划基于真实故事设定生成（替代 mock），章节数按剧情需要、不写死；NFR4 一致性按「几百章」设计、不设人为章数上限

**Given** 我进入第一章
**When** 页面初始
**Then** 章节创作状态为输入态（`chapterCreationState="input"`，原型 app.js:575），等待我的本章想法或直接生成

### Story 4.4: 本章想法输入 + 真实生成章节正文

As a 要写某一章的用户，
I want 可选地补充本章想法、然后让 Agent 依设定和上下文真实写出这一章，
So that 我既能引导本章走向、也能零负担地直接生成。

**Acceptance Criteria:**

**Given** 盲测已通过（4.1 门禁前置，AR19）
**When** 本 story 接入正文生成
**Then** 真实调用 4.2 流水线生成章节正文（替代原型 1200ms mock + 硬编码 3 页）

**Given** 我在输入态（FR18，UX-DR7）
**When** 我查看本章想法输入
**Then** 「本章想法」可选填（标记「可选」，原型 app.js:1209），placeholder「可以补充想看到的场面、人物表现、节奏或一句具体的对白……」；可留空

**Given** 我点生成
**When** 提交
**Then** 按钮文案随输入切换「生成本章」（有想法）/「跳过并生成」（空，原型 app.js:1211）；状态流转 input→generating→reading

**Given** 写前上下文组装（AR16，context-agent）
**When** 生成本章
**Then** 消费「故事设定 + 已定稿章节 + 归档卡片」作上下文（FR18）；V1 写前上下文先用「全量设定 + 最近定稿章节」直接注入、不阻塞 RAG（RAG 三级召回属 Epic 5 回头增强）

**Given** 生成中（NFR2 异步）
**When** 流水线运行
**Then** 显示生成过渡态（原型「正在写下这一章」+ 据 `chapterIdea` 动态插入「和你的本章想法」，app.js:1218-1219），经 SSE 推进度、完成转 reading 态

### Story 4.5: 分页阅读 + 段落批注 + 整体点评

As a 读到生成正文的用户，
I want 分页阅读、对具体段落批注、对整章点评，
So that 我能像编辑一样精确地表达哪里要改。

**Acceptance Criteria:**

**Given** 正文已生成（reading 态，FR19，UX-DR7）
**When** 我阅读
**Then** 正文支持分页阅读，翻页控件「←/→」按边界 disabled（首页禁上一页、末页禁下一页，原型 app.js:1188-1193），底部页码「NN / 总页数」

**Given** 我想批注某一段
**When** 我点该段的 `＋` 按钮（原型 `paragraph-annotation-trigger`，app.js:1176）
**Then** 进入批注模式（`chapterAnnotationTarget` 定位该页该段），textarea 转「批注第 N 段」、placeholder「写下对这一段的具体意见……」（app.js:1112-1114）

**Given** 我填写批注并保存
**When** 点「保存批注 →」（空则 disabled，原型 app.js:1115）
**Then** 批注进入本章批注列表（`chapterAnnotations`，原型内存数组→V1 持久化），侧栏列表可展开、点某条可回定位到对应段（app.js:1088-1095,1316-1332）

**Given** 我未选中任何段落
**When** textarea 处于默认态
**Then** 为「对这一章的点评」整体点评（placeholder「例如：开头再快一点……」，原型 app.js:1112-1114，存 `chapterFeedback`）

**Given** 段落批注 + 整体点评
**When** 二者存在
**Then** 共同作为「改进本章」输入（`canImprove = 有点评或批注`，原型 app.js:1099/1115），说明「段落批注和整体点评都会用于"改进本章"」

### Story 4.6: 改进本章 / 重新生成整章

As a 对正文不满意的用户，
I want 用我的反馈改进本章、或干脆重写整章，
So that 我能把这一章打磨到我认可为止。

**Acceptance Criteria:**

**Given** 我要改进本章（FR20，UX-DR7，原型 `data-chapter-revision="improve"`）
**When** 我点「改进本章 →」
**Then** 要求具体反馈——无点评且无批注时按钮 disabled 且守卫拦截（`canImprove`，原型 app.js:1336-1341）；改进尽量保留现有内容，消费段落批注 + 整体点评作输入

**Given** 我要重新生成整章（原型 `data-chapter-revision="regenerate"`）
**When** 我点「重新生成」
**Then** 允许不填反馈、替换整章、清除旧批注（`chapterAnnotations=[]`，原型 app.js:1360）

**Given** 改进/重生成执行中
**When** 流水线运行（替代原型 900ms mock）
**Then** 显示忙碌态（`chapterAgentBusy`，原型文案 improve「正在根据你的点评改进这一章……」/ regenerate「正在重新规划并生成这一章……」，app.js:1346-1349），完成后 `chapterRevision` 递增、回第一页

**Given** 改进/重生成走真实流水线
**When** 每次修订
**Then** 走 4.2 四段流水线（仍受 style_profile + 去 AI 味词表约束，NFR1）；修订版本可追溯

### Story 4.7: 定稿本章 + 阶段循环 + 阶段交界方向输入

As a 对某章满意的用户，
I want 定稿本章、无感进入下一章，并在阶段交界处轻量表达走向，
So that 我能持续写下去，并在关键处对故事收尾有唯一的主动控制点。

**Acceptance Criteria:**

**Given** 我要定稿本章（FR21，原型 `data-finalize-chapter`）
**When** 我点「定稿本章 →」
**Then** 当前版本成为后续章节创作的正式上下文（FR21，真实持久化，替代原型仅跳转无数据传递）；定稿后本章不可再批注/改进（原型 `chapterFinalized` 隐藏反馈表单与 `＋` 按钮，app.js:1108/1176）

**Given** 章节定稿（接 Epic 5 归档）
**When** 定稿完成
**Then** 触发 Epic 5 的章节卡片生成 + 写后投影（chapter-commit，跨 epic 衔接）；原型定稿即跳归档页（app.js:1375）

**Given** 阶段循环幕后推进（FR22）
**When** 一章接一章
**Then** 阶段推进对用户无感（无阶段规划页/确认弹窗），续写下一章回到输入态循环（原型 `data-start-next-chapter`，app.js:1635-1655）

**Given** 阶段交界的方向输入（FR22，原型完全缺失的新增项，须新增）
**When** 到达阶段交界处
**Then** 提供一个极轻、可跳过的方向输入（「这一段想往哪走？/ 直接继续」），是用户主动表达进入收尾的唯一控制点、不可省略（FR22）

**Given** 阶段交界方向输入
**When** 我填写走向或选「直接继续」
**Then** 该输入衔接下一章/下一阶段生成；选「直接继续」则幕后按既有阶段计划推进

**Given** 长程一致性（NFR4）
**When** 故事写到很长（几百章量级）
**Then** 一致性机制不设人为章数上限、不砍成 20–50 章；状态/人物/世界规则/时间线/伏笔不穿帮（投影机制由 Epic 5 兑现）

## Epic 5: 故事档案与归档（含 RAG）

章节定稿后自动凝练成章节卡片并持久化，归档页作为故事档案统一入口（设定圣经 + 分阶段章节归档一处呈现）；RAG 三级召回回头增强创作的写前上下文，防长篇跑偏穿帮。

**Story 依赖**：5.1 →5.2 →{5.3 →5.4（归档页）, 5.5 →5.6（RAG）}；两链在 5.2 后并行。
**按需建表**：5.1 `chapter_card`/`story_thread`/`story_state` · 5.5 `embedding`。
**关键跨 epic 衔接**：① 5.2 承接 Epic 4 定稿触发、补齐流水线第五段 data-agent。② 5.6 回改 Epic 4 Story 4.4 写前上下文注入点（从「全量设定+最近章节」升级为完整召回）。③ 5.3 消费 Epic 3 story_bible 展示设定圣经。

### Story 5.1: 归档核心表落地（chapter_card / story_thread / story_state）

As a Muse 后端开发者，
I want 承载章节卡片、未回收线索、故事状态的三张一致性核心表，
So that 写后投影有落点、长程一致性有数据根。

**Acceptance Criteria:**

**Given** AR8 五张核心表（story_bible 已在 Epic 3 建、embedding 归 Story 5.5）
**When** 建表迁移执行
**Then** 建 `chapter_card`（章节卡片）、`story_thread`（未回收伏笔/线索）、`story_state`（主角状态/世界规则/当前阶段）三表，均带 `user_id`+`project_id`（NFR3）

**Given** 三表都服务写后投影（Story 5.2 的直接落点）
**When** 设计表结构
**Then** `chapter_card` 存章节归档五要素（本章发生了什么/人物变化/新增事实与线索/未解决悬念/章末状态）、`story_thread` 存伏笔状态、`story_state` 存主角与世界规则当前快照

**Given** 多租户隔离（NFR3）
**When** 任意读写三表
**Then** repository/DAO 层强制注入租户守卫，不越权

**Given** 后续 Story（5.2 投影、5.3 归档展示）依赖三表
**When** 表就位
**Then** 结构支持单事务原子投影（为 Story 5.2 chapter-commit 做准备）

### Story 5.2: 写后投影——data-agent + chapter-commit 单事务

As a 持续写作的用户，
I want 每章定稿后系统自动把这一章的事实沉淀成结构化档案，
So that 后续章节能记住已发生的一切、不穿帮。

**Acceptance Criteria:**

**Given** 章节定稿（接 Epic 4 Story 4.7，写后投影归本 epic）
**When** 定稿触发
**Then** data-agent 从定稿正文提取事件/状态变化/新增实体为结构化 JSON（AR17）

**Given** 提取完成（AR17，NFR4）
**When** 投影回库
**Then** 以单事务 chapter-commit 原子投影回 `story_state` / `chapter_card` / `story_thread`（+ `embedding` 见 Story 5.5），防半更新穿帮

**Given** 章节卡片真实生成（FR23）
**When** 投影完成
**Then** `chapter_card` 含五要素并持久化，写下一章时作为长期上下文注入（接 Epic 4 写前上下文）

**Given** data-agent 是 Epic 4 流水线的第五段（V1 前四段已在 E4 落地）
**When** 本 story 实现
**Then** 补齐 `context→drafter→reviewer→polisher→data-agent` 完整五段（AR11），data-agent 为写后段

**Given** 投影是多步 LLM + DB 操作
**When** 某步失败
**Then** 单事务回滚、不留半更新状态（NFR4 一致性投影原子性），可重试

### Story 5.3: 归档页——故事档案统一入口（设定圣经 + 分阶段）

As a 想回顾自己作品的用户，
I want 在一处看到我定下的设定圣经和我已写下的章节归档，
So that 「我定的规则 + 我已写的事实」一目了然。

**Acceptance Criteria:**

**Given** 归档页作为故事档案统一入口（FR24，UX-DR8）
**When** 我打开归档页（`#/projects/:id/archive`）
**Then** 顶部展示已确认的设定圣经（消费 Epic 3 story_bible）、下方是分阶段的章节归档（原型 `archive-story-profile` + `archive-stage-group`）

**Given** 章节卡片来自真实投影（Story 5.2）
**When** 归档页渲染各阶段章节
**Then** 展示真实 `chapter_card` 数据（替代原型第二阶段硬编码 4 章 preview mock、`stagePlanningDraft` 恒空的占位）

**Given** 设定圣经区（原型 `archiveStoryProfile`）
**When** 渲染
**Then** 展示已确认设定的 12 字段（替代原型缺省占位 app.js:1513），字段以 `NN / 字段名` 编号呈现

**Given** 数据多租户隔离（NFR3）
**When** 我访问归档页
**Then** 只显示属于我的设定圣经与章节归档

### Story 5.4: 归档页——首屏收起/展开交互 + 章节归档详情

As a 浏览归档的用户，
I want 首屏清爽、按需展开我关心的部分、点开单章看详情，
So that 我能自由控制信息密度、不被一屏塞满。

**Acceptance Criteria:**

**Given** 归档页首屏（FR25，UX-DR8）
**When** 页面加载
**Then** 首屏为清爽概览，设定圣经与各阶段默认收起（原型 `archiveStagesInitialized` 预置收起 + `archiveProfileCollapsed`，app.js:152-154）

**Given** 我点某行标题（原型 `archive-stage-toggle` / `data-toggle-archive-profile`）
**When** 点击
**Then** 该区展开/收起并带高度动画（原型 `archive-stage-collapse` + `is-collapsed`），`aria-expanded` 同步、箭头 ↓/↑ 切换（app.js:1500-1505）

**Given** 多个可折叠区（设定圣经 + 各阶段）
**When** 我展开/收起其中一个
**Then** 各区状态互相独立、由我自由控制（FR25，原型每区独立收起态）

**Given** 我点某章卡片（原型 `archive-chapter-card` / `data-open-archive-chapter`）
**When** 点击
**Then** 弹出该章归档详情弹窗（原型 `archive-dialog`，app.js:1464-1468），展示章节五要素，页脚「这份归档将作为后续章节创作的长期上下文。」

**Given** 我点续写下一章卡片（原型 `data-start-next-chapter`）
**When** 点击
**Then** 进入下一章创作输入态（衔接 Epic 4 章节循环，app.js:1635-1655）

### Story 5.5: embedding 表 + EmbeddingProvider（pgvector）

As a Muse 后端开发者，
I want 一张 pgvector embedding 表和可切换的 EmbeddingProvider 抽象，
So that 长篇故事的历史事实能被语义检索、为 RAG 打底。

**Acceptance Criteria:**

**Given** AR8/AR10 要求向量库与关系数据同库
**When** 建表迁移执行
**Then** 建 `embedding` 表（pgvector chunk + 向量 + 元数据），带 `user_id`+`project_id`（NFR3），用 pgvector 0.8.x + HNSW 索引

**Given** EmbeddingProvider 抽象（AR18，类比 LLMProvider）
**When** 定义接口并实现
**Then** 支持阿里/智谱 embedding 实现、可切换；业务层只依赖接口

**Given** 章节投影时（接 Story 5.2 chapter-commit）
**When** 定稿正文投影
**Then** 章节内容 chunk 化 + 向量化写入 `embedding`（纳入 5.2 的单事务或紧随其后）

**Given** 无 embedding key 的降级（AR18）
**When** 未配置 embedding Provider
**Then** 退回纯 tsvector 关键词、不阻断（RAG 召回质量下降但可用）

**Given** 数据不出境（NFR8）
**When** 选 embedding Provider
**Then** embedding（阿里/智谱）与 LLM（DeepSeek）同区，满足数据合规

### Story 5.6: RAG 三级召回接回写前上下文

As a 写长篇的用户，
I want 系统在写新章节时自动调取相关的历史设定与事实，
So that 就算写到几百章，故事也不会前后矛盾、跑偏穿帮。

**Acceptance Criteria:**

**Given** RAG 三级召回（AR18）
**When** 实现召回
**Then** 向量（pgvector HNSW）+ tsvector 关键词 + RRF 融合 + rerank 三级召回

**Given** RAG 回头增强 Epic 4 写前上下文（架构原意「回头增强」）
**When** context-agent 组装写作任务书
**Then** 回改 Epic 4 Story 4.4 的写前上下文注入点——从「全量设定+最近定稿章节」升级为「story_bible + 最近 chapter_cards + 未回收 story_threads + 世界规则 + 主角状态 + RAG 召回的相关历史」（AR16）

**Given** 真 BM25（pg_search）V1 用 tsvector 近似（AR18）
**When** V1 实现关键词召回
**Then** 用 tsvector 近似 BM25、不引入 pg_search（视需要 V2 引入）

**Given** 长程一致性（NFR4，不设章数上限）
**When** 故事写到几百章
**Then** RAG 召回让写前上下文覆盖长距离伏笔/设定，状态/人物/世界规则/时间线不穿帮

**Given** embedding 降级场景（接 Story 5.5）
**When** 无 embedding key
**Then** RAG 退化为纯 tsvector 关键词召回、仍能提供基础一致性保障

## Epic 6: 通读与交付

用户拿到「一本真正的小说」——全本连续通读视图，按顺序呈现已定稿章节，并标注「AI 辅助生成」满足合规。

**Story 依赖**：6.1 →6.2（AI 标识叠加在通读视图上）。
**按需建表**：无（消费 Epic 4 已定稿章节）。
**说明**：原型无通读视图页（全新页面，无既有交互契约可继承），AC 依 FR26 + UX-DR3 + NFR7a 从需求出发。

### Story 6.1: 全本连续通读视图（全新页面）

As a 写完（部分）章节的用户，
I want 从头到尾连续读一遍我自己写的书，
So that 我能以读者视角体验「我写出了一本真正的小说」。

**Acceptance Criteria:**

**Given** 原型无通读视图页（全新页面，FR26；原型最终页仅到归档 `archive`）
**When** 我从作品入口进入通读视图
**Then** 按顺序连续呈现该作品所有已定稿章节的正文（消费 Epic 4 定稿章节），让我从头读一遍自己的书

**Given** 通读视图连续呈现
**When** 我阅读
**Then** 已定稿章节按章节顺序无缝拼接呈现（区别于 Epic 4 单章分页创作视图），只读、聚焦阅读体验

**Given** 数据多租户隔离（NFR3）
**When** 我打开通读视图
**Then** 只呈现属于我（当前 `user_id` + `project_id`）的已定稿章节

**Given** 只有已定稿章节进入通读（与 Epic 4 定稿态一致）
**When** 某章尚未定稿
**Then** 未定稿章节不进入通读视图（通读是「已完成的书」的视图）

**Given** 作品尚无任何已定稿章节
**When** 我进入通读视图
**Then** 呈现合理空态提示（还没有可通读的已定稿章节），不报错

### Story 6.2: AI 辅助生成标识（合规）

As a Muse 运营方 / 用户，
I want 通读视图明确标注「AI 辅助生成」，
So that 满足 2025.9.1 起 AI 生成内容强制标识的合规要求。

**Acceptance Criteria:**

**Given** AI 辅助生成内容强制标识合规（2025.9.1 起，NFR7a/UX-DR3）
**When** 通读视图（V1）渲染
**Then** 标注「AI 辅助生成」标识，满足强制标识要求

**Given** 标识须清晰可见、不误导
**When** 用户阅读通读视图
**Then** 「AI 辅助生成」标识在视图中明确呈现（位置合理、不影响阅读但可被识别）

**Given** 合规是交付前提
**When** Epic 6 通读视图上线
**Then** AI 标识作为通读视图的必备组成（无标识不合规、不可交付）

## Epic 7: 前端真实接线与端到端集成（2026-07-30 Correct Course 新增）

用户能在真实浏览器里走通「注册登录→管理作品→探索→出设定圣经」全闭环，所有数据来自后端而非 mock。本 epic 把 Epic 1-3 已 done 的后端 API 首次接上前端原型，偿还 1.6–3.5 积压的接线债（`app.js` 2374 行至今零 fetch/零 token）。

**背景**：旧节奏「后端先行、前端 later 统一接」导致 Epic 1-3 后端全 done 但从未经真实前端验证。本 epic 是「前后端一起走」转向后的一次性还债工程；此后新 story 默认前后端一起交付。
**Story 依赖**：7.1 →7.2 →{7.3, 7.4}；7.2 →7.5 →7.6；{7.5, 7.6} →7.7。7.1 统一请求工具为全 epic 硬前置（不接则所有请求 401）。**7.6 另依赖 Epic 2 Story 2.8**（2026-07-31 Correct Course 新增：自由探索设定导航/按需回答思路/7项完成度门禁）——7.6 须先消费 2.8 提供的后端能力才能重写自由探索前端交互，不可只接旧版 2.6/2.7 门禁。
**按需新增 UI**：7.4 BYOK 设置页 + 用量入口（UX-DR2，原型无）· 7.7 文风锚点入口（UX-DR1，原型无）。其余 story 严格保持原型既有交互契约，只把数据源从 mock 换成后端。
**说明**：本 epic 不新增 FR，兑现 FR1–FR16 的前端侧；AC 事实来源 = 原型页面契约（`prototype/app/`）+ UX-DR + 对应后端已 done 接口。

### Story 7.1: 统一请求工具地基（token / 401 跳转 / error envelope / camelCase 边界）

As a Muse 前端开发者，
I want 一个统一的请求工具封装 token 注入、401 刷新/跳转、error envelope 解包与命名边界，
So that 后续所有页面接线都建立在一致、可复用的连接底座上，不重复造轮子。

**Acceptance Criteria:**

**Given** app.js 当前零 fetch、零 token（纯 mock）
**When** 引入统一请求工具（如 `apiFetch`）
**Then** 所有业务请求经它发出，自动注入 `Authorization: Bearer <access>`，无 token 时不附带

**Given** 后端返回统一 error envelope `{code, message, detail}`（AR5）
**When** 任一请求失败
**Then** 工具统一解包 envelope，向调用方抛出结构化错误（含 code），页面据 code 分支呈现，不裸露原始响应

**Given** access token 过期、持有 refresh token（AR3）
**When** 请求返回 401
**Then** 工具自动用 refresh 换新 access 并重放原请求；若 refresh 亦失效，跳 `#/login?state=expired`（原型 app.js:246 契约）

**Given** DB/后端为 snake_case、API 边界为 camelCase（AR4）
**When** 前端收发数据
**Then** 请求工具层收敛命名转换，页面代码只见 camelCase，不散落转换逻辑

**Given** 地基须可被 7.2–7.7 复用
**When** 后续页面接线
**Then** 复用同一工具，不各自实现 token/401/error 处理（本 story 只建地基与登录注册所需最小闭环，不接业务页）

### Story 7.2: 登录 / 注册接线（真实会话，替换 mock）

As a 用户，
I want 在真实登录/注册页用账号进出创作空间，
So that 我的会话与身份由后端真实签发，而非前端假数据。

**Acceptance Criteria:**

**Given** 注册页（`#/register`，邀请码必填、密码 minlength=8，原型 app.js:294-296）
**When** 我提交有效邀请码 + 邮箱 + 密码
**Then** 经 7.1 工具调后端注册接口，成功后存 token 并按原型跳 `#/projects`；邀请码无效/已用/过期呈现 `invalid` 文案「邀请码无效、已使用或已过期。」（app.js:249-252）

**Given** 登录页（`#/login`）
**When** 我用正确邮箱密码登录
**Then** 调后端登录接口取 access + refresh 双 token 持久化，进 `#/projects`；错误呈现 `invalid`「邮箱或密码错误，请检查后重试。」（app.js:247-248）

**Given** 登录失败超阈值触发后端限流（AR6）
**When** 后端返回 locked
**Then** 前端呈现 `locked`「登录尝试次数过多，请稍后再试。」（app.js:253）

**Given** 会话过期（refresh 失效，7.1 已处理跳转）
**When** 我被跳回 `#/login?state=expired`
**Then** 呈现 `expired`「会话已过期，请重新登录。登录后会返回你的创作空间。」（app.js:246）

**Given** 我已登录
**When** 点作品库 header「退出」（app.js:374）
**Then** 调后端登出使 refresh 作废、清本地 token，回登录态

**Given** UX-DR9 错误位对接
**When** 各错误分支触发
**Then** 前端布尔状态位（expired/invalid/locked）严格对应后端 error envelope 的 code，不臆造分支

### Story 7.3: 作品库接线（列表 / 新建 / 重命名 / 删除 / 空·失败态 / 继续创作跳转）

As a 已登录用户，
I want 在作品库真实管理我的多部作品，
So that 我的作品数据持久化在后端、跨设备可回到。

**Acceptance Criteria:**

**Given** 作品库页（`#/projects`）此前渲染 mock 列表
**When** 页面加载
**Then** 经 7.1 工具拉取当前用户真实作品列表并渲染（FR2）；仅呈现属于我（`user_id`）的作品（NFR3）

**Given** 列表为空 / 加载失败
**When** 后端返回空集或错误
**Then** 分别呈现原型 `empty` / `error` 状态位（UX-DR9），不报裸错

**Given** 新建 / 重命名 / 删除操作
**When** 我执行对应操作
**Then** 调后端真实持久化，成功后列表反映最新状态（FR2）；删除按原型交互确认后生效

**Given** 作品行主操作「继续创作」（FR3）
**When** 我点击
**Then** 读该作品后端 `phase` 字段，跳转到当前所处创作步骤（探索/章节/归档），而非固定路由

**Given** 未登录 / token 失效访问作品库
**When** 请求 401
**Then** 由 7.1 统一处理跳登录，不在本页重复实现

### Story 7.4: BYOK 设置页 + 托管用量入口接线（含 UX-DR2 须新增 UI）

As a 关注成本/隐私的用户，
I want 绑定自己的 API Key 并查看托管免费额度用量，
So that 我能自主选择走自己的 Key 或托管额度，并掌握用量。

**Acceptance Criteria:**

**Given** 原型无 BYOK 设置页与用量入口（UX-DR2 · A 类须新增 UI）
**When** V1 前端集成
**Then** 新增 API Key 绑定页 + 托管用量/剩余免费额度展示入口，形态与原型整体风格一致

**Given** 我在设置页填入 API Key（FR4）
**When** 提交绑定
**Then** 经 7.1 工具调后端绑定接口（后端 AES-GCM 加密存储，NFR6）；绑定后该账户生成走用户 Key

**Given** 托管默认路径受免费额度护栏约束（FR4，后端 1-8 已建 usage_ledger + 校验框架）
**When** 我打开用量入口
**Then** 展示真实用量/剩余免费额度（消费后端 usage 接口），额度耗尽按后端护栏结果呈现

**Given** Key 绑定态可解绑/更换
**When** 我更换或解绑 Key
**Then** 前端反映最新绑定状态，操作经后端持久化

**Given** 多租户隔离（NFR3）
**When** 我查看 Key/用量
**Then** 只呈现属于我的绑定与用量数据

### Story 7.5: 引导探索接线（SSE 流式问答 / 翻页持久化 / 整理中过渡 / 设定卡弹出）

As a 选了引导模式的用户，
I want 与真实 Explorer Agent 做沉浸问答并真实保存答案，
So that 我聊出的故事线索被真实持久化、可翻页修改。

**Acceptance Criteria:**

**Given** 新建作品选引导模式（FR5，模式独立不中途切换）
**When** 进入引导探索
**Then** 经 7.1 工具建探索会话，接后端真实 Explorer Agent（FR6）；长时生成走 POST+SSE 异步（NFR2），前端消费 SSE 流式呈现

**Given** 引导探索交互契约（UX-DR4）
**When** 呈现问答
**Then** 只显当前一题 + 选项、无历史无右侧线索区；第一题一句话自述、其余题「都不是这些」出口——严格保持原型契约，只把数据源换成后端

**Given** 问卷式前后翻页（FR7）
**When** 我翻页/翻回/重选
**Then** 答案经后端真实持久化（FR11）；翻页不清答案、翻回高亮回填、重选只更新该题不影响其后（app.js 既有交互契约不变）

**Given** 答完最后一题（FR8）
**When** 触发收尾
**Then** 先进「整理中」过渡态（约 1.2s）再弹后端生成的设定卡；中途「回到探索」过渡态复位、回可翻页收尾态

**Given** 待确认设定卡浏览器会话内恢复（FR11）
**When** 刷新页面
**Then** 不回退到探索主界面，恢复待确认态（消费后端持久化状态）

### Story 7.6: 自由探索接线（系统引导 / 按需回答思路 / 线索编辑持久化 / 7项完成度门禁）

> **2026-07-31 Correct Course 修订**（Sprint Change Proposal 2026-07-31）：本 story 已在进行中；已实现的 SSE 消费、Bearer/401、AbortController、自由消息真实持久化、右侧 preset/custom 线索 CRUD、`user_edited` 保护、跨项目/跨账号加载代次与清理、free settle task SSE 与候选卡弹出**全部保留**。本次修订**替换**的只是「固定给方向文案」与「一条消息即门禁」两处过时产品逻辑，改为消费 Story 2.8 提供的自由探索导航能力。

As a 选了自由模式的用户，
I want 系统主动帮我发现故事设定还缺什么、每轮只问一个具体问题，并在我卡住时提供可选思路，
So that 我不会被同一话题无限追问，也能确认设定卡在整理前已经足够完整。

**Acceptance Criteria:**

**Given** 新建作品选自由模式（FR5）
**When** 进入自由探索
**Then** 经 7.1 工具建会话接真实 Explorer Agent（FR9），对话走 SSE 流式（NFR2）；连续只读对话记录不折叠不拆分（UX-DR5）；进页同时拉取 Story 2.8 的导航状态（7 项完成度、当前问题、`readyToSettle`）

**Given** 会话尚无任何对话（UX-DR5 零对话起点）
**When** 页面渲染
**Then** 展示「你想从哪里开始？」四个固定入口（故事想法 / 主角 / 核心冲突 / 世界与氛围）；点击后调用 2.8 后端能力生成对应第一问，作为本轮对话开场；不展示旧版「给我一些方向」复选框与固定三文案

**Given** 对话进行中，Agent 已针对某个缺失主干项提出具体问题（UX-DR5 当前具体问题）
**When** 用户不知道怎么回答
**Then** 用户可点击「没想好？看看几个思路」，按需请求当前问题相关的 2–4 个 AI 回答选项；点击任一选项直接作为本轮回答提交并触发导航状态刷新

**Given** 用户面对当前问题
**When** 用户点击「先跳过这个问题」
**Then** 该项标记 `skipped`、系统据已有材料谨慎归纳并推进到下一缺失项或收束；本项本轮不再被重复追问

**Given** 右侧「故事线索」区（FR9，UX-DR5）
**When** 我直接编辑线索
**Then** 编辑经后端真实持久化（FR11）；用户编辑优先、不被 Agent 自动整理或导航归纳覆盖（延续 2.6 `user_edited` 硬约束）

**Given** 「整理为故事设定」门禁（FR10，消费 2.8 后端 `readyToSettle`）
**When** 7 项通用主干尚未全部 `filled`/`skipped`
**Then** 按钮不可用，前端据当前导航状态呈现提示；若用户绕过前端直接触发 settle，后端 400 拒绝并回传当前缺失项，前端据此展示可读提示（不得只依赖「≥1 条用户消息」的旧判据）

**Given** 7 项通用主干均已 `filled`/`skipped`（`readyToSettle=true`）
**When** 导航状态刷新
**Then** Agent 在对话流中呈现明确收束提示；「整理为故事设定」按钮开放，用户主动点击后走既有 free settle SSE 流程弹出候选卡（复用 2.7/3.3 已有链路，不重建）

**Given** 对话、线索与导航状态持久化（FR11）
**When** 刷新
**Then** 恢复对话记录、线索区与当前导航进度（当前问题/完成度/收束态），不丢失、不回退到「从头开始」

### Story 7.7: 设定卡 + 文风锚点接线（含 UX-DR1 须新增 UI）

As a 结束探索的用户，
I want 编辑真实生成的 12 字段设定卡、锚定文风并确认成设定圣经，
So that 我的设定成为只读全文上下文，注入后续所有创作。

**Acceptance Criteria:**

**Given** 探索结束真实生成 12 字段设定候选卡（FR12，后端 3-3 已做）
**When** 设定卡呈现
**Then** 渲染后端返回的 12 字段（通用主干 7 + 题材特化 4 按 genre 激活 + 文风锚点 1），特化字段可空按 genre 显隐

**Given** 设定卡可直接编辑、反馈升版本（FR13，UX-DR6）
**When** 我编辑并向 Agent 反馈
**Then** 经 7.1 工具调后端生成新版本，提升版本号 + 标出本轮变化项（消费后端 3-4 真实 Agent 结果）

**Given** 文风锚点入口（FR16，UX-DR1 · A 类须新增 UI，原型无）
**When** V1 前端集成
**Then** 新增「从预置样本库选择/粘贴一段爱读文字」入口，提交后端抽取 style_profile（后端 3-2 已做），作为字段⑫呈现

**Given** 确认设定（FR14，UX-DR6）
**When** 我确认
**Then** 设定成只读设定圣经、清除待确认态（消费后端 3-5）；确认后为后续创作只读上下文

**Given** 「回到探索」（FR15，UX-DR6）
**When** 我点击
**Then** 二次确认后调后端丢弃当前设定内容与修改记录

**Given** 待确认卡会话内恢复（FR11/UX-DR6）
**When** 刷新
**Then** 不回退、恢复待确认态
