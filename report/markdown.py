"""
Markdown 报告生成器
汇总分析结果，生成可读的扫榜报告。
"""

import json
import logging
import re
from collections import Counter
from datetime import datetime

from config import AUTHOR_LEVELS, ALL_RANKINGS, get_rank_name, get_site_name, get_site_rankings
from scraper.fanqie import decode_fanqie_font_text

logger = logging.getLogger(__name__)


def generate_report(data):
    """
    从分析数据生成 Markdown 报告。
    data 结构: {"timestamp", "bookCount", "books", "analyses": {...}}
    """
    data = _decode_report_value(data)
    analyses = data.get("analyses", {})
    books = data.get("books") or data.get("bookSamples") or []
    book_count = data.get("bookCount", 0) or len(books)
    timestamp = data.get("timestamp", datetime.now().isoformat())
    site = data.get("site") or _site_from_books(books)
    site_name = data.get("siteName") or get_site_name(site)

    sections = [
        _header(timestamp, book_count, analyses, books, site, site_name),
        _overview(analyses, books),
        _rank_portrait_section(books),
        _highlight_books_section(books),
        _genre_section(analyses.get("genre", {}), books),
        _title_section(analyses.get("title", {}), books),
        _synopsis_section(analyses.get("synopsis", {}), books),
        _author_section(analyses.get("author", {})),
        _wordcount_section(analyses.get("wordcount", {}), books),
        _cross_rank_section(analyses.get("crossrank", {})),
        _writing_tips(analyses, books),
        _original_books_section(books),
    ]

    return "\n\n".join(s for s in sections if s)


def _header(timestamp, book_count, analyses, books, site, site_name):
    """报告头部。"""
    rank_names = _rank_names_from_books(books)
    if not rank_names:
        genre = analyses.get("genre", {})
        rank_names = [_rank_name(key) for key in _rank_keys_in_order(genre.get("byRank", {}))]

    if not rank_names:
        rank_names = [_rank_name(key) for key in get_site_rankings(site)]

    sample_line = f"\n> 报告样本: {len(books)} 本" if books and len(books) != book_count else ""

    return f"""# {site_name}排行榜分析报告

> 生成时间: {timestamp[:10]}
> 分析书籍: {book_count} 本{sample_line}
> 数据来源: {', '.join(rank_names) if rank_names else '未知榜单'}"""


def _overview(analyses, books):
    """概览。"""
    lines = ["## 概览\n"]

    genre = analyses.get("genre", {})
    title = analyses.get("title", {})
    synopsis = analyses.get("synopsis", {})
    author = analyses.get("author", {})
    wordcount = analyses.get("wordcount", {})

    total = genre.get("total", [])
    if total:
        top3 = total[:3]
        top3_count = sum(item.get("count", 0) for item in top3)
        total_count = sum(item.get("count", 0) for item in total) or 1
        top3_text = "、".join(f"{item['category']}({item['pct']}%)" for item in top3)
        lines.append(f"- 分类头部: **{top3_text}**，Top3 合计 {round(top3_count / total_count * 100, 1)}%。")
        lines.append(f"- 分类广度: 共 {genre.get('categoryCount', len(total))} 个分类，长尾分类 {max(len(total) - 3, 0)} 个。")

    length = title.get("length", {})
    if length:
        lines.append(
            f"- 标题形态: 平均 **{length.get('average', 0)} 字**，"
            f"样本范围 {length.get('min', 0)}-{length.get('max', 0)} 字。"
        )

    hook_types = synopsis.get("hookTypes", [])
    if hook_types:
        hook = hook_types[0]
        lines.append(f"- 简介开篇: 最常见为 **{hook['type']}**，占 {hook['pct']}%。")

    stats = wordcount.get("stats", {})
    if stats:
        lines.append(
            f"- 字数成熟度: 平均 **{stats.get('averageWan', 0)}万字**，"
            f"中位数 {stats.get('medianWan', 0)}万字。"
        )

    newbie = author.get("newbie", {})
    if newbie and author.get("totalWithLevel", 0):
        lines.append(f"- 新人作者占比 (LV5及以下): **{newbie.get('pct', 0)}%**。")
    elif author and not author.get("totalWithLevel", 0):
        lines.append("- 作者等级: 本次未抓到可用等级数据，新人占比暂不解读。")

    if books:
        rank_counts = {rank: len(items) for rank, items in _group_books_by_rank(books).items()}
        rank_text = "、".join(f"{_rank_name(rank)} {count}本" for rank, count in rank_counts.items())
        lines.append(f"- 书目样本覆盖: {rank_text}。")

    return "\n".join(lines).rstrip()


