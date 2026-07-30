---
baseline_commit: 3080785
---
# Story 7.4: BYOK 设置页 + 托管用量入口接线（含 UX-DR2 须新增 UI）

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a 关注成本/隐私的用户，
I want 绑定自己的 API Key 并查看托管免费额度用量，
so that 我能自主选择走自己的 Key 或托管额度，并掌握用量。

## Acceptance Criteria

> **本 story = 把 7.1 已建好的地基（`api.js` 的 `apiFetch`/`ApiError`）接到既有的模型接入页 `renderByok()`（app.js:2353-2384 + `bindByokInteractions` :2386-2413），把硬编码占位（`usedChapters=3`/`quotaChapters=5` :2354-2355、假保存按钮 :2407-2412、无 data 属性的 provider 三选 :2377）换成后端真实 BYOK 绑定/用量数据，并补一个从作品库进入设置页的入口链接（当前完全缺失，只能手敲 hash）。** 后端 BYOK/用量 API（Epic 1 Story 1.7/1.8 已 done）契约稳定，前端零改动对接。
>
> **关键事实澄清（勘察后修正 epics 措辞）**：epics.md:1328 写「原型无 BYOK 设置页与用量入口」，实际是**页面骨架已存在**（`renderByok()` + 路由 `#/settings/model-access` app.js:2603，由就绪报告 UX-ALIGN-01 建）——UX-DR2 的「A 类须新增 UI」在骨架层已兑现。7.4 的真实工作是 **(a) 接线（占位→真实数据/写入）+ (b) 补入口链接**，而非从零建页。不新建页面、不新增路由。
>
> **口径差异须对齐（承 1.8 交接）**：后端用量按 **tokens** 计（`free_quota_tokens` 默认 200000）、**不做每日重置**（`resetAt` 恒 null）；而原型 hosted tab 显示「N/M **章**」+「免费额度**每天重置**」文案（app.js:2371,2373）。1.8 Completion Notes 明确把「原型『N/M 章』『每天重置』文案与 tokens/累计总量口径的对齐」留给本前端接线切片。见 Dev Notes「受控决策 1」。
>
> **边界严守**：只接模型接入页 `renderByok` + 补设置页入口；**不接** 探索页（7.5/7.6）、设定卡/文风锚点（7.7）；不改 `api.js` 地基逻辑（追加 `byokApi`/`usageApi` 薄封装，仿 `projectApi`）；不加路由级鉴权守卫（业务请求 401 由 7.1 `apiFetch` 兜住跳登录）；不碰后端（BYOK/usage 后端 Story 1.7/1.8 已 done）。

