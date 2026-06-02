"""
作者等级分布分析
"""

import logging
from collections import Counter, defaultdict

from config import AUTHOR_LEVELS, MAX_AUTHOR_LEVEL
from analysis.ranks import get_book_ranks

logger = logging.getLogger(__name__)


def analyze_author(books):
    """
    分析作者等级分布：
    - 总体等级分布
    - 新人占比
    - 各榜单新人比例
    """
    if not books:
        return {}

    # 等级统计
    level_counter = Counter()
    rank_level_counters = defaultdict(Counter)
    no_level_count = 0

    for book in books:
        level = book.get("authorLevel")
        ranks = get_book_ranks(book) or ["未知"]

        if level is not None:
            if isinstance(level, str):
                import re
                m = re.search(r'(\d+)', level)
                level = int(m.group(1)) if m else None

            if level is not None:
                label = AUTHOR_LEVELS.get(level, f"LV{level}")
                level_counter[label] += 1
                for rank in ranks:
                    rank_level_counters[rank][label] += 1
            else:
                no_level_count += 1
        else:
            no_level_count += 1

    total_with_level = sum(level_counter.values())
    total = len(books)

    # 总体分布
    level_dist = [
        {"level": lv, "count": c, "pct": round(c / total_with_level * 100, 1) if total_with_level else 0}
        for lv, c in sorted(level_counter.items(), key=lambda x: _level_sort_key(x[0]))
    ]

    # 新人占比 (LV5及以下)
    newbie_count = sum(c for lv, c in level_counter.items() if _level_value(lv) <= MAX_AUTHOR_LEVEL)
    newbie_pct = round(newbie_count / total_with_level * 100, 1) if total_with_level else 0

    # 各榜单新人比例
    rank_newbie = {}
    for rank, counter in rank_level_counters.items():
        rank_total = sum(counter.values())
        rank_newbie_count = sum(c for lv, c in counter.items() if _level_value(lv) <= MAX_AUTHOR_LEVEL)
        rank_newbie[rank] = {
            "total": rank_total,
            "newbie": rank_newbie_count,
            "pct": round(rank_newbie_count / rank_total * 100, 1) if rank_total else 0,
        }

    # 新人成功案例 (LV5以下且上榜)
    newbie_books = []
    for book in books:
        level = book.get("authorLevel")
        if level is not None:
            if isinstance(level, str):
                import re
                m = re.search(r'(\d+)', level)
                level = int(m.group(1)) if m else None
            if level is not None and level <= MAX_AUTHOR_LEVEL:
                newbie_books.append({
                    "title": book.get("title", ""),
                    "author": book.get("author", ""),
                    "level": AUTHOR_LEVELS.get(level, f"LV{level}"),
                    "category": book.get("category", ""),
                    "ranks": get_book_ranks(book),
                    "wordCount": book.get("wordCount", 0),
                })

    result = {
        "distribution": level_dist,
        "totalBooks": total,
        "totalWithLevel": total_with_level,
        "noLevelCount": no_level_count,
        "newbie": {
            "count": newbie_count,
            "pct": newbie_pct,
        },
        "byRank": rank_newbie,
        "newbieBooks": newbie_books[:20],  # Top 20
    }

    logger.info(f"作者分析: 新人占比 {newbie_pct}% ({newbie_count}/{total_with_level})")
    return result


def _level_sort_key(label):
    """排序用：将等级标签转换为数值"""
    if label.startswith("LV"):
        try:
            return int(label[2:])
        except ValueError:
            return 99
    if label == "大神":
        return 10
    if label == "普通":
        return 0
    return 99


def _level_value(label):
    """等级标签转数值"""
    if label.startswith("LV"):
        try:
            return int(label[2:])
        except ValueError:
            return 99
    if label == "大神":
        return 10
    if label == "普通":
        return 0
    return 99
