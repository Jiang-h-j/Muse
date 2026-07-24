---
baseline_commit: 6967074
---

# Story 1.3: 用户登录与 JWT 双 token 会话

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a 已注册用户，
I want 用邮箱密码登录并获得可持续的真实会话，
so that 我能安全地回到创作空间且会话过期能被正确处理。

## Acceptance Criteria

**AC1 — 正确邮密登录，签发双 token（FR1 / AR3 / NFR6）**
- **Given** 我在登录页（`#/login`），邮箱 + 密码字段（原型 `prototype/app/app.js:306-307`，登录模式密码 `minlength="8"`、`autocomplete="current-password"`）
- **When** 我用正确的邮箱 + 密码登录
- **Then** 后端 argon2 `verify_password` 校验通过，签发 **access + refresh 双 token**（access = 无状态短期 JWT；refresh = 高熵随机串，其哈希落 `refresh_session` 表，见 Dev Notes 设计）
- **And** 接口返回成功资源体（camelCase，不套 `data` 包装，如 `{accessToken, refreshToken, tokenType:"Bearer", expiresIn}`），前端据此按原型行为进入 `#/projects`（原型 `app.js:1697-1699`，`650ms` 后跳转）

**AC2 — access 过期用 refresh 刷新；refresh 失效跳登录（会话不中断 / expired 文案）**
- **Given** 我持有的 access token 已过期、refresh token 仍有效
- **When** 我用 refresh token 请求刷新（`POST /api/auth/refresh`）
- **Then** 系统校验 refresh 有效（签名/存在于 `refresh_session` 表/未撤销/未过期）后签发**新 access token**，会话不中断（并按轮转策略作废旧 refresh、下发新 refresh，见 Dev Notes 陷阱④）
- **And Given** refresh token 亦失效（过期/被撤销/不存在）
- **When** 我请求刷新或访问受保护接口
- **Then** 后端返回可识别的 `401` error envelope（`code=token_invalid`/`token_expired`），前端据此跳 `#/login?state=expired`，呈现文案「会话已过期，请重新登录。登录后会返回你的创作空间。」（原型 `app.js:257`，经 `stateMessage(state,'login')`）

**AC3 — 邮箱或密码错误被拒（原型 `invalid` 文案对接，不签发 token）**
- **Given** 我在登录页
- **When** 邮箱不存在、或密码错误
- **Then** 后端返回统一 error envelope `{code, message, detail}`（HTTP 401），响应体附兼容原型的布尔位（`detail.invalid=true`），**不签发任何 token**
- **And** 前端呈现登录模式 `invalid` 文案「邮箱或密码错误，请检查后重试。」（原型 `app.js:261`，`stateMessage` 按 `mode==='login'` 分支）
- **And** 错误措辞对「邮箱不存在」与「密码错误」**完全一致**，且两分支耗时相近（等时校验，防邮箱枚举，见 Dev Notes 陷阱③）

**AC4 — 登录失败限流锁定（AR6 / 原型 `locked` 文案）**
- **Given** 同一账号（归一化邮箱）登录失败次数在时间窗内超过阈值（默认 5 次 / 15 分钟，见 Dev Notes）
- **When** 我继续尝试登录
- **Then** 触发锁定：后端返回 `429` error envelope（`code=too_many_attempts`，`detail.locked=true`），**锁定窗口内直接拒绝、不再做密码校验**（省 argon2 开销且不泄露账号是否存在）
- **And** 前端呈现 `locked` 文案「登录尝试次数过多，请稍后再试。」（原型 `app.js:264`）
- **And** 登录成功后清零该账号的失败计数；限流后端（Redis）不可用时 **fail-open**（记 warning，不阻断登录，内测期可用性优先）

**AC5 — 退出使会话失效（refresh 作废，受保护接口需重新登录）**
- **Given** 我已登录，持有有效 refresh token
- **When** 我点击作品库 header 的「退出」（原型 `app.js:385`，当前为纯 `<a href="#/login">` mock），前端调用 `POST /api/auth/logout` 提交当前 refresh
- **Then** 该 refresh 对应的 `refresh_session` 行被撤销（`revoked_at=now`），此后用它刷新一律 `401`；再访问受保护接口需重新登录
- **And** 提供最小受保护端点 `GET /api/auth/me`（经 `get_current_user` 依赖鉴权）用于验证「有效 access 可访问、失效/缺失 token 被 401 拒」，兑现 AC5 的「受保护接口」语义

**AC6 — refresh 会话表落地 + 生产密钥 fail-fast（建表范围 / NFR6 / deferred 纳入）**
- **Given** 需按需建 `refresh_session` 表（epics.md `按需建表：1.3 refresh 会话`）
- **When** 建表迁移执行
- **Then** `refresh_session` 表带 `user_id` FK 指向 `user`（NFR3 租户根延续），`alembic upgrade head` 升级、`downgrade` 可回滚，autogenerate 能检出新表（模型须在 `migrations/env.py` 登记 import，见陷阱②）
- **And** 应用启动时若 `debug=False` 且 `jwt_secret` 仍为默认占位值 `dev-only-change-me`，**启动即失败**（fail-fast，兑现 deferred-work.md L5）

