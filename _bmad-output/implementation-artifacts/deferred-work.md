# Deferred Work

## Deferred from: code review of 1-1-后端工程基座与本地开发环境 (2026-07-23)

- JWT 弱密钥默认值 `dev-only-change-me` 缺生产 fail-fast 护栏 [backend/src/muse/core/settings.py:29] — 归 Story 1.3，JWT 实际签发时一并加「debug=False 时校验密钥非默认值」的启动断言。
- `echo=settings.debug` 会把 SQL 及绑定参数打进日志 [backend/src/muse/core/db.py:20] — 存 BYOK/JWT 敏感表前（Epic 2 / Story 1.3）再把 SQL echo 与 debug 开关解耦。
- `/health` DB 探活无 statement/connect 超时，半开连接（网络分区）下可能挂死 [backend/src/muse/services/health_service.py:13] — 与 health HTTP 语义决策绑定；`pool_pre_ping=True` 已部分缓解，超时策略随语义决策一并处理。
- pgvector 版本口径漂移：README 称 0.8.x(HNSW) 但镜像仅锁 `pgvector/pgvector:pg16` tag，未锁扩展小版本 [backend/README.md:53 vs docker-compose.yml:2] — 如需严格复现应 pin 镜像 digest，超出基座 story 范围。
- 清华镜像设为 `[[tool.uv.index]] default=true` 影响境外 CI 可移植性与供应链信任面 [backend/pyproject.toml:58-60] — 用户已在 Debug Log 记录取舍（PyPI 直连 46KB/s 卡死），保留待团队/CI 环境统一时复议是否移到本地配置。
- env.py 隐性约定：后续建表须手动 `import` 模型到 `Base.metadata`，漏 import 会致 autogenerate「看不见」新表却不报错 [backend/migrations/env.py:12-13] — Story 1.2 建表时务必登记，并考虑加自动扫描或 CI 校验。
- 422 请求校验错误分支无真实测试覆盖（现有同名测试实为 404）[backend/tests/test_health.py] — Story 1.2 出现带 body 校验的业务端点后，补一个真实触发 `RequestValidationError` 的 422 用例。

## Deferred from: code review of 1-2-用户注册邀请码 (2026-07-24)

- 邮箱枚举 + 时序侧信道 [backend/src/muse/services/auth_service.py:61-65] — 用户裁决 2026-07-24 接受为已知取舍，内测阶段不修（攻击前提是持有有效邀请码，内测期可控）。**开放注册前须重新评估**：统一错误措辞 + 已存在分支走等时哈希消除时序差 + 接口限流。

## Deferred from: code review of 1-3-用户登录与JWT双token会话 (2026-07-24)

- refresh 轮转并发下可「一换二」[backend/src/muse/repositories/session_repo.py:77] — revoke_and_replace 未校验 revoke rowcount 且 get_active 无行锁，两个并发 /refresh 携同一旧 refresh 可各自换出一枚新 refresh。spec 陷阱④明确 V1 仅需「旧作废+发新」，顺序重放已被测试覆盖。**开放注册前增强**：检测重放（revoke 命中 0 行）即作废该用户全部 session。
- refresh_session 表无界增长、无清理任务 [backend/src/muse/models/account.py] — 每次登录/刷新 INSERT 新行，撤销/过期行永不清理，单用户会话无限累积。需 cron/定时清理基础设施，跨 story，内测期不紧迫。
- 全局 async Redis 客户端从不关闭、绑定首个事件循环 [backend/src/muse/services/rate_limit.py:29-34] — 惰性单例无 shutdown/lifespan 清理。生产 uvicorn 单事件循环不触发，测试已用 module-scoped client 规避；随应用 lifespan 管理统一完善。
- refresh 签发新 access 不校验用户是否仍存在/有效 [backend/src/muse/services/auth_service.py:208] — 与 get_current_user 不一致；已停用/注销但持有效 refresh 的用户仍能刷出 access。V1 无用户停用功能，get_current_user 已 401 兜底。用户停用功能落地时一并处理。
- 登录限流仅邮箱维度、无 IP：账号锁定型 DoS + 无分布式撞库防护 [backend/src/muse/services/rate_limit.py:37] — 对已知邮箱狂发错误密码可锁死该账号 15 分钟。AC4 明确按归一化邮箱限流；IP 维度 + 撞库防护与邮箱枚举同属「开放注册前」加固项。
- /refresh 与 /logout 无接口级限流 [backend/src/muse/routers/auth.py] — 可用随机 token 反复轰炸 /refresh（每次 SHA-256+DB 查询）。内测期无 argon2 开销、影响可控；接口限流随开放注册前加固统一处理。

