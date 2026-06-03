"""
榜单元数据辅助函数。
"""

from config import ALL_RANKINGS


RANK_ORDER = {rank: index for index, rank in enumerate(ALL_RANKINGS)}


def sort_ranks(ranks):
    """按配置顺序稳定排序榜单 key。"""
    return sorted(ranks, key=lambda rank: (RANK_ORDER.get(rank, 999), rank))


def get_book_ranks(book):
    """从书籍记录中提取去重后的榜单 key。"""
    ranks = []

    for appearance in book.get("rankAppearances", []) or []:
        if isinstance(appearance, dict):
            rank = appearance.get("rankType")
            if rank:
                ranks.append(rank)

    for rank in book.get("ranks", []) or []:
        if rank:
            ranks.append(rank)

    rank = book.get("rankType")
    if rank:
        ranks.append(rank)

    return sort_ranks(set(ranks))
