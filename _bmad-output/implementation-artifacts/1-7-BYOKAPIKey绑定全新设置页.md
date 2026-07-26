---
baseline_commit: b2f0bd5ba7132e38fecacff0686e5e23bb270486
---

# Story 1.7: BYOK API Key 绑定（全新设置页）

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a 想用自己额度的用户，
I want 在设置页绑定我自己的 API Key，
so that 我的生成走我自己的 Key、不受托管免费额度限制。

## Acceptance Criteria

1. **Given** 我已登录、进入设置页的「绑定自有 Key」（原型 `renderByok()` 的 `byok` tab，`app.js:2101-2106`，路由 `#/settings/model-access`）
   **When** 我提交一把要绑定的 API Key（附模型提供方，原型 provider 三选：DeepSeek/Claude/自定义，`app.js:2103`）
   **Then** 后端接收后，Key 明文经**应用层 AES-GCM 加密**后存 PG（新表 `byok_key`，主密钥来自环境变量 `BYOK_MASTER_KEY`，NFR6/AR9），**明文绝不落库、绝不出现在日志**；接口返回**只含掩码**（如 `sk-…a1b2`，尾 4 位）与 provider，不回显明文

2. **Given** 我提交的 API Key 为空、纯空白、或超出长度上限
   **When** 后端校验
   **Then** 拒绝并返回 error envelope（`{code,message,detail}`，AR5），**不写入无效密钥**；provider 仅接受受支持的枚举值（`deepseek`/`claude`/`custom`），非法 provider 同样 422/400 拒绝

3. **Given** 我已绑定过一把 Key
   **When** 我再次提交新 Key（替换）或请求解绑
   **Then** 替换：旧密文被**覆盖**（同账户至多一条有效 BYOK 记录，`upsert` 语义），后续生成用新 Key；解绑：该账户 BYOK 记录被**删除**，后续生成**回落托管路径**；两种操作都真实持久化，且都只回显掩码/空态、不泄露明文

4. **Given** 我查询当前 BYOK 绑定状态（设置页加载时）
   **When** 后端返回
   **Then** 已绑定→返回 `{bound:true, provider, maskedKey}`（掩码，AC1）；未绑定→返回 `{bound:false}`（或等价空态）；**任何路径都不回显明文 Key**；且严格按 `user_id` 租户隔离——**杜绝越权读取/覆盖/删除他人 Key**（NFR3），越权目标一律等同「未绑定/404」不泄露存在性

5. **Given** 后续（Epic 2）章节生成真正调用 LLM 时
   **When** 该账户已绑定 BYOK
   **Then** 本 story **只负责安全存取 + 提供「取当前账户已解密 Key」的内部接口**（供 Provider 层消费）；**真正的「生成走用户 Key」接入在 Epic 2 的 `providers/llm.py`（AR12/AR14）落地**，本 story 不实现 LLM 调用、不接生成链路（见 Dev Notes「跨 Epic 边界」）——这是**受控留茬**，非遗漏

## Tasks / Subtasks

- [x] **Task 1：BYOK 主密钥配置 + 生产 fail-fast 护栏（AC1）**
  - [x] `core/settings.py` 新增字段 `byok_master_key: str`（默认占位值 `_DEFAULT_BYOK_MASTER_KEY = "dev-only-byok-key-change-me"`，仿 `jwt_secret` 模式）。AES-GCM-256 需 32 字节密钥——约定 `BYOK_MASTER_KEY` 存 **base64 编码的 32 字节随机串**（`base64.urlsafe_b64encode(os.urandom(32))`），加载时解码校验长度
  - [x] 扩展现有 `_fail_fast_on_weak_secret` 校验器（或并列新增一个 `model_validator`）：`debug=False`（生产）时，若 `byok_master_key` 仍为默认占位值 **或** base64 解码后不足 32 字节，**拒绝启动**（与 JWT 弱密钥 fail-fast 完全同构，`settings.py:43-58`）。`debug=True` 放行开箱即用
  - [x] `.env.example` 增补 `BYOK_MASTER_KEY=dev-only-byok-key-change-me`（附注释：生产务必换 `python -c "import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"` 生成的强随机值，否则 fail-fast）
  - [x] **不改** `db_echo` 默认值，但在 Dev Notes 提醒：`byok_key` 表存密文，SQL echo 打开会打印密文绑定参数——已由现有 `db_echo` 默认 `false` 覆盖（deferred-work.md L6 关切在此闭合，无需额外动作，仅确认默认关）

- [x] **Task 2：AES-GCM 加解密函数落 `core/security.py`（AC1/AC3）**
  - [x] 在 `core/security.py` 实现两个函数（该文件模块 docstring `security.py:6` 已预留「AES-GCM BYOK 加解密：Story 1.7」占位，就落这里，勿另起文件）：
    - `encrypt_api_key(plaintext: str) -> str`：`AESGCM(key).encrypt(nonce, plaintext.encode(), None)`，`nonce = os.urandom(12)`（96-bit，GCM 标准）；**每次加密新随机 nonce**（绝不复用）；返回 **`base64(nonce || ciphertext_with_tag)`** 单串（nonce 前置拼接密文，解密时切片取回），便于单列存储
    - `decrypt_api_key(token: str) -> str`：逆操作，base64 解码 → 切出前 12 字节 nonce + 余下密文 → `AESGCM(key).decrypt(nonce, ct, None)` → `.decode()`；解密失败（`InvalidTag`/篡改/密钥变更）抛语义化异常（新增 `class KeyDecryptError` 或复用既有异常风格），**不 silently 返回空**
  - [x] 密钥来源：模块内 `_load_master_key() -> bytes`，从 `get_settings().byok_master_key` base64 解码得 32 字节；可做模块级惰性缓存（仿 `DUMMY_PASSWORD_HASH` 的 import 时一次性开销风格），但注意 `get_settings()` 是 `lru_cache`，直接调用即可
  - [x] **依赖零新增**：`cryptography`（已随 `pyjwt[crypto]` 传递安装，本机实测 `cryptography 49.0.0`、`AESGCM` 往返通过）。`from cryptography.hazmat.primitives.ciphers.aead import AESGCM`

