"""Story 5.5 Task 4.3 验证：chunk_chapter_text（纯单元，不需 DB/API）。

覆盖：短文本 1 chunk；空/空白文本 []；长文本多 chunk 且相邻有 overlap 重叠；
超长单段落硬切。
"""

from muse.rag.chunking import chunk_chapter_text


def test_empty_text_returns_empty() -> None:
    # 空文本 / 纯空白 → []（投影侧据此 skip，不打 API）。
    assert chunk_chapter_text("") == []
    assert chunk_chapter_text("   \n\n  ") == []


def test_short_text_single_chunk() -> None:
    # 短文本（远小于 max_chars）→ 单 chunk，原文保留。
    chunks = chunk_chapter_text("第一段。\n\n第二段。")
    assert len(chunks) == 1
    assert "第一段。" in chunks[0]
    assert "第二段。" in chunks[0]


def test_long_text_multiple_chunks_with_overlap() -> None:
    # 多段落聚合超上限 → 多 chunk；相邻 chunk 有 overlap 字重叠。
    para = "甲" * 300
    text = "\n\n".join([para, "乙" * 300, "丙" * 300])
    chunks = chunk_chapter_text(text, max_chars=400, overlap=50)
    assert len(chunks) >= 2
    # 相邻 chunk：后一块开头应含前一块尾部 overlap 字（重叠衔接）。
    prev_tail = chunks[0][-50:]
    assert chunks[1].startswith(prev_tail)


def test_oversize_single_paragraph_hard_split() -> None:
    # 超长单段落（无 \n\n 可断）→ 按 max_chars 硬切成多块。
    text = "字" * 2000
    chunks = chunk_chapter_text(text, max_chars=800, overlap=100)
    assert len(chunks) >= 3
    # 每块不超过 max_chars（拼 overlap 后仍 ≤ 上限：内部按 effective=700 攒 + 100 重叠）。
    assert all(len(c) <= 800 for c in chunks)
    # 相邻块有 overlap 字重叠：后一块开头 100 字 = 前一块尾部 100 字。
    assert chunks[1][:100] == chunks[0][-100:]


def test_overlap_zero_no_overlap() -> None:
    # overlap=0 时相邻 chunk 不拼接重叠（回归防线：_apply_overlap 短路）。
    text = "\n\n".join(["甲" * 300, "乙" * 300])
    chunks = chunk_chapter_text(text, max_chars=350, overlap=0)
    assert len(chunks) == 2
    assert chunks[1].startswith("乙")
