"""
标题模式分析
使用 jieba 分词提取关键词，分析标题结构
"""

import re
import logging
from collections import Counter

logger = logging.getLogger(__name__)

# 尝试导入 jieba
try:
    import jieba
    jieba.setLogLevel(logging.WARNING)
    HAS_JIEBA = True
except ImportError:
    HAS_JIEBA = False
    logger.warning("jieba 未安装，标题关键词分析将使用简单模式 (pip install jieba)")


def analyze_title(books):
    """
    分析标题模式：
    - 长度分布
    - 高频关键词
    - 结构模式
    """
    if not books:
        return {}

    titles = [b.get("title", "") for b in books if b.get("title")]
    if not titles:
        return {}

    result = {}

    # ── 长度分析 ──
    lengths = [len(t) for t in titles]
    avg_len = sum(lengths) / len(lengths) if lengths else 0
    result["length"] = {
        "average": round(avg_len, 1),
        "min": min(lengths) if lengths else 0,
        "max": max(lengths) if lengths else 0,
        "distribution": _length_distribution(lengths),
    }

    # ── 关键词 ──
    result["keywords"] = _extract_keywords(titles)

    # ── 结构模式 ──
    result["patterns"] = _analyze_patterns(titles)

    # ── 首字分析 ──
    first_chars = Counter(t[0] for t in titles if t)
    result["firstChars"] = [
        {"char": c, "count": n}
        for c, n in first_chars.most_common(10)
    ]

    logger.info(f"标题分析: {len(titles)} 个标题, 平均长度{avg_len:.1f}字")
    return result


def _length_distribution(lengths):
    """长度区间分布"""
    ranges = [
        (1, 3, "1-3字"),
        (4, 6, "4-6字"),
        (7, 10, "7-10字"),
        (11, 15, "11-15字"),
        (16, 99, "16字以上"),
    ]
    result = []
    for lo, hi, label in ranges:
        count = sum(1 for l in lengths if lo <= l <= hi)
        if count > 0:
            result.append({
                "range": label,
                "count": count,
                "pct": round(count / len(lengths) * 100, 1),
            })
    return result


def _extract_keywords(titles):
    """提取高频关键词"""
    if HAS_JIEBA:
        words = []
        stop_words = set("的了是在我他她它们这那个有不人大为上中")
        stop_words.update({"一个", "什么", "没有", "不是", "他们", "我们", "自己", "什么"})
        for t in titles:
            for word in jieba.cut(t):
                if len(word) >= 2 and word not in stop_words:
                    words.append(word)
        counter = Counter(words)
        return [
            {"word": w, "count": c}
            for w, c in counter.most_common(20)
        ]
    else:
        # 简单模式：提取2-4字子串
        ngram_counter = Counter()
        for t in titles:
            for n in (2, 3, 4):
                for i in range(len(t) - n + 1):
                    gram = t[i:i + n]
                    if not re.match(r'^[\s\d\W]+$', gram):
                        ngram_counter[gram] += 1
        # 只保留出现2次以上的
        return [
            {"word": w, "count": c}
            for w, c in ngram_counter.most_common(20)
            if c >= 2
        ]


def _analyze_patterns(titles):
    """分析标题结构模式"""
    patterns = {
        "冒号分隔": 0,     # XX：XXXX
        "书名号": 0,       # 《XXX》
        "问句": 0,         # ？/怎么/如何/为什么
        "我在XX": 0,       # 我在XX当/成了/...
        "数字开头": 0,     # 1990/一/第一...
        "人名/称呼": 0,    # X哥/X爷/X总
        "系统/金手指": 0,  # 系统/面板/签到/模拟
        "重生/穿越": 0,    # 重生/穿越/回到
        "全球/全民": 0,    # 全球/全民/全世界
    }

    for t in titles:
        if "：" in t or ":" in t:
            patterns["冒号分隔"] += 1
        if "？" in t or "?" in t or any(w in t for w in ["怎么", "如何", "为什么"]):
            patterns["问句"] += 1
        if t.startswith("我在"):
            patterns["我在XX"] += 1
        if re.match(r'^[\d一二三四五六七八九十]', t):
            patterns["数字开头"] += 1
        if any(w in t for w in ["哥", "爷", "总", "姐", "嫂"]):
            patterns["人名/称呼"] += 1
        if any(w in t for w in ["系统", "面板", "签到", "模拟器", "金手指", "商城"]):
            patterns["系统/金手指"] += 1
        if any(w in t for w in ["重生", "穿越", "回到", "回到过去"]):
            patterns["重生/穿越"] += 1
        if any(w in t for w in ["全球", "全民", "全世界", "诸天"]):
            patterns["全球/全民"] += 1

    total = len(titles) or 1
    return [
        {"pattern": k, "count": v, "pct": round(v / total * 100, 1)}
        for k, v in sorted(patterns.items(), key=lambda x: -x[1])
        if v > 0
    ]
