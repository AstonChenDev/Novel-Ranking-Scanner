"""
起点中文网排行榜扫描 - 配置常量
"""

# ─── 榜单配置 ──────────────────────────────────────────────────

RANKINGS = {
    "sanjiang": {
        "name": "三江推荐",
        "url": "https://www.qidian.com/rank/sanjiang/",
        "mobile_url": "https://m.qidian.com/sanjiang/",
    },
    "strong": {
        "name": "强推榜",
        "url": "https://www.qidian.com/rank/strong/",
        "mobile_url": "https://m.qidian.com/strongrec/",
    },
    "newbook": {
        "name": "新书榜",
        "url": "https://www.qidian.com/rank/newbook/",
        "mobile_url": "https://m.qidian.com/rank/newbook/",
    },
    "hotsales": {
        "name": "畅销榜",
        "url": "https://www.qidian.com/rank/hotsales/",
        "mobile_url": "https://m.qidian.com/rank/hotsales/",
    },
}

# ─── 分类ID ────────────────────────────────────────────────────

CATEGORIES = {
    1: "玄幻", 2: "奇幻", 3: "武侠", 4: "仙侠", 5: "都市",
    6: "现实", 7: "军事", 8: "历史", 9: "游戏", 10: "体育",
    11: "科幻", 12: "灵异", 13: "同人", 14: "轻小说", 15: "悬疑",
}

# ─── 作者等级 ──────────────────────────────────────────────────

AUTHOR_LEVELS = {
    0: "普通", 1: "LV1", 2: "LV2", 3: "LV3", 4: "LV4",
    5: "LV5", 6: "LV6", 7: "LV7", 8: "LV8", 9: "LV9", 10: "大神",
}

# ─── 请求参数 ──────────────────────────────────────────────────

REQUEST_DELAY = (2, 5)          # 请求间随机延迟（秒）
DETAIL_DELAY = (3, 6)           # 详情页延迟（更保守）
BACKOFF_DELAY = (10, 20)        # 403后退避延迟
PENALTY_PAUSE = 60              # 连续3次403后暂停（秒）
MAX_RETRIES = 3                 # 最大重试次数
REQUEST_TIMEOUT = 20            # 请求超时（秒）
MAX_PAGES_PER_RANK = 5          # 每个榜单最大翻页数
CONSECUTIVE_403_THRESHOLD = 3   # 触发暂停的连续403次数

# ─── 筛选参数 ──────────────────────────────────────────────────

FILTER_MONTHS = 6               # 保留几个月内的书籍
MAX_AUTHOR_LEVEL = 5            # 保留此等级及以下的作者

# ─── 起点域名 ──────────────────────────────────────────────────

QIDIAN_BASE = "https://www.qidian.com"
QIDIAN_BOOK = "https://book.qidian.com"
QIDIAN_MOBILE = "https://m.qidian.com"
QIDIAN_MOBILE_AJAX = "https://m.qidian.com/majax"

# ─── User-Agent 列表 ──────────────────────────────────────────

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
]

MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 "
    "Mobile/15E148 Safari/604.1"
)

# ─── 输出目录 ──────────────────────────────────────────────────

DEFAULT_OUTPUT_DIR = "output"
