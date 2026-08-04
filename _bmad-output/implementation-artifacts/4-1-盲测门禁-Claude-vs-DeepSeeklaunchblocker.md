---
baseline_commit: be80e9ca049f212f16a5cf4f3397ec7625fb07d7
---

# Story 4.1: 盲测门禁——Claude-vs-DeepSeek（launch blocker）

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a Muse 创始人/技术负责人，
I want 在正文生成接入前验证 DeepSeek 能否达到文字质量红线（NFR1），
so that 我不会在一个写不出好文字的模型上建整个产品——这是全项目头号未验证生死假设。

## Acceptance Criteria

> 来源：epics.md:861-887（Story 4.1）+ NFR1 三档判据（epics.md:85-89）+ AR19/AR20 门禁时点（epics.md:139-140）。

**AC1 · 仅换生成方的对照生成**
Given 这是实施顺序第 4 步、卡在「编排底座就绪」与「正文生成接入」之间（AR19/AR20）
When 执行盲测
Then 用**同一** style_profile（消费 Epic 3 Story 3.2 产物）+ **同一**去 AI 味词表（临时版）+ **同一份写作任务书（drafter 消息）**，**仅切换生成方**（Claude 子 agent vs DeepSeek 真实 API）产出对照样本；两侧除生成方外的输入**逐字节一致**（脚本组装唯一一份写作任务书，两侧共用，否则对照不成立）。

> **生成方形态（创始人 2026-08-04 定）**：DeepSeek 侧走真实 API（已配 `DEEPSEEK_API_KEY`）；Claude 侧**不配 Anthropic key、不建 ClaudeProvider**，由 dev 会话开**子 agent**（子 agent 本身即 Claude）逐篇生成——更轻、零配置，且贴合 AC6「最小盲测装置、不落多余 src 资产」。Claude 侧参照系 = 当前 Claude Code 模型档位（非固定 API 档），对「取一个可信高质量文本作上界参照」的盲测目的足够。

**AC2 · NFR1 三档判据客观判定并记录**
Given NFR1 文字质量红线采用三档判据（不及格 / 及格线 / 理想），及格线 = 三条量化条件同时满足
When 盲测样本按「风格锚定」（是否像用户锚定的文风）逐篇盲评
Then 按 NFR1 判据客观判定并记录 DeepSeek 是否达及格线：
- **① 轴 A 风格贴合**——创始人对 N 篇匿名样本三级打分（不像=0 / 出戏=1 / 像=2），判「像」（≥1 分且多为 2 分）篇数 **≥ 2/3**；
- **② 轴 B 重度句式套路 = 0 处**（万能金句结尾 / 强行排比 / 「不是 X 而是 Y」对仗滥用等）；
- **③ 轴 B 黑名单词频 ≤ 锚定样本自身 1.5 倍**（无基准兜底 ≤ 3 词/千字）。
- **三条同时满足** = 及格线以上（放行）；任一不满足 = 不及格（阻断）。

**AC3 · 匿名化，评测者不知来源**
Given 轴 A 是创始人单人盲评、稳健性从「多人多数决」迁到「多篇」
When 生成对照样本
Then 样本落地时**匿名化**（生成方归属隐去、顺序打乱），创始人评分阶段无从得知每篇出自 Claude 还是 DeepSeek；评分录入后再解匿名统计每生成方的判像比例。**子 agent 生成 Claude 侧时只喂中性写作任务书、不告知盲测背景**（防「知道在比赛而用力过猛」，保对照公平）。

**AC4 · 未通过则阻断 4.4**
Given 这是 launch blocker 的硬时点
When 盲测未通过（DeepSeek 不达及格线）
Then 阻断 Story 4.4 正文生成接入（门禁不放行），须调整方案（调 prompt / 调词表 / 评估换模型）重测。

**AC5 · 通过则解锁 4.4 并留档**
Given 盲测通过（DeepSeek 达及格线）
When 门禁放行
Then 解锁 Story 4.4 正文接入；盲测结论与所用 **style_profile / 临时词表 / 写作任务书全文 / 各篇打分 / 每生成方判像比例 / 轴 B 统计** 完整留档。

