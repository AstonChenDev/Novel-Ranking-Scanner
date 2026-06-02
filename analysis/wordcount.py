"""
字数分布分析
"""

import logging
from collections import Counter, defaultdict

from analysis.ranks import get_book_ranks

logger = logging.getLogger(__name__)


def analyze_wordcount(books):
    """
    分析字数分布：
    - 总体字数区间分布
    - 各榜单字数分布
    - 字数统计
    """
    if not books:
        return {}

    # 字数区间定义
    ranges = [
        (0, 100000, "10万以下"),
        (100000, 300000, "10-30万"),
        (300000, 500000, "30-50万"),
        (500000, 1000000, "50-100万"),
        (1000000, 3000000, "100-300万"),
        (3000000, float("inf"), "300万以上"),
    ]

    total_counter = Counter()
    rank_counters = defaultdict(Counter)
    word_counts = []

    for book in books:
        wc = book.get("wordCount", 0)
        if not isinstance(wc, (int, float)) or wc <= 0:
            continue

        wc = int(wc)
        word_counts.append(wc)
        ranks = get_book_ranks(book) or ["未知"]

        label = _get_range_label(wc, ranges)
        total_counter[label] += 1
        for rank in ranks:
            rank_counters[rank][label] += 1

    if not word_counts:
        return {}

    # 总体分布
    total = len(word_counts)
    dist = []
    for _, _, label in ranges:
        count = total_counter.get(label, 0)
        if count > 0:
            dist.append({
                "range": label,
                "count": count,
                "pct": round(count / total * 100, 1),
            })

    # 各榜单分布
    by_rank = {}
    for rank, counter in rank_counters.items():
        rank_total = sum(counter.values())
        by_rank[rank] = [
            {"range": label, "count": c, "pct": round(c / rank_total * 100, 1)}
            for _, _, label in ranges
            if (c := counter.get(label, 0)) > 0
        ]

    # 统计
    avg_wc = sum(word_counts) / len(word_counts)
    word_counts_sorted = sorted(word_counts)
    median = word_counts_sorted[len(word_counts_sorted) // 2]

    result = {
        "distribution": dist,
        "byRank": by_rank,
        "stats": {
            "count": total,
            "average": int(avg_wc),
            "averageWan": round(avg_wc / 10000, 1),
            "median": median,
            "medianWan": round(median / 10000, 1),
            "min": min(word_counts),
            "max": max(word_counts),
        },
    }

    logger.info(f"字数分析: {total} 本, 平均{avg_wc/10000:.1f}万字, 中位数{median/10000:.1f}万字")
    return result


def _get_range_label(wc, ranges):
    for lo, hi, label in ranges:
        if lo <= wc < hi:
            return label
    return "未知"