## Deferred from: code review of 1-4-作品创建与列表持久化空-失败状态 (2026-07-24)

- `GET /api/projects` 无分页/无上限，返回用户全部作品 [backend/src/muse/repositories/project_repo.py] — 单用户作品达数千条时无界查询 + 超大响应体；且索引仅 `user_id`，缺 `(user_id, updated_at)` 复合索引使排序需额外 sort。原型未设计分页 UI、V1 内测作品数少，分页涉及前端契约 + 产品决策，跨 story 处理。
- `project.user_id` FK 未声明 `ON DELETE` 行为 [backend/migrations/versions/b56755f75420_create_project.py] — 默认 NO ACTION/RESTRICT，删除仍有作品的用户会 FK 约束失败；用户数据生命周期（级联/软删/归档）未定义。V1 无删除用户入口触发不到，与 1.3 deferred「用户停用功能落地时处理」一并。（注：conftest `TRUNCATE ... CASCADE` 能清干净靠 TRUNCATE 级联，与 FK ondelete 无关。）
- `_clean_tables`（autouse）在 `MUSE_DB_READY=1` 时无条件访问 Redis [backend/tests/conftest.py] — `_sync_redis().scan_iter("login:fail:*")` 无 Redis 就绪门禁，Redis 宕机（DB 正常）则全部 DB 用例 setup 阶段 error；且 project 用例根本不碰限流。属 Story 1.3 引入的限流测试基建（非 1.4 增量），建议补 Redis 就绪门禁或 try 兜底。

## Deferred from: code review of 1-5-作品重命名与删除 (2026-07-24)

- 并发改名/删除的 check-then-act TOCTOU：非原子，commit/UPDATE 命中 0 行抛 `StaleDataError` 退化 500 而非幂等 404 [backend/src/muse/services/project_service.py:rename_project/delete_project] — 两个并发请求各自 `get_owned_project` 查到同一行后先后 commit，第二个命中 0 行。单用户作品库极低概率触发；根治需 commit 处 try/except StaleDataError → rollback → 转 404，或加行锁/乐观版本。与 1.3/1.4 并发类 deferred 同属「开放注册/多端并发前」加固项。

## Deferred from: code review of 1-6-继续创作-按phase跳转当前步骤 (2026-07-24)

- explore/chapter 目标页未消费路由 id [prototype/app/app.js:2328,2335] — `render()` 的 `exploreMatch`/`chapterMatch` 已捕获 id，但 `renderExploration`/`renderChapterCreation` 函数体不读 id：页面标题依赖全局 `explorationTitle`（首次进入显示默认「未命名小说」而非项目名）、内部返回链硬编码 `#/projects/demo/explore`、chapter route 恒跳 `/chapters/1` 占位（无真实「读到第几章」数据源）。spec AC2 明确「只保证路由正确、不改目标页函数体」，陷阱④/⑤已授权占位并划归 Epic 2（探索）/ Epic 4（章节）无缝接管——届时在对应 render 函数内用路由 id 取真实数据即可闭合。

## Deferred from: Story 1.7 BYOK API Key 绑定 (2026-07-24)

> 以下两项为 story 设计时即定档的**架构性受控留茬**（非 code-review 发现），已在 1.7 Completion Notes 与 sprint-status.yaml 头 MUSE SEQUENCING NOTES 登记，此处汇总便于后续 epic 无缝接管。

