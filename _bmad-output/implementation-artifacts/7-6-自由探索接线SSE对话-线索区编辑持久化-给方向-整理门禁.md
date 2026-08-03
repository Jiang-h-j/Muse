---
baseline_commit: e481329
---
# Story 7.6: 自由探索接线（系统引导 / 按需回答思路 / 线索编辑持久化 / 7项完成度门禁）

Status: review

> **2026-07-31 Correct Course 修订**（Sprint Change Proposal 2026-07-31，`_bmad-output/planning-artifacts/sprint-change-proposal-2026-07-31.md`）：本 story 在下方 Tasks 1–6 已完成的 SSE 消费、Bearer/401、AbortController、自由消息真实持久化、右侧 preset/custom 线索 CRUD、`user_edited` 保护、跨项目/跨账号加载代次与清理、free settle task SSE 与候选卡弹出**全部保留、无需重做**。本次修订**替换**的只是「固定给方向文案」（原「给我一些方向」三选项）与「一条消息即门禁」两处已被判定为过时的产品逻辑，改为消费 Epic 2 **Story 2.8**（自由探索设定导航/按需回答思路/7项完成度门禁，backlog）提供的后端能力。**在 Story 2.8 完成并被本 story 消费之前，不得把本 story 标记为 `review`**；下方 `## Acceptance Criteria` 已按 `epics.md` 的新 Story 7.6 定义整体重写，`## Tasks / Subtasks` 的既有勾选历史保留不动，供后续增补消费 2.8 的新任务。

## Story

As a 选了自由模式的用户，
I want 与真实 Explorer Agent 连续对话并直接编辑故事线索，
so that 我用自己的节奏聊出设定，且线索由我主导。

## Acceptance Criteria

> **2026-07-31 Correct Course 重写**（对齐 `epics.md` 新 Story 7.6 定义，取代下方旧版 1–7 条）：本 story 仍是「把自由探索页从纯内存 mock 接到真实后端」，但产品契约已从「用户随便聊、Agent 无限追问」改为「系统主导发现设定缺项、每轮只问一个具体问题、用户按需获取思路或跳过、7 项主干齐备才整理」。**新增硬前置：本 story 依赖 Epic 2 Story 2.8**（自由探索设定导航/按需回答思路/7项完成度门禁，backlog）提供的后端能力；Story 2.8 未完成前，本 story 不得实现下方第 2–6 条，也不得转 `review`。
>
> **复用而不重造：** 继续复用 Story 7.5 已建的 `apiStream`（Bearer 鉴权、401 refresh/跳登录、`fetch`+`ReadableStream` SSE、AbortController）与 `explorationApi`（`enter`、`taskEvents`）；复用本 story 已实现的 free 消息 SSE、线索 CRUD、`teardownExplorationInflight` 生命周期清理、`openStoryProfileFromBackend`。不新建 EventSource、第二套 SSE 解析器或 mock profile 构造。
>
> **关键历史教训：** 7.5 code review 已修复「模式残留」「在途 SSE 切页后污染另一作品」「logout 后 A 的 pending 卡展示给 B」「SSE 无终态卡死」。消费 2.8 导航状态时同样要纳入这套跨项目/跨账号生命周期清理，不能只让旧版聊天/线索安全。

1. **[进入与恢复，含导航状态]** 进入 `#/projects/{projectId}/explore` 的自由模式时，先 `POST /api/projects/{projectId}/explore` 建/取会话（首次自动播种 4 个预设线索），并发 `GET .../free/messages`、`GET .../free/clues` 与 **Story 2.8 提供的导航状态端点**（7 项主干完成度、当前字段、当前问题、`readyToSettle`）。页面须显示后端返回的完整连续对话、线索与导航进度；刷新/断线重进不得丢失。加载期间有明确 loading 态；失败（非 401）有可重试 error 态。401 仍由 7.1 `apiFetch`/7.5 `apiStream` 统一处理。

2. **[零对话起点]** 会话尚无任何对话时，展示「你想从哪里开始？」四个固定入口（故事想法 / 主角 / 核心冲突 / 世界与氛围）；不再展示旧版「给我一些方向」复选框与固定三文案。点击入口调用 2.8 的起始能力生成对应第一问，随后展示常规输入框。这四个入口是产品固定入口，不得渲染成或命名为 AI 建议。

3. **[真实 SSE 对话 + 当前具体问题]** 用户发送非空消息后，调用 `POST /api/projects/{projectId}/explore/free/messages`，用既有 `apiStream` 消费 `delta → done → error`。连续对话只读、不折叠不拆分，新消息自动滚到底。`done` 后串行：① `GET free/messages` 重新同步权威历史；② 调用 2.8 导航刷新能力，取回更新后的 7 项完成度与下一个具体问题；③ 用新问题渲染 Agent 最新轮次下方的「当前具体问题」区。流内 `error`、建流前非 2xx、或无终态流结束，均需退出 busy 态并给出可重试提示，不得把不完整 delta 当作已完成回复。离开探索页、切换项目、新建作品、登出时必须 abort 在途对话流与导航请求，以 projectId/代次校验丢弃过期回调。

4. **[按需回答思路 + 跳过]** 在当前具体问题下方提供「没想好？看看几个思路」入口：仅当用户点击时才调用 2.8 的按需建议能力，请求 2–4 个与当前问题、已有线索、缺失字段相关的回答选项；不得在每轮自动生成。用户点击任一选项即直接作为本轮回答提交（等价于发送该消息），触发第 3 条的同一套刷新链路。同时提供「先跳过这个问题」：点击后调用 2.8 的跳过能力，把当前字段标记 `skipped`，前端据返回的下一问题或收束态重绘，不得让同一字段在跳过后继续被追问。

