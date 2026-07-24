"""DAO 基类：跨表业务查询的 user_id 租户守卫约定（NFR3 行级隔离）。

本 story（1.4）起 project 是首张带 user_id 的业务表，租户守卫从「占位」转为「必须遵守的
约定」：**每个业务 repo 的查询/写入都必须显式绑定 user_id**（`select(Model).where(
Model.user_id == user_id)`、写入时 `user_id=current_user.id`），漏写即越权读到他人数据。

未在此提供泛型 `tenant_scoped_select` 原语：SQLAlchemy 的 Mapped 列在「实例访问」与「类访问」
下类型不同，泛型 Protocol 难同时满足二者而不牺牲类型安全；当前仅 project_repo 一个调用方，
按 YAGNI 就地内联更清晰。待第二张业务表出现（如 1.7 byok_key）再评估是否抽取共享原语。
"""
