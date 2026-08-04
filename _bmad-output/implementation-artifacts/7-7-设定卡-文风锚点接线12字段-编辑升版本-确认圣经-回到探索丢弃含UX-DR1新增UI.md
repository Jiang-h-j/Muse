---
baseline_commit: 434c304
---

# Story 7.7: 设定卡 + 文风锚点接线（含 UX-DR1 须新增 UI）

Status: done

## Story

As a 结束探索的用户，
I want 编辑真实生成的 12 字段设定卡、锚定文风并确认成设定圣经，
so that 我的设定成为只读全文上下文，注入后续所有创作。

## Acceptance Criteria

> **本 story = 把设定卡页（`storyProfileDialogMarkup` + `bindStoryProfileDialogInteractions` + `confirmStoryProfileAndEnterChapter` + 文风锚点入口）从纯 mock/sessionStorage 换成 Epic 3 已 done 的真实后端**：进页恢复后端候选卡（3.4）、直接编辑字段落库（3.4）、反馈升版本真实 Agent（3.4）、确认成只读圣经+推进 phase（3.5）、回到探索后端丢弃（3.5）、文风锚点入口真实抽取（3.2，含样本库 UI）。后端 7 个端点（story.py:67-209）已全部就绪，前端零后端改动——只需新增 `api.js` `storyApi` 薄封装 + `app.js` 接线替换。
>
> **复用而不重造**：继续复用 `apiFetch`（Bearer 鉴权、401 refresh/跳登录、error envelope 解包）与 `explorationApi`（settle SSE `taskEvents`、`openStoryProfileFromBackend` + `buildProfileFromBackend` 候选卡映射）。不新建 SSE 消费、不复制 token/error 处理代码。**关键依赖已满足**：① `story_bible` 表（3.1）已建，含 `status/revision/changed_fields` 三列；② `style_profile` 抽取（3.2）已做，前端可调 `style-anchor` 端点获取；③ 候选卡编辑/反馈升版本/确认/丢弃后端（3.4/3.5）均已 done；④ settle SSE result 已回传 12 字段 `profile`（`StoryProfileCard`），`openStoryProfileFromBackend` + `buildProfileFromBackend` 已把它转成设定卡对话框渲染用的 `[{label, value}]` 结构（7.5/7.6 共享、不重复建）。
>
> **关键历史教训（从前端 7.5/7.6 的 code review 修正中提取）**：① 7.5 的 `discardStoryProfileAndReturn` 当时基于「settle emit-only 无落库副作用」的**过时理解**只做前端复位、未调后端 discard，并明说「已确认设定的真实丢弃 FR15 归 7.7」（app.js:1626-1628）——但实际 3.4 起 settle 已落库 pending 卡（见下方 Dev Notes「设定卡状态机」），所以本 story 的「回到探索」二次确认**必须调后端 `POST .../story-profile/discard`** 删 pending 行；② 7.5 的 Task 7（`persistPendingStoryProfile` + `readPendingStoryProfile`）已建 sessionStorage 恢复机制——本 story 须让恢复态承载**后端返回的真实 `StoryProfileCardResponse`**（含 `revision/changedFields/status`），而非 mock 构造；③ 7.6 的 `teardownExplorationInflight` + `resetExplorationStateForNewProject` + logout 清理已覆盖全探索状态——本 story 的新增 state（`styleAnchorResult` / `styleAnchorTab` / `styleAnchorSelected` / `styleAnchorPasteText`）须同样纳入同一套清理范式，不得另建不被调用的清理函数。
>
> **边界严守**：只接设定卡页（含文风锚点入口）；**不接**引导/自由探索接线（7.5/7.6 已做）、章节创作页（Epic 4）、归档页（Epic 5）、通读视图（Epic 6）。不改 `apiFetch`/token/401/error 地基（仅**追加** storyApi 薄封装）；不碰后端；不引入新构建/打包/module。

1. **[设定卡从后端恢复到真实渲染]** 进入设定卡页时（`renderExploration` 探索页在 settle task result 或 `openStoryProfileFromBackend` 被调用后），前端须 `GET /api/projects/{projectId}/story-profile` 恢复待确认卡（`StoryProfileCardResponse`：12 内容字段 + `revision`/`changedFields`/`status`）。有 pending 卡则渲染后端数据；无待确认卡（后端 204）则 settling finish 正常完成，不作异常。替换 `buildFinalStoryProfile`（mock `collectStoryDraft`→关键词匹配 `buildFinalStoryProfile`）和 `confirmStoryProfileAndEnterChapter`（mock `window.setTimeout`→`confirmedStoryProfile` sessionStorage→`location.hash` 跳转章节页）的纯前端 mock 逻辑。

2. **[直接编辑字段落库]** 用户在设定卡中编辑任意字段（`data-final-profile-field` contenteditable）→ `PATCH /api/projects/{projectId}/story-profile` 写值（body 只含改动的字段，`revision` 不变如后端 AC2）。成功以返回的权威行更新 `finalStoryProfile` 并重新渲染（保留用户已填内容）；失败（如 404 `no_pending_card`）按 `err.code` 分支呈现集中错误。

3. **[反馈升版本真实 Agent]** 用户在「你想调整什么？」textarea 提交反馈 → `POST /api/projects/{projectId}/story-profile/revise`（body `{feedback}`，**同步 REST、非 ARQ**，受控决策 2）。后端真实凝练 Agent 重生成候选卡、`revision` 递增 + `changedFields` 列表返回（`StoryProfileCardResponse`）。前端用 `changedFields` 数组 `is-updated` 高亮「Agent 改了哪些」（保持原型 `data-final-profile-field` `is-updated` 约定）；处理中按钮 `disabled` + 文案「调整中…」（替换 `window.setTimeout(...,520)` mock）；`feedback` 为空时前端 `422` 或后端 `422` 均不提交（表单与后端 dual validate）。

4. **[确认设定 → 只读圣经 + 推进 phase]** 用户点「确认故事设定」→ `POST /api/projects/{projectId}/story-profile/confirm`（**无请求体**，幂等动作，受控决策 3）。后端翻 `status` `pending`→`confirmed` + `project.phase` `explore`→`chapter`（同一事务，Story 3.5 AC1）。成功后清 `pendingStoryProfile` + `clearPendingStoryProfile` + 跳转到第一章创作页（`location.hash = "#/projects/${projectId}/chapters/1"`）。替换 `confirmStoryProfileAndEnterChapter`（当前 mock `window.setTimeout`→`confirmedStoryProfile` sessionStorage→`location.hash` 跳转硬编码 `demo` 作品 id）。

5. **[「回到探索」二次确认 + 后端丢弃]** 用户在设定卡点「回到探索页面」→ 出现二次确认弹窗（原型已有 `data-profile-return-confirm`），选「取消」保留现状、选「确定返回」调 `POST /api/projects/{projectId}/story-profile/discard`（幂等：无卡也 204）。后端删 pending 行（仅 pending，confirmed 只读圣经/ draft 半成品行不受影响）。成功后清掉前端状态并回探索页（`discardStoryProfileAndReturn` + `renderExploration`）。

6. **[文风锚点入口（UX-DR1 · 须新增 UI）]** 在设定卡阶段新增「从预置样本库选择/粘贴一段爱读文字」的锚点入口。提供两种锚定方式：① 库选 `GET /api/projects/{projectId}/style-anchor/samples`（全局样本库，后端单一事实源）、选择后 `POST /api/projects/{projectId}/style-anchor`（body `{sampleId}`，后端查库原文抽取）；② 粘贴 `POST /api/projects/{projectId}/style-anchor`（body `{sampleText}`，后端直接抽取）。抽取后 `style_profile` 五维（人称/语气/句式节奏/意象密度/段落长度倾向）写入 `story_bible`（`upsert_style_profile`），随 `StoryProfileCardResponse.styleProfile` 返回。前端在设定卡第⑫字段展示文风锚点结果（替换当前原型 mock `styleAnchorResult` 占位）；未锚定时视为可空/默认风格（不阻塞出设定）。