- **AC5「生成走用户 Key」的真正消费未接入** [backend/src/muse/services/byok_service.py:122 `get_decrypted_key_for_user`] — 本 story 只交付「安全取回某账户明文 Key」的内部接口，**未实现任何 LLM 调用、未接生成链路、未碰 Provider**（`src/muse/providers/` 当前仅空 `__init__.py`）。LLM 调用一律走 `providers/llm.py` 的 `LLMProvider` 抽象（AR12，architecture.md#焦点一 / #Process-Patterns「业务层禁止直接 import openai SDK」），该文件 **Epic 2 Story 2.1 才建**。**归 Epic 2 Story 2.1**：建 Provider 时调用 `get_decrypted_key_for_user` 决定「走用户 Key 还是托管 Key」；用量计量埋点（AR14）同属 Provider 层、一并落地。非遗漏，是受控衔接。
- **前端 `renderByok` 未接线 + 作品库无设置页入口** [prototype/app/app.js:2079 `renderByok()`、:2133 `[data-byok-save]`、:405 header] — 原型 `app.js` 全站零 `fetch`/零 token 携带；本 story 后端把 `PUT/GET/DELETE /api/byok` 契约做实做透，但**未接前端**（拖入即引入 fetch/token 横切基础设施——token 携带 + 鉴权失败跳转 + error envelope 前端分支 + 掩码渲染 + 解绑交互，属独立前端接线 story 职责）。`data-byok-save` 保存按钮当前仅改 DOM 文案（`app.js:2133-2138`）未落库；作品库 header（`app.js:405`）仅「邮箱 + 退出」，**无进入设置页导航链接**（用户只能手敲 `#/settings/model-access`）。**归后续统一前端接线切片**：届时后端 API 已就绪可零改动对接。此为 1.6 dev notes 已论证的「前端 API 接线是独立关注点」方法论延续。
- **⚠️ `provider=custom` 数据模型不完整：缺 base_url + model（+ 可能的 API 兼容风格）** [backend/src/muse/schemas/account.py `ByokBindRequest`、backend/src/muse/models/account.py `ByokKey`、prototype/app/app.js:2103 provider 三选] — 1.7 的 `ByokBindRequest` 只收 `apiKey` + `provider` 枚举（deepseek/claude/custom），`byok_key` 表也只存这几列。对 **deepseek/claude**，base_url 与 model 名是系统内置常量（architecture.md:107,194-195「OpenAI SDK 兼容，切 base_url」），用户只给 Key 即可；但 **`custom` 的语义就是「用你们没预置的模型」**——后端不知道该往哪个 endpoint 发、用哪个 model 名，**光一把 Key 无法真正调用**。原型三选按钮（app.js:2103）目前是纯视觉（click 仅切 `is-current`，不存不传），Muse 后台「切 base_url」的能力尚未落地。**custom 若要真正可用，须补：`base_url`、`model_name`，很可能还需「API 兼容风格」（OpenAI 兼容 vs Anthropic 兼容，鉴权 header 不同）**——这些是 `LLMProvider` 契约的一部分。**归 Epic 2 Story 2.1**：连同 base_url/model 如何被 Provider 消费一起设计（届时同步补 `ByokKey` 列 + `ByokBindRequest` 字段 + 原型 custom 输入框），避免现在只补 url+model 却在建 Provider 时发现不够、二次返工。**用户 2026-07-24 知悉此缺口并授权按此处理**（当前 custom 为「能选能存但通不了」的占位；deepseek/claude 不受影响）。

## Deferred from: code review of 1-7-BYOKAPIKey绑定全新设置页 (2026-07-24)

- 并发 upsert 的 check-then-act 在 `user_id` 唯一约束下退化为未捕获 500 [backend/src/muse/repositories/account_repo.py:297-313 `upsert_byok`] — 同一用户两个并发 PUT /api/byok（此前均未绑定）都读到 `existing is None`、双双走 insert 分支，第二个 `flush()` 撞 `user_id` unique 约束 → `IntegrityError` 冒泡全局 handler → `internal_error`/500，而非幂等成功或 409。三层审查中 Blind Hunter + Edge Case Hunter 独立确认。code-review 判为 defer：spec Task 4 + 陷阱④已授权「并发替换极低概率，与既有 rename/delete check-then-act 同风险级，加固 deferred 到开放注册/多端并发前」，与 1-5 rename/delete TOCTOU 同属并发类加固项。根治：`upsert_byok` 的 insert 分支 try/except IntegrityError → rollback 后转 update（PG `ON CONFLICT DO UPDATE` 更佳，一条语句原子 upsert）。