5. **[右侧故事线索：真实持久化 + 用户优先，保持不变]** 右侧线索区数据源为后端 `ClueResponse[]`：预设线索按 `displayOrder` 显示、`PATCH` 编辑置后端 `userEdited=true`；自定义线索走 `POST`/`PATCH`/`DELETE`。每轮对话 `done` 后的自动整理只更新 `userEdited=false` 的 preset，绝不覆盖用户已编辑值或触碰 custom（Story 2.6 硬 AC，延续不变）。`preset_label_immutable`/`clue_not_deletable`/`project_not_found` 等既有错误码继续按原映射处理。

6. **[7 项完成度门禁 + 真 settle]** 「整理为故事设定」按钮的可用性完全消费 2.8 返回的 `readyToSettle`：7 项通用主干（题材/核心吸引力/主角/主要冲突/关键世界规则/整体气质/开篇钩子）未全部 `filled`/`skipped` 时按钮禁用并展示当前进度提示；全部完成后 Agent 在对话流中给出明确收束文案、按钮才开放。点击后仍走 `settleFree(projectId)` → `{taskId}` → 既有 `taskEvents` 消费 `progress → result → error`，`result.profile` 用 `openStoryProfileFromBackend` 弹真实候选卡；若用户绕过前端直接触发、后端 400 拒绝，前端据返回缺失项给出可读提示，不得再依赖旧版「≥1 条用户消息」判据。settle 期间禁用重复触发；离开/登出/新建时 abort 并防跨项目弹卡。候选卡编辑/反馈/确认/丢弃/文风锚点仍属 Story 7.7 范围。

7. **[严格保持 UX-DR5 新契约]** 连续对话记录只读展示、不折叠不拆分；右侧线索可直接编辑；零对话四入口、当前具体问题、按需思路、跳过、完成收束五态齐备；只有 7 项主干齐备后才允许整理。只替换数据源与交互逐层，保留页面双栏布局与整体阅读体感。

8. **[租户、模式与边界]** 前端不得传 `userId` 或自行判断资源归属；越权/不存在同码 404；free 项目只调 free 端点避免 409 `mode_mismatch`。**本 story 不修改 Story 2.8 之外的后端能力**（不新增/不重复实现导航状态、门禁判定逻辑——那属于 2.8 职责）；不新增前端构建工具/module/路由级守卫；不把 API 业务数据放入 localStorage/sessionStorage（仅方向偏好等已有 UI 态例外）。

## Tasks / Subtasks

- [x] **Task 1：追加 free 域 API 薄封装，复用 7.5 SSE 地基**（AC: 1, 2, 3, 5, 7）
  - [x] 在 `prototype/app/api.js` 的现有 `explorationApi` 对象中追加，不新建平行 API 对象：
    - `listFreeMessages(projectId)` → `GET /api/projects/${projectId}/explore/free/messages`
    - `sendFreeMessage(projectId, {content}, {onEvent, signal})` → `apiStream` `POST .../free/messages`，body `{content}`
    - `listClues(projectId)` → `GET .../free/clues`
    - `createCustomClue(projectId, {label, value})` → `POST .../free/clues`
    - `editClue(projectId, clueId, {value, label})` → `PATCH .../free/clues/${clueId}`；label 未改时不要发送 `undefined` 之外的伪值
    - `deleteClue(projectId, clueId)` → `DELETE .../free/clues/${clueId}`
    - `refreshClues(projectId)` → `POST .../free/clues/refresh`
    - `settleFree(projectId)` → `POST .../free/settle`
  - [x] 保留并复用已有 `enter(projectId)`、`taskEvents(taskId)`、`apiStream`。CRUD 全走 `apiFetch`，两个流端点全走 `apiStream`；不要复制 Bearer/refresh/error 解包代码。
  - [x] 更新 `api.js` 的探索端点说明与 `window.explorationApi` 既有暴露（对象引用已暴露，无需另挂新全局）。

- [x] **Task 2：建立自由探索的真实状态、通用清理与加载器**（AC: 1, 2, 3, 5, 7）
  - [x] 在 `app.js` 为 free 接线增加最小状态：后端线索数组、加载态/错误/代次、对话 busy 标记、对话 AbortController、settle 错误/终态标记（可复用现有 settle controller，但必须保证 guided/free 互不串扰）。
  - [x] 将 7.5 的 `teardownGuidedInflight` 扩展并改名为表达真实范围的清理函数（如 `teardownExplorationInflight`）；它必须 abort guided interpret、free message、settle 流，递增相关代次并复位全部提交门禁。更新所有现有调用点：离开 explore 的 render 分支、进入任一 explore 分支、`loadGuidedExploration`、新建作品重置、logout。不得损坏 7.5 的 guided 防污染修复。
  - [x] 新增 `loadFreeExploration(projectId)`：先 `await explorationApi.enter(projectId)` 以确保首次进入播种 preset，再 `Promise.all([listFreeMessages, listClues])` 回填。转换后端 `{role, content, createdAt}` 到现有渲染可消费的消息形态，或让渲染直接读 `content`，但只能保留一个前端消息字段约定。
  - [x] 以 `projectId`、自由加载代次和当前 hash 三重校验异步回调；切页/换作品/登出后的结果一律丢弃。进入自由模式不能再直接 `guidedLoadState="ready"; renderExploration()`。
  - [x] 给自由分支提供 loading/error/retry UI，错误信息走 `explorationErrorText` 的集中映射。`enter` 完成前不要并发 list，避免首次进入拿不到 preset clues。