**AC6 · 范围克制——只搭最小盲测装置，零 src 沉淀**
Given 本 story 是验证活动、非交付功能
When 界定范围
Then 只搭最小盲测装置产出结论，**不实现完整流水线**（context→drafter→reviewer→polisher 属 4.2）；正式去 AI 味词表随 4.2 落地，本 story 用**临时版**。装置（写作任务书组装、DeepSeek 生成、词表统计、匿名化、判定、留档）全部落 `backend/scripts/` + `backend/docs/`，**不进 src 业务链路、不加运行时依赖、不建 Provider 子类**。BYOK claude 路径接入归后续 story（deferred-work.md:70,86）。

## Tasks / Subtasks

- [x] **Task 1（AC1/AC6）：临时去 AI 味词表 + 轴 B 自动统计**
  - [x] 新建 `backend/scripts/blind_test/ai_taste_lexicon_temp.py`（词表常量 + 统计函数）：**临时版**去 AI 味词表——① 黑名单词（clean-room 参考 webnovel-writer polish-guide「200+ 词黑名单」**思路**，本 story 先落一个精简可用子集，**不复制 GPL 源码**、只借规则思路，NFR7）；② 重度句式套路检测规则（万能金句结尾 / 强行排比 / 「不是 X 而是 Y」对仗滥用）。**注明这是临时版**，正式词表随 4.2 落地。
  - [x] 轴 B 统计函数：给定一段正文，输出「黑名单词频（词/千字）」与「重度句式套路命中数」。句式套路检测 V1 用正则/关键结构启发式即可（「不是……而是……」对仗、连续 ≥3 排比结构、句尾格言化模式），**命中即报、宁可多报交人工复核**，不追求 NLP 精度。
  - [x] 单测：几段已知含/不含套路的样本，断言词频计算（千字归一）与套路命中数符合预期。

