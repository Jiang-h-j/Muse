---
baseline_commit: 49d33bf4595fcbd5404a2cc970cf2e9df4aec5f4
---

# Story 1.6: 继续创作——按 phase 跳转当前步骤

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a 有在写作品的用户，
I want 点「继续创作」直接回到该作品当前所处的创作步骤，
so that 我不必手动找自己写到哪了。

## Acceptance Criteria

1. **Given** `project` 记录带 `phase` 字段，取值 `explore`/`chapter`/`archive`（后端 Story 1.4 已建表并返回，`models/project.py:36`、`schemas/project.py:52`）
   **When** 我在作品行点主操作按钮（原型 `data-continue`，`app.js:1835-1841`）
   **Then** 系统按 `phase` 路由——`explore`→探索页、`chapter`→章节页、`archive`→归档页（**替代原型仅 `id==="nameless"` 特例 + 其余「目标页面待设计」占位**的现状，`app.js:1837-1839`），跳转逻辑对**所有作品**（三种 phase 各有样例）完整可测

2. **Given** 目标创作页在后续 Epic（探索属 E2、章节属 E4、归档属 E5）才真正接真实数据
   **When** 本 story 阶段跳转到尚未接真实数据的目标页
   **Then** 跳转 URL/路由正确、`render()` 能识别并渲染对应原型页（**本 story 把 explore/chapters 路由从硬编码 `demo` 改为按 `:id` 参数化**，与已参数化的 archive 对齐），可被后续 Epic 无缝接管（Epic 2/4/5 只需在对应 render 函数内用路由 id 取真实数据）；**本 story 只保证路由正确，不要求目标页功能完整、不改目标页内部逻辑**

3. **Given** 作品行主操作按钮文案（原型 `action` 字段：`explore`→「继续设定」、`chapter`→「阅读草稿」等）
   **When** 渲染作品行
   **Then** 按钮文案按该作品 `phase` **语义派生**（不再依赖 mock 写死的 `action` 字段），与 phase 一致，**不再出现原型「目标页面待设计」占位**（`app.js:1839`）

## Tasks / Subtasks

- [x] **Task 1：建立 phase 元数据映射（AC1/AC2/AC3）**
  - [x] 在 `prototype/app/app.js` 的 `projects` 数组定义之后、`projectRow` 之前，新增一张 phase 元数据表 `PHASE_META`（单一数据源，避免三处分散映射），每个 phase 键含：`label`（中文展示串，供作品行状态区）、`continueLabel`（继续按钮文案）、`route(id)`（返回该 phase 的目标 hash 路由）。三个键：
    - `explore` → `{ label: "故事设定", continueLabel: "继续设定", route: (id) => \`#/projects/${id}/explore\` }`
    - `chapter` → `{ label: "章节创作", continueLabel: "阅读草稿", route: (id) => \`#/projects/${id}/chapters/1\` }`
    - `archive` → `{ label: "已归档", continueLabel: "回到归档", route: (id) => \`#/projects/${id}/archive\` }`
  - [x] 文案（`label`/`continueLabel`）与原型现有语义保持一致即可（`explore`/`chapter` 照抄原型现有 `action`：「继续设定」「阅读草稿」；`archive` 原型无样例，取语义一致的「回到归档」）；**章节路由固定 `/chapters/1`**——「读到第几章」是 Epic 4 的真实数据，本 story 用第 1 章占位（陷阱④）
- [x] **Task 2：mock `projects` 数组 phase 中文→英文枚举 + 覆盖三态（AC1）**
  - [x] 把 `app.js:209-240` 三条 mock 作品的 `phase` 由中文改为**英文枚举**（与后端 `models/project.py` 一致，是 phase 路由判断的前提，陷阱①）：`nameless`→`"explore"`、`mist-harbor`→`"chapter"`、`stardust-postman`→**`"archive"`**（改这一条以让 `explore`/`chapter`/`archive` 三态各有可点测样例，AC1「对所有作品完整可测」）
  - [x] **仅改 `phase` 值**：同数组的 `mode`/`attention`/`detail`/`updated`/`action` **保持不动**（`mode` 中文展示与 continue 路由无关，不在本 story 范围；`attention`/`detail`/`action` 是展示 mock，其真实性属后续数据接线，本 story 不负责——见陷阱②「克制范围」）。`action` 字段虽保留但 `projectRow` 不再读它（Task 3 改为派生），保留是为最小化 mock 扰动，勿顺手删（YAGNI 的反面：删它需连带核对无其它引用，非本 story 必需）
