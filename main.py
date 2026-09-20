#!/usr/bin/env python3
"""
小说排行榜扫描工具
自动抓取榜单数据，分析分类/标题/简介/作者等维度，生成报告。

用法:
  python main.py full                    # 完整流水线
  python main.py scrape                  # 只抓取榜单
  python main.py detail --limit 20       # 只获取前20本详情
  python main.py analyze                 # 只运行分析
  python main.py report                  # 只生成报告
  python main.py ingest --dry-run        # 导出后端导入格式
"""

import argparse
import json
import logging
import os
from datetime import datetime

from config import (
    ALL_RANKINGS,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_SITE,
    FANQIE_MAX_PAGES_PER_RANK,
    MAX_PAGES_PER_RANK,
    SITE_RANKINGS,
    get_site_name,
    get_site_rankings,
)
from session import QidianSession
from scraper.ranking import scrape_all_rankings
from scraper.fanqie import scrape_all_fanqie_rankings
from scraper.detail import fetch_details_batch
from analysis.filter import filter_books
from analysis.genre import analyze_genre
from analysis.title import analyze_title
from analysis.synopsis import analyze_synopsis
from analysis.author import analyze_author
from analysis.wordcount import analyze_wordcount
from analysis.cross_rank import analyze_cross_rank
from analysis.ranks import sort_ranks
from report.markdown import generate_report
from ingestion import (
    build_ingestion_payload,
    load_json_file,
    push_payload,
    write_json_file,
    validate_ingestion_result,
)


REPORT_BOOK_SAMPLE_LIMIT = None