def _rank_portrait_section(books):
    """各榜单画像。"""
    groups = _group_books_by_rank(books)
    if not groups:
        return ""

    lines = ["## 一、榜单画像\n"]
    for rank in _rank_keys_in_order(groups):
        rank_books = groups[rank]
        cats = Counter(book.get("category") or "未知" for book in rank_books)
        cat_text = _counter_text(cats, limit=3)
        word_values = [_word_count(book) for book in rank_books if _word_count(book)]
        median_text = f"{_format_word_count(_median(word_values))}" if word_values else "未知"
        top_books = _top_books_for_rank(rank_books, rank, limit=4)
        top_text = "、".join(
            f"{_rank_position_label(book, rank)}{_book_plain_title(book)}"
            for book in top_books
        )

        lines.append(f"### {_rank_name(rank)}\n")
        lines.append(f"- 样本规模: {len(rank_books)} 本；头部分类: {cat_text}；字数中位数: {median_text}。")
        if top_text:
            lines.append(f"- 排名前列: {top_text}。")
        lines.append("")

    return "\n".join(lines).rstrip()


def _highlight_books_section(books):
    """重点书目速览。"""
    if not books:
        return ""

    lines = ["## 二、重点书目速览\n"]
    lines.append("| 榜单/名次 | 书名 | 作者 | 分类 | 字数 | 简介抓手 |")
    lines.append("|-----------|------|------|------|------|----------|")
    for book in sorted(books, key=_book_sort_key)[:12]:
        synopsis = _truncate(_first_sentence(_synopsis(book)), 54)
        lines.append(
            f"| {_escape_md(_book_rank_label(book))} "
            f"| {_book_link(book)} "
            f"| {_escape_md(book.get('author') or '未知')} "
            f"| {_escape_md(book.get('category') or '未知')} "
            f"| {_format_word_count(_word_count(book))} "
            f"| {_escape_md(synopsis or '暂无简介')} |"
        )

    return "\n".join(lines)


def _genre_section(genre, books):
    """分类分布。"""
    if not genre:
        return ""

    lines = ["## 三、分类分布\n"]

    total = genre.get("total", [])
    if total:
        top = total[0]
        total_count = sum(item.get("count", 0) for item in total) or 1
        top_count = sum(item.get("count", 0) for item in total[:3])
        lines.append(
            f"**观察:** 头部分类由 **{top['category']}** 领跑，Top3 分类吃掉 "
            f"{round(top_count / total_count * 100, 1)}% 的样本；如果要避开拥挤赛道，"
            f"可以重点看 4-8 名分类的题材切口。"
        )

        lines.append("\n### 总体分布\n")
        lines.append("| 分类 | 数量 | 占比 |")
        lines.append("|------|------|------|")
        for item in total[:12]:
            lines.append(f"| {item['category']} | {item['count']} | {item['pct']}% |")

    by_rank = genre.get("byRank", {})
    if by_rank:
        lines.append("\n### 各榜单分类对比\n")
        rank_keys = _rank_keys_in_order(by_rank)
        rank_names = [_rank_name(key) for key in rank_keys]
        lines.append("| 分类 | " + " | ".join(rank_names) + " |")
        lines.append("|------|" + "|".join(["------"] * len(rank_names)) + "|")

        all_cats = set()
        for counter in by_rank.values():
            all_cats.update(item["category"] for item in counter)

        cat_totals = {}
        for cat in all_cats:
            cat_totals[cat] = sum(
                next((item["count"] for item in by_rank[rank] if item["category"] == cat), 0)
                for rank in rank_keys
            )

        for cat in sorted(cat_totals, key=lambda value: -cat_totals[value])[:12]:
            row = f"| {cat} "
            for rank in rank_keys:
                count = next((item["count"] for item in by_rank[rank] if item["category"] == cat), 0)
                row += f"| {count} "
            row += "|"
            lines.append(row)

        leaders = []
        for rank in rank_keys:
            if by_rank[rank]:
                leader = by_rank[rank][0]
                leaders.append(f"{_rank_name(rank)}偏{leader['category']}({leader['pct']}%)")
        if leaders:
            lines.append("\n- 榜单差异: " + "；".join(leaders) + "。")

    examples = _category_examples(books, [item["category"] for item in total[:5]])
    if examples:
        lines.append("\n### 分类代表书目\n")
        lines.append("| 分类 | 代表书目 | 题材/卖点抓手 |")
        lines.append("|------|----------|----------------|")
        for category, book in examples:
            lines.append(
                f"| {_escape_md(category)} | {_book_link(book)} | "
                f"{_escape_md(_truncate(_first_sentence(_synopsis(book)), 56) or '暂无简介')} |"
            )

    return "\n".join(lines)


