"""muse.models 包：SQLAlchemy 2.0 ORM 模型。

`load_all_models()` 自动导入本包内所有模型模块，确保其 ORM 类注册到
`Base.metadata`——供 Alembic autogenerate 检测。

根治「新建表忘在 alembic `env.py` 手动 import，致 autogenerate『看不见』新表
却不报错」：env.py 与门禁测试均调用它，加新模型文件无需再改任何 import 列表。
"""

import importlib
import pkgutil

from muse.models.base import Base

__all__ = ["Base", "load_all_models"]

# 本包内不含表定义、无需作为模型模块加载的子模块。
_NON_MODEL_MODULES = {"base"}


def load_all_models() -> None:
    """导入本包内所有模型模块，触发其 ORM 类注册到 Base.metadata。"""
    for module_info in pkgutil.iter_modules(__path__):
        name = module_info.name
        if name in _NON_MODEL_MODULES or name.startswith("_"):
            continue
        importlib.import_module(f"{__name__}.{name}")
