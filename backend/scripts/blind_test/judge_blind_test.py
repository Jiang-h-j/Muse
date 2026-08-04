"""盲测判定聚合 + 门禁结论 + 留档（Story 4.1 Task 5）。

读创始人填好的 scoring-sheet.md（轴 A 分）+ _key.json（解匿名 + 轴 B 统计），按生成方聚合，
按 NFR1 三条判据判定 DeepSeek 是否达及格线，输出 GATE 结论 + report.md 留档（AC2/AC4/AC5）。

**判据（AC2，三条同时满足 = 及格线以上放行）**：
① 轴 A 风格贴合：判「像」（分数 >= 1 且多为 2）篇数比例 >= 2/3。
② 轴 B 重度句式套路总数 = 0。
③ 轴 B 黑名单词频 <= 锚定样本自身 1.5 倍（无基准兜底 <= 3 词/千字）。

**判像口径**（AC2「≥1 分且多为 2 分」）：单篇分 >= 1 记为候选像；「多为 2 分」在**群体层面**
兑现——判像集合里 2 分占多数（> 半）才算风格真站住，否则判像质量存疑按不达标处理。

Claude 侧同样跑一遍判定作**参照上界对照**（看差距），非门禁条件——门禁只卡 DeepSeek。

运行：
    cd backend && uv run python -m scripts.blind_test.judge_blind_test
    cd backend && uv run python -m scripts.blind_test.judge_blind_test --baseline-per-kchar 2.0
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# 统一 blind_test.* 绝对 import：直接跑本文件时自注入 scripts/ 到 sys.path，pytest 下由
# conftest 注入（同路径幂等）。与 run_blind_test.py 同款引导。
_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from blind_test.ai_taste_lexicon_temp import LEXICON_VERSION  # noqa: E402
from blind_test.run_blind_test import (  # noqa: E402
    _BRIEF_PATH,
    _DOCS_DIR,
    _KEY_PATH,
    _SCORING_SHEET_PATH,
    load_key,
)

_REPORT_PATH = _DOCS_DIR / "report.md"

# 轴 B 硬底线（AC2③）：无锚定样本基准时的兜底词频上限（词/千字）。
_FALLBACK_PER_KCHAR = 3.0
# 判像倍数（AC2③）：黑名单词频须 <= 锚定样本自身的这个倍数。
_BASELINE_MULTIPLIER = 1.5
# 判像比例门槛（AC2①）：判像篇数 / 总篇数 >= 此值。
_PASS_RATIO = 2 / 3


# ---------------------------------------------------------------------------
# 打分表解析（轴 A）
# ---------------------------------------------------------------------------
def parse_scoring_sheet(text: str) -> dict[str, int]:
    """解析 scoring-sheet.md 的表格，返回 {匿名 id: 轴A分}。

    只收「| id | 分 |」形态的数据行（分为 0/1/2）；表头/分隔行/未填分的行跳过。
    未填分的样本视为「未评」——由调用方决定是否报缺失（判定要求全评）。
    """
    scores: dict[str, int] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        anon_id, raw_score = cells[0], cells[1]
        # 跳过表头（「样本 id」）与分隔行（---）。
        if anon_id in ("样本 id", "") or set(anon_id) <= set("-: "):
            continue
        m = re.fullmatch(r"[012]", raw_score)
        if m:
            scores[anon_id] = int(raw_score)
    return scores


# ---------------------------------------------------------------------------
# 聚合 + 判定
# ---------------------------------------------------------------------------
@dataclass
class GeneratorVerdict:
    """单个生成方的三条判据结果。"""

    generator: str
    total: int
    # 轴 A
    liked_count: int  # 判像（分 >= 1）篇数
    liked_ratio: float
    two_count: int  # 判像里 2 分篇数
    axis_a_pass: bool
    # 轴 B
    pattern_total: int
    axis_b_pattern_pass: bool
    max_per_kchar: float  # 该生成方样本里最高词频（最严篇）
    avg_per_kchar: float
    baseline_limit: float
    axis_b_lexicon_pass: bool
    # 综合
    passed: bool  # 三条同时满足
    notes: list[str] = field(default_factory=list)


def judge_generator(
    generator: str,
    records: list[dict],
    scores: dict[str, int],
    *,
    baseline_per_kchar: float,
) -> GeneratorVerdict:
    """对一个生成方的样本聚合三条判据。

    records：该生成方的 _key 记录（含 axis_b）；scores：全体轴 A 分（按 anon_id 取）。
    baseline_per_kchar：锚定样本自身词频基准（无则传兜底 _FALLBACK_PER_KCHAR）。
    """
    total = len(records)
    notes: list[str] = []

    # 轴 A：判像（分 >= 1）+「多为 2 分」（判像集合里 2 分占多数）。
    liked = [r for r in records if scores.get(r["anon_id"], 0) >= 1]
    liked_count = len(liked)
    two_count = sum(1 for r in liked if scores.get(r["anon_id"], 0) == 2)
    liked_ratio = (liked_count / total) if total else 0.0
    # 「多为 2 分」：判像里 2 分须占多数（> 半），否则风格质量存疑。
    mostly_two = two_count * 2 > liked_count if liked_count else False
    axis_a_pass = liked_ratio >= _PASS_RATIO and mostly_two
    if liked_count and not mostly_two:
        notes.append(
            f"判像 {liked_count} 篇但仅 {two_count} 篇给 2 分（不足多数），"
            "风格贴合质量存疑，轴 A 不达标"
        )

    # 轴 B①：重度句式套路总数 = 0。
    pattern_total = sum(r["axis_b"]["pattern_total"] for r in records)
    axis_b_pattern_pass = pattern_total == 0

    # 轴 B②：黑名单词频 <= 基准 1.5 倍。用该生成方最高词频篇做最严判定（任一篇超标即不达）。
    per_kchars = [r["axis_b"]["blacklist_per_kchar"] for r in records]
    max_per_kchar = max(per_kchars) if per_kchars else 0.0
    avg_per_kchar = (sum(per_kchars) / len(per_kchars)) if per_kchars else 0.0
    baseline_limit = round(baseline_per_kchar * _BASELINE_MULTIPLIER, 2)
    axis_b_lexicon_pass = max_per_kchar <= baseline_limit

    passed = axis_a_pass and axis_b_pattern_pass and axis_b_lexicon_pass

    return GeneratorVerdict(
        generator=generator,
        total=total,
        liked_count=liked_count,
        liked_ratio=round(liked_ratio, 3),
        two_count=two_count,
        axis_a_pass=axis_a_pass,
        pattern_total=pattern_total,
        axis_b_pattern_pass=axis_b_pattern_pass,
        max_per_kchar=max_per_kchar,
        avg_per_kchar=round(avg_per_kchar, 2),
        baseline_limit=baseline_limit,
        axis_b_lexicon_pass=axis_b_lexicon_pass,
        passed=passed,
        notes=notes,
    )


def group_by_generator(records: list[dict]) -> dict[str, list[dict]]:
    """按 generator 分组 _key 记录。"""
    groups: dict[str, list[dict]] = {}
    for r in records:
        groups.setdefault(r["generator"], []).append(r)
    return groups


# ---------------------------------------------------------------------------
# 留档报告 + GATE 结论（AC5）
# ---------------------------------------------------------------------------
def _verdict_block(v: GeneratorVerdict) -> str:
    """单生成方判定的报告段（三条逐条列 PASS/FAIL + 数据）。"""
    def mark(ok: bool) -> str:
        return "✅ PASS" if ok else "❌ FAIL"

    lines = [
        f"### 生成方：{v.generator}（{v.total} 篇）",
        "",
        f"- **轴 A 风格贴合**：{mark(v.axis_a_pass)} — 判像 {v.liked_count}/{v.total} "
        f"（比例 {v.liked_ratio:.0%}，门槛 ≥ 2/3），其中 2 分 {v.two_count} 篇",
        f"- **轴 B 句式套路**：{mark(v.axis_b_pattern_pass)} — "
        f"重度套路总数 {v.pattern_total}（门槛 = 0）",
        f"- **轴 B 黑名单词频**：{mark(v.axis_b_lexicon_pass)} — 最高 {v.max_per_kchar} 词/千字"
        f"（均值 {v.avg_per_kchar}，上限 {v.baseline_limit} = 基准×1.5）",
        "",
        f"**综合：{'达及格线' if v.passed else '未达及格线'}**",
    ]
    if v.notes:
        lines.append("")
        lines.extend(f"> ⚠️ {n}" for n in v.notes)
    return "\n".join(lines)


def build_report(
    ds_verdict: GeneratorVerdict,
    other_verdicts: list[GeneratorVerdict],
    *,
    gate_pass: bool,
    style_profile: str,
    baseline_per_kchar: float,
    baseline_is_fallback: bool,
) -> str:
    """组装 report.md 全文（AC5 完整留档）。顶部 GATE 机读结论行（AC4，供 4.4 前置检查）。"""
    gate = "PASS" if gate_pass else "BLOCK"
    brief_text = (
        _BRIEF_PATH.read_text(encoding="utf-8")
        if _BRIEF_PATH.exists()
        else "（未找到 writing-brief.md）"
    )
    baseline_note = (
        f"锚定样本自身词频基准 = {baseline_per_kchar} 词/千字"
        + ("（**无样本基准，兜底 ≤ 3 词/千字**）" if baseline_is_fallback else "")
    )
    parts = [
        "# 盲测门禁报告（Story 4.1，Claude-vs-DeepSeek）",
        "",
        f"**GATE: {gate}**  ·  临时词表 {LEXICON_VERSION}",
        "",
        (
            "> GATE=PASS 解锁 Story 4.4 正文接入；GATE=BLOCK 阻断 4.4，"
            "须调整方案（调 prompt / 调词表 / 评估换模型）重测。"
        ),
        (
            "> **Claude 侧为参照上界对照（非门禁条件）**，门禁只卡 DeepSeek。"
            "Claude 侧参照系 = Claude Code 当前模型档，非固定 Anthropic API 档。"
        ),
        "",
        "## 门禁判定（DeepSeek）",
        "",
        _verdict_block(ds_verdict),
        "",
        "## 参照对照（Claude 侧，非门禁）",
        "",
    ]
    if other_verdicts:
        parts.extend(_verdict_block(v) + "\n" for v in other_verdicts)
    else:
        parts.append("（无 Claude 侧样本——Task 3 未生成或未并入 _key）\n")
    parts.extend(
        [
            "## 判据说明（NFR1）",
            "",
            "及格线 = 三条同时满足：① 轴 A 判像 ≥ 2/3 且多为 2 分；② 重度句式套路 = 0；"
            f"③ 黑名单词频 ≤ 基准×1.5。{baseline_note}。",
            "",
            "## 所用 style_profile",
            "",
            f"```\n{style_profile}\n```",
            "",
            "## 写作任务书（两侧共用，AC1）",
            "",
            brief_text,
        ]
    )
    return "\n".join(parts)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Story 4.1 盲测判定 + 门禁结论 + 留档")
    parser.add_argument(
        "--baseline-per-kchar", type=float, default=None,
        help="锚定样本自身黑名单词频基准（词/千字）；不给则用兜底 3.0",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    if not _KEY_PATH.exists():
        print(f"✗ 找不到 {_KEY_PATH}，请先运行 run_blind_test 生成样本。")
        return 1
    if not _SCORING_SHEET_PATH.exists():
        print(f"✗ 找不到 {_SCORING_SHEET_PATH}，请先生成打分表并由创始人填分。")
        return 1

    records = load_key()
    scores = parse_scoring_sheet(_SCORING_SHEET_PATH.read_text(encoding="utf-8"))

    # 校验：所有样本都已评分（判定要求全评，未评则中止提示）。
    all_ids = {r["anon_id"] for r in records}
    scored_ids = set(scores)
    missing = all_ids - scored_ids
    if missing:
        print(f"✗ 还有 {len(missing)} 篇未评分：{', '.join(sorted(missing))}")
        print("  请在 scoring-sheet.md 填完轴 A 分（0/1/2）再运行。")
        return 1

    # 基准词频（AC2③）：命令行给则用之，否则兜底 3.0。
    baseline_is_fallback = args.baseline_per_kchar is None
    baseline = _FALLBACK_PER_KCHAR if baseline_is_fallback else args.baseline_per_kchar

    groups = group_by_generator(records)
    if "deepseek" not in groups:
        print("✗ _key 无 deepseek 样本，无法判定门禁。")
        return 1

    ds_verdict = judge_generator(
        "deepseek", groups["deepseek"], scores, baseline_per_kchar=baseline
    )
    other_verdicts = [
        judge_generator(g, recs, scores, baseline_per_kchar=baseline)
        for g, recs in groups.items()
        if g != "deepseek"
    ]

    gate_pass = ds_verdict.passed

    # style_profile：从写作任务书里已含（brief 落盘时写入 system），报告单列一份便于查阅。
    # 这里从 _key 无法拿 profile 原文，故留档报告用 brief 全文承载；单列段落用占位说明。
    style_profile = "（见下方「写作任务书」段的【文风锚点】部分）"

    report = build_report(
        ds_verdict, other_verdicts,
        gate_pass=gate_pass, style_profile=style_profile,
        baseline_per_kchar=baseline, baseline_is_fallback=baseline_is_fallback,
    )
    _REPORT_PATH.write_text(report, encoding="utf-8")

    print("=" * 60)
    print(f"GATE: {'PASS ✅ 解锁 4.4' if gate_pass else 'BLOCK ❌ 阻断 4.4'}")
    print("=" * 60)
    print(f"DeepSeek：轴A {'✓' if ds_verdict.axis_a_pass else '✗'}"
          f"（判像 {ds_verdict.liked_count}/{ds_verdict.total}）| "
          f"套路 {'✓' if ds_verdict.axis_b_pattern_pass else '✗'}({ds_verdict.pattern_total}) | "
          f"词频 {'✓' if ds_verdict.axis_b_lexicon_pass else '✗'}"
          f"({ds_verdict.max_per_kchar}≤{ds_verdict.baseline_limit})")
    for v in other_verdicts:
        print(f"{v.generator}（参照）：判像 {v.liked_count}/{v.total} | 套路 {v.pattern_total} | "
              f"词频峰 {v.max_per_kchar}")
    print(f"\n留档：{_REPORT_PATH}")
    if not gate_pass:
        print("\n⚠️ 门禁未通过——报告已记不达线的轴与差距，须调整方案重测（不放行 4.4）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
