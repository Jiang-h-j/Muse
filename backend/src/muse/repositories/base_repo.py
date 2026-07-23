"""DAO 基类：后续所有业务查询经此层，强制注入 user_id + project_id 租户守卫（NFR3）。

占位模块——本 story（1.1）无业务表，仅建立目录约定。
租户守卫逻辑从 Story 1.2（user 表落地）起实现。
"""