- [x] **Task 3：`byok_key` ORM 模型 + Alembic 迁移（AC1/AC4）**
  - [x] `models/account.py` 新增 `class ByokKey(Base, UUIDPKMixin, TimestampMixin)`（放账户域本文件，复用 env.py 既有 `from muse.models import account`，免踩空迁移陷阱 deferred-work.md L10；勿新建 `models/byok.py`）。字段：
    - `user_id: Mapped[uuid.UUID]`，`ForeignKey("user.id")`，`nullable=False`，`unique=True`（**唯一约束 = 每账户至多一条 BYOK，支撑 AC3 upsert/替换语义**；V1 BYOK 按账户绑定不按作品——AC 主体是账户级，"作品级隔离"在 epics 是可选粒度，V1 定账户级最简，Dev Notes 说明）
    - `provider: Mapped[str]`，`String(16)`，`nullable=False`（存英文枚举 `deepseek`/`claude`/`custom`，与 mode/phase 存英文枚举一脉相承）
    - `encrypted_key: Mapped[str]`，`String`/`Text`，`nullable=False`（存 Task 2 的 base64(nonce‖ciphertext) 密文单串；长度不封顶用 `Text`，API Key 长度不定）
    - `key_suffix: Mapped[str]`，`String(8)`，`nullable=False`（存明文尾 4 位供掩码回显——**掩码所需的尾 4 位单独明文存**，避免每次查询都解密整串只为取尾 4 位；只存尾 4 位不足以泄露密钥）
  - [x] `alembic revision --autogenerate -m "create byok_key"` 生成迁移；**down_revision 必须指向当前 head `b56755f75420`**（create_project）。生成后**人工核对**：`user_id` 有 FK 到 `user.id` + unique 约束、`ix_byok_key_user_id` 索引（unique）、字段类型与 nullable 正确（autogenerate 有时漏 unique，参照 `b56755f75420` 迁移文件风格手工补齐）
  - [x] `migrations/env.py` 已 `from muse.models import account`——`ByokKey` 在 account.py 内**自动注册 metadata，无需改 env.py**（这正是放 account.py 的理由）。若 dev 误把模型放新文件，务必回 env.py 补 import（陷阱，见 deferred-work.md L10）

- [x] **Task 4：`byok_key` DAO（`repositories/account_repo.py` 扩展，AC1/AC3/AC4）**
  - [x] 在 `repositories/account_repo.py` 扩展（BYOK 属账户域，复用现有 repo，勿新建）。所有查询**显式绑定 user_id 租户守卫**（NFR3，参照 `project_repo.get_owned_project` 的 id+user_id 同 where 一次过滤范式）：
    - `get_byok_by_user(session, user_id) -> ByokKey | None`：按 user_id 查本人 BYOK（唯一约束下至多一条）
    - `upsert_byok(session, user_id, provider, encrypted_key, key_suffix) -> ByokKey`：存在则更新（覆盖 provider/encrypted_key/key_suffix + `updated_at=func.now()`）、不存在则 insert；**替换语义**（AC3）。可用「先 get 再改/建」或 PG `ON CONFLICT`——V1 用先 get 再分支最直白（并发替换极低概率，与既有 rename/delete 的 check-then-act 同风险级，deferred 到「开放注册/多端并发前」加固，不在本 story 处理）
    - `delete_byok(session, user_id) -> int`：条件删除本人 BYOK，返回 rowcount（解绑，AC3）；只 delete 不 commit（repo 只 flush，事务边界归 service）
  - [x] repo 只 `flush`/`delete`，**不 commit**——事务边界在 service（延续 `account_repo`/`project_repo` 铁律）

- [x] **Task 5：`byok_service` 业务编排（新建 `services/byok_service.py`，AC1-AC4）**
  - [x] 新建 `services/byok_service.py`（BYOK 编排独立成 service，与 `usage_service`（1.8 建）并列属账户域；不塞进 `auth_service`）：
    - `bind_or_replace_key(session, user_id, provider, plaintext_key) -> ByokKey`：**先校验**（`_validate_key` + provider 枚举）→ `encrypt_api_key(plaintext)` → 算 `key_suffix = plaintext[-4:]` → `upsert_byok` → `commit` → 返回（供 router 转掩码响应）。校验失败抛 `ErrorEnvelope`（400/422 语义）
    - `get_binding_status(session, user_id) -> dict | schema`：`get_byok_by_user` → 有则组 `{bound:True, provider, masked_key}`（掩码 = `"sk-…" + key_suffix` 或更通用 `"…"+suffix`，不依赖前缀假设）、无则 `{bound:False}`（AC4）
    - `unbind_key(session, user_id) -> None`：`delete_byok` → `commit`（AC3 解绑）；删 0 行也幂等成功（未绑定时解绑不报错，或按团队偏好 404——**推荐幂等 204**，解绑是"确保没有绑定"的意图）
    - `get_decrypted_key_for_user(session, user_id) -> str | None`：**供 Epic 2 Provider 层消费的内部接口**（AC5）——`get_byok_by_user` → 有则 `decrypt_api_key(encrypted_key)` 返回明文、无则 `None`。**本 story 只提供此函数，不接生成链路**；明文只在内存中传给 Provider，绝不写日志/不落库/不出 API 边界
  - [x] `_validate_key(plaintext: str)`：去首尾空白后非空、长度 ≤ 上限（如 512，防超大输入，参照 project title `max_length` 风格）；空/纯空白/超长抛 `ErrorEnvelope("byok_invalid_key", ...)`（AC2）。**不校验 Key 是否真实有效**（不发测试请求验活——那属 Provider 层，且会引入外部调用与延迟；V1 只做格式校验，Dev Notes 说明）
  - [x] 事务边界在 service（`commit`/`rollback`），业务错误抛 `ErrorEnvelope` 交全局 handler（延续 `project_service` 范式）

