"""
书籍详情页爬取
从 book.qidian.com/info/{bookId}/ 提取完整简介、作者等级、标签等
"""

import re
import os
import json
import logging
from datetime import datetime

from bs4 import BeautifulSoup

from config import QIDIAN_BOOK, DETAIL_DELAY

logger = logging.getLogger(__name__)


def parse_book_detail(html, book_id):
    """
    解析书籍详情页 HTML，返回增强的书籍信息 dict。
    """
    soup = BeautifulSoup(html, "lxml")
    detail = {"bookId": book_id}

    # ── 书名 ──
    title_el = soup.select_one("h1") or soup.select_one("h1.book-info-title")
    if title_el:
        detail["title"] = title_el.get_text(strip=True)

    # ── 作者 ──
    author_el = (
        soup.select_one("h2 a[href*='/author/']") or
        soup.select_one("a.writer") or
        soup.select_one("p.book-info a.name") or
        soup.select_one("span.writer a")
    )
    if author_el:
        detail["author"] = author_el.get_text(strip=True)

    # ── 作者等级 ──
    # 可能出现在多个位置：badge元素、文本"作家等级"、class名
    author_level = _extract_author_level(soup)
    if author_level is not None:
        detail["authorLevel"] = author_level

    # ── 分类 ──
    cat_el = (
        soup.select_one("p.book-info a[href*='/all/']") or
        soup.select_one("a.tag") or
        soup.select_one("span.tag")
    )
    if cat_el:
        detail["category"] = cat_el.get_text(strip=True)

    # ── 简介（完整版）──
    intro_el = (
        soup.select_one("div.book-intro p") or
        soup.select_one("p.intro") or
        soup.select_one("div.book-info-detail p.intro") or
        soup.select_one("div.intro")
    )
    if intro_el:
        detail["synopsis"] = intro_el.get_text(strip=True)

    # ── 标签 ──
    tags = []
    tag_els = soup.select("div.tag-wrap a") or soup.select("p.tag a") or soup.select("a.tag-wrap")
    for tag_el in tag_els:
        tag_text = tag_el.get_text(strip=True)
        if tag_text and tag_text not in ("", " "):
            tags.append(tag_text)
    if tags:
        detail["tags"] = tags

    # ── 字数（精确版）──
    word_count = _extract_word_count(soup)
    if word_count:
        detail["wordCount"] = word_count

    # ── 状态（连载/完结）──
    status_el = soup.select_one("p.book-info span.blue") or soup.select_one("span.blue")
    if status_el:
        status_text = status_el.get_text(strip=True)
        if "完" in status_text or "完结" in status_text:
            detail["status"] = "完结"
        elif "连载" in status_text or "连" in status_text:
            detail["status"] = "连载"

    # ── 总点击/总推荐/总收藏 ──
    stats = _extract_stats(soup)
    detail.update(stats)

    # ── 评分/评价人数（页面结构不稳定，做多策略兜底）──
    rating = _extract_rating(soup, html)
    detail.update(rating)

    # ── 发布日期 ──
    pub_date = _extract_pub_date(soup)
    if pub_date:
        detail["publishDate"] = pub_date

    # ── 作家作品数（辅助判断是否新人）──
    works_count = _extract_works_count(soup)
    if works_count is not None:
        detail["authorWorksCount"] = works_count

    return detail


def _extract_author_level(soup):
    """提取作者等级"""
    # 方法1: 查找等级 badge
    level_el = soup.select_one("i.lv-icon, span.lv-icon, em.lv")
    if level_el:
        cls = " ".join(level_el.get("class", []))
        m = re.search(r'lv[_-]?(\d+)', cls, re.I)
        if m:
            return int(m.group(1))

    # 方法2: 文本中查找 "LV5" 等
    for el in soup.select("span, em, i, p"):
        text = el.get_text(strip=True)
        m = re.search(r'(?:作家)?等级[:\s]*LV\s*(\d+)', text, re.I)
        if m:
            return int(m.group(1))
        m = re.search(r'LV\s*(\d+)', text)
        if m and len(text) < 20:  # 避免匹配到正文中的LV
            return int(m.group(1))

    # 方法3: class名中查找
    for el in soup.select("[class*='level'], [class*='lv']"):
        cls = " ".join(el.get("class", []))
        m = re.search(r'(?:level|lv)[_-]?(\d+)', cls, re.I)
        if m:
            return int(m.group(1))

    return None


def _extract_word_count(soup):
    """提取精确字数"""
    for el in soup.select("p.book-info em, p.count span, span.word-count"):
        text = el.get_text(strip=True)
        m = re.search(r'([\d,.]+)\s*万字', text)
        if m:
            return int(float(m.group(1).replace(",", "")) * 10000)
        m = re.search(r'([\d,]+)\s*字', text)
        if m:
            return int(m.group(1).replace(",", ""))
    return None


