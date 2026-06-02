"""
起点排行榜列表爬取
支持桌面端 SSR 解析 + 移动端 API 备选
"""

import re
import json
import logging
import subprocess
from datetime import datetime
from urllib.parse import urljoin, urlencode

from bs4 import BeautifulSoup

from config import (
    RANKINGS, QIDIAN_BASE, MAX_PAGES_PER_RANK, MOBILE_USER_AGENT,
)

logger = logging.getLogger(__name__)


MOBILE_HEADERS = {
    "User-Agent": MOBILE_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Referer": "https://m.qidian.com/",
}


# ─── 桌面端 HTML 解析 ─────────────────────────────────────────

def parse_ranking_page(html, rank_key):
    """
    解析桌面端排行榜页面 HTML。
    返回书籍列表 [dict, ...]
    """
    soup = BeautifulSoup(html, "lxml")
    books = []

    if _looks_like_block_page(html):
        logger.warning(f"[{rank_key}] 桌面端返回风控/探测页，准备使用移动端 SSR")
        return books

    # 策略1: 标准 book-img-text 结构
    items = soup.select("ul.all-img-list li") or soup.select("div.book-img-text ul li")

    if not items:
        # 策略2: rank-specific 结构（三江/强推可能不同）
        items = soup.select("div.rank-list li") or soup.select("ul.rank-list li")

    if not items:
        # 策略3: 通用 - 查找所有包含书籍链接的列表项
        items = soup.select("li")

    if not items:
        logger.warning(f"[{rank_key}] 未找到书籍列表项，保存 HTML 用于调试")
        _save_debug_html(html, rank_key)
        return books

    for idx, li in enumerate(items, 1):
        try:
            book = _parse_book_item(li, idx, rank_key)
            if book and book.get("bookId"):
                books.append(book)
        except Exception as e:
            logger.debug(f"解析第{idx}项失败: {e}")
            continue

    logger.info(f"[{rank_key}] 解析到 {len(books)} 本书")
    return books


def _parse_book_item(li, position, rank_key):
    """从单个列表项提取书籍信息"""
    book = {"rankType": rank_key, "rankPosition": position}

    # 书名和链接 → 提取 bookId
    title_link = (
        li.select_one("h2 a[href*='/info/']") or
        li.select_one("h4 a[href*='/info/']") or
        li.select_one("a[href*='/info/']") or
        li.select_one("h2 a") or
        li.select_one("h4 a")
    )
    if title_link:
        book["title"] = title_link.get_text(strip=True)
        href = title_link.get("href", "")
        m = re.search(r'/info/(\d+)', href)
        if m:
            book["bookId"] = m.group(1)
            book["detailUrl"] = f"{QIDIAN_BASE}/info/{m.group(1)}/"

    if not book.get("title"):
        return None

    # 作者
    author_el = (
        li.select_one("p.author a[href*='/author/']") or
        li.select_one("a.name") or
        li.select_one("p.author a") or
        li.select_one("span.author a")
    )
    if author_el:
        book["author"] = author_el.get_text(strip=True)

    # 分类
    cat_el = (
        li.select_one("p.author a[href*='/all/']") or
        li.select_one("span.tag") or
        li.select_one("a.tag")
    )
    if cat_el:
        book["category"] = cat_el.get_text(strip=True)

    # 简介（截断版）
    intro_el = li.select_one("p.intro") or li.select_one("p.desc")
    if intro_el:
        book["synopsis_short"] = intro_el.get_text(strip=True)

    # 字数
    update_el = li.select_one("p.update") or li.select_one("p.book-info")
    if update_el:
        update_text = update_el.get_text(strip=True)
        wc_match = re.search(r'([\d.]+)\s*万字', update_text)
        if wc_match:
            book["wordCount"] = int(float(wc_match.group(1)) * 10000)
        wc_match2 = re.search(r'([\d,]+)\s*字', update_text)
        if wc_match2 and "wordCount" not in book:
            book["wordCount"] = int(wc_match2.group(1).replace(",", ""))

    # 字数（可能在单独的 span/em 中）
    for el in li.select("span, em"):
        text = el.get_text(strip=True)
        wc_match = re.search(r'([\d.]+)\s*万字', text)
        if wc_match:
            book["wordCount"] = int(float(wc_match.group(1)) * 10000)
            break

    # 最新章节
    chapter_el = li.select_one("p.update a") or li.select_one("a.chapter")
    if chapter_el:
        book["latestChapter"] = chapter_el.get_text(strip=True)

    # 封面图
    img = li.select_one("img[src]")
    if img:
        src = img.get("src", "")
        if src and not src.startswith("data:"):
            book["coverUrl"] = src if src.startswith("http") else urljoin(QIDIAN_BASE, src)

    return book


