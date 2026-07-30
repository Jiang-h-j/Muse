---
baseline_commit: 077f50d
---
# Story 7.2: 登录 / 注册接线（真实会话，替换 mock）

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a 用户，
I want 在真实登录 / 注册页用账号进出创作空间，
so that 我的会话与身份由后端真实签发，而非前端假数据。

## Acceptance Criteria

> **本 story = 把 7.1 已建好的地基（`api.js` 的 `authApi` + `apiFetch`）接到登录 / 注册 UI。** 7.1 交付了工具与 `authApi.register/login/logout/refresh` 调用函数 + 冒烟验证；**本 story 只做 UI 接线**：把 `bindAuthInteractions`（`app.js:1710-1719`）的假延迟提交换成真实调用、把 header「退出」（`app.js:405`）纯链接换成调 `authApi.logout()`、把后端 error envelope 布尔位真实映射到既有 `expired`/`invalid`/`locked` 状态位。**边界严守**：不接作品库 / 探索 / 设定任何业务页（7.3–7.7）；不改 `api.js` 地基本身（除非发现 7.1 缺口，须先在 Dev Notes 记录再动）；不加路由级鉴权守卫（未登录访问受保护路由的全局拦截，V1 归各页 401 处理，7.1 的 `apiFetch` 已能兜住业务请求 401 跳登录）。