- [x] **Task 6：BYOK API schema（`schemas/account.py` 扩展，AC1/AC4，AR4 camelCase 边界）**
  - [x] `schemas/account.py` 扩展（继承 `CamelModel`，边界自动 snake↔camel）：
    - `ByokBindRequest(CamelModel)`：`api_key: str`（边界收 `apiKey`）+ `provider: Literal["deepseek","claude","custom"]`（边界枚举校验，非法 provider 直接 422，AC2）。**空 Key 校验的明确分工**（与 project title「留空是合法业务回落」不同——此处空 Key 是**非法**，AC2 要求拒绝）：`api_key` **设 `min_length=1`**（明显空串 `""` 走 422 validation_error）；**纯空白**（如 `"   "`）无法被 min_length 拦、须由 `byok_service._validate_key` strip 后判空抛 `ErrorEnvelope("byok_invalid_key")`（400）。两条路径都保证「空/纯空白被拒、不写库」，dev 两条都要实现（不是二选一）
    - `ByokStatusResponse(CamelModel)`：`bound: bool`、`provider: str | None`、`masked_key: str | None`（边界 `maskedKey`）——未绑定时后两者为 `null`（AC4）
    - **绝不定义**任何回显明文 Key 的 response 字段（安全红线，AC1/AC4）
  - [x] 掩码串生成放 service（或 schema 计算），格式 `…` + 尾 4 位（如 `…a1b2`）；不硬编码 `sk-` 前缀（Claude/自定义 provider 前缀不同）

- [x] **Task 7：BYOK router（新建 `routers/byok.py` + main 注册，AC1-AC4）**
  - [x] 新建 `routers/byok.py`（`prefix="/api/byok"`, `tags=["byok"]`），仅校验入参 + 调 `byok_service`（AR2 router 不写业务）；全部依赖 `CurrentUser`（鉴权入口，未登录 401，参照 `routers/projects.py`）：
    - `PUT /api/byok`（`ByokBindRequest` → `ByokStatusResponse`）：绑定/替换（**PUT = 幂等 upsert 语义**，天然覆盖 AC1 绑定 + AC3 替换；用 PUT 而非 POST 因同账户至多一条、重复提交结果一致）
    - `GET /api/byok`（→ `ByokStatusResponse`）：查询绑定状态（AC4）
    - `DELETE /api/byok`（→ 204 No Content，无响应体，参照 `delete_project`）：解绑（AC3）
  - [x] `main.py` `create_app()` 内 `app.include_router(byok.router)`（与 auth/health/projects 并列，`main.py:11,27`）
  - [x] 路由用 `/api/byok`（账户级单例资源，无 `{id}`）——BYOK 按账户绑定，当前用户即资源主体，`CurrentUser.id` 定位，**路径不带 project_id/key_id**（避免 IDOR 面，也契合账户级唯一约束）

- [x] **Task 8：测试（`tests/test_byok.py` 新建，全 AC 覆盖）**
  - [x] **离线用例（不需 DB）**：
    - 加解密单元测试：`encrypt_api_key`/`decrypt_api_key` 往返（`decrypt(encrypt(x))==x`）；同一明文两次加密**密文不同**（随机 nonce 验证）；篡改密文 → `decrypt` 抛异常
    - 鉴权前置：无 token `PUT/GET/DELETE /api/byok` → 401 `token_invalid`；过期 token → 401 `token_expired`（参照 `test_projects.py:40-70`）
  - [x] **DB 端到端用例（`@requires_db`，参照 `test_projects.py` 结构 + conftest fixture `make_user`/`auth_headers`）**：
    - AC1 绑定落库 + 只回掩码：`PUT` 合法 Key → 200，响应含 `bound:true`/`provider`/`maskedKey`（尾 4 位），**响应体不含明文**；直查 DB `byok_key.encrypted_key != 明文` 且 `decrypt` 回得明文（验证真加密非明存）
    - AC2 校验：空 Key / 纯空白 Key → error envelope 拒绝、库中无记录；非法 provider → 422
    - AC3 替换：绑定 A → 再 `PUT` 绑定 B → `GET` 掩码为 B 的尾 4 位、DB 仅一条记录（唯一约束）；解绑：`DELETE` → 204 → `GET` 返 `bound:false`、DB 无记录
    - AC4 查询 + 租户隔离：未绑定 `GET` → `bound:false`；**A 绑定后 B `GET` 只见自己（bound:false）**、B `DELETE` 删不到 A 的（A 记录分毫未动，参照 `test_projects.py` 租户隔离用例）
    - AC5 内部接口：`get_decrypted_key_for_user` 绑定后返明文、未绑定返 `None`（单元级，验证供 Epic 2 消费的契约）
  - [x] **conftest 增量**：`tests/conftest.py` 的 `_clean_tables` TRUNCATE 列表需加 `byok_key`（`byok_key` 有 user_id FK 指向 user，CASCADE 一并清；参照 `conftest.py:63` 现有 `TRUNCATE "user", invite_code, refresh_session, project`）；`conftest.py:26-29` 的 `from muse.models import (account, project)` 无需改（ByokKey 在 account.py 内，account import 已覆盖）。**注入测试用 `BYOK_MASTER_KEY`**：conftest 顶部 `os.environ.setdefault("BYOK_MASTER_KEY", <base64 32字节固定测试值>)`（参照 `conftest.py:13-14` 注入 JWT_SECRET/DEBUG 的模式，保证测试不依赖本机 .env、不触发 fail-fast）

