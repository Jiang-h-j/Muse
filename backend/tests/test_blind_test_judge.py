"""Story 4.1 Task 5 验证：盲测判定聚合 + 门禁结论 + 留档（离线纯逻辑，CI 必过）。

覆盖：
- parse_scoring_sheet：解析轴 A 分、跳过表头/分隔/未填行
- judge_generator 三条判据：全过 PASS、轴A判像不足、判像但2分不占多数、套路非0、词频超标
- group_by_generator：按生成方分组
- build_report：GATE 行、DeepSeek 判定 + Claude 参照、Claude 参照系说明
判定是纯函数、无 IO；report 落盘用 monkeypatch 到 tmp。
"""


from blind_test import judge_blind_test as jbt
from blind_test.judge_blind_test import (
    GeneratorVerdict,
    build_report,
    group_by_generator,
    judge_generator,
    parse_scoring_sheet,
)


def _rec(anon_id: str, generator: str, *, per_kchar: float = 0.0, patterns: int = 0) -> dict:
    """造一条 _key 记录（含 axis_b 统计）。"""
    return {
        "anon_id": anon_id,
        "generator": generator,
        "model": "m",
        "char_count": 1500,
        "axis_b": {
            "char_count": 1500,
            "blacklist_total": int(per_kchar * 1.5),
            "blacklist_per_kchar": per_kchar,
            "blacklist_hits": [],
            "pattern_total": patterns,
            "pattern_hits": [],
        },
    }


# ========== parse_scoring_sheet ==========


def test_parse_scoring_sheet_basic() -> None:
    sheet = """# 打分表
| 样本 id | 轴A评分(0/1/2) |
|---|---|
| aaa | 2 |
| bbb | 0 |
| ccc | 1 |
"""
    scores = parse_scoring_sheet(sheet)
    assert scores == {"aaa": 2, "bbb": 0, "ccc": 1}


def test_parse_skips_unfilled_and_invalid() -> None:
    # 未填分（空）、非法分（3/文字）都跳过，不进 scores。
    sheet = """| 样本 id | 轴A评分 |
|---|---|
| aaa | 2 |
| bbb |  |
| ccc | 3 |
| ddd | x |
"""
    scores = parse_scoring_sheet(sheet)
    assert scores == {"aaa": 2}


# ========== judge_generator 三条判据 ==========


def test_verdict_all_pass() -> None:
    # 6 篇：全给 2 分（判像 6/6，全 2 分）、无套路、词频 0 → 三条全过。
    records = [_rec(f"d{i}", "deepseek", per_kchar=1.0, patterns=0) for i in range(6)]
    scores = {f"d{i}": 2 for i in range(6)}
    v = judge_generator("deepseek", records, scores, baseline_per_kchar=2.0)
    assert v.axis_a_pass  # 判像 6/6 ≥ 2/3，2 分占多数
    assert v.axis_b_pattern_pass  # 套路 0
    assert v.axis_b_lexicon_pass  # 1.0 ≤ 2.0×1.5=3.0
    assert v.passed


def test_verdict_axis_a_ratio_insufficient() -> None:
    # 6 篇里仅 3 篇判像（3/6=0.5 < 2/3）→ 轴 A 不达标 → 综合 FAIL。
    records = [_rec(f"d{i}", "deepseek", per_kchar=0.5) for i in range(6)]
    scores = {"d0": 2, "d1": 2, "d2": 2, "d3": 0, "d4": 0, "d5": 0}
    v = judge_generator("deepseek", records, scores, baseline_per_kchar=2.0)
    assert not v.axis_a_pass
    assert not v.passed


def test_verdict_liked_but_not_mostly_two() -> None:
    # 判像比例够（5/6）但大多是 1 分（出戏）、仅 1 篇 2 分 → 2 分不占多数 → 轴 A 不达标。
    records = [_rec(f"d{i}", "deepseek", per_kchar=0.5) for i in range(6)]
    scores = {"d0": 2, "d1": 1, "d2": 1, "d3": 1, "d4": 1, "d5": 0}
    v = judge_generator("deepseek", records, scores, baseline_per_kchar=2.0)
    assert v.liked_count == 5  # 分 >= 1
    assert v.two_count == 1
    assert not v.axis_a_pass  # 2 分不占多数
    assert v.notes  # 记了质量存疑
    assert not v.passed