- [x] **Task 3：`projectRow` 用 phase 派生展示 + 按钮文案（AC1/AC3）**
  - [x] `app.js:332` 作品行状态区 `<span>${project.phase}</span>` → `<span>${PHASE_META[project.phase].label}</span>`（英文枚举转中文展示，phase 改英文后不改此处会显示英文）
  - [x] `app.js:336` 主按钮 `${project.action}` → `${PHASE_META[project.phase].continueLabel}`（文案按 phase 派生，AC3）
  - [x] 其余 `projectRow` 结构/class/`data-continue="${project.id}"` **保持不变**（`data-continue` 仍传 project id，Task 4 的 handler 据 id 查 phase）
- [x] **Task 4：`data-continue` handler 改为按 phase 路由（AC1/AC3）**
  - [x] 重写 `app.js:1835-1841` 的 `data-continue` 点击回调：由 `button.dataset.continue` 拿 project id → 在 `projects` 数组 `find` 到该作品 → 取 `PHASE_META[project.phase].route(id)` → `location.hash = 目标路由`
  - [x] **删除** 原「`nameless` 特例跳 explore、其余 `textContent = "目标页面待设计"`」两分支（AC1「替代特例」、AC3「消除占位」）；找不到作品或 phase 非法时安全兜底（`find` 返回 `undefined` 时不跳转、不报错，防御性即可，不需弹错）
  - [x] **不重置任何 sessionStorage/全局状态**：continue 是「回到已有作品断点」，语义上不清空探索/章节状态（区别于 `data-new-project` 的全套重置 `app.js:1790-1800`，那是新建才做）——陷阱③
- [x] **Task 5：`render()` 路由 explore/chapters 参数化（AC2）**
  - [x] 改 `app.js:2293-2314` `render()`：新增 `exploreMatch = hashPath().match(/^#\/projects\/([^/]+)\/explore$/)`、`chapterMatch` 正则由 `demo` 改为 `([^/]+)`（`/^#\/projects\/([^/]+)\/chapters\/(\d+)$/`）
  - [x] 分派：`exploreMatch` → `renderExploration()`；`chapterMatch` → 沿用现有 `chapterCreationIndex = Math.max(0, Number(chapterMatch[<章号捕获组>]) - 1)` 后 `renderChapterCreation()`（archive 分支已参数化，保持不动）；**参数化后章号捕获组由 `[1]` 改为 `[2]`**（新增 id 捕获组在前）
  - [x] **保持** `style-anchor`/`readthrough`/`settings/model-access`/`stage-direction` 等 demo 专属精确路由不变（它们不是 continue 目标，参数化会误伤）
  - [x] **不改 `renderExploration`/`renderChapterCreation`/`renderChapterArchive` 函数体**：它们靠全局状态渲染、不读路由 id，参数化后照常渲染原型内容（为后续 Epic 用路由 id 取真实数据铺路，AC2「无缝接管」）——陷阱⑤
- [x] **Task 6：手工验证 + 铁律确认（AC 全，done 前必过）**
  - [x] 起原型静态服务器 `cd prototype/app && python3 -m http.server 4173 --bind 127.0.0.1`，硬刷新（Cmd+Shift+R，app.js 会被缓存）
  - [x] `#/projects` 三条作品：点 `nameless`（explore）→ 落 `#/projects/nameless/explore` 且渲染探索页；点 `mist-harbor`（chapter）→ 落 `#/projects/mist-harbor/chapters/1` 且渲染章节页；点 `stardust-postman`（archive）→ 落 `#/projects/stardust-postman/archive` 且渲染归档页（三态路由全对、无白页 fallback、无「目标页面待设计」占位）
  - [x] 三条作品行状态区中文 phase 展示正确（故事设定/章节创作/已归档）、按钮文案与 phase 语义一致
  - [x] 回归：`#/projects/demo/explore`、`#/projects/demo/chapters/1`、`#/projects/demo/archive`（截图清单里的 demo 路由）仍能正常渲染（demo 是合法 id，参数化后照常匹配）；`#/login`/`#/register`/`#/settings/model-access` 等其它路由无回归
  - [x] **不碰后端**：`backend/` 一字节不动（后端 phase 字段 1.4 已就绪，本 story 零后端增量，见 Dev Notes「后端零增量」）

