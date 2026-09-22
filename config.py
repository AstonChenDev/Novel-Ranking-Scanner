"""
小说排行榜扫描 - 配置常量
"""

# ─── 榜单配置 ──────────────────────────────────────────────────

QIDIAN_RANKINGS = {
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

# 兼容旧代码：默认榜单仍然指向起点。
RANKINGS = QIDIAN_RANKINGS

FANQIE_RANKINGS = {
    "male_read": {
        "name": "男频阅读榜",
        "url": "https://fanqienovel.com/rank/1_2",
        "gender": "male",
        "rankType": "read",
    },
    "male_new": {
        "name": "男频新书榜",
        "url": "https://fanqienovel.com/rank/1_1",
        "gender": "male",
        "rankType": "new",
    },
    "female_read": {
        "name": "女频阅读榜",
        "url": "https://fanqienovel.com/rank/0_2",
        "gender": "female",
        "rankType": "read",
    },
    "female_new": {
        "name": "女频新书榜",
        "url": "https://fanqienovel.com/rank/0_1",
        "gender": "female",
        "rankType": "new",
    },
}

# 短剧榜单使用平台原始公开读取端点。榜单 key 带平台前缀，避免跨平台
# 合并配置时 ``hot`` / ``new`` 等通用名称互相覆盖。
HONGGUO_RANKINGS = {
    "hongguo_hot_all": {
        "name": "红果热播总榜",
        "route": "hot-drama",
        "contentForm": "mixed",
    },
    "hongguo_hot_real": {
        "name": "红果真人剧热播榜",
        "route": "hot-real-drama",
        "contentForm": "real_drama",
    },
    "hongguo_hot_ai": {
        "name": "红果AI剧热播榜",
        "route": "hot-ai-drama",
        "contentForm": "ai_drama",
    },
    "hongguo_hot_comic": {
        "name": "红果漫剧热播榜",
        "route": "hot-comic-drama",
        "contentForm": "comic_drama",
    },
}

DOUYIN_RANKINGS = {
    "douyin_hot": {"name": "抖音短剧热播榜", "billboardType": 1},
    "douyin_comic": {"name": "抖音短剧漫剧榜", "billboardType": 2},
    "douyin_new": {"name": "抖音短剧新剧榜", "billboardType": 3},
    "douyin_interaction": {"name": "抖音短剧互动榜", "billboardType": 4},
    "douyin_must_watch": {"name": "抖音短剧必看榜", "billboardType": 8},
}

KUAISHOU_RANKINGS = {
    "kuaishou_all_hot": {"name": "快手短剧全网热播榜", "classifyId": 13},
    "kuaishou_recommend": {"name": "快手短剧推荐榜", "classifyId": 0},
    "kuaishou_hot": {"name": "快手短剧热播榜", "classifyId": 10},
    "kuaishou_real": {"name": "快手短剧真人榜", "classifyId": 12},
    "kuaishou_comic": {"name": "快手短剧漫剧榜", "classifyId": 1},
    "kuaishou_must_watch": {"name": "快手短剧必看榜", "classifyId": 2},
    "kuaishou_xingmang": {"name": "快手短剧星芒榜", "classifyId": 11},
    "kuaishou_time_travel": {"name": "快手短剧穿越榜", "classifyId": 9},
    "kuaishou_costume": {"name": "快手短剧古风榜", "classifyId": 8},
    "kuaishou_fantasy": {"name": "快手短剧脑洞榜", "classifyId": 7},
    "kuaishou_family": {"name": "快手短剧家庭榜", "classifyId": 6},
    "kuaishou_romance": {"name": "快手短剧甜宠榜", "classifyId": 4},
    "kuaishou_comeback": {"name": "快手短剧逆袭榜", "classifyId": 3},
    "kuaishou_urban": {"name": "快手短剧都市榜", "classifyId": 5},
}

DEFAULT_SITE = "qidian"
SITE_NAMES = {
    "qidian": "起点中文网",
    "fanqie": "番茄小说",
    "hongguo": "红果短剧",
    "douyin": "抖音短剧",
    "kuaishou": "快手短剧",
}
SITE_RANKINGS = {
    "qidian": QIDIAN_RANKINGS,
    "fanqie": FANQIE_RANKINGS,
    "hongguo": HONGGUO_RANKINGS,
    "douyin": DOUYIN_RANKINGS,
    "kuaishou": KUAISHOU_RANKINGS,
}
ALL_RANKINGS = {
    rank_key: config
    for rankings in SITE_RANKINGS.values()
    for rank_key, config in rankings.items()
}


def get_site_rankings(site=DEFAULT_SITE):
    """返回指定站点的榜单配置。"""
    return SITE_RANKINGS.get(site or DEFAULT_SITE, QIDIAN_RANKINGS)


def get_site_name(site=DEFAULT_SITE):
    """返回站点中文名。"""
    site = site or DEFAULT_SITE
    return SITE_NAMES.get(site, site)


def get_rank_name(rank_key):
    """跨站点获取榜单中文名。"""
    return ALL_RANKINGS.get(rank_key, {}).get("name", rank_key or "未知榜单")

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
FANQIE_MAX_PAGES_PER_RANK = 10  # 防失控的页数上限；API每页50本，通常两页抓完100名
SHORT_DRAMA_MAX_PAGES_PER_RANK = 10  # 红果/抖音通常5～7页，留出接口扩容余量
CONSECUTIVE_403_THRESHOLD = 3   # 触发暂停的连续403次数

# ─── 筛选参数 ──────────────────────────────────────────────────

FILTER_MONTHS = 6               # 保留几个月内的书籍
MAX_AUTHOR_LEVEL = 5            # 保留此等级及以下的作者

# ─── 起点域名 ──────────────────────────────────────────────────

QIDIAN_BASE = "https://www.qidian.com"
QIDIAN_BOOK = "https://book.qidian.com"
QIDIAN_MOBILE = "https://m.qidian.com"
QIDIAN_MOBILE_AJAX = "https://m.qidian.com/majax"
FANQIE_BASE = "https://fanqienovel.com"
HONGGUO_BASE = "https://hongguoduanju.com"
DOUYIN_DRAMA_BILLBOARD = "https://api.amemv.com/aweme/v1/series/billboard/"
KUAISHOU_DRAMA_BILLBOARD = "https://api.e.kuaishou.com/rest/miniSeries/wd/hotRank/queryListNew"

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

FANQIE_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# ─── 输出目录 ──────────────────────────────────────────────────

DEFAULT_OUTPUT_DIR = "output"
