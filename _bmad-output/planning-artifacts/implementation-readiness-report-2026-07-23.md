---
stepsCompleted: [1, 2, 3, 4, 5, 6]
documentsIncluded:
  - Muse-PRD-V1.md
  - Muse-PRD-V1-addendum.md
  - Muse-PRD-V1.decision-log.md
  - _bmad-output/planning-artifacts/architecture.md
  - _bmad-output/planning-artifacts/epics.md
  - _bmad-output/planning-artifacts/prfaq-Muse.md
  - _bmad-output/planning-artifacts/ux-designs/ux-Muse-2026-07-23/DESIGN.md
  - _bmad-output/planning-artifacts/ux-designs/ux-Muse-2026-07-23/EXPERIENCE.md
  - prototype/spec/prototype-spec.md
  - prototype/spec/exploration-pending-requirements.md
---

# Implementation Readiness Assessment Report

**Date:** 2026-07-23
**Project:** Muse

## 文档盘点（Step 1 · Document Discovery）

### PRD 文档
- `Muse-PRD-V1.md`（主 PRD，项目根目录）
- `Muse-PRD-V1-addendum.md`（技术 how 归档：选型/成本/护城河）
- `Muse-PRD-V1.decision-log.md`（决策日志）

> ℹ️ **位置偏离规范**：PRD 三件套位于项目根目录，BMAD 规范路径应为 `planning-artifacts/prds/prd-Muse-.../prd.md`。**决定暂不迁移**——architecture.md 与 epics.md 已将根目录路径钉为 `inputDocuments` 事实源，迁移会打断事实链。仅在此记录。

### 架构文档
- `_bmad-output/planning-artifacts/architecture.md`（status: complete，2026-07-22）

### Epics & Stories
- `_bmad-output/planning-artifacts/epics.md`（stepsCompleted 1-4，2026-07-23 最新）

### UX 设计文档 —— 本次校验中补齐
- `ux-designs/ux-Muse-2026-07-23/DESIGN.md`（视觉 spine · draft）
- `ux-designs/ux-Muse-2026-07-23/EXPERIENCE.md`（体验 spine · draft）
- `ux-designs/ux-Muse-2026-07-23/.decision-log.md`（决策日志）

> **背景**：盘点时未发现独立 UX 文档。查证确认 Muse 采用"页面即契约"方法论——UX 事实基准 = `prototype/app/` 原型（可交互）+ `prototype/spec/prototype-spec.md` 行为契约，非传统 UX 稿。经创始人确认，**从原型反向蒸馏**出 BMAD 规范形态的 DESIGN/EXPERIENCE，两份文件均显式声明"服从原型、不凌驾"（与 BMAD-UX 默认 spine-wins 规则相反，以守住 Muse"原型=唯一事实基准"铁律）。

### 事实基准 / 输入源
- `prototype/spec/prototype-spec.md`（行为契约权威）
- `prototype/spec/exploration-pending-requirements.md`（待实现机制权威：EXP-P01/P02）
- `prototype/app/`（index.html / styles.css 3901 行 / app.js 1905 行 —— 契约最终事实基准）
- `prfaq-Muse.md`（PRFAQ 裁决源头）

### 盘点结论
- ✅ 无重复版本冲突（无整篇+分片并存）。
- ✅ PRD / 架构 / Epics / UX 四类文档齐备（UX 于本次补齐）。
- ⚠️ PRD 位置偏离规范（已决定暂不动，见上）。
- 📌 蒸馏中发现的事实纠偏已记入 UX `.decision-log.md`：存储实为 sessionStorage（非 localStorage）；登录 error 态为预览态；`--sans`/`--line-soft` 为未定义缺陷 token。

---

## PRD 分析（Step 2 · PRD Analysis）

### 分析方法说明
Muse PRD 采用「**开发模块 × 能力版本（V1/V2/V3）**」矩阵组织，非传统 `FR1/FR2` 编号式。为支撑 Step 3 逐条追溯，本节把每条能力陈述编号为 `FR-<模块>.<序>`（功能）与 `NFR-<序>`（非功能/跨切面），并标注**版本档**。本次为 V1 实现就绪校验，故 **V1 项为追溯重点**；V2/V3 一并登记，用于 Step 3 判断 Epic 是否遗漏 V1 或误纳 V2/V3。

### 🔴 PRD 内部一致性缺陷（Step 2 首要发现，影响后续追溯基线）
> **DRIFT-01｜行为红线与盲测章节在主 PRD 缺失**
> `decision-log.md`（2026-07-20）与 `addendum.md` 头部均声明：Q7 行为红线已灌入主 PRD **§7.1（不及格/及格线/理想 三档判据表）**、Q2 盲测前置已灌入 **§7.2 + 模块 3 V1**、原「七、已定决策」**顺延为§八**、Q4-B 托管+BYOK **挂进模块 0**。
> **实测主 PRD（`Muse-PRD-V1.md`，221 行）：** §七仍为「已定决策」（仅 5 项，未顺延）；**无 §7.1/§7.2**；模块 0 正文（L102–111）**无 BYOK/托管额度**能力；模块 3 V1（L152–155）**无盲测前置**表述。
> **影响：** ①行为红线是记忆与 PRFAQ 反复强调的 **launch blocker**，其「验收判据定义」被 addendum B 节显式甩给主文档 §七，而主文档并无 → **红线判据在全体文档中无完整落地**，Epic 无法据此写验收标准。②BYOK/托管额度、盲测门禁的正文缺失，使这些需求的追溯源头只能退回 addendum（技术附录，非能力正文）。
> **处置建议：** 记为高优先级 gap；Step 3 追溯这些需求时以 **addendum + decision-log 的意图**为准绳（而非主 PRD 正文），并在最终报告标记「PRD 正文需补写§7.1/§7.2 与模块 0 BYOK 能力」为实现前置修复项。

### Functional Requirements（功能需求）