7. **[待确认卡会话内恢复]** 设定卡在浏览器会话内恢复：刷新页面不回退到探索主界面，恢复待确认态（`pendingStoryProfile=true` + `GET story-profile` 返回真实卡，非 mock 构造）。`persistPendingStoryProfile`/`readPendingStoryProfile` 在已有 sessionStorage 恢复机制上只改来源——profile 数据源从 mock 换成后端 `StoryProfileCardResponse`。

8. **[错误码映射与多租户]** 后端拒绝/失败时前端按 `err.code`（和 SSE `data.code`）精确映射中文提示：`no_pending_card`（无待确认卡——注意：确认后设定翻 `confirmed`，编辑/反馈端对 confirmed 行**也返 `no_pending_card`**，因为后端 `get_pending_by_project` 只查 `status='pending'`，无独立 `already_confirmed` 码）、`project_not_found`/404（越权/不存在，二义合一）、`unknown_style_sample`（样本库选 id 无效）、`generate_failed`（抽取/反馈失败）、`quota_exceeded`（额度耗尽引导绑 Key）。多租户隔离由后端 `CurrentUser` + `get_owned_project` 强制过滤；前端不传 `userId`、不自行判断资源归属。

9. **[租户、模式与边界]** 前端不传 `userId` 或自行判断资源归属；越权/不存在同码 404；`project_id` 从路由解析（消费 `#/projects/{id}` 路由 id）。**本 story 不修改 Epic 3 后端**（不新增/不重复实现 story-profile 端点或 style-anchor 端点——那属 3.2/3.4/3.5 职责）；不新增前端构建工具/module/路由级守卫；不把 API 业务数据放入 `localStorage`/`sessionStorage`（仅 `muse-pending-story-profile` 等已有 UI 态 key 例外——符合 AR4「前端 storage 仅存 UI 态」约束）。

## Tasks / Subtasks

- [x] **Task 1：storyApi 薄封装（api.js 追加，仿 explorationApi）**（AC: 1, 2, 3, 4, 5, 6）
  - [x] 在 `prototype/app/api.js` 追加 `storyApi` 对象（仿 `explorationApi`/`byokApi` 风格，`window` 暴露）：
    - `getProfile(projectId)` → `apiFetch(`/api/projects/${projectId}/story-profile`)`（返 `StoryProfileCardResponse` 或 204→null）
    - `editProfile(projectId, fields)` → `apiFetch(..., {method:"PATCH", body:fields})`（只传改动的字段，`revision` 不变）
    - `reviseProfile(projectId, {feedback})` → `apiFetch(..., {method:"POST", body:{feedback}})`（同步 REST，非 ARQ）
    - `confirmProfile(projectId)` → `apiFetch(..., {method:"POST"})`（无请求体）
    - `discardProfile(projectId)` → `apiFetch(..., {method:"POST"})`（幂等 204）
    - `listStyleSamples(projectId)` → `apiFetch(`/api/projects/${projectId}/style-anchor/samples`)`（返 `[{id,name,note,excerpt}]`）
    - `anchorStyle(projectId, {sampleId?, sampleText?})` → `apiFetch(..., {method:"POST", body:{...}})`（返 `{styleProfile, anchored}`）
  - [x] 常规 CRUD 全走 `apiFetch`（默认 auth=true），不新建 SSE/EventSource/第二套请求工具。
  - [x] 更新 `api.js` 端点注释与 `window` 暴露块。

- [x] **Task 2：设定卡恢复与渲染替换 mock**（AC: 1, 7）
  - [x] 改造 `openStoryProfileFromBackend`（app.js:1569-1579）：将入参 `profile` 从 `StoryProfileCard`（settle SSE `result.profile`，仅 12 内容字段）扩展为可接受 `StoryProfileCardResponse`（含 `revision`/`changedFields`/`status`）；`finalStoryProfileRevision` 从后端读取 `revision`（非硬编码 1）；`lastProfileChangedFields` 从后端 `changedFields` 初始化（非空数组）。
  - [x] `buildProfileFromBackend`（app.js:1551-1565）：字段渲染逻辑保持 PROFILE_FIELD_LABELS 12 字段顺序（已正确），只新增对 `revision`/`changedFields` 的消费——`lastProfileChangedFields` 从后端 `changed_fields` 列名映射到前端 `PROFILE_FIELD_LABELS` 索引（`data-final-profile-field` 按序编号 `0..11`）。
  - [x] `storyProfileDialogMarkup`（app.js:1581-1610）：头部 `v${finalStoryProfileRevision}` 从后端 `revision` 读取（非 mock `finalStoryProfileRevision`）；反馈区「调整中…」替换为真实按钮 `disabled`+文案（~0.5-2s 同步 REST，受控决策 2，不用 `setTimeout`）。
  - [x] 删除 mock 函数：`collectStoryDraft`（app.js 扫描 `explorationHistory`/`freeConversation` 生成 mock 12 字段，当设定卡不展示时无用）、`buildFinalStoryProfile`（mock 关键词匹配 `applyStoryProfileFeedback`，当 `reviseProfile` 后端 Agent 已替换时不调用）。
  - [x] **注意**：`openStoryProfileFromBackend` 和 `buildProfileFromBackend` 在 `app.js` 中已被 7.5/7.6 调用（从 settle SSE `result.profile`）。本 story 重写后必须保持向后兼容——`profile` 入参 `revision`/`changedFields`/`status` 字段可选（缺省时用默认 1/[]/"pending"），保证 7.5/7.6 的调用方不因本改动挂掉。

- [x] **Task 3：直接编辑字段落库接线**（AC: 2）
  - [x] 改造 `bindStoryProfileDialogInteractions`（app.js:1719-1772）的 `[data-final-profile-field]` 监听：
    - `input` 事件 → 收集所有改动字段（比较当前 `finalStoryProfile[index].value` 与原始 `textContent.trim()`）→ `storyApi.editProfile(projectId, fields)` 落库。
    - 成功 `StoryProfileCardResponse` → 更新 `finalStoryProfile` 各字段值（后端权威）并重绘（`mountStoryProfileDialog` 重渲染以更新 `is-updated` 等 UI）。
    - `revision` 直接编辑不变（后端 AC2，写值不 bump `revision`）——前端不重新计算 `finalStoryProfileRevision`。
  - [x] **防重复**：提交中 `button disabled` + `aria-busy`，避免快速连续编辑并发双 PATCH。
  - [x] **error 映射**：`no_pending_card`（无待确认卡）→ 提示 + 保留本地输入不清除；`project_not_found`→回作品库。

- [x] **Task 4：反馈升版本真实 Agent 接线**（AC: 3）
  - [x] 改造 `bindStoryProfileDialogInteractions` 的 `[data-profile-feedback]` submit：
    - `event.preventDefault` → 校验 `feedback` 非空（前端+后端 dual validate）→ `storyApi.reviseProfile(projectId, {feedback})`。
    - 成功 `StoryProfileCardResponse` → `finalStoryProfileRevision = response.revision`（后端 `+1`）；`lastProfileChangedFields` = 据 `response.changedFields` 映射的 `index` 数组 → `mountStoryProfileDialog` 重绘（`is-updated` 高亮）。
    - 失败 → `profileFeedbackStatus` 设错误文案（如 `generate_failed`/`quota_exceeded`）；按钮恢复（不保持 disabled）。
  - [x] 处理中按钮 `disabled` + 文案 `调整中…`（替换 `window.setTimeout(()=>{...}, 520)` mock，保持同上同步 REST）。
  - [x] **删除 mock**：`applyStoryProfileFeedback`（app.js:1687-1700+）——mock 关键词匹配 `includesAny`→`apply` 写 `finalStoryProfile[index].value`，已被后端真实凝练 `StoryProfileCardResponse.changed_fields` 取代。

