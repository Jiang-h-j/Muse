"""临时去 AI 味词表 + 轴 B 自动统计（Story 4.1，盲测门禁装置）。

**本模块是临时版**（AC6）：正式去 AI 味词表随 Story 4.2 落地。这里只落一个精简可用子集，
供盲测轴 B（负向硬底线）客观量化两项——黑名单词频 + 重度句式套路数（NFR1 epics.md:85-88）。

**NFR7 GPL 护栏（clean-room）**：黑名单与句式规则参照开源项目 webnovel-writer polish-guide
的**规则思路**（200+ 词黑名单 + 7 层句式规则的设计意图）自行组织，**不复制其 GPL 源码**——
词条与正则均为本项目独立编写，只借「哪类词/句式算 AI 味」的判断思路。正式实现前的许可证义务
评估见 architecture.md:250-252。

**装置定位**：放 backend/scripts/blind_test/（退风险验证脚本，与 spike_* 同级），不进 src
业务链路。纯函数、无 IO、无外部依赖，可离线单测。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# 临时版本号：留档报告记录用（AC5）。正式词表随 4.2 落地时另起版本。
# ---------------------------------------------------------------------------
LEXICON_VERSION = "temp-4.1-2026-08-04"

# ---------------------------------------------------------------------------
# 黑名单词（临时精简子集）。clean-room 自编：收录网文/AI 生成里高频、空洞、抽象的
# 「翻译腔 + 万能形容 + 抽象名词化」词汇。命中即计频，词频 = 命中总次数 / 千字（AC2③）。
#
# 分组仅为可读性与维护，统计时合并为一个集合。选词原则：宁缺毋滥，只收「一出现就明显
# 出戏」的词；模棱两可的日常词不收（避免误伤正常叙事，宁可漏报交轴 A 人评兜底）。
# ---------------------------------------------------------------------------
_BLACKLIST_GROUPS: dict[str, list[str]] = {
    # 抽象名词化 / 概念堆砌（AI 爱把具体场景抽象成"某种…感"）
    "abstraction": [
        "某种",
        "一种莫名",
        "难以言喻",
        "无法言说",
        "复杂的情绪",
        "五味杂陈",
        "百感交集",
        "心中五味",
    ],
    # 万能形容 / 空洞修饰（放哪都行、等于没说）
    "empty_modifier": [
        "淡淡的",
        "深深地",
        "深深的",
        "缓缓地",
        "缓缓的",
        "轻轻地",
        "微微一笑",
        "嘴角勾起",
        "嘴角微微",
        "不易察觉",
        "若有若无",
        "若有所思",
    ],
    # 翻译腔 / 书面僵硬（口语网文里不该出现的生硬连接与句式词）
    "translationese": [
        "不由得",
        "不禁",
        "仿佛整个世界",
        "整个世界仿佛",
        "这一刻",
        "那一刻",
        "在这一瞬间",
        "与此同时",
        "毫无疑问",
        "无可否认",
    ],
    # 情绪爆发套路词（AI 写情绪爱堆的强度词）
    "emotion_cliche": [
        "内心深处",
        "灵魂深处",
        "撕心裂肺",
        "刻骨铭心",
        "泪如雨下",
        "泪流满面",
    ],
}

# 合并为统计用的扁平集合（去重）。
BLACKLIST_WORDS: tuple[str, ...] = tuple(
    dict.fromkeys(word for group in _BLACKLIST_GROUPS.values() for word in group)
)


# ---------------------------------------------------------------------------
# 重度句式套路检测规则（AC2②，命中数须 = 0 才达及格线）。
# clean-room 自编正则/启发式，对齐 NFR1 点名的三类：万能金句结尾 / 强行排比 /
# 「不是 X 而是 Y」对仗滥用。**命中即报、宁可多报交人工复核**（不追求 NLP 精度）。
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PatternRule:
    """一条句式套路规则：name 供报告归类，pattern 是预编译正则，note 说明命中含义。"""

    name: str
    pattern: re.Pattern[str]
    note: str


# 中文标点集合（用于切句 / 判句尾）。
_SENTENCE_END = "。！？…”"


def _compile(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern)


PATTERN_RULES: tuple[PatternRule, ...] = (
    # ① 「不是 X 而是 Y」对仗（AI 极爱的伪深刻对仗）。含常见变体「不是…，而是…」。
    PatternRule(
        name="not_x_but_y",
        pattern=_compile(r"不是[^，。！？；]{1,20}[，,]\s*而是"),
        note="「不是 X 而是 Y」对仗句式（伪深刻对仗滥用）",
    ),
    # ② 强行排比：连续三段以**同一实词**（≥2 字，非虚词）起头的分句
    #    （「有的人…有的人…有的人…」「不是…不是…不是…」）。引导词限 2-4 字实词——
    #    1 字虚词（在/是/也/的）起头是自然叙事（「在说话，在走动，在拧发条」），不算套路。
    PatternRule(
        name="forced_parallel",
        pattern=_compile(
            r"([一-鿿]{2,4})[^，。！？；]{1,15}[，,]"
            r"\s*\1[^，。！？；]{1,15}[，,]"
            r"\s*\1[^，。！？；]{1,15}"
        ),
        note="连续三段同引导词排比（强行排比）",
    ),
    # ③ 万能金句结尾：段落/句子以格言化、抽象升华收束。近似检测——句尾出现
    #    「……的意义/答案/真相/全部/一切。」这类抽象名词收束，或「或许，这就是……」式升华。
    PatternRule(
        name="aphorism_ending",
        pattern=_compile(
            r"(?:或许|也许|大概|这|那)[^，。！？；]{0,12}"
            r"(?:就是|便是|正是)[^。！？…]{0,20}"
            r"(?:的意义|的答案|的真相|的全部|的一切|的宿命|的命运)[。！？…]"
        ),
        note="万能金句式升华结尾（格言化收束）",
    ),
    # ④ 排比式抽象升华：三连短语 + 末句抽象名词升华收束
    #    （「不是 X，不是 Y，更是命运/救赎/意义……」）。**必须末句带抽象升华名词**才算套路——
    #    白描的三分句（「放了十三年，没人赎，也不知搬去哪」）不带抽象名词，不算（此前假阳性根源）。
    PatternRule(
        name="triadic_uplift",
        pattern=_compile(
            r"[^，。！？；]{1,12}[，,][^，。！？；]{1,12}[，,]"
            r"[^，。！？；]{0,8}(?:也|亦|更|终究|终于|最终)[^。！？…]{0,16}"
            r"(?:命运|宿命|救赎|意义|真相|答案|全部|一切|归宿|终点|羁绊|执念|信仰|永恒)"
            r"[^。！？…]{0,6}[。！？…]"
        ),
        note="三连短语 + 抽象名词升华收束（排比式煽情）",
    ),
)


# ---------------------------------------------------------------------------
# 统计结果结构
# ---------------------------------------------------------------------------


@dataclass
class BlacklistHit:
    """单个黑名单词命中：word + 出现次数。"""

    word: str
    count: int


@dataclass
class PatternHit:
    """单条句式套路命中：rule_name + note + 命中的原文片段列表（供人工复核）。"""

    rule_name: str
    note: str
    snippets: list[str] = field(default_factory=list)


@dataclass
class AxisBStats:
    """一段正文的轴 B 统计结果（AC2②③）。

    - char_count：计频用的字符数（用于千字归一）。
    - blacklist_total：黑名单命中总次数。
    - blacklist_per_kchar：每千字命中数（= blacklist_total / char_count * 1000）。
    - blacklist_hits：逐词命中明细（供报告）。
    - pattern_total：重度句式套路命中总数（AC2② 须 = 0）。
    - pattern_hits：逐规则命中明细（含原文片段，供人工复核）。
    """

    char_count: int
    blacklist_total: int
    blacklist_per_kchar: float
    blacklist_hits: list[BlacklistHit]
    pattern_total: int
    pattern_hits: list[PatternHit]


def _count_chars(text: str) -> int:
    """计频归一用的字符数：去掉空白与换行，按可见字符计（中英文混排近似）。

    千字归一的分母口径须稳定：只剔除空白类字符，标点计入（网文标点是正文一部分）。
    空文本返回 0，由调用方防除零。
    """
    return len(re.sub(r"\s", "", text))


def count_blacklist(text: str) -> tuple[int, list[BlacklistHit]]:
    """统计黑名单词命中：返回 (总次数, 逐词明细)。

    子串计数（非分词）：中文无天然词边界，黑名单词多为多字固定搭配，直接 str.count 子串
    足够（临时版精度，AC6）。只收 count>0 的词进明细，按出现次数降序便于报告聚焦。
    """
    hits: list[BlacklistHit] = []
    total = 0
    for word in BLACKLIST_WORDS:
        c = text.count(word)
        if c > 0:
            hits.append(BlacklistHit(word=word, count=c))
            total += c
    hits.sort(key=lambda h: h.count, reverse=True)
    return total, hits


def count_patterns(text: str) -> tuple[int, list[PatternHit]]:
    """统计重度句式套路命中：返回 (命中总数, 逐规则明细含原文片段)。

    每条规则 findall 全部命中，命中数累加。明细保留原文片段（截断到合理长度）供人工复核
    ——轴 B 套路检测是启发式、宁可多报，人工据片段判真伪（AC2② 语义）。
    """
    hits: list[PatternHit] = []
    total = 0
    for rule in PATTERN_RULES:
        matches = rule.pattern.findall(text)
        if not matches:
            continue
        # findall 对含分组的正则返回分组元组；用 finditer 取整体匹配片段更直观。
        snippets = [m.group(0) for m in rule.pattern.finditer(text)]
        count = len(snippets)
        if count > 0:
            hits.append(
                PatternHit(rule_name=rule.name, note=rule.note, snippets=snippets)
            )
            total += count
    return total, hits


def analyze_axis_b(text: str) -> AxisBStats:
    """对一段正文做完整轴 B 统计（黑名单词频 + 句式套路数），返回结构化结果。

    这是盲测生成阶段对每篇样本自动调用的入口（轴 B 客观、无需人评，AC2）。
    """
    char_count = _count_chars(text)
    blacklist_total, blacklist_hits = count_blacklist(text)
    pattern_total, pattern_hits = count_patterns(text)
    per_kchar = (blacklist_total / char_count * 1000) if char_count > 0 else 0.0
    return AxisBStats(
        char_count=char_count,
        blacklist_total=blacklist_total,
        blacklist_per_kchar=round(per_kchar, 2),
        blacklist_hits=blacklist_hits,
        pattern_total=pattern_total,
        pattern_hits=pattern_hits,
    )