1. **[注册接线]** 注册页（`#/register`，邀请码必填、密码 `minlength=8`，`app.js:324/326`）提交有效邀请码 + 邮箱 + 密码时，经 `authApi.register({inviteCode, email, password})` 调后端 `POST /api/auth/register`。**关键：注册不签发 token（受控决策 1，后端契约事实）**——注册成功（201 返 `{id, email}`）后须**串接一次 `authApi.login({email, password})`** 拿到会话 token，再按原型跳 `#/projects`。邀请码无效 / 已用 / 过期时后端返 `invalid_invite`（400，`detail.invalid`），呈现注册模式 `invalid` 文案「邀请码无效、已使用或已过期。」（`stateMessage` app.js:277-282，register 模式）。[Source: epics.md#Story-7.2 AC1（1268-1270）；7.1 story 后端契约表：register→201 `{id,email}` 无 token / auth_service.py:32-40 `invalid_invite`；受控决策 8（注册不签发 token）；app.js:324 邀请码 input required、:326 密码 minlength=8]

2. **[登录接线]** 登录页（`#/login`）提交正确邮箱密码时，经 `authApi.login({email, password})` 调后端 `POST /api/auth/login` 取 `{accessToken, refreshToken, tokenType, expiresIn}`。`authApi.login` **内部已 `setTokens` 落 localStorage**（api.js:245-249），本 story **不要重复存 token**。成功后进 `#/projects`；凭证错误后端返 `invalid_credentials`（401，`detail.invalid`），呈现登录模式 `invalid` 文案「邮箱或密码错误，请检查后重试。」（app.js:277-281，login 模式）。[Source: epics.md#Story-7.2 AC2（1272-1274）；7.1 后端契约表：login→200 双 token；api.js:239-250 login 已 setTokens；auth_service.py:132-140 `invalid_credentials`]

3. **[限流锁定态]** 登录失败超阈值触发后端限流（AR6，5 次 / 15 分钟）时，后端返 `too_many_attempts`（**429**，`detail.locked`），前端呈现 `locked` 文案「登录尝试次数过多，请稍后再试。」（app.js:283）。**注意**：限流依赖 Redis 且 **fail-open**（Redis 不可用则不锁定放行，`rate_limit.py:6-9`）——本地无 Redis 时无法复现锁定态，据后端 error code 分支即可，前端不自行计数模拟锁定。[Source: epics.md#Story-7.2 AC3（1276-1278）；7.1 后端契约表：`too_many_attempts`→429 `detail.locked`；auth_service.py:143-150；rate_limit.py:21-22 限流阈值、:6-9 fail-open]

4. **[会话过期跳转呈现]** 会话过期（refresh 失效，**7.1 `apiFetch`/`doRefresh` 已处理清 token + 跳 `#/login?state=expired`**，非本 story 触发）时，用户被跳回登录页，前端据 `queryState()==='expired'` 呈现 `expired` 文案「会话已过期，请重新登录。登录后会返回你的创作空间。」（app.js:276）。**本 story 只须保证登录页 render 时 `stateMessage` 机制正常呈现 expired（该机制 7.1 前已存在，app.js:274-286/322），不须新写跳转逻辑**——跳转是 7.1 地基的能力。[Source: epics.md#Story-7.2 AC4（1280-1282）；7.1 story AC3 + api.js:166-168 `redirectToLogin`、:184-207 `doRefresh`；app.js:276 expired 文案、:290-292/322 renderAuth 据 queryState 渲染]

5. **[退出接线]** 已登录用户在作品库 header 点「退出」（`app.js:405`，当前是纯 `<a href="#/login">` 链接，无 logout 调用）时，须改为调 `authApi.logout()`（作废后端 refresh + 清本地 token，api.js:260-275 已封装、失败静默吞掉且 finally 清 token），成功后回登录态（`#/login`）。[Source: epics.md#Story-7.2 AC5（1284-1286）；app.js:405 退出纯链接（须改）；api.js:260-275 `authApi.logout` 幂等清本地态；backend auth.py:61-64 logout→204]

6. **[状态位严格对应后端 code，不臆造分支（UX-DR9）]** 前端布尔状态位（`expired`/`invalid`/`locked`）严格对应后端 error envelope 的 `code`（经 `ApiError.code` / `ApiError.detail` 判定），映射见 Dev Notes「error code → 状态位映射表」，**不臆造后端未定义的分支**。`ApiError` 由 7.1 `apiFetch` 统一抛出（含 `code`/`detail`/`status`），本 story `catch (err)` 后据 `err.code` 或 `err.detail` 分支设置 `?state=`，复用既有 `stateMessage` 呈现。[Source: epics.md#Story-7.2 AC6（1288-1290）；epics.md#UX-DR9（160）；7.1 api.js:77-101 `ApiError`/`toApiError`；后端 code 见 auth_service.py + errors.py]

**边界（本 story 不做）**：不接作品库列表 / 新建 / 重命名 / 删除 / 继续创作跳转（7.3）；不接 BYOK / 探索 / 设定各页（7.4–7.7）；不改 `api.js` 地基（token 存取 / apiFetch / 401 刷新 / redirectToLogin / authApi 均 7.1 已交付，本 story 直接复用）；不加 `render`（app.js:2316-2340）路由级鉴权守卫（未登录直接访问 `#/projects` 的全局拦截 V1 不做，业务请求 401 由 7.1 `apiFetch` 兜住跳登录）；不引入构建 / 打包 / module（保持全局脚本）。

## Tasks / Subtasks

- [x] **Task 1：登录表单真实接线**（AC: 2, 3, 6）（改 `bindAuthInteractions` 的 submit 处理 app.js:1710-1719）
  - [x] 把 `#/auth-form` submit 里的 `window.setTimeout(() => location.hash = "#/projects", 650)` 假延迟（app.js:1717-1719）替换为真实异步调用。submit handler 改为 `async`（或在内部调 async IIFE）。
  - [x] 读取表单值：`email`（`#email`）、`password`（`#password`），登录模式无邀请码字段。保留既有 `reportValidity()` 前置校验（app.js:1712）与 submit 按钮 disable + 文案「正在登录…」（app.js:1713-1716）。
  - [x] 登录模式（`currentMode()==='login'`）调 `await authApi.login({email, password})`；成功后 `location.hash = "#/projects"`（`authApi.login` 已内部 `setTokens`，**勿重复存 token**）。
  - [x] `catch (err)`：据 `err`（`ApiError`，含 `code`/`detail`）映射状态位——`invalid_credentials`→`invalid`、`too_many_attempts`→`locked`（见 Dev Notes 映射表），设 `location.hash = "#/login?state=<state>"` 触发 renderAuth 呈现文案。**失败须恢复 submit 按钮可用 + 文案复原**（否则卡「正在登录…」灰态）——注意跳 hash 会触发 render 重绘表单，天然复位；若同 hash（如已在 `#/login` 无 state 变化）不触发 render，须手动恢复按钮。
  - [x] **未知 / 网络错误兜底**：`err` 无可识别 code（如 `unknown`/`invalid_response`/网络失败）时，不臆造 expired/invalid，给一个通用错误呈现（可复用 `invalid` 文案或加一个中性提示），并恢复按钮，不静默吞掉让用户以为在转圈。

- [x] **Task 2：注册表单真实接线（含注册→登录串接）**（AC: 1, 6）（同 `bindAuthInteractions` submit，按 `currentMode()` 分支）
  - [x] 注册模式（`currentMode()==='register'`）读取 `invite`（`#invite`）+ `email` + `password`，调 `await authApi.register({inviteCode: invite, email, password})`。
  - [x] **注册成功后串接 login（受控决策 1，关键）**：`register` 返 `{id, email}` **无 token**，紧接着 `await authApi.login({email, password})` 拿会话 token（login 内部 setTokens），再 `location.hash = "#/projects"`。串接的 login 用注册时同一 email/password。
  - [x] `catch (err)`：注册阶段 `invalid_invite`（400）→ 注册模式 `invalid` 文案（app.js:279-281 register 分支已是「邀请码无效…」）；`validation_error`（422，如密码不合规——虽有 minlength 前置但后端仍会校验）→ 给可读提示。恢复 submit 按钮。
  - [x] **边界情形**：注册成功但串接 login 失败（极端：账号刚建好但 login 返错）——按 login 的错误分支处理并恢复按钮；不重复注册（避免 email 已存在错误）。

- [x] **Task 3：退出按钮接线**（AC: 5）（改 header「退出」app.js:405 + 绑定事件）
  - [x] 把 `renderProjects`（app.js:405）header 里的 `<a href="#/login">退出</a>` 改为带标识的按钮 / 链接（如加 `data-logout` 属性），避免纯 hash 跳转绕过 logout。
  - [x] 在 `bindProjectInteractions`（app.js:1736 起）内绑定 `[data-logout]` click：`event.preventDefault()` → `await authApi.logout()` → `location.hash = "#/login"`。`authApi.logout` 已保证 finally 清本地 token 且失败静默（api.js:260-275），故无论后端结果都能回登录态。
  - [x] **注意**：header 邮箱当前硬编码 `creator@example.com`（app.js:405）——真实用户邮箱展示归 7.3（作品库接 `/api/auth/me` 或用户信息），**本 story 不改邮箱展示**，只接退出行为（除非 dev 判断顺手改，但须在 completion notes 说明并保持零回归）。

- [x] **Task 4：expired 状态呈现验证**（AC: 4）（无新代码，验证 7.1 跳转 + 既有 stateMessage 闭环）
  - [x] 验证：手动触发 7.1 的 `redirectToLogin('expired')`（或 devtools 改坏 localStorage token 后发业务请求）→ 跳 `#/login?state=expired` → renderAuth 呈现「会话已过期…」文案（app.js:276）。这是 7.1 地基能力 + 既有 stateMessage 机制的闭环，本 story 只确认接线后未破坏该链路。
  - [x] 确认 `#/login?state=expired` 下登录成功后正常进 `#/projects`（expired 态不阻断后续登录）。

- [x] **Task 5：联调冒烟 + 移除 7.1 临时冒烟入口**（AC: 全部）（本机双端联调，[[muse_local_dev_env]]）
  - [x] 起真实后端（`MUSE_DB_READY=1` + Redis `MUSE_REDIS_READY=1` 若测锁定态）+ 原型静态 `:4173`（`cd prototype/app && python3 -m http.server 4173 --bind 127.0.0.1`）。准备可登录测试账号（或先注册）。
  - [x] 浏览器真实走通：① 注册（有效邀请码）→ 自动 login → 进作品库；② 登录（正确密码）→ 进作品库；③ 错密码 → `invalid` 文案 + 按钮复位；④ 无效邀请码 → 注册 `invalid` 文案；⑤ 退出 → 回登录页且 localStorage token 已清；⑥（可选，需 Redis）连错 5 次 → `locked` 文案；⑦ expired 跳转呈现。
  - [x] **移除 7.1 遗留的临时冒烟入口** `window.__museApiSmoke`（api.js:297-322）——7.1 明确「7.2 接 UI 后移除」（deferred-work 已登记）。移除后确认地基其余符号（apiFetch/authApi/...）仍正常暴露。
  - [x] **前端零回归**：登录 / 注册 / 作品库页在接线后仍正常渲染；未接的业务页（探索 / 设定 / 归档）mock 渲染不受影响。

- [x] **Task 6：收尾**
  - [x] 更新 `_bmad-output/implementation-artifacts/deferred-work.md`：勾除 / 更新 7.1 登记的「① 登录/注册页完整接线」「⑤ 冒烟临时入口移除」为已完成；确认作品库列表 / 邮箱展示等仍 defer 至 7.3。
  - [x] 更新 `sprint-status.yaml`：`7-2-登录注册接线真实会话替换mock` 状态 `ready-for-dev` → `review`（dev 完成后）。
  - [x] 按 story 边界提交（`feat: 实现 Story 7.2 登录注册接线...`），[[feedback_timely_commit]]。

## Dev Notes

### 本 story 的边界（务必守住，勿越界）

- **本 story 交付**：登录 / 注册表单真实调 `authApi`（替换 app.js:1717-1719 假延迟）+ 注册成功串接 login + 退出按钮调 `authApi.logout()`（替换 app.js:405 纯链接）+ error code→状态位真实映射 + 移除 7.1 临时冒烟入口。
- **不做**：不接作品库数据 / 邮箱展示（7.3）；不接 BYOK / 探索 / 设定（7.4–7.7）；不改 `api.js` 地基逻辑（复用即可，如发现 7.1 缺口须先在 Dev Notes 记录）；不加路由级鉴权守卫（未登录访问 `#/projects` 的全局拦截 V1 不做）；不引入构建 / 打包 / module。

### 前后端契约事实（源自 7.1 已验证 + 后端真实代码，直接复用勿再造）

**7.1 已交付、本 story 直接复用的地基符号**（`prototype/app/api.js`，全局 window 暴露）：

| 符号 | 作用 | 本 story 用法 |
|---|---|---|
| `authApi.register({inviteCode, email, password})` | 调 register，返 `{id, email}` **无 token** | Task 2，成功后须串接 login |
| `authApi.login({email, password})` | 调 login，**内部已 setTokens** | Task 1/2，成功即会话就绪，勿重复存 token |
| `authApi.logout()` | 作废 refresh + 清本地 token，失败静默 | Task 3 退出 |
| `apiFetch` | 统一请求（token 注入 / 401 刷新 / error 解包） | 间接经 authApi 用 |
| `ApiError`（含 `code`/`detail`/`status`） | 结构化错误 | Task 1/2 `catch` 据此分支 |
| `redirectToLogin('expired')` | 跳登录 | 7.1 已在 401/refresh 失效时调用，本 story 不主动调 |

**后端认证接口契约**（Epic 1 done，路径含 `/api/auth` 前缀）：

| 接口 | 方法/路径 | 请求体 | 响应 |
|---|---|---|---|
| 注册 | `POST /api/auth/register` → **201** | `{inviteCode, email, password}`（password 8-128） | `{id, email}`（**无 token**，auth.py:26-36） |
| 登录 | `POST /api/auth/login` → **200** | `{email, password}` | `{accessToken, refreshToken, tokenType, expiresIn}`（auth.py:39-47） |
| 登出 | `POST /api/auth/logout` → **204** | `{refreshToken}` | 无体（auth.py:61-64） |

### error code → 状态位映射表（AC6 严格对应，不臆造）

`catch (err)` 后据 `err.code`（或 `err.detail` 布尔位）设 `?state=`，复用既有 `stateMessage`（app.js:274-286）：

| 后端 code | HTTP | detail 布尔位 | 前端 `?state=` | 呈现文案（app.js） | 触发场景 |
|---|---|---|---|---|---|
| `invalid_credentials` | 401 | `{invalid:true}` | `invalid` | 「邮箱或密码错误，请检查后重试。」(login 模式) | 登录错密码 |
| `invalid_invite` | 400 | `{invalid:true}` | `invalid` | 「邀请码无效、已使用或已过期。」(register 模式) | 注册无效邀请码 |
| `too_many_attempts` | 429 | `{locked:true}` | `locked` | 「登录尝试次数过多，请稍后再试。」 | 登录超限流 |
| `token_invalid`(refresh 失效) | 401 | `{expired:true}` | `expired` | 「会话已过期，请重新登录。」 | **7.1 已处理跳转**，本 story 只呈现 |
| `validation_error` | 422 | 错误列表 | （给通用可读提示，非既有 3 态） | — | 后端字段校验（密码等） |

- **判定优先用 `err.code`**（后端恒字符串，见 7.1 review dismiss「后端返数字 code」为假阳性）；`detail` 布尔位（invalid/expired/locked）可作辅助。
- **注意 `invalid` 文案随模式变**：`stateMessage(state, mode)`（app.js:274-286）据 `mode` 返回登录 or 注册文案，`?state=invalid` 在登录页显「邮箱或密码错误」、注册页显「邀请码无效…」——所以设 `?state=invalid` 前须确保停在对应模式页（登录错误留 `#/login`、注册错误留 `#/register`）。

### 前端接线锚点（源自 `prototype/app/app.js`，行号已核实）

- **登录/注册表单提交**：`bindAuthInteractions`（app.js:1695-1729），submit handler 在 **1710-1719**（当前 `setTimeout` 假延迟跳 `#/projects`——本 story 替换核心）。`reportValidity()`（1712）前置校验、submit disable + 文案（1713-1716）保留。
- **模式判定**：`currentMode()`（app.js:270-272）据 hash 是否 `#/register` 返 `register`/`login`。
- **状态位机制**：`queryState()`（app.js:265-268）读 `?state=`；`stateMessage(state, mode)`（app.js:274-286）映射文案；`renderAuth`（app.js:288-341）据此渲染 `.message`（app.js:322）。**7.1 前已存在，本 story 复用不改**。
- **退出按钮**：`renderProjects` header（app.js:405）`<a href="#/login">退出</a>`（纯链接，须改为调 logout）；事件绑定加在 `bindProjectInteractions`（app.js:1736 起）。
- **表单字段 id**：邀请码 `#invite`（仅注册，required app.js:324）、邮箱 `#email`（type=email required）、密码 `#password`（minlength=8 required app.js:326）。
- **路由**：`render()`（app.js:2316-2340）hash dispatcher，`else renderAuth()` 兜底登录/注册；`#/projects`→`renderProjects`。**本 story 不加鉴权守卫**。
- **7.1 临时冒烟入口**：`window.__museApiSmoke`（api.js:297-322）——本 story Task 5 移除。

### 受控决策记录（[[feedback_design_decision_delegation]] 已授权先例可依时自主选最优）

1. **注册成功须串接 login（后端契约事实，非可选）**。`POST /api/auth/register` 返 `{id, email}` **不签发 token**（auth.py:29 注释 + 7.1 受控决策 8 已坐实）。epics 7.2 AC1（1270）明写「成功后存 token 并跳 `#/projects`」——但注册接口不给 token，故须在注册成功后立即 `authApi.login` 拿 token。此串接逻辑 7.1 明确 defer 到 7.2（7.1 story:119），是本 story 的活。用注册时同一 email/password 串接。
2. **失败后必须恢复 submit 按钮态**。当前假延迟成功即跳走不复位（app.js:1714 disable + 文案改「正在登录…」）。真实调用失败时须复位按钮可用 + 文案还原，否则卡灰态。**便捷做法**：失败跳 `#/login?state=xxx` / `#/register?state=xxx` 会触发 hashchange→render→重绘表单天然复位；**但若目标 hash 与当前完全相同**（如已在 `#/login` 无 state、再错一次仍无 state 变化）hashchange 不触发，须手动复位。稳妥起见：`catch` 里显式恢复按钮 disabled=false + 文案，再按需改 hash。
3. **本 story 不加路由鉴权守卫**。未登录直接输 `#/projects` URL 的全局拦截 V1 不做（7.1 已 defer，7.1 story:34/84）。理由：业务请求（作品列表等）在 7.3 接线后经 `apiFetch` 发出，无 token → 401 → 7.1 `apiFetch` 自动 `clearTokens`+跳登录（api.js:136-140），足以兜住「未登录看不到数据」。纯静态页壳短暂可见不构成数据泄露（NFR3 是数据隔离，非 URL 隐藏）。如后续要更严可在部署/加固批次补，本 story 不引入。
4. **退出改按钮而非保留纯链接**。纯 `<a href="#/login">` 会绕过 logout 直接跳 hash（本地 token 不清、后端 refresh 不作废，留登录态残留）。改为拦截 click 先调 `authApi.logout()` 再跳。header 邮箱硬编码（creator@example.com）本 story 不改（真实邮箱展示归 7.3）。

### 本机开发环境（[[muse_local_dev_env]]）

- `uv` 在 `~/.local/bin`；容器用 Colima（非 Docker 桌面）；清华镜像。
- 后端 DB 相关须 `MUSE_DB_READY=1`；限流锁定态须 Redis 就绪（`MUSE_REDIS_READY=1`）——本地无 Redis 时限流 fail-open 放行，无法复现 `locked`，据后端 code 分支即可。
- 双端联调：真实后端 `:8000` + 原型静态 `:4173`（`cd prototype/app && python3 -m http.server 4173 --bind 127.0.0.1`），7.1 后端 dev CORS 已配（允许 `:4173` origin + Authorization 头）。

### Project Structure Notes

- 前端沿用原型 `prototype/app`（architecture.md:324 不重构目录）：本 story 只改 `app.js`（`bindAuthInteractions` submit + `renderProjects` 退出 + `bindProjectInteractions` 绑定）+ 移除 `api.js` 冒烟入口段。**不新增前端文件**（地基 api.js 7.1 已建）。
- 无后端改动（认证接口 Epic 1 done、CORS 7.1 done）。
- 命名：前端 camelCase（architecture.md:305）；后端出入参已 camelCase，前端直接用（7.1 受控决策 2，不写转换器）。

### References

- [Source: epics.md#Story-7.2（1260-1290）] — 本 story 6 条 AC 原文
- [Source: epics.md#Epic-7（1223-1231）] — Epic 7 目标、Story 依赖（7.1→7.2→{7.3,7.4}）、不新增 FR、严格保持原型交互契约
- [Source: epics.md#UX-DR9（160）] — 错误/边界状态对接（expired/invalid/locked → error envelope 布尔位）
- [Source: epics.md#FR1（37）] — 邮箱+密码注册（邀请码）与登录，真实会话（access+refresh）
- [Source: 7-1-统一请求工具地基...md] — 地基交付物（apiFetch/authApi/ApiError/redirectToLogin）、受控决策 8（注册不签发 token）、后端契约表、error code 映射
- [Source: prototype/app/api.js:227-276] — `authApi`（register/login/logout/refresh）薄封装（本 story 复用）
- [Source: prototype/app/api.js:77-101] — `ApiError`/`toApiError`（catch 分支据此）
- [Source: prototype/app/api.js:297-322] — 临时冒烟入口 `__museApiSmoke`（本 story 移除）
- [Source: prototype/app/app.js:1695-1729] — `bindAuthInteractions`（submit 假延迟须替换）
- [Source: prototype/app/app.js:405] — 作品库 header「退出」纯链接（须改调 logout）
- [Source: prototype/app/app.js:1736-1760] — `bindProjectInteractions`（退出事件绑定点）
- [Source: prototype/app/app.js:270-286,288-341] — currentMode/queryState/stateMessage/renderAuth（状态位机制，复用不改）
- [Source: backend/src/muse/routers/auth.py:26-70] — register(201)/login(200)/logout(204) 真实路由
- [Source: backend/src/muse/services/auth_service.py:32-160] — invalid_invite/invalid_credentials/too_many_attempts/token_invalid error code
- [Source: backend/src/muse/services/rate_limit.py:6-9,21-22] — 登录限流 5 次/15 分、429 locked、fail-open

## Dev Agent Record

### Agent Model Used

Claude Opus 4.8 (claude-opus-4.8)

### Debug Log References

- 纯逻辑单测（Node vm 抽取 app.js 纯函数，无 DOM 依赖）：`authStateFromError` + `stateMessage` 共 16 项断言全绿——覆盖 AC6 全部 error code 映射（invalid_credentials/invalid_invite→invalid、too_many_attempts→locked、token_invalid→expired、validation_error/unknown/invalid_response/空/null→failed 兜底）+ detail 布尔位回退 + 文案随 login/register 模式变 + 新增 failed 中性兜底文案。
- 后端契约层 curl 端到端（真实后端 :8000 + Redis + DB 容器 healthy，邀请码 STORY72-TEST）：9 场景全部对齐 story 映射表——① CORS 预检 200；② 注册 201 返 `{id,email}` **无 token**（坐实串接 login 必要性）；③ 登录 200 双 token camelCase；④ 错密码 401 `invalid_credentials`+`detail.invalid`；⑤ 无效邀请码 400 `invalid_invite`+`detail.invalid`；⑥ 已用邀请码复用 400 `invalid_invite`；⑦ 登出 204；⑧ 登出后 refresh 401 `token_invalid`+`detail.expired`；⑨ 连错 6 次第 6 次 429 `too_many_attempts`+`detail.locked`（Redis 就绪锁定态可复现）。
- 真实浏览器 UI 联调（playwright + 系统 Chrome，双端 :8000/:4173）：13 项 UI 断言全绿——① 注册→串接 login→进作品库 + localStorage 有 access token；② 登录正确密码→进作品库；③ 错密码→invalid 文案 + submit 按钮复位（disabled=false、文案复原「登录到创作空间」）+ 停登录页；④ 无效邀请码→register invalid 文案 + 停注册页；⑤ 退出→回登录页 + localStorage token 清空；⑦ expired 文案呈现；零回归（控制台无 JS pageerror）。截图人工核对：注册后作品库正常渲染（退出按钮就位、mock 列表/硬编码邮箱如期未变——归 7.3）、错密码红框文案 + 按钮已复位。
- 后端全量回归：`pytest -q` → 340 passed, 2 skipped，零回归（本 story 无后端改动，符合预期）。
- 前端语法检查：`node --check api.js && node --check app.js` 通过；确认 `__museApiSmoke` 无残留。

### Completion Notes List

- **交付**：改 `prototype/app/app.js` 三处 + 删 `prototype/app/api.js` 冒烟入口段。
  - `bindAuthInteractions` submit handler（app.js）：假延迟 `setTimeout` 替换为真实 async 调用——登录模式直调 `authApi.login`；注册模式 `authApi.register`→**串接 `authApi.login`**（受控决策 1，因注册不签发 token）；成功跳 `#/projects`；`catch` 经 `authStateFromError` 映射状态位跳 `?state=`，并显式复位 submit 按钮（disabled=false + 文案还原，防同 hash 不触发 render 时卡灰态——受控决策 2）。
  - 新增纯函数 `authStateFromError(err)`（app.js，紧接 `stateMessage`）：按后端 `code` 严格映射 invalid/locked/expired，未知落 `failed` 中性兜底（AC6 不臆造分支）；code 不可识别时回退 detail 布尔位；对 null/空错误不崩。
  - `stateMessage` 新增 `failed` 态文案「操作未能完成，请检查网络后稍后重试。」（未知/网络/校验类错误兜底）。
  - `renderProjects` header 退出（app.js:405）：`<a href="#/login">` 加 `data-logout` 标识；`bindProjectInteractions` 新增 `[data-logout]` click 绑定——`preventDefault` → `await authApi.logout()` → 跳 `#/login`（受控决策 4，避免纯链接绕过 logout 留登录态残留）。
  - 移除 `api.js` 末尾临时冒烟入口 `window.__museApiSmoke`（7.1 遗留，明确 7.2 接 UI 后删）。
- **受控决策落地**：① 注册成功串接 login 拿 token（后端契约事实，已 UI 坐实）；② 失败显式复位 submit 按钮；③ 未加路由鉴权守卫（业务请求 401 由 7.1 apiFetch 兜住，符合 story 边界）；④ 退出改按钮调 logout。
- **边界严守（零越界）**：未接任何业务页（作品库列表/探索/设定仍 mock）；未改 `api.js` 地基逻辑（仅删冒烟入口）；header 邮箱硬编码 `creator@example.com` **未改**（真实邮箱展示归 7.3，保持零回归）；未加构建/打包/module。
- **测试策略说明**：前端为全局脚本静态站、无测试运行器（7.1 亦未给 app.js 写单测因其重 DOM/全局态）。故把可提取的纯逻辑（error code→state 映射）抽成 `authStateFromError` 独立函数做 Node vm 回归（16 项），DOM 交互走真实浏览器 playwright 联调（13 项）+ 后端契约 curl（9 场景）三层验证，覆盖全部 6 条 AC。

### File List

- `prototype/app/app.js`（修改）— submit handler 真实接线（登录 + 注册串接 login）；新增 `authStateFromError`；`stateMessage` 加 `failed` 态；header 退出加 `data-logout` + `bindProjectInteractions` 绑定 logout
- `prototype/app/api.js`（修改）— 移除临时冒烟入口 `window.__museApiSmoke`
- `_bmad-output/implementation-artifacts/deferred-work.md`（修改）— 标注 7.1 登记的「登录注册接线」「冒烟入口移除」已由 7.2 兑现；作品库邮箱展示仍 defer 至 7.3
- `_bmad-output/implementation-artifacts/sprint-status.yaml`（修改）— 7-2 状态 ready-for-dev → in-progress → review

## Change Log

- 2026-07-30：实现 Story 7.2 登录/注册接线（替换 mock）。submit handler 改真实 async 调用（登录直调 login、注册 register→串接 login）；新增 `authStateFromError` 按后端 error code 映射 invalid/locked/expired/failed；退出按钮改调 `authApi.logout`；移除 7.1 临时冒烟入口。Tasks 1–6 全部完成，AC1–6 满足。验证：纯逻辑 16 项 + 后端契约 curl 9 场景 + playwright UI 13 项全绿，后端全量回归 340 passed 零回归。
