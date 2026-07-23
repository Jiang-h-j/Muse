---
name: Muse
description: AI 小说创作伙伴的体验设计系统 —— 信息架构、行为契约、状态、交互原语、无障碍与关键流程
status: draft
created: 2026-07-23
updated: 2026-07-23
project_name: Muse
authority_note: >
  本文件是从已实现原型（prototype/app/app.js 1905 行 + prototype-spec.md 行为契约）反向蒸馏的体验事实结构化镜像。
  与 BMAD-UX 默认「spine 凌驾原型」规则相反：Muse 铁律是「原型 = 唯一事实基准」。
  故本 EXPERIENCE.md 在冲突时【服从】原型代码与 prototype-spec.md，不凌驾。行号可追溯。
  视觉 token 引用见同目录 DESIGN.md，用 {path.to.token} 语法。
sources:
  - prototype/app/app.js
  - prototype/app/index.html
  - prototype/spec/prototype-spec.md
  - prototype/spec/exploration-pending-requirements.md
---

# Muse — EXPERIENCE.md

> **权威声明**：本文件是原型交互事实（`prototype/app/app.js` + `prototype/spec/*`）的结构化镜像，服务于 BMAD 交付物完整性。**与 BMAD-UX 默认规则相反**，Muse 铁律是"原型 = 唯一事实基准"，本文件冲突时**服从原型**。视觉规格见同目录 `DESIGN.md`（本文件只写行为，视觉引用其 token）。
>
> **两个下游必知的事实纠偏**：① 原型持久化用的是 `sessionStorage`（会话级，关标签页即清），**非 localStorage**——这直接决定"待确认设定刷新不丢、关标签页清空"的行为。② 登录页 error 态（expired/invalid/locked）是**预览态**，仅能经页内 `state-preview` 手动触发，**非真实校验产生**（表单只做 HTML5 `reportValidity()`）。

## Foundation

- **Form-factor**：桌面优先的响应式 Web。截图清单同时定义 1440×1100 桌面视口与 390×1200 移动作品库（app.js:1873-1901）。无原生 App / 桌面壳，纯浏览器。
- **技术形态**：vanilla JS 单文件（无构建、无模块），`<main id="app">` 单容器，全部页面用 `app.innerHTML` 字符串模板重渲染 + `addEventListener` 绑定。
- **路由**：hash 路由。`hashPath()` 剥离 `?query`，`queryState()` 解析 `?state=`；`hashchange → render`，无 hash 默认跳 `#/login`（app.js:1903-1905）。
- **存储**：`sessionStorage` 持久化探索模式 / 入口模式 / 已确认设定 / 待确认设定（键名带 `muse-` 前缀，app.js:115-117、155）。
- **UI 框架 / 设计系统：无**。设计语言靠 CSS 自定义属性（见 `DESIGN.md`）+ Google Fonts。视觉身份参考 `DESIGN.md`。

## Information Architecture

**路由表**（全部来自 `render()` app.js:1855-1871）：

| Hash 路径 | 页面 | 备注 |
|---|---|---|
| `#/login`（默认/兜底） | 登录页 | 无 hash 自动跳此 |
| `#/register` | 邀请码注册页 | 与登录同 `renderAuth`，register 态 |
| `#/projects` | 作品库（根） | 登录后落脚点 |
| `#/projects/demo/explore` | 探索页 | 引导/自由二合一，硬编码 `demo` |
| `#/projects/demo/chapters/:n` | 章节创作页 | 正则匹配章号，硬编码 `demo` |
| `#/projects/:id/archive` | 章节归档页 | **唯一真正按作品 id 参数化**的路由 |

**层级**：登录/注册 →（登录后）作品库 = 根；每个作品下三类视图：探索 → 章节创作 → 归档。归档页是"故事档案统一入口"（prototype-spec.md:47）。

**评审入口（`?state=` 参数）**：登录 `expired|invalid|locked`（app.js:244-256）；作品库 `empty|error`；探索 `conversation`（预置 5 条引导历史 + 2 条自由对话种子）。各页内均有 `state-preview` 手动触发钮。

**非路由叠层（模态，无独立 hash）**：新建小说对话框（两步 mode→naming）；故事设定确认弹窗；"回到探索"二次确认（`role="alertdialog"`，内嵌于设定弹窗）；归档章节详情弹窗。

**页面地图**：