## Tasks / Subtasks

- [x] **Task 1：`refresh_session` ORM 模型 + 迁移（AC1, AC5, AC6）**
  - [x] 在 `models/account.py` 新增 `RefreshSession`（继承 `Base` + `UUIDPKMixin` + `TimestampMixin`）：`user_id`（`ForeignKey("user.id")`, 非空, 建索引）、`token_hash`（`String`, 唯一, 非空——存 refresh 的 SHA-256 十六进制，**不存明文**）、`expires_at`（`DateTime(timezone=True)`, 非空）、`revoked_at`（`DateTime(timezone=True)`, 可空，NULL=有效）
  - [x] **放 `models/account.py` 而非新建 `models/session.py`**：会话属账户域，且 `migrations/env.py:13` 已 `from muse.models import account`，复用该 import 免踩陷阱②（若另起新模块务必在 env.py 补 import）
  - [x] `uv run alembic revision --autogenerate -m "create refresh_session"`，`Revises` 应指向 `56139203fb92`（1.2 迁移）；人工核对唯一约束/FK/索引，`upgrade`/`downgrade` 往返通过
- [x] **Task 2：JWT 编解码 + `verify_password`（core/security.py，AC1, AC2, AC3）**
  - [x] 在 `core/security.py` 补 `verify_password(hash, plain) -> bool`：`PasswordHasher().verify`，捕获 `argon2.exceptions.VerifyMismatchError` 返回 `False`；同样经 `anyio.to_thread.run_sync` 挪线程池（延续 `hash_password` 做法，argon2 是 CPU 密集，勿阻塞事件循环）
  - [x] 新增 `create_access_token(user_id) -> (token, expires_in)`：PyJWT `jwt.encode`，payload `{sub, type:"access", iat, exp}`，HS256 + `settings.jwt_secret`；`decode_access_token(token) -> claims`：`jwt.decode`，捕获 `ExpiredSignatureError`/`InvalidTokenError` 转语义化结果（**用 pyjwt，勿用 python-jose——已移除，见强制变更**）
  - [x] refresh 生成：`secrets.token_urlsafe(32)` 明文 + `hashlib.sha256` 哈希。**refresh 哈希用 SHA-256 不用 argon2**（陷阱⑤：refresh 是高熵随机串，无字典/暴力面，argon2 会让高频刷新路径无谓变慢）
- [x] **Task 3：登录失败限流（AR6，AC4）**
  - [x] 新增 async Redis 客户端依赖：`uv add redis`（用 `redis.asyncio`）；连接串复用 `settings.redis_url`（已在 settings/`.env.example`）
  - [x] 新增 `services/rate_limit.py`（或 `core/rate_limit.py`）：`check_and_incr_login_failure(email)` / `reset_login_failures(email)` / `is_locked(email)`；key `login:fail:<normalized_email>`，`INCR` + 首次 `EXPIRE`（窗口 15 min），达阈值 5 视为锁定
  - [x] **fail-open**：Redis 连接异常时 `try/except` 记 warning 并放行（内测期可用性优先，AC4）；锁定判定在密码校验**之前**
- [x] **Task 4：登录/刷新/退出 schema（AC1, AC2, AC5）**
  - [x] `schemas/account.py` 新增：`LoginRequest{email, password}`（继承 `CamelModel`，`email` 用 `EmailStr` + 复用 1.2 的 `_normalize_email` 归一化口径；`password` 不设 min_length——登录不暴露密码策略，避免旁路提示，仅非空）
  - [x] `TokenResponse{access_token, refresh_token, token_type, expires_in}`、`RefreshRequest{refresh_token}`、`LogoutRequest{refresh_token}`、`MeResponse{id, email}`（均 `CamelModel`，边界自动 camelCase：`accessToken`/`refreshToken`/`tokenType`/`expiresIn`）
- [x] **Task 5：refresh 会话 repository（AC1, AC2, AC5）**
  - [x] 新增 `repositories/session_repo.py`（或并入 `account_repo.py`）：`create_refresh_session`、`get_active_by_token_hash`（未撤销未过期）、`revoke_by_token_hash`、（轮转用）`revoke_and_replace`
  - [x] 复用 `account_repo.get_user_by_email` 查登录用户；事务边界（commit/rollback）由 service 编排，repo 只 flush（延续 1.2 约定）
