"""正式去 AI 味词表 + 轴 B 统计（Story 4.2，AR15 / NFR1 / NFR7b）。

**本模块是正式版**（Story 4.2 AC3）：在 Story 4.1 临时子集（`backend/scripts/blind_test/
ai_taste_lexicon_temp.py`）基础上，黑名单扩充到 200+ 词、句式规则补齐到 7 层，进入 src 业务
链路，供五段流水线 polisher step 自查自改（orchestration/steps）。临时版冻结不动（4.1 已
review 的留档验证装置），本正式版另起模块与版本号。

**NFR7b GPL 护栏（clean-room）**：黑名单与句式规则参照开源项目 webnovel-writer polish-guide
的**规则思路**（哪类词/句式算「AI 味」的判断意图：200+ 词黑名单 + 7 层句式规则的设计目标）
自行组织，**不复制其 GPL 源码**——词条与正则均为本项目独立编写。许可证义务评估见
architecture.md:250-252。

**判据定位（延续 4.1 Completion Notes 判据局限）**：句式套路检测是启发式，区分不了「正当
修辞」与「AI 煽情套路」，故命中语义是**「疑似命中 → 交 polisher/人工复核」**，不是硬门禁——
polisher 用统计作**自查改写的输入信号**（宁可多报，由 LLM 据语义决定改不改），不直接判死。

纯函数、无 IO、无外部依赖，可离线单测。接口签名与临时版一致（`LEXICON_VERSION` /
`BLACKLIST_WORDS` / `PATTERN_RULES` / `analyze_axis_b` / `count_blacklist` / `count_patterns`
及各结果 dataclass），便于共用统计口径与测试范式。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# 正式版本号：留档 / polisher 日志记录用。区别于临时版 "temp-4.1-*"。
# ---------------------------------------------------------------------------
LEXICON_VERSION = "v1-4.2-2026-08-04"

# ---------------------------------------------------------------------------
# 黑名单词（正式版，200+ 词）。clean-room 自编：收录网文/AI 生成里高频、空洞、抽象、
# 翻译腔的词汇。命中即计频，词频 = 命中总次数 / 千字。
#
# 分组仅为可读性与维护，统计时合并为一个集合。选词原则：只收「一出现就明显出戏」的
# AI 味词；日常高频实词（走/看/说/门/雨…）一律不收，避免误伤正常叙事（宁可漏报交
# polisher 语义复核 / 轴 A 人评兜底）。
# ---------------------------------------------------------------------------
_BLACKLIST_GROUPS: dict[str, list[str]] = {
    # ① 抽象名词化 / 概念堆砌（把具体场景抽象成「某种…感」）
    "abstraction": [
        "某种",
        "某种意义上",
        "一种莫名",
        "一种难以",
        "难以言喻",
        "难以名状",
        "难以形容",
        "无法言说",
        "无法形容",
        "无以言表",
        "复杂的情绪",
        "复杂的心情",
        "五味杂陈",
        "百感交集",
        "心中五味",
        "说不清道不明",
        "莫名的情绪",
        "某种情感",
        "一丝异样",
        "一丝复杂",
        "一种前所未有",
        "某种默契",
        "某种共鸣",
        "某种联系",
        "一种宿命",
    ],
    # ② 万能形容 / 空洞修饰（放哪都行、等于没说）
    "empty_modifier": [
        "淡淡的",
        "淡淡地",
        "深深地",
        "深深的",
        "缓缓地",
        "缓缓的",
        "轻轻地",
        "轻轻的",
        "微微地",
        "微微一笑",
        "微微一顿",
        "嘴角勾起",
        "嘴角微微",
        "嘴角扬起",
        "嘴角泛起",
        "不易察觉",
        "若有若无",
        "若有所思",
        "意味深长",
        "意味不明",
        "神色复杂",
        "眼神复杂",
        "神情复杂",
        "深邃的目光",
        "深邃的眼眸",
        "清冷的气息",
        "淡漠的神情",
        "云淡风轻",
        "波澜不惊",
        "不动声色",
        "了然于心",
        "了然于胸",
    ],
    # ③ 翻译腔 / 书面僵硬（口语网文里不该出现的生硬连接与句式词）
    "translationese": [
        "不由得",
        "不由自主",
        "不禁",
        "情不自禁",
        "仿佛整个世界",
        "整个世界仿佛",
        "仿佛时间静止",
        "时间仿佛静止",
        "这一刻",
        "那一刻",
        "在这一瞬间",
        "在那一瞬间",
        "在这一刻",
        "与此同时",
        "毫无疑问",
        "无可否认",
        "不可否认",
        "值得一提的是",
        "众所周知",
        "显而易见",
        "换句话说",
        "更确切地说",
        "某种程度上",
        "在某种程度上",
        "如此这般",
        "正因如此",
        "也正因为如此",
        "无论如何",
        "不管怎样",
        "总而言之",
        "归根结底",
        "说到底",
    ],
    # ④ 情绪爆发套路词（写情绪爱堆的强度词）
    "emotion_cliche": [
        "内心深处",
        "灵魂深处",
        "心灵深处",
        "内心最柔软",
        "撕心裂肺",
        "肝肠寸断",
        "刻骨铭心",
        "痛彻心扉",
        "泪如雨下",
        "泪流满面",
        "热泪盈眶",
        "泪水夺眶",
        "泣不成声",
        "心如刀绞",
        "心如死灰",
        "万念俱灰",
        "五雷轰顶",
        "如遭雷击",
        "天旋地转",
        "手足无措",
        "不知所措",
        "百爪挠心",
        "五内俱焚",
        "肝胆俱裂",
        "痛不欲生",
    ],
    # ⑤ 感官/生理套路（AI 描身体反应的固定搭配）
    "sensory_cliche": [
        "一阵刺痛",
        "一阵眩晕",
        "一阵酸楚",
        "一阵暖流",
        "一股暖流",
        "一股寒意",
        "一阵寒意",
        "寒意袭来",
        "暖流涌上",
        "涌上心头",
        "涌上心间",
        "涌上鼻尖",
        "鼻尖一酸",
        "鼻子一酸",
        "喉咙发紧",
        "喉头一紧",
        "心头一颤",
        "心头一暖",
        "心头一紧",
        "心脏漏跳",
        "血液凝固",
        "浑身一颤",
        "遍体生寒",
        "汗毛倒竖",
        "头皮发麻",
    ],
    # ⑥ 动作套路（AI 写人物动作的万能填充）
    "action_cliche": [
        "深吸一口气",
        "深吸了一口气",
        "长舒一口气",
        "长出一口气",
        "深深吸了口气",
        "揉了揉眉心",
        "揉了揉太阳穴",
        "捏了捏眉心",
        "扶了扶额头",
        "顿了顿",
        "顿了一下",
        "微微颔首",
        "微不可查地",
        "几不可闻地",
        "下意识地",
        "鬼使神差地",
        "身形一顿",
        "脚步一顿",
        "动作一顿",
        "眸光一闪",
        "眼底闪过",
        "眼中闪过一丝",
        "眼神一凝",
        "瞳孔一缩",
        "眉头紧锁",
        "眉头微皱",
    ],
    # ⑦ 时间/场景转场套路
    "time_cliche": [
        "不知过了多久",
        "不知何时",
        "不知不觉",
        "曾几何时",
        "此时此刻",
        "此情此景",
        "夜幕降临",
        "夜色渐深",
        "华灯初上",
        "晨曦微露",
        "天边泛起鱼肚白",
        "空气仿佛凝固",
        "空气中弥漫着",
        "空气骤然",
        "时间一分一秒",
        "分秒流逝",
        "光阴荏苒",
        "岁月如梭",
        "转瞬即逝",
        "弹指一挥间",
    ],
    # ⑧ 认知/顿悟套路（AI 爱堆的「意识到/明白」升华）
    "cognition_cliche": [
        "他忽然明白",
        "她忽然明白",
        "忽然意识到",
        "蓦然回首",
        "恍然大悟",
        "如梦初醒",
        "幡然醒悟",
        "茅塞顿开",
        "醍醐灌顶",
        "豁然开朗",
        "心照不宣",
        "不言而喻",
        "了然",
        "释然",
        "怅然若失",
        "怅然",
        "若有所悟",
        "百思不得其解",
        "细思极恐",
        "冥冥之中",
    ],
    # ⑨ 程度堆砌（空洞强化副词，多余的强度词）
    "intensifier": [
        "无比",
        "格外",
        "异常",
        "极致",
        "极尽",
        "彻头彻尾",
        "前所未有",
        "史无前例",
        "无与伦比",
        "无可比拟",
        "登峰造极",
        "淋漓尽致",
        "空前绝后",
        "彻彻底底",
        "完完全全",
        "确确实实",
        "真真切切",
        "实实在在",
    ],
    # ⑩ 比喻/修辞套路（AI 爱用的书面比喻连接与陈词滥调喻体）
    "metaphor_cliche": [
        "仿佛一只",
        "宛如一只",
        "犹如一道",
        "宛如新生",
        "如同潮水",
        "如潮水般",
        "似潮水般",
        "决堤般",
        "如释重负",
        "如临大敌",
        "如坐针毡",
        "如芒在背",
        "行尸走肉",
        "困兽犹斗",
        "惊弓之鸟",
        "断了线的风筝",
        "断了线的木偶",
        "被抽走了所有力气",
        "像是被抽空",
        "灵魂被抽离",
    ],
}

# 合并为统计用的扁平集合（去重）。
BLACKLIST_WORDS: tuple[str, ...] = tuple(
    dict.fromkeys(word for group in _BLACKLIST_GROUPS.values() for word in group)
)


# ---------------------------------------------------------------------------
# 重度句式套路检测规则（7 层）。clean-room 自编正则/启发式。
# 前 4 层承 4.1 临时版（含其已修的假阳性回归约束），补 3 层至 7 层，覆盖 polish-guide
# 「7 层句式规则」思路里的其余套路类型。**命中即报、宁可多报交 polisher/人工复核**。
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PatternRule:
    """一条句式套路规则：name 供报告归类，pattern 是预编译正则，note 说明命中含义。"""

    name: str
    pattern: re.Pattern[str]
    note: str


# 中文标点集合（保留供后续切句/判句尾扩展用）。
_SENTENCE_END = "。！？…”"


def _compile(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern)


PATTERN_RULES: tuple[PatternRule, ...] = (
    # ① 「不是 X 而是 Y」对仗（伪深刻对仗滥用）。含常见变体「不是…，而是…」。
    PatternRule(
        name="not_x_but_y",
        pattern=_compile(r"不是[^，。！？；]{1,20}[，,]\s*而是"),
        note="「不是 X 而是 Y」对仗句式（伪深刻对仗滥用）",
    ),
    # ② 强行排比：连续三段以**同一实词**（≥2 字，非虚词）起头的分句。
    #    引导词限 2-4 字实词——1 字虚词（在/是/也/的）起头是自然叙事，不算套路
    #    （承 4.1 回归：「在说话，在走动，在拧发条」不该命中）。
    PatternRule(
        name="forced_parallel",
        pattern=_compile(
            r"([一-鿿]{2,4})[^，。！？；]{1,15}[，,]"
            r"\s*\1[^，。！？；]{1,15}[，,]"
            r"\s*\1[^，。！？；]{1,15}"
        ),
        note="连续三段同引导词排比（强行排比）",
    ),
    # ③ 万能金句结尾：句子以格言化、抽象升华收束（「或许，这就是……的意义。」）。
    PatternRule(
        name="aphorism_ending",
        pattern=_compile(
            r"(?:或许|也许|大概|这|那)[^，。！？；]{0,12}"
            r"(?:就是|便是|正是)[^。！？…]{0,20}"
            r"(?:的意义|的答案|的真相|的全部|的一切|的宿命|的命运)[。！？…]"
        ),
        note="万能金句式升华结尾（格言化收束）",
    ),
    # ④ 排比式抽象升华：三连短语 + 末句抽象名词升华收束。**必须末句带抽象升华名词**
    #    才算套路（承 4.1 假阳性修正：白描三分句「放了十三年，没人赎，也没人肯买断」不算）。
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
    # ⑤（新增）「与其说 X，不如说 Y」——伪深刻转折对仗（AI 爱的另一种对仗滥用）。
    PatternRule(
        name="antithesis_uplift",
        pattern=_compile(r"与其说[^，。！？；]{1,20}[，,]\s*不如说"),
        note="「与其说 X 不如说 Y」转折对仗（伪深刻）",
    ),
    # ⑥（新增）设问自答式煽情：「什么是 X？X 就是……」/「何为 X？」式反问自答。
    #    限「什么是/何为」起头 + 问号 + 「就是/便是/正是」承接，避免误伤普通疑问句。
    PatternRule(
        name="rhetorical_qa",
        pattern=_compile(
            r"(?:什么是|何为|何谓)[^，。！？；]{1,12}[？?]"
            r"[^。！？…]{0,20}(?:就是|便是|正是)"
        ),
        note="设问自答式升华（「什么是 X？X 就是…」煽情反问）",
    ),
    # ⑦（新增）连续短感叹堆砌：连续 ≥3 个以感叹号收束的短句（煽情式感叹轰炸）。
    #    每段限 1-15 字，避免把长句误判；三连感叹是 AI 煽情高发套路。
    PatternRule(
        name="exclamation_barrage",
        pattern=_compile(
            r"[^。！？…]{1,15}！\s*[^。！？…]{1,15}！\s*[^。！？…]{1,15}！"
        ),
        note="连续三句短感叹堆砌（煽情式感叹轰炸）",
    ),
)


# ---------------------------------------------------------------------------
# 统计结果结构（与临时版一致，供共用测试范式与报告口径）
# ---------------------------------------------------------------------------


@dataclass
class BlacklistHit:
    """单个黑名单词命中：word + 出现次数。"""

    word: str
    count: int


@dataclass
class PatternHit:
    """单条句式套路命中：rule_name + note + 命中的原文片段列表（供人工/polisher 复核）。"""

    rule_name: str
    note: str
    snippets: list[str] = field(default_factory=list)


@dataclass
class AxisBStats:
    """一段正文的轴 B 统计结果。

    - char_count：计频用的字符数（用于千字归一）。
    - blacklist_total：黑名单命中总次数。
    - blacklist_per_kchar：每千字命中数（= blacklist_total / char_count * 1000）。
    - blacklist_hits：逐词命中明细（供报告）。
    - pattern_total：重度句式套路命中总数。
    - pattern_hits：逐规则命中明细（含原文片段，供人工/polisher 复核）。
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
    足够。只收 count>0 的词进明细，按出现次数降序便于报告聚焦。
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

    每条规则取全部命中，命中数累加。明细保留原文片段供复核——套路检测是启发式、宁可
    多报，polisher/人工据片段判真伪（延续 4.1 判据局限说明）。
    """
    hits: list[PatternHit] = []
    total = 0
    for rule in PATTERN_RULES:
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

    polisher step 用它对 drafter 正文自查，据命中信号做去 AI 味改写（AR15）。
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


def format_lexicon_constraints() -> str:
    """把黑名单代表词 + 句式套路规则压成一段**写作约束文本**，注入 drafter/polisher 消息。

    用于流水线：drafter 写前告知「避免这些 AI 味」，polisher 据此自查改写（AR15 词表叠加
    style_profile）。不逐字塞 200+ 词（挤占 token 且模型不需穷举），给分组代表 + 规则说明。
    """
    lines = ["【去 AI 味约束（写作时规避以下套路）】"]
    lines.append("· 忌用空洞抽象词与万能修饰，例如：" + "、".join(
        _BLACKLIST_GROUPS["empty_modifier"][:6]
        + _BLACKLIST_GROUPS["abstraction"][:4]
    ))
    lines.append("· 忌堆砌情绪/感官套语，例如：" + "、".join(
        _BLACKLIST_GROUPS["emotion_cliche"][:4]
        + _BLACKLIST_GROUPS["sensory_cliche"][:4]
    ))
    lines.append("· 忌翻译腔与书面连接词，例如：" + "、".join(
        _BLACKLIST_GROUPS["translationese"][:6]
    ))
    lines.append("· 忌下列句式套路：")
    for rule in PATTERN_RULES:
        lines.append(f"  - {rule.note}")
    lines.append("· 多用具体的动作、场景、对白与细节；少用概括、升华、金句式收尾。")
    return "\n".join(lines)