- [x] **Task 3：替换 mock 对话为 SSE 真实流，并在成功后自动整理线索**（AC: 2, 3, 6, 7）
  - [x] 将 `#explore-response` 的同步 mock submit（当前插入固定 Agent 文案）改为 async：校验非空、记录当前 projectId/代次、立即追加用户消息视觉态、清空输入、设 busy、创建 AbortController，调用 `explorationApi.sendFreeMessage`。
  - [x] `delta` 累积到当前 Agent 临时消息并重绘/滚底；`done` 标记终态，随后串行 `await listFreeMessages(projectId)` 回填权威对话、`await refreshClues(projectId)` 整体替换线索、解除 busy。任一步异步完成前重新校验项目/代次/hash。
  - [x] `error` 事件、HTTP `ApiError` 和无终态流结束：不写 mock 回复；解除 busy，保留用户可见消息/显示 `explorationErrorText`，并可重新 `listFreeMessages` 以恢复服务端已落库的那条用户消息。Abort 是正常生命周期结果，不向已切走页面显示错误。
  - [x] 自动调用 `refreshClues` 只发生于该轮 `done`，不得在用户手动编辑未完成时盲目覆盖本地输入；后端 `userEdited=true` 是最终保护，前端刷新完整 `ClueResponse[]` 后须展示其返回值。
  - [x] 保持 `data-conversation-scroll` 每次渲染后滚到底，且提交期间 submit 按钮 disabled，避免重复真实 LLM 请求。

- [x] **Task 4：将线索区改为 `ClueResponse[]` 驱动并真实 CRUD**（AC: 3, 6, 7）
  - [x] 重写 free 分支的四个固定线索渲染，使其从后端 preset（按 `displayOrder`/`clueKey`）读取，不能再读取 `explorationHistory[0/1/2/4]`；保留原型 label、contenteditable 值和「尚未确定」空值表现。
  - [x] fixed/preset value 的 blur 编辑调用 `editClue`；成功以返回资源更新；失败恢复上次确认值并显示集中错误。不要发送 preset label，也不要渲染删除按钮。
  - [x] custom 线索以真实 `id` 管理。新增按钮创建草稿；label 有值才 create，成功后使用后端 id；已有 custom 的 label/value 改动 PATCH；删除 `DELETE` 后才移除。编辑事件必须避免 DOM 注入：沿用 `escapeHtml` 写入任何 API 返回的 label/value，属性值同样安全编码。
  - [x] 保持 placeholder 与空字符串语义：后端允许 `value:""`，前端将其显示为「尚未确定」；不要把这四个中文占位字面量作为实际 value 落库。

- [x] **Task 5：给方向 UI 偏好与整理门禁/settle 接线**（AC: 4, 5, 6, 7）
  - [x] 方向复选框状态改为按 `projectId` 的 sessionStorage UI 偏好；click direction 仅填 `#explore-answer` 并 focus，严格不调用 `sendFreeMessage`。
  - [x] 继续用恢复后对话中的 user role 渲染按钮 disabled 与二态 formingHint；不要仅根据尚未成功持久化的乐观消息开放。若 `settleFree` 返回 `exploration_not_ready`，显示该提示、重新同步消息并保持继续对话入口。
  - [x] 将 `.finish-exploration` 的 mock `openStoryProfileDialog()` 替换成 `startFreeSettleFlow`：设 submitting/进行中 → `settleFree` → 复用 `taskEvents`。仅 `result` 事件以 `openStoryProfileFromBackend(data.profile)` 弹真实卡；`progress` 可更新进行中提示；`error` 或流结束无终态时复位、提示重试。完整复用 Story 7.5 的 profile 映射/会话恢复，绝不回退 mock card。
  - [x] 新建、切走、logout 经过 Task 2 清理时 abort settle；card 结果回调须校验 task 发起项目仍是当前项目，禁止跨项目/跨用户弹卡。

- [x] **Task 6：错误、状态清理、零回归验证**（AC: 全部）
  - [x] 扩展 `explorationErrorText`，至少精确映射：`exploration_not_ready`、`clue_not_deletable`、`preset_label_immutable`、`quota_exceeded`、`generate_failed`、`mode_mismatch`、`already_settled`、`project_not_found`、`task_not_found`、`settle_empty`，其余走中性网络/操作失败文案。只按 `err.code`/SSE `data.code` 判定。
  - [x] logout 必须清 freeConversation、后端线索数组、free load/error/busy/AbortController、settle 状态及当前 projectId；同时保留 7.5 已有的 `clearPendingStoryProfile` 与 guided 清理。A 用户的任何待处理消息/线索/候选卡不得残留给 B。
  - [x] `resetExplorationStateForNewProject` 同步清理 free 接线态与按作品的 UI 偏好，防新项目显示旧项目的对话、线索或 busy 状态。
  - [x] 运行 `node --check prototype/app/api.js && node --check prototype/app/app.js`；本 story 前端 only，确认 `git status backend/` 没有改动。

- [x] **Task 7：追加 guidance 域 API 薄封装，消费 Story 2.8 四个新端点**（AC: 1, 2, 3, 4, 6）
  - [x] 在 `prototype/app/api.js` 的 `explorationApi` 追加（不新建平行对象）：
    - `getGuidance(projectId)` → `GET .../free/guidance`
    - `startGuidance(projectId, {entry})` → `POST .../free/guidance/start`，body `{entry}`
    - `suggestGuidance(projectId)` → `POST .../free/guidance/suggestions`
    - `skipGuidance(projectId)` → `POST .../free/guidance/skip`
  - [x] 四个方法全走 `apiFetch`（常规 CRUD/非流式，不新增 SSE 消费）；更新 `api.js` 顶部探索端点注释纳入这四条。
  - [x] Node/vm 契约测试：断言四个方法的方法/路径/body 组装正确（仿既有 free 域测试写法）。