## Deferred from: code review of 1-8-托管免费额度护栏与用量展示 (2026-07-26)

- `usage_ledger` 外键未声明 `ON DELETE`，删用户/作品会被外键阻断 [backend/migrations/versions/8cafe7161b60_create_usage_ledger.py:36-37] — `user_id`/`project_id` FK 默认 `NO ACTION`，一旦存在引用行，行级 DELETE user/project 会被外键约束拒绝。**非本 story 引入**：项目全部既有表（byok_key/project/refresh_session）FK 均无 ON DELETE，是既有约定；conftest 用表级 `TRUNCATE ... CASCADE` 清理，掩盖了生产删除路径。属跨 story 的级联删除策略（用户注销/作品删除时用量流水如何处置——级联删还是保留归档），非本 story 范围，与 1.5/1.7 并发类 deferred 同批在「开放注册/数据生命周期治理」时统一定夺。
- `record_usage`/tokens 无 `>=0` 校验、`billing_path` 无枚举/`CHECK` 约束、聚合缺 `(user_id, billing_path)` 复合索引 [backend/src/muse/repositories/account_repo.py:124-175] — 三者均属护栏「真正生效」的输入契约与热路径优化：① `record_usage` 是「供 Epic 2 Provider 层调用的写入接口」，负值 tokens / 非法 billing_path（大小写/拼写变体）由调用方传入、判定归 Epic 2，**当前无任何调用方**（本 story 不接生成链路）；② `sum_hosted_usage` 按 `(user_id, billing_path)` 过滤但仅 `user_id` 单列索引，用量表随每次 LLM 调用膨胀后护栏（每次生成前查）会退化为扫全用户流水。**归 Epic 2 Story 2.1**：Provider 层接入记账埋点时，一并加 tokens `>=0` 校验 + billing_path 归一化/白名单 + 复合索引（表数据量起来后）。Blind Hunter + Edge Case Hunter 独立指出，因落在受控留茬边界内故 defer 而非当下 patch。
- 护栏 `check_quota` 的 check-then-act TOCTOU 竞态：并发生成可整体越过免费额度 [backend/src/muse/services/usage_service.py:42-69 `check_quota`] — `sum_hosted_usage` 读累计与 `used >= quota` 判定之间无行锁/`SELECT ... FOR UPDATE`/原子递增，叠加「生成前 check、LLM 返回后才 record」的巨大时间窗，多个并发生成请求可各自读到旧 `used` 同时通过校验、集体超发。三层审查中 Blind Hunter + Edge Case Hunter 独立指出。**Jianghj 2026-07-27 裁定 defer**：本 story 护栏**不在生成链路上生效**（记账埋点在 Epic 2，当前 `check_quota` 无任何调用方、无并发面），与 1.5 rename/delete、1.7 upsert 的 check-then-act 同属「开放注册/多端并发前」加固项。**归 Epic 2 Story 2.1**：接入生成入口调 `check_quota` 时，连同并发控制一起做（如对 usage 累计加原子递增/预留额度，或 `SELECT ... FOR UPDATE` 锁定用户维度）。

## 设计输入 from: P1 DeepSeek 联调 spike (2026-07-27)

> 非留茬，是 spike 实测产出的**正向设计输入**，供 Epic 2 Story 2.1 LLMProvider 落地时直接采用。可复跑凭证见 `backend/scripts/spike_deepseek.py`（OpenAI SDK 切 base_url `https://api.deepseek.com`，纯外呼不碰 DB）。