- [x] **Task 5：确认设定与回到探索丢弃接线**（AC: 4, 5）
  - [x] 改造 `[data-confirm-profile]` click（app.js:1763-1771）：
    - `event.currentTarget.disabled = true` + `"✓"` → `storyApi.confirmProfile(projectId)`（无请求体）。
    - 成功 → `confirmedStoryProfile = finalStoryProfile.map(...)`（本地缓存只读副本）；`clearPendingStoryProfile`；`project.phase` 推进 `explore→chapter`（后端同一事务已做，前端只消费）；跳 `location.hash = "#/projects/${projectId}/chapters/1"`（替换硬编码 `demo`）。
    - 失败（如 `no_pending_card`/404）→ 恢复按钮 + 提示；不跳转。
  - [x] 改造 `[data-confirm-profile-return]` click（app.js:1761-1762，`discardStoryProfileAndReturn`）：
    - 保留二次确认弹窗（`data-profile-return-confirm`，原型已有），**删除确认**按钮调 `storyApi.discardProfile(projectId)`（幂等 204）。
    - 成功后 `discardStoryProfileAndReturn` 只清前端状态 + `renderExploration`；不调后端（后端已 discard，part of 同一个按钮流程）。
    - `[data-cancel-profile-return]` click → 保留前端不变，不触后端（与原型一致）。
  - [x] **替换 mock**：`confirmStoryProfileAndEnterChapter`（app.js:1640-1659）当前 mock `window.setTimeout`→`confirmedStoryProfile` sessionStorage→`location.hash` 硬编码跳转。改为消费 `storyApi.confirmProfile` 真实 `project_id`。
  - [x] **关键事实纠正（settle 已落库，非 emit-only）**：`worker.py:132` 的注释「emit-only 不写 story_bible」是 **3.3 时代的陈旧注释**；实际 3.4 起 `story_settle_agent.settle_into_profile`（worker 实际调用的函数）**既落库 pending 卡又推 SSE**（story_settle_agent.py:13-16、338、428）。因此：**只要 settle 完成弹出过候选卡，后端就有一行 `status='pending'` 的 `story_bible`**——引导（7.5）和自由（7.6）两条 settle 链都如此。这意味着「回到探索」丢弃**必须调后端 `discard`**（后端确有 pending 行要删），不能只做前端复位。
  - [x] **改造 `discardStoryProfileAndReturn`（app.js:1617-1638）**：这是 7.5 遗留、归 7.7 补的债——7.5 当时基于「settle emit-only 无落库副作用」的**过时理解**，只做了前端 `abort`+清 pending、没调后端 discard（7.5 注释 app.js:1626-1628 明说「已确认设定的真实丢弃 FR15 归 7.7」）。本 story 补上：`data-confirm-profile-return`「确定返回」→ **先 `await storyApi.discardProfile(projectId)`**（后端删 pending 行，幂等 204 即使无卡也安全）→ 再做既有前端复位（清 `finalStoryProfile`/`pendingStoryProfile`/`clearPendingStoryProfile`/`closeStoryProfileDialog`/`renderExploration`）。保留既有的 settle SSE `abort`（若 settle 还在途被点回到探索，先 abort 断流再 discard）。
  - [x] **不必区分「settle 前收尾态」与「弹卡后」两场景**：settle 一旦触发就落库 pending，前端 `pendingStoryProfile` 也随 `openStoryProfileFromBackend` 置 true——两态一致。因此本 story 统一：`discardStoryProfileAndReturn` 无条件调 `storyApi.discardProfile`（幂等，无 pending 行后端也返 204，不报错）。若担心 settle 未落库完成就点回到探索的竞态，`discard` 幂等语义已兜住（删不到行也 204）。


- [x] **Task 6：文风锚点入口（UX-DR1 · 全新 UI）**（AC: 6）
  - [x] 在设定卡对话框（`storyProfileDialogMarkup`）或设定卡所在页（`renderExploration` profile 段）新增文风锚点区：
    - **样本库 tab**：`GET /api/projects/{projectId}/style-anchor/samples` 渲染 3 个预置样本卡片（`StyleSampleResponse`：`{id, name, note, excerpt}`）供选择；当前选中高亮（`styleAnchorSelected`）。替换原型 mock `styleSampleLibrary`（app.js:1940-1954 写死的 3 个样本）。
    - **粘贴 tab**：textarea 粘贴用户自己的文风样本（`minlength=20`，前端+后端 dual validate；`max_length=4000` 已经在 schema 层拦）。
    - **提交抽取**：库选 `POST style-anchor` body `{sampleId}`；粘贴 `POST style-anchor` body `{sampleText}`。成功后 `StyleProfileResponse.styleProfile` → 写入 `finalStoryProfile` 第⑫字段（`styleProfile`）+ 展示五维结果（`styleAnchorResult`）。
  - [x] 处理中态（`styleAnchorSaving`）+ 错误分支（`unknown_style_sample`/`generate_failed`/`quota_exceeded` 按 `err.code` 中文提示）。
  - [x] `project_id` 从当前路由 `#/projects/{id}` 解析（同 7.3/7.5/7.6 的模式）。
  - [x] **注意**：文风锚点入口可能出现在两处——① 设定卡对话框内（`storyProfileDialogMarkup`，弹窗态）；② 探索页 profile 段（`renderExploration` profile 态，在这个状态下 `pendingStoryProfile=true` 待确认卡已弹出）。两处共享同一套状态变量 + 同一套 `storyApi` 调用，不写两份代码。
  - [x] **移除原型的 mock 数据源**：`styleAnchorResult` mock（app.js `buildStyleProfile`、`styleAnchorProfileMarkup`、`styleSampleLibrary` 写死 3 样本）——替换为真实后端 `GET samples` + `POST style-anchor` 的结果。

- [x] **Task 7：错误码映射与状态清理**（AC: 8, 9）
  - [x] 扩展或新增设定卡错误码映射（如 `storyErrorText(err)`），至少精确映射：`no_pending_card`（含 confirmed 后编辑/反馈的情形，后端无独立 `already_confirmed` 码）、`unknown_style_sample`、`generate_failed`、`quota_exceeded`、`project_not_found` + 中性兜底（如 `网络中断，请稍后重试`）。只按 `err.code` 判定（后端恒字符串）。
  - [x] `teardownExplorationInflight`（app.js:621-632）已 abort 所有探索 SSE + settle controller + 清 pending。本 story 新增的 `styleAnchorResult`/`styleAnchorTab`/`styleAnchorSelected`/`styleAnchorPasteText`/`styleAnchorSaving` 在清理时一同复位（`resetExplorationStateForNewProject` + logout 清理已覆盖探索全状态，新增状态变量追加进去即可——不要另建新的清理函数）。
  - [x] logout 时清 `finalStoryProfile`/`pendingStoryProfile`/`confirmedStoryProfile` 及所有设定卡相关状态（已有 `clearPendingStoryProfile` + `app.js` logout 块覆盖，确认不遗漏）。
  - [x] 确保所有异步回调（`editProfile`/`reviseProfile`/`confirmProfile`/`discardProfile`）在操作完成前重新校验 `projectId`（当前路由 `#/projects/{id}` 未变）——防用户在操作过程中切换作品后旧回调写错数据。