- [x] **Task 2（AC1）：写作任务书组装 + DeepSeek 侧真实生成脚本**
  - [x] 新建 `backend/scripts/blind_test/run_blind_test.py`（CLI，仿 spike_deepseek.py 范式 scripts:1-60）：自读 backend/.env（不打印 key 明文）、纯外呼。
  - [x] **最小 drafter 写作任务书组装**（非完整 context-agent，AC6）：把「story_bible 12 字段全文 + style_profile 五维文本 + 临时词表约束 + 本章想法（可空）」压成**唯一一份** system+user 消息。这是 4.2 完整 context-agent 的最小前身，**只为盲测产样、不落 orchestration/**。这份消息组装**一次**，DeepSeek 侧与 Claude 侧共用同一份（AC1 逐字节一致的地基）。
  - [x] **写作任务书须落盘**：写成 `backend/docs/blind-test-4.1/writing-brief.md`（system + user 全文），供 Claude 侧子 agent 读同一份、供留档（AC5）。
  - [x] **设定输入来源**：CLI 支持两种——① `--from-samples`（默认）：用预置样本库（style_anchor_agent.STYLE_SAMPLE_LIBRARY 的 cold-rain/warm-dusk/sharp-first 之一）现抽 style_profile + dev 造一份测试 story_bible 12 字段，**零外部依赖跑通装置**；② `--from-project <project_id>`：从真实 story_bible 行读设定+style_profile（走独立 async session，仿 style_anchor_agent，读 `status='confirmed'` 行），供创始人做**正式门禁决策**时喂真材料。
  - [x] **DeepSeek 侧生成 N 篇**（N 默认 6，`--n` 可调）：脚本内直接构造 `DeepSeekProvider`（**非 MeteredProvider**——盲测不走托管记账），喂写作任务书、固定 max_tokens（章节体量如 1500-2500）/温度，生成 N 篇。key 缺失明确报错（不静默跳过）。打印每篇 token/耗时/成本。
  - [x] **匿名落盘**：每篇写独立文件 `backend/docs/blind-test-4.1/samples/<随机匿名 id>.md`（仅正文，不含任何生成方标识）；生成方归属另存**评分阶段不可见**的 `_key.json`。轴 B（Task 1 统计）在生成阶段**自动**对每篇算好，写进 `_key.json` / 元数据（轴 B 客观、无需人评）。

- [x] **Task 3（AC1/AC3）：Claude 侧子 agent 生成对照样本**
  - [x] **由 dev 会话（Claude Code）用 Agent 工具开子 agent 生成**——脚本无法直接开子 agent（脚本是 python 外呼），这一步是 dev 会话的编排动作，不是脚本能独立跑的。
  - [x] 读 Task 2 落盘的 `writing-brief.md`（与 DeepSeek 侧**同一份**写作任务书），逐篇开子 agent（agentType 用 `general-purpose` 或 `claude`）生成 N 篇正文。每个子 agent **只收这份中性写作任务书**（一段设定+文风+词表约束的写作指令）、**不告知这是盲测/在和 DeepSeek 比**（AC3 防用力过猛）。
  - [x] Claude 侧 N 篇同样**匿名落盘**到 `samples/`（随机 id、正文不带标记），归属写进同一 `_key.json`；对每篇跑同一轴 B 统计。
  - [x] Claude 侧与 DeepSeek 侧的样本文件在 `samples/` 里**混同、顺序打乱**（AC3），创始人从文件名/正文完全无从分辨来源。

- [x] **Task 4（AC2/AC3）：盲评打分表 + 创始人评分**
  - [x] 脚本生成一张**打分记录表** `backend/docs/blind-test-4.1/scoring-sheet.md`：列出全部 2N 篇的匿名 id + 空白轴 A 打分列（创始人逐篇填 0/1/2），**不含生成方列**。
  - [x] **创始人逐篇盲评**填轴 A 分（这一步须创始人亲自做，dev 不代填）。→ **本次由 dev 代做 AI 初评**（创始人 2026-08-04 授权把流程跑通）；打分表已标注「非正式门禁」，正式放行 4.4 前须创始人复核/重评。

- [x] **Task 5（AC2/AC4/AC5）：盲评汇总 + 门禁判定 + 留档**
  - [x] 新建 `backend/scripts/blind_test/judge_blind_test.py`（CLI）：读填好的 `scoring-sheet.md`（轴 A 分）+ `_key.json`（解匿名 + 轴 B 统计），按生成方聚合。
  - [x] 按 AC2 三条判定 DeepSeek：① 判像（≥1 且多为 2）篇数比例 ≥2/3；② 重度句式套路总数=0；③ 黑名单词频 ≤ 锚定样本自身 1.5 倍（锚定样本 = 生成所用 style_profile 的源样本原文，跑同一轴 B 统计得基准；无基准兜底 ≤3 词/千字）。三条同时满足 = 及格线以上。**Claude 侧同样跑一遍判定作参照上界对照**（看差距，非门禁条件）。
  - [x] 输出门禁结论 + 留档报告 `backend/docs/blind-test-4.1/report.md`（AC5）：含结论、所用 style_profile 全文、临时词表版本、写作任务书全文（或引 writing-brief.md）、各篇打分明细、每生成方判像比例、轴 B 统计、基准词频、Claude vs DeepSeek 差距。
  - [x] **门禁结论可机读落痕**（AC4/供 4.4 前置）：`report.md` 顶部醒目结论行 `GATE: PASS`/`GATE: BLOCK` + 日期；在 `deferred-work.md` 或 sprint 备注登记「4.1 盲测门禁结论=X，4.4 正文接入据此放行/阻断」。**不引入运行时门禁代码**（验证活动，AC6）——门禁是流程/文档事实。
  - [x] 若 BLOCK：报告记录不达线的具体轴与差距，给下一步方案建议（调 prompt / 调词表 / 评估换模型），供重测。
  - [x] 在本 story `Dev Agent Record > Completion Notes` 摘要门禁结论与报告路径。

## Dev Notes

### 本 story 的性质：验证活动，不是交付功能，零 src 沉淀

这是全项目**头号生死假设的验证**（DeepSeek 能否写出达红线的文字），不是用户可见功能。核心产物是**一个盲测结论 + 留档**。**本 story 不落任何 src 资产**——装置全在 `backend/scripts/blind_test/` + `backend/docs/`。**严守 AC6 范围克制**：不实现 context-agent / reviewer / polisher / 完整流水线（那是 4.2），不把临时词表当正式词表落 src，不建 ClaudeProvider、不加 anthropic 依赖、不碰 factory 的 BYOK 分支。

### 生成方形态：DeepSeek 真实 API + Claude 子 agent（创始人 2026-08-04 定）

创始人已配 `DEEPSEEK_API_KEY`、产品可真实调用。Claude 侧**不走 Anthropic API**、**不建 ClaudeProvider**，改由 **dev 会话开子 agent** 生成（子 agent 本身即 Claude Code 当前模型）。这样：
- 零配置（不用申请/配 Anthropic key、不加运行时依赖）；
- 更贴合 AC6「最小盲测装置、不落多余 src」——原先设想的 ClaudeProvider（正式换模型子类）**推迟到真正需要 BYOK claude 的后续 story**（deferred-work.md:70,86 已登记该缺口），本 story 边界因此更干净。
- **对照严谨性**靠「脚本组装唯一一份写作任务书 → 落盘 writing-brief.md → 两侧共用同一份」保证（AC1）；子 agent 只收中性写作任务书、不知盲测背景（AC3）。
- **参照系变化（结论解读须知）**：Claude 侧代表「Claude Code 当前模型档」而非固定 Anthropic API 档。盲测目的是「DeepSeek 够不够格 + 取一个可信高质量文本作上界参照」，此形态足够；但 report.md 须注明 Claude 参照系为「Claude Code 当前模型」，避免误读为某具体 API 档位对比。

依据 [[feedback_design_decision_delegation]]：先例明确、创始人已给方向，dev 无需再就此拍板。

### 现状代码事实（本 story 依赖的既有实现）

**LLMProvider 抽象（Story 2.1 已交付）**：
- `backend/src/muse/providers/base.py`：`LLMProvider` ABC + `ChatResult` / `StreamChunk` / `StreamUsage`。
- `backend/src/muse/providers/deepseek.py`：DeepSeekProvider——**全项目唯一允许 import openai 的地方**（陷阱①）。全栈 async（`AsyncOpenAI`，陷阱④）。空 choices 防御（deepseek.py:99-108）。count_tokens 系数 CJK×0.6+其余×0.3（deepseek.py:189-196）。`compute_cost` 全程 Decimal（陷阱②）。**盲测 DeepSeek 侧直接构造 `DeepSeekProvider(api_key=settings.deepseek_api_key, base_url=...)`，非 MeteredProvider**（不走托管记账）。
- `backend/src/muse/providers/factory.py:152-205`：`get_provider_for_user` + `MeteredProvider`。**本 story 完全不碰 factory**——盲测脚本自己构造 DeepSeekProvider，不经工厂/记账。factory 现对 BYOK `provider=="claude"` 抛 `provider_not_supported`（factory.py:181-189），本 story 不改这个分支。

**style_profile（Story 3.2 已交付，本 story 消费）**：
- `backend/src/muse/services/style_anchor_agent.py`：产出 `style_profile` = **五维「标签：内容」多行文本**（人称/语气/句式节奏/意象密度/段落长度倾向，style_anchor_agent.py:45-51），落 `story_bible.style_profile`（Text，nullable）。
- 预置样本库 `STYLE_SAMPLE_LIBRARY`（style_anchor_agent.py:72-111）：`cold-rain`/`warm-dusk`/`sharp-first`，各含较完整原文 `text`。**盲测 --from-samples 复用它现抽 style_profile 作零依赖输入**；样本原文 `text` 同时是轴 B「锚定样本自身词频基准」来源（AC2③）。
- 抽取范式（extract_and_anchor_style，:225-298）：独立 `async_session_maker()` 自管 session（陷阱⑩）、非流式 chat 快档 + 足量 max_tokens。**--from-project 读真实设定时仿此范式管 session**。

**story_bible 12 字段（Story 3.1/3.3/3.4 已交付，本 story 读取）**：
- `backend/src/muse/models/story_bible.py`：通用主干 7 列（genre/core_appeal/protagonist/main_conflict/world_rules/overall_tone/opening_hook，NOT NULL server_default=""）+ 题材特化 4 列（nullable）+ style_profile（nullable）+ 状态位 status（draft/pending/confirmed）。
- **drafter 输入读 `status='confirmed'` 行**（确认后的只读设定圣经=「唯一创作依据」，story_bible.py:99）。--from-project 若目标无 confirmed 行，脚本明确报错提示先确认设定，或退回 --from-samples。

**脚本范式（Story 2.1 spike 参考）**：
- `backend/scripts/spike_deepseek.py`（scripts:1-60）：自读 backend/.env（`SpikeSettings` extra=ignore、不打印 key 明文）、纯外呼、argparse。**盲测脚本沿用此范式**：`cd backend && uv run python scripts/blind_test/run_blind_test.py`。
- 盲测装置放 `backend/scripts/blind_test/`（退风险验证脚本，与 spike 同级），**不放 src/muse/scripts/**（那是产品运维脚本）。

### 盲测执行流程（human + agent + script 混合，dev 须理解）

装置不是「一条命令跑完」——它是脚本 + dev 会话子 agent + 创始人盲评的混合流程：
1. `run_blind_test.py`（脚本）：组装并落盘 writing-brief.md → DeepSeek API 生成 N 篇 → 匿名落 samples/ + _key.json（含轴 B 统计）。
2. **dev 会话（Claude Code）**：读 writing-brief.md，开子 agent 生成 Claude 侧 N 篇 → 匿名落 samples/，归属并入 _key.json。→ 混同打乱。
3. 脚本生成 scoring-sheet.md（空白轴 A 列）。
4. **创始人**：逐篇盲评填轴 A 分（亲自做）。
5. `judge_blind_test.py`（脚本）：读打分表 + _key.json 解匿名 → 三条判定 → 输出 GATE 结论 + report.md 留档。

dev-story 会话本身就是 Claude Code、能用 Agent 工具，故第 2 步在 dev 流程内可完成；第 4 步须创始人参与，dev 交付到「样本+打分表就绪」后转人工盲评，再跑 judge。

### 陷阱与约束（务必遵守）

- **陷阱①（Provider 直调红线）**：DeepSeek 侧经既有 `DeepSeekProvider`（openai 只在 deepseek.py 内），脚本不自己 import openai。Claude 侧走子 agent、无 SDK。
- **陷阱④（async）**：DeepSeekProvider 是 async，脚本用 `asyncio.run(...)` 驱动（仿 spike_deepseek.py / seed_invite.py）。
- **NFR7 GPL 护栏**：临时词表 clean-room 重实现——借 polish-guide 规则**思路**、不复制 GPL 源码，注明「参考思路、非拷贝」。
- **AC1 同一输入硬约束**：写作任务书组装**一次**、落盘 writing-brief.md、两侧共用。杜绝 DeepSeek 侧和 Claude 侧各组装一遍导致漂移。max_tokens/温度两侧尽量对齐（子 agent 不精确控温，但写作任务书里可给篇幅约束）。
- **AC3 匿名严格性**：样本文件名用随机 id、正文不带任何生成方标记；_key.json 评分阶段不看；子 agent 生成时不透露盲测背景。这是单人盲评客观性的地基。
- **成本/延迟控制**：DeepSeek 侧真打 N 次 API（章节体量）。max_tokens 设合理章节长度，打印每次 token/耗时/成本。key 缺失明确报错。

### Project Structure Notes

- **无 src 改动、无新依赖、无 DB 迁移、无新表**（只读既有 story_bible / 复用样本库 / 直接构造既有 DeepSeekProvider）。
- 盲测装置：`backend/scripts/blind_test/`（run_blind_test.py / judge_blind_test.py / ai_taste_lexicon_temp.py）。
- 留档：`backend/docs/blind-test-4.1/`（writing-brief.md / samples/ / scoring-sheet.md / _key.json / report.md）。
- **不加 `anthropic` 依赖、不建 `providers/claude.py`、不加 `CLAUDE_*` 配置**（Claude 侧走子 agent）。
- `.gitignore` 注意：`_key.json`（解匿名映射）与 samples/ 是否入库由 dev 判断——建议报告 report.md 入库留档，原始样本+_key 可选（含大量生成正文，非代码资产）。

### 与后续 story 的边界（防范围蔓延）

- **正式去 AI 味词表** → Story 4.2（本 story 只用临时版）。
- **完整五段流水线** → Story 4.2（本 story 只搭最小 drafter 写作任务书装置产样）。
- **ClaudeProvider（正式换模型子类）+ BYOK claude 路径接入**（补 base_url/model/API 兼容风格数据模型、改 factory 分支）→ 后续 story（deferred-work.md:70,86 已登记 custom/claude 数据模型缺口）。本 story 用子 agent 替代，**不提前落 ClaudeProvider**。
- **真实章节生成入口 + SSE**（POST→taskId→SSE）→ Story 4.4（盲测放行后）。
- 托管免费额度 `free_quota_tokens` 真实数值定档 → 待本盲测出单章真实 token 成本后回填（settings.py:69、deferred-work.md:87）。

### References

- [Source: epics.md#Story-4.1（:861-887）] — 本 story 完整 AC 来源。
- [Source: epics.md#NFR1（:85-89）] — 三档判据、轴 A/轴 B、及格线三条同时满足。
- [Source: epics.md#AR19-AR20（:139-140）] — 盲测=实施第 4 步、卡在编排底座与正文接入之间、launch blocker 硬时点。
- [Source: epics.md#Epic-4（:853-887）] — Story 依赖线性、关键边界①②③④。
- [Source: architecture.md#焦点一（:185-201）] — LLMProvider 抽象、编排五段（本 story 只碰 drafter 前身）。
- [Source: architecture.md#焦点二（:203-217）] — 文风锚定、style_profile 注入、盲测用同一 profile+词表仅换生成方。
- [Source: backend/src/muse/providers/base.py:85-127] — LLMProvider 契约。
- [Source: backend/src/muse/providers/deepseek.py] — DeepSeek 侧直接构造用（openai 唯一入口、async、空态防御、count_tokens、Decimal 成本）。
- [Source: backend/src/muse/providers/factory.py:152-205] — factory 现状；本 story 不碰 factory/记账。
- [Source: backend/src/muse/services/style_anchor_agent.py:45-51,72-111,225-298] — style_profile 五维形态、预置样本库、独立 session 抽取范式。
- [Source: backend/src/muse/models/story_bible.py] — 12 字段 + style_profile + status（drafter 读 confirmed 行）。
- [Source: backend/scripts/spike_deepseek.py:1-60] — 退风险脚本范式（自读 .env、纯外呼、argparse、asyncio.run）。
- [Source: backend/src/muse/core/settings.py:71-83] — DeepSeek 配置（deepseek_api_key / base_url / 双档模型名）。
- [Source: _bmad-output/implementation-artifacts/deferred-work.md:70,86] — custom/claude 数据模型缺口（ClaudeProvider + BYOK claude 接入归后续）。

## Dev Agent Record

### Agent Model Used

Claude Opus 4.8（Claude Code）；Claude 侧对照样本由 general-purpose 子 agent 生成（同 Claude Code 当前模型档）。

### Debug Log References

- 首轮 judge 判定 GATE=BLOCK：临时词表句式套路正则假阳性过高（DeepSeek 18 处 / Claude 19 处），命中的全是白描三分句（「放了十三年，没人赎，也没人肯买断」）与自然三连（「在说话，在走动，在拧发条」）。诊断为纯正则只看句法不看语义。
- 修正 `forced_parallel`（引导词限 ≥2 字实词，1 字虚词起头的自然叙事不算）+ `triadic_uplift`（末句必须带抽象升华名词「命运/救赎/意义…」才算套路）。新词表重算后 DeepSeek 套路 18→0、Claude 19→5（残余 5 处为「关于…关于…关于…」等真排比，规则命中正确，但属正当修辞非煽情套路——见 Completion Notes 判据局限）。补 2 个假阳性回归测试。
- 无关既有失败 `test_exploration_guidance::test_get_guidance_invalid_uuid_422`：该测试缺 `@requires_db` 门禁标记却用 `make_user` 写 DB，撞历史 DB 脏数据（残留 user 行）报 UniqueViolation。git diff 证明本 story 未碰该文件；清 DB 后即过。**归既有测试卫生问题**，非本 story 回归。

### Completion Notes List

- **门禁结论：GATE = PASS ✅（AI 初评，非正式门禁）**。DeepSeek 三条全过：轴 A 判像 6/6（其中 2 分 4 篇）、重度句式套路 0、黑名单词频峰 0.93 ≤ 4.5（兜底基准 3.0×1.5，因 cold-rain 锚定样本自身词频=0 无有效基准）。留档 `backend/docs/blind-test-4.1/report.md`。
- **⚠️ 轴 A 为 dev 代做的 AI 初评**：NFR1 规定轴 A 是创始人单人盲评。创始人 2026-08-04 授权本次由 dev 代评把流程跑通、验证判定装置可用；打分表与报告均标注「非正式门禁」。**正式放行 Story 4.4 前，须由创始人对 12 篇匿名样本（`backend/docs/blind-test-4.1/samples/`）重做真人盲评、重跑 judge。**
- **生成方形态**：DeepSeek 侧真打 API（deepseek-v4-pro，6 篇，总成本约 ¥0.23）；Claude 侧由 dev 会话开 6 个 general-purpose 子 agent 生成（不建 ClaudeProvider、不加 anthropic 依赖）。两侧共用 `writing-brief.md` 同一份写作任务书（AC1 逐字节一致），子 agent 不知盲测背景（AC3）。
- **观察：DeepSeek 质量与 Claude 参照几无差距**，两侧都紧扣设定、贴合 cold-rain 冷峻夜雨文风；轴 A 判像率均 6/6。这是「DeepSeek 能否达文字质量红线」这一头号生死假设的正面初步信号。
- **判据局限（重要，供创始人 & Story 4.2 正式词表参考）**：轴 B「重度句式套路=0」用纯启发式正则实现，区分不了「正当修辞排比」与「AI 煽情套路」——Claude 参照侧 5 处命中（「关于…关于…关于…」「为了…为了…为了…」）是有力的文学排比、非套路，却被判 FAIL。说明这条硬底线偏严，正式词表（4.2）需引入语义判断或放宽为「疑似命中→人工复核」而非直接判死。当前实现「命中即报供人工复核」，门禁只卡 DeepSeek 故不影响本次结论。
- **AC6 范围克制守住**：零 src 沉淀——装置全在 `backend/scripts/blind_test/` + 留档 `backend/docs/blind-test-4.1/`；未建 ClaudeProvider、未加 anthropic 依赖、未碰 factory BYOK 分支、无 DB 迁移。ClaudeProvider + BYOK claude 接入仍归后续 story（deferred-work.md:70,86）。
- **conftest 改动**：仅在顶部加 `sys.path` 注入 `scripts/`，使 `blind_test.*` 可被离线单测导入；未碰任何既有 fixture。
- 测试：新增 38 个离线单测（词表统计 15 + runner 12 + judge 11），全过；全量离线回归 214 passed / 218 skipped（DB 门禁用例），无本 story 引入的回归。

### File List

**新增（装置代码，backend/scripts/blind_test/）**
- `backend/scripts/blind_test/__init__.py`
- `backend/scripts/blind_test/ai_taste_lexicon_temp.py` — 临时去 AI 味词表 + 轴 B 统计
- `backend/scripts/blind_test/run_blind_test.py` — 写作任务书组装 + DeepSeek 生成 + 匿名落盘 CLI
- `backend/scripts/blind_test/judge_blind_test.py` — 盲评汇总 + 门禁判定 + 留档 CLI

**新增（单测，backend/tests/）**
- `backend/tests/test_blind_test_lexicon.py`
- `backend/tests/test_blind_test_runner.py`
- `backend/tests/test_blind_test_judge.py`

**新增（留档，backend/docs/blind-test-4.1/）**
- `writing-brief.md`、`samples/*.md`（12 篇匿名样本）、`_key.json`、`scoring-sheet.md`、`report.md`

**修改**
- `backend/tests/conftest.py` — 顶部加 sys.path 注入 scripts/（使装置可离线单测）
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — 4-1 状态流转
- `_bmad-output/implementation-artifacts/deferred-work.md` — 登记门禁结论 + 正式盲评待办

## Change Log

- 2026-08-04：实现盲测门禁装置（临时词表+轴B统计、写作任务书+DeepSeek生成、判定+留档），跑通一轮盲测 AI 初评，GATE=PASS（非正式，待创始人真人复核）。修正句式套路正则假阳性。