- [x] **Task 9：质量门禁 + 验证（done 前必过）**
  - [x] `uv run ruff check .` + `uv run mypy` 通过（新增文件全部纳入，`byok_service.py`/`routers/byok.py` 类型标注完整）
  - [x] `MUSE_DB_READY=1 uv run pytest tests/test_byok.py -v`（需先 `docker compose up -d` 起 PG+Redis 容器）全绿；离线用例（加解密单元 + 401）不设 DB 也应过
  - [x] `uv run alembic upgrade head` 迁移可正跑、`alembic downgrade -1` 可回滚（byok_key 迁移的 upgrade/downgrade 双向验证）
  - [x] **`prototype/app/app.js` 一字节不改**（`git status prototype/` 应为空）——本 story 零前端增量（范围见 Dev Notes「前端不接线」）；`grep -c "fetch(" prototype/app/app.js` 仍为 0
  - [x] 全链路人工核对：`git diff` 确认无明文 Key 写入日志/无回显；`encrypted_key` 列确为密文

## Dev Notes

### 🔑 本 story 的性质：后端主体 story（建表 + 加密 + API），`app.js` 零改动
1.7 与 1.6（纯前端路由 story）**相反**：它的 AC 主体是后端安全存取（AES-GCM 加密、byok_key 表、绑定/解绑/查询 API、校验），与 1.1-1.5 后端 story 同类。**唯一涉及前端的 AC1「设置页 + 绑定区」，原型 `renderByok()`（`app.js:2079-2139`）已完整实现**（含密钥输入框、DeepSeek/Claude/自定义 provider 三选、保存按钮、hosted/byok tab 切换）——设置页 UI 本身不需要本 story 新建。

**范围边界（本 story 做 / 不做）**：
| 做 | 不做（越界 / 属别的 story） |
|---|---|
| `byok_key` 表 + ORM + 迁移（Task 3） | 接前端 `renderByok` 到真实 API（前端 API 接线契约，见下「前端不接线」） |
| AES-GCM 加解密函数（Task 2） | 作品库 header 加「设置页入口链接」（前端改动，同属接线契约推后） |
| BYOK 主密钥配置 + fail-fast（Task 1） | LLM 调用 / 生成走用户 Key 的**真正接入**（Epic 2 `providers/llm.py`，AR12/AR14，见「跨 Epic 边界」） |
| 绑定/替换/解绑/查询 API + 校验（Task 4-7） | 托管免费额度护栏 / usage_ledger / 用量展示（**Story 1.8**，别抢做） |
| 「取当前账户已解密 Key」内部接口（AC5，供 E2 消费） | Key 有效性验活（发测试请求验 Key 真能用——属 Provider 层，V1 只格式校验） |
| 测试全 AC（Task 8） | 作品级（非账户级）Key 隔离粒度（V1 定账户级，见「绑定粒度」） |

### 🔑 为何前端不接线（本 story 的关键范围判断，已与用户对齐授权按最佳方案执行）
- **前端全站零 API 接线**：原型 `app.js`（5800+ 行）**至今无一处 `fetch`**、无 token 携带、无 `localStorage` 存业务数据（只用 `sessionStorage` 存 UI 态，如 `muse-exploration-mode`）。1.1-1.5 后端 story 均明确「不做前端接线」，1.6 dev notes 更把「前端 API 接线」论证为**独立关注点**（拖入即 scope 爆炸：token 携带 + 鉴权失败跳转 + error envelope 前端分支 + 掩码渲染 + 解绑交互 + 设置页入口）。
- **1.7 若接前端 = 全项目第一次引入 fetch/token 横切基础设施**，属独立前端接线 story 的职责，不该塞进 BYOK 后端 story。**后端把 API 契约做实、做对、测透**，前端 `renderByok` 的保存/解绑接线与「作品库→设置页入口链接」留给后续统一的前端接线切片（届时 `PUT/GET/DELETE /api/byok` 已就绪、可零改动对接）。
- **AC1 的「从账户入口进入设置页」如何验收**：路由 `#/settings/model-access` 与 `renderByok()` 已存在，dev/评审在浏览器手动访问该 hash 即可验证设置页与绑定区渲染正常；「作品库 header 加入口链接」是前端接线项，本 story 不做（原型 `app.js:405` header 目前仅邮箱 + 退出，无设置入口——这是**已知前端缺口，记入下方 deferred**）。

### 🔑 跨 Epic 边界：AC5「生成走用户 Key」的真正消费在 Epic 2（受控留茬，非遗漏）
- **架构事实**：LLM 调用一律走 `providers/llm.py` 的 `LLMProvider` 抽象（AR12、architecture.md#焦点一、#Process-Patterns「业务层禁止直接 import openai SDK」）。该文件 **Epic 2 Story 2.1 才建**（`providers/` 目录当前只有空 `__init__.py`）。用量计量埋点（AR14）同属 Provider 层、Epic 2 落地。
- **本 story 的边界**：只交付 `byok_service.get_decrypted_key_for_user(session, user_id)` 这一**内部接口**（AC5），把「安全取回某账户明文 Key」的能力备好。**不实现任何 LLM 调用、不接生成链路、不碰 Provider**。Epic 2 建 Provider 时调用此接口决定「走用户 Key 还是托管 Key」。
- **sprint-status.yaml 已登记此衔接**（文件头 MUSE SEQUENCING NOTES：「1-8 额度护栏『真正生效』依赖 Epic 2 Provider 层埋点」）；BYOK 消费同理。**必须在 Completion Notes 显式记录此留茬**，供 Epic 2 dev 无缝接管，勿让它变成隐性空窗。