- [x] **Task 8：联调冒烟与零回归验证**（AC: 全部）
  - [x] 起真实后端（`MUSE_DB_READY=1` + Redis via Colima，`:8000`）+ 原型静态 `:4173`（`cd prototype/app && python3 -m http.server 4173 --bind 127.0.0.1`）；经 7.2 注册/登录建测试账号。
  - [x] 浏览器真实走通（登录后，新建**自由模式**作品，进入自由探索并与 Agent 对话到 7 项主干齐备后点「整理为故事设定」→ settle SSE 弹设定卡）：① 设定卡恢复真实后端数据（含 `revision`/`changedFields`）；② 编辑任一字段 → `PATCH` 落库 + 刷新重绘；③ 填写反馈 → `POST revise` 升版本 + `is-updated` 高亮；④ 确认设定 → `POST confirm` + `phase` explore→chapter + 跳转第一章；⑤ 「回到探索」二次确认 → `POST discard` 后端丢弃 + 回探索页；⑥ 文风锚点入口：选样本库/粘贴样本 → `POST style-anchor` 抽取五维 `styleProfile` → 展示在设定卡第⑫字段；⑦ 刷新页面 → 待确认卡恢复；⑧ 断后端/改坏请求 → 错误态可重试。
  - [x] **多租户验证**：A 在设定卡编辑后，B 登录 → 只见自己的设定卡（后端 `user_id` 强制过滤，前端不传 `userId`）。
  - [x] **前端零回归**：登录/注册/退出（7.2）、作品库（7.3）、BYOK/用量（7.4）、引导探索（7.5）、自由探索（7.6）均正常；`node --check api.js && node --check app.js` 通过；`git status backend/` 干净（本 story 前端 only）。
  - [x] **若本机仍无法使用 Playwright/Chromium，必须如实写入 Completion Notes，不得将 Node/curl 验证宣称为浏览器 UI 验证**（同 7.5 Task 8 缺口记录，7.6 已解决——本 story 优先用真实浏览器验证；若环境不具备，则明确记录缺口）。核心风险（API 契约/纯逻辑/错误码映射）已用 Node 原生 fetch + 后端 curl 端到端覆盖。

- [x] **Task 9：收尾**
  - [x] 更新 `deferred-work.md`：勾除/更新「设定卡编辑/反馈升版本/确认/丢弃/文风锚点前端接线」（deferred-work.md:185-193）为已由 7.7 兑现；登记本 story 新发现的 defer（如文风锚点入口需在弹窗态/探索页 profile 段两处共现）。
  - [x] 前端语法检查：`node --check prototype/app/api.js && node --check prototype/app/app.js`。
  - [x] 提交：按 [[feedback_timely_commit]] 在 story 完成且 review 通过后提交，不急在工作区积压。

## Review Findings

（2026-08-04 code review：盲审猎手 + 边界猎手 + 验收审计 三层并行，全部返回无失败层。8/9 条 AC 实现到位，唯 AC2 核心链路存在被三层独立确认的静默失效。）

- [x] [Review][Patch] 【高·CONFIRMED】直接编辑字段的 PATCH 永不触发，AC2 核心链路静默失效 [prototype/app/app.js:1957] — `input` 监听器（app.js:2050）每次击键把 `finalStoryProfile[key].value` 同步为 DOM `textContent`；`collectProfileFieldEdits`（app.js:1957）又拿 `next !== field.value` 与同一对象比对做变更基线 → input 已把二者拉平 → `changes` 恒空 → `persistProfileFieldEdits`（app.js:1970）在 `Object.keys(changes).length===0` 提前 return，PATCH 永不发送。真实键盘编辑字段 blur 后不落库，刷新/reconcile/confirm 后编辑全丢。三层（盲审#1/边界#1/验收#1）独立确认；对照 7.6 用 `data-free-clue-value` DOM 属性快照做基线（app.js:2592）才能落库，7.7 移植范式时把基线换成被 input 改写的 JS 对象值。Dev Record 声称 Playwright「编辑 blur→PATCH 14/14」通过，疑因自动化直接 set textContent 绕过 input 事件而误过——须用真实按键（pressSequentially）复测。修复：变更基线改用独立于 input 的「上次已落库值」快照（如渲染时写 `data-final-profile-value` DOM 属性，仿 7.6）。
- [x] [Review][Patch] 【中·CONFIRMED】修复上一条后暴露：编辑落库回包重挂会吞掉其它字段未保存输入 [prototype/app/app.js:1990] — `persistProfileFieldEdits` 的 `while` 循环每轮 PATCH 返回即 `openStoryProfileFromBackend(card)` 整体重建 `finalStoryProfile` + 重挂 DOM。字段 A 的 PATCH 在途时用户在字段 B 输入（未 blur）→ 回包重挂 → B 的未保存文本与光标被后端权威值冲掉。当前被高优先级#1掩盖（PATCH 根本不发），修#1 时必须一并处理（如重挂时保留正在编辑字段的本地值，或仅局部更新非编辑中字段）。盲审#4/边界#2。
- [x] [Review][Patch] 【中·CONFIRMED】`submitStyleAnchor` 两段 await 间提前置 `styleAnchorSaving=false`，打开并发双提交窗口 [prototype/app/app.js:1744] — anchorStyle 成功后、editProfile 仍在途时就复位 saving 门禁且未重绘；paste input 监听（app.js:1788）`extract.disabled = ...||styleAnchorSaving` 因 saving=false 把「抽取文风」重新启用 → 再点时顶部 `if(styleAnchorSaving)return`（app.js:1724）失效 → 与在途 editProfile 并发。修复：saving 应在第二段 editProfile 完成后（或 finally）才复位。盲审#2/边界#4。
- [x] [Review][Patch] 【中·CONFIRMED】样本库拉取失败被固化为永久空态，同一作品内无法重试 [prototype/app/app.js:1712] — `loadStyleSamplesIfNeeded` 用 `styleAnchorSamples !== null`（app.js:1702）判「已拉过」，但 catch 置 `[]`（app.js:1712）而非 null → 首次网络抖动失败后永久停在「暂无可选样本」，只有切作品才复位。修复：catch 保持 `null`（或引入独立错误态）以允许重试。盲审#3。
- [x] [Review][Patch] 【中·CONFIRMED】文风抽取「第一段成功、第二段失败」前后端不一致 [prototype/app/app.js:1745] — anchorStyle 已把 style_profile 落库（返 `anchored`），随后 editProfile 失败仅显「抽取失败」；刷新/reconcile 后第⑫字段却显示已锚定 → 用户所见与真实落库相反。修复：第二段失败时用第一段返回的 styleProfile 乐观写入第⑫字段，或提示「已锚定但同步失败」。边界#5。
- [x] [Review][Patch] 【中·PLAUSIBLE】文风抽取在途时 discard「确定返回」→ 被丢弃的设定卡被复活/带错误重挂 [prototype/app/app.js:1837] — `discardStoryProfileAndReturn` 既不 abort 文风请求也不改 hash、不复位 `styleAnchorSaving`；在途 anchorStyle/editProfile 回包时 hash/projectId 守卫放行 → `openStoryProfileFromBackend` 重挂已丢弃弹窗，或 no_pending_card 落 catch 后 `mountStoryProfileDialog` 重挂带错误的弹窗。修复：discard 时引入 saving 代次守卫或标记，使在途文风回调识别到卡已丢弃而不重挂。边界#3。
- [x] [Review][Patch] 【低·PLAUSIBLE】confirm 与 discard 并发 → `finalStoryProfile.map` 空指针 [prototype/app/app.js:1923] — 点「确认」（confirm 在途）后立即点「回到探索→确定返回」（discard 在途），若 discard 先 resolve 置 `finalStoryProfile=null`，confirm 后 resolve 且 hash 未变 → `finalStoryProfile.map(...)`（app.js:1923，在 try/守卫之外）抛未捕获 TypeError。触发窗口窄（两模态按钮各自在途期间交替点、且 discard 先完成）。修复：map 前判空或纳入 try。边界#7。
- [x] [Review][Patch] 【低·PLAUSIBLE】`submitProfileFeedback` 对 revise 返回 null/空体无守卫 → TypeError [prototype/app/app.js:2026] — `openStoryProfileFromBackend(card)` 自身对 null 安全，但紧接 `Array.isArray(card.changedFields)`（app.js:2026）前一行已用 null-unsafe 的 `openStoryProfileFromBackend(null)` 把卡重建为占位；若 revise 异常返 204/空（apiFetch→null）则 `card.changedFields` 前的 `openStoryProfileFromBackend(null)` 丢失用户内容。对比 submitStyleAnchor/persistProfileFieldEdits 均有 `if(card)` 守卫，此处漏。契约上 revise 恒 200，故 PLAUSIBLE。修复：加 `if(card)` 守卫，仿其它调用点。边界#6。
- [x] [Review][Patch] 【低】discard 未复位文风区展开态 `styleAnchorPanelOpen/Tab/Samples` [prototype/app/app.js:1877] — `discardStoryProfileAndReturn` 复位了 Result/Selected/PasteText/ErrorText，漏了 PanelOpen/Tab/Samples；同会话再 settle 弹卡时面板自动展开带旧残留。边界#8。
- [x] [Review][Patch] 【低】discard 后只 `renderExploration` 不重载引导会话，已答进度显示丢失 [prototype/app/app.js:1888] — 刷新后内存 explorationHistory 为空、卡由 sessionStorage 恢复，此时 discard 只 renderExploration 不调 loadGuidedExploration/loadFreeExploration → 回探索页显示第 1 题空白（对比 reconcile 的 204 分支会 loadX 重载）。边界#9。
- [x] [Review][Patch] 【低】`loadStyleSamplesIfNeeded` 收尾重挂不校验当前 tab，打断粘贴输入焦点 [prototype/app/app.js:1716] — 库 tab 触发拉取后切到粘贴 tab 打字，样本返回仍 `mountStoryProfileDialog` 重挂 → 值不丢但光标跳失。边界#10。
- [x] [Review][Patch] 【低·清理】`styleAnchorResult` 已成只写死变量 [prototype/app/app.js:205] — 删除旧 renderStyleAnchor 后无任何读取点（真实结果改从 finalStoryProfile 第⑫字段 currentStyleProfileValue 取），仅剩声明 + 3 处 null 复位。无功能影响，可一并清理。盲审#5/边界#11/验收#3。
- [x] [Review][Patch] 【低·偏离】编辑失败错误呈现落在「反馈」区状态行而非字段编辑区 [prototype/app/app.js:2003] — `persistProfileFieldEdits` catch 把 no_pending_card 等写入 `profileFeedbackStatus`（「你想调整什么？」反馈区状态行），语义上「编辑落库失败」错位显示在「反馈」区。spec 允许集中错误，可接受，酌情调整。验收#4。