def setup_logging(verbose=False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def save_json(data, filepath):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logging.info(f"已保存: {filepath}")


def load_latest_file(directory, pattern=None, site=None):
    """加载目录中最新的 JSON 文件"""
    if not os.path.exists(directory):
        return None
    files = [f for f in os.listdir(directory) if f.endswith(".json")]
    if pattern:
        files = [f for f in files if pattern in f]
    if not files:
        return None
    files.sort(reverse=True)

    for filename in files:
        path = os.path.join(directory, filename)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if site and isinstance(data, dict):
            payload_site = data.get("site") or DEFAULT_SITE
            if payload_site != site:
                continue

        return data

    return None


def _coerce_position(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _collect_rank_appearances(book, default_rank=None):
    """收集一本书在各榜单中的出现信息。"""
    appearances = []

    rank = book.get("rankType") or default_rank
    if rank:
        appearances.append({
            "rankType": rank,
            "rankPosition": _coerce_position(book.get("rankPosition")),
        })

    for appearance in book.get("rankAppearances", []) or []:
        if not isinstance(appearance, dict):
            continue
        rank = appearance.get("rankType")
        if not rank:
            continue
        appearances.append({
            "rankType": rank,
            "rankPosition": _coerce_position(appearance.get("rankPosition")),
        })

    for rank in book.get("ranks", []) or []:
        if rank:
            appearances.append({"rankType": rank, "rankPosition": None})

    return appearances


def _merge_appearance(appearances_by_rank, appearance):
    rank = appearance.get("rankType")
    if not rank:
        return

    position = _coerce_position(appearance.get("rankPosition"))
    current = appearances_by_rank.get(rank)
    if current is None:
        item = {"rankType": rank}
        if position is not None:
            item["rankPosition"] = position
        appearances_by_rank[rank] = item
        return

    current_position = _coerce_position(current.get("rankPosition"))
    if position is not None and (current_position is None or position < current_position):
        current["rankPosition"] = position


def merge_ranked_books(books, default_rank=None):
    """
    按 bookId 去重，同时保留每本书出现过的榜单与名次。

    这样总体分析不会被同一本书重复放大，跨榜和各榜单对比也不会丢信息。
    """
    merged_by_id = {}
    appearances_by_id = {}
    rank_fields = {"rankType", "rankPosition", "rankAppearances", "ranks"}

    for book in books or []:
        book_id = str(book.get("bookId", "")).strip()
        if not book_id:
            continue

        if book_id not in merged_by_id:
            merged = dict(book)
            merged["bookId"] = book_id
            merged_by_id[book_id] = merged
            appearances_by_id[book_id] = {}
        else:
            merged = merged_by_id[book_id]
            for key, value in book.items():
                if key in rank_fields or value in (None, "", []):
                    continue
                if merged.get(key) in (None, "", []):
                    merged[key] = value

        for appearance in _collect_rank_appearances(book, default_rank):
            _merge_appearance(appearances_by_id[book_id], appearance)

    result = []
    for book_id, book in merged_by_id.items():
        appearances = [
            appearances_by_id[book_id][rank]
            for rank in sort_ranks(appearances_by_id[book_id])
        ]
        ranks = [appearance["rankType"] for appearance in appearances]

        book["rankAppearances"] = appearances
        book["ranks"] = ranks
        if appearances:
            first = appearances[0]
            book["rankType"] = first["rankType"]
            if "rankPosition" in first:
                book["rankPosition"] = first["rankPosition"]

        result.append(book)

    return result


def merge_ranking_data(ranking_data, site=None):
    """合并 scrape_all_rankings 返回的 {rank_key: [books]} 数据。"""
    books = []
    for rank_key, rank_books in (ranking_data or {}).items():
        for book in rank_books:
            item = dict(book)
            item.setdefault("rankType", rank_key)
            if site:
                item.setdefault("site", site)
            books.append(item)
    return merge_ranked_books(books)


def _book_report_sort_key(book):
    rank_order = {rank: index for index, rank in enumerate(ALL_RANKINGS)}
    appearances = book.get("rankAppearances") or _collect_rank_appearances(book)
    keys = []
    for appearance in appearances:
        rank = appearance.get("rankType")
        position = _coerce_position(appearance.get("rankPosition"))
        keys.append((rank_order.get(rank, 999), position if position is not None else 9999))
    best_rank = min(keys) if keys else (999, 9999)
    return (best_rank[0], best_rank[1], book.get("title", ""))


def _json_safe_value(value):
    if isinstance(value, dict):
        return {
            str(key): _json_safe_value(item)
            for key, item in value.items()
            if item not in (None, "", [])
        }
    if isinstance(value, list):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def build_report_book_snapshot(books, limit=REPORT_BOOK_SAMPLE_LIMIT):
    """
    保留报告需要的完整书籍快照。

    分析 JSON 以前只保存聚合指标，报告只能输出统计表。现在保留每本书
    已抓到的全部字段，报告既能做总结，也能附上原始书籍档案。
    """
    if not books:
        return []

    snapshot = []
    sorted_books = sorted(merge_ranked_books(books), key=_book_report_sort_key)
    if limit:
        sorted_books = sorted_books[:limit]

    for book in sorted_books:
        item = {
            str(key): _json_safe_value(value)
            for key, value in book.items()
            if value not in (None, "", [])
        }
        if "synopsis" not in item and book.get("synopsis_short"):
            item["synopsis"] = _json_safe_value(book.get("synopsis_short"))
        snapshot.append(item)

    return snapshot


def load_latest_report_books(output_dir, site=None):
    """加载报告可用的最近书籍样本，用于兼容旧版 analysis JSON。"""
    for directory, pattern in (
        (os.path.join(output_dir, "analysis"), "filtered"),
        (os.path.join(output_dir, "details"), "all_details"),
    ):
        data = load_latest_file(directory, pattern, site=site)
        if data and data.get("books"):
            return build_report_book_snapshot(data.get("books", []))
    return []


def _books_from_payload(payload, default_rank=None):
    if isinstance(payload, list):
        return merge_ranked_books(payload, default_rank=default_rank)

    if not isinstance(payload, dict):
        return []

    site = payload.get("site")
    if isinstance(payload.get("rankings"), dict):
        return merge_ranking_data(payload["rankings"], site=site)

    rank_key = payload.get("rankKey") or default_rank
    books = []
    for book in payload.get("books", []) or []:
        item = dict(book)
        if site:
            item.setdefault("site", site)
        books.append(item)
    return merge_ranked_books(books, default_rank=rank_key)


def load_latest_raw_books(output_dir, site=None):
    """加载最近一次 scrape 结果；优先使用 all_rankings 快照。"""
    raw_dir = os.path.join(output_dir, "raw")
    snapshot = load_latest_file(raw_dir, "all_rankings", site=site)
    if snapshot:
        return _books_from_payload(snapshot)

    books = []
    for rank_key in get_site_rankings(site):
        data = load_latest_file(raw_dir, f"{rank_key}_", site=site)
        if data:
            books.extend(_books_from_payload(data, default_rank=rank_key))
    return merge_ranked_books(books)


# ─── 子命令实现 ──────────────────────────────────────────────

def _arg_site(args):
    return getattr(args, "site", DEFAULT_SITE) or DEFAULT_SITE


def _validate_rankings(site, rank_keys):
    rankings = get_site_rankings(site)
    unknown = [key for key in (rank_keys or []) if key not in rankings]
    if unknown:
        valid = " ".join(rankings)
        raise SystemExit(
            f"未知{get_site_name(site)}榜单: {', '.join(unknown)}\n"
            f"可选榜单: {valid}"
        )


def _attach_site_to_rankings(ranking_data, site):
    for books in (ranking_data or {}).values():
        for book in books:
            book.setdefault("site", site)
    return ranking_data


def _input_site(data, args):
    if isinstance(data, dict) and data.get("site"):
        return data["site"]
    return _arg_site(args)


def cmd_scrape(args):
    """抓取榜单列表"""
    site = _arg_site(args)
    site_name = get_site_name(site)
    rankings_config = get_site_rankings(site)
    _validate_rankings(site, args.rankings)
    pages = args.pages if args.pages is not None else (FANQIE_MAX_PAGES_PER_RANK if site == "fanqie" else MAX_PAGES_PER_RANK)

    session = QidianSession(proxy=args.proxy, cookie=args.cookie)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if site == "fanqie":
        all_data = scrape_all_fanqie_rankings(
            session,
            rank_keys=args.rankings,
            max_pages=pages,
        )
    else:
        all_data = scrape_all_rankings(
            session,
            rank_keys=args.rankings,
            max_pages=pages,
            strategy=args.strategy,
        )
    all_data = _attach_site_to_rankings(all_data, site)

    # 榜单采集是发布前置条件：任一请求榜单为空都视为失败，避免把不完整结果覆盖为当天快照。
    expected_keys = args.rankings or list(rankings_config.keys())
    missing = [key for key in expected_keys if not all_data.get(key)]
    if missing:
        raise SystemExit(f"{site_name}榜单采集不完整，拒绝导入空榜: {', '.join(missing)}")

    total = 0
    for rank_key, books in all_data.items():
        total += len(books)
        filepath = os.path.join(args.output_dir, "raw", f"{site}_{rank_key}_{timestamp}.json")
        save_json({
            "site": site,
            "siteName": site_name,
            "rankKey": rank_key,
            "rankName": rankings_config[rank_key]["name"],
            "timestamp": datetime.now().isoformat(),
            "count": len(books),
            "books": books,
        }, filepath)

    merged_books = merge_ranking_data(all_data, site=site)
    snapshot_path = os.path.join(args.output_dir, "raw", f"all_rankings_{site}_{timestamp}.json")
    save_json({
        "site": site,
        "siteName": site_name,
        "timestamp": datetime.now().isoformat(),
        "rankingCount": len(all_data),
        "rawCount": total,
        "uniqueCount": len(merged_books),
        "rankings": all_data,
        "books": merged_books,
    }, snapshot_path)

    print(f"\n{site_name}抓取完成: {total} 条榜单记录，去重后 {len(merged_books)} 本书（{len(all_data)} 个榜单）")
    return {
        "site": site,
        "timestamp": timestamp,
        "rankings": all_data,
        "books": merged_books,
    }


def cmd_detail(args, books=None):
    """获取书籍详情"""
    site = _arg_site(args)
    site_name = get_site_name(site)
    session = QidianSession(proxy=args.proxy, cookie=args.cookie)

    # 加载榜单数据
    input_path = getattr(args, "input", None)
    if books is not None:
        books = merge_ranked_books(books)
    elif input_path:
        with open(input_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        site = _input_site(raw_data, args)
        site_name = get_site_name(site)
        books = _books_from_payload(raw_data)
    else:
        books = load_latest_raw_books(args.output_dir, site=site)

    if not books:
        print("没有找到榜单数据，请先运行 scrape 命令")
        return

    if site == "fanqie":
        results = books[:args.limit] if args.limit else books
        print(f"番茄榜单已包含基础详情，复用 {len(results)} 本书（limit={args.limit}）")
    else:
        print(f"准备获取 {len(books)} 本书的详情（limit={args.limit}）")
        details_dir = os.path.join(args.output_dir, "details")
        results = fetch_details_batch(session, books, limit=args.limit, output_dir=details_dir)

    # 保存合并结果
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(args.output_dir, "details", f"all_details_{timestamp}.json")
    save_json({
        "site": site,
        "siteName": site_name,
        "timestamp": datetime.now().isoformat(),
        "count": len(results),
        "books": results,
    }, filepath)

    print(f"\n详情获取完成: {len(results)} 本书")
    return results


def cmd_filter(args):
    """筛选书籍"""
    # 加载详情数据
    site = _arg_site(args)
    site_name = get_site_name(site)
    input_path = getattr(args, "input", None)
    if input_path:
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        site = _input_site(data, args)
        site_name = get_site_name(site)
        books = data.get("books", [])
    else:
        data = load_latest_file(os.path.join(args.output_dir, "details"), "all_details", site=site)
        if not data:
            print("没有找到详情数据，请先运行 detail 命令")
            return
        books = data.get("books", [])

    books = merge_ranked_books(books)
    filtered = filter_books(books, months=args.months, max_level=args.max_level)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(args.output_dir, "analysis", f"filtered_{timestamp}.json")
    save_json({
        "site": site,
        "siteName": site_name,
        "timestamp": datetime.now().isoformat(),
        "totalBefore": len(books),
        "totalAfter": len(filtered),
        "filterMonths": args.months,
        "maxAuthorLevel": args.max_level,
        "books": filtered,
    }, filepath)

    print(f"\n筛选完成: {len(books)} → {len(filtered)} 本书")
    return filtered


def cmd_analyze(args):
    """运行分析"""
    # 加载筛选后数据
    site = _arg_site(args)
    site_name = get_site_name(site)
    input_path = getattr(args, "input", None)
    if input_path:
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        site = _input_site(data, args)
        site_name = get_site_name(site)
        books = data.get("books", [])
    else:
        data = load_latest_file(os.path.join(args.output_dir, "analysis"), "filtered", site=site)
        if not data:
            # 如果没有筛选数据，尝试加载详情数据
            data = load_latest_file(os.path.join(args.output_dir, "details"), "all_details", site=site)
        if not data:
            print("没有找到数据，请先运行 scrape + detail + filter 命令")
            return
        books = data.get("books", [])

    books = merge_ranked_books(books)
    print(f"分析 {len(books)} 本书...")

    analyses = getattr(args, "analyses", None) or [
        "genre", "title", "synopsis", "author", "wordcount", "crossrank"
    ]
    results = {}

    analysis_funcs = {
        "genre": ("分类分布", analyze_genre),
        "title": ("标题分析", analyze_title),
        "synopsis": ("简介分析", analyze_synopsis),
        "author": ("作者等级", analyze_author),
        "wordcount": ("字数分布", analyze_wordcount),
        "crossrank": ("跨榜上榜", analyze_cross_rank),
    }

    for key in analyses:
        if key not in analysis_funcs:
            print(f"未知分析: {key}")
            continue
        name, func = analysis_funcs[key]
        print(f"  运行: {name}")
        result = func(books)
        results[key] = result

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(args.output_dir, "analysis", f"analysis_{timestamp}.json")
    save_json({
        "site": site,
        "siteName": site_name,
        "timestamp": datetime.now().isoformat(),
        "bookCount": len(books),
        "books": build_report_book_snapshot(books),
        "analyses": results,
    }, filepath)

    print(f"\n分析完成: {len(results)} 个维度")
    return results


def cmd_report(args):
    """生成 Markdown 报告"""
    # 加载分析数据
    site = _arg_site(args)
    input_path = getattr(args, "input", None)
    if input_path:
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        site = _input_site(data, args)
    else:
        data = load_latest_file(os.path.join(args.output_dir, "analysis"), "analysis", site=site)
        if not data:
            print("没有找到分析数据，请先运行 analyze 命令")
            return

    if not data.get("books") and not input_path:
        books = load_latest_report_books(args.output_dir, site=site)
        if books:
            data["books"] = books

    data.setdefault("site", site)
    data.setdefault("siteName", get_site_name(site))

    report_text = generate_report(data)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = getattr(args, "output", None) or os.path.join(
        args.output_dir, "reports", f"report_{timestamp}.md"
    )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    print(f"\n报告已生成: {output_path}")
    print(f"共 {len(report_text)} 字符")
    return output_path


def ingestion_result_summary(result):
    """日常日志只报告批次数和新增任务数，避免打印数千条任务；原始返回值保持不变。"""
    if not isinstance(result, dict) or "accepted" not in result:
        return result
    tasks = result.get("collection_tasks", 0)
    return {
        "accepted": result["accepted"],
        "snapshot_count": len(result.get("snapshot_ids") or []),
        "created_tasks": len(tasks) if isinstance(tasks, list) else tasks,
    }


def cmd_ingest(args):
    """将榜单快照导出或推送到独立 rank-ingestion-service，业务服务只读。

    该命令是可选的，不改变 ``scrape``/``full`` 的既有输出。默认读取
    ``output/raw/all_rankings_*.json`` 最新快照；使用 ``--output`` 可只
    生成规范化 JSON 而不发起网络请求，便于调度器和其他语言复用协议。
    """
    input_path = getattr(args, "input", None)
    if input_path:
        data = load_json_file(input_path)
        site = _input_site(data, args)
    else:
        site = _arg_site(args)
        data = load_latest_file(os.path.join(args.output_dir, "raw"), "all_rankings", site=site)
        if not data:
            raise SystemExit("没有找到榜单快照，请先运行 scrape 命令或使用 --input 指定 JSON")

    payload = build_ingestion_payload(data, site=site)
    output_path = getattr(args, "output", None)
    if output_path:
        write_json_file(payload, output_path)
        print(f"已导出导入 payload: {output_path}（{payload['count']} 条榜单记录）")

    if getattr(args, "dry_run", False):
        if not output_path:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        return payload

    endpoint = getattr(args, "url", None) or os.getenv("RANK_INGEST_URL", "")
    if not endpoint:
        raise SystemExit("未设置导入接口 URL，请使用 --url 或 RANK_INGEST_URL；仅导出请加 --dry-run")

    try:
        result = push_payload(
            payload,
            url=endpoint,
            token=getattr(args, "token", None),
            timeout=args.timeout,
            retries=args.retries,
        )
        validate_ingestion_result(result, payload)
    except Exception as exc:
        logging.error("榜单导入失败: %s", exc)
        raise SystemExit(1) from exc

    print(json.dumps(result if getattr(args, "verbose", False) else ingestion_result_summary(result), ensure_ascii=False, indent=2))
    return result


def cmd_full(args):
    """完整流水线"""
    site_name = get_site_name(_arg_site(args))
    print("=" * 60)
    print(f"  {site_name}排行榜扫描 - 完整流水线")
    print("=" * 60)
    print()

    # Step 1: 抓取榜单
    print("Step 1/5: 抓取榜单列表...")
    scrape_result = cmd_scrape(args)
    print()

    # Step 2: 获取详情
    print("Step 2/5: 获取书籍详情...")
    args.input = None
    cmd_detail(args, books=scrape_result["books"])
    print()

    # Step 3: 筛选
    print("Step 3/5: 筛选...")
    cmd_filter(args)
    print()

    # Step 4: 分析
    print("Step 4/5: 分析...")
    cmd_analyze(args)
    print()

    # Step 5: 报告
    print("Step 5/5: 生成报告...")
    cmd_report(args)
    print()

    print("=" * 60)
    print(f"  完成！查看 {os.path.join(args.output_dir, 'reports')} 目录获取报告")
    print("=" * 60)


# ─── CLI 入口 ────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="小说排行榜扫描工具 - 抓取榜单数据，分析题材趋势",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  %(prog)s full --strategy mobile            # 起点完整流水线
  %(prog)s full --site fanqie                 # 番茄完整流水线
  %(prog)s full --site fanqie --pages 1       # 番茄快速测试
  %(prog)s scrape --rankings sanjiang strong  # 起点只抓三江和强推
  %(prog)s scrape --site fanqie --rankings male_read female_new
  %(prog)s detail --limit 20                  # 只获取前20本详情
  %(prog)s analyze --analyses genre title     # 只运行指定分析
  %(prog)s report                             # 生成报告

起点榜单:
  sanjiang  三江推荐 (编辑推荐的上升期新书)
  strong    强推榜   (编辑强推的重点书)
  newbook   新书榜   (新发布书籍排名)
  hotsales  畅销榜   (VIP订阅畅销书)

番茄榜单:
  male_read    男频阅读榜
  male_new     男频新书榜
  female_read  女频阅读榜
  female_new   女频新书榜
        """,
    )

    # 子命令
    subparsers = parser.add_subparsers(dest="command", help="操作类型")
    subparsers.required = True

    # scrape
    p_scrape = subparsers.add_parser("scrape", help="抓取榜单列表")
    p_scrape.add_argument("--rankings", nargs="+",
                          default=None, help="指定榜单 (默认当前站点全部)")
    p_scrape.add_argument("--pages", type=int, default=None, help="最大页数（番茄默认10，其他默认5；番茄不足完整榜单时拒绝发布）")
    p_scrape.add_argument("--strategy", choices=["auto", "desktop", "mobile"],
                          default="auto", help="抓取策略 (默认auto)")

    # detail
    p_detail = subparsers.add_parser("detail", help="获取书籍详情")
    p_detail.add_argument("--input", help="输入JSON文件路径")
    p_detail.add_argument("--limit", type=int, help="限制获取数量")

    # filter
    p_filter = subparsers.add_parser("filter", help="筛选书籍")
    p_filter.add_argument("--input", help="输入JSON文件路径")
    p_filter.add_argument("--months", type=int, default=6, help="保留几个月内的书 (默认6)")
    p_filter.add_argument("--max-level", type=int, default=5, help="最大作者等级 (默认5)")

    # analyze
    p_analyze = subparsers.add_parser("analyze", help="运行分析")
    p_analyze.add_argument("--input", help="输入JSON文件路径")
    p_analyze.add_argument("--analyses", nargs="+",
                           choices=["genre", "title", "synopsis", "author", "wordcount", "crossrank"],
                           help="指定运行的分析 (默认全部)")

    # report
    p_report = subparsers.add_parser("report", help="生成Markdown报告")
    p_report.add_argument("--input", help="输入分析JSON文件路径")
    p_report.add_argument("--output", "-o", help="输出报告路径")

    # ingest / push
    p_ingest = subparsers.add_parser(
        "ingest", aliases=["push"], help="导出或推送榜单快照到后端内部接口"
    )
    p_ingest.add_argument("--input", help="输入榜单 JSON 文件（默认读取最新 raw/all_rankings）")
    p_ingest.add_argument("--output", "-o", help="只导出规范化导入 JSON 到指定路径")
    p_ingest.add_argument("--url", help="内部导入接口 URL（默认读取 RANK_INGEST_URL）")
    p_ingest.add_argument("--token", help="内部接口 token（默认读取 RANK_INGEST_TOKEN）")
    p_ingest.add_argument("--timeout", type=float, default=30.0, help="HTTP 超时秒数（默认30）")
    p_ingest.add_argument("--retries", type=int, default=3, help="失败重试次数（默认3）")
    p_ingest.add_argument("--dry-run", action="store_true", help="只转换/导出，不调用后端")

    # full
    p_full = subparsers.add_parser("full", help="完整流水线 (scrape→detail→filter→analyze→report)")
    p_full.add_argument("--rankings", nargs="+",
                        default=None, help="指定榜单")
    p_full.add_argument("--pages", type=int, default=None, help="最大页数（番茄默认10，其他默认5）")
    p_full.add_argument("--strategy", choices=["auto", "desktop", "mobile"],
                        default="auto", help="抓取策略")
    p_full.add_argument("--limit", type=int, help="限制详情获取数量")
    p_full.add_argument("--months", type=int, default=6, help="筛选月数")
    p_full.add_argument("--max-level", type=int, default=5, help="最大作者等级")

    # 全局选项
    for sub in [p_scrape, p_detail, p_filter, p_analyze, p_report, p_full, p_ingest]:
        sub.add_argument("--site", choices=list(SITE_RANKINGS.keys()), default=DEFAULT_SITE,
                         help="站点: qidian 或 fanqie (默认qidian)")
        sub.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="输出目录")
        sub.add_argument("--proxy", help="HTTP代理")
        sub.add_argument("--cookie", help="Cookie字符串")
        sub.add_argument("--verbose", "-v", action="store_true", help="详细日志")

    args = parser.parse_args()
    setup_logging(args.verbose)

    cmd_map = {
        "scrape": cmd_scrape,
        "detail": cmd_detail,
        "filter": cmd_filter,
        "analyze": cmd_analyze,
        "report": cmd_report,
        "full": cmd_full,
        "ingest": cmd_ingest,
        "push": cmd_ingest,
    }

    cmd_map[args.command](args)


if __name__ == "__main__":
    main()