```
#/login ⇄ #/register ──(提交, 650ms)──▶ #/projects (根)
                                            │  作品行"继续"/整行链接/••• 菜单(重命名·删除)
                                            ▼
#/projects/demo/explore ──[新建流: 弹窗 mode→naming]
   ├ 引导探索(guided) ┐
   └ 自由探索(free)   ┘→[整理为故事设定]→ 设定确认弹窗
                          ├ 直接编辑 / 反馈调整(版本号↑)
                          ├ 回到探索(二次确认→丢弃)
                          └ 确认(420ms)→ #/projects/demo/chapters/1
                                            │ input→generating(1200ms)→reading
                                            │ 改进/重新生成/段落批注
                                            └ 定稿 → #/projects/{id}/archive
                                                       ├ 设定圣经(折叠)
                                                       ├ 阶段分组(折叠)+章节卡→详情弹窗
                                                       └ 下一章卡 → 回 chapters/N（循环）
```

## Voice and Tone

- **品牌主张（权威，prototype-spec.md:19）**：`让每一个人，成为小说家。`
- **解释文案（权威，prototype-spec.md:20）**：`你参与设定、选择与修改，Agent 陪你把一个想法，一章章写成小说。`
- **品牌标记**：wordmark "M"+"Muse"；edition `Private beta · 2026`；kicker `AI novel collaboration`。
- **整体语气**：文学化、克制、诗意，带邀请感与陪伴感。Agent 定位是"陪你写 / 保留你的创作意图"，而非替你决定。引导问题刻意"偏间接、有画面感，借鉴人格测试从倾向推断"（app.js:2-4）。
- **双语排版母题**：英文小标 + 数字/中文并置（`New novel / 01`、`Free exploration / 自由探索`、`Story profile / v1`）。
- **microcopy 样本**：空库"你的第一本小说，从这里开始。"；整理中"正在把你的回答整理成一份故事设定……"；反馈占位（示例式引导）"例如：主角可以更自私一些，但不要让他成为反派。"；章节 Agent"我会保留你的创作意图，再改进这一章。"
- 微文案的品牌嗓音落点见 `DESIGN.md` 的 **Brand & Style**。

## Component Patterns

行为契约（非视觉；视觉规格见 `DESIGN.md` 的 **Components**）：

- **引导选项卡片**（app.js:819-828、954-960）：显示短标签 + 完整答案，索引 A/B/C/D；点击即提交并前进；翻回已答题按 value 高亮上次所选（`aria-pressed=true` + ✓）。
- **一句话自述 / "都不是这些"出口**（app.js:835-851、975-992）：第一题常驻输入框；其余题为折叠的"用一句话自己回答"，点击就地展开聚焦；走同一提交链路；翻回旧题若上次为自述则回填输入。
- **问卷式翻页栏**（app.js:776-791、961-974）：上一题/下一题固定底部；`canPrev = view>0`、`canNext = view<answeredCount`；不可用一侧渲染空占位保持两端对齐；翻页只移指针、**不清答案**；整理中过渡态不出翻页栏。
- **设定卡直接编辑**（app.js:511-517、639-646）：每字段 contenteditable，`input` 即写回并持久化。
- **反馈 → 版本号提升**（app.js:607-664）：提交反馈 → 按钮 disabled + "调整中…" → 520ms 后按关键词命中改对应字段（主角类→field2；冲突类→field3；世界类→field4；风格类→field5；兜底改 field5；每次必改 field1 概述）→ `revision += 1` → 改动项 `is-updated` 高亮 → 状态"已根据反馈更新 N 项设定"。`regenerate` 同样 `revision += 1`。
- **自由探索线索卡**（app.js:389-396、1062-1075）：contenteditable，聚焦清占位、失焦无内容回填"尚未确定"（`is-empty`）；自定义线索可增/删/改。
- **章节翻页阅读器**（app.js:1188-1194、1264-1272）：上/下一页 ±1；首页禁"上一页"、末页禁"下一页"；翻页清当前批注目标；固定 3 页正文。
- **段落批注**（app.js:1176、1273-1315）：每段悬浮"＋"→设目标→侧栏切"批注第 N 段"输入→保存 push 进列表并聚焦定位；列表项点击跳回对应页/段；**定稿后不再渲染"＋"触发器**。
- **改进 / 重新生成**（app.js:1333-1365）："改进本章"需有整体点评或批注才可用（`canImprove`），保留现有内容；"重新生成"允许空反馈、替换整章并清空旧批注；两者均进 900ms busy、`revision += 1`、回第 0 页。
- **作品行菜单 / 重命名 / 删除**（app.js:1790-1852）：`•••` 菜单互斥展开（`aria-expanded`）；重命名内联表单替换 `<h2>`；删除内联二次确认"删除后无法恢复。"。
- **归档折叠组**（app.js:1598-1615）：设定圣经与各阶段各自独立折叠（带高度动画），默认全收起。

## State Patterns

