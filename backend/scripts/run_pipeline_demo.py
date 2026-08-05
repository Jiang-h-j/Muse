"""Story 4.2 Task 6：四段流水线装置验证脚本（退风险验证，非 src 业务链路）。

目的（AC6）：跑通完整四段流水线 context→drafter→reviewer→polisher，验证「四段串起来能出
一章符合 NFR1 的正文」，并产出单章真实 token 成本（供回填免费额度阈值 settings.py:69）。

装置定位：放 backend/scripts/（退风险验证脚本，与 spike_deepseek.py / blind_test 同级），
不进 src 业务链路。真打 DeepSeek API（drafter/reviewer/polisher 各一次），需连 DB（造种子
confirmed story_bible + 编排器落 run 表）。

两种输入：
- --from-samples（默认）：造一份测试 user + project + confirmed story_bible（12 字段 +
  预置五维 style_profile），零外部依赖跑通装置。
- --from-project <project_id> --user <user_id>：读真实 confirmed 行跑（喂真材料）。

运行：
  cd backend && export MUSE_DB_READY 无关（脚本直接连主 .env 的 DATABASE_URL）
  cd backend && uv run python scripts/run_pipeline_demo.py            # 造种子跑
  cd backend && uv run python scripts/run_pipeline_demo.py --idea "想看一场雨夜的重逢"
  cd backend && uv run python scripts/run_pipeline_demo.py --from-project <pid> --user <uid>

产样落 backend/docs/pipeline-4.2/：终稿 + 各段中间产物 + 轴 B 统计 + 成本报告。
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
from muse.orchestration import ai_taste_lexicon, pipeline  # noqa: E402
from muse.repositories import chapter_generation_repo as run_repo  # noqa: E402

_DOCS_DIR = _BACKEND_ROOT / "docs" / "pipeline-4.2"

# 预置测试设定（修仙题材，12 字段 confirmed）——零依赖造种子用。
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
# 预置五维 style_profile（cold-rain 冷峻夜雨文风，对应 style_anchor 五维格式）。
_DEMO_STYLE_PROFILE = (
    "人称：第三人称贴身视角\n"
    "语气：冷峻克制，不煽情\n"
    "句式节奏：短句为主，偶尔一个长句收束\n"
    "意象密度：中等，偏爱潮湿、旧物、灯火的意象\n"
    "段落长度倾向：短段落，留白多"
)


async def _seed_confirmed_project(idea: str | None) -> tuple[uuid.UUID, uuid.UUID]:
    """造一个 user + project + confirmed story_bible，返回 (user_id, project_id)。"""
    async with async_session_maker() as session:
        user = User(
            email=f"pipeline-demo-{uuid.uuid4()}@test.local", password_hash="x"
        )
        session.add(user)
        await session.flush()
        project = Project(user_id=user.id, title="流水线装置测试作品", mode="guided")
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


def _print_step(title: str, text: str) -> None:
    print(f"\n{'=' * 70}\n【{title}】\n{'-' * 70}\n{text}\n")


async def _dump_run_products(
    user_id: uuid.UUID, project_id: uuid.UUID, chapter_number: int
) -> dict:
    """从 run 表读各段落库产物（context/drafter/reviewer/polisher），返回 steps dict。"""
    async with async_session_maker() as session:
        run = await run_repo.get_run(
            session,
            user_id=user_id,
            project_id=project_id,
            chapter_number=chapter_number,
        )
        return dict(run.steps) if run and run.steps else {}


async def main() -> int:
    parser = argparse.ArgumentParser(description="四段流水线装置验证")
    parser.add_argument(
        "--from-project", dest="project_id", default=None,
        help="用真实作品的 confirmed 设定跑（需同时给 --user）",
    )
    parser.add_argument("--user", dest="user_id", default=None, help="--from-project 的属主")
    parser.add_argument("--chapter", type=int, default=1, help="第几章（默认 1）")
    parser.add_argument("--idea", default=None, help="本章想法（可选）")
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
        user_id, project_id = await _seed_confirmed_project(args.idea)
        print(f"已造种子 confirmed 作品：user={user_id} project={project_id}")

    print(f"开始跑四段流水线（第 {args.chapter} 章，idea={args.idea!r}）……")

    async def _on_progress(step_name: str) -> None:
        print(f"  ▶ {step_name} …")

    final_text = await pipeline.run_chapter_pipeline(
        user_id=user_id,
        project_id=project_id,
        chapter_number=args.chapter,
        chapter_idea=args.idea,
        on_progress=_on_progress,
    )

    steps_state = await _dump_run_products(user_id, project_id, args.chapter)
    for name in pipeline.PIPELINE_STEPS:
        entry = steps_state.get(name, {})
        _print_step(f"{name}（{entry.get('status', '?')}）", entry.get("output", ""))

    # 轴 B 统计：终稿的黑名单词频 + 句式套路命中（NFR1 客观信号）。
    stats = ai_taste_lexicon.analyze_axis_b(final_text)
    print(f"\n{'=' * 70}\n【轴 B 统计（终稿）】\n{'-' * 70}")
    print(f"字符数：{stats.char_count}")
    print(f"黑名单词频：{stats.blacklist_per_kchar} 词/千字（总 {stats.blacklist_total} 次）")
    if stats.blacklist_hits:
        print("  命中：" + "、".join(f"{h.word}×{h.count}" for h in stats.blacklist_hits))
    print(f"句式套路命中：{stats.pattern_total} 处")
    for h in stats.pattern_hits:
        print(f"  {h.note}：{'／'.join(h.snippets[:3])}")

    # 落档留存（终稿 + 各段产物 + 轴 B）。
    _DOCS_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "lexicon_version": ai_taste_lexicon.LEXICON_VERSION,
        "chapter_number": args.chapter,
        "chapter_idea": args.idea,
        "final_text": final_text,
        "steps": steps_state,
        "axis_b": {
            "char_count": stats.char_count,
            "blacklist_per_kchar": stats.blacklist_per_kchar,
            "blacklist_total": stats.blacklist_total,
            "pattern_total": stats.pattern_total,
        },
    }
    out = _DOCS_DIR / f"demo-chapter-{args.chapter}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (_DOCS_DIR / f"demo-chapter-{args.chapter}-final.md").write_text(
        final_text, encoding="utf-8"
    )
    print(f"\n✅ 产样已落档：{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
