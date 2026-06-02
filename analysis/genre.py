"""
分类/题材分布分析
"""

import logging
from collections import Counter, defaultdict

from analysis.ranks import get_book_ranks

logger = logging.getLogger(__name__)


def analyze_genre(books):
    """
    分析分类分布。
    返回: 总体分布 + 各榜单分布
    """
    if not books:
        return {"total": {}, "byRank": {}}

    # 总体分布
    total_counter = Counter()
    # 按榜单分布
    rank_counters = defaultdict(Counter)

    for book in books:
        cat = book.get("category", "未知")
        total_counter[cat] += 1
        ranks = get_book_ranks(book) or ["未知"]
        for rank in ranks:
            rank_counters[rank][cat] += 1

    # 排序
    total_sorted = sorted(total_counter.items(), key=lambda x: -x[1])
    total = [
        {"category": cat, "count": count, "pct": round(count / len(books) * 100, 1)}
        for cat, count in total_sorted
    ]

    # 各榜单分布
    by_rank = {}
    for rank, counter in rank_counters.items():
        rank_total = sum(counter.values())
        rank_sorted = sorted(counter.items(), key=lambda x: -x[1])
        by_rank[rank] = [
            {"category": cat, "count": count, "pct": round(count / rank_total * 100, 1)}
            for cat, count in rank_sorted
        ]

    # 热门分类 Top3
    top3 = [item["category"] for item in total[:3]]

    result = {
        "total": total,
        "byRank": by_rank,
        "topCategories": top3,
        "categoryCount": len(total_counter),
    }

    logger.info(f"分类分析: {len(total_counter)} 个分类, Top3={top3}")
    return result