### Review Fix 小结（2026-08-04 应用全部 13 项）

三层审查 13 项 patch 全部修复，`node --check api.js && app.js` 通过。关键改动：

- **#1（高·核心）**：变更基线从被 input 逐键改写的 `finalStoryProfile[].value` 改为渲染时写死的 DOM 属性快照 `data-final-profile-value`（仿 7.6 `data-free-clue-value`），`collectProfileFieldEdits` 用 `el.dataset.finalProfileValue` 比对——真实键盘编辑 blur 现能正确检出改动并发 PATCH。
- **#2**：`openStoryProfileFromBackend` 重建前捕获正在编辑（`document.activeElement`）字段的本地文本，重建后回写该字段值并 `restoreProfileFieldFocus` 恢复焦点+光标到末尾，防 PATCH 回包冲掉未 blur 字段的输入。
- **#3+#5+#6（submitStyleAnchor 重写）**：删中间提前的 `styleAnchorSaving=false`、统一在 finally 复位（#3）；catch 用 `anchoredStyle` 乐观回写第⑫字段+persist（#5）；引入 `styleAnchorSeq` 代次守卫，`stale()` 三重校验 hash/projectId/seq（#6）。
- **#4**：`loadStyleSamplesIfNeeded` catch 保持 `styleAnchorSamples=null`（而非 `[]`）+ 设错误提示，允许重试。
- **#7**：`confirmStoryProfileAndEnterChapter` 在 `finalStoryProfile.map` 前加 `if(!finalStoryProfile)return` 判空。
- **#8**：`submitProfileFeedback` 对 revise 返回加 `if(card)` 守卫，空体不重建占位。
- **#9+#10**：`discardStoryProfileAndReturn` 补齐 `styleAnchorPanelOpen/Tab/Samples/SamplesLoading` 复位、开头递增 `styleAnchorSeq`+复位 `styleAnchorSaving`；末尾按 `explorationEntryMode` 调 `loadGuidedExploration`/`loadFreeExploration` 重载会话。
- **#11**：`loadStyleSamplesIfNeeded` 收尾重挂条件加 `styleAnchorTab==='library'`。
- **#12**：删除死变量 `styleAnchorResult`（声明 + `resetExplorationStateForNewProject`/logout/discard 三处复位）；后两处顺带补 `styleAnchorSeq += 1`。
- **#13**：`persistProfileFieldEdits` catch 编辑失败改用 `window.alert`（与 `project_not_found` 分支/discard 失败一致），不再借反馈区状态行。

**复测提醒**：#1 是真实键盘交互下才暴露的静默失效，Dev Record 的 Playwright「14/14」疑因直接 set textContent 绕过 input 事件误过。回归验证务必用真实按键（`pressSequentially`/`type`）走一遍「编辑字段→blur→确认 PATCH 发出且刷新后保留」。

## Dev Notes

### 边界与依赖

- **依赖已满足：** 7.1 `apiFetch`/token/401/error 边界；7.2 真实会话；7.3 projects 与路由 id；7.4 `byokApi`/`usageApi`；7.5 `apiStream`、`explorationApi`、`taskEvents`、`openStoryProfileFromBackend`、`buildProfileFromBackend`、`persistPendingStoryProfile`/`readPendingStoryProfile`；7.6 自由探索接线（含 `teardownExplorationInflight`、`resetExplorationStateForNewProject`、logout 清理）。后端：`story_bible` 表（3.1）、`style_profile` 抽取（3.2）、候选卡编辑/反馈升版本/确认/丢弃（3.4/3.5）、文风样本库（3.2）均已 done。
- **本 story 交付：** 前端 `api.js` 的 `storyApi` 薄封装 + `app.js` 设定卡页的真实接线（恢复/编辑/反馈/确认/丢弃）+ 文风锚点入口全新 UI（UX-DR1）。为保持真实结果，允许对 7.5/7.6 的已建函数做小范围扩展（如 `openStoryProfileFromBackend` 消费 `revision`/`changedFields`），但必须保持向后兼容（7.5/7.6 调用方不因本改动挂掉）。
- **不做：** 不改 backend、schema、迁移、Provider、ARQ、SSE 服务器；不修 `apiStream` 的末帧 flush/整体超时/自动重连；不接章节创作页（Epic 4）、归档页（Epic 5）、通读视图（Epic 6）；不新增全局路由鉴权、模块化/打包、UI 新页面或第二个请求工具。

### 前后端契约（已从真实代码核实）

所有常规响应直接返回 camelCase 资源体；HTTP 失败是 `{code,message,detail}`。所有项目资源从 Bearer 当前用户派生租户，不传 `userId`。文风锚点抽取**是同步 REST**（非 SSE/ARQ），受控决策 2；确认/丢弃也是同步 POST（无请求体）。