#### 模块 0 · 账户与作品管理（旅程：门厅）
- **FR-0.1**（V1）真实注册登录与会话管理（邮箱密码登录、邀请码注册）。
- **FR-0.2**（V1）作品的增删改查（继续/重命名/删除/新建）与持久化。
- **FR-0.3**（V1）"继续创作"跳转到该作品**当前所处步骤**（探索/创作/通读的断点恢复）。
- **FR-0.4**（V1，来源=decision-log/addendum C，主 PRD 正文缺失见 DRIFT-01）托管为主：Muse 出 Key、用户零门槛即写；**成本护栏=托管免费额度上限**（N 章/天或 N 次/天，数值待盲测出单章成本后定）。
- **FR-0.5**（V1，同上来源）进阶 BYOK：设置页绑定自有 API Key、成本自付、解绑额度。（*注：设置页/用量入口原型暂无，须新增*）
- **FR-0.6**（V2）作品封面/简介、创作进度概览（已写章节数、字数）。
- **FR-0.7**（V3）多端同步、回收站、作品导入。

#### 模块 1 · 探索（旅程：探索主线）
- **FR-1.1**（V1）接入真实 Explorer Agent 的多轮对话；**有限问题集**跑通，非动态选题。
- **FR-1.2**（V1）对话记录与故事线索持久化。
- **FR-1.3**（V1）**引导探索**双模式之一：纯选项式沉浸问答，一次聚焦一题；第一题可一句话自述、其余题提供"都不是这些"自答出口；底部导航栏问卷式前后翻页；答完最后一题先进"整理中"过渡态再弹故事设定卡。
- **FR-1.4**（V1）**自由探索**双模式之一：连续只读对话记录；右侧"故事线索"区可直接编辑；"给我一些方向"只写入输入框不代答；信息充分后才开放"整理为故事设定"。
- **FR-1.5**（V1）两模式产出**同一套故事设定**；新建作品时二选一，进入后各自独立、不在途中切换。
- **FR-1.6**（V2）动态选题：实现 EXP-P01（问题原型库与动态选题）+ EXP-P02（以覆盖度决定探索是否完成）；问题数量/顺序不固定，覆盖充分才开放整理。
- **FR-1.7**（V3）跨作品的用户创作偏好沉淀，复用于新作品探索。

#### 模块 2 · 故事设定 / 设定圣经（旅程：故事档案常驻层——"我定下的规则"）
- **FR-2.1**（V1）真实生成故事设定，含六维：核心吸引力、主角与欲望、主要冲突、关键世界规则、整体气质、目标阅读体验。
- **FR-2.2**（V1）用户可编辑候选设定；可向 Agent 反馈生成新版本。
- **FR-2.3**（V1）确认后设定变为只读的全文指导上下文，注入后续所有创作；"回到探索"需二次确认并丢弃当前设定。
- **FR-2.4**（V1）设定在归档页（故事档案统一入口）可查阅。
- **FR-2.5**（V1，decision-log 主动判断上提至 V1）**文风样本锚点**：原型设定页须新增风格样本锚点，作为§7.1 行为红线「像不像用户要的味道」的验收前提。（*原型须新增*）
- **FR-2.6**（V2）设定圣经：从「按章节纵向记录」升级为「按实体横向维护」——人物/地点/世界规则/时间线各成条目，防穿帮。
- **FR-2.7**（V2）**文风锁定**：人称、语气、句式节奏一经设定，写作全程遵循。
- **FR-2.8**（V3）设定变更影响分析（改一条设定，提示哪些已写章节受影响）。
- **FR-2.9**（暂缓）设定卡片版本号 + 逐版 diff 展示。

#### 模块 3 · 创作（旅程：创作主线，用户 95% 时间）
- **FR-3.1**（V1）**首个阶段规划全程幕后**：探索确认设定后，后台完成第一阶段规划（阶段目标+章节骨架），不展示、无问答、无确认弹窗，用户体感"探索完立即进第一章"。
- **FR-3.2**（V1）真实生成章节正文，消费「故事设定 + 已定稿章节 + 归档卡片」作上下文。
- **FR-3.3**（V1）章节创作循环：可选填"本章想法"→生成正文→分页阅读→段落批注+整体点评→改进本章/重新生成整章→定稿；全部真实持久化。
- **FR-3.4**（V1）定稿版本成为后续章节的正式上下文。
- **FR-3.5**（V1）阶段循环推进（规划→创作→阶段写完→下一阶段规划），对用户无感。
- **FR-3.6**（V1）**阶段交界的方向输入（收尾控制点）**：阶段章节写完、进下一阶段前，给极轻、可跳过的"这一段想往哪走？（或直接继续）"入口；是用户主动提出进入收尾的唯一控制点，**不可省略**。
- **FR-3.7**（V2）局部重写：段落/句子级修改，保留其余内容。
- **FR-3.8**（V2）收尾阶段显式化：声明进入收尾后，Agent 转结局收束+伏笔回收模式。
- **FR-3.9**（V2）规划可展开（可选）：默认幕后，为深度用户提供查看/干预本阶段规划的进阶入口。
- **FR-3.10**（V3）多结局/分支尝试、章节级重写历史与回滚、写作节奏建议。

#### 模块 4 · 归档（旅程：故事档案常驻层——"我已写下的事实"）
- **FR-4.1**（V1）定稿后真实生成章节卡片并持久化；含"本章发生了什么/人物变化/新增事实与线索/未解决悬念/章末状态"，按阶段分组。
- **FR-4.2**（V1）章节卡片写下一章时作为上下文注入。
- **FR-4.3**（V1）归档页调整为**故事档案统一入口**，纳入设定圣经（模块 2）的查阅，一处呈现"规则+事实"。
- **FR-4.4**（V2）定稿自动回流：章节定稿时新增的人物/规则/线索**自动**回流更新设定圣经，无需用户手动确认。
- **FR-4.5**（V3）全书线索/悬念看板，追踪伏笔是否回收。