def _title_section(title, books):
    """标题分析。"""
    if not title:
        return ""

    lines = ["## 四、标题分析\n"]

    length = title.get("length", {})
    if length:
        dist = length.get("distribution", [])
        preferred = max(dist, key=lambda item: item.get("count", 0)) if dist else None
        lines.append(f"- 平均标题长度: **{length.get('average', 0)} 字**")
        if preferred:
            lines.append(f"- 主流长度段: **{preferred['range']}**，占 {preferred['pct']}%。")
        if dist:
            parts = [f"{item['range']}({item['pct']}%)" for item in dist[:5]]
            lines.append(f"- 长度分布: {', '.join(parts)}")

    keywords = title.get("keywords", [])
    if keywords:
        kw_parts = [f"{item['word']}({item['count']})" for item in keywords[:12]]
        lines.append(f"- 高频关键词: {', '.join(kw_parts)}")

    patterns = title.get("patterns", [])
    if patterns:
        top_pattern = patterns[0]
        lines.append(
            f"- 结构倾向: **{top_pattern['pattern']}** 最多，"
            f"{top_pattern['count']} 本，占 {top_pattern['pct']}%。"
        )

        lines.append("\n### 标题结构偏好\n")
        lines.append("| 模式 | 数量 | 占比 |")
        lines.append("|------|------|------|")
        for pattern in patterns[:8]:
            lines.append(f"| {pattern['pattern']} | {pattern['count']} | {pattern['pct']}% |")

        examples = _title_pattern_examples(books, patterns)
        if examples:
            lines.append("\n### 标题样例\n")
            lines.append("| 模式 | 样例 |")
            lines.append("|------|------|")
            for pattern, titles in examples:
                lines.append(f"| {_escape_md(pattern)} | {_escape_md('、'.join(titles))} |")

    return "\n".join(lines)


def _synopsis_section(synopsis, books):
    """简介分析。"""
    if not synopsis:
        return ""

    lines = ["## 五、简介开篇分析\n"]

    hooks = synopsis.get("hookTypes", [])
    if hooks:
        top_hook = hooks[0]
        lines.append(
            f"**观察:** 简介开篇以 **{top_hook['type']}** 为主。"
            "如果“其他”占比高，通常说明样本里存在大量复合式开篇，"
            "后续可以继续细分为重生、职业、年代、异世界等更细标签。"
        )

        lines.append("\n### 开篇类型\n")
        lines.append("| 类型 | 数量 | 占比 |")
        lines.append("|------|------|------|")
        for hook in hooks:
            lines.append(f"| {hook['type']} | {hook['count']} | {hook['pct']}% |")

    first = synopsis.get("firstSentence", {})
    if first:
        avg = first.get("averageLength", 0)
        lines.append("\n### 首句特征\n")
        lines.append(f"- 平均首句长度: {avg} 字")
        openers = first.get("topOpeners", [])
        if openers:
            parts = [f'"{opener["word"]}"({opener["count"]})' for opener in openers[:8]]
            lines.append(f"- 常见开头: {', '.join(parts)}")

    length = synopsis.get("length", {})
    if length:
        lines.append(
            f"- 简介长度: 平均 {length.get('average', 0)} 字，"
            f"范围 {length.get('min', 0)}-{length.get('max', 0)} 字。"
        )

    common_words = synopsis.get("commonWords", [])
    if common_words:
        parts = [f"{word['word']}({word['count']})" for word in common_words[:10]]
        lines.append(f"- 简介高频词: {', '.join(parts)}")

    examples = _synopsis_examples(books)
    if examples:
        lines.append("\n### 简介样例\n")
        lines.append("| 书名 | 识别开篇 | 首句/卖点 |")
        lines.append("|------|----------|-----------|")
        for book in examples:
            text = _synopsis(book)
            lines.append(
                f"| {_book_link(book)} | {_infer_hook_type(text)} | "
                f"{_escape_md(_truncate(_first_sentence(text), 70) or '暂无简介')} |"
            )

    return "\n".join(lines)