- [x] **Task 6：登录/刷新/退出 service（AC1-AC5）——业务编排在此，不在 router**
  - [x] `services/auth_service.py` 新增 `login(session, email, password)`：① `is_locked` 早拒（AC4）→ ② 查 user；**user 不存在也要跑一次等时 argon2 verify**（用固定假 hash）消除时序差（陷阱③）→ ③ `verify_password` 失败则 `incr` 失败计数 + 抛 `invalid_credentials`（`detail.invalid=true`, 401）→ ④ 成功则 `reset` 计数 + 签发 access + 建 refresh_session + 返回 token
  - [x] `refresh(session, refresh_token)`：SHA-256 → 查 active session → 无/失效抛 `token_invalid`（401）→ 签发新 access（轮转：作废旧 refresh + 下发新 refresh，防重放，陷阱④）
  - [x] `logout(session, refresh_token)`：`revoke_by_token_hash`（幂等——已撤销/不存在均视为成功，退出不应报错）
  - [x] 错误措辞：邮箱不存在与密码错误**共用同一 envelope 文案**「邮箱或密码错误，请检查后重试。」（AC3，不泄露账号是否存在）
- [x] **Task 7：鉴权依赖 `get_current_user`（AC5）**
  - [x] 新建 `core/deps.py`（core 横切基座聚合 FastAPI 依赖）：`get_current_user` — 从 `Authorization: Bearer` 提取 access → `decode_access_token` → 查 user → 返回；无/过期/非法 token 抛 `401`（`code=token_expired`/`token_invalid`，对接原型 `expired` 分支）
  - [x] 导出 `CurrentUser = Annotated[User, Depends(get_current_user)]` 供后续所有受保护 router 复用（1.4 project 起大量使用）
- [x] **Task 8：登录/刷新/退出/me router（AC1-AC5）**
  - [x] `routers/auth.py` 新增 `POST /api/auth/login`、`POST /api/auth/refresh`、`POST /api/auth/logout`、`GET /api/auth/me`（`me` 依赖 `CurrentUser`）；router 仅校验 + 分发，业务在 service（AR2，以现有 `register` 为样板）
  - [x] 登录/刷新成功返回 `TokenResponse`；`logout` 返回 204 或简单成功体；错误经既有全局 handler 转 envelope
- [x] **Task 9：生产护栏（deferred-work.md L5-6 纳入，AC6）**
  - [x] **JWT 弱密钥 fail-fast**：在 `core/settings.py` 加 `model_validator`（或 `create_app` 启动断言）——`debug=False` 且 `jwt_secret=="dev-only-change-me"` 时抛错拒绝启动
  - [x] **SQL echo 与 debug 解耦**：`core/settings.py` 加独立 `db_echo: bool = False`，`core/db.py:20` 改 `echo=settings.db_echo`（存 token_hash/密码相关表后，SQL echo 会打印绑定参数，不应随 debug 一起开）
  - [x] JWT 有效期设为可配置 settings（`access_token_ttl_seconds` 默认 900、`refresh_token_ttl_seconds` 默认 30 天），补进 `.env.example`
- [x] **Task 10：测试（全 AC）**
  - [x] `tests/test_auth_login.py`（pytest-asyncio，镜像 src 树，复用 1.2 的 conftest DB fixture + `MUSE_DB_READY=1` 门禁）：①正确邮密登录得双 token + `me` 可访问 ②错误密码/邮箱不存在均 401 `invalid` 且不签发 token ③access 过期用 refresh 刷新得新 access、refresh 失效 401 ④失败超阈值 429 `locked` + 成功后计数清零 ⑤退出后旧 refresh 刷新 401 + 无/过期 token 访问 `me` 被 401
  - [x] 限流用例：mock/fake Redis 或标注 `requires_redis` 门禁；覆盖 fail-open（Redis 不可用不阻断）
  - [x] JWT 单元测试可离线（不需 DB）：签发→解码 round-trip、过期 token 被拒、篡改签名被拒
  - [x] 跑通 `uv run ruff check`、`uv run mypy`、`uv run pytest`（全绿方可 done）；curl 端到端走通全 AC（延续 1.2，真机起 FastAPI + 真实 PG）
- [x] **Task 11：前端接线契约说明（不改原型，AC1-AC5）**
  - [x] 在 Dev Agent Record 记录后端契约与前端接线点（login submit `app.js:1690-1700`、退出 `app.js:385`、状态位 `app.js:246-267`），**原型 `app.js` 一字节不改**——真实 fetch/token 存储/错误态回填在页面即契约方法论下随统一接线 pass 落地（延续 1.2）
  - [x] `backend/README.md` 补「本地登录/刷新/退出」curl 示例小节

## Dev Notes

### ⚠️ 强制变更（epics.md 旧文本已过期，一律以下表为准，不遵守必然返工）
1.1 code review（2026-07-24 裁决）改动的地基，1.2 已落实，本 story 继续遵循：

| 事项 | epics.md 字面（旧，勿用） | 实际现状（必须遵循） | 证据 |
|---|---|---|---|
| JWT 库 | `python-jose` | **pyjwt[crypto]**（`import jwt`） | `backend/pyproject.toml:15` |
| 密码哈希 | `passlib[bcrypt]` | **argon2-cffi**（`from argon2 import PasswordHasher`） | `backend/src/muse/core/security.py:9` |
| 主键 | 自增整型 | **UUID**（`UUIDPKMixin`，应用侧 `default=uuid4`） | `models/base.py:36` |