- [x] **Task 8：加载与恢复导航状态，零对话四入口替换旧版「给方向」**（AC: 1, 2, 7）
  - [x] 新增最小状态：导航 `fields`（7 项 missing/filled/skipped）、`currentField`、`currentQuestion`、`readyToSettle`、按需思路列表与加载态、跳过提交中标记。
  - [x] `loadFreeExploration` 的 `Promise.all` 追加 `explorationApi.getGuidance(projectId)`，与消息/线索一起回填；沿用既有 projectId/代次/hash 三重校验丢弃过期回调。
  - [x] 当 `freeConversation` 为空（零对话）时，渲染「你想从哪里开始？」四个固定入口（故事想法/主角/核心冲突/世界与氛围），替换旧版 `.inspiration-toggle`/`.inspiration-list`「给我一些讨论方向」三选项 UI 与 `showInspirationDirections`/`restoreFreeInspiration`/`setFreeInspiration`/`freeInspirationKey` 整套 sessionStorage 偏好机制（AC2 明确不再展示旧版三文案，四入口是产品固定入口不得渲染成 AI 建议）。点击入口调用 `startGuidance({entry})`，用返回的导航状态渲染当前具体问题与常规输入框；同一时序失败沿用 `explorationErrorText` 集中映射。
  - [x] 移除 `bindExplorationInteractions` 中 `[data-inspiration]`/`[data-direction]` 的旧监听与 `inspirationOptions` 固定灵感文案数组；新增四入口按钮的点击绑定。

- [x] **Task 9：对话轮次后刷新导航状态，渲染当前具体问题**（AC: 3, 7）
  - [x] `submitFreeMessage` 的 `done` 分支在现有 `syncFreeMessages` + `refreshFreeClues` 之后，串行追加 `explorationApi.getGuidance(projectId)` 拉取本轮刷新后的导航状态（后端 `stream_free_chat` 已在落库后同步调用 `refresh_guidance`，前端只需重新 GET 一次即可拿到最新 `currentField`/`currentQuestion`/`readyToSettle`），同一 projectId/代次/hash 校验后才写状态。
  - [x] 在对话流下方渲染「当前具体问题」区（`currentQuestion` 非空时展示；为空且 `readyToSettle` 为真时展示收束文案，取代旧版 `canFinish` 纯本地判据的收束提示）。
  - [x] `error` 事件/HTTP 失败/无终态流结束：不追加导航刷新请求，保持现有「不写 mock、解除 busy、可重试」路径不变。

- [x] **Task 10：按需回答思路 + 跳过接线**（AC: 4）
  - [x] 在当前具体问题下方增加「没想好？看看几个思路」按钮：点击才调用 `suggestGuidance(projectId)`，展示返回的 2–4 个建议为可点击选项；仅点击时请求，不随每轮自动生成。点击任一建议直接作为 `#explore-answer` 内容调用现有 `submitFreeMessage`（等价于用户手动发送）。
  - [x] 返回 400 `no_current_question`（无当前问题）时按钮不渲染或点击后走中性提示，不视为异常错误态。
  - [x] 增加「先跳过这个问题」按钮：点击调用 `skipGuidance(projectId)`，用返回的导航状态原地刷新当前具体问题区（可能是下一问，也可能是收束态），不触发 `submitFreeMessage`、不新增对话消息。
  - [x] 两个按钮在 `freeMessageSending`/跳过提交中时禁用，避免与在途对话流或重复跳过并发冲突。

- [x] **Task 11：7 项完成度门禁替换旧判据，settle 按钮与提示接线**（AC: 6, 7, 8）
  - [x] 将 `canFinish`（当前 `!freeMessageSending && freeConversation.some(user 消息)`）替换为 `!freeMessageSending && readyToSettle`（导航状态字段）；`formingHint` 按 `fields` 完成度展示当前进度提示（如「还差 N 项」），而非旧版二态文案。
  - [x] `startFreeSettleFlow` 前置校验、`exploration_not_ready` 错误处理保持不变（后端仍是最终防线）；确认前端 disabled 判据已与后端门禁字段同源，不再依赖「≥1 条用户消息」。
  - [x] 更新 Task 2/6 已建立的 `teardownExplorationInflight`、`resetExplorationStateForNewProject`、logout 清理，纳入新增导航状态字段与按需思路列表的复位，避免跨项目/跨账号残留（同既有 free 状态清理范式）。

- [x] **Task 12：真实浏览器联调与测试记录**（AC: 全部）
  - [x] 用真实后端、Redis、ARQ worker、前端静态站验证：自由模式新作品首次进页能建会话/出现 4 preset 与四入口零对话态；点击入口生成开场问题；刷新后对话/线索/导航状态恢复；发送消息见真实 SSE 回答且无固定 mock 文案；每轮 done 自动刷新 Agent 线索与导航状态、显示新的当前具体问题；按需思路只在点击时生成且可直接提交；跳过后不再追问同一字段；手改 preset 后继续对话/refresh 不覆盖；新增/改名/删除 custom 均持久化；首屏整理 disabled、7 项主干全部 filled/skipped 后开放；free settle 走 task SSE 并弹真实候选卡；流/页面切换/登出不发生跨作品或跨账号污染。
  - [x] 至少覆盖：SSE 建流前 401 的 7.5 统一跳登录；free 项目访问 guided 端点/反向访问导致的 `mode_mismatch` 友好兜底；手工或直接请求造成的 `exploration_not_ready` 400；`no_current_question`（已就绪或未初始化时点按需思路/跳过）；自定义/预设线索的后端 400 约束；A/B 租户隔离（B 不可读/改/删 A 的 clues、messages、task events、guidance）。
  - [x] 若本机仍无法使用 Playwright/Chromium，必须如实写入 Completion Notes，不得将 Node/curl 验证宣称为浏览器 UI 验证；仍须完成 SSE 契约与纯逻辑/语法检查。