def _author_section(author):
    """作者等级。"""
    if not author:
        return ""

    lines = ["## 六、作者等级分布\n"]

    total = author.get("totalBooks", 0)
    total_with_level = author.get("totalWithLevel", 0)
    no_level = author.get("noLevelCount", 0)
    if total:
        lines.append(
            f"- 等级数据覆盖: {total_with_level}/{total} 本；"
            f"缺失 {no_level} 本。缺失较多时，新人占比只代表已抓到等级的样本。"
        )

    dist = author.get("distribution", [])
    if dist:
        lines.append("\n| 等级 | 数量 | 占比 |")
        lines.append("|------|------|------|")
        for item in dist:
            lines.append(f"| {item['level']} | {item['count']} | {item['pct']}% |")

    newbie = author.get("newbie", {})
    if newbie:
        lines.append(f"\n**新人作者 (LV5及以下): {newbie.get('count', 0)} 本 ({newbie.get('pct', 0)}%)**")

    by_rank = author.get("byRank", {})
    if by_rank:
        lines.append("\n### 各榜单新人占比\n")
        lines.append("| 榜单 | 有等级样本 | 新人 | 占比 |")
        lines.append("|------|------------|------|------|")
        for rank in _rank_keys_in_order(by_rank):
            stats = by_rank[rank]
            lines.append(f"| {_rank_name(rank)} | {stats['total']} | {stats['newbie']} | {stats['pct']}% |")

    newbie_books = author.get("newbieBooks", [])
    if newbie_books:
        lines.append("\n### 新人上榜样本\n")
        lines.append("| 书名 | 作者 | 等级 | 分类 | 字数 |")
        lines.append("|------|------|------|------|------|")
        for book in newbie_books[:10]:
            lines.append(
                f"| 《{_escape_md(book.get('title', ''))}》 | {_escape_md(book.get('author', ''))} "
                f"| {_escape_md(book.get('level', '未知'))} | {_escape_md(book.get('category', ''))} "
                f"| {_format_word_count(_word_count(book))} |"
            )

    return "\n".join(lines)


def _wordcount_section(wordcount, books):
    """字数分布。"""
    if not wordcount:
        return ""

    lines = ["## 七、字数分布\n"]

    stats = wordcount.get("stats", {})
    if stats:
        lines.append(f"- 平均字数: **{stats.get('averageWan', 0)}万字**")
        lines.append(f"- 中位数: {stats.get('medianWan', 0)}万字")
        lines.append(f"- 范围: {stats.get('min', 0) / 10000:.0f}万 ~ {stats.get('max', 0) / 10000:.0f}万字")

    dist = wordcount.get("distribution", [])
    if dist:
        main_range = max(dist, key=lambda item: item.get("count", 0))
        lines.append(f"- 主力区间: **{main_range['range']}**，占 {main_range['pct']}%。")

        lines.append("\n| 字数区间 | 数量 | 占比 |")
        lines.append("|----------|------|------|")
        for item in dist:
            lines.append(f"| {item['range']} | {item['count']} | {item['pct']}% |")

    valid_books = [book for book in books if _word_count(book)]
    if valid_books:
        shortest = min(valid_books, key=_word_count)
        longest = max(valid_books, key=_word_count)
        lines.append("\n### 字数样本\n")
        lines.append(
            f"- 最短样本: {_book_link(shortest)}，{_format_word_count(_word_count(shortest))}，"
            f"{_book_rank_label(shortest)}。"
        )
        lines.append(
            f"- 最长样本: {_book_link(longest)}，{_format_word_count(_word_count(longest))}，"
            f"{_book_rank_label(longest)}。"
        )

    by_rank = wordcount.get("byRank", {})
    if by_rank:
        lines.append("\n### 各榜单字数结构\n")
        for rank in _rank_keys_in_order(by_rank):
            parts = [f"{item['range']} {item['pct']}%" for item in by_rank[rank]]
            lines.append(f"- {_rank_name(rank)}: {'、'.join(parts)}。")

    return "\n".join(lines)