- **双档模型名已实测确认，与架构文档一致** [architecture.md:108,196] — `models.list()` 探测账号可用模型恰为 `deepseek-v4-pro`（思考，起草/审查）+ `deepseek-v4-flash`（快，提取/轻任务）两个，与 architecture.md 写定的名字**完全吻合**。实测延迟 flash（~2.9s）约为 pro（~5.6s）的一半，token 用量两档相当。**2.1 可直接按这两个模型名写 Provider，无需再探**。
- **⚠️ 护栏计量必须信 API 回报的 `usage.total_tokens`，不能用「生成前本地字符预估」做触顶判据** [backend/src/muse/services/usage_service.py `check_quota`、backend/src/muse/repositories/account_repo.py `record_usage`] — spike 用「CJK×0.6+其余×0.3」本地估算同一 prompt，得 13 tokens，而 API 实际 `prompt_tokens=17`，**偏差 +23.5%（低估）**。这印证 Story 1.8 以 `SUM(total_tokens)` 为触顶数据源的方向正确；**2.1 接记账埋点时，务必以 chat 响应 `usage`（prompt/completion/total）落库，而非任何本地预估**——本地预估只可用于「调用前的粗略拦截提示」，不可作为扣费/触顶的准数。
- **双档均返回 `reasoning_content`（含 flash 快档），SSE 推送需区分 reasoning vs content** [architecture.md:194 `LLMProvider` chat/stream 接口] — spike 意外发现 flash 快档也带思考过程字段（非仅 pro）。**2.1 的 `LLMProvider.stream` + SSE 三事件设计需明确**：reasoning_content 是单独推给前端（做「思考中」展示）还是丢弃，两档都要处理该字段，不能假设只有 pro 有。此点与 P2（ARQ+SSE 骨架）的事件设计衔接。

## 设计输入 from: P2 ARQ + SSE 端到端骨架 spike (2026-07-27)

> 非留茬，是 spike 实测产出的**正向设计输入**，供 Epic 2 Story 2.x 编排/回传落地时采用。可复跑凭证见 `backend/scripts/spike_arq_sse.py`（单文件同进程起 worker+uvicorn，httpx 跑两轮端到端；需先 `make dev-up` 起 Redis）。依赖已入库：`arq==0.25.0`、`sse-starlette==3.4.6`（pyproject.toml/uv.lock）。

- **技术选型已实测跑通，可直接定为正式选型** — ARQ（`arq==0.25.0`，async 原生 + Redis broker，architecture.md:197）+ sse-starlette（`EventSourceResponse` 接受异步生成器，自动处理 event-stream 帧/心跳）+ Redis Pub/Sub 作 worker→SSE 通道（推模型，对齐 architecture.md:472「Redis+SSE 推送」、:358「禁轮询」）。端到端两轮（happy + error）全绿。**2.x 建 `tasks/worker.py` + `core/sse.py` + `routers/tasks.py` 时可直接照此骨架**。
- **三事件契约已端到端验证，含 error 路径** [architecture.md:335-336] — `progress`（payload `{step, percent}` camelCase）× N → `result`；worker 内异常经 `try/except` 推 `error`（payload `{code, message}`，复用错误 envelope）。**关键：error 是长时任务最需保证的路径**——spike 特地用 `--fail` 让 worker 第 2 步抛异常，确认 error 事件经同一 Pub/Sub 链路推达客户端、且失败后不再有 progress/result。2.x 五段流水线每 step 失败都须走此 error 事件。
- **⚠️ Pub/Sub「先订阅后发布」时序风险，2.x 须处理** [backend/scripts/spike_arq_sse.py `events` 端点] — Redis Pub/Sub 不留存历史消息：若客户端 SSE 订阅**晚于** worker 首个 progress 发布，早期事件会丢。spike 里因 worker 有 0.3s/step 延迟、客户端提交后立即订阅，天然错开未暴露此问题。**2.x 正式实现须补**：要么用 Redis Stream（可回放 + 消费位点）替代纯 Pub/Sub，要么 SSE 端点先补发一次「当前任务快照/已完成 step」再订阅增量——否则页面刷新/断线重连会丢进度。此为 spike 刻意留给正式设计的已知缺口，非疏漏。（**已在 Story 2.1 定档「快照补发 + Pub/Sub 增量」并实现，此缺口闭合**。）

## Deferred from: code review of 2-1-LLMProvider抽象-DeepSeek实现-ARQ-SSE异步底座 (2026-07-27)

> 三层对抗式审查（Blind/Edge/Auditor），主审已核验 ARQ 0.25.0 重试语义源码与各文件实现。6 条 patch 就地修复（见 story Review Findings），以下 6 条 defer 归后续 story。