| 目的 | 方法与路径 | 请求 | 成功响应 | 代码依据 |
|---|---|---|---|---|
| 取待确认候选卡 | `GET /api/projects/{projectId}/story-profile` | 无 | `200 StoryProfileCardResponse`（12 字段+revision/changedFields/status）；无卡 `204` | `routers/story.py:100-121`; `schemas/story.py:104-133` |
| 直接编辑字段 | `PATCH /api/projects/{projectId}/story-profile` | `{genre?, coreAppeal?, ...}` 只传非 None 字段 | `200 StoryProfileCardResponse`；`revision` 不变；无卡 `404 no_pending_card` | `routers/story.py:124-143`; `schemas/story.py:148-176` |
| 反馈升版本 | `POST /api/projects/{projectId}/story-profile/revise` | `{feedback}`（1-2000 字） | `200 StoryProfileCardResponse`；`revision` +1、`changedFields` 返 | `routers/story.py:146-165`; `schemas/story.py:135-146` |
| 确认设定 | `POST /api/projects/{projectId}/story-profile/confirm` | 无 | `200 StoryProfileCardResponse`（`status="confirmed"`）；同事务推 `project.phase` explore→chapter | `routers/story.py:168-188` |
| 回到探索丢弃 | `POST /api/projects/{projectId}/story-profile/discard` | 无 | `204`（幂等：无卡也 204） | `routers/story.py:191-209` |
| 列出文风样本 | `GET /api/projects/{projectId}/style-anchor/samples` | 无 | `200 [{id, name, note, excerpt}]`（全局常量、非用户数据） | `routers/story.py:46-64`; `schemas/story.py:60-70` |
| 文风锚点抽取 | `POST /api/projects/{projectId}/style-anchor` | `{sampleId?}` 或 `{sampleText?}`（互斥） | `200 StyleProfileResponse {styleProfile, anchored}` | `routers/story.py:67-97`; `schemas/story.py:22-57` |

### 设定卡状态机

- **draft**（缺省值）：`story_bible` 行刚建但未整理出候选卡（如 3.2 只锚了文风 `upsert_style_profile` 建行却还没有 settle 凝练）。`get_pending_card` **不返** draft 行（3.4 已 fix：`get_pending_by_project` 只查 `status='pending'`，code review fix），前端不会看到 draft 卡。
- **pending**：3.3 settle 凝练落库的待确认候选卡（可编辑/反馈/确认/丢弃/刷新恢复）。
- **confirmed**：3.5 确认后的只读设定圣经（编辑/反馈端对 confirmed 行天然 `404 no_pending_card`，后端硬拒绝）。

**settle 已落库（关键，纠正 worker 陈旧注释）**：`worker.py:132` 写「emit-only 不写 story_bible」是 3.3 时代注释；实际 worker 调 `settle_into_profile`（story_settle_agent.py:325），该函数 3.4 起**既落库 pending 卡（`upsert_profile_card`）又推 SSE**（docstring:13-16、338、428）。所以 settle 完成后后端**必有一行 `status='pending'`**——`GET story-profile` 能取到、「回到探索」丢弃时必须调后端 `discard` 删它。引导（7.5）/自由（7.6）两条 settle 链同理。

确认后 `project.phase` 已由后端同一事务 push `explore→chapter`（`routers/story.py:185`），前端接 `/api/projects` 重拉就能看到新 phase。

### 数据流（端到端，自由探索 settle 路径）

```
自由探索完成 chase → POST /explore/free/settle → {taskId}
  → GET /api/tasks/{taskId}/events（SSE progress/result/error）
    → result {taskId, status:"settle_ready", profile:StoryProfileCard（12 字段, 仅内容, camelCase）}
      → openStoryProfileFromBackend(profile)（当前 7.5/7.6 已做，本 story 保留并扩展）
      → buildProfileFromBackend(profile) → finalStoryProfile [{label, value}]
      → mountStoryProfileDialog()（app.js:1680-1685）
      → 用户编辑 / 反馈 / 确认 / 丢弃 → storyApi.* 真实后端
```

### 文风锚点数据流

```
文风锚点入口（两 tab：库选/粘贴）
  → 库选：GET /style-anchor/samples → 渲染 3 样本卡片 → 用户选样本 → styleAnchorSelected=sampleId
  → 粘贴：用户输入样本文字 → styleAnchorPasteText
  → 提交：POST /style-anchor（body {sampleId} 或 {sampleText}）
    → 成功 {styleProfile, anchored}
      → 写入 finalStoryProfile 第⑫字段（styleProfile）+ 展示五维结果
      → 或独立展示（styleAnchorResult，非 finalStoryProfile 内嵌）
    → 失败：unknown_style_sample / generate_failed / quota_exceeded
```

### 错误码映射（本 story 新接入的端点）

| code | 场景 | 前端行为 |
|---|---|---|
| `no_pending_card` | 编辑/反馈/确认时无待确认卡（含确认后 confirmed 行——后端无独立 `already_confirmed` 码） | 提示「没有待确认的设定卡，请先整理。」保留本地输入 |
| `unknown_style_sample` | 样本库选 id 无效 | 提示「所选文风样本不存在。」 |
| `generate_failed` | 反馈/文风抽取 LLM 空产 | 提示「生成失败，请稍后重试。」保留输入 |
| `quota_exceeded` | 反馈/抽取触顶 | 提示额度耗尽并引导到 7.4 设置页绑 Key |
| `project_not_found` / 404 | 越权或不存在 | 中性提示，回作品库（不区分不存在与越权） |

### 前端代码锚点（已实现的关键路径，不可破坏）

- **必须保留的交互：** `storyProfileDialogMarkup` 的 `data-final-profile-field` contenteditable（`app.js:1589`）；`profile-feedback` form（`app.js:1600`）；`profile-return-confirm` 二次确认（`app.js:1606`）；`data-confirm-profile` 确认（`app.js:1605`）；`data-request-profile-return` 回到探索（`app.js:1605`）。所有交互保持原牌——只把数据源换成后端。
- **已有 settle 消费链（7.5/7.6 已建，不可重写）：** `settleGuided(projectId)` → `taskEvents(taskId)` → `result.profile` → `openStoryProfileFromBackend`；自由 `settleFree(projectId)` → 同 `taskEvents` → `openStoryProfileFromBackend`。本 story 只扩展 `openStoryProfileFromBackend` 消费更多字段（`revision`/`changedFields`），不重写 SSE 链。
- **sessionStorage 恢复（7.5 已建，不可重写）：** `persistPendingStoryProfile`（`app.js:251`）、`readPendingStoryProfile`（`app.js:243`）、`clearPendingStoryProfile`（`app.js:265`）。本 story 只改数据源——profile 从 mock `buildFinalStoryProfile` → 后端 `StoryProfileCardResponse`。
- **已有 mock 路径（必须删除）：** `collectStoryDraft`、`buildFinalStoryProfile`、`openStoryProfileDialog`（mock `setTimeout`+`collectStoryDraft`→`buildFinalStoryProfile`）、`confirmStoryProfileAndEnterChapter`（mock `window.setTimeout`→`confirmedStoryProfile` sessionStorage→`location.hash` 硬编码跳转）、`buildCurrentStagePlan`（mock `stagePlanningDraft` 硬编码 5 章）。
- **必须保留的原型交互：** `contenteditable` 字段渲染（`PROFILE_FIELD_LABELS` 12 字段映射）；反馈 form `submit`；`profile-return-confirm` 二次确认；`data-confirm-profile-return`「确定返回」需要 `projectId` 来调 `storyApi.discardProfile`。API 文本进入 HTML 必须复用 `escapeHtml`。

### 已有生命周期保护（7.5/7.6 已建）