## Dev Notes

### 🔑 本 story 的性质：这是 Epic 1 里第一个「AC 本体即前端行为」的 story
1.1~1.5 是后端 story，其铁律「`prototype/app/app.js` 一字节不改、前端接线推后」指的是**后端 story 不顺手做前端数据接线**。**1.6 不同**：它的三条 AC 全部描述前端交互（按 phase 路由、路由可被接管、按钮文案派生），**改 `app.js` 是 1.6 的正当本体交付，不是违反铁律**。项目方法论本就是「先用 AI 把 `prototype/app/` 打磨到最终形态，后端再逐页替换 mock」——原型是被打磨的对象，前端交互逻辑正是要在原型上做实。

**范围边界（本 story 做 / 不做）**：
| 做 | 不做（越界 / 属别的 story） |
|---|---|
| continue 按 phase 路由（Task 4） | 接 `GET /api/projects` 替换 mock 数组（属列表数据接线，见下「为何不接 API」） |
| explore/chapters 路由参数化（Task 5） | 改目标页 `renderExploration`/`renderChapterCreation` 内部（属 Epic 2/4） |
| 按钮文案 + 状态区 phase 展示派生（Task 3） | `mode` 中英映射、`attention`/`detail` 真实化（属列表数据接线） |
| mock phase 值改英文枚举（Task 2） | 空态/失败态前端接线（属 1.4 的列表数据接线契约） |
| — | 任何 `backend/` 改动（phase 后端已就绪，零增量） |

### 🔑 为何后端零增量、且不接 API（本 story 唯一的关键判断）
- **后端 phase 已完全就绪**：Story 1.4 建表时 `phase` 列已落（`models/project.py:36`，`String(16)`，默认 `"explore"`，英文枚举 `explore`/`chapter`/`archive`），`ProjectResponse` 已返回 `phase`（`schemas/project.py:52`）。**1.6 无任何后端新端点/新字段需求**——AC 全程未要求后端做任何事。故 `backend/` 一字节不动。
- **不接 `GET /api/projects`（重要范围决策）**：AC2 明确「本 story 只保证路由正确，不要求目标页功能完整」。若在 1.6 接真实列表 API，会连带拖入——token 携带、`mode`/`phase` 全量中英映射、空态(`empty-library`)/失败态(`library-error`)前端接线、`updatedAt` 相对时间格式化——这**整套正是 Story 1.4 completion notes 登记的「列表数据接线契约」**，属独立的前端数据接线关注点（越界且 scope 爆炸）。1.6 基于 mock 数组的 `phase` 字段实现路由逻辑，**该逻辑对真实数据同样成立**（接线后 `phase` 来自 API，`PHASE_META`/handler/`render` 不变）。因此 1.6 保持 vanilla、不调 fetch、不引入 Vite。