#### 模块 5 · 通读与交付（旅程：终点，原型暂无、须新增）
- **FR-5.1**（V1）全本连续通读视图。
- **FR-5.2**（V2）导出 txt/Markdown/EPUB；作品信息页（书名、简介、字数、章节目录）。
- **FR-5.3**（V3）分享链接、只读在线阅读页。

### Non-Functional Requirements（非功能 / 跨切面需求）
- **NFR-1**（V1，launch blocker，判据落点见 DRIFT-01）**文字质量行为红线（去 AI 味）**：正文须过行为红线，验收判据="风格锚定/像不像用户要的味道"，三档（不及格/及格线/理想）。**上线拦路石**。
- **NFR-2**（V1 前置门禁）**盲测前置**：DeepSeek 起草正文的质量盲测，钉死时点=**模块 3 正文接入前**；"DeepSeek 在去 AI 味约束下能否过红线"是全项目头号未验证生死假设。
- **NFR-3**（V1）**长程一致性机制**（迁移 webnovel-writer Story System）：写前 context-agent 压写作任务书→起草→写后 data-agent 提取结构化事实 chapter-commit 投影→RAG（BM25+向量+rerank，无 key 退回 BM25）召回。**章数不设人为上限**。
- **NFR-4**（V1）**多用户存储层重写**：webnovel-writer 为单机单书文件系统框架，Muse 为多用户 Web 产品，存储/调度须为多用户后端重写（PRD 正文未计入工作量，架构阶段须估算）。
- **NFR-5**（V1）**AI 强制标识**：2025.9.1 起，导出件/分享页须标注"AI 辅助生成"。
- **NFR-6**（V1）**成本结构认知**：写一章=多次调用叠加（context 拉取+起草+reviewer 审查+去 AI 味润色+data 提取，按 5–10 次/章估），叠加用户反复重写。
- **NFR-7**（贯穿）**页面即契约方法论**：开发最小单元=页面；后端逐页把 mock 数据替换为真实 AI 能力 + 持久化；页面形态基本不动。**原型（`prototype/app/` + `prototype-spec.md`）是 UX/契约唯一事实基准。**
- **NFR-8**（V1 体验约束）**创作前流程尽量薄**：探索确认设定后**无缝进第一章**，中间不插入任何问答/确认弹窗。
- **NFR-9**（许可证）webnovel-writer 为 **GPL** 项目，迁移代码前须评估许可证义务与商业形态兼容性。

### Additional Requirements（约束、边界与残留待定）
- **CON-1** 阶段规划全程幕后（V1 起）：原型"阶段规划问答 + 阶段计划确认"两屏不再作为用户流程。
- **CON-2** 设定卡片逐版 diff 后置（非 V1 必需）。
- **CON-3** 原型第二阶段归档数据仅用于多阶段排版预览，**不进入真实创作流程**。
- **CON-4** Agent 三档（Vignette/Novella/Saga）仅品牌概念，不落用户可选档位，不在 V1–V3 路线内。
- **CON-5** 同人重写钩子仅在广告投放层，**绝不进产品正式门面**，重写他人 IP 不可公开发布/商业化引流；产品内核为全原创创作。
- **OPEN-1**（待创始人拍板）数据与版权政策（是否用于训练、版权归属）——未定，占位。
- **OPEN-2**（待创始人拍板）商业模式/定价——未定（BYOK 只保证不净亏，非盈利模式）。
- **RISK-1** 撞名：Sudowrite 旗舰模型即名"Muse"，英文市场混淆风险。

### PRD 完整性初评
- ✅ **能力覆盖完整**：6 模块 × 3 版本档矩阵清晰，V1 Walking Skeleton 目标明确（注册→通读产出一本读得完的小说）。
- ✅ **边界收敛清楚**：§六与§七（已定决策）对 V1 范围裁剪明确（动态选题→V2、导出→V2、diff 后置、三档暂不做）。
- 🔴 **DRIFT-01（见上）**：行为红线§7.1/盲测§7.2/模块 0 BYOK 三处 decision-log 声称已灌入但主 PRD 正文缺失——**这是 V1 最关键 NFR（NFR-1/NFR-2）的判据源头断裂**，须在实现前补写正文。
- ⚠️ **NFR 量化缺口**：NFR-1 红线三档判据无可测阈值定义；FR-0.4 托管免费额度数值待盲测；二者互为依赖（额度取决于盲测算出的单章成本），形成 V1 前置链：**盲测(NFR-2) → 红线判据(NFR-1) + 单章成本 → 免费额度(FR-0.4)**。
- ⚠️ **技术工作量未计入**：NFR-4 多用户存储层重写、NFR-9 GPL 许可证评估，PRD 正文未估工作量，须架构阶段承接。

---

## Epic 覆盖度校验（Step 3 · Epic Coverage Validation）

### 校验方法说明
`epics.md` 已内建一套自有 FR 编号（**FR1–FR26**），是对 PRD「模块×版本矩阵」的 **V1 重归一化**（仅 V1 档、拆成可测 FR），与本报告 Step 2 的 `FR-<模块>.<序>`（覆盖全版本）编号体系不同。故本步做**双向映射**：①PRD V1 能力 → epics FR（查遗漏）；②epics FR/AR/NFR → PRD（查超范围/来源）。**校验范围=V1**（epics.md 明确声明仅覆盖 V1，V2/V3 另立）。

### 覆盖矩阵（PRD V1 能力 → epics FR）