### 关键实现陷阱（务必规避）
- **陷阱①：明文 Key 绝不落库、绝不进日志、绝不出 API 边界。** 这是本 story 的**安全红线**。① 存库只存 `encrypt_api_key()` 密文；② 响应/schema 只有 `maskedKey`，**不存在**任何回显明文的字段；③ `db_echo` 默认 `false` 已防 SQL 参数打印密文（deferred-work.md L6 在此闭合，勿顺手开 echo）；④ `get_decrypted_key_for_user` 返回的明文只在内存传给（未来的）Provider，**不 log、不落库**；⑤ error envelope 的 `detail` 不回填用户提交的 Key（`errors.py:60-61` 已对 422 剔除 `input`，但业务 error 的 detail 由你构造，勿把 Key 塞进去）。
- **陷阱②：AES-GCM nonce 每次加密必须全新随机，绝不复用。** GCM 下同密钥 + 同 nonce 加密两条消息会**灾难性泄露密钥流**。`encrypt_api_key` 内 `os.urandom(12)` 每次现取，nonce 前置拼进密文串一起存（`base64(nonce‖ct)`），解密时切片取回。**不要**把 nonce 设成固定常量或存在配置里。
- **陷阱③：主密钥长度/编码校验 + 生产 fail-fast。** AES-256-GCM 密钥**必须恰好 32 字节**。约定 `BYOK_MASTER_KEY` 存 base64(32 字节)，加载时解码并断言长度=32，不足即启动失败。生产（`debug=False`）若仍为默认占位值 → 拒启动（仿 `settings.py:43-58` JWT 弱密钥 fail-fast，同构实现，别另发明模式）。
- **陷阱④：byok_key 唯一约束 = 每账户至多一条，支撑替换语义。** `user_id` 列加 `unique=True`。绑定即 upsert（存在覆盖、不存在插入），`PUT` 幂等。**别**建成一对多（会出现"一个账户多把 Key 该用哪把"的歧义，V1 无此需求，YAGNI）。autogenerate 可能漏 unique 约束，**人工核对迁移文件**补齐（参照 `b56755f75420` 手工调整惯例）。
- **陷阱⑤：租户守卫贯穿所有 BYOK 查询（NFR3）。** `get_byok_by_user`/`upsert_byok`/`delete_byok` 全部 `where(user_id == current)`。越权读/改/删他人 Key 一律等同「未绑定/删 0 行」，**不返回 403、不泄露他人是否绑定**（参照 `project_repo.get_owned_project` 的 IDOR 消除范式）。router 用 `CurrentUser.id`，路径**不带** key_id/project_id。
- **陷阱⑥：解密失败要抛语义化异常，不 silently 吞。** 主密钥轮转 / 密文损坏 / 篡改会让 `AESGCM.decrypt` 抛 `InvalidTag`。`decrypt_api_key` 捕获后抛明确异常（`KeyDecryptError`），上层据此走 500 或「视同未绑定回落托管」——**别 `except: return ""`**（空串会被误当合法 Key 用）。V1 至少保证不逃逸成裸 500 且日志可诊断（不打印密文/明文）。
- **陷阱⑦：掩码不硬编码 `sk-` 前缀。** DeepSeek Key 形如 `sk-…`，但 Claude/自定义 provider 前缀不同。掩码用中性格式 `…` + 尾 4 位（`key_suffix`），别拼 `"sk-" + suffix`（对 Claude Key 会显示错误前缀）。

### 强制复用 / 对齐的既有事实（照现状，勿另起炉灶）
- **security.py 已预留落点**：`core/security.py:6` 模块 docstring 明写「AES-GCM BYOK 加解密：Story 1.7」——加解密函数就落该文件，与 `hash_password`/`create_access_token` 并列，勿新建 `crypto.py`。
- **settings fail-fast 现成模板**：`settings.py:43-58` `_fail_fast_on_weak_secret`（`model_validator(mode="after")`）是 BYOK 主密钥 fail-fast 的**逐行模板**——扩展它或并列加一个同构 validator。
- **CamelModel 边界基类**：`schemas/base.py` 的 `CamelModel`（`alias_generator=to_camel`）——所有 BYOK schema 继承它，`apiKey`/`maskedKey` 自动转换，勿手写别名。
- **ErrorEnvelope 业务错误**：`core/errors.py` 的 `ErrorEnvelope(code, message, detail, http_status)`——校验失败抛它（`byok_service`），全局 handler 自动转 `{code,message,detail}`（参照 `project_service._project_not_found`）。
- **CurrentUser 鉴权依赖**：`core/deps.py` 的 `CurrentUser` 别名——router 参数标注即自动完成 access token 校验 + 取 User，未登录/失效自动 401（参照 `routers/projects.py` 全部端点）。
- **repo 只 flush、service 管事务**：`account_repo`/`project_repo` 铁律——BYOK repo 只 flush/delete，`commit`/`rollback` 在 `byok_service`。
- **迁移链 head**：当前 head = `b56755f75420`（create_project）。byok_key 迁移 `down_revision` 指向它。`env.py` 已 import account 模块（ByokKey 放 account.py 即自动注册，免空迁移陷阱 deferred-work.md L10）。
- **conftest 注入模式**：`tests/conftest.py:13-14` 用 `os.environ.setdefault` 注入 `JWT_SECRET`/`DEBUG`——BYOK 测试同法注入 `BYOK_MASTER_KEY`；`_clean_tables` TRUNCATE 列表（`conftest.py:63`）加 `byok_key`。

### 原型交互契约（页面即契约；本 story **不改** `app.js`，仅记录设置页现状供后续接线）
> 本 story 前端零改动。以下为设置页现状（后续前端接线 story 的对接点，非本 story 任务）：
- `app.js:2079-2110` — `renderByok()` 设置页：`byok` tab 有 `#byok-key`（type=password）输入、provider 三选按钮（`.byok-provider-option`，DeepSeek/Claude/自定义）、`[data-byok-save]` 保存按钮（当前只改 DOM 文案 `app.js:2133-2138`，未落库）；`hosted` tab 展示托管额度（占位值，属 Story 1.8）。
- `app.js:2326` — 路由 `#/settings/model-access` → `renderByok()`（已存在，手动访问可达）。
- `app.js:154-155` — 会话态 `byokTab`/`byokKeyDraft`（前端 UI 态，接线时改为读 `GET /api/byok`）。
- **已知前端缺口（记入 deferred）**：作品库 header（`app.js:405`）仅「邮箱 + 退出」，**无进入设置页的导航链接**——用户当前只能手敲 hash 到设置页。补入口链接属前端接线 story。

