"""Story 4.2 Task 1 验证：正式去 AI 味词表 + 轴 B 统计（离线纯逻辑，CI 必过）。

覆盖：
- 规模门槛：黑名单 ≥200 词、句式规则 =7 条（AC3）
- 黑名单词频：命中计数、千字归一、逐词明细降序、干净文本零命中
- 句式套路：7 类规则各自命中、干净文本零命中、命中含原文片段
- 回归约束：承 4.1 已修的假阳性（单字虚词排比 / 白描三分句不误报）
- 写作约束文本：format_lexicon_constraints 含分组代表词 + 7 条规则说明
- 边界：空文本防除零、纯空白文本

正式词表纯函数、无 IO/无 DB/无真实 API，属 CI 必过的离线单元。
"""

from muse.orchestration.ai_taste_lexicon import (
    BLACKLIST_WORDS,
    LEXICON_VERSION,
    PATTERN_RULES,
    analyze_axis_b,
    count_blacklist,
    count_patterns,
    format_lexicon_constraints,
)

# ========== 规模门槛（AC3：200+ 词黑名单 + 7 层句式规则）==========


def test_blacklist_has_at_least_200_words() -> None:
    # AC3 要求正式词表黑名单扩充到 200+ 词（临时版仅精简子集）。
    assert len(BLACKLIST_WORDS) >= 200, f"黑名单仅 {len(BLACKLIST_WORDS)} 词，须 ≥200"


def test_blacklist_words_unique() -> None:
    # 扁平集合已去重：无重复词条。
    assert len(BLACKLIST_WORDS) == len(set(BLACKLIST_WORDS))


def test_seven_pattern_rules() -> None:
    # AC3 要求句式规则补齐到 7 层。
    assert len(PATTERN_RULES) == 7
    names = {r.name for r in PATTERN_RULES}
    assert names == {
        "not_x_but_y",
        "forced_parallel",
        "aphorism_ending",
        "triadic_uplift",
        "antithesis_uplift",
        "rhetorical_qa",
        "exclamation_barrage",
    }


def test_lexicon_version_is_formal() -> None:
    # 正式版号（非临时 temp-* 前缀），留档/polisher 日志记录用。
    assert LEXICON_VERSION.startswith("v1-")


# ========== 黑名单词频 ==========


def test_blacklist_counts_hits_and_per_kchar() -> None:
    assert "淡淡的" in BLACKLIST_WORDS
    assert "不由得" in BLACKLIST_WORDS
    text = "他淡淡的看了一眼，不由得笑了。" * 2  # 各词出现 2 次
    total, hits = count_blacklist(text)
    assert total == 4
    hit_words = {h.word: h.count for h in hits}
    assert hit_words["淡淡的"] == 2
    assert hit_words["不由得"] == 2


def test_blacklist_hits_sorted_desc() -> None:
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
    # 用生僻不含其他黑名单词的填充串，确保恰 1 次命中。
    filler = "他站在窗前望着远山出神随后什么也没讲只是又坐了回来"
    text = "不由得" + filler * 3  # 恰含 1 次「不由得」命中
    stats = analyze_axis_b(text)
    assert stats.blacklist_total == 1
    assert stats.char_count > 0
    expected = round(1 / stats.char_count * 1000, 2)
    assert stats.blacklist_per_kchar == expected


# ========== 句式套路（前 4 层承 4.1）==========


def test_pattern_not_x_but_y() -> None:
    text = "他明白了，这不是结束，而是另一个开始。"
    total, hits = count_patterns(text)
    assert total >= 1
    assert "not_x_but_y" in {h.rule_name for h in hits}
    hit = next(h for h in hits if h.rule_name == "not_x_but_y")
    assert any("不是" in s and "而是" in s for s in hit.snippets)


def test_pattern_forced_parallel() -> None:
    text = "有的人在笑，有的人在哭，有的人在沉默。"
    total, hits = count_patterns(text)
    assert total >= 1
    assert "forced_parallel" in {h.rule_name for h in hits}


def test_forced_parallel_ignores_single_char_lead() -> None:
    # 回归：1 字虚词起头的自然三连不该命中。
    text = "有人在说话，在走动，在拧发条。"
    _, hits = count_patterns(text)
    assert "forced_parallel" not in {h.rule_name for h in hits}