| Step2 PRD V1 FR | PRD 能力（V1） | epics 覆盖 | 状态 |
|---|---|---|---|
| FR-0.1 | 注册登录 + 真实会话 | Epic1 FR1 / Story 1.2,1.3 | ✅ |
| FR-0.2 | 作品 CRUD + 持久化 + 空/失败态 | Epic1 FR2 / Story 1.4,1.5 | ✅ |
| FR-0.3 | 继续创作跳转当前步骤 | Epic1 FR3 / Story 1.6 | ✅ |
| FR-0.4 | 托管免费额度护栏 | Epic1 FR4 + NFR5 / Story 1.8 | ✅（来源见 COV-02） |
| FR-0.5 | BYOK 绑定 Key | Epic1 FR4 / Story 1.7 | ✅（来源见 COV-02） |
| FR-1.1 | 真实 Explorer Agent 多轮对话（有限问题集） | Epic2 FR6(引导)+FR9(自由) / Story 2.3,2.6 | ✅ |
| FR-1.2 | 对话+线索持久化 | Epic2 FR11 / Story 2.4,2.6 | ✅ |
| FR-1.3 | 引导探索（选项问答/自述出口/翻页/整理中过渡） | Epic2 FR6,FR7,FR8 / Story 2.3,2.4,2.5 | ✅ |
| FR-1.4 | 自由探索（只读对话/线索编辑/给方向不代答/门禁） | Epic2 FR9,FR10 / Story 2.6,2.7 | ✅ |
| FR-1.5 | 两模式二选一、独立、产出同一套设定 | Epic2 FR5 / Story 2.2 | ✅ |
| FR-2.1 | 真实生成故事设定（PRD **六维**） | Epic3 FR12 / Story 3.3 | ⚠️ 扩为 **12 字段**，见 COV-01 |
| FR-2.2 | 可编辑候选 + 反馈生成新版本 | Epic3 FR13 / Story 3.4 | ✅ |
| FR-2.3 | 确认后只读上下文注入 + 回到探索二次确认 | Epic3 FR14,FR15 / Story 3.5 | ✅ |
| FR-2.4 | 归档页查阅设定 | Epic5 FR24 / Story 5.3 | ✅ |
| FR-2.5 | 文风样本锚点（decision-log 上提至 V1） | Epic3 FR16 / Story 3.2 | ✅ |
| FR-3.1 | 首个阶段规划全程幕后 | Epic4 FR17 / Story 4.3 | ✅ |
| FR-3.2 | 真实生成章节正文（消费上下文） | Epic4 FR18 / Story 4.4 | ✅ |
| FR-3.3 | 章节循环（想法/分页/批注点评/改进重生） | Epic4 FR18,FR19,FR20 / Story 4.4,4.5,4.6 | ✅ |
| FR-3.4 | 定稿成后续正式上下文 | Epic4 FR21 / Story 4.7 | ✅ |
| FR-3.5 | 阶段循环幕后推进（无感） | Epic4 FR22 / Story 4.7 | ✅ |
| FR-3.6 | 阶段交界方向输入（收尾控制点） | Epic4 FR22 / Story 4.7 | ✅（原型缺失、新增项） |
| FR-4.1 | 定稿生成章节卡片 + 持久化 | Epic5 FR23 / Story 5.2 | ✅ |
| FR-4.2 | 章节卡片上下文注入 | Epic5 FR23 / Story 5.2 | ✅ |
| FR-4.3 | 归档页=故事档案统一入口 | Epic5 FR24,FR25 / Story 5.3,5.4 | ✅ |
| FR-5.1 | 全本连续通读视图 | Epic6 FR26 / Story 6.1 | ✅ |

**NFR 映射：** NFR-1 红线→epics NFR1；NFR-2 盲测→epics NFR1 内含 + AR19 + Story 4.1；NFR-3 一致性机制→epics NFR4 + AR16/17/18；NFR-4 多租户存储重写→epics NFR3 + AR7/8；NFR-5 AI 标识→epics NFR7a + Story 6.2；NFR-6 成本结构→epics NFR2 + NFR5；NFR-7 页面即契约→epics 概述 + UX-DR 全体；NFR-8 无缝进第一章→epics FR17；NFR-9 GPL→epics NFR7b。**全部 V1 NFR 有落点。**

### Missing Requirements（遗漏）
**✅ 无 V1 FR 遗漏。** PRD V1 全部 25 条能力 FR 均映射到 epics FR1–FR26，无未覆盖项；边界项（CON-3 第二阶段 mock 不进流程、CON-5 同人钩子不进门面）epics 均**正确排除**（Story 5.3 显式替换第二阶段 preview mock；同人钩子未纳入任何 V1 能力）。

### Deviations & Source Findings（偏离与追溯来源——本步核心增量）

> **COV-01｜设定字段从 6 维扩张为 12 字段（PRD 正文未同步）**
> PRD 模块 2 V1 明确写**六维**（核心吸引力/主角与欲望/主要冲突/关键世界规则/整体气质/目标阅读体验）。`epics.md` FR12 用 **12 字段**替换（通用主干 7 + 题材特化 4 + 文风锚点 1），并显式标注"原型六项为暂定未定稿，本 FR 以上表替换"。
> **依据链：** 该扩张源于记忆 `project_muse_setting_fields`（借 webnovel-writer `init-collection-schema.md` 字段结构，重塑为广谱网文向）+ 定位澄清（2026-07-22 广谱网文）。**有决策依据，非凭空扩张。**
> **风险：** PRD 正文仍是六维、未回改；epics FR12 是当前唯一记录 12 字段的规范文档。若未来有人以 PRD 正文为准，会与 epics 冲突。**建议：** 回写 PRD 模块 2 V1 字段定义，或在 PRD 明确"字段 schema 以 epics.md FR12 为准"。属**文档一致性修复项**，不阻塞实现（epics 已足够详尽可开工）。

> **COV-02｜NFR1 红线/盲测/BYOK 覆盖完整，但追溯依据来自 addendum，非 PRD 正文（承接 DRIFT-01）**
> epics 对这三项覆盖**充分**：NFR1（红线三档）、Story 4.1（盲测门禁 launch blocker）、Story 1.7/1.8（BYOK + 托管额度）。但 Step 2 已证 **PRD 正文缺失** §7.1/§7.2 与模块 0 BYOK 能力——故这些 Story 的事实来源实际指向 `addendum` + `architecture` + `decision-log 意图`，而非 PRD 正文。
> **这不是 epics 的缺陷**（epics 正确地基于决策意图开发），**是 PRD 正文的缺陷**。coverage 判定为 ✅，但追溯闭环未合。
> **衍生真实 gap（将在 Step 5 深挖）：** NFR1「不及格/及格线/理想」三档**无可测阈值定义**——addendum B 把判据定义甩给主文档 §七，主文档又无 → Story 4.1 盲测 AC「记录 DeepSeek 是否达及格线以上」中的**"及格线"在全体文档中无定义**，AC 不可客观判定。

