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
