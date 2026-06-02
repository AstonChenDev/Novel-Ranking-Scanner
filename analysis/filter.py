"""
书籍筛选：按发布时间和作者等级过滤
"""

import logging
from datetime import datetime, timedelta

from config import FILTER_MONTHS, MAX_AUTHOR_LEVEL

logger = logging.getLogger(__name__)


def filter_books(books, months=FILTER_MONTHS, max_level=MAX_AUTHOR_LEVEL):
    """
    筛选书籍：
    1. 发布时间在 N 个月内
    2. 作者等级 <= max_level
    """
    if not books:
        return []

    cutoff = datetime.now() - timedelta(days=months * 30)
    cutoff_str = cutoff.strftime("%Y-%m-%d")

    filtered = []
    skipped_date = 0
    skipped_level = 0
    no_date = 0

    for book in books:
        # 日期筛选
        pub_date = book.get("publishDate", "")
        if pub_date:
            # 处理不同日期格式
            try:
                if "年" in pub_date:
                    pub_date = pub_date.replace("年", "-").replace("月", "-").replace("日", "")
                dt = datetime.strptime(pub_date[:10], "%Y-%m-%d")
                if dt < cutoff:
                    skipped_date += 1
                    continue
            except ValueError:
                no_date += 1
                # 无法解析日期，保留（可能缺少日期信息）
        else:
            no_date += 1

        # 作者等级筛选
        level = book.get("authorLevel")
        if level is not None:
            if isinstance(level, str):
                # 尝试解析 "LV5" 格式
                import re
                m = re.search(r'(\d+)', level)
                level = int(m.group(1)) if m else None
            if level is not None and level > max_level:
                skipped_level += 1
                continue

        filtered.append(book)

    logger.info(f"筛选结果: {len(books)} → {len(filtered)}")
    logger.info(f"  跳过: 日期超限={skipped_date}, 等级过高={skipped_level}, 无日期={no_date}")

    return filtered