def test_verdict_pattern_nonzero_blocks() -> None:
    # 轴 A 全过、词频 OK，但有 1 处重度套路 → 轴 B 套路不达标 → 综合 FAIL（硬底线）。
    records = [_rec(f"d{i}", "deepseek", per_kchar=0.5, patterns=0) for i in range(6)]
    records[0]["axis_b"]["pattern_total"] = 1
    scores = {f"d{i}": 2 for i in range(6)}
    v = judge_generator("deepseek", records, scores, baseline_per_kchar=2.0)
    assert v.axis_a_pass
    assert v.pattern_total == 1
    assert not v.axis_b_pattern_pass
    assert not v.passed


def test_verdict_lexicon_over_baseline_blocks() -> None:
    # 某篇词频 4.0 > 基准 2.0×1.5=3.0 → 轴 B 词频不达标（取最高篇最严判） → FAIL。
    records = [_rec(f"d{i}", "deepseek", per_kchar=1.0) for i in range(5)]
    records.append(_rec("d5", "deepseek", per_kchar=4.0))
    scores = {f"d{i}": 2 for i in range(6)}
    v = judge_generator("deepseek", records, scores, baseline_per_kchar=2.0)
    assert v.max_per_kchar == 4.0
    assert v.baseline_limit == 3.0
    assert not v.axis_b_lexicon_pass
    assert not v.passed


def test_verdict_fallback_baseline() -> None:
    # 无样本基准兜底 3.0：词频 4.0 > 3.0×1.5=4.5? 否 → 4.0 ≤ 4.5 达标。
    records = [_rec(f"d{i}", "deepseek", per_kchar=4.0) for i in range(6)]
    scores = {f"d{i}": 2 for i in range(6)}
    v = judge_generator("deepseek", records, scores, baseline_per_kchar=3.0)
    assert v.baseline_limit == 4.5
    assert v.axis_b_lexicon_pass


# ========== group_by_generator ==========


def test_group_by_generator() -> None:
    records = [
        _rec("d1", "deepseek"),
        _rec("c1", "claude"),
        _rec("d2", "deepseek"),
    ]
    groups = group_by_generator(records)
    assert set(groups) == {"deepseek", "claude"}
    assert len(groups["deepseek"]) == 2
    assert len(groups["claude"]) == 1


# ========== build_report ==========


def _mk_verdict(gen: str, *, passed: bool) -> GeneratorVerdict:
    return GeneratorVerdict(
        generator=gen, total=6, liked_count=6 if passed else 2, liked_ratio=1.0 if passed else 0.33,
        two_count=6 if passed else 1, axis_a_pass=passed, pattern_total=0,
        axis_b_pattern_pass=True, max_per_kchar=1.0, avg_per_kchar=0.8,
        baseline_limit=3.0, axis_b_lexicon_pass=True, passed=passed,
    )


def test_report_gate_pass(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(jbt, "_REPORT_PATH", tmp_path / "report.md")
    monkeypatch.setattr(jbt, "_BRIEF_PATH", tmp_path / "no-brief.md")
    ds = _mk_verdict("deepseek", passed=True)
    cl = _mk_verdict("claude", passed=True)
    report = build_report(
        ds, [cl], gate_pass=True, style_profile="人称：第一人称",
        baseline_per_kchar=2.0, baseline_is_fallback=False,
    )
    assert "GATE: PASS" in report
    assert "解锁 Story 4.4" in report
    assert "Claude Code 当前模型档" in report  # 参照系说明


def test_report_gate_block(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(jbt, "_BRIEF_PATH", tmp_path / "no-brief.md")
    ds = _mk_verdict("deepseek", passed=False)
    report = build_report(
        ds, [], gate_pass=False, style_profile="x",
        baseline_per_kchar=3.0, baseline_is_fallback=True,
    )
    assert "GATE: BLOCK" in report
    assert "阻断" in report
    assert "兜底" in report  # 兜底基准说明
