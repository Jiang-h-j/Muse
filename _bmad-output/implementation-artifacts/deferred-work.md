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
