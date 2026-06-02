"""
简介开篇风格分析
分析简介的开篇类型和写作模式
"""

import re
import logging
from collections import Counter

logger = logging.getLogger(__name__)


def analyze_synopsis(books):
    """
    分析简介开篇风格：
    - 开篇类型（对话/场景/动作/独白/设定）
    - 首句模式
    - 常见开篇词
    """
    if not books:
        return {}

    synopses = []
    for b in books:
        text = b.get("synopsis") or b.get("synopsis_short", "")
        if text:
            synopses.append(text)

    if not synopses:
        return {}

    result = {}

    # ── 开篇类型 ──
    result["hookTypes"] = _classify_hooks(synopses)

    # ── 首句分析 ──
    result["firstSentence"] = _analyze_first_sentence(synopses)

    # ── 简介长度 ──
    lengths = [len(s) for s in synopses]
    result["length"] = {
        "average": round(sum(lengths) / len(lengths), 0),
        "min": min(lengths),
        "max": max(lengths),
    }

    # ── 高频词 ──
    result["commonWords"] = _extract_common_words(synopses)

    logger.info(f"简介分析: {len(synopses)} 本")
    return result


def _classify_hooks(synopses):
    """分类简介开篇类型"""
    counters = Counter()

    for text in synopses:
        opening = text[:50]  # 前50字

        # 对话式开篇
        if re.match(r'^[""「【]', opening) or re.search(r'[""「].*[""」]', opening[:30]):
            counters["对话式"] += 1
        # 动作/冲突
        elif any(w in opening for w in [
            "忽然", "突然", "猛地", "一脚", "一拳", "冲", "跑", "杀",
            "爆炸", "坠落", "醒来", "睁开眼", "一脚踹",
        ]):
            counters["动作/冲突"] += 1
        # 场景描写
        elif any(w in opening for w in [
            "夜", "月", "风", "雨", "山", "城", "海", "天空",
            "清晨", "黄昏", "黑暗", "阳光",
        ]):
            counters["场景描写"] += 1
        # 独白/内心
        elif any(w in opening for w in [
            "我叫", "我是一个", "我原本", "我曾经", "没想到",
            "万万没想到", "谁曾想",
        ]):
            counters["独白/内心"] += 1
        # 设定/世界观
        elif any(w in opening for w in [
            "公元", "这个世界", "在这个世界", "据说", "传说",
            "某年", "XX年", "故事发生",
        ]):
            counters["设定说明"] += 1
        # 问题/悬念
        elif any(w in opening for w in [
            "如果", "假如", "当你", "当你发现", "你知道",
        ]):
            counters["问题/悬念"] += 1
        else:
            counters["其他"] += 1

    total = len(synopses) or 1
    return [
        {"type": t, "count": c, "pct": round(c / total * 100, 1)}
        for t, c in counters.most_common()
    ]


def _analyze_first_sentence(synopses):
    """分析首句特征"""
    first_sentences = []
    for text in synopses:
        # 取第一句话
        m = re.match(r'^([^。！？\n]+[。！？]?)', text)
        if m:
            first_sentences.append(m.group(1))

    if not first_sentences:
        return {}

    # 首句长度
    lengths = [len(s) for s in first_sentences]

    # 首句开头词
    openers = Counter()
    for s in first_sentences:
        if len(s) >= 2:
            # 取前2-4个字作为开头模式
            openers[s[:2]] += 1

    return {
        "averageLength": round(sum(lengths) / len(lengths), 1),
        "topOpeners": [
            {"word": w, "count": c}
            for w, c in openers.most_common(10)
            if c >= 2
        ],
    }


def _extract_common_words(synopses):
    """提取简介中的常见词"""
    # 简单双字词频
    counter = Counter()
    for text in synopses:
        # 简单切分
        for i in range(len(text) - 1):
            bigram = text[i:i + 2]
            if re.match(r'^[一-鿿]{2}$', bigram):
                counter[bigram] += 1

    # 过滤停用词
    stop_words = set("的了是在我他她它们这那个有不人大为上中下来出会生到作时要")
    filtered = [(w, c) for w, c in counter.most_common(30) if w not in stop_words]

    return [
        {"word": w, "count": c}
        for w, c in filtered[:15]
    ]