def _cross_rank_section(cross_rank):
    """跨榜上榜。"""
    if not cross_rank:
        return ""

    lines = ["## 八、跨榜上榜书籍（重点研究对象）\n"]

    total = cross_rank.get("totalUniqueBooks", 0)
    lines.append(f"- 总去重书籍数: {total}")

    distribution = cross_rank.get("distribution", [])
    if distribution:
        parts = [f"{item['rankCount']}个榜={item['bookCount']}本" for item in distribution]
        lines.append(f"- 榜单分布: {', '.join(parts)}")

    rank_stats = cross_rank.get("rankStats", {})
    if rank_stats:
        lines.append("\n### 榜单独占/共享\n")
        lines.append("| 榜单 | 总数 | 独占 | 跨榜共享 |")
        lines.append("|------|------|------|----------|")
        for rank in _rank_keys_in_order(rank_stats):
            stats = rank_stats[rank]
            lines.append(
                f"| {_rank_name(rank)} | {stats.get('total', 0)} | "
                f"{stats.get('exclusive', 0)} | {stats.get('shared', 0)} |"
            )

    multi = cross_rank.get("multiRankBooks", [])
    if multi:
        lines.append(f"\n### 多榜上榜书籍 ({len(multi)}本)\n")
        lines.append("| 书名 | 作者 | 等级 | 分类 | 上榜数 | 出现榜单 |")
        lines.append("|------|------|------|------|--------|----------|")
        for book in multi[:20]:
            rank_names = [_rank_name(rank) for rank in book.get("ranks", [])]
            lines.append(
                f"| 《{_escape_md(book['title'])}》 | {_escape_md(book.get('author', ''))} "
                f"| {_escape_md(_level_label(book.get('authorLevel')))} "
                f"| {_escape_md(book.get('category', ''))} | {book['rankCount']} "
                f"| {'/'.join(rank_names)} |"
            )
    else:
        lines.append("\n本次样本没有多榜重叠书，说明这些榜单当前的推荐池区分度较高。")

    return "\n".join(lines)


def _writing_tips(analyses, books):
    """基于分析数据的写作建议。"""
    tips = []

    genre = analyses.get("genre", {})
    title = analyses.get("title", {})
    synopsis = analyses.get("synopsis", {})
    author = analyses.get("author", {})
    wordcount = analyses.get("wordcount", {})

    top_cats = genre.get("topCategories", [])
    if top_cats:
        tips.append(f"选题先看 **{', '.join(top_cats[:3])}**，再对照各榜单画像判断是跟头部热度还是找侧翼切口。")

    patterns = title.get("patterns", [])
    length = title.get("length", {})
    if patterns and length:
        tips.append(
            f"标题可优先控制在 {length.get('min', 0)}-{length.get('max', 0)} 字的样本区间内，"
            f"当前最高频结构是 **{patterns[0]['pattern']}**。"
        )
    elif length:
        tips.append(f"标题平均 {length.get('average', 0)} 字，避免明显短于或长于样本主流。")

    hooks = synopsis.get("hookTypes", [])
    first = synopsis.get("firstSentence", {})
    if hooks:
        tips.append(
            f"简介开篇别只复述设定，至少在首句附近交代冲突、身份差或目标；"
            f"本次最常见开篇是 **{hooks[0]['type']}**。"
        )
    if first.get("averageLength"):
        tips.append(f"首句长度可参考平均 {first['averageLength']} 字，尽量一口气给出人物处境或钩子。")

    stats = wordcount.get("stats", {})
    if stats:
        tips.append(
            f"上榜样本平均 {stats.get('averageWan', 0)}万字，中位数 {stats.get('medianWan', 0)}万字；"
            "评估新书节奏时优先和中位数对齐。"
        )

    newbie = author.get("newbie", {})
    if newbie and newbie.get("pct", 0) > 0:
        tips.append(f"新人作者占比 {newbie['pct']}%，说明低等级作者仍有进入榜单的窗口。")

    if books:
        sample_titles = "、".join(_book_plain_title(book) for book in sorted(books, key=_book_sort_key)[:3])
        tips.append(f"复盘时先拆前三个头部样本: {sample_titles}，重点看标题承诺、简介钩子和榜单位置的对应关系。")

    if not tips:
        return ""

    lines = ["## 九、可执行观察\n"]
    for tip in tips:
        lines.append(f"- {tip}")

    return "\n".join(lines)