def test_pattern_aphorism_ending() -> None:
    text = "他忽然懂了，或许这就是人生的意义。"
    total, hits = count_patterns(text)
    assert total >= 1
    assert "aphorism_ending" in {h.rule_name for h in hits}


def test_pattern_triadic_uplift() -> None:
    text = "这不是偶然，不是巧合，更是冥冥之中的命运。"
    total, hits = count_patterns(text)
    assert total >= 1
    assert "triadic_uplift" in {h.rule_name for h in hits}


def test_triadic_uplift_ignores_plain_narration() -> None:
    # 回归（4.1 假阳性根源）：白描三分句不带抽象升华名词，不该命中。
    for text in [
        "在这里放了十三年，没人赎，也没人肯买断。",
        "说是那一片拆了，住户们都搬走了，也不知道搬去了哪里。",
        "还能转，但没通电，也不知道还能不能响。",
        "风来了，雨停了，天终于亮了起来。",
    ]:
        _, hits = count_patterns(text)
        assert "triadic_uplift" not in {h.rule_name for h in hits}, f"误报：{text}"


# ========== 句式套路（新增 3 层）==========


def test_pattern_antithesis_uplift() -> None:
    # ⑤「与其说 X，不如说 Y」转折对仗。
    text = "这与其说是胜利，不如说是一场彻底的失败。"
    total, hits = count_patterns(text)
    assert total >= 1
    assert "antithesis_uplift" in {h.rule_name for h in hits}


def test_pattern_rhetorical_qa() -> None:
    # ⑥ 设问自答式升华。
    text = "什么是自由？自由就是明知代价仍愿承担的选择。"
    total, hits = count_patterns(text)
    assert total >= 1
    assert "rhetorical_qa" in {h.rule_name for h in hits}


def test_rhetorical_qa_ignores_plain_question() -> None:
    # 回归：普通疑问句（无「什么是/何为」起头 + 就是承接）不该命中。
    text = "你吃饭了吗？我还没呢。"
    _, hits = count_patterns(text)
    assert "rhetorical_qa" not in {h.rule_name for h in hits}


def test_pattern_exclamation_barrage() -> None:
    # ⑦ 连续三句短感叹堆砌。
    text = "太好了！我们成功了！这一切都值得！"
    total, hits = count_patterns(text)
    assert total >= 1
    assert "exclamation_barrage" in {h.rule_name for h in hits}


def test_exclamation_barrage_ignores_single() -> None:
    # 回归：单个感叹句不该命中（只有连续三句才算轰炸）。
    text = "太好了！他终于回来了，屋里也重新亮起了灯。"
    _, hits = count_patterns(text)
    assert "exclamation_barrage" not in {h.rule_name for h in hits}


def test_clean_text_zero_patterns() -> None:
    text = "他把伞收起来，靠在门边。屋里没开灯，只有窗外路灯的一点光。"
    total, hits = count_patterns(text)
    assert total == 0
    assert hits == []


# ========== 写作约束文本 ==========


def test_format_lexicon_constraints() -> None:
    # 注入 drafter/polisher 的约束文本：含标题 + 7 条规则说明 + 分组代表词。
    text = format_lexicon_constraints()
    assert "去 AI 味约束" in text
    for rule in PATTERN_RULES:
        assert rule.note in text
    # 至少含若干代表黑名单词（不逐字塞全量）。
    assert "淡淡的" in text or "内心深处" in text


# ========== 边界 ==========


def test_empty_text_no_division_error() -> None:
    stats = analyze_axis_b("")
    assert stats.char_count == 0
    assert stats.blacklist_per_kchar == 0.0
    assert stats.blacklist_total == 0
    assert stats.pattern_total == 0


def test_whitespace_only_text() -> None:
    stats = analyze_axis_b("   \n\t  \n")
    assert stats.char_count == 0
    assert stats.blacklist_per_kchar == 0.0


def test_analyze_axis_b_aggregates_both_axes() -> None:
    text = "他内心深处涌起一种莫名的悸动，这不是偶然，而是命运的安排。"
    stats = analyze_axis_b(text)
    assert stats.blacklist_total >= 1  # 「内心深处」「一种莫名」
    assert stats.pattern_total >= 1  # 「不是…而是…」
    assert stats.char_count > 0
