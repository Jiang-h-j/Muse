"""生成邀请码的最小 CLI，便于本地/QA 测试注册（AC1 配套）。

用法（在 backend/ 下）：
    uv run python -m muse.scripts.seed_invite            # 生成 1 个随机码
    uv run python -m muse.scripts.seed_invite --count 3  # 生成 3 个
    uv run python -m muse.scripts.seed_invite --code MY-CODE  # 指定码

只依赖标准库 secrets 生成码，不引入无关依赖。
"""

import argparse
import asyncio
import secrets

from sqlalchemy.exc import IntegrityError

from muse.core.db import async_session_maker
from muse.models.account import InviteCode


def generate_code() -> str:
    """生成 URL 安全的随机邀请码。"""
    return secrets.token_urlsafe(12)


async def seed(codes: list[str]) -> list[str]:
    async with async_session_maker() as session:
        session.add_all(InviteCode(code=code) for code in codes)
        await session.commit()
    return codes


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成 Muse 邀请码")
    parser.add_argument("--count", type=int, default=1, help="生成随机码的数量（>=1）")
    parser.add_argument("--code", type=str, default=None, help="指定单个邀请码（忽略 --count）")
    args = parser.parse_args()
    if args.code is None and args.count < 1:
        parser.error("--count 必须 >= 1")
    return args


def main() -> None:
    args = _parse_args()
    codes = [args.code] if args.code else [generate_code() for _ in range(args.count)]
    try:
        created = asyncio.run(seed(codes))
    except IntegrityError:
        # code 唯一约束冲突：--code 指定了已存在的码，或随机码极小概率碰撞。
        raise SystemExit(f"邀请码已存在，未创建：{', '.join(codes)}") from None
    print("已生成邀请码：")
    for code in created:
        print(f"  {code}")


if __name__ == "__main__":
    main()