def _original_books_section(books):
    """逐本输出已经抓到的原始书籍信息。"""
    if not books:
        return ""

    lines = ["## 十、原件：逐本书籍档案\n"]
    lines.append(
        "下面保留本次结果中每本书已经抓到的原始字段。评分如果显示“未抓到”，"
        "表示当前页面或缓存里没有可解析的评分字段。"
    )

    for index, book in enumerate(sorted(books, key=_book_sort_key), 1):
        lines.append(f"\n### {index}. {_book_plain_title(book)}\n")
        lines.append("| 字段 | 内容 |")
        lines.append("|------|------|")
        for label, value in _original_core_rows(book):
            lines.append(f"| {label} | {_format_original_value(value)} |")

        synopsis = _synopsis(book)
        if synopsis:
            lines.append("\n**简介原文**\n")
            lines.append("```text")
            lines.append(synopsis)
            lines.append("```")

        lines.append("\n**完整字段 JSON**\n")
        lines.append("```json")
        lines.append(json.dumps(_ordered_book_fields(book), ensure_ascii=False, indent=2))
        lines.append("```")

    return "\n".join(lines)


def _rank_name(rank):
    return get_rank_name(rank)


def _rank_keys_in_order(values):
    keys = list(values.keys()) if isinstance(values, dict) else list(values)
    known = [key for key in ALL_RANKINGS if key in keys]
    unknown = sorted(key for key in keys if key not in ALL_RANKINGS)
    return known + unknown


def _site_from_books(books):
    for book in books or []:
        site = book.get("site")
        if site:
            return site
    return "qidian"


def _rank_names_from_books(books):
    groups = _group_books_by_rank(books)
    return [_rank_name(rank) for rank in _rank_keys_in_order(groups)]


def _group_books_by_rank(books):
    groups = {}
    seen = set()
    for book in books:
        book_key = book.get("bookId") or book.get("title")
        for appearance in _rank_appearances(book):
            rank = appearance.get("rankType")
            if not rank:
                continue
            key = (book_key, rank)
            if key in seen:
                continue
            seen.add(key)
            groups.setdefault(rank, []).append(book)
    return {rank: groups[rank] for rank in _rank_keys_in_order(groups)}


def _rank_appearances(book):
    appearances = []
    for appearance in book.get("rankAppearances", []) or []:
        if not isinstance(appearance, dict):
            continue
        rank = appearance.get("rankType")
        if rank:
            appearances.append({
                "rankType": rank,
                "rankPosition": _coerce_int(appearance.get("rankPosition")),
            })

    if not appearances and book.get("rankType"):
        appearances.append({
            "rankType": book.get("rankType"),
            "rankPosition": _coerce_int(book.get("rankPosition")),
        })

    existing = {appearance["rankType"] for appearance in appearances}
    for rank in book.get("ranks", []) or []:
        if rank and rank not in existing:
            appearances.append({"rankType": rank, "rankPosition": None})

    return sorted(appearances, key=_appearance_sort_key)


def _appearance_sort_key(appearance):
    rank_order = {rank: index for index, rank in enumerate(ALL_RANKINGS)}
    position = _coerce_int(appearance.get("rankPosition"))
    return (
        rank_order.get(appearance.get("rankType"), 999),
        position if position is not None else 9999,
    )


def _book_sort_key(book):
    appearances = _rank_appearances(book)
    first = _appearance_sort_key(appearances[0]) if appearances else (999, 9999)
    return (first[0], first[1], book.get("title", ""))


def _book_rank_label(book):
    parts = []
    for appearance in _rank_appearances(book):
        rank = _rank_name(appearance.get("rankType"))
        position = appearance.get("rankPosition")
        parts.append(f"{rank}#{position}" if position else rank)
    return "/".join(parts) if parts else "未知榜单"


def _rank_position_label(book, rank):
    position = _position_for_rank(book, rank)
    return f"#{position} " if position else ""


def _position_for_rank(book, rank):
    for appearance in _rank_appearances(book):
        if appearance.get("rankType") == rank:
            return appearance.get("rankPosition")
    return None


def _top_books_for_rank(books, rank, limit=4):
    return sorted(
        books,
        key=lambda book: (_position_for_rank(book, rank) or 9999, book.get("title", "")),
    )[:limit]


def _book_plain_title(book):
    title = decode_fanqie_font_text(book.get("title") or "") or "未命名"
    return f"《{title}》"


