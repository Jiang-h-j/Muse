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