### Project Structure Notes
- **新增文件**：`services/byok_service.py`、`routers/byok.py`、`tests/test_byok.py`、`migrations/versions/<hash>_create_byok_key.py`（autogenerate）。
- **扩展文件**：`core/settings.py`（+byok_master_key +fail-fast）、`core/security.py`（+encrypt/decrypt_api_key）、`models/account.py`（+ByokKey）、`repositories/account_repo.py`（+3 个 byok DAO）、`schemas/account.py`（+ByokBindRequest/ByokStatusResponse）、`main.py`（+include_router）、`.env.example`（+BYOK_MASTER_KEY）、`tests/conftest.py`（+TRUNCATE byok_key +注入 BYOK_MASTER_KEY）。
- **依赖零新增**：`cryptography` 已随 `pyjwt[crypto]` 传递安装（实测 49.0.0）。
- **无偏差**：严格遵循 architecture.md 分层（routers→services→repositories→models→schemas）、camelCase 边界、租户守卫、error envelope 约定；BYOK 放账户域 `models/account.py`/`account_repo.py`（AR9「account 表：user/project/byok_key/usage_ledger」明示 byok_key 属账户域）。

### 绑定粒度决策（V1 账户级）
epics/NFR 有「BYOK 密钥按账户/作品隔离」表述（NFR3/FR4）。**V1 定账户级**（`byok_key.user_id` 唯一）：AC 主体是账户级绑定（「我的生成走我自己的 Key」），作品级粒度会引入「每作品可绑不同 Key」的复杂度，V1 无此明确需求（YAGNI）。若未来需作品级，加 `project_id` 列 + 复合唯一约束即可平滑升级，本 story 的账户级是其子集、不阻塞。**Dev 按账户级实现**，勿自作主张做作品级。

### 测试形态
- 后端 pytest + pytest-asyncio（`asyncio_mode=auto`），DB 用例 `@requires_db` 门禁（需 `MUSE_DB_READY=1` + 容器，memory「DB 测试需 MUSE_DB_READY=1」）。
- 加解密函数是**纯离线单元测试**（不需 DB），务必覆盖：往返、随机 nonce（两次密文不同）、篡改检测。
- DB 端到端参照 `test_projects.py` 结构（离线鉴权 + `@requires_db` 业务），复用 conftest `make_user`/`auth_headers` fixture。

### 待澄清（保存至末尾，请用户确认）
- **无阻塞性疑问。** 关键范围判断（1.7 = 后端主体 story、`app.js` 零改动、前端接线与"设置页入口链接"推后、AC5 生成消费 defer 到 Epic 2、绑定粒度 V1 账户级）已在开发前定档，用户授权按最佳方案执行。
- **供用户知悉的两个受控决策**（非阻塞，dev 照此执行）：
  1. **BYOK 按账户级绑定**（非作品级）——V1 最简，未来可平滑升级到作品级。
  2. **前端 `renderByok` 保存/解绑接线 + 作品库设置页入口链接**不在本 story——留给后续统一前端接线切片；本 story done 后 `PUT/GET/DELETE /api/byok` 已就绪可零改动对接。若希望把前端接线并入或单独立 story，可在本 story done 后安排。