| 状态 | 触发 | 表现 | 源 |
|---|---|---|---|
| 会话过期 expired | `?state=expired`（仅预览） | error 条"会话已过期，请重新登录。" | app.js:245 |
| 输入错误 invalid | `?state=invalid` | login"邮箱或密码错误"；register"邀请码无效/已使用/已过期" | app.js:246-251 |
| 频控锁定 locked | `?state=locked` | error 条"登录尝试次数过多，请稍后再试。" | app.js:252 |
| 空库 empty | `?state=empty` | 隐藏列表，显示 empty-library"你的第一本小说，从这里开始。" | app.js:366-381 |
| 加载失败 error | `?state=error` | library-error"暂时无法读取你的作品。" + 重新加载钮 | app.js:381 |
| 整理中 settling | 引导答完最后一题 | ~1.2s spinner + "正在把你的回答整理成一份故事设定……"（`aria-live`），随后弹设定卡 | app.js:434-442 |
| 章节生成中 generating | 提交本章想法/跳过 | 1.2s，三步进度"整理章节计划→生成正文→检查连续性" | app.js:1214-1262 |
| Agent 处理中 busy | 改进/重新生成 | 900ms，输入禁用、结果区"正在处理…" | app.js:1345-1363 |
| 待确认设定恢复 pending | sessionStorage 有 `muse-pending-story-profile` | 进探索页即重挂设定弹窗，**刷新不回退问答主界面**；确认后清除 | app.js:155-196 |
| 定稿 finalized | 点"定稿本章" | 侧栏"本章已定稿"，正文隐藏批注触发器 | app.js:1107-1176 |
| 登录提交中 | 表单校验通过 | 按钮 disabled + "正在登录…/正在创建账号…"，650ms 后跳 projects | app.js:1679-1689 |

## Interaction Primitives

- **破坏性动作二次确认**：① "回到探索页面"→ `alertdialog`"返回后，当前设定内容和修改记录都会丢失。"→确认才丢弃（app.js:665-682）；② 删除作品内联确认。
- **问卷式前后翻页（指针/进度解耦）**：`explorationView`（在看第几题）与 `explorationHistory.length`（已答数）解耦，翻回重选不清后续答案。
- **只读连续记录**：自由探索对话"不折叠不拆分"，滚动置底。
- **就地直接编辑**：设定卡 / 线索卡均 contenteditable，编辑即入模型态。
- **会话级持续偏好**："给我一些方向"勾选状态持续到用户主动取消；方向按钮只把文本写入输入框、**不替用户提交、不替用户决定故事**（app.js:1037-1043）。
- **幕后逻辑不打扰**：阶段规划全程幕后（无独立页，确认设定时静默生成）。
- **过渡态遮盖等待**：整理中/生成中都是"传递它在认真理解我"的体感等待。
- **命名可跳过**：命名输入有值显"继续"、空显"跳过"，跳过用占位"未命名小说"。

## Accessibility Floor

行为层无障碍（视觉对比见 `DESIGN.md`）：

- **减弱动效**：`prefers-reduced-motion: reduce` 全局关停过渡与入场动画（styles.css:578）。
- **视觉隐藏可读**：`.visually-hidden` 标准 clip 类用于读屏可读的 h1。
- **焦点环**：`:focus-visible { outline: 2px solid var(--ink) }` 全局 + 各组件专门 focus 样式。
- **语义角色**：`role=dialog/alertdialog`、`role=tablist/tab + aria-selected`、`role=status` + `aria-live=polite`（整理中/生成中/翻页正文/反馈状态）、`role=textbox`（contenteditable）、`nav aria-label`、语义 `time/ol/li`。
- **aria 状态**：`aria-current=page`（主导航）、`aria-expanded`（菜单/折叠）、`aria-pressed`（选中选项）、大量 `aria-label`。
- **焦点管理**：弹窗/展开后主动 `.focus()`——二次确认回焦、批注保存后聚焦段落、新增线索/重命名聚焦输入、"都不是"展开聚焦。
- **表单**：`novalidate` + `reportValidity()`，`required/minlength=8/type=email/autocomplete`；密码显隐钮带 `aria-label`。
- **⚠️ 缺口**：无 focus trap（模态未限制 Tab 环绕）、无暗色/高对比模式、无 skip-link。这些是 V1 若做无障碍强化需补的项。

## Key Flows

主角 **苏晓**：常年追更网文、屡被烂尾气到、终于决定自己动手写的读者。每步忠于原型实际交互，★ 标关键时刻。

**A — 进门**：落地 `#/login`（品牌区滚动播放主张）→ 苏晓无账号，切"邀请码注册"→填邀请码+邮箱+密码(≥8)→提交转"正在创建账号…"，650ms 进 `#/projects`。★ 门槛极低、无验证码/第三方账号，第一眼被"我也能当小说家"击中。

**B — 作品库落脚**：`#/projects` 顶部 `Library / 03 novels`，列 3 条作品→点"＋ 开始一本新小说"→弹 mode 步骤。★ 列表里"未命名小说·继续设定"把"未完成的创作在等你"具象化。

