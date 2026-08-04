"""Story 4.1 Task 2 验证：写作任务书组装 + 匿名落盘 + _key 合并（离线纯逻辑，CI 必过）。

覆盖：
- build_writing_brief：12 字段进任务书、style_profile 注入 / 缺省提示、chapter_idea 可空、
  两次调用同输入产出逐字节一致（AC1 地基）
- _format_bible：空/None 特化字段跳过、不产空标签行
- make_anonymous_id：无生成方线索、够随机
- 匿名落盘 + _key 读写合并（append_records 累积两侧）
- write_scoring_sheet：列匿名 id、**不含生成方列**（AC3）
真实 DeepSeek 生成不在此测（需 key，属集成）。IO 用 monkeypatch 重定向到 tmp。
"""

import json

import pytest
from blind_test import run_blind_test as rbt
from blind_test.run_blind_test import (
    TEST_BIBLE,
    BibleFields,
    build_sample_record,
    build_writing_brief,
    make_anonymous_id,
)


@pytest.fixture
def tmp_docs(tmp_path, monkeypatch):
    """把装置的落盘路径常量重定向到 tmp，隔离测试产物、不污染真实 docs/。"""
    docs = tmp_path / "blind-test-4.1"
    monkeypatch.setattr(rbt, "_DOCS_DIR", docs)
    monkeypatch.setattr(rbt, "_SAMPLES_DIR", docs / "samples")
    monkeypatch.setattr(rbt, "_BRIEF_PATH", docs / "writing-brief.md")
    monkeypatch.setattr(rbt, "_KEY_PATH", docs / "_key.json")
    monkeypatch.setattr(rbt, "_SCORING_SHEET_PATH", docs / "scoring-sheet.md")
    return docs


# ========== build_writing_brief ==========


def test_brief_includes_bible_fields() -> None:
    system, user = build_writing_brief(TEST_BIBLE)
    # 通用主干字段值须进任务书（抽查题材、主角、开篇钩子）。
    assert TEST_BIBLE.genre in user
    assert "沈砚" in user
    assert "三点十七分" in user
    # 去 AI 味约束 + 输出要求进 system。
    assert "去 AI 味" in system
    assert "只输出第一章正文" in system


def test_brief_injects_style_profile() -> None:
    profile = "人称：第一人称限知\n语气：冷峻克制"
    fields = BibleFields(**{**vars(TEST_BIBLE), "style_profile": profile})
    system, _ = build_writing_brief(fields)
    assert "第一人称限知" in system
    assert "冷峻克制" in system


def test_brief_default_style_hint_when_no_profile() -> None:
    # style_profile 为 None → 用默认风格提示、不崩。
    system, _ = build_writing_brief(TEST_BIBLE)  # TEST_BIBLE.style_profile is None
    assert rbt._DEFAULT_STYLE_HINT in system


def test_brief_chapter_idea_optional() -> None:
    _, user_no = build_writing_brief(TEST_BIBLE)
    _, user_yes = build_writing_brief(TEST_BIBLE, chapter_idea="从雨夜的当铺打烊写起")
    assert "本章想法" not in user_no
    assert "从雨夜的当铺打烊写起" in user_yes


def test_brief_deterministic_same_input(monkeypatch) -> None:
    # AC1 地基：同一设定输入两次组装产出逐字节一致（两侧生成方共用同一份的前提）。
    a = build_writing_brief(TEST_BIBLE, chapter_idea="x")
    b = build_writing_brief(TEST_BIBLE, chapter_idea="x")
    assert a == b


def test_format_bible_skips_empty_specialized_fields() -> None:
    # 特化字段 None → 不出现在任务书里（不产"力量体系："空标签行）。
    block = rbt._format_bible(TEST_BIBLE)
    assert "力量体系" not in block  # power_system=None
    assert "感情线" not in block  # romance_line=None
    assert "金手指" in block  # golden_finger 有值


# ========== 匿名 id ==========


def test_anonymous_id_no_generator_leak() -> None:
    # 匿名 id 不含 deepseek/claude 字样、够随机（两次不相等）。
    a, b = make_anonymous_id(), make_anonymous_id()
    assert a != b
    assert "deepseek" not in a and "claude" not in a
    assert len(a) >= 8


# ========== 落盘 + _key 合并 ==========


def test_write_sample_content_only(tmp_docs) -> None:
    # 样本文件只含正文、无任何生成方标识（AC3）。
    path = rbt.write_sample("abc123", "这是一段正文。")
    assert path.read_text(encoding="utf-8") == "这是一段正文。"
    assert path.name == "abc123.md"


def test_append_records_accumulates_both_sides(tmp_docs) -> None:
    # 模拟 DeepSeek 侧先写 2 条、Claude 侧再并入 1 条 → _key 共 3 条、两侧齐。
    ds = [
        build_sample_record("d1", "deepseek", "deepseek-v4-pro", "正文一"),
        build_sample_record("d2", "deepseek", "deepseek-v4-pro", "正文二"),
    ]
    rbt.append_records(ds)
    cl = [build_sample_record("c1", "claude", "claude-code-subagent", "正文三")]
    merged = rbt.append_records(cl)
    assert len(merged) == 3
    generators = {r["generator"] for r in merged}
    assert generators == {"deepseek", "claude"}
    # 落盘的 _key.json 可复读。
    on_disk = json.loads(rbt._KEY_PATH.read_text(encoding="utf-8"))
    assert len(on_disk) == 3


def test_sample_record_has_axis_b(tmp_docs) -> None:
    # 生成阶段自动算轴 B 并进 _key（AC2 轴 B 客观、无需人评）。含黑名单词的正文应统计到。
    rec = build_sample_record("x1", "deepseek", "m", "他内心深处淡淡的叹了口气。")
    assert rec.axis_b["blacklist_total"] >= 1
    assert "blacklist_per_kchar" in rec.axis_b
    assert "pattern_total" in rec.axis_b


# ========== 打分表 ==========


def test_scoring_sheet_no_generator_column(tmp_docs) -> None:
    # 打分表只有匿名 id + 空轴 A 列，绝不含生成方列（AC3 盲评前提）。
    rbt.write_scoring_sheet(["id1", "id2", "id3"])
    text = rbt._SCORING_SHEET_PATH.read_text(encoding="utf-8")
    assert "id1" in text and "id3" in text
    assert "轴A评分" in text
    # 表格 header 行（含 | 的那一行）不得含生成方 / provider 列——只校验表格结构，
    # 说明文字里出现「生成方」（解释盲评前提）不算泄露。
    header = next(ln for ln in text.splitlines() if ln.strip().startswith("| 样本"))
    assert "deepseek" not in header.lower()
    assert "claude" not in header.lower()
    assert "生成方" not in header


def test_write_brief_records_ac1_constraint(tmp_docs) -> None:
    # writing-brief.md 落盘含 AC1 硬约束说明 + system/user 全文（留档 AC5）。
    system, user = build_writing_brief(TEST_BIBLE)
    rbt.write_brief(system, user)
    text = rbt._BRIEF_PATH.read_text(encoding="utf-8")
    assert "逐字节一致" in text
    assert "沈砚" in text  # user 全文
    assert "去 AI 味" in text  # system 全文