> **COV-03｜NFR8 数据不出境/国内云部署 来源为 architecture，PRD 无此约束**
> epics NFR8（DeepSeek + 阿里/智谱 embedding 同区、部署国内云、ICP 备案）来自 `architecture.md`，PRD/addendum 未提此合规约束（addendum F 仅提 AI 强制标识）。属**架构派生需求**，合理且 V1 需要，但 PRD 层无对应能力陈述。**处置：** 记录来源即可，无需修复（架构有权引入部署约束）。

### 反向检查（epics 中 PRD 没有的内容 = 是否超范围）
- **AR1–AR21（21 条架构需求）**：全部来自 `architecture.md`，epics 已明确标注"来自架构决策"。逐条核对均为 **V1 walking skeleton 必需的 enablement**（骨架/认证/多租户/五表/编排/Provider/RAG），**无明显 gold-plating**。唯一可能偏重的 AR18 RAG 三级召回，epics 已克制处理（Story 5.6 放 Epic 5 末尾"回头增强"、V1 用 tsvector 近似 BM25、无 key 退化），可接受。
- **未见 V2/V3 能力泄漏进 V1**：动态选题（EXP-P01/02）、局部重写、导出、自动回流、设定变更影响分析等 V2/V3 项，epics 均正确排除或标注归属。文风相关边界清楚：V1=锚点抽取+注入（FR16/AR15），V2 完整"文风锁定"未纳入。

### Coverage Statistics（覆盖统计）
- **PRD V1 功能能力（Step 2 计数，仅 V1）**：25 条 → **映射到 epics FR1–FR26，覆盖率 100%**（无遗漏）。
- **PRD V1 NFR**：9 条（NFR-1~9）→ epics NFR1–8 + AR 全部有落点，**覆盖率 100%**。
- **偏离项**：3 条（COV-01 字段扩张 / COV-02 追溯来源断裂 / COV-03 架构派生），其中 **0 条阻塞实现**，2 条为文档一致性修复项（COV-01、COV-02 追溯），1 条仅记录来源（COV-03）。
- **超范围（scope creep）**：0 条。架构需求均为 V1 enablement，无 V2/V3 泄漏。
- **结论**：Epic 对 PRD V1 的功能覆盖**完整无遗漏**；主要问题是 **PRD 正文滞后于 epics/决策**（字段 6→12、红线/BYOK 未回写正文），而非 Epic 缺失需求。

---

## UX 对齐校验（Step 4 · UX Alignment）

### UX 文档状态：Found（本次校验补齐）
- `ux-designs/ux-Muse-2026-07-23/DESIGN.md`（视觉 spine · draft）— 从 `styles.css`（3901 行）反向蒸馏，token 照抄、行号可追溯。
- `ux-designs/ux-Muse-2026-07-23/EXPERIENCE.md`（体验 spine · draft）— 从 `app.js`（1905 行）+ `prototype-spec.md` 反向蒸馏。
- **权威性**：两份文件均显式声明「**服从原型、不凌驾**」（与 BMAD-UX 默认 spine-wins 相反），守住 Muse「原型=唯一事实基准」铁律。**本步以原型契约为准绳做三方对齐。**

### A. UX ↔ 原型契约对齐：✅ 一致
逐条比对 `prototype-spec.md`（行为契约权威，51 行）与 EXPERIENCE.md：探索双模式、引导翻页/自述出口/整理中过渡、自由探索只读对话+线索区+给方向不代答、设定卡编辑/反馈升版本/回到探索二次确认/待确认恢复、章节批注点评改进重生定稿、归档折叠组——**逐条吻合，无冲突**。EXPERIENCE.md 忠实镜像原型，且主动登记了 3 处事实纠偏（sessionStorage / 登录 error 预览态 / `--sans`·`--line-soft` 缺陷 token，均与本报告 Step 1 已记事实一致）。

### B. UX ↔ PRD 对齐：✅ 一致
UX 用户旅程（进门→作品库→探索→设定确认→章节创作→归档→循环）与 PRD §3.1 三主线+常驻层完全对应；「幕后阶段规划、无缝进第一章」（EXPERIENCE Key Flows D/E）兑现 PRD NFR-8/CON-1；归档=故事档案统一入口（EXPERIENCE IA）兑现 PRD 已定决策 1。**无 UX 要素缺 PRD 依据，也无 PRD 能力缺 UX 表达**（新增页面除外，见 D）。

### C. UX ↔ 架构对齐：✅ 关键交互均被支撑
| UX 关键交互（EXPERIENCE） | 架构支撑点 | 状态 |
|---|---|---|
| 整理中/生成中/busy 长时等待态 | SSE `POST→taskId→GET /events`（progress/result/error）+ ARQ | ✅ |
| 登录 `expired/invalid/locked`、库 `empty/error` 状态位 | error envelope 附布尔位对接原型分支（arch:331） | ✅ |
| 原型 camelCase 字段（`changedFields` 等）零改动 | snake_case↔camelCase 转换唯一收敛 Pydantic schema（AR4） | ✅ |
| 设定卡 contenteditable 即写回持久化 | story_service + story_bible 表 | ✅ |
| 探索对话/线索刷新可恢复 | exploration_session/message + story_clue 表 | ✅ |