def _book_link(book):
    title = _escape_md(book.get("title") or "未命名")
    url = book.get("detailUrl")
    if url:
        return f"[《{title}》]({url})"
    return f"《{title}》"


def _original_core_rows(book):
    rows = [
        ("站点", book.get("site")),
        ("榜单/名次", _book_rank_label(book)),
        ("书籍ID", book.get("bookId")),
        ("书名", book.get("title")),
        ("作者", book.get("author")),
        ("作者等级", _level_label(book.get("authorLevel")) if book.get("authorLevel") not in (None, "") else None),
        ("分类", book.get("category")),
        ("子分类", book.get("subCategory")),
        ("状态", book.get("status")),
        ("评分", _book_rating_label(book)),
        ("评分人数", _book_rating_count_label(book)),
        ("字数", _format_word_count(_word_count(book)) if _word_count(book) else None),
        ("总点击", book.get("totalClicks")),
        ("阅读数", book.get("readCount")),
        ("总推荐", book.get("totalRecom")),
        ("总收藏", book.get("totalCollect")),
        ("标签", book.get("tags")),
        ("最新章节", book.get("latestChapter")),
        ("发布日期", book.get("publishDate")),
        ("作者作品数", book.get("authorWorksCount")),
        ("详情页", book.get("detailUrl")),
        ("封面", book.get("coverUrl")),
        ("抓取时间", book.get("scrapedAt")),
    ]
    return [(label, value) for label, value in rows if value not in (None, "", [])]


def _book_rating_label(book):
    for field in ("rating", "score", "bookScore", "rankScore"):
        value = book.get(field)
        if value not in (None, ""):
            return f"{value}分"
    return "未抓到"


def _book_rating_count_label(book):
    for field in ("ratingCount", "scoreCount", "rateCount"):
        value = book.get(field)
        if value not in (None, ""):
            return value
    return "未抓到"


def _format_original_value(value):
    if value in (None, ""):
        return "未抓到"
    if isinstance(value, list):
        return _escape_md("、".join(str(item) for item in value)) if value else "未抓到"
    if isinstance(value, dict):
        return _escape_md(json.dumps(value, ensure_ascii=False))
    text = str(value)
    if text.startswith("http://") or text.startswith("https://"):
        safe = _escape_md(text)
        return f"[{safe}]({text})"
    return _escape_md(text)


def _ordered_book_fields(book):
    preferred = [
        "bookId",
        "site",
        "title",
        "author",
        "authorLevel",
        "category",
        "subCategory",
        "status",
        "rating",
        "ratingCount",
        "score",
        "scoreCount",
        "wordCount",
        "readCount",
        "synopsis",
        "synopsis_short",
        "tags",
        "totalClicks",
        "totalRecom",
        "totalCollect",
        "latestChapter",
        "lastUpdateDate",
        "publishDate",
        "authorWorksCount",
        "detailUrl",
        "coverUrl",
        "rankType",
        "rankPosition",
        "ranks",
        "rankAppearances",
        "rankCountText",
        "rankPosDiff",
        "fanqieCategoryId",
        "fontEncrypted",
        "scrapedAt",
    ]

    ordered = {}
    for field in preferred:
        value = book.get(field)
        if value not in (None, "", []):
            ordered[field] = _decode_report_value(value)

    for field in sorted(book):
        if field in ordered:
            continue
        value = book.get(field)
        if value not in (None, "", []):
            ordered[field] = _decode_report_value(value)

    return ordered


def _decode_report_value(value):
    if isinstance(value, str):
        return decode_fanqie_font_text(value)
    if isinstance(value, list):
        return [_decode_report_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _decode_report_value(item) for key, item in value.items()}
    return value


def _synopsis(book):
    return _clean_text(book.get("synopsis") or book.get("synopsis_short") or "")


def _first_sentence(text):
    text = _clean_text(text)
    if not text:
        return ""
    match = re.match(r"^([^。！？!?]+[。！？!?]?)", text)
    return match.group(1) if match else text


def _clean_text(value):
    return " ".join(decode_fanqie_font_text(str(value or "")).split())


def _truncate(text, limit=80):
    text = _clean_text(text)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip("，。、；,. ") + "..."


def _escape_md(value):
    return _clean_text(value).replace("|", "\\|")