def _save_debug_html(html, rank_key):
    """保存HTML用于调试"""
    import os
    debug_dir = os.path.join("output", "debug")
    os.makedirs(debug_dir, exist_ok=True)
    path = os.path.join(debug_dir, f"{rank_key}_debug_{datetime.now().strftime('%H%M%S')}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info(f"调试HTML已保存: {path}")


# ─── 移动端 API 解析 ──────────────────────────────────────────

def _looks_like_block_page(html):
    """检测起点 WAF/probe 风控页。"""
    markers = [
        "WAF拦截页面",
        "您的请求已中断",
        "Web应用防护服务检测",
        "probe.js",
    ]
    return any(marker in html for marker in markers)


def _build_mobile_url(rank_key, page=1):
    config = RANKINGS[rank_key]
    base_url = config["mobile_url"]
    if page <= 1:
        return base_url

    sep = "&" if "?" in base_url else "?"
    return f"{base_url}{sep}{urlencode({'pageNum': page})}"


def _extract_mobile_page_data(html):
    soup = BeautifulSoup(html, "lxml")
    script = soup.select_one("script#vite-plugin-ssr_pageContext")
    if not script:
        return {}

    try:
        context = json.loads(script.get_text())
    except json.JSONDecodeError:
        logger.warning("移动端 SSR JSON 解析失败")
        return {}

    return (
        context.get("pageContext", {})
        .get("pageProps", {})
        .get("pageData", {})
    )


def _parse_word_count(text):
    if isinstance(text, (int, float)):
        return int(text)

    text = str(text or "").replace(",", "").strip()
    m = re.search(r'([\d.]+)\s*万字', text)
    if m:
        return int(float(m.group(1)) * 10000)

    m = re.search(r'([\d.]+)\s*万', text)
    if m:
        return int(float(m.group(1)) * 10000)

    m = re.search(r'(\d+)\s*字', text)
    if m:
        return int(m.group(1))

    return 0


def _record_to_book(record, rank_key, position):
    if not isinstance(record, dict) or record.get("isTime"):
        return None

    book_id = str(
        record.get("bid") or record.get("bookId") or record.get("bId") or ""
    ).strip()
    title = (
        record.get("bName") or
        record.get("bookName") or
        record.get("title") or
        ""
    )
    if not book_id or not title:
        return None

    rank_position = record.get("rankNum") or position
    book = {
        "bookId": book_id,
        "title": title,
        "author": record.get("bAuth") or record.get("authorName") or record.get("author") or "",
        "category": record.get("cat") or record.get("catName") or record.get("category") or "",
        "wordCount": _parse_word_count(record.get("cnt") or record.get("wordCount")),
        "synopsis_short": record.get("desc") or record.get("rec") or record.get("description") or "",
        "rankType": rank_key,
        "rankPosition": int(rank_position) if str(rank_position).isdigit() else position,
        "detailUrl": f"{QIDIAN_BASE}/info/{book_id}/",
    }

    if record.get("state"):
        book["status"] = record["state"]
    if record.get("subCat"):
        book["subCategory"] = record["subCat"]
    if record.get("rankCnt"):
        book["rankCountText"] = record["rankCnt"]

    return book


def parse_mobile_ranking_page(html, rank_key):
    """解析移动端 SSR 页面中的榜单 JSON。"""
    if _looks_like_block_page(html):
        logger.warning(f"[{rank_key}] 移动端也返回风控页")
        return []

    page_data = _extract_mobile_page_data(html)
    records = page_data.get("records")

    # /rank/ 首页会把各榜单放在不同 key 中，作为兜底。
    if records is None:
        fallback_keys = {
            "newbook": "newbRank",
            "hotsales": "hotRank",
            "strong": "fyRank",
        }
        data_key = fallback_keys.get(rank_key)
        if data_key:
            records = page_data.get(data_key)

    if not isinstance(records, list):
        return []

    books = []
    for record in records:
        book = _record_to_book(record, rank_key, len(books) + 1)
        if book:
            books.append(book)

    return books


def fetch_mobile_ranking(session, rank_key, page=1, csrf_token=""):
    """通过移动端 SSR 页面获取排行榜数据。"""
    url = _build_mobile_url(rank_key, page)
    logger.info(f"[{rank_key}] 移动端SSR请求: page={page}")
    resp = session.safe_get(url, delay_range=(1, 3), extra_headers=MOBILE_HEADERS)
    html = resp.text if resp else ""

    books = parse_mobile_ranking_page(html, rank_key) if html else []
    if not books:
        logger.info(f"[{rank_key}] requests 未取到可解析数据，尝试 curl 兜底")
        curl_html = _curl_get_text(
            url,
            cookie=session.session.headers.get("Cookie"),
            proxy=session.proxy,
        )
        if curl_html:
            books = parse_mobile_ranking_page(curl_html, rank_key)
            html = curl_html

    if not books and html:
        _save_debug_html(html, f"{rank_key}_mobile")
    return books


def _curl_get_text(url, cookie=None, proxy=None):
    """用系统 curl 兜底获取页面，避开 requests 客户端特征导致的风控。"""
    cmd = [
        "curl",
        "-L",
        "-sS",
        "--compressed",
        "--max-time",
        "30",
        "-A",
        MOBILE_USER_AGENT,
        "-H",
        "Referer: https://m.qidian.com/",
        "-H",
        "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "-H",
        "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8",
    ]

    if cookie:
        cmd.extend(["-H", f"Cookie: {cookie}"])
    if proxy:
        cmd.extend(["--proxy", proxy])

    cmd.append(url)

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=40,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning(f"curl 兜底请求失败: {exc}")
        return ""

    if proc.returncode != 0:
        logger.warning(f"curl 兜底请求失败: {proc.stderr.strip()}")
        return ""

    return proc.stdout


# ─── 主入口 ───────────────────────────────────────────────────

def scrape_ranking(session, rank_key, max_pages=MAX_PAGES_PER_RANK, strategy="auto"):
    """
    爬取单个排行榜。
    strategy: "desktop" | "mobile" | "auto" (先桌面后移动)
    """
    config = RANKINGS[rank_key]
    rank_name = config["name"]
    all_books = []
    mobile_strategy = strategy == "mobile"

    logger.info(f"{'=' * 50}")
    logger.info(f"开始爬取: {rank_name} ({rank_key})")
    logger.info(f"策略: {strategy}, 最大页数: {max_pages}")

    for page in range(1, max_pages + 1):
        logger.info(f"[{rank_name}] 第 {page}/{max_pages} 页")

        if mobile_strategy:
            # 移动端 SSR
            books = fetch_mobile_ranking(session, rank_key, page)
        else:
            # 桌面端 SSR
            url = config["url"]
            if page > 1:
                url = url.rstrip("/") + f"/page{page}/"

            resp = session.safe_get(url)
            if not resp:
                if strategy == "auto":
                    logger.warning(f"桌面端失败，切换到移动端 SSR")
                    mobile_strategy = True
                    books = fetch_mobile_ranking(session, rank_key, page)
                else:
                    logger.error(f"请求失败，跳过第{page}页")
                    break
            else:
                books = parse_ranking_page(resp.text, rank_key)

                # 桌面端解析失败时降级
                if not books and strategy == "auto":
                    logger.warning(f"桌面端解析为空，切换到移动端 SSR")
                    mobile_strategy = True
                    books = fetch_mobile_ranking(session, rank_key, page)

        if not books:
            logger.info(f"第{page}页无数据，停止翻页")
            break

        logger.info(f"  获取 {len(books)} 本书")
        all_books.extend(books)

    # 去重
    seen = set()
    unique = []
    for book in all_books:
        bid = book.get("bookId")
        if bid and bid not in seen:
            seen.add(bid)
            unique.append(book)

    logger.info(f"[{rank_name}] 共获取 {len(unique)} 本（去重后）")
    return unique


def scrape_all_rankings(session, rank_keys=None, max_pages=MAX_PAGES_PER_RANK, strategy="auto"):
    """爬取所有（或指定）排行榜"""
    keys = rank_keys or list(RANKINGS.keys())
    all_data = {}

    for key in keys:
        if key not in RANKINGS:
            logger.warning(f"未知榜单: {key}，跳过")
            continue

        books = scrape_ranking(session, key, max_pages, strategy)
        all_data[key] = books

    return all_data