### D. 🔴 核心风险：4 个新增页面打破「页面即契约」前提（UX-ALIGN-01）
> Muse 方法论根基 = **原型即契约、逐页替换 mock**。但以下 4 处 V1 能力**原型完全没有**，即无契约事实基准可继承——这是方法论的**例外区**，EXPERIENCE.md 末尾（line 161-177）已诚实登记：
>
> | 新增项 | 来源 | 契约缺口 | epics 覆盖 |
> |---|---|---|---|
> | 文风样本锚点入口 | UX-DR1 / FR16 | 视觉+交互规格全无 | Story 3.2（AC 从需求出发，非原型） |
> | BYOK 设置页 + 用量入口 | UX-DR2 / FR4 | 整页无原型 | Story 1.7/1.8（同上） |
> | 通读视图 | UX-DR3 / FR26 | 整页无原型 | Story 6.1（同上，已声明「无既有交互契约可继承」） |
> | 阶段交界方向输入 | FR22 | 交互无原型 | Story 4.7（新增项，已标注） |
>
> **影响**：这 4 处的 Story AC **无法引用原型行号做事实锚点**，只能从 FR/NFR 文字推导 → 验收判定比"逐页替换"类 Story 更主观、实现自由度更大、返工风险更高。**这不是 epics 的缺陷**（epics 已对每处显式标注"原型无/须新增"并尽力从需求写 AC），而是**方法论固有的薄弱区**。
> **处置建议**：V1 实现这 4 页**前**，建议先补最小原型/线框（哪怕静态 HTML）纳入 `prototype/app/`，恢复"页面即契约"闭环，再逐页实现。至少 UX-DR1 文风锚点（NFR-1 红线验收前提）与 UX-DR3 通读视图（旅程终点）应优先补契约。属**实现前建议补强项**，非阻塞（epics AC 已可支撑开工，但建议补原型降低返工）。

### E. 次要一致性偏差（低优先级，记录备查）
> **UX-ALIGN-02｜架构文档存储语义未回改**：`architecture.md` 多处（line 64「localStorage 原型」、165「原型 localStorage 已适配」、306/440「localStorage 仅存 UI 态」）仍写 **localStorage**，与已确认纠偏（原型实为 **sessionStorage**）不一致。**影响极小**——V1 迁移后业务数据全走 API、前端存储仅留 UI 态；但 JWT token 存 session 还是 local 会影响"关标签页是否登出"的会话持续性，实现前需明确。**属架构文档措辞回改项，非新 bug**（sessionStorage 事实本报告 Step 1 已记）。

> **UX-ALIGN-03｜原型返回链接文案残留**：EXPERIENCE.md line 159 登记——章节创作页返回链接文案仍写「← 阶段规划」但实际指向 explore（app.js:1229），与 PRD「阶段规划全程幕后、不作为用户页面」矛盾。这是原型残留文案 bug。**epics 未显式覆盖此文案清理**（Story 4.3/1.6 均未提），建议实现章节页时顺带修正为语义正确的返回文案。属**极小的契约清理项**。（另一处"目标页面待设计"占位 epics Story 1.6/FR3 已明确覆盖修复。）

### UX 对齐结论
- **UX 文档存在且与原型/PRD/架构三方高度一致**，无实质性对齐冲突。
- **1 个结构性风险**（UX-ALIGN-01：4 新增页面破契约前提）——不阻塞但强烈建议实现前补原型/线框。
- **2 个次要偏差**（UX-ALIGN-02 架构存储措辞、UX-ALIGN-03 返回文案残留）——低优先级清理项。
- UX 文档 draft 状态、且明确"服从原型"，作为 BMAD 交付物完整性镜像已达标。

---

## Epic/Story 质量校验（Step 5 · Epic Quality Review）

> 姿态：Epic Quality Enforcer——按 `create-epics-and-stories` 最佳实践严格逐项审查。**总体结论前置**：这份 epics.md 质量**显著高于常见水平**——按需建表教科书级、AC 大量引用原型行号（`app.js:xxx`）做事实锚点、Story 依赖显式声明且无环。真正的缺陷高度集中在**一处可测性硬伤**，其余为受控设计权衡与常规补强项。

### A. Epic 用户价值检查：✅ 全部通过（无技术里程碑 epic）
6 个 epic 均按用户旅程站点命名、交付用户可感价值（登录管作品 / 探索存线索 / 出设定圣经 / 写章定稿 / 归档防跑偏 / 通读全本）。**关键正确决策**：技术基座（骨架/LLM/RAG）不单独立"技术层 epic"，而是"随第一个需要它的 epic 走"（基座挂 E1、LLM 底座挂 E2、RAG 挂 E5）——这**正是**最佳实践要求的做法，规避了"Infrastructure Setup"式无价值 epic。

### B. Starter / 建表 / 依赖方向：✅ 三项教科书级
- **Starter**：架构指定"轻量 FastAPI 手工骨架"，Step 5 要求 Epic1 Story1 必须是 setup story——`Story 1.1`（后端工程基座：uv init + 依赖 + docker-compose + 分层 + Alembic）**完全合规**。
- **按需建表**：每 story 只建自己需要的表（1.2 user·1.3 refresh·1.4 project·1.7 byok_key·1.8 usage_ledger·2.2 session·2.4 message·2.6 clue·3.1 story_bible·5.1 三表·5.5 embedding）——**无"Story1 建全表"违规**。story_bible 在 3.1 一次建全 12 字段是"单表 schema 一次建全"，非"一次建所有表"，合理。
- **Epic 内 Story 依赖**：6 条依赖链全部向后、无环、无前向引用（1.1→1.2→1.3→{1.4,1.7}… 等）。✅

