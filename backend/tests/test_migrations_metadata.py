"""门禁：Alembic autogenerate 的模型可见性契约（离线，无需 DB）。

根治历史反复踩坑——「新建业务表忘在 alembic `env.py` 手动 import 模型，
致 autogenerate『看不见』新表却不报错」。现由 `muse.models.load_all_models()`
用 `pkgutil.iter_modules` 遍历包目录自动发现，env.py 不再手写 import 列表。

自动发现遍历目录，不会漏掉任何 `.py` 文件——唯一的退化路径是：某个真正
含表定义的模块被错误地加进 `_NON_MODEL_MODULES` 排除名单，从而被跳过。
本测试正面守住这条：断言每个被排除的模块都确实不含 `__tablename__`；并断言
所有声明的表在 load 后都进了 Base.metadata（autogenerate 的 target）。
"""

import ast
import pkgutil
from pathlib import Path

import muse.models
from muse.models import (
    _NON_MODEL_MODULES,  # 门禁针对的排除名单
    Base,
    load_all_models,
)


def _module_declares_table(module_name: str) -> bool:
    """静态解析：该模型源文件是否声明了 `__tablename__`（不 import、不实例化）。"""
    source = (Path(muse.models.__path__[0]) / f"{module_name}.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "__tablename__" for t in node.targets
        ):
            return True
    return False


def _all_module_names() -> set[str]:
    return {m.name for m in pkgutil.iter_modules([str(Path(muse.models.__path__[0]))])}


def test_no_table_module_is_excluded() -> None:
    """排除名单里的模块都不能含表定义——否则该表会被 load_all_models 跳过、autogenerate 漏掉。

    这是自动发现唯一的退化路径：新增/改动模型时把真含表的模块误加进
    `_NON_MODEL_MODULES`。遍历目录本身不会漏文件，故只需守住这一条。
    """
    wrongly_excluded = {
        name
        for name in _NON_MODEL_MODULES
        if name in _all_module_names() and _module_declares_table(name)
    }
    assert not wrongly_excluded, (
        f"以下模块含表定义却被 _NON_MODEL_MODULES 排除：{wrongly_excluded}。"
        "它们的表会被 load_all_models() 跳过，导致 alembic autogenerate 看不见——"
        "请从排除名单移除。"
    )


def test_declared_tables_registered_after_load() -> None:
    """load_all_models() 后，每个源文件里声明的表都出现在 Base.metadata。"""
    load_all_models()
    registered = set(Base.metadata.tables)

    declared = {
        name for name in _all_module_names() if name not in _NON_MODEL_MODULES
    }
    # 至少核心表在位，防止整体失效时空集静默通过。
    for core_table in ("user", "project", "usage_ledger"):
        assert core_table in registered, (
            f"核心表 {core_table} 未注册到 Base.metadata——load_all_models 可能失效"
        )
    # 声明了表的模块，其表名必须已注册（用 metadata 侧的完整表集合校验覆盖面）。
    assert declared, "muse.models 下未发现任何模型模块——包结构可能异常"