- `python-jose` / `passlib` **已从依赖移除**，import 会直接报错。
- `core/security.py:15-21` 已有 async `hash_password`（argon2 经 `anyio.to_thread`），本 story 补 `verify_password` 照此 async + 线程池模式。

### 双 token 设计（V1 已决策，dev 照此实现）
- **access token**：无状态 JWT，短 TTL（默认 900s）。payload `{sub:<user_id>, type:"access", iat, exp}`，HS256 + `settings.jwt_secret`。无状态 = 每请求本地验签，不查库。
- **refresh token**：高熵随机串（`secrets.token_urlsafe(32)`），**只把 SHA-256 哈希存 `refresh_session` 表**，明文仅下发前端一次（泄库不可反推）。长 TTL（默认 30 天）。带服务端表 = 可撤销（AC5 退出、AC2 失效判定），弥补纯无状态 JWT 无法注销的短板。
- **为何 refresh 不做成 JWT**：AC5 要求「退出使 refresh 作废」，纯 JWT 无状态不可撤销；epics.md:243「按需建表：1.3 refresh 会话」正为此表。access 无状态保效率，refresh 有状态保可撤销——各取所长。
- **存储/传输取舍（我方决策）**：双 token 均由前端存 localStorage、请求带 `Authorization: Bearer <access>`，贴合 architecture.md:165「无状态、原型 localStorage 已适配」，零 CORS/CSRF 额外配置，最省。**代价**：refresh 长效凭证暴露于 XSS。→ 已作为「开放注册前的加固项」记入 Deferred Work（refresh 迁 httpOnly+Secure+SameSite cookie），与 1.2 邮箱枚举取舍同一处置逻辑。

### 关键实现陷阱（务必规避）
- **陷阱①：JWT 库是 pyjwt 不是 python-jose。** `import jwt`（PyJWT），`jwt.encode/decode`。`jwt.decode` 过期抛 `jwt.ExpiredSignatureError`、非法抛 `jwt.InvalidTokenError`，分别映射 `token_expired`/`token_invalid` envelope（对接原型 `expired` 态）。
- **陷阱②：新增/迁移模型必须在 `migrations/env.py` 登记 import。** `env.py:13` 已 `from muse.models import account`——`RefreshSession` 放 `account.py` 即自动被 autogenerate 看见；若另建模块务必补 import，否则生成空迁移**却不报错**（1.1/1.2 均已预警）。
- **陷阱③：邮箱枚举 / 时序侧信道（AC3 硬要求「不泄露多余信息」）。** 邮箱不存在与密码错误必须：(a) 返回**完全相同**的 envelope 文案；(b) 耗时相近——user 不存在时也跑一次 argon2 `verify` 对固定假 hash，避免「不存在=快返回/存在=慢 verify」的时序区分。1.2 注册侧的枚举问题已 defer（内测接受），但**登录是开放前哨，等时兜底成本低、值得做**。
- **陷阱④：refresh 轮转防重放。** 每次 `refresh` 成功应作废旧 refresh + 下发新 refresh（rotation）。若检测到已撤销的 refresh 被再次使用（重放信号），可选作废该用户全部 session。V1 至少做「旧作废+发新」，重放全撤为增强。
- **陷阱⑤：refresh 哈希用 SHA-256，不是 argon2。** refresh 是高熵随机串（无字典/暴力面），SHA-256 足够且快；argon2 会让高频刷新路径无谓变慢。**密码**仍用 argon2（低熵、需抗暴力）——两者勿混。
- **陷阱⑥：限流锁定判定在密码校验之前。** 锁定态直接返回 `locked`，不进 argon2 verify（省开销 + 不泄露账号存在性）。Redis 不可用 fail-open（AC4）。
- **陷阱⑦：logout 幂等。** 传入已撤销/不存在的 refresh 也返回成功——退出是终态操作，不应因 token 已失效而报错。

### 强制复用的基座 pattern（照抄，勿另起炉灶）
- **分层样板**：`routers/auth.py`（现有 `register`）→ `services/auth_service.py` → `repositories/*` → `core/db.get_session`（`SessionDep = Annotated[AsyncSession, Depends(get_session)]`）。login/refresh/logout/me 照此结构扩展同一批文件。
- **schema 边界（AR4）**：新 schema 继承 `schemas/base.py:CamelModel`（L29-34，`alias_generator=to_camel, populate_by_name=True, from_attributes=True`）。前端提交 `refreshToken`（camel）自动映射 `refresh_token`；响应 `accessToken`/`expiresIn` 自动 camel。**禁止两端手写不一致字段名。**
- **错误 envelope（AR5）**：业务错误抛 `core/errors.py:ErrorEnvelope(code, message, detail, http_status)`（L17-31），全局 handler 已注册。校验错误脱敏（剔除 `input`）已就绪（`_handle_validation`），登录密码不会被反射回响应体。
- **邮箱归一化**：复用 1.2 的 `_normalize_email`（`schemas/account.py`，`.strip().lower()` + 超长 422）——登录邮箱须与注册**同一归一化口径**，否则大小写差导致查不到 user。
- **时间序列化（AR5）**：如响应含时间字段用 `schemas/base.py:UTCDateTime`（输出带 `Z`）。

