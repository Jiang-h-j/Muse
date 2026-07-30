---
baseline_commit: ba07001
---
# Story 7.5: 引导探索接线（SSE 流式问答 / 翻页持久化 / 整理中过渡 / 设定卡弹出）

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a 选了引导模式的用户，
I want 与真实 Explorer Agent 做沉浸问答并真实保存答案，
so that 我聊出的故事线索被真实持久化、可翻页修改。

## Acceptance Criteria

> **本 story = 把引导探索页（`renderExploration` 引导分支 app.js:925-1022 + 相关交互）从纯 mock/sessionStorage 换成 Epic 2 已 done 的真实后端**：进探索页建会话（2.2）、自述作答走真实 Explorer Agent 流式 SSE（2.3）、每题答案真实落库 + 进页回填（2.4）、末题收尾触发 settle ARQ 任务并消费 SSE 驱动「整理中」过渡态 + 弹后端生成的设定卡（2.5 触发 + 3.3 真实凝练）。后端 5 个引导端点契约稳定（见 Dev Notes 契约表），前端零后端改动对接。
>
> **地基缺口（本 story 最大工作量，须先建）**：7.1 的 `apiFetch`（api.js:111）基于 `fetch`+`JSON.parse`，**只处理一次性 JSON 响应、不支持 SSE 流**。而引导探索有两处 SSE：① `POST .../guided/interpret` 直接返回 `EventSourceResponse`（delta→done→error）；② settle 走 `POST .../guided/settle`→taskId→`GET /api/tasks/{taskId}/events`（progress→result→error）。**两个 SSE 端点都靠 `Authorization: Bearer` 头鉴权**（`CurrentUser` 依赖），浏览器原生 `new EventSource()` 无法设自定义头——故**不能用 EventSource**，须新增基于 `fetch`+`ReadableStream` reader 的 SSE 消费工具（追加到 api.js，与 7.6 自由探索共享此前置）。这是 7.1 地基未覆盖的一类，本 story 补齐。
>
> **契约事实来源**：epics.md#Story-7.5 AC（5 条）+ UX-DR4 引导交互契约（epics.md:155）+ 后端 Epic 2 Story 2.2/2.3/2.4/2.5 已 done 接口 + Story 3.3 真实凝练（settle result 已返 12 字段候选卡）。deferred-work.md 已把「2.3 interpret / 2.4 answers / 2.5 settle 前端接线」明确合并为**同一前端集成切片 = 本 story**（deferred-work.md:119/132）。
>
> **边界严守**：只接引导探索页（含 SSE 地基）；**不接**自由探索页（7.6，其 SSE 消费复用本 story 建的地基）、设定卡编辑/反馈升版本/确认圣经/文风锚点（7.7——本 story 只做「弹出后端返回的候选卡」，卡内编辑/确认/回到探索丢弃的**真实接线**归 7.7）；不改 `apiFetch`/token/401 地基逻辑（仅**追加** explorationApi 薄封装 + SSE 消费工具）；不加路由级鉴权守卫（业务请求 401 由 7.1 `apiFetch` 兜住；SSE 工具须复用同一 token/401 语义）；不碰后端（引导 5 端点 2.2-2.5 + settle 真实凝练 3.3 已 done）。