- **worker 被取消（SIGTERM）且已 record_usage 后 ARQ 重跑致重复计费** [backend/src/muse/tasks/worker.py:118-128] — 核实 ARQ 0.25.0：普通 `Exception` 不重试（落 `else` 分支直接置失败），仅 `CancelledError`/`Retry` 重跑（`retry_jobs=True`/`max_tries=5` 默认）。真实窗口：worker 消费任务、`record_usage` 已 commit、job 未登记完成时被 SIGTERM → CancelledError → 重跑 → 第二条 usage_ledger 行。demo 任务非幂等。本 story 无真实并发生成面。**归 Story 4.4**：`WorkerSettings.max_tries=1` 或任务级幂等键（record_usage 带 task_id 去重）。与下条 TOCTOU 同批做。
- **`check_quota`→`record_usage` TOCTOU，托管额度并发超发** [backend/src/muse/tasks/worker.py:53-73] — **1.8 已登记同条**（本文件上方 1-8 条目，Jianghj 2026-07-27 裁定 defer 至接入生成链路时做）。本 story 是「接入生成链路」时点但仍无真实并发生成面（只示范任务），Completion Notes 已重新登记。**归 Story 4.4**：接入真实生成入口调 check_quota 时连同并发控制（原子递增/预留额度/`SELECT FOR UPDATE`）一起做，不再 defer。
- **`demo_generate` 用 `settings.deepseek_api_key` 作真实生成门槛，跳过 BYOK 用户记账链路** [backend/src/muse/tasks/worker.py:64] — 已绑 deepseek 的 BYOK 用户走自己的 Key（不依赖托管 key），但 worker 用「托管 key 是否配置」作唯一门槛，托管 key 空但已配 BYOK 的用户走进「跳过真实生成」分支，BYOK 记账路径未被示范任务覆盖（factory 单元已验 byok 分派）。本 story 为底座示范任务。**归真实生成入口切片（4.4）**：门槛改为「用户是否有可用 provider」而非「托管 key 是否配置」。
- **OpenAI 流式响应未 `async with`/显式 close，中途异常/早断可能不释放连接** [backend/src/muse/providers/deepseek.py:130-141] — `create(stream=True)` 后直接 `async for`，无 `finally: await stream.close()`；中途 break/异常时底层 httpx 流响应可能不归还连接池。与 story patch「MeteredProvider.stream 早断不计费」同源场景。**归 Epic 2 探索对话接线切片**（Completion Notes 已登记流式 include_usage 待该切片验证）：连同 stream 生命周期一起硬化。
- **SSE `event_stream` 的 `listen()` 无服务端超时，worker 崩溃/永不推终态则流永久挂起** [backend/src/muse/core/sse.py:126] — 快照为 None（任务入队但 worker 未起/已崩）或快照非终态时进入 `pubsub.listen()` 无 watchdog；worker `except Exception` 不捕获 `CancelledError`（SIGTERM 不推 error）。客户端 UI 永久「生成中」，靠 sse-starlette 15s ping 保活。本 story 示范任务不主动崩，真实长时生成才现实化。**归 Epic 4**：任务级看门狗/整体超时，或 worker 信号处理器捕获 CancelledError 推 error 终态。
- **AC4/Task5/定档① 原文「先补发快照再订阅」与代码「先订阅再补发」矛盾（spec 可追溯性）** [spec L33/L87/L149 vs backend/src/muse/core/sse.py:113-126] — 文档修正而非代码问题：代码顺序**更正确**（dev 实现中发现原顺序有竞态并纠正，Debug Log + 模块 docstring + Completion Notes 定档① 均已 subscribe-first）。AC4 Then-意图由代码达成且测试佐证。属同文档前文陈旧措辞与后文+代码打架。**归文档收尾**：回改 AC4/Task5/定档① 的 snapshot-first 措辞为 subscribe-first。

## Deferred from: code review of 2-2-探索会话根与模式分叉模式独立 (2026-07-27)

> 三层对抗式审查（Blind/Edge/Auditor）。5 条 AC 全部满足、8 个陷阱全部规避。1 条 decision-needed（main.py 提交边界，已按 2.1/2.2 拆分提交解决）；3 条噪声/假阳性 dropped；以下 2 条 defer 归后续。

