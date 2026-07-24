# Muse 后端

FastAPI 分层骨架 + 多租户就绪地基 + AI 编排底座。采用 `src/muse/` src-layout，uv 管理依赖。

## 技术栈

- Python 3.12+ / FastAPI（`fastapi[standard]`）
- SQLAlchemy 2.0 async + Alembic（**不用 SQLModel**）
- PostgreSQL + pgvector 0.8.x（HNSW），DB driver 用 **psycopg3**（DSN `postgresql+psycopg://`）
- Redis 7（后续 ARQ broker + SSE/缓存）
- Pydantic V2 + pydantic-settings；ruff + mypy + pytest

## 目录结构

```
backend/
├── pyproject.toml          # uv 依赖 + ruff/mypy/pytest 配置
├── alembic.ini
├── .env.example
├── docker/initdb/          # Postgres 初始化脚本（启用 pgvector 扩展）
├── src/muse/
│   ├── main.py             # FastAPI 应用入口
│   ├── core/               # settings / db / errors（+ security / sse 占位）
│   ├── models/             # SQLAlchemy 2.0 ORM（base.py 通用 Base，无租户列）
│   ├── schemas/            # Pydantic V2（CamelModel = snake_case↔camelCase 边界）
│   ├── repositories/       # DAO：后续注入 user_id + project_id 租户守卫
│   ├── services/           # 业务编排
│   ├── routers/            # 仅校验入参 + 分发
│   └── orchestration/ providers/ rag/ tasks/   # 独立域（占位，后续 epic 实现）
├── migrations/             # Alembic async
└── tests/                  # 镜像 src 树的 pytest 布局
```

## 本地开发

前置：已装 [uv](https://docs.astral.sh/uv/) 与 Docker。

```bash
# 1. 起本地依赖（PostgreSQL+pgvector / Redis），在项目根 Muse/ 执行
docker-compose up -d

# 2. 安装依赖（在 backend/ 执行；据 uv.lock 装齐）
uv sync

# 3. 准备环境变量
cp .env.example .env        # 按需修改

# 4. 跑迁移（当前无业务表，空跑通过）
uv run alembic upgrade head

# 5. 启动应用
uv run fastapi dev src/muse/main.py
# 健康检查
curl http://localhost:8000/health      # → {"status":"ok","dbConnected":true}
```

> 说明：首次搭建时依赖是经 `uv add` 引入并写入 `pyproject.toml` / `uv.lock` 的；
> 后续克隆仓库只需 `uv sync` 即可据 lock 还原环境。

## 质量校验

```bash
uv run ruff check      # lint
uv run mypy            # 类型
uv run pytest          # 测试
```

## 生成邀请码（本地测试注册）

注册（`POST /api/auth/register`）需要一个有效未使用的邀请码。用内置脚本生成：

```bash
uv run python -m muse.scripts.seed_invite            # 生成 1 个随机码
uv run python -m muse.scripts.seed_invite --count 3  # 生成 3 个
uv run python -m muse.scripts.seed_invite --code MY-CODE  # 指定码
```

脚本会把码写入 `invite_code` 表并打印。随后用该码 + 邮箱 + ≥8 位密码调用注册接口即可。


## 本地登录 / 刷新 / 退出（Story 1.3）

双 token 会话：`access`（无状态短期 JWT，默认 15 分钟）+ `refresh`（长效可撤销，默认 30 天，
服务端只存 SHA-256 哈希）。前端存两枚 token，受保护接口带 `Authorization: Bearer <access>`。

```bash
B=http://localhost:8000

# 1. 登录：得双 token（先按上一节注册好账号）
LOGIN=$(curl -s -X POST $B/api/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"your-password"}')
ACCESS=$(echo "$LOGIN"  | python3 -c 'import sys,json;print(json.load(sys.stdin)["accessToken"])')
REFRESH=$(echo "$LOGIN" | python3 -c 'import sys,json;print(json.load(sys.stdin)["refreshToken"])')

# 2. 访问受保护端点：带 access token
curl -s $B/api/auth/me -H "Authorization: Bearer $ACCESS"        # → {"id":...,"email":...}

# 3. 刷新：用 refresh 换新 access（会轮转下发新 refresh，旧 refresh 立即失效）
curl -s -X POST $B/api/auth/refresh -H 'Content-Type: application/json' \
  -d "{\"refreshToken\":\"$REFRESH\"}"

# 4. 退出：作废当前 refresh 会话（幂等，返回 204）
curl -s -o /dev/null -w "%{http_code}\n" -X POST $B/api/auth/logout \
  -H 'Content-Type: application/json' -d "{\"refreshToken\":\"$REFRESH\"}"
```

错误响应统一 error envelope `{code, message, detail}`，`detail` 附对接原型的布尔位：
密码/邮箱错误 `401 invalid_credentials`（`detail.invalid`）、refresh 失效 `401 token_invalid`
（`detail.expired`）、失败超阈值 `429 too_many_attempts`（`detail.locked`，默认 5 次 / 15 分钟，
限流走 Redis，不可用时 fail-open 放行）。

> 生产护栏：`DEBUG=false` 时若 `JWT_SECRET` 仍为默认占位值会**拒绝启动**（fail-fast）。
> 本地 `.env` 用 `DEBUG=true` 即可开箱即用；部署前务必换强随机 `JWT_SECRET`。


## 前端原型与 Vite 渐进增强（预留，本阶段不初始化）

前端原型位于 `../prototype/app/{index.html, app.js, styles.css}`，是 **UX/契约的唯一事实基准**，
本阶段一字节不改。原型为纯静态，可直接用任意静态服务器访问：

```bash
cd ../prototype/app && python3 -m http.server 5173
```

**未来接入 Vite 的正确姿势**（届时另起前端 story 执行，切勿现在做）：

- 以 `prototype/app` 为 Vite `root`，**复用现有 `index.html` 作为入口**（其入口为传统
  `<script src="./app.js">`）。
- 手写极简 `vite.config.js`（设 `root`/`server`），仅为原型加 HMR、打包、环境变量能力。
- **切勿执行 `npm create vite`**：其 vanilla 模板会生成同名 `index.html` / `main.js` / `style.css`
  覆盖原型三件套、且入口范式（ES module）与原型冲突，违反「原型=唯一契约事实基准」铁律。