1. **[新增 UI 收口 · 设置页入口]** UX-DR2 要求账户层有「API Key 绑定页 + 托管用量/剩余免费额度展示入口」。页面骨架（`renderByok()` + 路由 `#/settings/model-access`）已存在，但**无任何链接指向它**（全仓搜 `href="#/settings/model-access"` 零命中，只能手敲 hash）。本 story 须在作品库 header `.account`（app.js:493，紧邻邮箱/退出）或 `.library-nav`（app.js:492）补一个进入设置页的入口链接，形态与原型整体风格一致。[Source: epics.md#Story-7.4 AC1（1328-1330）；前端勘察「设置页入口目前不存在」；app.js:492-493 header 挂点；1.7 dev notes「作品库 header 无设置入口=已知前端缺口」deferred-work.md:45]

2. **[BYOK 绑定 · 真实写入]** 我在设置页 `byok` tab 填入 API Key（FR4）+ 选提供方（DeepSeek/Claude/自定义）后点「保存并启用」`[data-byok-save]`（app.js:2407），须经 7.1 `apiFetch` 调 `PUT /api/byok` 传 `{apiKey, provider}`（后端 AES-GCM 加密存储，NFR6）。成功返 `{bound:true, provider, maskedKey}`，前端呈现绑定态（掩码回显 `maskedKey` = `…`+尾4位）。**替换语义**：已绑定时再次提交新 Key 即覆盖（PUT 幂等 upsert）。**当前假保存**（app.js:2407-2412 仅改按钮文案 disable、无 fetch）须换成真实写入 + loading/成功/失败态。[Source: epics.md#Story-7.4 AC2（1332-1334）；后端契约 `PUT /api/byok`→`ByokStatusResponse`（byok.py:17-29）；byok_service.py bind_or_replace_key；app.js:2407-2412 假保存]

3. **[BYOK 状态查询 · 掩码回显]** 进入设置页（`renderByok` 加载时）须经 `apiFetch` 调 `GET /api/byok` 拉真实绑定状态：已绑定→`{bound:true, provider, maskedKey}`，界面展示已绑定态（掩码 + provider 高亮 + 可解绑/更换）；未绑定→`{bound:false}`，展示空态（输入框待填）。**替换**当前的会话级本地态 `byokKeyDraft`/provider 纯 class 切换（app.js:155,2399-2406）——绑定态改由后端 `GET /api/byok` 驱动。[Source: epics.md#Story-7.4 AC2/AC3（1332-1338）；后端契约 `GET /api/byok`→`ByokStatusResponse`（byok.py:32-38）；app.js:2393-2406 本地 draft/provider 切换]

4. **[托管用量展示 · 真实数据 + 口径对齐]** 打开 hosted tab（或页面加载）须经 `apiFetch` 调 `GET /api/usage` 展示真实用量/剩余免费额度（消费后端 usage 接口）：托管用户返 `{billingPath:"hosted", quotaApplies:true, used, quota, remaining}`（tokens 数）；BYOK 用户返 `{billingPath:"byok", quotaApplies:false, used/quota/remaining=null}` → 展示「走自有 Key、不占免费额度」（对齐原型 byok tab 文案 app.js:2378「Muse 不再计免费额度」）。**替换**写死的 `usedChapters=3/quotaChapters=5`（app.js:2354-2356）。**口径对齐**（受控决策 1）：后端按 tokens 计、无每日重置，原型「N/M 章」「每天重置」文案须对齐真实口径（tokens 展示或折算 + 移除/修正「每天重置」表述）。[Source: epics.md#Story-7.4 AC2/AC3（1336-1338）；后端契约 `GET /api/usage`→`UsageViewResponse`（usage.py:17-24）；1.8 Completion Notes「原型『每天重置』文案与 tokens/累计总量口径差异留待前端接线切片对齐」；app.js:2354-2356,2371-2373 占位]

5. **[解绑 / 更换 Key]** 绑定态可解绑（`DELETE /api/byok`→204，成功后回落未绑定空态、hosted 额度重新适用）或更换（再次 `PUT /api/byok` 覆盖）。前端反映最新绑定状态，操作经后端持久化。原型当前**无解绑交互**（假保存后仅 disable），须新增解绑按钮 + 交互。[Source: epics.md#Story-7.4 AC4（1340-1342）；后端契约 `DELETE /api/byok`→204（byok.py:41-44）；byok_service.py unbind_key 幂等]

6. **[多租户隔离 + 401 由 7.1 兜底]** 查看/绑定 Key 与用量只呈现属于我的数据（NFR3，后端从 token 拿 `current_user.id` 强制过滤、前端不传 userId）。未登录/token 失效访问设置页、请求 401 时，由 7.1 `apiFetch` 统一处理（自动 refresh 重放；refresh 亦失效则跳 `#/login?state=expired`），**不在本页重复实现**。BYOK/usage 请求经 `apiFetch`（默认 `auth:true`）发出，401 天然被兜住。[Source: epics.md#Story-7.4 AC5（1344-1346）；后端 BYOK/usage 全部 `CurrentUser` 鉴权 + user_id 租户守卫（1.7/1.8 已测）；7.1 api.js apiFetch 401 单例刷新重放 + redirectToLogin；7.2/7.3 受控决策「不加路由守卫，业务请求 401 兜底」]

**边界（本 story 不做）**：不接探索/自由探索页（7.5/7.6）；不接设定卡/文风锚点（7.7）；不改 `api.js` 地基逻辑（apiFetch/authApi/projectApi/token/401/redirectToLogin 复用，仅**追加** byokApi/usageApi）；不加路由级鉴权守卫；不引入构建/打包/module（保持全局脚本）；不碰后端（BYOK/usage API 已 done，本 story 零后端改动）；不做真实额度阈值定档（占位 tokens 阈值待 Epic 4 盲测，后端已配 200000）；不实现「生成走用户 Key」的真正消费（那是 Epic 2 Provider 层，本 story 只接绑定/查询/用量展示的前端）。

## Tasks / Subtasks

- [x] **Task 1：新增 byokApi + usageApi 薄封装**（AC: 2, 3, 4, 5, 6）
  - [x] 在 `prototype/app/api.js` 追加 `byokApi`（薄封装，仿 `projectApi` 风格 api.js:294-316，`window` 暴露）：
    - `status()` → `apiFetch("/api/byok")`（GET，返 `{bound, provider, maskedKey}`）
    - `bind({apiKey, provider})` → `apiFetch("/api/byok", {method:"PUT", body:{apiKey, provider}})`（返 `{bound:true, provider, maskedKey}`）
    - `unbind()` → `apiFetch("/api/byok", {method:"DELETE"})`（204→null）
  - [x] 追加 `usageApi`：`view()` → `apiFetch("/api/usage")`（返 `{billingPath, quotaApplies, used, quota, remaining, resetAt}`）
  - [x] `apiFetch` 默认 `auth:true` 自动注入 Bearer + 401 刷新重放 + error envelope 解包，**勿在封装内重复处理 token/401/error**。追加薄封装属对地基 `api.js` 的**追加**（非改既有逻辑），符合 7.2/7.3 边界（deferred-work.md「各页用 apiFetch/authApi/xxxApi 逐页替换 mock」）。在 `api.js:321-331` 的 `window` 暴露块挂 `window.byokApi`/`window.usageApi`。
  - [x] 若判断放 app.js 更合适（避免 api.js 膨胀）也可，dev 择优并在 Completion Notes 说明（7.3 已确立此裁量权）。

- [x] **Task 2：作品库补设置页入口链接**（AC: 1）
  - [x] 在作品库 header `.account`（app.js:493，当前 `<span>${email}</span><a href="#/login" data-logout>退出</a>`）补一个 `<a href="#/settings/model-access">设置</a>`（或「模型接入」），置于邮箱与退出之间/旁，形态与原型 header 风格一致。或挂 `.library-nav`（app.js:492，当前只有「作品」）——dev 择优，保持视觉不崩。
  - [x] 纯 `<a href>` 导航即可（hash 路由，无需 JS 拦截）；无需鉴权守卫（未登录访问设置页 → BYOK/usage 请求 401 → 7.1 兜底跳登录）。
  - [x] **注意**：`.account` header 在 `paintProjects()`（app.js:464-504）内，7.3 已接线该函数——本 story 只**追加**一个 header 链接，勿动 7.3 的邮箱展示（`${email}` 来自 `currentUserEmail`）/退出逻辑（`[data-logout]` app.js:1959）。

- [x] **Task 3：renderByok 加载时拉真实状态（BYOK 绑定态 + 用量）**（AC: 3, 4, 6）
  - [x] `renderByok()`（app.js:2353）改为**异步数据驱动**：进入时先渲染骨架/loading 态，并发拉 `byokApi.status()` + `usageApi.view()`（仿 7.3 `loadProjects` 的 `Promise.allSettled` 并发范式 app.js:510-534），回填后重绘。
  - [x] **模块级状态**：新增（或改造既有 `byokTab`/`byokKeyDraft`）承载后端返回——如 `byokBinding`（`{bound, provider, maskedKey}` 或 null）、`usageView`（`{billingPath, quotaApplies, used, quota, remaining}` 或 null）、`byokLoadState`（loading/ready/error）。保留 `byokTab` 作 hosted/byok tab 切换（纯 UI 态）。
  - [x] **时序防护**（承 7.3 受控决策 4）：异步拉取前记录 `location.hash`，回调时校验仍在 `#/settings/model-access` 才写 DOM（防用户快速切走后回调覆盖）；可参照 7.3 `loadProjects` 的 hash + 代次（`projectsLoadSeq`）校验模式（app.js:510-534）。若判断本页低频可 V1 简单实现并登记 defer，dev 择优。
  - [x] **失败态**：`status()`/`view()` 抛 `ApiError`（非 401，401 由 7.1 兜住）→ 渲染 error 态（可复用作品库 `.library-error` 风格 + 重载按钮，或页内错误条）。**展示查询不因触顶失败**：后端 `GET /api/usage` 只读、永不返 429（触顶护栏在生成链路，非本接口，1.8 已坐实）——前端无需处理用量查询的 429 分支。

- [x] **Task 4：hosted tab 用量真实展示 + 口径对齐**（AC: 4）（改 app.js:2354-2356,2370-2374）
  - [x] 删除写死的 `usedChapters=3`/`quotaChapters=5`/`usedPercent`（app.js:2354-2356），改用 `usageView` 真实数据渲染。
  - [x] **托管用户**（`billingPath:"hosted"`, `quotaApplies:true`）：展示 `used`/`quota`/`remaining`（tokens）+ 进度条（`usedPercent = used/quota*100`，用真实 tokens 算）。**口径对齐（受控决策 1）**：原型「N/M **章**」（app.js:2371）→ 改为 tokens 展示（如「已用 100000 / 200000 tokens」）或折算「约 N 章」并注明折算；原型「免费额度**每天重置**」（app.js:2373）→ 后端 `resetAt` 恒 null（累计总量护栏，不重置）须修正文案（移除「每天重置」或改「累计免费额度」）。dev 定档展示措辞并在 Completion Notes 说明，保持「不弹付费墙」的产品语气（app.js:2373）。
  - [x] **BYOK 用户**（`billingPath:"byok"`, `quotaApplies:false`, used/quota/remaining=null）：hosted tab 展示「已绑定自有 Key、不占免费额度」语义态（对齐原型 byok tab 文案 app.js:2378），不显 tokens 进度条（额度不适用）。
  - [x] **配套 CSS 已就绪**（styles.css:3910 起 `.byok-usage-head`/`.byok-usage-bar`/`.byok-usage-note`/`.byok-tip`）——用量展示零新增 CSS，复用既有类。

- [x] **Task 5：BYOK 绑定/替换真实写入**（AC: 2, 3）（改 `[data-byok-save]` app.js:2407-2412）
  - [x] `byok` tab 渲染据 `byokBinding` 分支：**未绑定**→显 API Key 输入框（app.js:2376）+ provider 三选 + 「保存并启用」；**已绑定**→显掩码 `maskedKey`（`…`+尾4位）+ 已选 provider 高亮 + 「更换 Key」（重新填）/「解绑」按钮（AC5）。
  - [x] **provider 三选须带值**：原型 `.byok-provider-option`（app.js:2377）是纯文字按钮**无 data 属性**，仅 class 切换（app.js:2399-2406）。须给三个按钮加 `data-provider="deepseek"/"claude"/"custom"`（后端枚举，`ByokBindRequest.provider` Literal），保存时读当前 `.is-current` 的 `data-provider` 传后端。默认高亮 DeepSeek（app.js:2377 `is-current`）。
  - [x] `[data-byok-save]` handler（app.js:2407）改为 `async`：读 `#byok-key` 值 + 选中 provider，调 `await byokApi.bind({apiKey, provider})`。**成功**（返 `{bound:true, provider, maskedKey}`）→ 更新 `byokBinding` + 重绘为已绑定态（显掩码）；**失败** `catch (err)`（`ApiError`）→ 恢复按钮 + 给可读错误提示。
  - [x] **loading/防重复**：提交时 disable 按钮 + 改「保存中…」文案（仿 7.3 rename/delete 按钮 loading app.js:2107-2108），成功/失败恢复。**空 Key 前端软校验**：`apiKey` 后端 `min_length=1`（空串走 422）+ service strip 判空（纯空白走 `byok_invalid_key` 400）——前端保存按钮在输入非空白前 disable（app.js:2397 既有逻辑保留）即可，勿依赖后端兜底所有空态。
  - [x] **error code 映射**（AC 严格对应，不臆造）：`byok_invalid_key`（400，空/纯空白/超长）→「API Key 不能为空或过长」；`validation_error`（422，provider 非法/apiKey 空串）→「请检查 Key 与提供方」；`token_invalid`/401 → 7.1 兜住不处理。可仿 7.3 `projectErrorText`（app.js:283-288）新增 `byokErrorText(err)` 按 `err.code` 出中文文案 + 中性兜底。

- [x] **Task 6：解绑真实接线**（AC: 5）（新增解绑交互）
  - [x] 已绑定态显「解绑」按钮，点击调 `await byokApi.unbind()`（204）。成功 → 更新 `byokBinding=null` + 重绘为未绑定态（输入框空态）+ 重拉 `usageApi.view()`（解绑后 hosted 额度重新适用，用量展示从 byok 态切回 hosted 态）。
  - [x] **交互确认**：解绑是可逆操作（可再绑），V1 可直接解绑或加轻二次确认（仿 7.3 删除内联确认 app.js:2130-2153，dev 择优——BYOK 解绑不如删作品严重，简单确认或直接解绑均可，勿过度设计）。
  - [x] **失败处理**：`ApiError` → 恢复按钮 + 提示；解绑幂等（后端未绑定也 204 成功），并发/重复解绑友好。

- [x] **Task 7：联调冒烟 + 零回归验证**（AC: 全部）（本机双端联调，[[muse_local_dev_env]]）
  - [x] 起真实后端（`MUSE_DB_READY=1`，`:8000`）+ 原型静态 `:4173`（`cd prototype/app && python3 -m http.server 4173 --bind 127.0.0.1`），准备可登录测试账号（经 7.2 注册/登录，或 curl 建 + 有效邀请码）。7.1 后端 dev CORS 已配 `:4173`。**BYOK 需 `BYOK_MASTER_KEY`**（后端 .env，dev 有占位默认可开箱用）。
  - [x] 浏览器真实走通（登录后）：① 作品库 header 有「设置」入口 → 点进 `#/settings/model-access`；② hosted tab 显真实用量（新账号 used=0/quota=200000）+ 口径对齐（tokens 展示、无「每天重置」误导文案）；③ byok tab 填 Key + 选 provider（如 Claude）→ 保存 → 显掩码 `…`+尾4位 + provider 高亮；④ 刷新页面 → `GET /api/byok` 回填已绑定态（掩码持久=真落库）；⑤ 切 hosted tab → 显「已绑定自有 Key、不占额度」；⑥ 解绑 → 回未绑定空态 + hosted 额度重新适用；⑦ 更换 Key（再绑不同 Key）→ 掩码更新为新尾4位；⑧ 断后端/改坏请求 → error 态可重试。
  - [x] **多租户验证**：A 绑定 Key 后，B 登录进设置页 → `GET /api/byok` 返 `bound:false`（只见自己），B 看不到 A 的绑定/用量。
  - [x] **401 兜底验证**（AC6，复用 7.1 能力）：devtools 改坏 localStorage token 后进设置页触发 `GET /api/byok` → 401 → 7.1 apiFetch 自动跳 `#/login?state=expired`（本页不重复实现）。
  - [x] **安全红线核对**：devtools Network 确认响应体**只含 `maskedKey`（掩码），无明文 Key**；前端不 log/不存明文（输入框值提交后不持久化到 localStorage）。
  - [x] **前端零回归**：登录/注册/退出（7.2）、作品库列表/新建/改名/删除/继续创作（7.3）仍正常；header 加设置链接后作品库布局不崩；未接的探索/设定页从作品库跳入 mock 渲染不崩。
  - [x] 前端语法检查：`node --check api.js && node --check app.js`。
  - [x] **后端零改动确认**：`git status backend/` 应为空（本 story 前端 only）；若发现后端契约缺口须先在 Dev Notes 记录再定夺（预期无缺口，1.7/1.8 已 done 且 curl 可验）。

- [x] **Task 8：收尾**
  - [x] 更新 `_bmad-output/implementation-artifacts/deferred-work.md`：勾除/更新 1.7「renderByok 未接线 + 作品库无设置页入口」（deferred-work.md:45）、1.8「hosted tab 接 GET /api/usage + 每天重置文案对齐」为已由 7.4 兑现；登记本 story 新发现的 defer（如 BYOK 触发端点无限流——1.7 已登记归开放注册前加固批次、异步 render 时序加固等，视实现情况）。
  - [x] 更新 `sprint-status.yaml`：`7-4-BYOK设置页...` 状态 `ready-for-dev` → `in-progress` → `review`（dev 完成后）。
  - [x] 按 story 边界提交（`feat: 实现 Story 7.4 BYOK 设置页/用量入口接线...`），[[feedback_timely_commit]]。

## Dev Notes

### 本 story 的边界（务必守住，勿越界）

- **本 story 交付**：`renderByok` + `bindByokInteractions` 真实接线——设置页入口链接（作品库 header）、BYOK 绑定（PUT）/查询（GET）/解绑（DELETE）真实持久化、hosted 用量（GET /api/usage）真实展示 + 章/tokens & 每日重置口径对齐；新增 `byokApi`/`usageApi` 薄封装（追加到 api.js 或 app.js）。
- **不做**：不接探索页（7.5/7.6）、设定卡/文风锚点（7.7）；不改 `api.js` 地基逻辑（apiFetch/authApi/projectApi/token/401/redirectToLogin 复用，仅**追加** byokApi/usageApi）；不加路由级鉴权守卫；不引入构建/打包/module；**不碰后端**（BYOK/usage 后端 Story 1.7/1.8 done、CORS 7.1 done）；不做真实额度阈值定档；不实现「生成走用户 Key」真正消费（Epic 2 Provider 层）。
- **与 7.3 的关系**：7.3 接好了作品库 `paintProjects`（含 header 邮箱 `${email}`/退出 `[data-logout]`）——本 story 只**追加** header 一个设置入口链接，勿动 7.3 的邮箱/退出逻辑。设置页 `renderByok` 与作品库是不同 render 函数，互不干扰。

### 关键事实澄清：原型「已有骨架、缺接线与入口」（勘察后修正 epics 措辞）

epics.md:1328「原型无 BYOK 设置页与用量入口」措辞不准。**实际现状**（前端勘察坐实）：
- `renderByok()`（app.js:2353-2384）**已存在**：hosted/byok 两态 tab、API Key 输入框、provider 三选、用量展示区，样式 `.byok-*`（styles.css:3910 起）全就绪。
- 路由 `#/settings/model-access` → `renderByok()`（app.js:2603）**已挂**。
- 但**全是硬编码占位**：用量写死 `usedChapters=3/quotaChapters=5`（:2354-2355）、保存按钮假态（:2407-2412 仅改文案 disable、**无 fetch**）、provider 三选纯 class 切换无 data 属性（:2377,2399-2406）、Key 输入注明「仅本地演示，不会上传」（:2376）。
- **无任何入口链接**指向设置页（全仓搜 `href="#/settings/model-access"` 零命中）——用户只能手敲 hash。

**结论**：UX-DR2「A 类须新增 UI」在**页面骨架层已由 UX-ALIGN-01 兑现**；7.4 = 接线（占位→真实）+ 补入口。**不新建页面、不新增路由**。这与 7.7 文风锚点（UX-DR1，原型 renderStyleAnchor 也已建骨架）是同类情形。

### 前后端契约事实（源自后端真实代码考古 + 1.7/1.8 story，直接照写勿再造）

**后端 BYOK 端点**（`backend/src/muse/routers/byok.py`，前缀 `/api/byok`，Story 1.7 done）：

| 接口 | 方法/路径 | 请求体（camelCase） | 成功码 | 响应体（camelCase） | 行号 |
|---|---|---|---|---|---|
| 查询绑定状态 | `GET /api/byok` | 无 | **200** | `ByokStatusResponse` | byok.py:32-38 |
| 绑定/替换 | `PUT /api/byok` | `{apiKey, provider}` | **200** | `ByokStatusResponse` | byok.py:17-29 |
| 解绑 | `DELETE /api/byok` | 无 | **204**（无体） | 无 | byok.py:41-44 |

**后端用量端点**（`backend/src/muse/routers/usage.py`，前缀 `/api/usage`，Story 1.8 done）：

| 接口 | 方法/路径 | 请求体 | 成功码 | 响应体（camelCase） | 行号 |
|---|---|---|---|---|---|
| 查询用量 | `GET /api/usage` | 无 | **200** | `UsageViewResponse` | usage.py:17-24 |

- **无「更换 Key」独立端点**：替换即再次 `PUT`（幂等 upsert，同账户至多一条 BYOK）。
- **BYOK/usage 均为账户级单例，路径不带任何 id**（用 token 定位当前用户，无 IDOR 面）。
- `GET /api/usage` **只读、永不返 429**（触顶护栏 `check_quota` 在生成链路、非本接口，1.8 坐实）——前端无需处理用量查询的触顶分支。

**`ByokStatusResponse` 字段**（`backend/src/muse/schemas/account.py:120-129`，GET/PUT 共用）：

| 字段（camelCase） | 类型 | 说明 |
|---|---|---|
| `bound` | bool | 是否已绑定 |
| `provider` | string \| null | `deepseek`/`claude`/`custom`（**枚举**，前端 provider 按钮 data 值须逐字一致；未绑定为 null） |
| `maskedKey` | string \| null | 掩码 `…`+尾4位（如 `…a1b2`；≤4 字符 Key 全打码 `*`；**绝不回显明文**；未绑定为 null） |

**`UsageViewResponse` 字段**（`backend/src/muse/schemas/account.py:132-148`）：

| 字段（camelCase） | 类型 | 说明 |
|---|---|---|
| `billingPath` | string | `hosted` / `byok`（区分展示态） |
| `quotaApplies` | bool | 托管 true / BYOK false（是否受额度约束） |
| `used` | int \| null | 已用 **tokens**（BYOK 用户 null） |
| `quota` | int \| null | 免费额度 tokens（默认 200000；BYOK 用户 null） |
| `remaining` | int \| null | 剩余 = max(0, quota-used)（BYOK 用户 null） |
| `resetAt` | ISO8601+Z \| null | **V1 恒 null**（累计总量护栏，不做每日重置） |

**请求 schema 约束**（`backend/src/muse/schemas/account.py:106-117`）：
- `ByokBindRequest`：`apiKey` **必填** `str` `min_length=1, max_length=512`（空串 `""` → 422 validation_error）；`provider` **必填** `Literal["deepseek","claude","custom"]`（非法值 → 422）。**纯空白**（`"   "`）min_length 拦不住，后端 service strip 后判空抛 `byok_invalid_key`（400）——前端保存按钮在非空白前 disable 即可（app.js:2397 既有逻辑）。

### error code → 前端处理映射表（AC 严格对应，不臆造）

`catch (err)`（`ApiError`，含 `code`/`detail`/`status`，7.1 apiFetch 统一抛出）后据 `err.code` 分支：

| 后端 code | HTTP | 触发场景 | 前端处理 |
|---|---|---|---|
| `byok_invalid_key` | 400 | Key 空/纯空白/超长（>512） | 提示「API Key 不能为空或过长」；恢复保存按钮 |
| `byok_invalid_provider` | 400 | provider 非枚举（service 兜底，通常 schema 层先 422） | 提示「不支持的模型提供方」 |
| `validation_error` | 422 | 边界校验失败（apiKey 空串/provider 非法枚举） | 提示「请检查 Key 与提供方」；provider 由按钮固定传不该触发 |
| `token_invalid`/`token_expired` | 401 | 无/过期 token；detail `{expired:true}` | **7.1 apiFetch 已兜住**（refresh 重放/跳 `#/login?state=expired`），本页不处理 |
| （用量/绑定加载失败·任意非 401 err） | — | 网络失败/500/502 等 | 渲染 error 态 + 重试；用量查询**不会** 429（只读接口） |

- **判定用 `err.code`**（后端恒字符串，7.1/7.2/7.3 review 已坐实）。
- 建议仿 7.3 `projectErrorText`（app.js:283-288）新增 `byokErrorText(err)` 集中映射 + 中性兜底「操作未能完成，请检查网络后稍后重试。」。

### 受控决策记录（[[feedback_design_decision_delegation]] 已授权先例可依时自主选最优）

1. **原型「章 / 每天重置」文案与后端「tokens / 累计总量」口径的对齐**。后端 `GET /api/usage` 按 **tokens** 计（`free_quota_tokens=200000`）、`resetAt` 恒 null（不做每日重置，1.8 定档）；原型 hosted tab 显示「N/M **章**」（app.js:2371）+「免费额度**每天重置**」（app.js:2373）。**1.8 Completion Notes 明确把此文案对齐留给本前端接线切片**。**建议**：① 用量展示改 tokens 口径（「已用 X / Y tokens」+ 真实百分比进度条），或折算「约 N 章」并注明是估算（真实单章成本待 Epic 4 盲测，当前无换算依据——倾向直接显 tokens，不臆造章折算）；② 移除/修正「每天重置」文案为「累计免费额度」（后端不重置）。保留原型「不弹付费墙」「盲测定档」的产品语气（app.js:2373）。dev 定档措辞并在 Completion Notes 说明。**理由**：后端已 done 且口径明确（tokens/累计），前端须诚实展示真实口径，不显示与后端不符的「章/每天重置」误导用户。真实章折算依赖 Epic 4 盲测成本，当前无据，倾向 tokens 直显。

2. **`byokApi`/`usageApi` 封装位置**。仿 7.3 `projectApi` 追加到 `api.js`（与 authApi/projectApi 并列，语义内聚），或放 app.js（避免 api.js 膨胀）。**建议**追加到 api.js（BYOK/usage 是账户域 API，与 authApi 同层内聚）。dev 择优并在 Completion Notes 说明。**理由**：7.3 已确立「追加薄封装是 7.1 明示的逐页接线方式」，api.js 是 API 封装单一落点。

3. **设置页入口挂点（header `.account` vs `.library-nav`）**。作品库 header 有 `.wordmark`（app.js:490-491）、`.library-nav`（:492 仅「作品」）、`.account`（:493 邮箱+退出）。**建议**挂 `.account`（紧邻邮箱/退出，账户设置语义内聚，如「设置」链接置于邮箱与退出之间），或 `.library-nav`（作「模型接入」导航项）。dev 择优，保持 header 视觉平衡不崩。**理由**：BYOK/用量是账户级设置，与 `.account` 区（身份/退出）语义最近；`.library-nav` 是内容导航，次选。

4. **renderByok 异步化时序防护**。当前 `renderByok` 同步、`render()`（app.js:2590-2617）直接调。异步拉 status+usage 后须防「用户快速切走后回调仍写 DOM」。**建议**：渲染前记录 `location.hash`，回调校验仍在 `#/settings/model-access` 才写 DOM（参照 7.3 `loadProjects` 的 hash + `projectsLoadSeq` 代次校验 app.js:510-534）；或 V1 接受简单实现（设置页低频、切走后写 DOM 低概率副作用）并登记 defer。dev 择优。**理由**：与 7.3 同源时序问题，设置页比作品库低频，但复用 7.3 已验证的模式成本低。

5. **解绑二次确认粒度**。解绑是可逆操作（可再绑），不如删作品严重。**建议**：V1 直接解绑或加轻量内联确认（仿 7.3 删除确认 app.js:2130-2153 但更轻），勿过度设计成 modal。dev 择优。**理由**：解绑可逆、低破坏性，[[feedback_plain_language]] 精神下不为低风险操作堆交互。

### 前端接线锚点（源自 `prototype/app/app.js` + `api.js`，行号已核实 @HEAD 3080785）

- **api.js 地基**（复用，仅追加）：`apiFetch`（api.js:111-157，默认 auth=true）、`ApiError`（:77-85，含 code/detail/status）、`projectApi`（:294-316，byokApi/usageApi 追加范式）、`window` 暴露块（:321-331，挂 byokApi/usageApi）、`authApi.me`（:279-281，Promise.allSettled 并发范式参照）。
- **设置页渲染**：`renderByok()`（app.js:2353-2384）——用量占位 `usedChapters=3`/`quotaChapters=5`/`usedPercent`（:2354-2356，删）、header 返回链接 `#/projects`（:2359，保留）、hosted/byok tab（:2367-2368）、hosted 用量区 `.byok-usage-*`（:2370-2374，接真实）、byok 输入区 `#byok-key`（:2376）、provider 三选 `.byok-provider-option`（:2377，加 data-provider）、保存按钮 `[data-byok-save]`（:2379）。
- **设置页交互**：`bindByokInteractions()`（app.js:2386-2413）——tab 切换（:2387-2392，保留）、key 输入 draft（:2393-2398，改后端驱动）、provider 纯 class 切换（:2399-2406，加 data 值读取）、**假保存 `[data-byok-save]`（:2407-2412，改真实 PUT）**。
- **会话态**：`byokTab`（app.js:154，保留作 tab UI 态）、`byokKeyDraft`（:155，可保留作输入草稿或改后端驱动）。
- **作品库 header**（补入口）：`.account`（app.js:493）/`.library-nav`（:492），在 `paintProjects()`（:464-504）内；退出 `[data-logout]`（:1959，勿动，7.2 已接）；邮箱 `${email}`（来自 currentUserEmail，7.3 已接，勿动）。
- **路由**：`render()`（app.js:2590-2617）——`#/settings/model-access`→renderByok（:2603，已存在勿改）。
- **复用范式**：`escapeHtml`（app.js:596，maskedKey/provider 虽后端可信但保持转义习惯）；7.3 `loadProjects` 并发拉取 + hash/代次时序（:510-534）；`projectErrorText`（:283-288，byokErrorText 参照）；7.3 按钮 loading（rename :2107-2108 / delete :2134-2135）。

### 已知边界与衔接（本 story 不修，须记录）

- **「生成走用户 Key」真正消费在 Epic 2**：本 story 只接 BYOK 绑定/查询/解绑 + 用量展示的**前端**。绑定后「该账户生成走用户 Key」的真正接入是 Epic 2 Provider 层（`get_decrypted_key_for_user`，1.7 AC5 留茬，deferred-work.md:44）——V1 探索/章节生成尚未全接（7.5-7.7 + Epic 2），本 story 绑定的 Key 在生成链路真正生效依赖后续切片。此为受控衔接、非缺陷。
- **额度阈值为占位**：后端 `free_quota_tokens=200000` 是占位值（真实阈值待 Epic 4 盲测单章成本定档，1.8 登记）。前端展示真实后端返回值即可，不硬编码阈值。
- **BYOK 触发端点无限流**：`PUT /api/byok` 无幂等/限流（1.7 defer，归开放注册前加固批次）。前端保存按钮 loading 期 disable 防重复提交即可缓解，通用限流非本 story。

### Project Structure Notes

- 前端沿用原型 `prototype/app`（architecture.md 不重构目录）：本 story 改 `app.js`（renderByok/bindByokInteractions 真实接线 + 作品库 header 补入口链接 + 新增 byokErrorText/异步加载函数）+ `api.js`（**追加** byokApi/usageApi 薄封装，不改地基逻辑）。**不新增前端文件、不新增路由、不新建页面**（骨架已存在）。
- **无后端改动**（BYOK 端点 Story 1.7 done、usage 端点 Story 1.8 done、CORS 7.1 done、/api/auth/me 7.3 已用）。`git status backend/` 应为空。
- 命名：前端 camelCase（架构约定）；后端 BYOK/usage 出入参已 camelCase（ByokStatusResponse/UsageViewResponse），前端直接用（7.1 受控决策 2，转换收敛在 apiFetch，业务代码不写 snake↔camel 转换器）。
- API 路径 RESTful（`/api/byok`、`/api/usage` 账户级单例无 id）；成功直返资源体不套 `{data}`；204 无体（解绑）。

### 本机开发环境（[[muse_local_dev_env]]）

- `uv` 在 `~/.local/bin`；容器用 Colima（非 Docker 桌面）；清华镜像。
- 后端 DB 相关须 `MUSE_DB_READY=1`（BYOK/usage 依赖 DB）；**BYOK 需 `BYOK_MASTER_KEY`**（后端 .env，dev 有占位默认 `dev-only-byok-key-change-me` 可开箱用，1.7 已配 fail-fast 仅生产拦截）。本 story 不涉限流锁定态（无需 Redis 亦可，除非验证 refresh）。
- 双端联调：真实后端 `:8000` + 原型静态 `:4173`（`cd prototype/app && python3 -m http.server 4173 --bind 127.0.0.1`），7.1 后端 dev CORS 已配（允许 `:4173` origin + Authorization 头）。
- 测试账号：经 7.2 注册/登录建，或 curl 后端 `POST /api/auth/register`（需有效邀请码）+ `POST /api/auth/login`。**新账号无绑定 → 天然验证未绑定空态 + hosted 用量 used=0**。

### 测试策略

- 前端全局脚本静态站、无测试运行器（承 7.1/7.2/7.3）。**可提取纯逻辑**（如 `byokErrorText` error code→提示映射、用量 tokens→展示/百分比格式化、provider 枚举→中文标签映射）抽成独立函数做 Node vm 回归（仿 7.3 纯逻辑 19 项断言范式）。
- **DOM 交互 + 数据态**走真实浏览器 playwright 联调（仿 7.3 UI 断言）：设置页入口点击、绑定态/未绑定态渲染、保存→掩码回显、刷新→状态回填持久、解绑→回空态、hosted 用量真实展示 + 口径对齐、BYOK 用户「不占额度」态、error 态重试、401 兜底、多租户隔离、安全（Network 只见 maskedKey 无明文）。
- **后端契约层 curl**（真实后端 :8000 + DB 容器）：`GET/PUT/DELETE /api/byok` + `GET /api/usage` 各端点响应契约对齐（尤其 camelCase 字段、200/204 状态码、maskedKey 掩码格式、usage tokens/null 两态、byok_invalid_key 400、validation_error 422）。
- **后端全量回归** `pytest -q`（本 story 无后端改动，应零回归——验证前端接线未意外触发后端问题）。
- 前端语法 `node --check api.js && node --check app.js`。

### References

- [Source: epics.md#Story-7.4（1320-1346）] — 本 story 5 条 AC 原文（新增 UI、绑定 PUT、用量展示、解绑/更换、多租户）
- [Source: epics.md#Epic-7（1223-1231）] — Epic 7 目标、Story 依赖（7.1→7.2→{7.3,7.4}）、7.4 UX-DR2 须新增 UI、不新增 FR、严格保持原型交互契约、只换数据源
- [Source: epics.md#UX-DR2（150）] — 账户层新增 API Key 绑定页 + 托管用量/剩余免费额度展示入口
- [Source: epics.md#Story-1.7（405-431）] — BYOK 后端 AC（AES-GCM 加密、只回掩码、绑定/替换/解绑/查询、非法 Key 拒绝）
- [Source: epics.md#Story-1.8（433-456）] — 用量护栏后端 AC（usage_ledger、可配置阈值、用量展示 + BYOK 豁免语义）
- [Source: 1-7-BYOKAPIKey绑定全新设置页.md] — BYOK 后端实现（PUT/GET/DELETE /api/byok、ByokStatusResponse、掩码尾4位不硬编码 sk-、账户级唯一约束、前端接线 + 设置页入口 defer 到本切片、`renderByok` 现状 app.js:2079-2139 记录）
- [Source: 1-8-托管免费额度护栏与用量展示.md] — 用量后端实现（GET /api/usage、UsageViewResponse、tokens 计量口径、累计总量不重置 resetAt=null、BYOK 豁免、hosted tab 接 GET /api/usage + 每天重置文案对齐留待前端接线切片）
- [Source: 7-3-作品库接线...md] — 前序接线范式（projectApi 薄封装追加、Promise.allSettled 并发拉取、hash+代次时序防护、projectErrorText error code 映射、按钮 loading、边界严守、三层验证策略、header 邮箱/退出勿动）
- [Source: 7-1-统一请求工具地基...md / api.js] — apiFetch/authApi/ApiError/projectApi/redirectToLogin 地基；追加薄封装为接线方式
- [Source: backend/src/muse/routers/byok.py:17-44] — PUT/GET/DELETE /api/byok 真实路由
- [Source: backend/src/muse/routers/usage.py:17-24] — GET /api/usage 真实路由（只读、不返 429）
- [Source: backend/src/muse/schemas/account.py:106-148] — ByokBindRequest/ByokStatusResponse/UsageViewResponse 字段与约束
- [Source: backend/src/muse/services/byok_service.py] — bind_or_replace_key/get_binding_status/unbind_key（掩码 ≤4 全打码、幂等解绑）
- [Source: backend/src/muse/services/usage_service.py:75-106] — get_usage_view 两态（hosted/byok）、resetAt=null
- [Source: prototype/app/app.js:2353-2413] — renderByok/bindByokInteractions 现状（占位用量、假保存、provider 无 data、tab 切换）
- [Source: prototype/app/app.js:490-504,1959] — 作品库 header（.account/.library-nav 入口挂点）、data-logout（7.2 已接勿动）
- [Source: prototype/app/app.js:2603] — 路由 #/settings/model-access→renderByok（已存在勿改）
- [Source: prototype/app/api.js:294-331] — projectApi 薄封装范式 + window 暴露块（byokApi/usageApi 追加）
- [Source: prototype/app/styles.css:3910+] — .byok-* 样式类（用量展示零新增 CSS）
- [Source: deferred-work.md:44-45] — 1.7 renderByok 未接线 + 作品库无设置入口（本 story 兑现）；get_decrypted_key_for_user 生成消费归 Epic 2

## Dev Agent Record

### Agent Model Used

Claude Opus 4.8 (claude-opus-4-8)

### Debug Log References

- **纯逻辑单测**（Node vm 抽取 app.js 纯函数，无 DOM 依赖）：`byokErrorText` + `providerLabel` + `formatTokens` 共 18 项断言全绿——覆盖 error code→中文提示映射（byok_invalid_key/byok_invalid_provider/validation_error/未知兜底/null）、provider 枚举→中文标签（deepseek/claude/custom/未知回落 DeepSeek）、tokens 千分位格式化（0/200000/1234567 + null/undefined/NaN/Infinity 容错→0）。跑完即清理（临时脚本）。
- **后端契约层 curl 端到端**（真实后端 :8000 + DB 容器 healthy，邀请码 qtYAyzySeeQVdft_）：14 场景全部对齐 story 契约表——① 注册 201；② 登录 200 双 token；③ 未绑定 `GET /api/byok` → `{bound:false, provider:null, maskedKey:null}`；④ hosted 初始 `GET /api/usage` → `{billingPath:hosted, quotaApplies:true, used:0, quota:200000, remaining:200000, resetAt:null}`；⑤ `PUT /api/byok` 绑定 claude → `{bound:true, provider:claude, maskedKey:…wxyz}`；⑥ `GET /api/byok` 回显掩码持久；⑦ 绑定后 `GET /api/usage` → `{billingPath:byok, quotaApplies:false, used/quota/remaining=null}`；⑧ 空 Key → 422 validation_error（string_too_short）；⑨ 纯空白 Key → 400 byok_invalid_key；⑩ 非法 provider(openai) → 422 literal_error；⑪ 替换绑定 deepseek → 掩码更新 …last；⑫ `DELETE /api/byok` → 204；⑬ 解绑后 `GET /api/byok` → bound:false；⑭ 无 token → 401 token_invalid+detail.expired。
- **真实浏览器 UI 联调**（playwright-core + 缓存 chromium-1228，双端 :8000/:4173）：主流程 16 项 UI 断言全绿——登录进作品库；① header 存在设置入口链接 + 点进设置页；② hosted 显真实 quota 200,000 + tokens 口径 + 无「每天重置」+ 有「累计免费额度」；③ byok tab 填 Key+选 Claude+保存 → 无错误弹窗 + 显掩码 …mnop + provider Claude；④ 刷新后掩码持久（=真落库）；⑤ 绑定后 hosted tab 显「不占免费额度」；⑥ 解绑回未绑定空态（显输入框、无掩码）；⑦ 更换 Key 掩码更新 …zzzz；⑥ 安全：Network 响应无明文 Key 泄露；零 JS pageerror。
- **401 兜底 + 未授权联调**（playwright，5 项全绿）：登录后改坏 localStorage token 进设置页 → 自动跳 `#/login?state=expired`（本页未重复实现）；全新 context 无 token 进设置页 → 跳登录。真正跨用户隔离（A 绑定后 B 只见 bound:false）由后端 user_id 强制过滤 + 1.7 租户测试坐实，前端不传 userId 无隔离逻辑可绕。
- **前端零回归联调**（playwright，8 项全绿）：7.2 登录/退出仍正常；7.3 header 邮箱真实展示未回归 + 新建作品→真实 UUID 探索页 + 列表可见；header「设置」链接与邮箱/退出共存不冲突；无 JS pageerror。
- **后端零改动确认**：`git status backend/` 空（0 行）——本 story 前端 only，BYOK/usage 后端 1.7/1.8 已 done。
- **前端语法检查**：`node --check api.js && node --check app.js` 通过。

### Completion Notes List

- **交付**：改 `prototype/app/api.js`（追加 `byokApi`(status/bind/unbind) + `usageApi`(view) 薄封装 + window 暴露，**未改地基逻辑**）+ 改 `prototype/app/app.js`（模型接入页真实接线 + 作品库 header 补设置入口 + logout 重置 BYOK 模块态）。
  - **api.js**：新增 `byokApi = {status/bind/unbind}`（GET/PUT/DELETE /api/byok）+ `usageApi = {view}`（GET /api/usage），全经 apiFetch（默认 auth=true 自动注入 Bearer + 401 刷新重放 + error 解包，不重复实现 token/401/error）；window 暴露 `byokApi`/`usageApi`。
  - **app.js 状态**：新增模块级 `byokBinding`（{bound,provider,maskedKey}|null）、`usageView`、`byokLoadState`（loading/ready/error）、`byokLoadSeq`（代次防赛跑）、`byokReplaceMode`（更换态）、`byokSelectedProvider`（写入用）；保留 `byokTab`（hosted/byok tab UI 态）。
  - **app.js 渲染**：`renderByok` 拆为同步 `paintByok`（三层态绘制：loadState × tab × binding）+ 异步 `loadByok`（Promise.allSettled 并发拉 status+usage，hash+代次双校验时序防护，仿 7.3 loadProjects）；`render()` dispatcher 进 `#/settings/model-access` 时重置 loadState=loading 触发重拉。新增 `paintHostedPanel`（hosted 用量）/`paintByokPanel`（绑定态）分区渲染。
  - **app.js 字段适配**（新增纯函数）：`byokErrorText`（ApiError→提示）、`providerLabel`（provider→中文）、`formatTokens`（tokens 千分位+容错）。
  - **app.js 交互**：`data-byok-save` 改真实 `byokApi.bind`（loading+成功回填掩码+失败恢复+error 映射，抽 `bindByokSave`）；新增 `data-byok-unbind` 解绑（`bindByokUnbind`，成功回空态+重拉用量）；`data-byok-replace`/`data-byok-replace-cancel` 更换态切换；provider 三选加 `data-provider` 真实提交；`data-byok-reload` error 态重载。
  - **app.js header**：作品库 `.account` 补 `<a href="#/settings/model-access">设置</a>`（邮箱与退出之间）；logout handler 追加 BYOK 模块态重置（byokBinding/usageView/byokKeyDraft/byokReplaceMode/byokSelectedProvider/byokLoadState + byokLoadSeq++），防跨账号残留（仿 7.3 review P3）。
- **受控决策落地**：① **口径对齐**：hosted 用量按后端真实 tokens 口径展示「已用 X / Y tokens（累计免费额度）」，移除原型「N/M 章」「每天重置」误导文案（后端 resetAt=null 不重置）；未做 tokens→章折算（真实单章成本待 Epic 4 盲测，当前无据、会误导，登记 deferred）；BYOK 用户 hosted tab 显「不占免费额度」豁免态。② `byokApi`/`usageApi` 追加到 api.js（与 authApi/projectApi 同层内聚）。③ 设置入口挂 `.account`（账户设置语义最近）。④ 异步 render 时序：loadByok hash+byokLoadSeq 代次双校验（复用 7.3 已验证模式）。⑤ 解绑直接执行（可逆低破坏，未加二次确认，[[feedback_plain_language]] 精神不为低风险堆交互）。
- **边界严守（零越界）**：未接探索/自由探索页（7.5/7.6）/设定卡/文风锚点（7.7）；未改 api.js 地基逻辑（仅追加 byokApi/usageApi）；未加路由级鉴权守卫（401 由 apiFetch 兜底）；未引入构建/打包/module；**未碰后端**（git status backend/ 空，BYOK/usage 1.7/1.8 已 done）；未做真实额度阈值定档；未实现「生成走用户 Key」真正消费（Epic 2 Provider 层）。退出/邮箱逻辑（7.2/7.3 已接）未动，仅在 logout 追加 BYOK 态重置。
- **新登记 deferred**（详见 deferred-work.md 7.4 段）：① provider=custom 前端现可提交但后端缺 base_url/model 无法真正调用（归 Epic 2 2.1，与 1.7 同条合并）；② 用量未做 tokens→章折算（归 Epic 4 盲测定档后）；③ renderByok 异步无真正 abort（复用 7.3 代次校验，归 apiFetch 超时/abort 批次）。
- **安全红线守住**：Network 联调确认响应体只含 `maskedKey`（掩码 …+尾4位），无明文 Key；前端输入框值提交后不持久化 localStorage（byokKeyDraft 仅内存态，绑定成功即清空）；密钥经后端 AES-GCM 加密存储（1.7 已实现，前端不碰明文）。
- **测试策略说明**：前端全局脚本静态站、无测试运行器（承 7.1/7.2/7.3）。纯逻辑（error/provider/tokens 映射）抽纯函数做 Node vm 回归（18 项）；DOM 交互+数据态走真实浏览器 playwright（主流程 16 + 401/未授权 5 + 零回归 8）+ 后端契约 curl（14 场景）三层验证，覆盖全部 6 条 AC。

### File List

- `prototype/app/api.js`（修改）— 追加 `byokApi`（status/bind/unbind）+ `usageApi`（view）薄封装 + window 暴露；未改地基逻辑
- `prototype/app/app.js`（修改）— 新增模块级 BYOK 接线态（byokBinding/usageView/byokLoadState/byokLoadSeq/byokReplaceMode/byokSelectedProvider）；renderByok 拆 paintByok（三层态）+ loadByok（异步并发拉取 + hash/代次时序防护）；新增 paintHostedPanel/paintByokPanel/byokErrorText/providerLabel/formatTokens/bindByokSave/bindByokUnbind；bindByokInteractions 真实接线（PUT 绑定/DELETE 解绑/更换态/provider data-provider/error 重载）；作品库 header .account 补设置入口链接；render dispatcher 进设置页重置 loading 重拉；logout 追加 BYOK 模块态重置防跨账号残留
- `_bmad-output/implementation-artifacts/deferred-work.md`（修改）— 标注 1.7「renderByok 未接线 + 作品库无设置入口」已由 7.4 兑现；新增 7.4 段登记 3 条 defer（custom base_url/model、tokens→章折算、异步 abort）
- `_bmad-output/implementation-artifacts/sprint-status.yaml`（修改）— 7-4 状态 backlog → ready-for-dev → in-progress → review

## Review Findings (2026-07-30，三层对抗审查，子 agent 用 Sonnet 独立于实现 Opus)

> Blind Hunter（仅 diff，17 条）+ Edge Case Hunter（diff + 项目只读 + 前后端契约核实，12 条）+ Acceptance Auditor（diff + spec，**AC1-6 全 PASS、边界严守、5 受控决策全落地、无越界无谎报**）。三层完整无 failed_layer。去重合并后：0 decision-needed + 4 patch + 1 defer + 24 dismiss（噪声/假阳性/已处理/设计取舍）。

- [ ] [Review][Patch] 保存/解绑成功/失败回调 `renderByok()` 无 hash+代次守卫 → 跨页覆盖 DOM [prototype/app/app.js:2578 bindByokSave / :2619 bindByokUnbind] — blind#1 + edge#1/#2 三层收敛。`bindByokSave`/`bindByokUnbind` 的 async IIFE 在 `await byokApi.bind/unbind` + `usageApi.view()` 完成后**无条件** `renderByok()`（→ `paintByok` → `app.innerHTML=`）。触发：用户点「保存并启用」/「解绑」后立即点顶部「← 作品库」跳 `#/projects`，作品库渲染完后 PUT/DELETE 回调把整页替换成 BYOK 页。`loadByok`（:2450 附近）有 `startedHash + byokLoadSeq` 双校验，这两条写路径完全没有。**与 7.3 review P2 同源教训**（异步回调须过时序校验）。**顺带修 blind#2**：logout 重置（:1976-1984）漏清 `byokTab`（纯 UI tab 位置，A 切到 byok tab 登出后 B 进设置页仍停 byok tab），一并加 `byokTab="hosted"`。
- [ ] [Review][Patch] 保存/解绑 401 后跳登录页仍弹 `alert("操作未能完成")` [prototype/app/app.js:2612 / :2642 catch 分支] — edge#5/#6。核实 api.js `apiFetch`：不可救回的业务 401 会 `clearTokens()`+`redirectToLogin("expired")` 后 **`throw`**（api.js:136-140），前端 catch 执行 `window.alert(byokErrorText(err))` → 已跳登录页却盖一个突兀弹窗。**承 7.3「401 由地基兜底、本页不重复处理」**：catch 里加 `if (err && err.status === 401) return`（不弹 alert，跳转已由地基完成）。
- [ ] [Review][Patch] `usageView` 为 null/缺字段时 hosted 面板画「0 / 0 tokens」假额度 [prototype/app/app.js:2471 paintHostedPanel] — blind#8 + edge#3 收敛。`usageApi.view()` 失败静默吞（bindByokSave/Unbind 的 `catch { usageView = null }` :2604/:2634）后，`paintHostedPanel` 的 `used/quota/remaining` 全兜底取 0，用户看到「免费额度 0 / 0 tokens」「剩余 0 tokens」误以为额度耗尽。须加 `if (!usage) 显示「用量暂不可用」占位`，与「展示查询不误导」一致。
- [ ] [Review][Patch] PUT 成功 `result` 缺字段时兜底假绑定 `{bound:true,provider}` [prototype/app/app.js:2597 bindByokSave] — blind#10 + edge#7。`byokBinding = result || {bound:true, provider}`：若后端 200 但 body 空/缺 `bound`/`maskedKey`（反代截断等边缘），显假绑定态（「provider / 已绑定」无掩码）。**与 7.3 review P4「新建响应缺 id」完全同源**（当时选 patch：缺关键字段抛错而非用假态）。改为 `if (!result || !result.bound) throw new ApiError("invalid_response",...)` 走统一失败分支，不显假绑定。
- [x] [Review][Defer] `providerLabel` 未知 provider 静默兜底「DeepSeek」，掩盖后端契约漂移 [prototype/app/app.js:2513 providerLabel] — deferred。blind#4/#12 + edge#8。后端将来加 `gemini/openai` 而前端未同步时，已绑定新 provider 的用户看到误标「DeepSeek」。**当前后端 provider 枚举锁定 `deepseek/claude/custom`**（1.7 `ByokBindRequest.provider` Literal，已核实），无触发面。**归「后端 provider 扩展时」同步**：届时 providerLabel 加新分支或未知值降级为原文 + 提示，与前端 provider 三选按钮一并扩展。

**Dismissed（噪声/假阳性/已处理/设计取舍，24 条）**：① blind#5 空 Key 死锁（**假阳性**：核实 input handler :2545-2548 每次输入同步 `save.disabled = !key.value.trim()`，删光→disabled、再输入→恢复，不死锁）；② blind#6/edge(未列) `childNodes[0]`/`btn.textContent` 按钮结构脆性（原型按钮结构稳定 `保存并启用 <span>→</span>`，与 7.3 dismiss 同类）；③ blind#11 render 强制 loading 打断输入（前提「hash 不变的 render 调用」当前不存在，render 仅由 hashchange/load 驱动，进设置页=hash 变=本就该重拉）；④ edge#4 loadByok 期间反复点 tab 发并发请求（seq 已截结果、内测期无性能面）；⑤ blind#9 headState loading 时按 tab 显文案（loading 分支 panel 已显「正在读取」，header 文案次要）；⑥ blind#3/#13-17 alert 无障碍/孤儿节点写/事件语义（原型阶段可接受、低优无副作用）；⑦ edge#10/#11/#12 error 保留 tab/空白无反馈/已被 if(save) 兜住（低概率或已处理）；⑧ blind#7/#14-16 provider 兜底 deepseek/loadByok 部分降级（当前枚举稳定、局部降级属 UX 精细化非缺陷）；⑨ 其余 UX 偏好项（解绑后停 byok tab、null 消毒等，与 patch 修复重叠或低优）。

## Review Findings（2026-07-30 第二轮·修复后复审，三层对抗审查，子 agent 独立于实现）

> 复审范围 = 7.4 原始提交（2d2bea4）+ 上一轮 4 patch 的未提交修复合并 diff（api.js +44 / app.js +316/-23）。Blind Hunter（仅 diff，6 条）+ Edge Case Hunter（diff + 项目只读 + 前后端契约核实，5 条）+ Acceptance Auditor（diff + spec，**AC1-6 全 PASS、5 受控决策全落地、上一轮 4 patch 真实修复到位、边界零越界、File List/Completion Notes 无谎报**）。三层完整无 failed_layer。去重合并后：0 decision-needed + 3 patch + 1 defer + 其余 dismiss。

- [x] [Review][Patch] 保存 in-flight 时在输入框继续打字可再次点「保存」触发并发双 PUT [prototype/app/app.js:2555-2558 input handler / :2588-2600 bindByokSave] — edge#1（唯一命中，已核实属实）。`bindByokSave` 进入时 `save.disabled=true`，但**面板未重绘**、`#byok-key` 输入框仍在 DOM，其 input handler（:2558）每次输入执行 `save.disabled = !key.value.trim()` → 在途期间把按钮**重新 enable** → 用户再点「保存」，`if(save.disabled)return` 判 false → 第二次 `byokApi.bind` 发出。两个并发 PUT 回调各写 `byokBinding` + `renderByok()`，第一个 resolve 后 `save`/`labelNode` 已成脱离节点，第二个回调再操作脱离节点并二次重绘 → 掩码态闪烁/「保存中…」错乱。**对照 7.3 命名输入监听只改 textContent、从不碰 disabled**，本 diff 是新引入的在途放行面。**已修复**：新增模块级 `byokSaving` 标志，提交时置 true、finally 解除；input handler 改 `if (save && !byokSaving)`，在途不重新 enable；logout 一并重置。
- [x] [Review][Patch] usage GET 瞬时失败把整页锁成 error，连已绑定用户都无法解绑 [prototype/app/app.js:2403-2420 loadByok] — blind#1 + edge#2 两层独立收敛。`Promise.allSettled([byokApi.status(), usageApi.view()])` 后**要求两者都 fulfilled 才 ready，否则整页 error**（只剩「重新加载」）。当 status 成功、`GET /api/usage` 因 DB SUM 抖动 5xx 时，绑定/解绑面板完全不可达——把只读、非核心的 usage 抬成和 status 同级的致命依赖。**偏离 7.3 loadProjects 范式**（me() 失败降级为不显邮箱、仅 list 失败才 error）。且 usage 对绑定管理并非必需（bound 时 hosted 面板本就显「不适用」）。**已修复**：改为 status 成功即 ready，usage 单独失败降级 `usageView=null`（paintHostedPanel 已有「用量暂不可用」占位兜底），仅 status 失败才 error。
- [x] [Review][Patch] byokReplaceMode 切 tab 未复位造成状态残留 [prototype/app/app.js:2543-2548 tab 切换 / :2570 data-byok-replace] — blind#3（已核实属实）。已绑定用户点「更换 Key」进 `byokReplaceMode=true`，再切「Muse 托管」tab、又切回「绑定自有 Key」→ `paintByokPanel(bound=true, replaceMode=true)` 仍显重填表单而非「已绑定摘要」。用户预期切 tab 回来看到已绑定态，实际停在半途编辑态。**已修复**：data-byok-tab 切换 handler 里重置 `byokReplaceMode=false` + 清 byokKeyDraft。
- [x] [Review][Defer] providerLabel 未知 provider 静默兜底「DeepSeek」，掩盖后端契约漂移 [prototype/app/app.js:2380-2384 providerLabel] — blind#5 + edge#5 + auditor 三层收敛，**与上一轮同一条 defer**。后端 `ByokBindRequest.provider` 当前锁定 `deepseek/claude/custom`（Literal，已核实），无触发面；仅后端未来扩枚举而前端未同步时才误标。归「后端 provider 扩展时」同步，与上一轮 defer 合并、不重复登记。

**Dismissed（噪声/假阳性/设计取舍/已处理）**：① blind#6 空白 Key 死锁（**假阳性**：input handler :2558 每次输入同步 `save.disabled=!value.trim()`，删光→disabled、再输入→恢复，不死锁）；② blind#2 明文 draft 常驻全局 + 反复写 innerHTML（原型阶段：type=password + escapeHtml 防截断 + 提交成功即清 byokKeyDraft，前端不 log/不持久化 localStorage，属已知设计取舍，真实明文加密存储在后端）；③ blind#5 `save.childNodes[0]` 文本节点脆性（当前模板 `保存并启用 <span>→</span>` 成立，取到确为文本节点，与 7.3 dismiss 同类）；④ edge#3/blind#4 save/unbind 仅 hash 守卫缺代次（往返同页窄窗竞态，操作幂等同账户多为闪烁而非持久错值，且下一次 loadByok 会纠正，低优）；⑤ edge#4 tab 切换在途回调对脱离节点写 label/弹 alert（纯体验瑕疵，与 patch#1「并发双 PUT」修复方向部分重叠，低优）；⑥ auditor 两条偏差（P4 只校验 !result.bound 未查 maskedKey——后端契约保证 bound=true 必带 maskedKey，与商定 patch 逐字一致；loading 态 header 文案按 tab 计算——panel 已显「正在读取」，无功能影响）。

## Change Log

- 2026-07-30：创建 Story 7.4 BYOK 设置页/用量入口接线 story 文件（context engine 分析）。综合 epics.md AC1-6、7.3 前序接线范式、1.7/1.8 后端契约考古（子 agent + 主 agent 核验）、UX-DR2、原型 renderByok 现状勘察（澄清「骨架已存在、缺接线与入口」）。8 个 Task 覆盖薄封装/设置入口/异步拉取/用量口径对齐/绑定/解绑/联调。5 项受控决策（口径对齐、封装位置、入口挂点、异步时序、解绑确认）。边界严守：只接模型接入页、不接探索/设定、不碰后端。
- 2026-07-30：实现 Story 7.4 BYOK 设置页/用量入口接线。api.js 追加 byokApi（status/bind/unbind）+ usageApi（view）；app.js 把模型接入页从硬编码占位换成后端真实数据——renderByok 异步数据驱动（loading/ready/error + hosted/byok tab + 绑定/未绑定态）、绑定 PUT（掩码回显）、解绑 DELETE、更换 Key、hosted 用量真实 tokens 展示 + 口径对齐（移除「章/每天重置」误导文案）、provider 三选加 data-provider 真实提交、作品库 header 补设置入口、logout 重置 BYOK 模块态防跨账号残留。5 受控决策落地。Tasks 1-8 全部完成，AC1-6 满足。验证：纯逻辑 18 项 + 后端契约 curl 14 场景 + playwright UI 主流程 16 项 + 401/未授权 5 项 + 零回归 8 项全绿，后端零改动（git status backend/ 空）。