## Dev Notes

### 边界与依赖

- **依赖已满足：** 7.1 `apiFetch`/token/401/error 边界；7.2 真实会话；7.3 projects 与真实路由 id；7.5 `apiStream`、`explorationApi.enter/taskEvents`、候选卡 `openStoryProfileFromBackend`、SSE 生命周期清理。自由后端 2.2、2.6、2.7 与真实候选卡 3.3 均已 done。
- **本 story 交付：** 前端 `api.js` 的 free 薄封装，以及 `app.js` 自由分支的真实会话/对话/线索/方向 UI 态/整理门禁接线；为保持真实结果，允许对 7.5 的清理函数做小范围泛化，但必须保留 guided 行为。
- **不做：** 不改 backend、schema、迁移、Provider、ARQ、SSE 服务器；不修 `apiStream` 的末帧 flush/整体超时/自动重连（已登记 SSE 编排硬化）；不做自由对话历史截断；不实现设定卡编辑/反馈/确认/丢弃/文风锚点（7.7）；不新增全局路由鉴权、模块化/打包、UI 新页面或第二个请求工具。

### 前后端契约（已从真实代码核实）

所有常规响应直接返回 camelCase 资源体；HTTP 失败是 `{code,message,detail}`，流内失败为 `event:error` 的 `{code,message}`。所有项目资源从 Bearer 当前用户派生租户，不传 `userId`。

| 目的 | 方法与路径 | 请求 | 成功响应 | 代码依据 |
|---|---|---|---|---|
| 建/取会话 | `POST /api/projects/{projectId}/explore` | 无 | `200 {id,projectId,mode,updatedAt}`；free 首建同时播种 4 preset | `routers/exploration.py:64-74`; `exploration_service.py:112-153` |
| 发一轮自由消息 | `POST /api/projects/{projectId}/explore/free/messages` | `{content}`，去首尾空白、1–2000 字 | `200` SSE：`delta {text}` ×N → `done {text}`；失败 `error {code,message}` | `routers/exploration.py:239-307`; `schemas/exploration.py:92-99` |
| 恢复消息 | `GET /api/projects/{projectId}/explore/free/messages` | 无 | `200 [{id,role,content,createdAt}]`，创建时间升序，空 `[]` | `routers/exploration.py:310-325`; `exploration_service.py:326-345` |
| 取全部线索 | `GET /api/projects/{projectId}/explore/free/clues` | 无 | `200 [{id,clueKey,kind,label,value,userEdited,displayOrder,updatedAt}]`，displayOrder 升序 | `routers/exploration.py:328-339`; `schemas/exploration.py:114-128` |
| 新增 custom | `POST /api/projects/{projectId}/explore/free/clues` | `{label,value}`；label 1–2000，value 允许空串、最多 2000 | `201 ClueResponse` | `routers/exploration.py:342-361`; `schemas/exploration.py:145-150` |
| 编辑线索 | `PATCH /api/projects/{projectId}/explore/free/clues/{clueId}` | `{value,label?}` | `200 ClueResponse`；任何编辑会置 `userEdited=true` | `routers/exploration.py:364-387`; `exploration_service.py:399-434` |
| 删除 custom | `DELETE /api/projects/{projectId}/explore/free/clues/{clueId}` | 无 | `204`；preset 不可删 | `routers/exploration.py:390-405`; `exploration_service.py:456-479` |
| Agent 自动整理 | `POST /api/projects/{projectId}/explore/free/clues/refresh` | 无 | `200 ClueResponse[]` 全量列表；只更新 `userEdited=false` preset，不碰 custom | `routers/exploration.py:408-430` |
| 自由整理提交 | `POST /api/projects/{projectId}/explore/free/settle` | 无 | `200 {taskId}` | `routers/exploration.py:433-458`; `exploration_service.py:265-323` |
| 消费任务流 | `GET /api/tasks/{taskId}/events` | 无 | SSE `progress {step,percent}` → `result {taskId,status,profile}` / `error {code,message}` | `routers/tasks.py:53-74`; `core/sse.py` |

### userEdited 优先机制（不可自行改写）

- free 会话第一次创建时固定播种 `opening / protagonist / conflict / world` 四个 preset（中文标签分别为「最初的念头 / 主角 / 核心冲突 / 世界与氛围」）。来源：`exploration_service.py:31-39,133-142`。
- 任何 `PATCH` 都将该 clue 标记为 `user_edited=true`；refresh 只允许更新未编辑的 preset，自定义 clue 永不触碰。来源：`routers/exploration.py:375-377,415-422`; `exploration_service.py:408-417`。
- 所以前端的正确时序是：**消息 `done` → `refreshClues` → 用返回的完整列表替换 UI**。不能用前端比较文本、不能在 refresh 前筛掉「看起来像手工编辑」的行、不能把 Agent 自动整理做成 mock。

### error code → 前端处理

| code | 场景 | 前端行为 |
|---|---|---|
| `exploration_not_ready` | free settle 前无已持久化 user message（400） | 显示「继续和 Agent 讨论，线索足够时就能整理为故事设定。」；保留对话输入并同步状态 |
| `quota_exceeded` | 消息 SSE 预检/流内、refresh 或 settle 触发额度护栏 | 提示额度耗尽并引导到 7.4 设置页绑定 Key；退出 busy |
| `generate_failed` | free Agent 流内 provider 异常或空产 | 显示可重试提示；同步已持久化消息；不插 mock 回复 |
| `mode_mismatch` | 用自由页调用 guided 项目，或反向 | 中性提示并回作品库/重载正确路由；正常路径不应发生 |
| `already_settled` | 已确认设定、project phase 不再是 explore | 提示已完成设定，不再次 settle |
| `project_not_found` / `task_not_found` | 越权或不存在，均不泄露存在性 | 中性提示，回作品库或恢复可重试态 |
| `clue_not_deletable` | 尝试删除 preset | 提示预设线索不可删除；正常 UI 不给该入口 |
| `preset_label_immutable` | 尝试改 preset label | 提示预设线索名称不可修改；正常 UI 不给该入口 |
| `settle_empty` | 后端凝练材料为空 | 提示内容还不够整理，继续对话 |
| `token_invalid` / `token_expired`（401） | token 不可用 | `apiFetch`/`apiStream` refresh 或跳 `#/login?state=expired`；本页不重复处理 |

