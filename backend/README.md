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