### 关键实现陷阱（务必规避）
- **陷阱①：mock `phase` 必须改英文枚举，否则路由判断无从下手。** 原型 mock 数组 `phase` 存**中文**（"章节创作"/"故事设定"，`app.js:216/227/234`），而后端与路由判断用**英文枚举**（explore/chapter/archive）。continue 要按 phase 路由，前端必须持有稳定英文键。改中文→英文后，作品行状态区显示会变英文，故 Task 3 必须同步加 `label` 中文映射回来。这与 Story 1.4 陷阱③「mode/phase 存英文枚举、中文是展示层的事」一脉相承。
- **陷阱②：克制范围，只碰 phase 链路。** 手滑风险是「既然改 mock，顺手把 `mode` 也改英文 + 加映射、把 `attention`/`detail` 真实化」——**不要**。`mode` 展示、`attention`/`detail` 与 continue 路由无关，AC 未提，属后续列表数据接线。本 story 只动 `phase` 值 + phase 派生的两处展示（状态区 label、按钮文案）+ 路由。
- **陷阱③：continue 不重置状态。** `data-new-project`（`app.js:1790-1800`）跳 explore 前重置一大堆全局态/sessionStorage（`clearPendingStoryProfile`、清 `explorationModeKey`/`confirmedStoryProfileKey` 等）——那是**新建**语义。continue 是**回到已有作品断点**，绝不清空。重写 handler 时勿照抄 new-project 的重置块，只做 `location.hash = route`。
- **陷阱④：章节路由用 `/chapters/1` 占位。** `render()` 的 chapter 路由需章号（`/chapters/(\d+)`）。「读到第几章」是 Epic 4 的真实数据，本 story 无来源，固定跳第 1 章。`PHASE_META.chapter.route` 返回 `#/projects/${id}/chapters/1`。
- **陷阱⑤：不改目标页函数体。** `render()` 参数化后，`renderExploration`/`renderChapterCreation` 内部仍全用全局状态与 `demo` 硬编码跳转（如 `app.js:589/1240/1665/1799` 的 `demo` 内部导航）。这些是**目标页功能**，AC2 明确「不要求目标页功能完整」——本 story 一律不动，留给 Epic 2/4。只要 `render()` 能识别 `:id` 路由并渲染出页面即算「路由正确」。
- **陷阱⑥：`data-continue` 仍传 project id，不传 phase。** 保持 `projectRow` 里 `data-continue="${project.id}"` 不变；handler 内用 id 从 `projects` 数组 `find` 出作品再取 phase。别改成 `data-continue="${project.phase}"`——那样丢了 id 就无法拼目标路由。

### 强制复用 / 对齐的既有事实（照现状，勿另起炉灶）
- **路由匹配范式**：`render()`（`app.js:2293-2314`）已有 `archiveMatch = hashPath().match(/^#\/projects\/([^/]+)\/archive$/)` 的**按 id 参数化正则**样板——explore/chapters 照此改（`([^/]+)` 捕获 id）。archive 分支已参数化，是现成模板。
- **hash 赋值即路由**：全站 `location.hash = "..."` 触发 `hashchange → render`（`app.js:2346`），无路由库。continue handler 直接赋值 hash 即可。
- **phase 枚举真值来源**：英文枚举定义在后端 `models/project.py:36` 注释与 `services/project_service.py:21`（`_INITIAL_PHASE = "explore"`）——前端 `PHASE_META` 三个键须与之**逐字一致**（explore/chapter/archive），为接线后无缝对接。
- **展示派生原则**：Story 1.4 completion notes 已定「`attention`/`detail`/`action` 为 phase 派生展示态、`mode`/`phase` 英文枚举→中文展示映射在前端」。本 story 的 `PHASE_META.label`/`continueLabel` 正是这一原则对 `phase`→按钮文案/状态串的落地（`action` 由写死改为派生，是该契约的兑现）。

### 原型交互契约（页面即契约，AC 事实来源；本 story **改** `prototype/app/app.js`）
> 以下行号经核实（就绪报告引用的行号为近似值）。本 story 是 Epic 1 首个正当改 `app.js` 的 story，改动集中在 5 处：
- `app.js:209-240` — `projects` mock 数组（三条：`mist-harbor` phase"章节创作"、`stardust-postman` phase"章节创作"、`nameless` phase"故事设定"）。**Task 2 改**：phase 中文→英文，`stardust-postman` 改 `archive` 覆盖第三态。
- `app.js:324-342` — `projectRow`：`app.js:332` 状态区 `${project.phase}`、`app.js:336` 主按钮 `${project.action}` + `data-continue="${project.id}"`。**Task 3 改**这两处为 phase 派生；`data-continue` 保持传 id。
- `app.js:1835-1841` — `data-continue` 点击回调现状：`if (button.dataset.continue === "nameless") location.hash = "#/projects/demo/explore"; else button.textContent = "目标页面待设计";`。**Task 4 整段重写**为按 phase 路由。
- `app.js:2293-2314` — `render()` 分派：explore（`app.js:2298` 精确 `#/projects/demo/explore`）、chapters（`app.js:2295` 正则含 `demo`）、archive（`app.js:2296` 已按 id 参数化）。**Task 5 改** explore/chapters 为 `:id` 参数化。
- `app.js:1790-1800` — `data-new-project` 的全套状态重置（**仅供对照，勿动**）：说明 continue 与 new-project 语义不同（陷阱③）。