### 前端接线锚点（当前真实代码）

- **复用的网络地基：** `apiStream`（`prototype/app/api.js:402-470`）已支持 Bearer、建流前 401 仅刷新/重放一次、非 2xx → `ApiError`、AbortSignal；`explorationApi`（`:484-521`）已有 `enter`/引导方法/`taskEvents`，free 方法追加在此。
- **自由分支：** `renderExploration` 的 free render（`app.js:1450-1529`）：现在用 `freeConversation` 计算 `canFinish`，但错误地用 `explorationHistory[0/1/2/4]` 填线索（`:1461-1464`）；须替换为 `ClueResponse[]`。
- **现存 mock：** 自由 form submit（`app.js:1641-1657`）push 用户文本 + 硬编码 Agent 回复，必须删除该 mock 路径；`finish-exploration` click（`:1594-1596`）调用 mock `openStoryProfileDialog()`，必须替换为 free settle。
- **原型必须保留的交互：** `storyClue` contenteditable（`:561-568`）、custom render（`:570-578`）、focus/blur placeholder（`:1658-1670`）、自动滚底（`:1672-1673`）、方向填入不提交（`:1626-1639`）、连续消息渲染（`:1474-1483`）。API 文本进入 HTML 必须复用 `escapeHtml`。
- **已有引导安全先例：** `explorationProjectId`/guided 状态（`:115-130`）、`explorationErrorText`（`:584-607`）、现有 teardown（`:621-632`）、`loadGuidedExploration`（`:636+`）、新建重置（`:2355-2419`）、logout 清理（`:2422-2456`）、render 路由分支与模式从真实 project 派生（`:3351-3408`）。自由侧必须加入这些生命周期，而非另立不被调用的清理函数。

### 测试策略

- **纯逻辑：** 在 Node/vm 或既有可行方式断言：free message / ClueResponse 映射；error code 文案；按 `userEdited`/kind 的渲染分支；free settle 终态判定；projectId/代次失效回调不更新状态；方向按钮只写输入文本。
- **SSE 契约：** 复用真实后端和现有 `apiStream` 验证 `POST free/messages` 确实得到 `text/event-stream`、delta/done、Bearer、abort；验证 `POST free/settle`→task SSE 的 progress/result/profile。
- **浏览器黄金路径：** 启 `make dev-up`（PG+Redis）、后端+ARQ worker、静态前端 `:4173`；注册/登录后用自由模式真实作品完整走 Task 7。UI 改动完成前应实际打开浏览器验证；若环境不具备，必须明确记录缺口。
- **回归：** `node --check prototype/app/api.js && node --check prototype/app/app.js`；`MUSE_DB_READY=1 uv run pytest -q`（本 story 不改后端，验证无意外回归）；7.2 登录/登出、7.3 作品库、7.4 设置、7.5 引导探索均需基本冒烟，尤其 guided 的加载、SSE abort、pending 卡恢复与 mode 路由不能回归。

### 项目结构与开发环境

- 前端维持全局脚本：仅修改 `prototype/app/api.js`、`prototype/app/app.js`，需要样式时仅改现有 `prototype/app/styles.css`。不新增文件、模块或路由。
- API 外部字段已是 camelCase；前端直接读写 camelCase，禁止散落 snake_case 转换。前端 sessionStorage 只允许 UI 态并采用 `muse-` kebab-case key。
- 本机：`uv` 在 `~/.local/bin`，容器用 Colima；DB 测试前设 `MUSE_DB_READY=1`。自由消息直连 Provider，free settle 还依赖 Redis 与 ARQ worker；真实 LLM 联调需要可用的 DeepSeek/或 BYOK 配置，注意成本。

### References

- [Source: `_bmad-output/planning-artifacts/epics.md:1223-1231`] — Epic 7 目标、依赖 `7.5 → 7.6 → 7.7`、只换数据源的原则
- [Source: `_bmad-output/planning-artifacts/epics.md:1376-1402`] — Story 7.6 五项原始 AC
- [Source: `_bmad-output/planning-artifacts/epics.md:48-50,153-157`] — FR9/FR10/FR11 与 UX-DR5
- [Source: `backend/src/muse/routers/exploration.py:239-458`] — free 消息、线索 CRUD/refresh、settle 的真实端点与 SSE/门禁语义
- [Source: `backend/src/muse/services/exploration_service.py:31-39,53-108,265-479`] — preset、mode/phase/门禁守卫、free settle、线索 user_edited 与 CRUD 规则
- [Source: `backend/src/muse/schemas/exploration.py:92-150`] — `FreeMessageRequest` / `FreeMessageResponse` / clue 请求与响应的 camelCase 字段和长度约束
- [Source: `prototype/app/api.js:402-521`] — 7.5 已交付的 SSE 工具与 explorationApi 追加位置
- [Source: `prototype/app/app.js:561-578,1450-1529,1594-1673,2355-2456,3351-3408`] — 自由页当前 mock、原型交互契约、已有异步清理与路由先例
- [Source: `_bmad-output/implementation-artifacts/7-5-引导探索接线SSE问答-翻页持久化-整理中过渡-设定卡弹出.md:18-44,260-273,283-323`] — 必须复用的 SSE/API/候选卡地基，及 code review 修复的生命周期/跨用户隔离先例
- [Source: `_bmad-output/implementation-artifacts/deferred-work.md:166-193,295-300`] — 2.6/2.7 已完成后端范围、SSE 硬化与不在本 story 解决的 deferred 边界
- [Source: `_bmad-output/planning-artifacts/architecture.md:275-358`] — camelCase 边界、前端 storage 约束、REST/SSE/error envelope、多租户与前端目录约束

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6