**C1 — 引导探索（系统主导）**：选"A 引导探索"→命名（可跳过）→进探索页(guided)→纯选项式沉浸问答，一次一题、不显示历史、无右侧线索区；第一题可自述、其余有"都不是这些"出口；底部可翻页可改；共 6 题→答完 ★ **整理中过渡态**（1.2s"正在把你的回答整理成一份故事设定……"）——"它在认真理解我"的高光→弹设定卡。

**C2 — 自由探索（用户主导）**：选"B 自由探索"→进探索页(free)，左侧只读连续对话、右侧 Living notes 线索区→边聊边成形，"给我一些方向"给提示不替她提交；"整理为故事设定"首屏禁用，必须有用户发言后才可用。★ 右侧线索卡随讨论被 Agent 逐条整理、且可直接改——掌控感。

**D — 设定确认（两路汇合）**：设定弹窗 `Story profile / v1`，6 字段可直接编辑→苏晓在反馈框写"主角可以更自私一些"→提交"调整中…"→升 v2、改动项高亮、状态"已根据反馈更新 N 项设定"→若点"回到探索页面"★ 二次确认拦截防误伤→点"确认故事设定"→✓ + "正在进入第一章创作"→420ms 跳 chapters/1（幕后静默生成阶段计划，★ 无打扰）。

**E — 章节创作与修改**：`input` 态可选填"本章想法"（空则"跳过并生成"）→`generating` 三步进度→`reading` 阅读态 3 页翻页→苏晓逐段"＋"批注 + 写整体点评→"改进本章"（900ms busy→v↑，从第一页呈现改动）；或"重新生成"替换整章。★ 每条批注/点评被明确"用于改进本章、保留你的创作意图"，读到 v2 里被强化的句子——第一次看见自己的意见变成文字。

**F — 定稿 + 分阶段归档**：点"定稿本章"→跳 archive→归档页首屏清爽（设定圣经 + 分阶段章节，默认全收起）→点开章节卡→详情弹窗展示凝练五项（本章发生什么/人物变化/新增事实与线索/未解决悬念/章末状态）。★ 第一次看到"已写下的故事"被结构化归档成长期记忆——成就感闭环。

**G — 循环下一章**：归档"下一章卡"→重置章节态→回 chapters/N，循环 E→F。**边界事实**：第二阶段是排版预览假数据，其"下一章"仅改文案、不进真实创作流程（app.js:1416-1453）。

> **两处已知小不一致**（供文档取舍，非本文件裁决）：章节创作页返回链接文案仍写"← 阶段规划"但实际指向 explore（app.js:1229）；作品库中除 `nameless` 外的作品点"继续"只显示"目标页面待设计"占位（app.js:1824-1830）。

## 待实现机制性需求（V1 须新增 · 原型未表达）

来源：`prototype/spec/exploration-pending-requirements.md`（权威登记表）。静态原型仅用固定题库/固定顺序/固定轮数验证了页面布局与问答/反馈交互，**以下机制无法表达**：

**EXP-P01 · 问题原型库与动态选题**（待设计、待实现，2026-07-16）
- 不用固定问题清单机械提问，而用"有趣、间接甚至抽象"的问题（借鉴人格测试从答案推断倾向）理解用户真正想写什么。
- 库组成：① 问题原型（从哪些角度问）② 推断标签（回答→创作偏好，不把单次回答当结论）③ 追问策略（继续确认/换角度验证/跳过已明确项）。
- 运行规则：Explorer Agent 依当前对话+已推断+置信度**动态选下一题**；顺序与数量不固定；同一结论多角度交叉验证。
- **原型差距**：现用 `explorationQuestions` 预设数组 + 固定顺序（app.js:5-62）。

**EXP-P02 · 以设定结果覆盖度决定探索是否完成**（待设计、待实现，2026-07-16）
- 不规定"必须答 N 题"，而由系统判断"整理设定所需结果是否已充分形成"再决定继续追问或放行。
- 必须覆盖的结果：核心吸引力/主角及核心欲望/主要阻力或冲突/世界最关键规则/整体气质/期望阅读体验；每个结果至少记录：当前结论/来源/置信度/是否经用户确认。
- 完成判断由"理解充分程度"而非固定轮数决定；用户在右侧直接改/确认某项→提高该结果确定性、避免重复提问。
- **原型差距**：现以固定问答轮数开启"整理为故事设定"，未实现覆盖度/证据来源/置信度判断。

> **与 epics 的衔接**：epics.md 已把 EXP-P01/P02 归为 V2；本节仅登记原型未表达的机制事实，具体版本归属以 epics.md 为准。另 epics.md §"UX 设计需求"登记的两处 V1 须新增入口（UX-DR1 文风样本锚点、UX-DR2 BYOK 设置页 + 用量入口）原型同样未表达，视觉/交互规格待其实现时补入本 spine。