- `teardownExplorationInflight`（`app.js:621-632`）已 abort guided interpret、free message、settle 流 + 清 pending。本 story 新增的 `styleAnchor*` 状态在此清理中一同复位（不要新建第二清理函数）。
- `resetExplorationStateForNewProject`（`app.js:2355-2419`）已清探索全状态。本 story 新增的 `finalStoryProfile`/`pendingStoryProfile`/`lastProfileChangedFields`/`profileFeedbackStatus`/`styleAnchor*` 新增进去。
- logout（`app.js:2422-2456`）已清 `finalStoryProfile`/`pendingStoryProfile`/`confirmedStoryProfile` + 调 `clearPendingStoryProfile`。本 story 新增的 `styleAnchor*` 状态追加进去。
- 异步回调以 `projectId`、代次、hash 三重校验（7.6 已建范式，本 story 复用）。

### 测试策略

- **纯逻辑：** 在 Node/vm 或既有可行方式断言：`storyApi` 薄封装方法/路径/body 组装（7 个端点）；`buildProfileFromBackend` 对 `StoryProfileCardResponse`（含 `revision`/`changedFields`）的字段映射 + `changedFields` 列名→`PROFILE_FIELD_LABELS` 索引映射；`storyErrorText` 错误码中文映射；`openStoryProfileFromBackend` 扩展（`revision`/`changedFields` 可选字段兼容）。
- **API 契约：** 用真实后端 + Node 原生 fetch 验证：`GET story-profile` 有卡 200/无卡 204；`PATCH story-profile` 返回 `revision` 不变；`POST revise` 返回 `revision` 递增 + `changedFields` 数组；`POST confirm` 推进 `phase`；`POST discard` 204 幂等；`GET samples` 3 样本；`POST style-anchor` 返回 `styleProfile`。
- **浏览器黄金路径：** 启 `make dev-up`（PG+Redis）+ 后端+ARQ worker + 静态前端 `:4173`；注册/登录后用自由模式真实作品完成 Task 8 的完整 walk through。UI 改动完成前应实际打开浏览器验证；若环境不具备，必须明确记录缺口。
- **回归：** `node --check prototype/app/api.js && node --check prototype/app/app.js`；`MUSE_DB_READY=1 uv run pytest -q`（本 story 不改后端，验证无意外回归）；7.2–7.6 全部冒烟（尤其 7.5 引导 settle SSE + 7.6 自由 settle SSE 不能回归）。

### 项目结构与开发环境

- 前端维持全局脚本：仅修改 `prototype/app/api.js`、`prototype/app/app.js`，需要样式时仅改现有 `prototype/app/styles.css`。不新增文件、模块或路由。
- API 外部字段已是 camelCase；前端直接读写 camelCase，禁止散落 snake_case 转换。前端 sessionStorage 只允许 UI 态并采用 `muse-` kebab-case key。
- 本机：`uv` 在 `~/.local/bin`，容器用 Colima；DB 测试前设 `MUSE_DB_READY=1`。设定卡编辑/反馈/确认/丢弃是同步 REST（非 ARQ/SSE），但自由探索 settle 还依赖 Redis + ARQ worker；真实 LLM 联调需要可用的 DeepSeek/或 BYOK 配置，注意成本。

### References

- [Source: `_bmad-output/planning-artifacts/epics.md:1274-1282`] — Epic 7 目标、依赖 `7.5→7.6→7.7`、只换数据源的原则
- [Source: `_bmad-output/planning-artifacts/epics.md:1472-1502`] — Story 7.7 原始 AC（设定卡+文风锚点接线）
- [Source: `_bmad-output/planning-artifacts/epics.md:147-159`] — UX-DR6（设定卡交互契约）与 UX-DR1（文风锚点入口须新增）
- [Source: `_bmad-output/planning-artifacts/architecture.md:275-358`] — camelCase 边界、前端 storage 约束、REST/SSE/error envelope 约束
- [Source: `backend/src/muse/routers/story.py:1-210`] — 7 个端点（samples/style-anchor/story-profile/edit/revise/confirm/discard）
- [Source: `backend/src/muse/schemas/story.py:1-177`] — `StoryProfileCardResponse` / `StoryProfileCard` / `StyleProfileResponse` / `StyleAnchorRequest` 的 camelCase 字段与边界
- [Source: `backend/src/muse/models/story_bible.py:1-113`] — `StoryBible` ORM（12 字段 + status/revision/changed_fields 三状态位）
- [Source: `backend/src/muse/services/style_anchor_agent.py:1-299`] — 文风锚点抽取逻辑（样本库+`style_profile` 抽取+`upsert_style_profile`）
- [Source: `backend/src/muse/services/story_settle_agent.py:1-567`] — 候选卡编辑/反馈升版本/确认/丢弃的逻辑（`get_pending_card`/`edit_profile_card`/`revise_profile_card`/`confirm_profile_card`/`discard_profile_card`）
- [Source: `prototype/app/api.js:472-587`] — 7.5/7.6 已交付的 `explorationApi`（含 settle 链）、`apiStream`、`apiFetch` ——本 story 复用这些地基
- [Source: `prototype/app/app.js:226-266`] — `persistPendingStoryProfile` / `readPendingStoryProfile` / `clearPendingStoryProfile` 的 sessionStorage 恢复机制
- [Source: `prototype/app/app.js:1567-1685`] — `openStoryProfileFromBackend` / `buildProfileFromBackend` / `mountStoryProfileDialog` / `storyProfileDialogMarkup` / `bindStoryProfileDialogInteractions` 的设定卡渲染与交互
- [Source: `prototype/app/app.js:1520-1565`] — `PROFILE_FIELD_LABELS` / `PROFILE_TRUNK_KEYS` / `buildProfileFromBackend` 的 12 字段映射（7.5 已建）
- [Source: `prototype/app/app.js:1607-1659`] — `discardStoryProfileAndReturn`（7.5 已建）+ `confirmStoryProfileAndEnterChapter`（mock，须替换）
- [Source: `prototype/app/app.js:621-632,2355-2456`] — `teardownExplorationInflight` / `resetExplorationStateForNewProject` / logout 的全局清理（7.6 已建）
- [Source: `_bmad-output/implementation-artifacts/7-5-引导探索接线SSE问答-翻页持久化-整理中过渡-设定卡弹出.md`] — 7.5 的 SSE 地基、`openStoryProfileFromBackend`、`persistPendingStoryProfile` 等已建函数（必须复用）
- [Source: `_bmad-output/implementation-artifacts/7-6-自由探索接线SSE对话-线索区编辑持久化-给方向-整理门禁.md`] — 7.6 的 `teardownExplorationInflight`、`resetExplorationStateForNewProject`、logout 清理、guidance 等已建函数（必须复用）
- [Source: `_bmad-output/implementation-artifacts/deferred-work.md`] — 已登记的 deferred 边界（7.7 应勾除相关条目）

## Dev Agent Record

### Agent Model Used

Claude Opus 4.8

### Debug Log References

- 前端纯逻辑离线断言（Node vm）：`storyApi` 7 端点方法/路径/body 组装 8/8；`snakeToCamel`/`buildProfileFromBackend`/`storyErrorText`/`styleProfileLinesMarkup` 15/15；`openStoryProfileFromBackend` 向后兼容（含/不含 `revision`/`changedFields`）5/5。
- API 契约端到端（真实后端 + Node fetch）：GET 无卡 204 / 有卡 200；PATCH revision 不变；GET samples；POST style-anchor 真实抽取五维（真实 LLM）；未知样本 400 `unknown_style_sample`；POST revise revision+1 + `changedFields`（真实 LLM）；空反馈 422；POST confirm status=confirmed + phase explore→chapter；confirmed 后 GET 204 / PATCH 404 `no_pending_card`；discard 幂等 204 —— 27/27。
- 多租户隔离：B 读/改 A 的设定卡均 404、A 读自己 200 —— 3/3。
- 真实浏览器 UI（Playwright + Chrome channel）：恢复后端真实卡、编辑 blur→PATCH 落库（revision 不变）、文风锚点样本渲染+真实 LLM 抽取写入第⑫字段+落库、反馈真实 LLM 升版本+头部版本号更新、确认→phase 推进+跳转第一章、回到探索二次确认→后端 discard 204 —— 功能断言 14/14（唯一 favicon.ico 404 为静态服务器固有、与本 story 无关）。