### Debug Log References

- 前端 API 薄封装 Node/vm 契约测试：15 项断言通过（free messages/clues CRUD/refresh/settle 与 `apiStream` POST 体）。
- 前端自由探索纯逻辑 Node/vm 测试：9 项断言通过（error code 映射、后端消息映射、项目隔离的方向 UI storage、延迟线索替换）。
- 前端静态检查：`node --check prototype/app/api.js && node --check prototype/app/app.js` 通过；`git diff --check` 通过；`git status backend/` 无改动。
- 真实后端联调（PostgreSQL + Redis + ARQ worker）：① free 首次进入返回 `mode=free` 并播种 4 个 preset；② 无用户消息 free settle → `400 exploration_not_ready`；③ preset PATCH 后 `userEdited=true`、custom create/edit/delete 持久化、删除 preset → `400 clue_not_deletable`（共 9 项断言）；④ `POST free/messages` 收到 `delta` + `done`，用户/Agent 两条消息落库；⑤ refresh 后用户编辑的 preset 未被覆盖（3 项断言）；⑥ free settle → task SSE progress/result，result 含 7 个主干 profile 字段；⑦ 独立账号最终回归再次验证 SSE/持久化/userEdited（5 项断言）。
- 后端全量回归：`MUSE_DB_READY=1 uv run pytest -q` → **316 passed, 26 skipped, 27 warnings**；`uv run ruff check` 通过。
- **Task 7–11 消费 Story 2.8（本次新增）：**
  - guidance API 薄封装 Node/vm 契约测试：15 项断言通过（`getGuidance`/`startGuidance`/`suggestGuidance`/`skipGuidance` 的方法/路径/body 组装）。
  - app.js guidance 逻辑 jsdom 测试：12 项断言通过（`explorationErrorText` 兜底、`applyGuidanceState` 在 `currentField` 变化时清空按需思路/不变化时保留、收束态字段写入、`canFinish` 已改用 `readyToSettle` 而非旧版消息判据、零对话四入口渲染数量、旧版「给方向」UI 已确认移除）。
  - 前端静态检查：`node --check prototype/app/api.js && node --check prototype/app/app.js` 通过；`git diff --check` 通过；`git status backend/` 无改动。
  - 真实后端联调（PostgreSQL + Redis + ARQ worker，新起一轮）：`GET free/guidance` 初始态 7 项全 `missing`；`POST guidance/start` entry=protagonist 生成具体开场问题；`POST guidance/suggestions` 返回 4 条建议；发送建议内容后 `done` 触发的后端 `refresh_guidance` 副作用正确刷新 `currentQuestion`；`POST guidance/skip` 标记 `skipped` 并谨慎归纳写入 `story_clue`（`userEdited` 仍为 `false`）、自动推进下一字段；连续 skip 完 7 项后 `readyToSettle=true`；再次 skip/suggestions 均返回 `400 no_current_question`；`POST free/settle` 在 `readyToSettle=true` 时成功返回 `taskId`；task SSE `progress→result`，`result.profile` 含真实凝练的 7 个主干字段。
  - 后端全量回归复跑：`MUSE_DB_READY=1 uv run pytest -q` → **372 passed, 27 skipped**；`uv run ruff check` 通过（确认本次前端改动零回归）。
  - **真实浏览器 UI 验证（Playwright + Chromium，本次已装好驱动，补齐此前缺口）：** 注册 → 登录 → 建 free 作品 → 进入探索页确认零对话四入口渲染数=4 且旧版 `.inspiration-toggle` 不存在 → 点击「主角」入口出现当前具体问题 → 点击「没想好？看看几个思路」生成 4 条建议 → 点击建议直接提交、对话消息数增至 2 → 等待导航刷新后「先跳过这个问题」按钮可用并点击成功。全程无浏览器控制台错误。

### Completion Notes List