def _extract_stats(soup):
    """提取统计数据（点击、推荐、收藏）"""
    stats = {}
    for el in soup.select("p.book-info em, p.count em, span.count-num"):
        text = el.get_text(strip=True)
        parent_text = el.parent.get_text(strip=True) if el.parent else ""

        if "点击" in parent_text:
            stats["totalClicks"] = _parse_count(text)
        elif "推荐" in parent_text:
            stats["totalRecom"] = _parse_count(text)
        elif "收藏" in parent_text:
            stats["totalCollect"] = _parse_count(text)

    return stats


def _extract_rating(soup, html):
    """提取评分和评分人数。页面若没有公开评分则返回空 dict。"""
    rating = {}

    for el in soup.select(
        ".score, .rating, .book-score, .bookScore, [class*='score'], [class*='rating']"
    ):
        text = el.get_text(" ", strip=True)
        class_text = " ".join(el.get("class", []))
        if not text:
            continue
        if not re.search(r'评分|评价|score|rating', text + " " + class_text, re.I):
            continue

        score = _extract_score_number(text)
        if score is not None:
            rating["rating"] = score

        count = _extract_rating_count(text)
        if count is not None:
            rating["ratingCount"] = count

        if "rating" in rating and "ratingCount" in rating:
            return rating

    text = soup.get_text(" ", strip=True)
    if "rating" not in rating:
        score = _extract_score_number_near_label(text)
        if score is not None:
            rating["rating"] = score

    if "ratingCount" not in rating:
        count = _extract_rating_count(text)
        if count is not None:
            rating["ratingCount"] = count

    if "rating" not in rating:
        for pattern in (
            r'"(?:bookScore|score|rating)"\s*:\s*"?([0-9](?:\.\d+)?)"?',
            r"'(?:bookScore|score|rating)'\s*:\s*'?([0-9](?:\.\d+)?)'?",
        ):
            match = re.search(pattern, html, re.I)
            if match:
                score = _normalize_score(match.group(1))
                if score is not None:
                    rating["rating"] = score
                    break

    if "ratingCount" not in rating:
        for pattern in (
            r'"(?:ratingCount|scoreCount|rateCount)"\s*:\s*"?([\d,]+)"?',
            r"'(?:ratingCount|scoreCount|rateCount)'\s*:\s*'?([\d,]+)'?",
        ):
            match = re.search(pattern, html, re.I)
            if match:
                rating["ratingCount"] = int(match.group(1).replace(",", ""))
                break

    return rating


def _extract_score_number(text):
    for number in re.findall(r'(?<!\d)([0-9](?:\.\d+)?|10(?:\.0)?)(?!\d)', text):
        score = _normalize_score(number)
        if score is not None:
            return score
    return None


def _extract_score_number_near_label(text):
    for pattern in (
        r'(?:评分|评价|score|rating)\s*[:：]?\s*([0-9](?:\.\d+)?|10(?:\.0)?)',
        r'([0-9](?:\.\d+)?|10(?:\.0)?)\s*(?:分|评分)',
    ):
        match = re.search(pattern, text, re.I)
        if match:
            score = _normalize_score(match.group(1))
            if score is not None:
                return score
    return None


def _normalize_score(value):
    try:
        score = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if 0 <= score <= 10:
        return int(score) if score.is_integer() else score
    return None


def _extract_rating_count(text):
    for pattern in (
        r'([\d,]+)\s*人\s*(?:评分|评价)',
        r'(?:评分|评价)\s*人数\s*[:：]?\s*([\d,]+)',
        r'(?:rating|score)\s*count\s*[:：]?\s*([\d,]+)',
    ):
        match = re.search(pattern, text, re.I)
        if match:
            return int(match.group(1).replace(",", ""))
    return None


def _extract_pub_date(soup):
    """提取发布日期"""
    for el in soup.select("p.book-info span, p.info span, span.pub-date"):
        text = el.get_text(strip=True)
        m = re.search(r'(\d{4}-\d{2}-\d{2})', text)
        if m:
            return m.group(1)
        m = re.search(r'(\d{4}年\d{1,2}月\d{1,2}日)', text)
        if m:
            return m.group(1)

    # 在整个页面文本中查找
    page_text = soup.get_text()
    m = re.search(r'上架时间[:\s]*(\d{4}-\d{2}-\d{2})', page_text)
    if m:
        return m.group(1)
    m = re.search(r'发布时间[:\s]*(\d{4}-\d{2}-\d{2})', page_text)
    if m:
        return m.group(1)

    return None