### Completion Notes List

- **交付范围**：`api.js` 新增 `storyApi` 薄封装（7 端点，复用 `apiFetch`，`window` 暴露）；`app.js` 设定卡恢复/编辑/反馈/确认/丢弃真实接线 + 文风锚点入口（UX-DR1，做进设定卡对话框）；`styles.css` 文风锚点区样式。**后端零改动**（`git status backend/` 干净）。
- **字段身份用 camelCase key（非数组下标）**：`buildProfileFromBackend` 产出的字段列表长度随题材特化字段激活/文风锚点而变，故每项带 `key`，编辑落库与 `changedFields` 高亮均按 key 定位，避免下标错位。后端 `changedFields` 是 snake_case 列名，`snakeToCamel` 映射到前端 key 驱动 `is-updated`。
- **待确认卡权威来源改为后端**：进探索页 `reconcilePendingStoryProfile` 先即时渲染 sessionStorage 缓存卡（刷新无闪烁），再 `GET /story-profile` 对账——后端返卡则覆盖（含最新 revision/changedFields），204（别标签页已确认/丢弃）则清陈旧缓存回落正常探索加载。引导 + 自由两模式均支持刷新恢复。
- **补齐 7.5 遗留债**：`discardStoryProfileAndReturn` 原基于「settle emit-only 无落库」的过时理解只做前端复位；本 story 纠正——「确定返回」先 `await storyApi.discardProfile`（后端删 pending 行，幂等 204）再前端复位。
- **编辑落库时机 blur**（仿 7.6 线索编辑）：input 只更新本地态 + persist；blur 收集所有改动字段一次 `PATCH`，在途去合并（`profileFieldEditing`）防并发双 PATCH。
- **`openStoryProfileFromBackend` 向后兼容**：`revision`/`changedFields` 缺省回落 1/[]，保证 7.5/7.6 传只含 12 内容字段的 `StoryProfileCard` 的 settle 调用方不挂。
- **删除的 mock**：`collectStoryDraft`、`buildFinalStoryProfile`、`applyStoryProfileFeedback`、`openStoryProfileDialog`（mock 版）、孤立的 `renderStyleAnchor`/`bindStyleAnchorInteractions`/`styleSampleLibrary`/`styleAnchorProfileMarkup`（`#/projects/demo/style-anchor` 独立页，硬编码 demo id、真实流程不可达）。`buildCurrentStagePlan` 保留（仍被 Epic 4 章节页占位消费，删除会越界破坏 Epic 4）。
- **UX 修正（实现中发现）**：文风锚点区最初置于 `.profile-dialog-body` 与 footer 之间的固定区，长设定卡下会被挤出视口不可点击；改置于可滚动的 `.profile-dialog-body` 内，随字段一起滚动。
- **状态清理**：`teardownExplorationInflight`（复位 profile/style 在途门禁，保留 pending 卡）、`resetExplorationStateForNewProject`、logout（清 pending + confirmed sessionStorage + 全套 styleAnchor 态）均纳入新增状态，防跨作品/跨账号残留（多租户，AC8）。
- **回归**：前端 `node --check api.js && app.js` 通过；后端全量 `MUSE_DB_READY=1 uv run pytest -q` 368 passed / 27 skipped（本 story 未改后端）。7.2-7.6 各页未回归（本 story 只在设定卡页与探索路由的 pending 分支扩展，未动其它页数据源）。
- **测试数据**：临时邀请码/测试账号（smoke77/smoke77b）在验证后已随 pytest 的 DB 清理清空（现库仅剩既有 `usage-mixed-billing@example.com`）；静态服务器已停、临时测试脚本已删。

### File List

- `prototype/app/api.js`（修改）— 在既有 `explorationApi` 旁新增 `storyApi` 薄封装（`getProfile`/`editProfile`/`reviseProfile`/`confirmProfile`/`discardProfile`/`listStyleSamples`/`anchorStyle`），复用 `apiFetch`，`window` 暴露。
- `prototype/app/app.js`（修改）— 设定卡恢复（`reconcilePendingStoryProfile` 以后端 GET 为权威、引导+自由两模式刷新恢复）/编辑（blur→PATCH 在途去合并）/反馈（POST revise 真实 Agent + changedFields 高亮）/确认（POST confirm + 真实路由跳转）/丢弃（POST discard 补 7.5 遗留债）的真实接线；`openStoryProfileFromBackend`/`buildProfileFromBackend` 扩展消费 `revision`/`changedFields`（每字段带 camelCase key）；文风锚点入口全新 UI（`styleAnchorEntryMarkup`/`bindStyleAnchorEntryInteractions`/`submitStyleAnchor`/`loadStyleSamplesIfNeeded`，做进设定卡对话框）；`storyErrorText` 错误码映射；`teardownExplorationInflight`/`resetExplorationStateForNewProject`/logout 纳入新增状态；删除 mock（`collectStoryDraft`/`buildFinalStoryProfile`/`applyStoryProfileFeedback`/`openStoryProfileDialog`/孤立 `renderStyleAnchor`+`styleSampleLibrary`+`styleAnchorProfileMarkup` 及其路由）。
- `prototype/app/styles.css`（修改）— 设定卡内文风锚点入口样式（`.style-anchor-entry`/`.style-anchor-toggle`/`.style-anchor-panel`/`.style-anchor-profile`/`.style-anchor-result`），置于可滚动 `.profile-dialog-body` 内；复用既有 `.style-sample-list`/`.style-sample-card`/`.style-paste-field`/`.tabs`。
- `_bmad-output/implementation-artifacts/sprint-status.yaml`（修改）— Story 7.7 `ready-for-dev → in-progress → review`。
- `_bmad-output/implementation-artifacts/deferred-work.md`（修改）— 勾除 3.4/3.5「候选卡编辑/反馈/恢复」「确认/丢弃」前端接线 defer 为 7.7 已兑现；标注「作品库/探索/设定各页接线」切片全部闭合；新增 Story 7.7 defer 段（删孤立 style-anchor 页决策、触发端点前端去重、错误 alert 呈现风格）。

## Change Log

- **2026-08-03（本次创建）**：基于 epics.md 和前端/后端已 done 工件创建。关键点：① `story_bible` 表（3.1）已含 `status/revision/changed_fields` 三列；② 后端 7 个端点已 done（story.py:67-209）；③ 7.5 已建 `openStoryProfileFromBackend` + `persistPendingStoryProfile` 等地基函数；④ 7.6 已建 `teardownExplorationInflight` + `resetExplorationStateForNewProject` + logout 清理；⑤ 文风锚点入口（UX-DR1）必须作为全新 UI 新增。
- **2026-08-04（本次实现，Status → review）**：完成 Task 1–9 全部实现。`api.js` 新增 `storyApi`；`app.js` 设定卡恢复/编辑/反馈/确认/丢弃真实接线 + 文风锚点入口（UX-DR1，设定卡对话框内）+ 错误码映射 + 状态清理，删除全部相关 mock（含孤立的 `#/projects/demo/style-anchor` 页）；`styles.css` 文风锚点样式。后端零改动（`git status backend/` 干净）。验证：前端纯逻辑离线断言 28/28、API 契约端到端（真实后端 + 真实 LLM）27/27、多租户 3/3、真实浏览器 UI（Playwright + Chrome）14/14；后端全量回归 368 passed / 27 skipped；`node --check` 通过。测试账号/邀请码已清理。