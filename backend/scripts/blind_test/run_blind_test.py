"""盲测门禁装置：写作任务书组装 + DeepSeek 侧真实生成（Story 4.1 Task 2）。

**装置定位**（AC6）：退风险验证脚本，放 backend/scripts/blind_test/，不进 src 业务链路。
产出盲测对照样本的 DeepSeek 一侧；Claude 一侧由 dev 会话开子agent读同一份 writing-brief
生成（Task 3，非本脚本能独立跑）。

**AC1 同一输入硬约束**：写作任务书（drafter 消息）在 build_writing_brief 里组装**一次**，
落盘 writing-brief.md，DeepSeek 侧与 Claude 侧共用同一份——两侧唯一变量是生成方。

**设定输入双来源**：
- --from-samples（默认，零 DB 依赖）：用 style_anchor 预置样本库现抽 style_profile
  + dev 造的测试 story_bible 12 字段（TEST_BIBLE）。
- --from-project <project_id>：从真实 story_bible confirmed 行读设定 + style_profile
  （走独立 async session，仿 style_anchor_agent）。

**匿名化**（AC3）：每篇写独立文件 samples/<随机 id>.md（仅正文，无生成方标识）；生成方
归属 + 轴 B 统计写进评分阶段不可见的 _key.json。

运行：
    cd backend && uv run python -m scripts.blind_test.run_blind_test          # 默认 from-samples
    cd backend && uv run python -m scripts.blind_test.run_blind_test --n 6 --sample cold-rain
    cd backend && uv run python -m scripts.blind_test.run_blind_test --from-project <uuid>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import secrets
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

# 让 `blind_test.xxx` 绝对 import 在两种运行上下文下都成立：直接跑本文件
# （python scripts/blind_test/run_blind_test.py）时 scripts/ 不在 sys.path，须自行注入；
# pytest 下由 conftest 注入（同一路径，幂等）。统一用 blind_test.* 绝对 import。
_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
# muse.* 在 backend/src/（pyproject pythonpath=["src"] 只对 pytest 生效）；直接跑脚本时
# 须注入 src/ 才能 import DeepSeekProvider / style_anchor_agent 等既有实现。
_SRC_DIR = str(Path(__file__).resolve().parent.parent.parent / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

# 装置纯逻辑（词表统计）复用 Task 1 模块（同目录）。
from blind_test.ai_taste_lexicon_temp import LEXICON_VERSION, analyze_axis_b  # noqa: E402

# ---------------------------------------------------------------------------
# 路径：留档落 backend/docs/blind-test-4.1/（脚本在 backend/scripts/blind_test/ 下）。
# ---------------------------------------------------------------------------
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
_DOCS_DIR = _BACKEND_ROOT / "docs" / "blind-test-4.1"
_SAMPLES_DIR = _DOCS_DIR / "samples"
_BRIEF_PATH = _DOCS_DIR / "writing-brief.md"
_KEY_PATH = _DOCS_DIR / "_key.json"
_SCORING_SHEET_PATH = _DOCS_DIR / "scoring-sheet.md"

# 生成参数：章节体量（AC 生成对照样本），控成本/延迟。两侧尽量对齐（子 agent 在 brief 里
# 约束篇幅）。DeepSeek 侧用思考档（起草主场景，architecture.md:196）。
_DEFAULT_N = 6
_GEN_MAX_TOKENS = 2500


# ---------------------------------------------------------------------------
# story_bible 12 字段轻量承载（不依赖 ORM，脚本可从 ORM 行或测试常量构造）。
# 字段名对齐 models/story_bible.py（snake_case），标签对齐设定圣经展示语义。
# ---------------------------------------------------------------------------
@dataclass
class BibleFields:
    """写作任务书所需的 story_bible 12 字段（通用主干 7 + 题材特化 4 + 文风 1）。

    特化 4 字段可空（None 表示该题材不适用，组装时跳过）。style_profile 空则用默认风格提示。
    """

    genre: str
    core_appeal: str
    protagonist: str
    main_conflict: str
    world_rules: str
    overall_tone: str
    opening_hook: str
    power_system: str | None = None
    golden_finger: str | None = None
    romance_line: str | None = None
    faction_landscape: str | None = None
    style_profile: str | None = None


# 12 字段的中文标签（组装写作任务书用；对齐设定圣经语义）。
_FIELD_LABELS: list[tuple[str, str]] = [
    ("genre", "题材"),
    ("core_appeal", "核心吸引力"),
    ("protagonist", "主角"),
    ("main_conflict", "主要冲突"),
    ("world_rules", "关键世界规则"),
    ("overall_tone", "整体气质"),
    ("opening_hook", "开篇钩子"),
    ("power_system", "力量体系"),
    ("golden_finger", "金手指"),
    ("romance_line", "感情线"),
    ("faction_landscape", "势力格局"),
]


# ---------------------------------------------------------------------------
# dev 造的测试设定（--from-samples 用，零 DB 依赖）。一份完整可写的广谱网文向设定，
# 供装置跑通；正式门禁决策用 --from-project 喂真材料。
# ---------------------------------------------------------------------------
TEST_BIBLE = BibleFields(
    genre="都市悬疑",
    core_appeal="一个能听见旧物记忆的当铺老板，被卷入一桩跨越三十年的旧案；卖点是每件当品背后的人生切片，读者体验是抽丝剥茧的解谜快感与人情况味。",
    protagonist="沈砚，三十岁，城郊老当铺继承人；核心欲望是查清养父失踪真相，致命缺陷是不敢直面自己也曾抛弃过一个人。",
    main_conflict="沈砚追查一枚反复典当又赎回的旧怀表，牵出养父当年经手的一桩灭门案；反派是当年的办案警官，与沈砚共享'守护真相'的信念却走向了掩盖。",
    world_rules="世界规模限于一座南方旧城；硬约束是沈砚只能听见'被珍视过的旧物'的记忆，一次读取会让他短暂失去自己的一段记忆作为代价。",
    overall_tone="潮湿、克制、旧时光的怅惘，悬疑外壳下是人与人错过的遗憾。",
    opening_hook="打烊前最后一个客人，用一枚停在三点十七分的怀表，换走了柜台里那台谁都不肯赎的旧收音机。",
    power_system=None,
    golden_finger="听见旧物记忆的能力（有记忆代价的金手指）",
    romance_line=None,
    faction_landscape=None,
    style_profile=None,  # 运行时由样本库现抽填入
)


# ---------------------------------------------------------------------------
# 写作任务书组装（AC1 核心：组装一次、两侧共用）。纯函数、可单测。
# ---------------------------------------------------------------------------

# 临时去 AI 味约束段（写进 drafter 任务书，让生成方主动规避——轴 B 事后再客观校验）。
# clean-room 自编，借 polish-guide「去翻译腔/去万能金句」思路，不复制 GPL 源码（NFR7）。
_AI_TASTE_CONSTRAINT = """写作时严格规避"AI 腔/翻译腔"：
- 不用空洞万能的修饰（如"淡淡的""缓缓地""某种莫名的情绪""内心深处"）。
- 不写格言式升华结尾、不强行排比、不用"不是 X 而是 Y"的伪深刻对仗。
- 用具体的动作、场景、细节说话，不用抽象名词堆砌情绪。
- 说人话，像成熟网文作者的自然叙事，不端着、不书面僵硬。"""

_DEFAULT_STYLE_HINT = "（未锚定具体文风，用干净、克制、有画面感的自然叙事。）"


def _format_bible(fields: BibleFields) -> str:
    """把 12 字段格式化为写作任务书里的设定段（空的特化字段跳过、不出现空行标签）。"""
    lines: list[str] = []
    data = asdict(fields)
    for key, label in _FIELD_LABELS:
        value = data.get(key)
        if value:  # 空串 / None 一律跳过（特化字段不适用时不列）
            lines.append(f"- {label}：{value}")
    return "\n".join(lines)


def build_writing_brief(
    fields: BibleFields, *, chapter_idea: str | None = None
) -> tuple[str, str]:
    """组装唯一一份写作任务书（drafter 消息），返回 (system, user)。

    这是 4.2 完整 context-agent 的最小前身（AC6：只为盲测产样，不落 orchestration/）。
    style_profile 空则用默认风格提示；chapter_idea 可空。**两侧生成方共用本函数产出的同一
    份消息**（AC1 逐字节一致的地基）。
    """
    style = (fields.style_profile or "").strip() or _DEFAULT_STYLE_HINT
    bible_block = _format_bible(fields)
    system = (
        "你是一位成熟的网文作者，正在为一部小说写它的第一章正文。"
        "请严格贴合给定的故事设定与文风锚点来写，写出能直接放进作品的成稿正文。\n\n"
        f"【文风锚点】请贴着这个味道写：\n{style}\n\n"
        f"【去 AI 味要求】\n{_AI_TASTE_CONSTRAINT}\n\n"
        "【输出要求】只输出第一章正文本身，不要标题、不要小标题、不要任何解释或旁白，"
        "篇幅约 1200–2000 字。"
    )
    idea_block = ""
    if chapter_idea and chapter_idea.strip():
        idea_block = f"\n\n【本章想法】{chapter_idea.strip()}"
    user = f"【故事设定】\n{bible_block}{idea_block}\n\n请开始写第一章正文。"
    return system, user


def make_anonymous_id() -> str:
    """生成匿名样本 id（无生成方线索，AC3）。短随机 hex，文件名友好。"""
    return secrets.token_hex(6)


# ---------------------------------------------------------------------------
# 样本落盘 + _key 结构（IO；匿名严格性靠此处保证）
# ---------------------------------------------------------------------------
@dataclass
class SampleRecord:
    """一篇样本的 _key.json 记录（评分阶段不可见）：匿名 id + 生成方 + 轴 B 统计。"""

    anon_id: str
    generator: str  # "deepseek" / "claude"
    model: str  # 具体档位 / "claude-code-subagent"
    axis_b: dict  # analyze_axis_b 结果（asdict）
    char_count: int


def write_sample(anon_id: str, content: str) -> Path:
    """把一篇正文写到 samples/<anon_id>.md（仅正文，无任何生成方标识，AC3）。"""
    _SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    path = _SAMPLES_DIR / f"{anon_id}.md"
    path.write_text(content, encoding="utf-8")
    return path


def build_sample_record(anon_id: str, generator: str, model: str, content: str) -> SampleRecord:
    """对一篇正文算轴 B 统计并组装 _key 记录（生成阶段自动做，AC2 轴 B 客观）。"""
    stats = analyze_axis_b(content)
    return SampleRecord(
        anon_id=anon_id,
        generator=generator,
        model=model,
        axis_b=asdict(stats),
        char_count=stats.char_count,
    )


# ---------------------------------------------------------------------------
# _key.json 读写（Claude 侧 Task 3 会追加记录，故支持读-合并-写）
# ---------------------------------------------------------------------------
def load_key() -> list[dict]:
    """读已有 _key.json（不存在返回空列表）。供 Claude 侧并入、judge 解匿名。"""
    if _KEY_PATH.exists():
        return json.loads(_KEY_PATH.read_text(encoding="utf-8"))
    return []


def save_key(records: list[dict]) -> None:
    """写 _key.json（生成方归属 + 轴 B 统计；评分阶段不可见）。"""
    _DOCS_DIR.mkdir(parents=True, exist_ok=True)
    _KEY_PATH.write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def append_records(new_records: list[SampleRecord]) -> list[dict]:
    """把新样本记录并入 _key.json（读-合并-写），返回合并后全量。

    Claude 侧（Task 3）生成后调本函数把自己 N 篇并入 DeepSeek 侧已写的 _key，最终一份含两侧。
    """
    existing = load_key()
    existing.extend(asdict(r) for r in new_records)
    save_key(existing)
    return existing


def write_brief(system: str, user: str) -> None:
    """把唯一写作任务书落盘 writing-brief.md（AC1：两侧共用同一份 + 留档 AC5）。"""
    _DOCS_DIR.mkdir(parents=True, exist_ok=True)
    content = (
        f"# 盲测写作任务书（Story 4.1，两侧生成方共用同一份）\n\n"
        f"> 临时词表版本：{LEXICON_VERSION}\n"
        f"> **AC1 硬约束**：DeepSeek 侧与 Claude 侧必须喂这份逐字节一致的任务书，"
        f"唯一变量是生成方。\n\n"
        f"## System\n\n```\n{system}\n```\n\n## User\n\n```\n{user}\n```\n"
    )
    _BRIEF_PATH.write_text(content, encoding="utf-8")


def write_scoring_sheet(anon_ids: list[str]) -> None:
    """生成空白打分记录表（AC3：只列匿名 id + 空轴 A 列，无生成方列）。

    创始人逐篇盲评，在'轴A评分'列填 0（不像）/ 1（出戏）/ 2（像）。judge 读此表 + _key 解匿名。
    """
    _DOCS_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 盲评打分表（Story 4.1 轴 A 风格贴合）",
        "",
        "> 逐篇盲评：读 `samples/<id>.md`，在「轴A评分」列填分——**0=不像 / 1=出戏 / 2=像**。",
        "> 你不知道每篇出自哪个生成方（这是盲评前提）。填完运行 judge_blind_test.py 解匿名判定。",
        "",
        "| 样本 id | 轴A评分(0/1/2) |",
        "|---|---|",
    ]
    for anon_id in anon_ids:
        lines.append(f"| {anon_id} |  |")
    _SCORING_SHEET_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# 真实 API：样本库现抽 style_profile（--from-samples）——复用 style_anchor 的 prompt/解析
# ---------------------------------------------------------------------------
async def extract_style_from_sample(sample_id: str) -> str:
    """用预置样本库某样本原文，经 DeepSeek 现抽 style_profile 五维文本（零 DB 依赖）。

    复用 src 的 style_anchor_agent 纯函数（prompt 组装 + 五维解析），但**不走 DB upsert**
    ——盲测装置只要 style_profile 文本喂写作任务书，不落库。DeepSeek 直接构造（非
    MeteredProvider，盲测不记账）。
    """
    from muse.core.settings import get_settings
    from muse.providers.deepseek import DeepSeekProvider
    from muse.services import style_anchor_agent

    settings = get_settings()
    if not settings.deepseek_api_key:
        raise SystemExit("✗ 未配置 DEEPSEEK_API_KEY，无法抽取 style_profile。")
    sample = style_anchor_agent._SAMPLE_BY_ID.get(sample_id)
    if sample is None:
        avail = ", ".join(s.id for s in style_anchor_agent.STYLE_SAMPLE_LIBRARY)
        raise SystemExit(f"✗ 未知样本 id：{sample_id}。可选：{avail}")
    provider = DeepSeekProvider(
        api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url
    )
    result = await provider.chat(
        style_anchor_agent._build_messages(sample.text),
        model=settings.deepseek_model_fast,
        max_tokens=style_anchor_agent._MAX_TOKENS,
    )
    profile = style_anchor_agent._parse_style_profile(result.content)
    if not profile.strip():
        raise SystemExit("✗ style_profile 抽取为空，请重试。")
    return profile


async def load_bible_from_project(project_id: str) -> BibleFields:
    """从真实 story_bible confirmed 行读 12 字段 + style_profile（--from-project）。

    走独立 async session（仿 style_anchor_agent）。仅读 status='confirmed' 行——确认后的
    只读设定圣经才是「唯一创作依据」（story_bible.py:99）。无 confirmed 行则报错提示先确认设定。
    """
    from sqlalchemy import select

    from muse.core.db import async_session_maker
    from muse.models.story_bible import StoryBible

    async with async_session_maker() as session:
        row = (
            await session.execute(
                select(StoryBible).where(
                    StoryBible.project_id == uuid.UUID(project_id),
                    StoryBible.status == "confirmed",
                )
            )
        ).scalar_one_or_none()
    if row is None:
        raise SystemExit(
            f"✗ 作品 {project_id} 无 confirmed 设定圣经；请先确认设定，或用 --from-samples。"
        )
    return BibleFields(
        genre=row.genre,
        core_appeal=row.core_appeal,
        protagonist=row.protagonist,
        main_conflict=row.main_conflict,
        world_rules=row.world_rules,
        overall_tone=row.overall_tone,
        opening_hook=row.opening_hook,
        power_system=row.power_system,
        golden_finger=row.golden_finger,
        romance_line=row.romance_line,
        faction_landscape=row.faction_landscape,
        style_profile=row.style_profile,
    )


async def generate_deepseek_samples(
    system: str, user: str, n: int
) -> list[tuple[str, str, str]]:
    """DeepSeek 侧生成 N 篇：返回 [(content, model, 匿名id), ...]。真实 API、思考档。

    直接构造 DeepSeekProvider（非 MeteredProvider，盲测不走托管记账）。逐篇打印
    token/耗时；key 缺失明确报错（不静默跳过——盲测没 key 跑不了）。
    """
    from muse.core.settings import get_settings
    from muse.providers.deepseek import DeepSeekProvider, compute_cost

    settings = get_settings()
    if not settings.deepseek_api_key:
        raise SystemExit("✗ 未配置 DEEPSEEK_API_KEY，盲测 DeepSeek 侧无法生成。")
    provider = DeepSeekProvider(
        api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url
    )
    model = settings.deepseek_model_thinking
    out: list[tuple[str, str, str]] = []
    print(f"\n[DeepSeek] 用 {model} 生成 {n} 篇（章节体量）…")
    for i in range(n):
        t0 = time.time()
        result = await provider.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            model=model,
            max_tokens=_GEN_MAX_TOKENS,
        )
        dt = time.time() - t0
        cost = compute_cost(model, result.prompt_tokens, result.completion_tokens)
        anon = make_anonymous_id()
        out.append((result.content, model, anon))
        print(
            f"  篇 {i + 1}/{n} → {anon}.md | {dt:.1f}s | "
            f"tokens {result.total_tokens} | 成本 ¥{cost}"
        )
    return out


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Story 4.1 盲测：DeepSeek 侧生成对照样本")
    parser.add_argument(
        "--n", type=int, default=_DEFAULT_N, help=f"每侧生成篇数（默认 {_DEFAULT_N}）"
    )
    parser.add_argument(
        "--sample", type=str, default="cold-rain",
        help="--from-samples 时用的预置文风样本 id（cold-rain/warm-dusk/sharp-first）",
    )
    parser.add_argument(
        "--from-project", type=str, default=None, metavar="UUID",
        help="从真实作品 confirmed 设定读输入（默认走 --from-samples 零依赖）",
    )
    parser.add_argument("--idea", type=str, default=None, help="可选：本章想法")
    args = parser.parse_args()
    if args.n < 1:
        parser.error("--n 必须 >= 1")
    return args


async def _amain(args: argparse.Namespace) -> int:
    # 1. 组装设定输入（双来源）。
    if args.from_project:
        print(f"[输入] 从作品 {args.from_project} 读 confirmed 设定 + style_profile …")
        fields = await load_bible_from_project(args.from_project)
    else:
        print(f"[输入] --from-samples：测试设定 + 样本库 {args.sample!r} 现抽 style_profile …")
        style_profile = await extract_style_from_sample(args.sample)
        fields = BibleFields(**{**asdict(TEST_BIBLE), "style_profile": style_profile})
        print(f"  style_profile 抽取完成：\n{style_profile}")

    # 2. 组装唯一写作任务书（AC1）+ 落盘供两侧共用。
    system, user = build_writing_brief(fields, chapter_idea=args.idea)
    write_brief(system, user)
    print(f"\n[写作任务书] 已落盘 {_BRIEF_PATH}（Claude 侧 Task 3 读同一份）")

    # 3. DeepSeek 侧生成 N 篇 + 匿名落盘 + 记账轴 B → _key。
    samples = await generate_deepseek_samples(system, user, args.n)
    records: list[SampleRecord] = []
    for content, model, anon in samples:
        write_sample(anon, content)
        records.append(build_sample_record(anon, "deepseek", model, content))
    all_records = append_records(records)
    print(f"\n[落盘] DeepSeek {len(records)} 篇 → {_SAMPLES_DIR}，_key 现共 {len(all_records)} 条")

    print(
        "\n✓ DeepSeek 侧完成。下一步（Task 3）：由 dev 会话读 "
        f"{_BRIEF_PATH.name}，开子 agent 生成 Claude 侧 {args.n} 篇并入 _key；"
        "再运行本包生成打分表、创始人盲评、judge 判定。"
    )
    return 0


def main() -> int:
    args = _parse_args()
    return asyncio.run(_amain(args))


if __name__ == "__main__":
    sys.exit(main())