### 原型交互契约（页面即契约，AC 事实来源，`prototype/app/app.js` 一字节不改）
- `app.js:257` — 登录 `expired` 文案「会话已过期，请重新登录。登录后会返回你的创作空间。」；`app.js:261` — 登录 `invalid` 文案「邮箱或密码错误，请检查后重试。」；`app.js:264` — `locked` 文案「登录尝试次数过多，请稍后再试。」（`stateMessage` 按 `state` + `mode` 分支，`app.js:255-267`）。
- `app.js:306-307` — 登录模式邮箱 `type=email required`、密码 `minlength=8 autocomplete=current-password`。
- `app.js:1690-1700` — 登录 submit：`reportValidity()` → 按钮转「正在登录…」→ `650ms` 后 `location.hash="#/projects"`。**本 story 后端替换「提交真正校验+签发」，前端跳转形态不变。**
- `app.js:385` — 作品库 header `<a href="#/login">退出</a>`（当前纯 hash 跳转 mock，无 token 逻辑）。本 story 提供 `POST /api/auth/logout`；前端「点退出先作废 refresh 再跳转」的接线随统一接线 pass 落地。
- 说明：原型 submit/退出均为 mock（固定 setTimeout 跳转、不发请求）。V1 由本 story 提供真实 `/login`/`/refresh`/`/logout` 接口；前端接线在页面即契约方法论下随后端接入，保持原型 DOM/文案不变（epics.md UX-DR9：`expired`/`invalid`/`locked` 状态位对接后端 envelope 布尔位）。
- 注：epics.md L308-326 引用的原型行号（246/247-248/253/374）为近似/旧值，以上为核实后的真实行号（1.2 已同样纠偏）。

### 建表范围与后续依赖
- 本 story 只建 `refresh_session`（epics.md「按需建表：1.3 refresh 会话」）。**不建** project/byok_key/usage_ledger（各归 1.4/1.7/1.8）。
- `refresh_session.user_id` FK 指向 1.2 已建的 `user`（租户根，NFR3）。`repositories/base_repo.py` 跨表租户守卫仍是占位——**从 1.4（project 带 user_id）起才实装**；本 story refresh 查询按 `token_hash` 唯一键直查即可。
- `core/deps.py:get_current_user` + `CurrentUser` 类型别名是**全项目受保护接口的鉴权入口**，1.4 起所有业务 router 依赖它，务必做成可复用依赖。

### Project Structure Notes
- 新增文件与 architecture.md 目录树对齐：`repositories/session_repo.py`、`services/rate_limit.py`、`core/deps.py`、`tests/test_auth_login.py`；扩展 `models/account.py`(+RefreshSession)、`schemas/account.py`、`repositories/account_repo.py`(复用)、`services/auth_service.py`、`routers/auth.py`、`core/security.py`、`core/settings.py`、`core/db.py`。
- **偏差与理由**：(a) `RefreshSession` 放 `models/account.py`（architecture 目录树注释仅列 user/project/byok_key/usage_ledger）——会话属账户域，且复用 env.py 既有 import 避陷阱②；(b) 新增 `core/deps.py`（目录树未显式列）——core 为横切基座，聚合 FastAPI 依赖符合其定位；(c) 新增 `redis` 依赖——AR21/AR6 已规划 Redis，容器已在 `docker-compose.yml` 起。三处均属合理扩展，记此备查。
- 沿用 1.1 src-layout（`backend/src/muse/`）与 pytest 镜像布局；前端 `prototype/app` 不改（铁律：原型=唯一契约事实基准）。

### 质量门禁（沿用 1.1/1.2，done 前必过）
- `uv run ruff check` 全过、`uv run mypy` 无 issue、`uv run pytest` 全绿。
- 迁移：`alembic upgrade head` 升级成功、`downgrade` 可回滚、autogenerate 能检出 `refresh_session`。
- curl 端到端：登录得双 token → `me` 可访问 → access 过期用 refresh 刷新 → 退出后旧 refresh 401（真机起 FastAPI + 真实 PG + Redis）。