### References
- [Source: _bmad-output/planning-artifacts/epics.md#Story-1.7（L397-423）] — 用户故事、5 条 AC（设置页绑定、AES-GCM 加密存储只回掩码、走用户 Key、解绑/替换、非法 Key 拒绝）。
- [Source: _bmad-output/planning-artifacts/epics.md#Epic-1-Story依赖（L242-243）] — `1.3 →1.7`、`1.7 →1.8`；「1.7 建 `byok_key` 表」。
- [Source: _bmad-output/planning-artifacts/epics.md#Story-1.8（L425-448）] — 1.8 用量护栏依赖 1.7 BYOK；「BYOK 用户不占托管免费额度」（本 story 只需备好 `get_decrypted_key_for_user`，用量归账属 1.8/E2）。
- [Source: _bmad-output/planning-artifacts/architecture.md#Authentication-Security（L164-170）] — 「BYOK 密钥存储：应用层 AES-GCM 加密后存 PG，主密钥放环境变量/云 KMS，随账户或作品绑定」。
- [Source: _bmad-output/planning-artifacts/architecture.md#焦点一（L194-201）] — LLMProvider 抽象 + 用量计量在 Provider 层（Epic 2）；BYOK 消费的接入点（AC5 defer 依据）。
- [Source: _bmad-output/planning-artifacts/architecture.md#Process-Patterns（L340-343）] — 「一律走 LLMProvider 接口，业务层禁止直接 import openai SDK」（本 story 不碰 Provider 的架构依据）。
- [Source: _bmad-output/planning-artifacts/architecture.md#Data-Boundaries（L448-451）] — 「BYOK 密钥 AES-GCM 加密后落 PG」；所有业务查询带 user_id 租户隔离。
- [Source: _bmad-output/planning-artifacts/architecture.md#项目结构（L389,393,416）] — `core/security.py`「JWT + AES-GCM BYOK 加解密」、`models/account.py`「user、project、byok_key、usage_ledger」、`providers/llm.py`（Epic 2）。
- [Source: backend/src/muse/core/security.py（L1-7）] — 模块 docstring 已预留「AES-GCM BYOK 加解密：Story 1.7」落点。
- [Source: backend/src/muse/core/settings.py（L11-14,43-58）] — `_DEFAULT_JWT_SECRET`/`_MIN_JWT_SECRET_LENGTH` + `_fail_fast_on_weak_secret`（BYOK 主密钥 fail-fast 的同构模板）。
- [Source: backend/src/muse/models/account.py（L1-6,46-62）] — 账户域模型文件（ByokKey 落此）；RefreshSession「放账户域复用 env.py import 免空迁移陷阱」的先例。
- [Source: backend/src/muse/models/base.py（L15-36）] — `Base`/`UUIDPKMixin`/`TimestampMixin`（ByokKey 继承）。
- [Source: backend/src/muse/repositories/project_repo.py（L44-58）] — `get_owned_project` 的 id+user_id 同 where 一次过滤（IDOR 消除范式，BYOK 租户守卫照此）。
- [Source: backend/src/muse/repositories/account_repo.py（L26-31,39-56）] — repo 只 flush、create_user/条件 UPDATE 范式（BYOK DAO 扩展此文件）。
- [Source: backend/src/muse/services/project_service.py（L30-52,60-87）] — service 管事务 + `ErrorEnvelope` 抛业务错误 + refresh 拉回时间戳（byok_service 照此）。
- [Source: backend/src/muse/routers/projects.py（L23-67）] — router 仅校验分发 + `CurrentUser` 鉴权 + 204 无体删除（routers/byok.py 照此）。
- [Source: backend/src/muse/schemas/base.py（L29-34）] + [schemas/project.py（L19-53）] — `CamelModel` 边界 + Literal 枚举 + Field max_length（BYOK schema 照此）。
- [Source: backend/src/muse/core/deps.py（L38-56）] — `get_current_user`/`CurrentUser`（BYOK router 鉴权依赖）。
- [Source: backend/src/muse/core/errors.py（L17-37,55-66）] — `ErrorEnvelope` + 422 剔除 input（陷阱①安全依据）。
- [Source: backend/src/muse/main.py（L11,21-28）] — router 注册点（+byok.router）。
- [Source: backend/migrations/env.py（L11-16）] — 「每建一张业务表就在此登记模块」；account 已 import（ByokKey 放 account.py 免改 env.py）。
- [Source: backend/migrations/versions/b56755f75420_create_project.py] — 迁移文件风格 + 当前 head（byok_key down_revision 指向它）+ 索引/FK 手工核对范例。
- [Source: backend/tests/test_projects.py（L40-70,169-199,296-339）] — 离线鉴权 401 + `@requires_db` 业务 + 租户隔离用例结构（test_byok.py 照此）。
- [Source: backend/tests/conftest.py（L13-14,53-72,109-144）] — 注入 JWT_SECRET/DEBUG 模式（+BYOK_MASTER_KEY）、`_clean_tables`（+byok_key）、`make_user`/`auth_headers` fixture。
- [Source: backend/pyproject.toml（L6-18）] — 依赖清单（`pyjwt[crypto]` 传递 cryptography，零新增）。
- [Source: prototype/app/app.js（L2079-2139,2326,154-155,405）] — `renderByok()` 设置页现状（本 story 不改，供后续接线）；作品库 header 无设置入口（已知前端缺口）。
- [Source: _bmad-output/implementation-artifacts/1-6-继续创作-按phase跳转当前步骤.md#为何不接 API] — 前端 API 接线是独立关注点、拖入即 scope 爆炸的先例论证（1.7 前端不接线的方法论依据）。
- [Source: _bmad-output/implementation-artifacts/deferred-work.md（L6,L10）] — SQL echo 解耦敏感表（byok_key 存密文，db_echo 默认 false 闭合）；env.py 漏 import 空迁移陷阱（ByokKey 放 account.py 规避）。
- [Source: _bmad-output/implementation-artifacts/sprint-status.yaml（MUSE SEQUENCING NOTES）] — 跨 epic 受控依赖：BYOK 消费/额度真正生效依赖 Epic 2 Provider 层，须追踪衔接不留空窗（AC5 defer 的登记依据）。

## Dev Agent Record

### Agent Model Used

Claude Opus 4.8 (claude-opus-4-8)

### Debug Log References

- Colima 启动 + `docker compose up -d` 起 PG(pgvector:pg16)+Redis 容器；`MUSE_DB_READY=1` 跑 DB 用例。
- Settings BYOK fail-fast 四分支验证：debug 放行占位值 / prod 占位值拒启 / prod 合法 32 字节放行 / prod 16 字节拒启——全过。
- AES-GCM 加解密预验证：往返 / 随机 nonce（两次密文不同）/ 篡改检测 / 残缺密文 / 非法 base64——全抛 KeyDecryptError 或正确往返。
- Alembic 迁移双向验证：`upgrade head` → `\d byok_key` 确认 `ix_byok_key_user_id UNIQUE` + FK；`downgrade -1` 表删除 → 升回 head。

### Completion Notes List

- **全 5 条 AC 交付并测通**：AES-GCM-256 加密存取（AC1）、空/纯空白/非法 provider/超长校验拒绝且不写库（AC2）、PUT 幂等替换 + DELETE 幂等解绑（AC3）、GET 绑定状态查询 + 严格 user_id 租户隔离（AC4）、`get_decrypted_key_for_user` 内部接口（AC5）。
- **测试结果**：`tests/test_byok.py` 20 个用例全过（8 离线：加解密单元 4 + 鉴权 401/expired 4；12 DB 端到端）；全量回归 93 passed 无回归。ruff + mypy（40 源文件）全绿。
- **安全红线守住（陷阱①）**：明文 Key 只在内存流转——存库仅 `encrypt_api_key()` 密文 + 尾 4 位明文（掩码用）；响应 schema 仅 `bound/provider/maskedKey`，无任何回显明文字段；无 log/print 明文语句；`db_echo` 默认 false 未改。掩码用中性 `…`+尾 4 位，不硬编码 `sk-` 前缀（陷阱⑦）。
- **AES-GCM 实现要点**：每次加密全新随机 nonce（陷阱②），`base64(nonce‖ciphertext_with_tag)` 单串存单列；解密失败（InvalidTag/篡改/残缺/非法 base64）一律抛 `KeyDecryptError` 语义化异常，绝不 silently 返回空串（陷阱⑥）。`_load_master_key` 对 dev 占位值做 SHA-256 确定性派生保证开箱即用往返，生产走 settings fail-fast 保证的合法 base64(32)。
- **绑定粒度 V1 账户级**：`byok_key.user_id` 唯一约束（`ix_byok_key_user_id UNIQUE`）= 每账户至多一条，支撑 upsert 替换语义（陷阱④）。未来需作品级加 `project_id` + 复合唯一即可平滑升级。
- **⚠️ 受控留茬（AC5，须 Epic 2 无缝接管）**：本 story **只交付** `byok_service.get_decrypted_key_for_user(session, user_id)` 内部接口，**不实现任何 LLM 调用、不接生成链路、不碰 Provider**。「生成走用户 Key」的真正消费在 **Epic 2 Story 2.1 建 `providers/llm.py`（LLMProvider 抽象，AR12/AR14）** 时落地——届时调用此接口决定「走用户 Key 还是托管 Key」。用量计量埋点（AR14）同属 Provider 层、Epic 2 落地。这是 sprint-status.yaml 头 MUSE SEQUENCING NOTES 已登记的跨 epic 受控依赖，非遗漏。
- **⚠️ 前端受控留茬（非本 story）**：原型 `app.js` 零改动（`git status prototype/` 空、`grep -c "fetch(" ` 仍为 0）。`renderByok()` 设置页 UI 已存在（路由 `#/settings/model-access` 手动访问可达），但**保存/解绑接线 + 作品库 header 设置页入口链接**留给后续统一前端接线切片；届时 `PUT/GET/DELETE /api/byok` 已就绪可零改动对接。作品库 header（`app.js:405`）当前无设置入口——已知前端缺口，记入 deferred。
- **迁移**：新增 `34b96a86fc00_create_byok_key`，down_revision 指向当前 head `b56755f75420`；autogenerate 本次正确生成 unique 索引（模型同时声明 unique+index），无需手工补齐。

### Change Log

- 2026-07-24：实现 Story 1.7 BYOK API Key 绑定后端主体——AES-GCM 加密存取 + `byok_key` 表 + 绑定/替换/解绑/查询 API + 内部解密接口（供 Epic 2）；`app.js` 零改动。20 个新测试用例全过，全量回归 93 passed。

### File List

**新增文件：**
- `backend/src/muse/services/byok_service.py` — BYOK 业务编排（bind/status/unbind/get_decrypted_key + 校验）
- `backend/src/muse/routers/byok.py` — BYOK 路由（PUT/GET/DELETE /api/byok）
- `backend/tests/test_byok.py` — 全 AC 测试（20 用例）
- `backend/migrations/versions/34b96a86fc00_create_byok_key.py` — byok_key 表迁移

**修改文件：**
- `backend/src/muse/core/settings.py` — +byok_master_key 字段 +BYOK 主密钥 fail-fast 校验器
- `backend/src/muse/core/security.py` — +encrypt_api_key/decrypt_api_key/KeyDecryptError/_load_master_key
- `backend/src/muse/models/account.py` — +ByokKey ORM 模型
- `backend/src/muse/repositories/account_repo.py` — +get_byok_by_user/upsert_byok/delete_byok（租户守卫）
- `backend/src/muse/schemas/account.py` — +ByokBindRequest/ByokStatusResponse
- `backend/src/muse/main.py` — +include_router(byok.router)
- `backend/.env.example` — +BYOK_MASTER_KEY
- `backend/tests/conftest.py` — +注入 BYOK_MASTER_KEY +TRUNCATE byok_key

## Review Findings

> 2026-07-24 code review（三层对抗式：Blind Hunter 纯 diff 推理 / Edge Case Hunter diff+项目 / Acceptance Auditor diff+spec）。三层高度收敛：Blind 独立复现 Edge 全部 3 条，Auditor 判 5 条 AC 全满足。共 3 条 finding：2 patch、1 defer、0 decision-needed、0 dismissed。

- [x] [Review][Patch] 短 Key（≤4 字符）导致 `key_suffix` 存全量明文、`maskedKey` 回显整串——击穿「明文绝不落库/回显」安全红线（陷阱①）[backend/src/muse/services/byok_service.py:198] — `key_suffix = normalized_key[-4:]` 对 `"abc"` 得 `"abc"`（Python 切片），schema `min_length=1` + `_validate_key` strip 后非空均放行短 Key，于是整串明文落 `key_suffix` 列且响应 `maskedKey="…abc"`。**已修复**：新增 `_mask_suffix()`，`len(key) <= _SUFFIX_LEN` 时返回等长 `*` 全打码；新增回归用例 `test_bind_short_key_masks_full_suffix_no_plaintext_leak`。
- [x] [Review][Patch] upsert 替换分支 `existing.updated_at = func.now()` 留下 SQL ClauseElement 脏内存值 [backend/src/muse/repositories/account_repo.py:302] — 与 `TimestampMixin.onupdate=func.now()` 重复设置；`expire_on_commit=False` 下 commit 后该属性停留为子句对象而非 datetime。当前 `status_payload` 不读 `updated_at` 故不显形，属潜伏坑，且偏离 `project_service.rename_project` commit 后 `await session.refresh()` 范式。**已修复**：删除 repo 侧冗余赋值（交给 onupdate），`bind_or_replace_key` commit 后 `await session.refresh(byok)` 拉回时间戳。
- [x] [Review][Defer] 并发 upsert check-then-act 双双 insert 撞 `user_id` 唯一约束 → IntegrityError 冒泡 500（而非幂等/409）[backend/src/muse/repositories/account_repo.py:297-313] — deferred，spec 授权（Task 4 + 陷阱④明确「并发替换极低概率，与既有 rename/delete check-then-act 同风险级，加固 deferred 到开放注册/多端并发前」，与 1-5 rename/delete 同类）。已记入 deferred-work.md。