### 已核实：UX-ALIGN-03「阶段规划」文案残留 **已不存在**，本 story 不涉及
就绪报告（2026-07-23，`implementation-readiness-report-2026-07-23.md:260`）曾登记：章节页返回链接文案残留「← 阶段规划」建议顺带清理。**经核实当前 `app.js:1240` 已是「← 故事设定」**（原型其后又打磨过），该残留已修复。本 story 不处理此项（且它属章节页内部，AC2 边界外）。

### Project Structure Notes
- **改动文件唯一**：`prototype/app/app.js`（5 处，见上「原型交互契约」）。不新增文件、不改 `styles.css`/`index.html`（无新样式/结构需求）、不碰 `backend/`、不引入构建工具。
- **无偏差**：延续原型 vanilla JS + hash 路由形态；`PHASE_META` 作为模块级常量新增在 `projects` 数组之后，与现有 `styleSampleLibrary`（`app.js:1872`）等模块常量风格一致。
- **测试形态**：原型无自动化测试框架（vanilla 静态原型），本 story 用 Task 6 手工浏览器验证覆盖全 AC（三态路由 + 展示 + 回归），与 memory「运行：`cd prototype/app && python3 -m http.server 4173` 硬刷新」一致。

### 质量门禁（done 前必过）
- 手工浏览器验证全 AC（Task 6）：三 phase 各点测、路由正确无白页、无「目标页面待设计」占位、demo 路由无回归、其它路由无回归。
- `backend/` 无改动（`git status backend/` 应为空）——本 story 零后端增量。
- 若本机装了前端 lint（原型此前无构建，通常无）：`app.js` 手改后目视确认无语法错误（可用 `node --check prototype/app/app.js` 快速校验语法）。

### 待澄清（保存至末尾，请用户确认）
- **无阻塞性疑问。** 关键范围判断（1.6=纯前端路由 story、后端零增量、不接 GET API、不引 Vite）已在开发前与用户对齐、用户授权按最佳方案执行。若后续希望把「列表数据接线（GET /api/projects 替换 mock）」也纳入或单独立 story，可在本 story done 后另行安排——1.6 的路由逻辑对接线后的真实数据零改动即兼容。
- `archive` 的 continue 文案已定为「回到归档」（用户 2026-07-24 裁定：最中性、所见即所得、与其它阶段「动作+去向」风格一致）。dev 照此实现，不再作为待决项。