### References
- [Source: _bmad-output/planning-artifacts/epics.md#Story-1.3（L300-326）] — 用户故事、5 条 AC、原型行号引用、双 token/限流/退出要求。
- [Source: _bmad-output/planning-artifacts/epics.md#Epic-1-Story依赖（L242-243）] — 1.2→1.3 依赖链、按需建表「1.3 refresh 会话」。
- [Source: _bmad-output/planning-artifacts/architecture.md#Authentication-Security（L164-171）] — JWT 自建 access+refresh 双 token、无状态、行级租户隔离。
- [Source: _bmad-output/planning-artifacts/architecture.md#API-Communication（L172-176）] — 错误 envelope + 布尔状态位、按用户+端点限流。
- [Source: _bmad-output/planning-artifacts/architecture.md#Format-Patterns（L328-332）] — 登录/校验错误响应附 `expired`/`invalid`/`locked` 布尔位对接原型。
- [Source: _bmad-output/planning-artifacts/architecture.md#Naming-Patterns（L283-306）] — snake_case↔camelCase 边界、DB/API 命名。
- [Source: _bmad-output/implementation-artifacts/1-2-用户注册邀请码.md#Review-Findings（L153）] — 邮箱枚举/时序侧信道 defer 裁决（登录侧本 story 做等时兜底）。
- [Source: _bmad-output/implementation-artifacts/deferred-work.md（L5-6）] — JWT 弱密钥 fail-fast、SQL echo 与 debug 解耦，明确路由到 Story 1.3。
- [Source: backend/src/muse/core/security.py（L15-21）] — 现有 async `hash_password`（argon2+anyio），本 story 补 `verify_password` + JWT。
- [Source: backend/src/muse/core/settings.py（L29）] — `jwt_secret` 占位，本 story 加 fail-fast + JWT TTL 配置。
- [Source: backend/src/muse/core/db.py（L20）] — `echo=settings.debug`，本 story 解耦为独立 `db_echo`。
- [Source: backend/src/muse/models/account.py（L17-43）] — User 租户根 + InviteCode；RefreshSession 加于此文件。
- [Source: backend/src/muse/repositories/account_repo.py（L16-18）] — `get_user_by_email` 复用查登录用户。
- [Source: backend/src/muse/services/auth_service.py] — 现有 `register` 编排样板；login/refresh/logout 加于此。
- [Source: backend/src/muse/routers/auth.py（L17-27）] — 现有 `register` router 样板（router 仅校验+分发）。
- [Source: backend/src/muse/schemas/base.py（L25-34）] — CamelModel + UTCDateTime 边界基类。
- [Source: backend/src/muse/core/errors.py（L17-31）] — ErrorEnvelope + 全局 handler（脱敏就绪）。
- [Source: backend/tests/conftest.py（L28-77）] — DB fixture（`MUSE_DB_READY=1` 门禁、建表/清表/种子），本 story 复用并扩展。
- [Source: backend/migrations/env.py（L13）] — 已 `from muse.models import account`（RefreshSession 放此模块免补 import）。
- [Source: docker-compose.yml] — postgres(pgvector) + redis 容器（限流用 Redis 已就绪）。
- [Source: prototype/app/app.js（L257,261,264,306-307,385,1690-1700,246-267）] — 登录页字段、三态文案、submit 跳转、退出链接、状态位契约。

## Dev Agent Record

### Agent Model Used

Claude Opus 4.8 (claude-opus-4-8)

### Debug Log References

- **测试 collection 崩溃（fail-fast 护栏副作用）**：新增的 JWT 弱密钥 fail-fast（`DEBUG=false` + 默认密钥拒启动）触发本机 `.env`（`DEBUG=false` + 占位密钥）→ 所有测试在 import 期崩溃。根因是「默认占位密钥本只应在本地 `DEBUG=true` 可用」，原 `.env`/`.env.example` 的 `DEBUG=false` 组合在加护栏后自相矛盾。修复：`.env`/`.env.example` 改 `DEBUG=true`（附生产注释）；conftest 顶部 `os.environ.setdefault` 注入测试专用强密钥，使测试不依赖任何特定 `.env`。
- **`RuntimeError: Event loop is closed`（测试间事件循环污染）**：应用 async DB/Redis engine 是模块级单例，连接池绑定首个事件循环；`TestClient` 非上下文模式下每请求起临时循环，同一用例内发两次请求（login+me）时第二次撞上残留连接。修复：`test_auth_login.py` 加 module-scoped autouse fixture 以 `with _client:` 固定单一持久循环。注册测试（1.2）单请求故未暴露此问题。

### Completion Notes List

- 全 6 条 AC 实现并验证：ruff / mypy / pytest 全绿（44 passed / DB+Redis 全激活；离线 20 passed + 24 skipped），curl 端到端走通全 AC（真机 FastAPI + PG + Redis，端口 8100）。
- 双 token 设计按 Dev Notes 落地：access 无状态 JWT（pyjwt HS256，非 python-jose）、refresh 高熵随机串仅存 SHA-256 哈希；refresh 轮转防重放（陷阱④，e2e 验证旧 refresh 重放 401）。
- 陷阱全部规避：①pyjwt ②`RefreshSession` 放 `models/account.py` 复用 env.py import（autogenerate 正常检出）③等时防枚举（user 不存在也对固定假 hash 跑 verify）④refresh 轮转 ⑤refresh 用 SHA-256 非 argon2 ⑥锁定判定在密码校验前 ⑦logout 幂等。
- 生产护栏（AC6 / deferred-work.md L5-6）：JWT 弱密钥 fail-fast（三态验证通过）、`db_echo` 与 `debug` 解耦、JWT TTL 可配置并补入 `.env.example`。
- `core/deps.py:get_current_user` + `CurrentUser` 类型别名已就绪，作为 1.4 起全项目受保护接口的统一鉴权入口。
- **前端接线契约（原型 `prototype/app/app.js` 一字节未改，页面即契约）**：
  - 登录 submit（`app.js:1690-1700`）：真实接线时替换「`reportValidity()` → 按钮转『正在登录…』→ 650ms 跳转」中的 mock，改为 `POST /api/auth/login`，成功存 `accessToken`/`refreshToken` 到 localStorage 后 `location.hash="#/projects"`。
  - 退出（`app.js:385` 当前纯 `<a href="#/login">`）：接线时先 `POST /api/auth/logout`（提交当前 refreshToken）再跳转。
  - 状态位（`app.js:246-267` `stateMessage`）：后端 error envelope 的 `detail` 布尔位对接原型三态——`invalid`（`invalid_credentials`，登录文案「邮箱或密码错误，请检查后重试。」）、`expired`（`token_invalid`，refresh/access 失效 → 跳 `#/login?state=expired`）、`locked`（`too_many_attempts`）。
  - 受保护请求：带 `Authorization: Bearer <accessToken>`；收到 401 `token_expired` 时用 refreshToken 静默刷新，刷新亦失败则跳 `#/login?state=expired`。

### File List

**新增：**
- `backend/src/muse/core/deps.py` — `get_current_user` 鉴权依赖 + `CurrentUser` 类型别名（AC5）
- `backend/src/muse/services/rate_limit.py` — 登录失败限流（Redis，fail-open，AC4）
- `backend/src/muse/repositories/session_repo.py` — refresh 会话 DAO（AC1/AC2/AC5）
- `backend/migrations/versions/5feac516df19_create_refresh_session.py` — refresh_session 建表迁移（AC6）
- `backend/tests/test_auth_login.py` — 登录/刷新/退出/me + JWT + 限流全 AC 测试

**修改：**
- `backend/src/muse/models/account.py` — 新增 `RefreshSession` 模型（AC1/AC5/AC6）
- `backend/src/muse/core/security.py` — 补 `verify_password` + JWT 编解码 + refresh 生成/哈希 + 等时假 hash（AC1/AC2/AC3）
- `backend/src/muse/core/settings.py` — JWT 弱密钥 fail-fast + `db_echo` 解耦 + JWT TTL 配置（AC6）
- `backend/src/muse/core/db.py` — `echo=settings.db_echo`（与 debug 解耦，AC6）
- `backend/src/muse/schemas/account.py` — 新增 Login/Token/Refresh/Logout/Me schema + 提取共用 `_normalize_email`（AC1/AC2/AC5）
- `backend/src/muse/repositories/account_repo.py` — 新增 `get_user_by_id`（鉴权取用户，AC5）
- `backend/src/muse/services/auth_service.py` — 新增 `login`/`refresh`/`logout` 编排（AC1-AC5）
- `backend/src/muse/routers/auth.py` — 新增 `POST /login` `/refresh` `/logout` + `GET /me`（AC1-AC5）
- `backend/tests/conftest.py` — 测试专用强密钥注入 + 清 refresh_session/限流键 + `make_user` fixture
- `backend/.env` / `backend/.env.example` — `DEBUG=true` + `DB_ECHO` + JWT TTL 配置
- `backend/pyproject.toml` / `backend/uv.lock` — 新增 `redis` 依赖
- `backend/README.md` — 补「本地登录/刷新/退出」curl 小节

### Change Log

- 2026-07-24：实现 Story 1.3 用户登录与 JWT 双 token 会话（登录/刷新/退出/me、refresh 轮转、Redis 限流、生产护栏），全 6 条 AC 通过 ruff/mypy/pytest + curl 端到端验证。

## Review Findings（2026-07-24 code-review）

三层对抗审查（Blind Hunter / Edge Case Hunter / Acceptance Auditor）结论：**无硬性 AC 违反**——AC1–AC6、陷阱①–⑦、基座 pattern（CamelModel / ErrorEnvelope / _normalize_email / 分层）全部满足。以下为加固与健壮性 findings，多项为三层重叠（强信号）。

### Patch（已修复，2026-07-24 全部应用 + ruff/mypy/pytest 48 passed 验证）

- [x] [Review][Patch] 限流 INCR/EXPIRE 非原子，EXPIRE 失败会致账号永久锁定 [backend/src/muse/services/rate_limit.py:63-65] — 首次 INCR 成功后若 EXPIRE 抛错（被 fail-open 吞掉）或进程崩溃，key 永无 TTL；达阈值后合法用户被永久锁死，且登录成功无法清零（death spiral）。**已修复**：改用 Lua 脚本单次原子执行 INCR + 保底 EXPIRE（TTL<0 才补设），杜绝窗口。（MEDIUM）
- [x] [Review][Patch] JWT 弱密钥 fail-fast 仅拦「恰等占位串」，空串/超短密钥可绕过 [backend/src/muse/core/settings.py:47] — 生产设空或极短 JWT_SECRET 时 fail-fast 不触发，HS256 签名可被暴力/伪造。**已修复**：validator 增加 `len < 32` 校验（含空串），并补 test_weak_jwt_secret_fails_fast_in_production 回归测试。（MEDIUM）
- [x] [Review][Patch] verify_password 仅捕获 VerifyMismatchError，哈希损坏会 500 [backend/src/muse/core/security.py:64] — DB 中 password_hash 非法/损坏时 argon2 抛 InvalidHash/VerificationError 逃逸，登录退化成 500 而非 401。**已修复**：捕获 `(VerificationError, InvalidHashError)` 两条继承链返回 False，补 test_verify_password_returns_false_on_corrupt_hash。（LOW）
- [x] [Review][Patch] decode_access_token 未强制 exp 声明 [backend/src/muse/core/security.py:97] — 缺 exp 的 token 被当永不过期接受（当前不可外部利用，属纵深防御）。**已修复**：`jwt.decode` 加 `options={"require":["exp"]}`，补 test_missing_exp_token_rejected。（LOW）
- [x] [Review][Patch] refresh 会话读写混用两个时钟源 [backend/src/muse/repositories/session_repo.py:22 vs 41] — create 用应用 `datetime.now(UTC)` 写 expires_at，get_active 用 DB `func.now()` 比较；app/DB 时钟偏差致 refresh 提前或延后失效。**已修复**：get_active 统一改用应用时钟 `datetime.now(UTC)`（revoke 的 revoked_at 属纯写入语义，保持 func.now()）。（LOW）
- [x] [Review][Patch] RefreshRequest/LogoutRequest.refresh_token 无 max_length 上界 [backend/src/muse/schemas/account.py:85,91] — 超大 body 无约束进入 SHA-256+DB 查询。**已修复**：加 `max_length=512`。注：Blind 提出的「登录 password max_length 与注册不一致」经核实为**误报**，两侧均为 128。（LOW）
- [x] [Review][Patch] JWT TTL 配置无正数校验 [backend/src/muse/core/settings.py:37-38] — access/refresh TTL 为裸 int，配 0 或负值会签发即过期 token。**已修复**：改 `Field(default=..., gt=0)`，补 test_non_positive_token_ttl_rejected。（LOW）

### Defer（超出 V1 验收范围 / 需跨 story 基础设施 / 已有兜底，已记入 deferred-work.md）

- [x] [Review][Defer] refresh 轮转并发下可「一换二」（revoke 未校验 rowcount）[backend/src/muse/repositories/session_repo.py:77] — deferred：spec 陷阱④明确 V1 仅需「旧作废+发新」，顺序重放已被 test_refresh_rotation_invalidates_old 覆盖；「检测重放即作废全部 session」为开放注册前增强。
- [x] [Review][Defer] refresh_session 表无界增长、无清理任务 [backend/src/muse/models/account.py] — deferred：需 cron/清理基础设施，跨 story，V1 内测期不紧迫。
- [x] [Review][Defer] 全局 async Redis 客户端从不关闭、绑定首个事件循环 [backend/src/muse/services/rate_limit.py:29-34] — deferred：生产 uvicorn 单事件循环不触发，测试已用 module-scoped client 规避；lifespan 管理属基础设施完善。
- [x] [Review][Defer] refresh 签发新 access 不校验用户是否仍存在 [backend/src/muse/services/auth_service.py:208] — deferred：V1 无用户停用/注销功能，且 get_current_user 已对不存在用户 401 兜底。
- [x] [Review][Defer] 登录限流仅邮箱维度、无 IP，存在账号锁定型 DoS + 无撞库防护 [backend/src/muse/services/rate_limit.py:37] — deferred：AC4 明确按归一化邮箱限流；IP 维度 + 撞库防护与邮箱枚举同属「开放注册前」加固。
- [x] [Review][Defer] /refresh 与 /logout 无接口级限流 [backend/src/muse/routers/auth.py] — deferred：内测期，端点无 argon2 开销（SHA-256 快）；接口限流随开放注册前加固统一处理。

### Dismissed（噪声 / 有意设计 / 误报，未写入行动项）

- token_expired 与 token_invalid 均返回 `detail.expired=true`（deps.py:29）——有意契约：原型仅 expired/invalid/locked 三态，鉴权失败统一走 expired 跳转，`code` 字段已区分二者。
- is_locked 早于 argon2 短路引入「被锁账号」时序侧信道——与陷阱⑥有意设计冲突；locked 态（429）本就明示该账号被锁，无额外信息泄露。
- conftest make_user 用自建 PasswordHasher——argon2 verify 从哈希串自身读参数，不依赖 hasher 配置，测试保真度不受损。
