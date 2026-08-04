"""Story 4.1 Task 1 验证：临时去 AI 味词表 + 轴 B 自动统计（离线纯逻辑，CI 必过）。

覆盖：
- 黑名单词频：命中计数、千字归一、逐词明细降序、干净文本零命中
- 句式套路：四类规则各自命中、干净文本零命中、命中含原文片段供复核
- 边界：空文本防除零、纯空白文本
装置纯函数、无 IO/无 DB/无真实 API，属 CI 必过的离线单元。
"""

from blind_test.ai_taste_lexicon_temp import (
    BLACKLIST_WORDS,
    LEXICON_VERSION,
    analyze_axis_b,
    count_blacklist,
    count_patterns,
)

# ========== 黑名单词频 ==========


def test_blacklist_counts_hits_and_per_kchar() -> None:
    # 构造含黑名单词的文本：「淡淡的」「不由得」各出现、其余为正常字符凑字数。
    # 取 BLACKLIST_WORDS 里确定存在的两个词做断言（避免硬编码依赖词表内部顺序）。
    assert "淡淡的" in BLACKLIST_WORDS
    assert "不由得" in BLACKLIST_WORDS
    text = "他淡淡的看了一眼，不由得笑了。" * 2  # 各词出现 2 次
    total, hits = count_blacklist(text)
    assert total == 4  # 两词各 2 次
    hit_words = {h.word: h.count for h in hits}
    assert hit_words["淡淡的"] == 2
    assert hit_words["不由得"] == 2


def test_blacklist_hits_sorted_desc() -> None:
    # 明细按出现次数降序，便于报告聚焦高频词。
    text = "淡淡的淡淡的淡淡的，不由得。"  # 淡淡的×3、不由得×1
    _, hits = count_blacklist(text)
    counts = [h.count for h in hits]
    assert counts == sorted(counts, reverse=True)
    assert hits[0].word == "淡淡的"
    assert hits[0].count == 3


def test_clean_text_zero_blacklist() -> None:
    # 干净的具体叙事文本不应命中黑名单（宁缺毋滥、不误伤日常词）。
    text = "他推开门，雨还在下。街角的灯亮着，照见半张湿透的报纸。"
    total, hits = count_blacklist(text)
    assert total == 0
    assert hits == []


def test_per_kchar_normalization() -> None:
    # 千字归一公式：per_kchar == blacklist_total / char_count * 1000（保留 2 位）。
    # 用「不由得」构造恰 1 次命中的文本，验证归一公式而非硬编码字数（字数由实现自行计）。
    filler = "他站在窗前看着远处的山影发呆然后什么也没说只是又坐了回去"
    text = "不由得" + filler * 3  # 恰含 1 次「不由得」命中
    stats = analyze_axis_b(text)
    assert stats.blacklist_total == 1
    assert stats.char_count > 0
    expected = round(1 / stats.char_count * 1000, 2)
    assert stats.blacklist_per_kchar == expected


# ========== 句式套路 ==========


def test_pattern_not_x_but_y() -> None:
    # ①「不是 X 而是 Y」对仗。
    text = "他明白了，这不是结束，而是另一个开始。"
    total, hits = count_patterns(text)
    assert total >= 1
    names = {h.rule_name for h in hits}
    assert "not_x_but_y" in names
    # 命中片段保留原文供复核。
    hit = next(h for h in hits if h.rule_name == "not_x_but_y")
    assert any("不是" in s and "而是" in s for s in hit.snippets)


def test_pattern_forced_parallel() -> None:
    # ② 连续三段同**实词**引导词排比（≥2 字实词起头）。
    text = "有的人在笑，有的人在哭，有的人在沉默。"
    total, hits = count_patterns(text)
    assert total >= 1
    assert "forced_parallel" in {h.rule_name for h in hits}


def test_forced_parallel_ignores_single_char_lead() -> None:
    # 回归：1 字虚词起头的自然三连（「在说话，在走动，在拧发条」）不是排比套路，不该命中。
    text = "有人在说话，在走动，在拧发条。"
    total, hits = count_patterns(text)
    assert "forced_parallel" not in {h.rule_name for h in hits}


def test_pattern_aphorism_ending() -> None:
    # ③ 万能金句式升华结尾。
    text = "他忽然懂了，或许这就是人生的意义。"
    total, hits = count_patterns(text)
    assert total >= 1
    assert "aphorism_ending" in {h.rule_name for h in hits}


def test_pattern_triadic_uplift() -> None:
    # ④ 三连短语 + 抽象名词升华（真 AI 套路）。
    text = "这不是偶然，不是巧合，更是冥冥之中的命运。"
    total, hits = count_patterns(text)
    assert total >= 1
    assert "triadic_uplift" in {h.rule_name for h in hits}


def test_triadic_uplift_ignores_plain_narration() -> None:
    # 回归（此前假阳性根源）：白描三分句不带抽象升华名词，不该命中 triadic_uplift。
    for text in [
        "在这里放了十三年，没人赎，也没人肯买断。",
        "说是那一片拆了，住户们都搬走了，也不知道搬去了哪里。",
        "还能转，但没通电，也不知道还能不能响。",
        "风来了，雨停了，天终于亮了起来。",
    ]:
        _, hits = count_patterns(text)
        assert "triadic_uplift" not in {h.rule_name for h in hits}, f"误报：{text}"


def test_clean_text_zero_patterns() -> None:
    # 干净的具体叙事不应触发任何套路规则。
    text = "他把伞收起来，靠在门边。屋里没开灯，只有窗外路灯的一点光。"
    total, hits = count_patterns(text)
    assert total == 0
    assert hits == []


# ========== 边界 ==========


def test_empty_text_no_division_error() -> None:
    # 空文本：char_count=0，per_kchar 防除零归 0。
    stats = analyze_axis_b("")
    assert stats.char_count == 0
    assert stats.blacklist_per_kchar == 0.0
    assert stats.blacklist_total == 0
    assert stats.pattern_total == 0


def test_whitespace_only_text() -> None:
    # 纯空白：可见字符数 0，同样防除零。
    stats = analyze_axis_b("   \n\t  \n")
    assert stats.char_count == 0
    assert stats.blacklist_per_kchar == 0.0


def test_analyze_axis_b_aggregates_both_axes() -> None:
    # 综合：一段同时含黑名单词与句式套路的文本，两轴都统计到。
    text = "他内心深处涌起一种莫名的悸动，这不是偶然，而是命运的安排。"
    stats = analyze_axis_b(text)
    assert stats.blacklist_total >= 1  # 「内心深处」「一种莫名」
    assert stats.pattern_total >= 1  # 「不是…而是…」
    assert stats.char_count > 0


def test_lexicon_version_is_temp() -> None:
    # 留档报告要记录临时词表版本（AC5/AC6：注明这是临时版）。
    assert LEXICON_VERSION.startswith("temp-")
