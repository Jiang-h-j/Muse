"""章节正文 chunk 化（Story 5.5 Task 3，RAG 向量化前置）。

把定稿章节正文切成 ~max_chars 字上限的 chunk，供逐块向量化写入 embedding 表。
按段落（`\n\n`）聚合，超长段落硬切，相邻 chunk 留 overlap 字重叠（防语义在边界处被截断）。

**V1 用字符数近似、不做 token 精确切分**（同 count_tokens「粗估够用」先例）：embedding
模型有自身 token 上限，800 字 CJK ≈ 480 token 远低于阿里 text-embedding-v3 的 8192
上限，安全。若未来换更小上限的模型再引精确 tokenizer。

**overlap 语义（事后拼接，内部预留空间）**：聚合/硬切时用
`effective = max_chars - overlap` 作上限攒块，再给相邻块开头拼上一块尾部 overlap 字——
拼接后每块正好 ≤ max_chars，且相邻块有 overlap 字重叠衔接。
"""


def chunk_chapter_text(
    text: str, *, max_chars: int = 800, overlap: int = 100
) -> list[str]:
    """把章节正文切成若干 chunk（每块 ≤ max_chars 字，相邻留 overlap 字重叠）。

    切分策略：
    1. 按段落（`\n\n`）拆去空段；超长单段落先按 `effective` 硬切成多个「单元」。
    2. 逐单元聚合到 `effective = max_chars - overlap` 上限（给重叠预留空间）才封口。
    3. 相邻 chunk 之间拼 overlap 字重叠——上一 chunk 尾部 overlap 字作下一 chunk 开头，
       避免关键语义恰好落在切点两侧被割裂（RAG 召回时任一侧都能命中完整语境）。

    空/纯空白文本返 []（不产 chunk，投影侧据此 skip，不打 embedding API）。
    """
    if not text or not text.strip():
        return []

    # 防御：overlap 不该 ≥ max_chars（否则 effective ≤ 0，攒不出块）；退化为无重叠。
    if overlap >= max_chars:
        overlap = 0
    effective = max_chars - overlap

    # 段落切分去空段；超长段落先硬切成 ≤ effective 的单元（长段无法靠段落边界断开）。
    units: list[str] = []
    for para in (p.strip() for p in text.split("\n\n")):
        if not para:
            continue
        if len(para) > effective:
            units.extend(_hard_split(para, size=effective))
        else:
            units.append(para)

    # 聚合相邻单元到 effective 上限（给随后拼 overlap 预留空间）。
    chunks: list[str] = []
    current = ""
    for unit in units:
        candidate = f"{current}\n\n{unit}" if current else unit
        if len(candidate) > effective and current:
            chunks.append(current)
            current = unit
        else:
            current = candidate
    if current:
        chunks.append(current)

    return _apply_overlap(chunks, overlap=overlap)


def _hard_split(text: str, *, size: int) -> list[str]:
    """把超长段落按 size 无重叠硬切（重叠由 _apply_overlap 事后统一补）。"""
    return [text[i : i + size] for i in range(0, len(text), size)]


def _apply_overlap(chunks: list[str], *, overlap: int) -> list[str]:
    """给相邻 chunk 开头拼上一块尾部 overlap 字（首块不动）。

    每块攒到 ≤ effective = max_chars - overlap，故拼 overlap 后 ≤ max_chars。
    overlap=0 或单块时短路返回原列表（无重叠可拼）。
    """
    if overlap <= 0 or len(chunks) <= 1:
        return chunks
    result = [chunks[0]]
    for i in range(1, len(chunks)):
        tail = chunks[i - 1][-overlap:]
        result.append(f"{tail}{chunks[i]}")
    return result