- **`except IntegrityError` 过宽，并发删 project 时 FK 违例退化成 500 而非 404** [backend/src/muse/services/exploration_service.py:59] — 同用户 TOCTOU 竞态（一处进入探索、一处删除该 project 并发）下，若删除发生在 `get_owned_project` 通过之后、`create_session` 的 INSERT 之前，INSERT 撞的是 project_id 的 FK 约束而非 (user_id, project_id) 唯一约束，同样抛 IntegrityError 落进同一 except；rollback 后重查 get_session_by_project 返 None（project 已删）→ 走 raise → 全局 handler 500。正常时序下对已删 project 进入探索应得 404 project_not_found。极罕见同用户竞态、无数据损坏、无越权，raise 路径安全，仅错误码不一致。**归后续**：如需精确化，按 sqlstate/约束名区分唯一约束冲突与 FK 违例（后者转 404）。
- **测试 conftest `_clean_tables` 未列 `exploration_session`，靠 CASCADE 兜底** [backend/tests/conftest.py:77] — 当前 `TRUNCATE "user", ... RESTART IDENTITY CASCADE` 会级联清空引用 user 的 exploration_session，且各用例断言按 `WHERE project_id = :pid` 收敛到本用例，不会污染——现无 bug。但清表清单注释逐个列举 refresh_session/project/byok_key/usage_ledger 却漏了 exploration_session，其安全性隐式依赖 FK+CASCADE；若日后改成显式逐表 TRUNCATE（不带 CASCADE）或调整 FK，会话残留会静默泄漏进后续用例。**归测试基建维护**：将 exploration_session 显式补入清表清单。


## Deferred from: code review of 2-3-引导探索-真实Agent理解自由作答-沉浸问答 (2026-07-28)

> 三层对抗式审查（Blind/Edge/Auditor）。5 条 AC 无硬违反、10 陷阱全规避、受控决策 A/B 兑现。主审已实测证伪 Blind#10（openai 2.47 的 AsyncStream 确实支持 `async with`，生产安全）。1 条 decision-needed（LLM 入参上界）+ 5 条 patch 见 story Review Findings；10 条噪声/假阳性 dropped；以下 3 条 defer 归后续。

- **`MeteredProvider.stream` 的 `"".join(m.get("content",""))` 在 content 为 None/list 时 TypeError** [backend/src/muse/providers/factory.py:116] — 既有代码（2.1 引入），本 story 只在 deepseek.py 搬动同款行进 diff `+` 区、未新引入。内部消息恒由 `_build_messages` 构造为 `{role, content: str}`，content 恒 str，边界已收窄，现无现实触发路径。**归 provider 层防御性加固**：若未来引入多模态（content 为 list）或允许 None content，改为 `(m.get("content") or "")` 并处理非 str 类型。
- **交互式流式无整体超时，上游 stall 时独立 session + httpx 连接可长时间占用** [backend/src/muse/providers/deepseek.py stream()] — SSE 客户端保持连接、上游 DeepSeek 中途 stall（不推 chunk 也不断开）时，`async for` 阻塞等待，独立 `async_session_maker()` session 与底层 httpx 连接被占用至 SDK 默认超时（可达数百秒）。本 story 交互式单次流式、非并发批量面，占用风险未现实化。**归 Story 4.4**：接入真实生成入口时连同 provider 层横切超时策略（`asyncio.timeout` 包裹流消费 / httpx client 显式 timeout）一并做，与并发控制同批。
- **`_FakeAsyncStream.__aiter__` 用 async-gen 实现、偏离真实 AsyncStream 协议；离线三用例全 mock、真实 `async with` 支持仅靠 CI 默认 skip 的 `@requires_deepseek` 覆盖** [backend/tests/test_providers.py:118-140] — 真实 `openai.AsyncStream.__aiter__` 返回 self 并实现 `__anext__`，fake 写成 async 生成器，docstring 却自称「模拟真实 AsyncStream 协议」——措辞过度。主审已实测 openai 2.47.0 的 AsyncStream 实现了 `__aenter__/__aexit__/__aiter__/__anext__/close`，故 `async with await create(...)` 生产安全，此为**测试保真度**而非缺陷。**归测试基建维护**：有真实 key 时跑一次 `test_real_deepseek_stream_contract` 坐实真实 SDK 契约；或让 fake 的 `__aiter__` 返回 self + 实现 `__anext__` 以更贴近真实协议。