def _coerce_int(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _word_count(book):
    value = book.get("wordCount")
    if isinstance(value, (int, float)):
        return int(value) if value > 0 else None
    if isinstance(value, str):
        value = value.strip()
        wan = re.search(r"([\d.]+)\s*万", value)
        if wan:
            return int(float(wan.group(1)) * 10000)
        digits = re.sub(r"\D", "", value)
        return int(digits) if digits else None
    return None


def _format_word_count(value):
    value = _coerce_int(value)
    if not value:
        return "未知"
    if value >= 10000:
        return f"{value / 10000:.1f}万字"
    return f"{value}字"


def _median(values):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def _counter_text(counter, limit=3):
    if not counter:
        return "暂无"
    return "、".join(f"{name}({count})" for name, count in counter.most_common(limit))


def _category_examples(books, categories):
    examples = []
    seen = set()
    for category in categories:
        if category in seen:
            continue
        match = next((book for book in books if book.get("category") == category), None)
        if match:
            examples.append((category, match))
            seen.add(category)
    return examples


def _title_pattern_examples(books, patterns):
    examples = []
    for pattern in patterns[:6]:
        label = pattern.get("pattern")
        matched = []
        for book in books:
            title = book.get("title") or ""
            if title and _title_matches_pattern(title, label):
                matched.append(_book_plain_title(book))
            if len(matched) >= 3:
                break
        if matched:
            examples.append((label, matched))
    return examples


def _title_matches_pattern(title, pattern):
    if pattern == "冒号分隔":
        return "：" in title or ":" in title
    if pattern == "书名号":
        return "《" in title or "》" in title
    if pattern == "问句":
        return "？" in title or "?" in title or any(word in title for word in ["怎么", "如何", "为什么"])
    if pattern == "我在XX":
        return title.startswith("我在")
    if pattern == "数字开头":
        return bool(re.match(r"^[\d一二三四五六七八九十]", title))
    if pattern == "人名/称呼":
        return any(word in title for word in ["哥", "爷", "总", "姐", "嫂"])
    if pattern == "系统/金手指":
        return any(word in title for word in ["系统", "面板", "签到", "模拟器", "金手指", "商城"])
    if pattern == "重生/穿越":
        return any(word in title for word in ["重生", "穿越", "回到", "回到过去"])
    if pattern == "全球/全民":
        return any(word in title for word in ["全球", "全民", "全世界", "诸天"])
    return False


def _synopsis_examples(books, limit=7):
    selected = []
    seen_types = set()
    sorted_books = sorted((book for book in books if _synopsis(book)), key=_book_sort_key)
    for book in sorted_books:
        hook_type = _infer_hook_type(_synopsis(book))
        if hook_type in seen_types:
            continue
        selected.append(book)
        seen_types.add(hook_type)
        if len(selected) >= limit:
            return selected

    for book in sorted_books:
        if book not in selected:
            selected.append(book)
        if len(selected) >= limit:
            break
    return selected


def _infer_hook_type(text):
    opening = _clean_text(text)[:50]
    if not opening:
        return "未知"
    if re.match(r'^[“"「【]', opening) or re.search(r'[“"「].*[”"」]', opening[:30]):
        return "对话式"
    if any(word in opening for word in [
        "忽然", "突然", "猛地", "一脚", "一拳", "冲", "跑", "杀",
        "爆炸", "坠落", "醒来", "睁开眼", "一脚踹",
    ]):
        return "动作/冲突"
    if any(word in opening for word in [
        "夜", "月", "风", "雨", "山", "城", "海", "天空",
        "清晨", "黄昏", "黑暗", "阳光",
    ]):
        return "场景描写"
    if any(word in opening for word in [
        "我叫", "我是一个", "我原本", "我曾经", "没想到",
        "万万没想到", "谁曾想",
    ]):
        return "独白/内心"
    if any(word in opening for word in [
        "公元", "这个世界", "在这个世界", "据说", "传说",
        "某年", "XX年", "故事发生",
    ]):
        return "设定说明"
    if any(word in opening for word in ["如果", "假如", "当你", "当你发现", "你知道"]):
        return "问题/悬念"
    return "其他"


def _level_label(level):
    if level in (None, ""):
        return "未知"
    if isinstance(level, int):
        return AUTHOR_LEVELS.get(level, f"LV{level}")
    text = str(level)
    if text in AUTHOR_LEVELS.values():
        return text
    match = re.search(r"\d+", text)
    if match:
        value = int(match.group(0))
        return AUTHOR_LEVELS.get(value, f"LV{value}")
    return text