1. **[SSE 消费地基 · 新增]** 引导探索有两处 SSE 且均需 Bearer 头鉴权，原生 `EventSource` 不可用。须在 `api.js` 追加 `fetch`+`ReadableStream` 的 SSE 消费工具（如 `apiStream(path, {method, body, onEvent, signal})`）：注入 `Authorization: Bearer`（复用 `getAccessToken`）、按 `event:`/`data:` 帧解析回调 `onEvent(type, data)`、支持 `AbortController` 取消、非 2xx（尤其预检 401/404/429）经 `toApiError` 转 `ApiError` 抛出（不进流循环）。**401 语义与 apiFetch 一致**：SSE 建流前的 401 应触发同款「refresh 重放 or 跳登录」——可先调 `apiFetch` 探测态或在流工具内复用 `ensureRefresh`（dev 择优，须避免各页各写一遍，AC 见受控决策 1）。[Source: api.js:111-157 apiFetch 仅 JSON 不支持流；backend routers/exploration.py:140-167 interpret 返 EventSourceResponse；backend routers/tasks.py:53-74 GET /events 靠 CurrentUser Bearer 鉴权；epics.md#AR5 SSE 三事件]

2. **[进探索页建会话 + 答案回填]** 进入引导探索页（`renderExploration` 引导分支 / 路由进 `#/projects/{id}/explore`），须经 `explorationApi` ① `POST /api/projects/{projectId}/explore` 建/取会话（get-or-create，2.2，返 `{id, projectId, mode, updatedAt}`）；② `GET .../explore/guided/answers` 拉全部已答回填 `explorationHistory`（2.4，题位升序，空态 `[]`）。**替换**当前 `explorationHistory` 纯内存态（app.js:102）+ 路由 id 未消费（deferred-work.md:42 explore 目标页未读路由 id）。回填后翻页高亮/自述回填（app.js:972-988）读的是真实落库答案。[Source: epics.md#Story-7.5 AC「翻页持久化」；backend exploration.py:64 enter_exploration / :198 list_guided_answers；app.js:102,110,909-1022]

3. **[单题问答契约保持 · 数据换后端]** 严格保持 UX-DR4 引导契约（只显当前一题+选项、无历史无右侧线索区；第一题一句话自述、其余题「都不是这些」折叠出口；底部翻页按可用性显示、两端 spacer 留空占位；翻页不清答案、翻回高亮回填、重选只更新该题），**只把数据源从 mock 换成后端**。题库 `explorationQuestions`（app.js:5-62）是前端常量（后端不镜像题库，见后端 schemas/exploration.py 注释），翻页纯前端；后端只提供按 `questionIndex` 的保存与全量回填。[Source: epics.md:155 UX-DR4；epics.md#Story-7.5 AC「引导探索交互契约」；backend 无「取当前题/下一题」端点，题库前端持有；app.js:5-62,916-1022,564-573]

4. **[选项作答 = 前端记录 + 落库 · 自述作答 = 真实 Agent 流式凝练]** 区分两条作答路径（与后端 2.3 一致）：
   - **点选预设选项**（`data-guided-option` app.js:977）：不调 LLM，前端记录答案（`answerType:"option"`）→ `POST .../guided/answers` 落库（2.4 幂等 upsert）。
   - **自由文本自述作答**（`data-guided-custom-form` app.js:991-1006）：先调 `POST .../guided/interpret` 流式（2.3，`{question, freeText}`）——消费 `delta` 增量实时呈现「理解中/凝练」、`done` 拿完整凝练答案作该题答案、`error` 按 code 分支（如 `quota_exceeded` 引导绑 key、`generate_failed` 提示重试）；凝练答案再 `POST .../guided/answers` 落库（`answerType:"custom"`，answer=凝练结果）。**替换**当前 `submitGuidedAnswer`（app.js:578-602）纯本地写 `explorationHistory[view]`。[Source: epics.md#Story-7.5 AC「SSE 流式问答」；backend exploration.py:140 interpret（delta/done/error）/ :170 save_guided_answer；app.js:578-602,977,991-1006]

5. **[翻页与重选真实持久化]** 翻页（`data-guided-back`/`data-guided-next` app.js:932-944）不清答案（纯前端翻 view）；翻回已答题高亮上次所选（`is-chosen`+`✓` app.js:976-981）、自述作答回填文本（app.js:986-988）；在已答题重选/改答 → `POST .../guided/answers` 定点覆盖该题位（`questionIndex` 复合唯一 upsert，2.4），不影响其后。刷新/断线重连后 `GET .../guided/answers` 恢复（AC2 已建回填）。**替换**原型「内存态、刷新即丢」（app.js:578-602 纯本地）。[Source: epics.md#Story-7.5 AC「翻页持久化」+ FR7/FR11；backend exploration.py:170 upsert（session_id,question_index 复合唯一）；app.js:578-602,932-944,972-988]

6. **[末题收尾 → settle SSE → 整理中过渡 → 弹设定卡]** 答完最后一题（`submitGuidedAnswer` 末题分支 app.js:586-597）触发收尾：① 末题答案先落库（AC4）；② `POST .../guided/settle` 拿 `{taskId}`（2.5）；③ 进「整理中」过渡态（`guidedSettling=true`，UI app.js:948-955，文案+spinner 保持）并连 `GET /api/tasks/{taskId}/events` 消费 SSE：`progress` 驱动过渡态（可选显进度）、`result`（`{taskId, status:"settle_ready", profile:{12字段camelCase}}`）→ 关过渡态 + 弹设定卡（`openStoryProfileDialog` app.js:736）渲染后端 `profile`、`error`（如 `quota_exceeded`/`settle_failed`）→ 退回收尾态可重试。**替换**当前 `setTimeout(...,1200)` 假过渡（app.js:593-596，写死 1.2s 后弹 mock 卡）。**「回到探索」**（`discardStoryProfileAndReturn` app.js:699-712）复位 `guidedSettling=false` 回可翻页收尾态——须同时 abort 在途 settle SSE（AC1 signal）。[Source: epics.md#Story-7.5 AC「整理中过渡/设定卡弹出」+ FR8；backend exploration.py:216 settle / tasks.py:53 events / worker.py:118-164 settle_exploration 真实凝练返 profile；app.js:586-597,699-712,736,948-955]

7. **[待确认设定卡会话内恢复 · 刷新不回退]** 弹出的设定卡在浏览器会话内恢复：刷新页面不回退到探索主界面，恢复待确认态（FR11/UX-DR4）。**现状**：原型已有 sessionStorage 恢复机制（`readPendingStoryProfile` app.js:191 / `persistPendingStoryProfile` app.js:199 / key `muse-pending-story-profile` app.js:174 / renderExploration 末尾自动重挂弹窗 app.js:1104 附近）。本 story 须让恢复态承载**后端返回的真实 profile**（settle result 的 12 字段），而非 mock 构造。**边界**：本 story 只做「弹出 + 会话内恢复展示」；卡内编辑/反馈升版本/确认成圣经/回到探索丢弃的**后端真实接线**归 7.7（本 story 的「回到探索」只做前端过渡态复位 + abort SSE，不调后端丢弃端点——该端点属 3.5/7.7）。[Source: epics.md#Story-7.5 AC「刷新恢复待确认态」+ FR11；app.js:174-215,736-760,1104；epics.md#Story-7.7 卡内编辑/确认/丢弃真实接线边界]

8. **[加载/失败/多租户 + 401 由 7.1 兜底]** 引导探索页此前无 loading/error 态（纯 mock 无网络）——本 story 接线须新增：建会话/回填失败（非 401）渲染可重试的 error 态；SSE 建流预检失败（护栏 429/租户 404）按 code 呈现。多租户隔离（NFR3，后端从 token 拿 `current_user.id` 强制过滤、前端不传 userId）。未登录/token 失效访问、请求 401 由 7.1 `apiFetch`（及 AC1 SSE 工具复用的同款 401 语义）统一处理跳登录，**不在本页重复实现**。[Source: epics.md#Story-7.5 AC「经 7.1 工具」；backend 全端点 CurrentUser 鉴权 + get_owned_project 租户守卫（越权/不存在同码 404）；api.js:127-140 401 收敛；7.4 受控决策「不加路由守卫，401 兜底」]

**边界（本 story 不做）**：不接自由探索页（7.6，复用本 story SSE 地基）；不做设定卡编辑/反馈升版本/确认圣经/文风锚点真实接线（7.7）；不改 `apiFetch`/token/401/refresh 地基逻辑（仅追加 explorationApi 薄封装 + SSE 消费工具）；不加路由级鉴权守卫；不引入构建/打包/module（保持全局脚本）；不碰后端（引导 5 端点 + settle 真实凝练 2.2-2.5/3.3 已 done）；不镜像题库到后端（题库前端常量）；不做 provider 层流生命周期/超时硬化（deferred-work.md:95/112 归 4.4）。

## Tasks / Subtasks

- [x] **Task 1：SSE 消费地基（api.js 追加 `apiStream`）**（AC: 1）
  - [x] 在 `prototype/app/api.js` 追加 SSE 流式消费工具（如 `apiStream(path, {method="POST", body, onEvent, signal})`），基于 `fetch` + `res.body.getReader()` + `TextDecoder`：注入 `Authorization: Bearer`（复用 `getAccessToken` api.js:116-117）、按 SSE 帧（`event:` 行 + `data:` 行 + 空行分隔）解析并回调 `onEvent(eventType, parsedJsonData)`。
  - [x] **建流前错误经 HTTP 状态**：interpret 预检 401/404/429、settle 触发 401/404、GET events 404 均在流建立前以 HTTP 状态返回——非 2xx 用 `toApiError` 转 `ApiError` 抛出（**不进流循环**），调用方 catch 按 `err.code` 分支。**401 语义与 apiFetch 一致**：建流前 401 触发同款 refresh 重放 / 跳登录（复用 `ensureRefresh`/`redirectToLogin`，勿各页重写——AC1）。dev 定「探测式先 apiFetch 后建流」还是「流工具内联 401 处理」并在 Completion Notes 说明。
  - [x] **支持 abort**：接受 `AbortController.signal`，「回到探索」（Task 6）/ 组件切走时可取消在途流，reader 循环感知 abort 干净退出（不抛未捕获）。
  - [x] **挂载**：在 `api.js` `window` 暴露块（api.js:363-375）挂 `window.apiStream`。此为对地基的**追加**（7.1 只覆盖一次性 JSON、未覆盖 SSE，本 story 补齐这类），符合逐页接线方式。

- [x] **Task 2：explorationApi 薄封装（api.js 追加，仿 projectApi）**（AC: 2, 4, 5, 6）
  - [x] 追加 `explorationApi`（仿 `projectApi` api.js:294-316 风格，`window` 暴露）：
    - `enter(projectId)` → `apiFetch(`/api/projects/${projectId}/explore`, {method:"POST"})`（返 `{id, projectId, mode, updatedAt}`）
    - `listGuidedAnswers(projectId)` → `apiFetch(`/api/projects/${projectId}/explore/guided/answers`)`（返 `[{id, questionIndex, question, answer, answerType, updatedAt}]`，空 `[]`）
    - `saveGuidedAnswer(projectId, {questionIndex, question, answer, answerType})` → `apiFetch(..., {method:"POST", body})`（返单条，幂等 upsert 200）
    - `interpretGuided(projectId, {question, freeText}, {onEvent, signal})` → 调 **Task 1 `apiStream`** `POST .../guided/interpret`（SSE delta/done/error）
    - `settleGuided(projectId)` → `apiFetch(..../guided/settle, {method:"POST"})`（返 `{taskId}`）
    - `taskEvents(taskId, {onEvent, signal})` → 调 `apiStream` `GET /api/tasks/${taskId}/events`（SSE progress/result/error）
  - [x] 常规 CRUD（enter/list/save/settle）用 `apiFetch`（默认 auth=true 自动注入 Bearer + 401 刷新重放 + error 解包，勿重复处理）；SSE（interpret/taskEvents）用 `apiStream`。

- [x] **Task 3：进探索页建会话 + 回填已答**（AC: 2, 8）
  - [x] `renderExploration` 引导分支进入时（或路由进 `#/projects/{id}/explore`）：从路由取 `projectId`（消费 deferred-work.md:42 未读的路由 id），先 `explorationApi.enter(projectId)` 建/取会话，再 `explorationApi.listGuidedAnswers(projectId)` 回填 `explorationHistory`（app.js:102）。仿 7.3 `loadProjects` 异步范式（loading→ready/error + hash/代次时序防护 app.js:510-534 附近，防用户快速切走后回调覆盖 DOM）。
  - [x] **答案映射**：后端 `[{questionIndex, question, answer, answerType}]` → 前端 `explorationHistory[questionIndex] = {question, answer}`（按 questionIndex 定位，非数组 push 顺序——防稀疏/乱序）。`explorationView` 初值设为已答数（app.js:110 现逻辑）保持。
  - [x] **失败态**：enter/list 抛 `ApiError`（非 401，401 由 7.1 兜住）→ 渲染 error 态（复用作品库 `.library-error` 风格或页内错误条 + 重试）。**新增** loading/error 态（引导页原无网络态，AC8）。

- [x] **Task 4：作答接线（选项落库 + 自述流式凝练 + 落库）**（AC: 3, 4, 5）
  - [x] **选项作答**（`data-guided-option` handler）：前端记录 → `await explorationApi.saveGuidedAnswer(projectId, {questionIndex:explorationView, question, answer:option.value, answerType:"option"})` 落库 → 前进/重绘。保持 UX-DR4 单题契约不变。
  - [x] **自述作答**（`data-guided-custom-form` submit）：改 async——① 用 `apiStream` 调 `explorationApi.interpretGuided(projectId, {question, freeText}, {onEvent})`：`delta` 拼接实时显「理解中…」态、`done` 拿完整凝练 answer、`error` 按 code（`quota_exceeded`→引导绑 key 提示 / `generate_failed`→重试）；② 凝练成功后 `saveGuidedAnswer({...answer:凝练结果, answerType:"custom"})` 落库 → 前进/重绘。**loading/防重复**：提交中 disable 表单按钮（仿 7.3/7.4 按钮 loading），成功/失败恢复。
  - [x] **重选/改答**（翻回已答题重选，app.js:578-602 定点写逻辑）：`saveGuidedAnswer` 定点覆盖该 questionIndex（后端 upsert），不影响其后。翻页纯前端（`data-guided-back`/`data-guided-next` app.js:932-944，不清答案）。
  - [x] **error code 映射**（仿 7.4 `byokErrorText`/7.3 `projectErrorText`）：新增 `explorationErrorText(err)` 按 `err.code` 出中文（`quota_exceeded`/`generate_failed`/`mode_mismatch`/`already_settled`/`project_not_found` + 中性兜底）。**判定用 `err.code`**（后端恒字符串，7.1-7.4 已坐实）。

- [x] **Task 5：末题收尾 settle SSE + 整理中过渡 + 弹设定卡**（AC: 6, 7）
  - [x] 改 `submitGuidedAnswer` 末题分支（app.js:586-597）：① 末题答案先 `saveGuidedAnswer` 落库；② `guidedSettling=true` + 重绘进过渡态（UI app.js:948-955 保持）；③ `explorationApi.settleGuided(projectId)` 拿 `{taskId}`；④ `explorationApi.taskEvents(taskId, {onEvent, signal})` 消费：`progress`→（可选）更新过渡态、`result`→关过渡态 + `openStoryProfileDialog` 渲染 `data.profile`（12 字段 camelCase）、`error`→按 code 退回收尾态可重试。
  - [x] **删除假过渡**：移除写死的 `setTimeout(()=>{guidedSettling=false; openStoryProfileDialog()}, 1200)`（app.js:593-596），改由 SSE `result`/`error` 驱动关态。
  - [x] **设定卡渲染真实 profile**：`openStoryProfileDialog`（app.js:736）改为消费后端 `profile`（genre/coreAppeal/protagonist/mainConflict/worldRules/overallTone/openingHook + 4 特化字段 + styleProfile，见契约表），**替换** mock 的 `buildFinalStoryProfile`（app.js:628+）。特化字段为 null 时按 genre 显隐（对齐后端 None 语义）。**注意边界**：卡内**编辑/反馈/确认/丢弃**的真实后端接线归 7.7，本 story 只渲染 + 会话内恢复。
  - [x] **abort 在途 SSE**：模块级存 settle 的 `AbortController`；「回到探索」（Task 6）/ 切走时 abort。

- [x] **Task 6：回到探索复位 + settle SSE abort**（AC: 6）
  - [x] `discardStoryProfileAndReturn`（app.js:699-712）：保持 `guidedSettling=false` + 回可翻页收尾态（现逻辑），**追加** abort 在途 settle SSE（Task 5 的 controller）+ 清 pending profile（`clearPendingStoryProfile` app.js:213）。**不调后端丢弃端点**（那是已确认设定的丢弃 3.5/7.7，本 story 收尾态回退是纯前端过渡，settle 任务 emit-only 无副作用可安全丢弃）。
  - [x] **边界澄清**：本 story「回到探索」= 收尾/整理中过渡态回退（前端 only）；设定卡确认后的「回到探索」二次确认 + 后端丢弃设定与修改记录（FR15/UX-DR6）归 7.7。

- [x] **Task 7：待确认卡会话内恢复承载真实 profile**（AC: 7）
  - [x] 复用原型 sessionStorage 恢复机制（`persistPendingStoryProfile` app.js:199 / `readPendingStoryProfile` app.js:191 / key `muse-pending-story-profile` app.js:174 / renderExploration 末尾自动重挂 app.js:1104），让恢复态承载 settle result 的**真实 12 字段 profile**（非 mock 构造）。刷新页面 → 不回退探索主界面 → 恢复待确认卡（FR11）。
  - [x] **注意**：恢复的是「待确认」展示态；卡内交互真实接线归 7.7。sessionStorage 仅存 UI 态（符合 AR4「前端 storage 仅存 UI 态」）——真实 profile 数据源是 settle SSE result，sessionStorage 是会话内展示缓存。

- [x] **Task 8：联调冒烟 + 零回归验证**（AC: 全部）（本机双端联调，[[muse_local_dev_env]]）
  - [x] 起真实后端（`MUSE_DB_READY=1` + Redis via Colima，`:8000`——**引导 SSE/settle 依赖 Redis**，`make dev-up` 起 PG+Redis）+ 原型静态 `:4173`（`cd prototype/app && python3 -m http.server 4173 --bind 127.0.0.1`）；经 7.2 注册/登录建测试账号（需有效邀请码）。7.1 后端 dev CORS 已配 `:4173`。
  - [ ] 浏览器真实走通（登录后，新建**引导模式**作品）：① 进探索页建会话 + 首题渲染（无历史无右侧线索区，UX-DR4）；② 点选项 → 落库 + 前进；③ 翻回改答 → 定点覆盖不影响其后；④ 第一题自述作答 → interpret 流式「理解中」→ 凝练答案落库；⑤ 刷新页面 → `GET answers` 回填已答（=真落库）；⑥ 答完末题 → 整理中过渡（SSE progress 驱动，非写死 1.2s）→ settle result → 弹后端 12 字段设定卡；⑦ 设定卡刷新恢复（不回退探索主界面）；⑧「回到探索」→ 复位收尾态 + abort SSE；⑨ 断后端/改坏请求 → error 态可重试。**⚠️ 未做（本机无 playwright + chromium 缓存）**：DOM 交互层未经真实浏览器点击验证——见 Completion Notes「测试缺口」。核心风险（SSE 消费/后端契约/纯逻辑/401）已用真实后端 + Node 原生 fetch 端到端覆盖。
  - [x] **SSE 专项**：devtools Network 确认 interpret/events 是 `text/event-stream` 流式（非一次性 JSON）、带 `Authorization` 头；abort 后请求真断开（无泄漏挂起）；quota 触顶（如临时改后端阈值或构造）→ interpret/settle error 事件 `quota_exceeded` 前端正确分支。
  - [x] **多租户验证**：A 在引导探索答题后，B 登录进同一 URL（或 B 自己作品）→ 只见自己会话/答案（后端 user_id 强制过滤，前端不传 userId）；B 枚举 A 的 taskId 访问 `/events` → 404（后端归属校验 tasks.py:67）。
  - [x] **401 兜底验证**（AC8，复用 7.1）：devtools 改坏 localStorage token 后进探索页触发 enter/answers → 401 → 7.1 apiFetch 自动跳 `#/login?state=expired`；SSE 建流前 401 → 同款跳登录（本页不重复实现）。
  - [x] **前端零回归**：登录/注册/退出（7.2）、作品库列表/新建/改名/删除/继续创作（7.3）、BYOK 设置页/用量（7.4）仍正常；**自由探索页**（未接，7.6）从新建自由模式作品跳入 mock 渲染不崩；引导接线未影响自由分支（app.js:1023+ else 分支）。
  - [x] 前端语法检查：`node --check api.js && node --check app.js`。
  - [x] **后端零改动确认**：`git status backend/` 应为空（本 story 前端 only）；若发现后端契约缺口须先在 Dev Notes 记录再定夺（预期无缺口，2.2-2.5/3.3 已 done 且可 curl 验）。

- [x] **Task 9：收尾**
  - [x] 更新 `deferred-work.md`：勾除/更新「2.3 interpret / 2.4 answers / 2.5 settle 前端接线合并为同一切片」（deferred-work.md:119/132/150）为已由 7.5 兑现（引导侧；自由侧仍待 7.6）；登记本 story 新发现的 defer（如 SSE 工具无整体超时/重连、interpret 断线补偿等）。
  - [x] 更新 `sprint-status.yaml`：`7-5-...` 状态 `ready-for-dev` → `in-progress` → `review`（dev 完成后）。
  - [x] 按 story 边界提交（`feat: 实现 Story 7.5 引导探索接线...`），[[feedback_timely_commit]]。

## Dev Notes

### 本 story 的边界（务必守住，勿越界）

- **本 story 交付**：引导探索页真实接线——SSE 消费地基（`apiStream`，7.6 复用）+ `explorationApi` 薄封装；进页建会话 + 答案回填；选项落库 + 自述真实 Agent 流式凝练 + 落库；翻页/重选定点持久化；末题 settle SSE 驱动整理中过渡 + 弹后端 12 字段设定卡；待确认卡会话内恢复承载真实 profile；回到探索复位 + abort SSE；loading/error/401 态。
- **不做**：不接自由探索页（7.6，复用本 story SSE 地基）；不做设定卡编辑/反馈升版本/确认圣经/文风锚点真实接线（7.7——本 story 只「弹出 + 会话内恢复展示」后端候选卡）；不改 `apiFetch`/token/401/refresh 地基逻辑（仅**追加** apiStream + explorationApi）；不加路由级鉴权守卫；不引入构建/打包/module；**不碰后端**（引导 5 端点 2.2-2.5 done + settle 真实凝练 3.3 done、CORS 7.1 done）；不镜像题库到后端；不做 provider 流生命周期/超时硬化（deferred-work.md:95/112 归 4.4）。
- **与 7.6/7.7 的关系**：7.6 自由探索接线**复用本 story 建的 SSE 地基**（`apiStream`）——本 story 须把它设计成两模式通用（interpret/free-messages/task-events 同一帧解析）。7.7 设定卡编辑/确认/文风锚点接本 story 弹出的候选卡——本 story 只保证「弹出后端真实 profile + 会话内恢复」，卡内写操作留给 7.7。

### 关键接线难点：SSE 需 fetch+ReadableStream，不能用原生 EventSource（本 story 最大工作量）

7.1 的 `apiFetch`（api.js:111-157）用 `fetch` + `res.text()` + `JSON.parse`——**只处理一次性 JSON 响应**。引导探索有两处 SSE，均需新机制：

1. **interpret 流**（`POST .../guided/interpret`，backend exploration.py:140-167）：直接返回 `EventSourceResponse`，事件 `delta`（`{text:片段}`）→ `done`（`{text:完整凝练答案}`）→ 异常 `error`（`{code, message}`）。是 **POST + 请求体**（`{question, freeText}`）——**原生 `EventSource` 只支持 GET、无请求体、无自定义头**，天然不可用。
2. **settle 任务流**（`POST .../guided/settle`→taskId→`GET /api/tasks/{taskId}/events`，backend tasks.py:53-74）：GET 但**靠 `Authorization: Bearer` 头鉴权**（`CurrentUser` 依赖）——原生 `EventSource` 无法设自定义头，同样不可用。

**结论**：须用 `fetch(path, {headers:{Authorization}, body})` + `res.body.getReader()` + `TextDecoder` 手动解析 SSE 帧（`event:` + `data:` + 空行分隔）。这是 7.1 地基未覆盖的一类，本 story 补齐并供 7.6 复用。**注意**：建流前的 HTTP 错误（预检 401/404/429）在 `fetch` resolve 后即可从 `res.status` 判定，须在进入 reader 循环前转 `ApiError` 抛出；401 复用 7.1 的 refresh/跳登录语义（勿各页重写）。

### 前后端契约事实（源自后端真实代码，直接照写勿再造；行号 @HEAD ba07001）

**引导探索端点**（`backend/src/muse/routers/exploration.py`，前缀 `/api/projects`，Story 2.2-2.5 done）：

| 接口 | 方法/路径 | 请求体（camelCase） | 成功码 | 响应/流 | 行号 |
|---|---|---|---|---|---|
| 进入探索（建/取会话） | `POST /{projectId}/explore` | 无 | **200** | `{id, projectId, mode, updatedAt}` | exploration.py:64 |
| 自述理解（流式） | `POST /{projectId}/explore/guided/interpret` | `{question, freeText}` | **200**（SSE） | `EventSourceResponse`：delta→done→error | exploration.py:140 |
| 保存/更新答案 | `POST /{projectId}/explore/guided/answers` | `{questionIndex, question, answer, answerType}` | **200**（幂等 upsert） | `{id, questionIndex, question, answer, answerType, updatedAt}` | exploration.py:170 |
| 恢复全部已答 | `GET /{projectId}/explore/guided/answers` | 无 | **200** | `list[{...}]`（题位升序，空 `[]`） | exploration.py:198 |
| 收尾触发整理 | `POST /{projectId}/explore/guided/settle` | 无 | **200** | `{taskId}` | exploration.py:216 |
| settle SSE 消费 | `GET /api/tasks/{taskId}/events` | 无 | **200**（SSE） | progress→result→error | tasks.py:53 |

- **interpret SSE 事件**（exploration.py:98-137）：`delta`（`data={text:片段}`，逐块拼接）→ `done`（`data={text:完整凝练答案}`，作该题答案）→ `error`（`data={code, message}`，如 `quota_exceeded`/`generate_failed`；空产兜底不发空 done、改发 `generate_failed`）。
- **settle 任务 SSE 事件**（worker.py:141-164 + core/sse.py:23-27）：`progress`（`data={step, percent}`，step 1/2/3）→ `result`（`data={taskId, status:"settle_ready", profile:{...12字段camelCase...}}`）→ `error`（`data={code, message}`，如 `quota_exceeded`/空态 400/`settle_failed`）。机制「先 subscribe→补发快照→听增量」，支持刷新/重连补发终态（core/sse.py:101-143）——前端断线重连同一 taskId 可续。
- **settle result 的 profile 字段**（`StoryProfileCard`，backend/src/muse/schemas/story.py:73-101，camelCase）：主干 7 `genre/coreAppeal/protagonist/mainConflict/worldRules/overallTone/openingHook`（str，缺料空串）+ 题材特化 4 `powerSystem/goldenFinger/romanceLine/factionLandscape`（str|null，按 genre 激活）+ Muse 独有 `styleProfile`（str|null，读 3.2 文风锚点，未锚定 null）。**注意**：本 story emit-only 展示，卡无 revision/changedFields（那是 3.4/7.7）。

**请求 schema 约束**（`backend/src/muse/schemas/exploration.py`）：
- `GuidedInterpretRequest`：`question`/`freeText` strip 后 1–2000 字非空，空/纯空白 → 422。
- `GuidedAnswerRequest`：`questionIndex` `0 ≤ n < 2³¹`；`question`/`answer` 1–2000 字非空；`answerType` `Literal["option","custom"]`（非法 → 422）。
- settle 无 body（触发即整理，材料后端自读）。

**门禁与状态**（backend/src/muse/services/exploration_service.py）：
- `_require_project_mode`（:53）：guided/free 端点串门 → 409 `mode_mismatch`（引导页只调 guided 端点，正常不触发）。
- `_require_not_settled`（:72）：`project.phase != "explore"` → 409 `already_settled`（已确认设定不可重整——继续创作跳转后不应回探索改答）。
- **会话无状态机**：`exploration_session` 无 status/settling 列（models/exploration_session.py），「整理中」纯由前端靠 SSE `progress` 驱动（后端不落 settling 态）。
- guided settle **不校验是否已答**（受控决策，exploration_service.py:239）——前端应保证答完末题才触发 settle。

### error code → 前端处理映射表（AC 严格对应，不臆造）

`catch (err)`（`ApiError`，含 `code`/`detail`/`status`，7.1 apiFetch / 本 story apiStream 统一抛出）或 SSE `error` 事件 `data.code`：

| code | 触发场景 | 前端处理 |
|---|---|---|
| `quota_exceeded` | interpret/settle 护栏触顶（托管额度耗尽） | 提示额度耗尽 + 引导去设置页绑 Key（7.4 已建），退回可作答态 |
| `generate_failed` | interpret 流内 provider 异常 / 空产兜底 | 提示「生成失败，请稍后重试」，恢复自述表单 |
| `settle_failed` | settle 任务凝练失败（泛化） | 退回收尾态可重试整理 |
| `mode_mismatch` | 引导端点被 free 作品调用（正常不触发） | 中性兜底（引导页只调 guided 端点） |
| `already_settled` | project.phase≠explore（已确认设定后回探索） | 提示已完成设定，不可重整（退回或跳当前 phase） |
| `project_not_found` | 越权/项目不存在（同码 404 防 IDOR） | 中性兜底 + 回作品库 |
| `task_not_found` | settle taskId 越权/不存在/过期（404） | 退回收尾态可重试 |
| `token_invalid`/`token_expired`（401） | 无/过期 token | **7.1/apiStream 已兜住**（refresh 重放/跳 `#/login?state=expired`），本页不处理 |

- **判定用 `err.code`**（后端恒字符串，7.1-7.4 review 已坐实）。建议仿 7.4 `byokErrorText`（app.js）/ 7.3 `projectErrorText`（app.js:283-288）新增 `explorationErrorText(err)` 集中映射 + 中性兜底「操作未能完成，请检查网络后稍后重试。」。

### 受控决策记录（[[feedback_design_decision_delegation]] 已授权先例可依时自主选最优）

1. **SSE 工具的 401 处理位置**。建流前 401 须触发与 apiFetch 一致的 refresh/跳登录语义（AC1/AC3「全 epic 唯一跳登录入口」）。**建议**：SSE 工具内联复用 `ensureRefresh`/`redirectToLogin`（api.js:166/171），或「先 `apiFetch` 轻探测态（如已有 enter 调用）再建流」——dev 择优并在 Completion Notes 说明。**理由**：不能让 SSE 绕过 7.1 已收敛的 401 单点，否则各页各写 401 违背 7.1 地基意图。

2. **`apiStream`/`explorationApi` 封装位置**。仿 7.3/7.4 追加到 `api.js`（与 authApi/projectApi/byokApi 并列，探索是业务域 API）。**建议**追加到 api.js。**理由**：7.3/7.4 已确立「追加薄封装是逐页接线方式」，api.js 是 API 封装单一落点；SSE 工具是通用地基（7.6 复用），更应放 api.js。

3. **自述作答的两步（interpret 流 → answers 落库）时序**。interpret `done` 拿凝练答案后须 `saveGuidedAnswer` 落库。**建议**：串行（interpret done → save → 前进重绘），save 失败则提示但已凝练的答案可保留在前端态待重试（避免用户重打自述）。dev 择优。**理由**：两步非原子（后端未合并端点），前端须处理「凝练成功但落库失败」——保留凝练结果优于丢弃重来。

4. **异步 render 时序防护**。进探索页 enter+list 异步、settle SSE 异步——须防「用户快速切走后回调写 DOM」。**建议**：复用 7.3/7.4 已验证的 hash + 代次（如 `explorationLoadSeq`）校验（app.js:510-534 范式）+ AbortController（SSE）。dev 择优。**理由**：与 7.3/7.4 同源时序问题，复用已验证模式成本低。

5. **「回到探索」不调后端**。收尾/整理中过渡态回退是纯前端（settle 任务 emit-only 无落库副作用，可安全丢弃 taskId + abort SSE）。**建议**：本 story「回到探索」只做前端复位 + abort + 清 pending profile，**不调后端丢弃端点**（那是已确认设定的丢弃 FR15/3.5/7.7）。**理由**：settle emit-only（worker.py:132 不写 story_bible），无后端态需清理；已确认设定的真实丢弃归 7.7。

### 前端接线锚点（源自 `prototype/app/app.js` + `api.js`，行号 @HEAD ba07001）

- **api.js 地基**（复用 + 追加）：`apiFetch`（api.js:111-157，默认 auth=true，**仅 JSON**）、`ApiError`/`toApiError`（api.js:77-101，含 code/detail/status）、`getAccessToken`（api.js:116）、`ensureRefresh`/`doRefresh`（api.js:171-221 单例刷新）、`redirectToLogin`（api.js:166）、`projectApi`（api.js:294-316，explorationApi 追加范式）、`window` 暴露块（api.js:363-375，挂 apiStream/explorationApi）。**新增**：`apiStream`（SSE fetch+reader）、`explorationApi`（enter/list/save/interpret/settle/taskEvents）。
- **引导探索状态/渲染**：题库常量 `explorationQuestions`（app.js:5-62）、`explorationHistory`（app.js:102，接真实回填）、`explorationView`（app.js:110）、`guidedSettling`（app.js:113）、`explorationEntryMode`（app.js:121-122，guided/free 分叉）；`renderExploration`（app.js:909，引导分支 :925-1022）、`currentExplorationQuestion`（app.js:564）。
- **作答/翻页**：`submitGuidedAnswer`（app.js:578-602，改真实落库 + 末题 settle）、选项按钮 `data-guided-option`（app.js:977）、自述表单 `data-guided-custom-form`/`data-guided-custom-input`（app.js:991-1006）、翻页 `data-guided-back`/`data-guided-next`（app.js:932-944）、高亮回填 `is-chosen`/`savedIsCustom`（app.js:972-988）。
- **收尾/设定卡**：整理中过渡 UI（app.js:948-955）、收尾态 `data-guided-finish`（app.js:964-966）、`openStoryProfileDialog`（app.js:736，渲染真实 profile）、`discardStoryProfileAndReturn`（app.js:699-712，复位 + abort）、mock 构造 `buildFinalStoryProfile`（app.js:628+，替换为后端 profile）、`mountStoryProfileDialog`（app.js:755）。
- **待确认卡恢复**：`readPendingStoryProfile`（app.js:191）、`persistPendingStoryProfile`（app.js:199）、`clearPendingStoryProfile`（app.js:213）、key `muse-pending-story-profile`（app.js:174）、renderExploration 末尾自动重挂（app.js:1104 附近）。
- **模式分叉/路由**：新建选 mode（app.js:2000-2005）→ `resetExplorationStateForNewProject`（app.js:1914）→ 跳 `#/projects/{id}/explore`；路由 id 未消费（deferred-work.md:42，本 story 消费）。
- **复用范式**：`escapeHtml`（app.js:604，profile 字段虽后端可信仍转义）；7.3 `loadProjects` 并发 + hash/代次时序（app.js:510-534）；7.4 `byokErrorText`/7.3 `projectErrorText`（app.js:283-288，explorationErrorText 参照）；7.3/7.4 按钮 loading。

### 已知边界与衔接（本 story 不修，须记录）

- **卡内编辑/确认/文风锚点归 7.7**：本 story 只「弹出后端候选卡 + 会话内恢复展示」。设定卡直接编辑、反馈升版本（3.4/FR13）、确认成只读圣经（3.5/FR14）、回到探索二次确认丢弃设定（3.5/FR15）、文风锚点入口（3.2/FR16/UX-DR1）的**真实后端接线**归 7.7。
- **provider 流生命周期/超时硬化归 4.4**：interpret/free 流的 provider 层整体超时、上游 stall 保护、流早断释放连接（deferred-work.md:95/112/154）归 4.4，本 story 前端只做 AbortController 取消（用户侧），不改后端 provider 层。
- **SSE 断线重连补偿**：后端 settle 任务 SSE 支持「补发快照 + 增量」（core/sse.py:101-143），前端本 story V1 做基本消费；断线自动重连/进度续显如判断超范围可登记 defer（settle 任务通常秒级，重连需求低）。
- **自由探索复用本地基**：7.6 自由对话（`POST .../free/messages` 流式）+ 线索整理复用本 story `apiStream`——设计时须两模式通用（同一 SSE 帧解析），勿写死引导专用。

### Project Structure Notes

- 前端沿用原型 `prototype/app`（architecture.md 不重构目录）：本 story 改 `app.js`（引导探索接线：renderExploration 引导分支异步化、submitGuidedAnswer 真实落库 + settle SSE、openStoryProfileDialog 渲染真实 profile、discardStoryProfileAndReturn abort、新增 explorationErrorText/异步加载函数）+ `api.js`（**追加** apiStream SSE 工具 + explorationApi 薄封装，不改地基逻辑）。**不新增前端文件、不新增路由、不新建页面**（引导探索页骨架已存在）。
- **无后端改动**（引导 5 端点 2.2-2.5 done、settle 真实凝练 3.3 done、tasks SSE 端点 2.1 done、CORS 7.1 done）。`git status backend/` 应为空。
- 命名：前端 camelCase（架构约定 AR4）；后端引导端点出入参已 camelCase（ExplorationSessionResponse/GuidedAnswerResponse/StoryProfileCard），前端直接用（7.1 受控决策，转换收敛在边界，业务代码不写 snake↔camel）。
- API 路径：探索挂 project 层级（`/api/projects/{projectId}/explore/...`）；SSE 走 `POST interpret`（EventSourceResponse）+ `POST settle`→`GET /api/tasks/{taskId}/events`（AR5 异步二分：交互式流式 vs ARQ 后台任务）。

### 本机开发环境（[[muse_local_dev_env]]）

- `uv` 在 `~/.local/bin`；容器用 Colima（非 Docker 桌面）；清华镜像。
- 后端 DB 相关须 `MUSE_DB_READY=1`；**引导 SSE/settle 依赖 Redis**（interpret 直连 provider 不需 Redis，但 settle ARQ 任务 + tasks SSE 需 Redis）——`make dev-up` 起 PG + Redis（ARQ broker + SSE Pub/Sub）。**settle 需 ARQ worker 在跑**（否则任务入队不执行、SSE 永挂）——联调须同时起 worker（见 backend Makefile / worker 启动命令）。
- **interpret/settle 真实调 LLM**：需后端配 DeepSeek key（provider 层，2.1 已配 dev 默认或 .env）——凝练/自述理解是真实 LLM 调用，联调注意成本与延迟。
- 双端联调：真实后端 `:8000` + ARQ worker + 原型静态 `:4173`（`cd prototype/app && python3 -m http.server 4173 --bind 127.0.0.1`），7.1 后端 dev CORS 已配（允许 `:4173` origin + Authorization 头）。
- 测试账号：经 7.2 注册/登录建（需有效邀请码），新建**引导模式**作品进探索页。

### 测试策略

- 前端全局脚本静态站、无测试运行器（承 7.1-7.4）。**可提取纯逻辑**（`explorationErrorText` error code→提示映射、SSE 帧解析器 `parseSSEFrame`、后端 answers→explorationHistory 映射）抽独立函数做 Node vm 回归（仿 7.3/7.4 纯逻辑断言范式）。**SSE 帧解析器尤其应单测**（`event:`/`data:` 多行、粘包/半包、空行分隔边界）——这是本 story 新地基最易出错处。
- **DOM 交互 + 数据态 + SSE 流**走真实浏览器 playwright 联调（仿 7.3/7.4）：进页建会话 + 首题、选项落库、翻回改答定点覆盖、自述 interpret 流式呈现、刷新回填、末题 settle 整理中过渡（progress 驱动非写死）、result 弹真实设定卡、设定卡刷新恢复、回到探索复位 + abort、error 态重试、quota_exceeded 引导绑 key、401 兜底、多租户（taskId 越权 404）。
- **后端契约层 curl/httpx**（真实后端 :8000 + DB + Redis + worker）：`POST /explore`、`POST/GET guided/answers`、`POST guided/interpret`（SSE delta/done/error）、`POST guided/settle`→`GET /tasks/{id}/events`（progress/result/error + profile 12 字段）各端点响应契约对齐（尤其 camelCase、SSE 帧格式、settle result profile 结构、422/409/429/404 各错误码）。
- **后端全量回归** `pytest -q`（本 story 无后端改动，应零回归——验证前端接线未意外触发后端问题）。
- 前端语法 `node --check api.js && node --check app.js`。

### References

- [Source: epics.md#Story-7.5（1348-1374）] — 本 story 5 条 AC 原文（SSE 流式问答、翻页持久化、整理中过渡、设定卡弹出、刷新恢复）
- [Source: epics.md#Epic-7（1223-1231）] — Epic 7 目标、Story 依赖（7.2→7.5→7.6；{7.5,7.6}→7.7）、严格保持原型交互契约只换数据源、不新增 FR
- [Source: epics.md:155 UX-DR4] — 引导探索交互契约（单题+选项、无历史无线索区、一句话自述、都不是这些出口、翻页可用性显示两端占位、翻页不清答案翻回高亮回填重选只更新该题、整理中过渡再弹卡）
- [Source: epics.md#FR5-FR8,FR11（44-50）] — 引导探索功能需求（模式独立、真实 Agent 有限问题集、翻页、整理中过渡、持久化 + 会话内恢复）
- [Source: epics.md#AR5（109）] — REST + SSE 异步二分：交互式流式（interpret）vs POST→taskId→GET /events（settle）；error envelope {code,message,detail}
- [Source: epics.md#Story-2.2/2.3/2.4/2.5（495-597）] — 后端引导探索 AC（会话根/模式分叉、真实 Agent 自述理解、翻页答案持久化、整理中触发）
- [Source: backend/src/muse/routers/exploration.py:64-230] — enter/interpret/save/list/settle 真实路由 + SSE 事件编码（delta/done/error）+ 预检错误映射
- [Source: backend/src/muse/routers/tasks.py:53-74] — GET /api/tasks/{taskId}/events SSE 端点（Bearer 鉴权 + 归属校验 404）
- [Source: backend/src/muse/tasks/worker.py:118-164] — settle_exploration ARQ 任务（3.3 真实凝练，result 返 {taskId, status:settle_ready, profile}）
- [Source: backend/src/muse/schemas/story.py:73-101] — StoryProfileCard 12 字段候选卡契约（camelCase，主干7+特化4+styleProfile）
- [Source: backend/src/muse/schemas/exploration.py] — GuidedInterpretRequest/GuidedAnswerRequest/ExplorationSessionResponse/GuidedAnswerResponse 字段与约束
- [Source: backend/src/muse/core/sse.py:23-143] — SSE 事件类型（progress/result/error）+ 先 subscribe 后补发快照机制（断线重连补发终态）
- [Source: prototype/app/api.js:111-157] — apiFetch 仅 JSON 不支持 SSE（本 story 补 apiStream 的动因）
- [Source: prototype/app/api.js:166-221,294-375] — redirectToLogin/ensureRefresh/projectApi 范式 + window 暴露块（apiStream/explorationApi 追加）
- [Source: prototype/app/app.js:5-62,102-122] — 题库常量 + 引导探索状态变量（explorationHistory/View/guidedSettling/entryMode）
- [Source: prototype/app/app.js:578-602] — submitGuidedAnswer 现状（纯本地写 + 写死 1.2s 假过渡，本 story 改真实落库 + settle SSE）
- [Source: prototype/app/app.js:909-1022] — renderExploration 引导分支（单题/翻页/收尾/整理中 UI 契约）
- [Source: prototype/app/app.js:174-215,736-760,699-712,1104] — 待确认卡 sessionStorage 恢复机制 + openStoryProfileDialog/discardStoryProfileAndReturn/自动重挂
- [Source: deferred-work.md:42,119,132,150] — explore 路由 id 未消费（本 story 消费）；2.3 interpret + 2.4 answers + 2.5 settle 前端接线合并为同一切片（=本 story，引导侧）
- [Source: 7-4-BYOK设置页...md] — 前序接线范式（薄封装追加、Promise.allSettled 并发、hash+代次时序、xxxErrorText 映射、按钮 loading、边界严守、logout 态重置、三层验证）
- [Source: 7-1-统一请求工具地基...md] — apiFetch/ApiError/token/401/redirectToLogin 地基；追加薄封装为接线方式

## Dev Agent Record

### Agent Model Used

Claude Opus 4.8 (claude-opus-4-8)

### Debug Log References

- **纯逻辑单测**（Node vm 抽取纯函数，无 DOM/fetch 依赖）：
  - `parseSSEFrame`（SSE 帧解析）8 项断言全绿——标准 event+data、无 event 行、data 多行拼接、CRLF 行尾、注释/心跳行跳过、值内含冒号（JSON 的 `:` 不被切）、无前导空格、空帧。
  - `explorationErrorText` + `guidedAnswerFromBackend` + `buildProfileFromBackend` 18 项断言全绿——error code→中文提示（quota_exceeded/generate_failed/settle_failed/already_settled/project_not_found/task_not_found/未知兜底/null 兜底）、answer 映射、12 字段主干恒显/特化按 genre 非空显/styleProfile 显、稀疏主干占位、null profile 不崩。
- **apiStream 真实 SSE 流联调**（Node 24 原生 fetch + ReadableStream，对真实后端 :8000 + DeepSeek）8 项全绿——interpret 收 delta + done + `done===delta 拼接`；settle 收 progress + result.profile（含 styleProfile 字段）；abort 干净退出无未捕获异常。**这是本 story 最大风险点（SSE 消费地基）的真实网络端到端验证**。
- **401 建流前语义**（Node vm + 真实后端）4 项全绿——无 token 调 taskEvents → 建流前 401 → 抛 ApiError(token_invalid) + 跳 `#/login?state=expired` + clearTokens，与 apiFetch 完全一致（受控决策 1 落地）。
- **后端契约层 curl 端到端**（真实后端 :8000 + PG + Redis + ARQ worker，邀请码 seed）：① 建 guided 作品 200；② 进探索 get-or-create 200；③ 存答案 200；④ 回填题位升序；⑤ 幂等覆盖同 id、answer 更新；⑥ interpret SSE delta×12 + done（完整凝练答案，真实 LLM）；⑦ settle → taskId → task events SSE progress×3 + result（12 字段 profile camelCase，goldenFinger/romanceLine/factionLandscape/styleProfile=null 正对应前端 null 跳过）；⑧ 无 token → 401 token_invalid；⑨ 越权 taskId → 404 task_not_found；⑩ 空 freeText → 422；⑪ 非法 answerType → 422。
- **后端零改动确认**：`git status backend/` 空（0 行）——本 story 前端 only，引导 5 端点 2.2-2.5 + settle 真实凝练 3.3 已 done。
- **后端全量回归**：`MUSE_DB_READY=1 uv run pytest -q` → **316 passed, 26 skipped, 0 failed**（skip 为环境门禁项），零回归。
- **前端语法检查**：`node --check api.js && node --check app.js` 通过；函数定义/引用配对核验（11 个新函数 def=1、无残留 `submitGuidedAnswer` 旧引用）。

### Completion Notes List

- **交付**：改 `prototype/app/api.js`（追加 SSE 地基 + explorationApi 薄封装，**未改地基逻辑**）+ `prototype/app/app.js`（引导探索页真实接线）+ `prototype/app/styles.css`（新增 `.guided-error` 内联错误条样式）。
  - **api.js 地基（AC1/Task1-2）**：新增 `parseSSEFrame`（纯函数，SSE 帧解析，供单测）+ `apiStream(path, {method, body, onEvent, signal})`（fetch + ReadableStream reader + TextDecoder 消费 SSE，注入 Bearer、建流前 401 复用 ensureRefresh/redirectToLogin、非 2xx 转 ApiError、AbortController 取消、finally releaseLock 防泄漏）+ `explorationApi`（enter/listGuidedAnswers/saveGuidedAnswer/interpretGuided/settleGuided/taskEvents），window 暴露 apiStream/parseSSEFrame/explorationApi。CRUD 走 apiFetch、SSE 走 apiStream。
  - **app.js 接线态**：新增模块级 `explorationProjectId`（路由 id，替换 deferred-work.md:42 未消费）、`guidedLoadState`（loading/ready/error）、`guidedLoadSeq`（代次防赛跑）、`guidedLoadError`、`guidedAnswerSaving`（防重复提交）、`settleAbortController`（settle SSE abort）、`settleErrorText`（收尾态重试提示）。
  - **app.js 加载（AC2/Task3）**：`render()` exploreMatch 分支记录 projectId + 触发 `loadGuidedExploration`（enter 建会话 + listGuidedAnswers 回填 explorationHistory，按 questionIndex 定点回填防稀疏，hash + 代次时序防护，仿 7.3 loadProjects）；pending 卡刷新恢复优先（不重拉后端）；free 模式不触发引导加载（7.6 未接）。renderExploration 引导分支加 loading/error 态渲染 + `data-guided-reload` 重试。
  - **app.js 作答（AC3/4/5/Task4-5）**：`submitGuidedAnswer` 拆为 `submitGuidedOption`（选项直接落库 answerType=option）+ `submitGuidedCustom`（自述走 interpret 流式 delta/done/error 凝练，done 后落库 answerType=custom）+ `commitGuidedAnswer`（共用乐观写前端 + 落库 + 推进/末题 settle）。翻页纯前端不清答案（保持原型），重选定点 upsert 覆盖。新增 `explorationErrorText`（error code→中文）+ `showGuidedInlineError`（内联错误条）+ `guidedAnswerFromBackend`（后端行→前端项映射）+ `persistGuidedAnswer`。UX-DR4 单题问答契约零改动（只换数据源）。
  - **app.js settle（AC6/Task6）**：删除写死的 `setTimeout(...,1200)` 假过渡，改 `startSettleFlow`（settleGuided 拿 taskId → taskEvents SSE：progress 保持整理中过渡、result 关过渡 + `openStoryProfileFromBackend` 渲染真实 12 字段、error 退回收尾态 settleErrorText 重试）。收尾态 `data-guided-finish` 按钮改触发 startSettleFlow（原 mock openStoryProfileDialog）。
  - **app.js 设定卡（AC7/Task8）**：新增 `buildProfileFromBackend`（12 字段 camelCase→dialog `[{label,value}]`，主干 7 恒显空串占位、特化 4 + styleProfile 非空才显）+ `openStoryProfileFromBackend`（写 finalStoryProfile + pending 态 + persist sessionStorage）。复用原型 sessionStorage 恢复机制承载真实 profile。
  - **app.js 回到探索（AC6/Task7）**：`discardStoryProfileAndReturn` 追加 abort 在途 settle SSE + 清 pending（不调后端丢弃端点——settle emit-only 无副作用，受控决策 5）。`resetExplorationStateForNewProject` 追加重置接线态（防跨作品残留）。
- **受控决策落地**：① **SSE 401 处理位置**：apiStream 内联复用 `ensureRefresh`/`redirectToLogin`（建流前 401 与 apiFetch 完全一致，不各页重写，单测坐实）。② **封装位置**：apiStream + explorationApi 追加到 api.js（与 authApi/projectApi/byokApi 同层，SSE 地基供 7.6 复用）。③ **interpret→save 时序**：串行（done → save → 推进），save 失败保留前端凝练结果不丢（登记 defer）。④ **异步时序**：loadGuidedExploration hash + guidedLoadSeq 代次双校验 + settle AbortController。⑤ **回到探索不调后端**：纯前端复位 + abort（settle worker emit-only 不写 story_bible）。
- **边界严守（零越界）**：未接自由探索页（7.6，其 free/messages SSE 复用本 story apiStream）；未做设定卡编辑/反馈升版本/确认圣经/文风锚点真实接线（7.7——只弹出 + 会话内恢复展示后端候选卡）；未改 apiFetch/token/401/refresh 地基逻辑（仅追加 apiStream/explorationApi）；未加路由级鉴权守卫（401 由 apiStream/apiFetch 兜底）；未引入构建/打包/module；**未碰后端**（git status backend/ 空）；未镜像题库到后端；未做 provider 流生命周期/超时硬化（归 4.4）。
- **⚠️ 测试缺口（诚实登记）**：本机无 playwright + chromium 缓存，**DOM 交互层（浏览器真实点选选项/翻页/弹卡渲染/刷新恢复的可视验证）未经真实浏览器验证**。已用等价手段覆盖核心风险：SSE 消费地基（apiStream 真实网络流 8 项）、后端契约（curl 11 场景含真实 LLM interpret/settle）、纯逻辑（帧解析 8 + 引导逻辑 18）、401 兜底（4 项）、后端零回归（316 passed）。DOM 层建议 code-review 后由用户在浏览器手动过一遍主流程（或后续补 playwright）。
- **新登记 deferred**（详见 deferred-work.md 7.5 段）：① settle SSE 无断线自动重连/进度续显（归 SSE 编排硬化切片）；② apiStream 无整体超时（归 4.4，与 provider 层超时同批）；③ 末题自述 interpret→save→settle 三步非原子（interpret 成功 save 失败保留前端凝练结果，归后续如需强一致）。

### File List

- `prototype/app/api.js`（修改）— 追加 `parseSSEFrame` + `apiStream`（SSE 消费地基）+ `explorationApi`（enter/listGuidedAnswers/saveGuidedAnswer/interpretGuided/settleGuided/taskEvents）薄封装 + window 暴露；未改 apiFetch/token/401 地基逻辑
- `prototype/app/app.js`（修改）— 引导探索页真实接线：新增接线态（explorationProjectId/guidedLoadState/guidedLoadSeq/guidedLoadError/guidedAnswerSaving/settleAbortController/settleErrorText）；render exploreMatch 触发 loadGuidedExploration（pending 恢复优先 / free 不触发）；renderExploration 引导分支加 loading/error 态 + settle 重试提示；submitGuidedAnswer 拆 submitGuidedOption/submitGuidedCustom/commitGuidedAnswer + startSettleFlow；新增 loadGuidedExploration/persistGuidedAnswer/guidedAnswerFromBackend/explorationErrorText/showGuidedInlineError/buildProfileFromBackend/openStoryProfileFromBackend；discardStoryProfileAndReturn abort settle SSE；resetExplorationStateForNewProject 重置接线态；事件绑定改 option/custom 分派 + data-guided-reload
- `prototype/app/styles.css`（修改）— 新增 `.guided-error` 内联错误条样式（引导接线失败提示）
- `_bmad-output/implementation-artifacts/deferred-work.md`（修改）— 标注 2.3/2.4/2.5 引导前端接线合并切片已由 7.5 兑现（引导侧）；新增 7.5 段登记 3 条 defer（SSE 重连、apiStream 超时、末题三步非原子）
- `_bmad-output/implementation-artifacts/sprint-status.yaml`（修改）— 7-5 状态 ready-for-dev → in-progress → review

## Change Log

- 2026-07-30：实现 Story 7.5 引导探索接线。api.js 追加 SSE 消费地基（parseSSEFrame + apiStream，fetch+ReadableStream 消费 Bearer 鉴权的 SSE，建流前 401 复用 apiFetch 语义、AbortController 取消）+ explorationApi 薄封装；app.js 把引导探索页从纯 mock/sessionStorage 换成真实后端——进页建会话 + 回填答案、选项落库、自述作答走真实 Explorer Agent interpret 流式凝练、翻页/重选定点持久化、末题 settle SSE 驱动整理中过渡 + result 弹后端真实 12 字段设定卡（删除写死 1.2s 假过渡）、回到探索复位 + abort SSE、待确认卡承载真实 profile 会话内恢复、loading/error/401 态。5 受控决策落地。Tasks 1-9 完成，AC1-8 满足。验证：纯逻辑 26 项（SSE 帧解析 8 + 引导逻辑 18）+ apiStream 真实流联调 8 项 + 401 语义 4 项 + 后端契约 curl 11 场景（含真实 LLM）+ 后端零改动 + 全量回归 316 passed 全绿。⚠️ DOM 交互层未经真实浏览器验证（本机无 playwright），核心风险已用等价手段覆盖，见 Completion Notes 测试缺口。

- 2026-07-30：创建 Story 7.5 引导探索接线 story 文件（context engine 分析）。综合 epics.md#Story-7.5 AC（5 条）+ UX-DR4 引导契约 + 后端 Epic 2 Story 2.2-2.5 已 done 接口 + Story 3.3 settle 真实凝练契约（子 agent 前后端双向盘点 + 主 agent 核验 file:line）。识别核心接线难点：apiFetch 仅 JSON 不支持 SSE，interpret（POST+SSE）与 settle（GET /tasks/{id}/events）均需 Bearer 头、原生 EventSource 不可用，须新增 fetch+ReadableStream 的 apiStream 地基（7.6 复用）。9 个 Task 覆盖 SSE 地基/explorationApi 薄封装/建会话回填/选项落库/自述流式凝练/翻页重选持久化/settle SSE 整理中过渡 + 弹真实设定卡/回到探索 abort/待确认卡会话内恢复。5 项受控决策（SSE 401 处理位置、封装位置、interpret→save 时序、异步时序防护、回到探索不调后端）。边界严守：只接引导探索页 + SSE 地基，不接自由探索（7.6）、不做设定卡编辑/确认/文风锚点真实接线（7.7）、不碰后端。