### References
- [Source: _bmad-output/planning-artifacts/epics.md#Story-1.6（L377-395）] — 用户故事、3 条 AC、`data-continue` 原型行号、phase 三态路由、「替代 nameless 特例」「消除占位」「路由正确不要求目标页完整」。
- [Source: _bmad-output/planning-artifacts/epics.md#Epic-1-Story依赖（L242-243）] — `1.4 →{1.5, 1.6}`；「1.6 project 加 `phase`」（实为 1.4 建表时已一并落，1.6 只**用** phase 路由）。
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-Muse-2026-07-23/EXPERIENCE.md（L36-71,145-159）] — 路由表（explore/chapters 硬编码 demo、archive 唯一按 id 参数化）、页面地图、Key Flow「继续」入口、已知不一致「除 nameless 外点继续显示占位」。
- [Source: _bmad-output/planning-artifacts/architecture.md#API-Naming（L297-301）] — RESTful 复数 + 资源 id 路径 `/api/projects/{id}`（前端路由 `#/projects/:id/...` 与之语义对齐）。
- [Source: backend/src/muse/models/project.py（L35-36）] — `phase` 列 `String(16)`、默认 `"explore"`、英文枚举 explore/chapter/archive（前端 `PHASE_META` 键须逐字一致）。
- [Source: backend/src/muse/schemas/project.py（L49-53）] — `ProjectResponse` 已返回 `phase`（后端零增量的依据）。
- [Source: backend/src/muse/services/project_service.py（L20-21）] — `_INITIAL_PHASE = "explore"` 新建初始 phase。
- [Source: _bmad-output/implementation-artifacts/1-4-作品创建与列表持久化空-失败状态.md#字段决策表/Completion Notes] — phase 存英文枚举、中文展示映射在前端、`attention`/`detail`/`action` 为 phase 派生展示态（本 story `PHASE_META` 派生的上游依据）。
- [Source: prototype/app/app.js（L209-240）] — `projects` mock 数组（Task 2 改 phase）。
- [Source: prototype/app/app.js（L324-342）] — `projectRow`（Task 3 改状态区/按钮派生）。
- [Source: prototype/app/app.js（L1835-1841）] — `data-continue` 现状 handler（Task 4 重写）。
- [Source: prototype/app/app.js（L1790-1800）] — `data-new-project` 全套重置（陷阱③对照，勿动）。
- [Source: prototype/app/app.js（L2293-2314）] — `render()` 路由分派（Task 5 参数化 explore/chapters；archive 参数化样板）。
- [Source: prototype/app/app.js（L2346-2348）] — `hashchange → render` 路由驱动（continue 赋值 hash 即路由）。
- [Source: _bmad-output/planning-artifacts/implementation-readiness-report-2026-07-23.md（L74,165,260）] — FR-0.3 继续创作跳转当前步骤 V1、UX-ALIGN-03（已核实修复，本 story 不涉及）。

## Dev Agent Record

### Agent Model Used

Claude Opus 4.8 (claude-opus-4-8)

### Debug Log References

- `node --check prototype/app/app.js` → 语法校验通过
- `git status --short backend/` → 空输出（后端零改动铁律满足）
- Node 路由逻辑等价验证（从 `app.js` 抽取 `projects` + `PHASE_META`，逐字复现 handler 的 `find`+`route` 与 `render()` 正则分派链）：18/18 断言通过，覆盖 AC1/AC2/AC3 + 安全兜底 + demo 回归 + 边界不误伤。

### Implementation Plan

按 Task 1→6 顺序在唯一文件 `prototype/app/app.js` 实施：先建 `PHASE_META` 单一数据源（Task 1），再将 mock `phase` 改英文枚举并覆盖三态（Task 2），随后 `projectRow` 改 phase 派生展示（Task 3），重写 `data-continue` handler 按 phase 路由（Task 4），最后 `render()` 将 explore/chapters 由硬编码 `demo` 改 `:id` 参数化（Task 5）。原型无自动化测试框架，Task 6 以语法校验 + 路由逻辑等价验证 + 后端零改动核验覆盖全 AC。

### Completion Notes List

- **AC1（按 phase 路由，替代 nameless 特例）**：`data-continue` handler 重写为 `id → find 作品 → PHASE_META[phase].route(id) → 赋值 hash`；三态样例（explore/chapter/archive）路由与目标页渲染均验证通过；未知 id/非法 phase 走 `project && meta` 安全兜底，不跳转不报错。
- **AC2（路由参数化、可被后续 Epic 接管）**：`render()` 新增 `exploreMatch`、`chapterMatch` 正则由 `demo` 改 `([^/]+)` 参数化；**关键修正**——参数化后 chapter 正则新增 id 捕获组在前，章号捕获组由 `chapterMatch[1]` 同步改为 `chapterMatch[2]`；目标页函数体（`renderExploration`/`renderChapterCreation`/`renderChapterArchive`）一字未动，靠全局状态渲染，为后续 Epic 用路由 id 取真实数据铺路。
- **AC3（按钮文案 + 状态区 phase 派生，消除占位）**：`projectRow` 状态区 `${project.phase}` → `PHASE_META[phase].label`（中文展示）、主按钮 `${project.action}` → `PHASE_META[phase].continueLabel`；「目标页面待设计」占位分支已删除，全库 grep 无残留。
- **陷阱规避确认**：①mock phase 已改英文枚举；②仅动 phase 链路，`mode`/`attention`/`detail`/`action` 未改；③continue handler 无任何 sessionStorage/全局态重置（区别于 new-project）；④chapter 路由固定 `/chapters/1` 占位；⑤目标页函数体未动；⑥`data-continue` 仍传 project id。
- **范围铁律**：`backend/` 零改动；唯一改动文件 `prototype/app/app.js`；未引入构建工具，延续 vanilla JS + hash 路由形态。
- **验证局限说明**：受环境限制未执行真实浏览器点击，改以从 `app.js` 抽取真实 `projects`/`PHASE_META` 常量 + 逐字复现 handler 与 `render()` 逻辑的 Node 等价验证替代（18/18 通过）；服务器端已 curl 核对交付的 `app.js` 含全部改动。建议评审时按 Task 6 清单在浏览器复核一次视觉呈现。

### File List

- `prototype/app/app.js`（修改，5 处：新增 `PHASE_META` 常量、mock 三条 phase 改英文枚举、`projectRow` 两处派生、`data-continue` handler 重写、`render()` explore/chapters 参数化含章号捕获组修正）

### Change Log

- 2026-07-24：实现 Story 1.6「继续创作——按 phase 跳转当前步骤」。新增 `PHASE_META` 单一数据源，将 continue 跳转由「仅 nameless 特例 + 其余占位」改为按 phase（explore/chapter/archive）完整路由；`render()` 的 explore/chapters 路由由硬编码 `demo` 改为 `:id` 参数化（为后续 Epic 无缝接管铺路）；作品行状态区与按钮文案改为按 phase 语义派生，消除「目标页面待设计」占位。仅改 `prototype/app/app.js`，后端零增量。

### Review Findings

<!-- 2026-07-24 code-review：Blind Hunter + Edge Case Hunter + Acceptance Auditor 三层对抗审查。收敛后 1 patch / 1 defer / 4 dismiss（dismiss 已按 spec 明确排除或已核实无问题而丢弃）。Auditor 判定 3 条 AC 与全部陷阱均满足。 -->

- [x] [Review][Patch] `projectRow` 渲染处 `PHASE_META[project.phase]` 无兜底，phase 越界即 TypeError 白屏 [prototype/app/app.js:351,355] — 点击处 handler 已用 `project && PHASE_META[project.phase]` 守卫，渲染处却裸取 `.label`/`.continueLabel`，同一访问模式一处守卫一处不守卫（Blind+Edge 一致命中）。当前 3 条种子 mock 均为合法 phase（`const` 数组、创建流程不 push 新项），运行时不可达；但代码注释「键须与后端英文枚举逐字一致」表明接 `GET /api/projects` 后 phase 来自系统边界，枚举漂移或回填旧中文值即崩溃。本 diff 新引入（改前 `${project.phase}` 任意值不崩）。**已修复（2026-07-24）**：提取 `const meta = PHASE_META[project.phase]`，label 降级为 `meta?.label ?? project.phase`（与改前 `${project.phase}` 行为一致）、按钮降级为 `meta?.continueLabel ?? "继续"`，与点击处守卫对齐；`node --check` 通过。

- [x] [Review][Defer] explore/chapter 目标页未消费路由 id（标题、返回链接、章节号仍走全局态 + demo 硬编码 / `/chapters/1` 占位）[prototype/app/app.js:2328,2335] — deferred, 属 Epic 2/4 范围。`render()` 的 `exploreMatch`/`chapterMatch` 已捕获 id，但 `renderExploration`/`renderChapterCreation` 函数体未读 id：标题依赖全局 `explorationTitle`（archive 分支会赋值、explore/chapter 分支不赋，首次进入显示默认「未命名小说」而非项目名）、内部返回链仍硬编码 `#/projects/demo/explore`、chapter route 恒跳 `/chapters/1`。spec AC2 明确「只保证路由正确、不要求目标页功能完整、不改目标页函数体」，陷阱④/⑤授权占位并划归 Epic 2/4 无缝接管。本 story 不处理。