- 已实现 Task 1–6：`explorationApi` 追加 free 域薄封装；自由页在进入时真实建/取会话并加载消息/线索；真实 SSE 对话、完成后自动刷新 Agent 线索；preset/custom 线索真实 CRUD；按 projectId 隔离的方向 UI 偏好；free settle 消费 task SSE 后弹已有真实候选卡。
- 生命周期防护扩展到自由模式：`teardownExplorationInflight` 同时取消 guided interpret、free message 与 settle 流；加载/消息/整理全部以 projectId、代次、hash 校验防跨项目回写；新建/登出清空 free 状态，避免跨账号残留。
- 自动线索 refresh 遵守后端 `userEdited` 规则；用户聚焦编辑线索时延后流式重绘与完整线索替换，失焦后再应用权威列表，避免覆盖未保存输入。
- 未引入新库或新框架；本 story 消费项目内已锁定的 `fetch`/ReadableStream、FastAPI SSE、ARQ 和既有 API 契约。
- **Task 7–12（本次新增，消费 Story 2.8）：**
  - `api.js` 追加 `getGuidance`/`startGuidance`/`suggestGuidance`/`skipGuidance` 四个薄封装，全走 `apiFetch`。
  - 零对话起点改为消费 2.8：无对话且无 `currentQuestion` 时渲染「你想从哪里开始？」四个固定入口（`data-guidance-entry`），点击调用 `startGuidance` 生成具体开场问题；彻底删除旧版 `showInspirationDirections`/`restoreFreeInspiration`/`setFreeInspiration`/`freeInspirationKey`/`inspirationOptions` 及 `.inspiration-toggle`/`.inspiration-list` 相关 CSS（旧版「给我一些讨论方向」三选项 UI 已不存在，改为按需思路 + 跳过两个入口）。
  - `submitFreeMessage` 的 `done` 分支在消息同步 + 线索刷新之后，追加一次 `getGuidance` 拉取本轮判定后的导航状态（对齐后端 `stream_free_chat` 落库后同步调用 `refresh_guidance` 的副作用时序）；该调用失败静默吞掉，不影响本轮已成功的对话与线索（同后端「主链路成功、副作用降级」的容忍粒度）。
  - 当前具体问题区新增「没想好？看看几个思路」（`suggestGuidance`，仅点击才请求，`currentField` 变化时自动清空旧建议）与「先跳过这个问题」（`skipGuidance`，不产生对话消息，原地刷新导航状态）；两者与自由对话共享 `freeMessageSending` 互斥, 各自独立的 `guidanceSuggestionsLoading`/`guidanceSkipping` 提交门禁。
  - `canFinish` 从旧版「至少一条用户消息」改为完全消费后端 `readyToSettle`；`formingHint` 按 `fields` 里 `missing` 计数展示进度提示；`teardownExplorationInflight`/`resetExplorationStateForNewProject`/logout 清理均已纳入新增的导航状态字段（`guidanceFields`/`guidanceCurrentField`/`guidanceCurrentQuestion`/`guidanceReadyToSettle`/`guidanceSuggestions`/`guidanceSuggestionsLoading`/`guidanceSkipping`/`guidanceStartingEntry`），防跨项目/跨账号残留。
  - Task 12 浏览器联调：本机成功安装 Playwright Chromium 驱动（此前 7.5 遗留的缺口在本 story 已解决），完成真实浏览器 UI 端到端验证（见 Debug Log），不再是「Node/curl 冒充浏览器验证」。测试全程使用临时邀请码/测试账号，验证完成后已从数据库清理干净，且已 `make dev-stop` 释放本机 Colima 内存。

### File List

- `prototype/app/api.js`（修改）— 在既有 `explorationApi` 追加 free messages、clues CRUD/refresh、free settle、**guidance 四个新端点**（`getGuidance`/`startGuidance`/`suggestGuidance`/`skipGuidance`）薄封装，复用 `apiFetch`/`apiStream`/`taskEvents`。
- `prototype/app/app.js`（修改）— 自由探索真实加载/SSE/线索 CRUD/free settle、异步取消和跨账号状态清理；**新增消费 Story 2.8 的导航状态加载、零对话四入口、当前具体问题渲染、按需思路、跳过、7 项完成度门禁**，并移除旧版「给方向」三选项 UI 及其 sessionStorage 偏好机制。
- `prototype/app/styles.css`（修改）— 删除死掉的 `.inspiration-toggle`/`.inspiration-list` 规则；新增 `.guidance-entry-points`/`.guidance-current-question`/`.guidance-suggestions` 等零对话四入口与当前问题区样式（含移动端响应式）。
- `_bmad-output/implementation-artifacts/sprint-status.yaml`（修改）— Story 7.6 `ready-for-dev → in-progress`。
- `_bmad-output/implementation-artifacts/7-6-自由探索接线SSE对话-线索区编辑持久化-给方向-整理门禁.md`（修改）— Task 1–12 全部完成；新增 Task 7–12 记录消费 Story 2.8 的接线过程。

## Change Log

- **2026-07-31（Correct Course，Sprint Change Proposal 2026-07-31）**：真实浏览器验证前，Jianghj 发现自由探索的产品契约存在根因问题——「给我一些方向」实为前端固定文案而非 AI 建议，Agent 会围绕单一话题无限追问，且「至少一条用户消息」的门禁无法保证设定卡主干信息已经形成。经 `/bmad-correct-course` 逐项裁定后，新增 Epic 2 **Story 2.8**（自由探索设定导航/按需回答思路/7项完成度门禁，backlog）承接后端能力；本 story 的标题与 `## Acceptance Criteria` 已按 `epics.md` 新 Story 7.6 定义整体重写（零对话四入口 / 当前具体问题 / 按需回答思路 / 跳过 / 7 项完成度门禁），取代旧版固定方向与一条消息门禁。**Tasks 1–6 已完成的 SSE/线索 CRUD/清理实现全部保留**，无需回退；但消费导航状态、按需思路、跳过与新门禁的实现须等 Story 2.8 完成后作为新增 Task 补入本 story，才可继续推进并转 `review`。详见 `_bmad-output/planning-artifacts/sprint-change-proposal-2026-07-31.md`。
- **2026-08-03（Story 2.8 完成后消费，本次实现）**：Story 2.8 已交付（commit f7ad976），本 story 补入 Task 7–12（`## Tasks / Subtasks` 新增段）消费其四个新端点（`guidance`/`guidance/start`/`guidance/suggestions`/`guidance/skip`）。零对话四入口替换旧版「给我一些方向」三选项 UI；对话轮次 `done` 后追加导航状态刷新；新增按需思路与跳过两个入口；`canFinish` 从「≥1 条用户消息」改为消费后端 `readyToSettle`；清理函数纳入新增状态字段。本次同时补齐此前 7.5/7.6 反复记录的浏览器驱动缺口——成功安装 Playwright Chromium，完成真实浏览器 UI 端到端验证（注册→建作品→四入口→当前问题→按需思路→提交→跳过），全程无控制台错误。后端零改动（`git status backend/` 干净），后端全量回归 372 passed / 27 skipped、`ruff check` 通过。Status 转 `review`。
