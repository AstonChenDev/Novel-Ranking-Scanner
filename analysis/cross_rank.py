"""
跨榜上榜分析
识别同时出现在多个榜单上的书籍
"""

import logging
from collections import Counter, defaultdict

from analysis.ranks import get_book_ranks, sort_ranks

logger = logging.getLogger(__name__)


def analyze_cross_rank(books):
    """
    分析跨榜上榜情况：
    - 书籍-榜单映射
    - 多榜上榜书籍列表
    - 各榜单独占/共享统计
    """
    if not books:
        return {}

    # bookId → 出现在哪些榜单
    book_ranks = defaultdict(set)
    book_info = {}

    for book in books:
        bid = book.get("bookId", "")
        ranks = get_book_ranks(book)
        if not bid or not ranks:
            continue

        book_ranks[bid].update(ranks)
        if bid not in book_info:
            book_info[bid] = {
                "bookId": bid,
                "title": book.get("title", ""),
                "author": book.get("author", ""),
                "authorLevel": book.get("authorLevel"),
                "category": book.get("category", ""),
                "wordCount": book.get("wordCount", 0),
                "synopsis_short": book.get("synopsis_short", ""),
            }

    # 统计
    rank_count_dist = Counter()
    for bid, ranks in book_ranks.items():
        rank_count_dist[len(ranks)] += 1

    # 多榜上榜书籍（2个及以上榜单）
    multi_rank_books = []
    for bid, ranks in book_ranks.items():
        if len(ranks) >= 2:
            info = book_info.get(bid, {})
            multi_rank_books.append({
                **info,
                "rankCount": len(ranks),
                "ranks": sort_ranks(ranks),
            })

    # 按上榜数排序
    multi_rank_books.sort(key=lambda x: (-x["rankCount"], x["title"]))

    # 各榜单独占/共享
    rank_stats = {}
    for book in books:
        bid = book.get("bookId", "")
        ranks = get_book_ranks(book)
        if not bid or not ranks:
            continue
        for rank in ranks:
            if rank not in rank_stats:
                rank_stats[rank] = {"total": 0, "exclusive": 0, "shared": 0}
            rank_stats[rank]["total"] += 1
            if len(book_ranks[bid]) == 1:
                rank_stats[rank]["exclusive"] += 1
            else:
                rank_stats[rank]["shared"] += 1

    total_unique = len(book_ranks)

    result = {
        "totalUniqueBooks": total_unique,
        "distribution": [
            {"rankCount": n, "bookCount": c}
            for n, c in sorted(rank_count_dist.items())
        ],
        "multiRankBooks": multi_rank_books,
        "rankStats": rank_stats,
    }

    logger.info(f"跨榜分析: {total_unique} 本, 多榜上榜 {len(multi_rank_books)} 本")
    return result
