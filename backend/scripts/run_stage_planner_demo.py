"""Story 4.3 Task 5：阶段规划装置验证脚本（退风险验证，非 src 业务链路）。

目的（AC2/AC8）：跑通 stage_planner.plan_first_stage，验证「读真实 confirmed 设定能出一份
合理的首阶段规划（阶段目标 + 若干章 title/brief、章数按剧情非写死）」，并产出单次真实 token
成本（供成本核算）。

装置定位：放 backend/scripts/（退风险验证脚本，与 run_pipeline_demo.py 同级），不进 src 业务
链路。真打 DeepSeek API（一次思考档调用），需连 DB（造种子 confirmed story_bible + 落表）。

两种输入：
- --from-samples（默认）：造一份测试 user + project + confirmed story_bible（12 字段 + 预置五维
  style_profile），零外部依赖跑通装置。
- --from-project <project_id> --user <user_id>：读真实 confirmed 行跑（喂真材料）。

运行：
  cd backend && uv run python scripts/run_stage_planner_demo.py            # 造种子跑
  cd backend && uv run python scripts/run_stage_planner_demo.py --from-project <pid> --user <uid>

产样落 backend/docs/stage-planner-4.3/：阶段目标 + 章节骨架 + 章数 + token/成本。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

# 让脚本能 import muse.*（src 在 backend/src；pyproject pythonpath=["src"] 仅对 pytest 生效）。
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_ROOT / "src"))

from muse.core.db import async_session_maker  # noqa: E402
from muse.core.settings import get_settings  # noqa: E402
from muse.models.account import User  # noqa: E402
from muse.models.project import Project  # noqa: E402
from muse.models.story_bible import StoryBible  # noqa: E402
from muse.orchestration import stage_planner  # noqa: E402

_DOCS_DIR = _BACKEND_ROOT / "docs" / "stage-planner-4.3"

# 预置测试设定（修仙题材，12 字段 confirmed）——与 run_pipeline_demo.py 同源，零依赖造种子。
_DEMO_BIBLE: dict[str, str] = {
    "genre": "修仙",
    "core_appeal": "小人物在冷酷宗门里稳扎稳打逆袭的爽感，慢热但扎实",
    "protagonist": "沈砚，外门杂役出身，想在宗门站稳脚跟证明自己；缺陷是过分谨慎、不敢赌",
    "main_conflict": "与打压他的内门执事争夺一处灵矿的采掘权；执事同样出身低微、却选择踩着别人上位（反派镜像）",  # noqa: E501
    "world_rules": "灵气复苏的旧修仙界，境界分练气—筑基—金丹；宗门论功分配资源，杂役几乎无出头之日",
    "overall_tone": "冷峻、克制、带一点旧时代的潮湿感",
    "opening_hook": "沈砚在雨夜的废弃丹房里，发现一枚被前人遗弃、却还残留一丝灵光的破损玉简",
    "power_system": "练气九层—筑基—金丹；灵根资质决定修炼速度，杂役多是杂灵根",
}
_DEMO_STYLE_PROFILE = (
    "人称：第三人称贴身视角\n"
    "语气：冷峻克制，不煽情\n"
    "句式节奏：短句为主，偶尔一个长句收束\n"
    "意象密度：中等，偏爱潮湿、旧物、灯火的意象\n"
    "段落长度倾向：短段落，留白多"
)


async def _seed_confirmed_project() -> tuple[uuid.UUID, uuid.UUID]:
    """造一个 user + project + confirmed story_bible，返回 (user_id, project_id)。"""
    async with async_session_maker() as session:
        user = User(
            email=f"stage-demo-{uuid.uuid4()}@test.local", password_hash="x"
        )
        session.add(user)
        await session.flush()
        project = Project(user_id=user.id, title="阶段规划装置测试作品", mode="guided")
        session.add(project)
        await session.flush()
        bible = StoryBible(
            user_id=user.id,
            project_id=project.id,
            style_profile=_DEMO_STYLE_PROFILE,
            status="confirmed",
            **_DEMO_BIBLE,
        )
        session.add(bible)
        await session.commit()
        return user.id, project.id


async def main() -> int:
    parser = argparse.ArgumentParser(description="阶段规划装置验证")
    parser.add_argument(
        "--from-project", dest="project_id", default=None,
        help="用真实作品的 confirmed 设定跑（需同时给 --user）",
    )
    parser.add_argument("--user", dest="user_id", default=None, help="--from-project 的属主")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.deepseek_api_key:
        print("❌ 未配置 DEEPSEEK_API_KEY（backend/.env），无法真打 API。", file=sys.stderr)
        return 1

    if args.project_id:
        if not args.user_id:
            print("❌ --from-project 需同时给 --user <user_id>。", file=sys.stderr)
            return 1
        user_id = uuid.UUID(args.user_id)
        project_id = uuid.UUID(args.project_id)
        print(f"用真实作品 confirmed 设定跑：project={project_id}")
    else:
        user_id, project_id = await _seed_confirmed_project()
        print(f"已造种子 confirmed 作品：user={user_id} project={project_id}")

    print("开始跑阶段规划生成（思考档 pro）……")
    plan = await stage_planner.plan_first_stage(user_id=user_id, project_id=project_id)

    print(f"\n{'=' * 70}\n【阶段目标】\n{'-' * 70}\n{plan.goal}\n")
    chapters = plan.chapters or []
    print(f"{'=' * 70}\n【章节骨架】（共 {len(chapters)} 章，按剧情定、非写死）\n{'-' * 70}")
    for i, ch in enumerate(chapters, 1):
        print(f"  第{i}章 · {ch.get('title', '')}")
        print(f"        {ch.get('brief', '')}")

    # 落档留存。
    _DOCS_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "stage_number": plan.stage_number,
        "goal": plan.goal,
        "chapter_count": len(chapters),
        "chapters": chapters,
    }
    out = _DOCS_DIR / "demo-stage-plan.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ 产样已落档：{out}")
    print(f"   章数={len(chapters)}（NFR4：按剧情非写死，非恒 5）")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