### C. 🟠 Major｜唯一实质硬伤：NFR1「及格线」无可测阈值 → Story 4.1 AC 不可判定（QUAL-01）
> **承接 COV-02。** `Story 4.1`（盲测门禁 · launch blocker）AC：「记录 DeepSeek 是否达到**及格线**以上的明确结论」；`NFR1` 定义三档判据「不及格 / 及格线 / 理想」但**无任一档的可测定义**（多少去 AI 味词命中率？何种风格贴合度评分？几人盲评多数通过？）。addendum B 把判据定义甩给主 PRD §七，主 PRD §七又不存在（DRIFT-01）。
> **后果**：全项目**头号 launch blocker 的验收标准不可客观判定**——盲测"通过与否"取决于评审人主观，Story 4.1 的 Then 分支（通过→解锁 4.4 / 不通过→阻断）失去客观触发条件。这是本次审查**最需在实现前修复**的一项。
> **修复建议**：实现 Story 4.1 前，创始人须把 NFR1 三档落成可操作判据（建议：①风格贴合——N 人盲评"像锚定样本"的比例阈值；②去 AI 味——polish-guide 词表命中率上限 + 句式规则通过项数；③明确"及格线"= 哪几条同时满足）。写入 PRD §7.1 或 epics NFR1。**这是 Step 6 就绪结论的关键前置。**

### D. 🟡 Minor｜跨 Epic 依赖：3 处受控，设计良性但须追踪（QUAL-02）
> 本项目架构是"回头增强"模式，天然产生跨 epic 衔接。逐条审查后判定**均不构成"Epic N 依赖 Epic N+1 才能工作"的硬违规**，因为每处都用 V1 降级方案保证前序 epic 可独立跑通：

| 衔接 | 类型 | 是否违规 | 依据 |
|---|---|---|---|
| `Story 1.8` 额度护栏 ← Epic2 Provider 埋点 | Epic1 依赖 Epic2 | ⚠️ 受控 | epics 已降级：1.8 只做「建表+校验框架+展示」，用量埋点显式划给 Epic2（AR14）。护栏框架可先立，真实计量后补——**1.8 不因缺 Epic2 而无法交付**，但"护栏真正生效"要等 Epic2。**唯一方向偏后的依赖**，须追踪。 |
| `Story 4.7` 定稿 → 触发 Epic5 chapter-commit | Epic4 引用 Epic5 | ✅ 非违规 | Epic4 独立性由 `Story 4.4` V1 降级保证（写前上下文用「全量设定+最近定稿正文」直接注入，不靠章节卡片）。定稿持久化本身完整，卡片生成是 Epic5 增强。 |
| `Story 5.6` RAG **回改** `Story 4.4` 注入点 | Epic5 增强 Epic4 | ✅ 非违规 | 方向正确（E5 依赖 E4）。Story 4.4 AC 已显式写「V1 先用全量设定+最近定稿章节直接注入、不阻塞 RAG」——Epic4 不需 Epic5 即可跑，RAG 是纯增量。 |

> **结论**：跨 epic 依赖设计**合理且已用降级方案兜底**，不阻塞。唯 `Story 1.8` 是方向偏后的受控依赖，建议实现时确认"护栏框架先行、Epic2 补埋点"的衔接不留空窗（否则 Epic1 交付时额度护栏是空壳）。

### E. 🟡 Minor｜4 个新增页面 Story 的 AC 无原型锚点（QUAL-03，承接 UX-ALIGN-01）
从 Story 质量视角复述 Step 4 发现：`Story 1.7/1.8`（BYOK/用量）、`Story 3.2`（文风锚点）、`Story 6.1`（通读）、`Story 4.7` 阶段交界输入——这 5 处 AC 无法引用原型行号，只能从 FR/NFR 文字推导。epics 已诚实标注"原型无/须新增"并尽力写 AC，但相较"逐页替换"类 Story（AC 精确到 app.js 行号），**这几个 Story 的 AC 具体度与可测性偏低、实现自由度偏大**。建议实现前补最小线框（见 UX-ALIGN-01 处置）。

### F. 🟡 Minor｜CI/CD story 缺失（QUAL-04）
Step 5 greenfield 检查项要求"CI/CD pipeline setup early"。epics 全文无 CI/CD story（Story 1.1 仅含本地 docker-compose + ruff/mypy，无流水线）。对单人 MVP 这**常被有意省略**，但严格按标准应记为 gap。**建议**：若 V1 有多环境/协作/自动部署需要，补一个 CI story 挂 Epic 1；纯单人本地开发可显式声明"V1 不做 CI/CD"以示非遗漏。

### G. 🟡 Minor｜原型残留文案未纳入清理 Story（QUAL-05，承接 UX-ALIGN-03）
章节页返回链接"← 阶段规划"文案 bug（app.js:1229，实际指向 explore）与 PRD"阶段规划全程幕后"矛盾，`Story 4.3` 未显式覆盖此清理。属极小项，建议实现章节页时顺带修正。

### H. 质量合规清单（逐 epic）
| 检查项 | E1 | E2 | E3 | E4 | E5 | E6 |
|---|---|---|---|---|---|---|
| 交付用户价值 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 可独立工作（前序 epic 足够） | ✅ | ✅ | ✅ | ✅* | ✅* | ✅ |
| Story 尺寸适中（单 dev 可完成） | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 无破坏独立性的前向依赖 | ⚠️1.8 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 按需建表 | ✅ | ✅ | ✅ | n/a | ✅ | n/a |
| AC 清晰可测 | ✅ | ✅ | ✅ | 🟠4.1 | ✅ | 🟡6.1 |
| FR 可追溯 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

（*E4/E5 独立性靠 V1 降级方案保证，见 D 表。）

### Step 5 质量结论
- **🔴 Critical 违规：0**（无技术里程碑 epic、无破坏性前向依赖、无 epic 级 story）。
- **🟠 Major：1**（QUAL-01 NFR1 及格线不可测——**launch blocker AC 不可判定，实现前必修**）。
- **🟡 Minor：4**（QUAL-02 Story1.8 受控后向依赖须追踪 / QUAL-03 新增页 AC 无锚点 / QUAL-04 CI/CD 缺失 / QUAL-05 返回文案残留）。
- **整体判定**：Epic/Story 结构质量**优秀**，可支撑实现开工；唯一必须在动工前解决的是 **QUAL-01（把 NFR1 三档判据落成可测阈值）**，否则头号 launch blocker（盲测门禁）验收无客观标准。

---

## 总结与建议（Step 6 · Final Assessment）