def _extract_works_count(soup):
    """提取作者作品数量"""
    for el in soup.select("p, span, div"):
        text = el.get_text(strip=True)
        m = re.search(r'共\s*(\d+)\s*部作品', text)
        if m:
            return int(m.group(1))
        m = re.search(r'(\d+)\s*部作品', text)
        if m and len(text) < 50:
            return int(m.group(1))
    return None


def _parse_count(text):
    """解析数字，如 '1.1万' '5,435' → int"""
    text = text.strip().replace(",", "")
    m = re.search(r'([\d.]+)\s*万', text)
    if m:
        return int(float(m.group(1)) * 10000)
    m = re.search(r'[\d.]+', text)
    if m:
        return int(float(m.group()))
    return 0


# ─── 检测字体反爬 ────────────────────────────────────────────

def has_font_encryption(html):
    """检测页面是否使用了字体反爬"""
    # PUA Unicode 范围: U+E000 - U+F8FF
    pua_pattern = re.compile(r'[-]')
    if pua_pattern.search(html):
        return True

    # 自定义 @font-face
    if '@font-face' in html and 'qidian' in html:
        return True

    return False


def decode_font_text(text, font_url=None):
    """
    处理字体加密文本。
    如果无法解码，返回带标记的原文。
    """
    pua_pattern = re.compile(r'[-]')
    if not pua_pattern.search(text):
        return text

    # 标记无法解码的字符
    return pua_pattern.sub('[?]', text)


# ─── 批量详情获取 ────────────────────────────────────────────

RANK_METADATA_FIELDS = {"rankType", "rankPosition", "rankAppearances", "ranks"}
DETAIL_CONTENT_FIELDS = {
    "title",
    "author",
    "authorLevel",
    "category",
    "synopsis",
    "tags",
    "wordCount",
    "status",
    "rating",
    "ratingCount",
    "totalClicks",
    "totalRecom",
    "totalCollect",
    "publishDate",
    "authorWorksCount",
}


def merge_book_with_detail(book, detail):
    """合并榜单书籍和详情数据，并让本次榜单元数据优先。"""
    merged = {**book, **detail}
    for field in RANK_METADATA_FIELDS:
        if field in book:
            merged[field] = book[field]
    return merged


def has_useful_detail(detail):
    """判断详情缓存是否真的含有详情页内容，而不只是 bookId/url。"""
    return any(detail.get(field) not in (None, "", []) for field in DETAIL_CONTENT_FIELDS)


def fetch_book_detail(session, book_id):
    """获取单本书的详情"""
    url = f"{QIDIAN_BOOK}/info/{book_id}/"
    logger.info(f"获取详情: {book_id}")

    resp = session.safe_get(url, delay_range=DETAIL_DELAY)
    if not resp:
        logger.warning(f"获取详情失败: {book_id}")
        return None

    # 字体反爬检测
    if has_font_encryption(resp.text):
        logger.info(f"检测到字体反爬: {book_id}")

    detail = parse_book_detail(resp.text, book_id)
    detail["detailUrl"] = url
    detail["scrapedAt"] = datetime.now().isoformat()
    return detail


def fetch_details_batch(session, books, limit=None, output_dir="output/details"):
    """批量获取书籍详情，支持断点续跑"""
    os.makedirs(output_dir, exist_ok=True)

    targets = books[:limit] if limit else books
    logger.info(f"批量获取详情: {len(targets)} 本书")

    results = []
    skipped = 0

    for i, book in enumerate(targets):
        book_id = book.get("bookId", "")
        if not book_id:
            continue

        # 断点续跑：检查是否已有详情文件
        detail_file = os.path.join(output_dir, f"{book_id}.json")
        if os.path.exists(detail_file):
            try:
                with open(detail_file, "r", encoding="utf-8") as f:
                    detail = json.load(f)
                if has_useful_detail(detail):
                    logger.debug(f"[{i+1}/{len(targets)}] 已存在，跳过: {book_id}")
                    results.append(merge_book_with_detail(book, detail))
                    skipped += 1
                    continue
                logger.info(f"[{i+1}/{len(targets)}] 缓存字段过少，重新抓取: {book_id}")
            except (json.JSONDecodeError, IOError):
                pass  # 文件损坏，重新抓取

        logger.info(f"[{i+1}/{len(targets)}] {book.get('title', book_id)}")
        detail = fetch_book_detail(session, book_id)

        if detail:
            merged = merge_book_with_detail(book, detail)
            # 单书缓存只保存详情，榜单元数据保存在 all_details 快照里。
            with open(detail_file, "w", encoding="utf-8") as f:
                json.dump(detail, f, ensure_ascii=False, indent=2)
            results.append(merged)
        else:
            results.append(book)  # 保留列表页数据

    if skipped:
        logger.info(f"断点续跑：跳过 {skipped} 本已有详情")

    logger.info(f"详情获取完成: {len(results)}/{len(targets)}")
    return results