### 总体就绪状态：**NEEDS WORK（就绪度高，但有关键前置未闭合）**

Muse V1 的规划质量**整体优秀**：功能覆盖 100% 无遗漏、无 scope creep、Epic 结构无 Critical 违规、架构自洽且版本经联网核实、AC 大量以原型行号为事实锚点。**它没有"缺东西"的问题，只有"文档没对齐上"和"一条 launch blocker 验收标准还没定"的问题。** 因此不是 NOT READY，但也不能标 READY——有 1 项关键前置必须在动工前闭合。

**分层结论：**
- **可立即开工的部分**：Epic 1 全部（骨架/认证/多租户/作品 CRUD）+ Epic 2 底座（LLMProvider/ARQ/探索）+ Epic 3 存储与文风锚点抽取 + Epic 5 建表——这些不依赖盲测门禁，架构已就绪（架构文档亦持此结论：READY WITH MINOR GAPS，骨架至编排底座可先行）。
- **被 launch blocker 卡住的部分**：Epic 4 Story 4.4 正文生成接入及其后——须待盲测（Story 4.1）通过，而盲测通过与否**目前无客观判据**（QUAL-01）。

### 必须在动工前解决的关键问题（按优先级）

**🔴 P0｜QUAL-01：NFR1「及格线」落成可测判据**（launch blocker 的 launch blocker）
全项目头号生死假设（DeepSeek 能否过文字红线）由盲测 Story 4.1 验证，但"及格线"在全体文档中无可操作定义 → 盲测无法客观判定通过。**必须**在实现 Epic 4 前，由创始人把 NFR1 三档（不及格/及格线/理想）落成可测阈值（风格贴合盲评比例 + 去 AI 味词表命中率 + 明确"及格线=哪几条同时满足"），写入 PRD §7.1 或 epics NFR1。

**🔴 P0｜DRIFT-01：PRD 正文补写缺失章节**（追溯链断裂）
decision-log 声称已灌入但主 PRD 正文实缺：§7.1 行为红线三档判据、§7.2 盲测前置、模块 0 的 BYOK/托管额度能力。当前这些需求的事实源只能退回 addendum（技术附录）。**必须**回写 PRD 正文——否则 QUAL-01 的判据"无处安放"，且未来以 PRD 正文为准的人会与 epics/决策冲突。P0 与 QUAL-01 是同一处伤口的两面（判据要先定义、再写进正文）。

**🟠 P1｜COV-01：PRD 设定字段 6→12 回写**（文档一致性）
epics FR12 用 12 字段替换 PRD 正文的六维，有决策依据（记忆 + 广谱网文定位）但 PRD 正文未同步。建议回写 PRD 模块 2 字段定义，或在 PRD 声明"字段 schema 以 epics.md FR12 为准"。不阻塞开工（epics 已是唯一详尽记录）。

**🟠 P1｜UX-ALIGN-01 / QUAL-03：4 个新增页面补最小原型契约**（降低返工）
文风锚点入口、BYOK/用量页、通读视图、阶段交界方向输入——原型无、打破"页面即契约"前提，Story AC 无行号锚点。建议实现前补最小线框纳入 `prototype/app/`，优先补 UX-DR1 文风锚点（红线验收前提）与通读视图。不阻塞但强烈建议。

### 建议的后续步骤（可执行顺序）
1. **【创始人决策】定义 NFR1 三档可测判据** → 写入 PRD §7.1（同时解决 QUAL-01 + DRIFT-01 红线部分）。这是解锁 Epic 4 的唯一钥匙。
2. **【文档回写】PRD 正文补齐** §7.1/§7.2 + 模块 0 BYOK/额度能力（DRIFT-01 剩余），并同步设定字段 6→12（COV-01）、"已定决策"章节号顺延为§八。
3. **【可并行开工】** 启动 Epic 1（Story 1.1 骨架初始化）——不被任何 P0 阻塞，架构已就绪。
4. **【补原型】** 为 4 个新增页面补最小线框（UX-ALIGN-01），至少在各自 Epic 动工前完成。
5. **【实现前确认】** Story 1.8 护栏与 Epic2 埋点的衔接不留空窗（QUAL-02）；明确 JWT token 存 session/local 语义（UX-ALIGN-02）；补或显式豁免 CI/CD（QUAL-04）。
6. **【门禁】** Epic 4 动工时先跑盲测 Story 4.1，用步骤 1 定义的判据判定；通过才接入 Story 4.4 正文生成。

### 最终说明
本次评估在 **5 个类别**（PRD 分析 / Epic 覆盖 / UX 对齐 / Epic 质量 / 跨文档一致性）共识别 **13 项发现**：
- **Critical 违规（Epic 结构层）：0**
- **P0 关键前置：2**（QUAL-01 判据不可测 + DRIFT-01 正文缺失，实为同一伤口）
- **P1 建议补强：2**（COV-01 字段回写 + UX-ALIGN-01 新增页原型）
- **其余 Minor/记录项：9**（COV-02/03、UX-ALIGN-02/03、QUAL-02/04/05 等）

**核心洞察**：Muse 的规划工程本身很扎实，风险不在"planning 做得好不好"，而在两个源头——① **PRD 正文滞后于已拍板的决策**（决策在 decision-log/addendum/记忆里，正文没跟上），② **全项目押注的文字质量红线至今是"赌"而非"知"**，且其验收判据尚未可测。前者是文档纪律问题、可快速修复；后者是产品生死题、须创始人正式定义判据 + 盲测验证。**建议解决 2 项 P0 后即可放心推进实现**，P1/Minor 可在对应 Epic 动工前分批处理。

---

**评估人**：Claude（BMAD Implementation Readiness · PM 视角）
**完成日期**：2026-07-23
**校验输入**：PRD 三件套 + architecture.md + epics.md（1210 行）+ UX DESIGN/EXPERIENCE + 原型契约 spec + 原型代码事实
**方法论铁律**：原型（`prototype/app/` + `prototype-spec.md`）= UX/契约唯一事实基准
