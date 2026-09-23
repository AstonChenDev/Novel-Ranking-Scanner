"""红果、抖音、快手短剧榜单采集器。

本模块只读取平台榜单并输出扫描器统一记录，不下载视频、不调用播放接口，也不
写数据库。所有分页都以平台返回的终止信号为准；缺页、游标停滞、重复作品、
排名断裂和响应结构漂移都会中止本批次，避免把残缺榜单发布成成功快照。
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Mapping, Optional
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from config import (
    DOUYIN_DRAMA_BILLBOARD,
    DOUYIN_RANKINGS,
    HONGGUO_BASE,
    HONGGUO_RANKINGS,
    KUAISHOU_DRAMA_BILLBOARD,
    KUAISHOU_RANKINGS,
    SHORT_DRAMA_MAX_PAGES_PER_RANK,
)


logger = logging.getLogger(__name__)

DOUYIN_PAGE_SIZE = 15
SHORT_DRAMA_SITES = frozenset({"hongguo", "douyin", "kuaishou"})

JSON_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
HONGGUO_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": HONGGUO_BASE + "/",
}
KUAISHOU_HEADERS = {**JSON_HEADERS, "User-Agent": "kwai-android"}


class IncompleteDramaRankingError(RuntimeError):
    """平台没有返回一个可证明完整且连续的榜单。"""


def _text(value: Any) -> str:
    return "" if value in (None, "") else str(value).strip()


def _int_or_none(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_chinese_count(value: Any) -> Optional[int]:
    """把 ``1.2亿``、``8624万热度`` 等展示值转换为整数。"""
    text = _text(value).replace(",", "")
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*([亿万]?)", text)
    if not match:
        return None
    number = float(match.group(1))
    multiplier = {"亿": 100_000_000, "万": 10_000, "": 1}[match.group(2)]
    return int(round(number * multiplier))


def _first_url(value: Any) -> str:
    if isinstance(value, Mapping):
        urls = value.get("url_list") or []
        if isinstance(urls, list) and urls:
            return _text(urls[0])
        return _text(value.get("url") or value.get("uri"))
    if isinstance(value, list) and value:
        return _text(value[0])
    return _text(value)


def _secure_kuaishou_cover_url(value: Any) -> str:
    """仅把快手已知图片域的明文地址升级为同路径 HTTPS。"""
    url = _text(value)
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        trusted = any(host == domain or host.endswith("." + domain) for domain in ("yximgs.com", "kwimgs.com"))
        if (parts.scheme == "http" and trusted and parts.port is None
                and parts.username is None and parts.password is None):
            return urlunsplit(("https", parts.netloc, parts.path, parts.query, parts.fragment))
    except ValueError:
        return url
    return url


def _iso_from_timestamp(value: Any) -> str:
    timestamp = _int_or_none(value)
    if not timestamp:
        return ""
    try:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except (OSError, OverflowError, ValueError):
        return ""


def _get_response(session, url: str, headers: Mapping[str, str]):
    response = session.safe_get(
        url,
        delay_range=(0.1, 0.25),
        timeout=20,
        extra_headers=dict(headers),
    )
    if response is None:
        raise IncompleteDramaRankingError(f"请求失败: {url}")
    return response


def _get_json(session, url: str, headers: Mapping[str, str]) -> dict[str, Any]:
    response = _get_response(session, url, headers)
    try:
        payload = response.json()
    except (TypeError, ValueError) as error:
        raise IncompleteDramaRankingError(f"榜单响应不是 JSON: {url}") from error
    if not isinstance(payload, dict):
        raise IncompleteDramaRankingError(f"榜单响应结构异常: {url}")
    return payload


def _assert_contiguous(items: list[dict[str, Any]], rank_key: str) -> None:
    positions = [item.get("rankPosition") for item in items]
    expected = list(range(1, len(items) + 1))
    if positions != expected:
        raise IncompleteDramaRankingError(
            f"{rank_key} 排名不连续: expected=1..{len(items)} actual={positions[:10]}"
        )
    ids = [_text(item.get("bookId")) for item in items]
    if len(ids) != len(set(ids)):
        raise IncompleteDramaRankingError(f"{rank_key} 出现重复作品 ID")


def discover_douyin_scopes(session, rank_key: str) -> list[tuple[str, str]]:
    """读取抖音当前榜单分类；调用方可据此选择需要采集的题材榜。"""
    config = DOUYIN_RANKINGS[rank_key]
    url = DOUYIN_DRAMA_BILLBOARD + "tab/?use_new_billboard=1"
    payload = _get_json(session, url, JSON_HEADERS)
    if payload.get("status_code") not in (0, None):
        raise IncompleteDramaRankingError(f"抖音榜单分类接口异常: {payload.get('status_msg')}")
    for board in payload.get("billboard_type_list") or []:
        if _int_or_none(board.get("type")) != int(config["billboardType"]):
            continue
        scopes = []
        for scope in board.get("sub_billboard_list") or []:
            key = _text(scope.get("type"))
            name = _text(scope.get("name"))
            if key and name:
                scopes.append((key, name))
        if scopes:
            return scopes
    raise IncompleteDramaRankingError(f"抖音未返回 {rank_key} 的分类定义")


def _douyin_item(raw: Mapping[str, Any], rank_key: str, position: int,
                  scope_key: str, scope_name: str) -> dict[str, Any]:
    series_id = _text(raw.get("series_id"))
    title = _text(raw.get("series_name"))
    if not series_id or not title:
        raise IncompleteDramaRankingError(f"{rank_key} 第 {position} 条缺少 series_id/title")
    stats = raw.get("stats") if isinstance(raw.get("stats"), Mapping) else {}
    author = raw.get("author") if isinstance(raw.get("author"), Mapping) else {}
    content_types = raw.get("series_content_types_new") or raw.get("series_content_types") or []
    tags = [
        _text(item.get("name"))
        for item in content_types
        if isinstance(item, Mapping) and _text(item.get("name"))
    ]
    share = raw.get("share_info") if isinstance(raw.get("share_info"), Mapping) else {}
    content_form = "comic_drama" if rank_key == "douyin_comic" else ""
    item = {
        "site": "douyin",
        "bookId": series_id,
        "title": title,
        "author": _text(author.get("nickname")),
        "category": tags[0] if tags else "",
        "synopsis_short": _text(raw.get("desc")),
        "rankType": rank_key,
        "rankPosition": position,
        "rankScopeKey": scope_key,
        "rankScopeName": scope_name,
        "coverUrl": _first_url(raw.get("cover_url")),
        "detailUrl": _text(share.get("share_url")),
        "contentKind": "short_drama",
        "contentForm": content_form,
        "heatValue": _int_or_none(raw.get("hot_value")),
        "playCount": _int_or_none(stats.get("play_vv")),
        "collectCount": _int_or_none(stats.get("collect_vv")),
        "episodeCount": _int_or_none(stats.get("total_episode")),
        "updatedEpisodeCount": _int_or_none(stats.get("updated_to_episode")),
        "sourceUpdatedAt": _iso_from_timestamp(stats.get("last_added_item_time") or raw.get("update_time")),
        "creatorId": _text(author.get("uid")),
        "creatorUniqueId": _text(author.get("unique_id")),
        "publisher": _text(author.get("enterprise_verify_reason")),
        "tags": tags,
        "seriesFormType": _int_or_none(raw.get("series_form_type")),
        "seriesType": _int_or_none(raw.get("series_type")),
        "isCharged": bool(raw.get("is_charge_series")),
        "isExclusive": bool(raw.get("is_exclusive")),
    }
    return {key: value for key, value in item.items() if value not in (None, "", [])}


def scrape_douyin_ranking(session, rank_key: str,
                           max_pages: int = SHORT_DRAMA_MAX_PAGES_PER_RANK,
                           scope_key: str = "1", scope_name: str = "总榜") -> list[dict[str, Any]]:
    config = DOUYIN_RANKINGS[rank_key]
    offset = 0
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    pinned_update_time: Any = None
    for page in range(1, max_pages + 1):
        query = urlencode({
            "billboard_type": config["billboardType"],
            "sub_billboard_type": scope_key,
            "use_new_billboard": 1,
            "offset": offset,
            "count": DOUYIN_PAGE_SIZE,
        })
        payload = _get_json(session, DOUYIN_DRAMA_BILLBOARD + "?" + query, JSON_HEADERS)
        if payload.get("status_code") not in (0, None):
            raise IncompleteDramaRankingError(
                f"{rank_key}:{scope_key} 接口异常: {payload.get('status_msg')}"
            )
        update_time = payload.get("update_time")
        if pinned_update_time in (None, ""):
            pinned_update_time = update_time
        elif update_time not in (None, "", pinned_update_time):
            raise IncompleteDramaRankingError(f"{rank_key}:{scope_key} 翻页期间榜单版本变化")
        rows = payload.get("series_infos") or []
        if not isinstance(rows, list) or not rows:
            raise IncompleteDramaRankingError(f"{rank_key}:{scope_key} 第 {page} 页为空")
        for raw in rows:
            if not isinstance(raw, Mapping):
                raise IncompleteDramaRankingError(f"{rank_key}:{scope_key} 返回非对象条目")
            series_id = _text(raw.get("series_id"))
            if not series_id or series_id in seen:
                raise IncompleteDramaRankingError(f"{rank_key}:{scope_key} 出现空或重复 series_id")
            seen.add(series_id)
            items.append(_douyin_item(raw, rank_key, len(items) + 1, scope_key, scope_name))
        if not payload.get("has_more"):
            _assert_contiguous(items, f"{rank_key}:{scope_key}")
            return items
        next_offset = _int_or_none(payload.get("offset"))
        if next_offset is None or next_offset <= offset:
            raise IncompleteDramaRankingError(f"{rank_key}:{scope_key} 翻页游标未前进")
        offset = next_offset
    raise IncompleteDramaRankingError(
        f"{rank_key}:{scope_key} 配置 {max_pages} 页不足，接口仍返回 has_more=true"
    )


def _hongguo_router_payload(html: str, route_id: str) -> dict[str, Any]:
    soup = BeautifulSoup(html or "", "html.parser")
    nodes = soup.find_all("script", attrs={"data-fn-name": "mergeLoaderData"})
    for node in nodes:
        encoded = node.get("data-fn-args")
        if not encoded:
            continue
        try:
            args = json.loads(encoded)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(args, list) or len(args) < 2 or args[0] != route_id:
            continue
        loaders = args[1] if isinstance(args[1], list) else []
        for loader in loaders:
            if not isinstance(loader, Mapping) or loader.get("key") != "content":
                continue
            router_args = loader.get("routerDataFnArgs") or []
            if not router_args:
                continue
            try:
                payload = json.loads(router_args[0])
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                return payload
    raise IncompleteDramaRankingError(f"红果页面缺少 {route_id} 榜单数据")


def _hongguo_loader_payload(text: str, route_id: str) -> dict[str, Any]:
    """解析 Modern.js loader 的普通 JSON 或流式 ``data:`` 事件。"""
    candidates = []
    try:
        candidates.append(json.loads(text))
    except (TypeError, json.JSONDecodeError):
        for line in (text or "").splitlines():
            if not line.startswith("data:"):
                continue
            try:
                candidates.append(json.loads(line[5:]))
            except json.JSONDecodeError:
                continue
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        content = candidate.get("content")
        if isinstance(content, Mapping) and isinstance(content.get("rankList"), list):
            return dict(content)
        if isinstance(candidate.get("rankList"), list):
            return dict(candidate)
    raise IncompleteDramaRankingError(f"红果 loader 缺少 {route_id} 榜单数据")


def _fetch_hongguo_payload(session, url: str, route_id: str, attempts: int = 2) -> dict[str, Any]:
    """优先读取稳定 loader；兼容完整 SSR 页面并在结构缺失时有限重取。"""
    last_error: Optional[Exception] = None
    for attempt in range(attempts):
        response = _get_response(session, url, HONGGUO_HEADERS)
        try:
            try:
                return _hongguo_loader_payload(response.text, route_id)
            except IncompleteDramaRankingError:
                return _hongguo_router_payload(response.text, route_id)
        except IncompleteDramaRankingError as error:
            last_error = error
            logger.warning("红果榜单 SSR 数据缺失，第 %s/%s 次请求", attempt + 1, attempts)
    assert last_error is not None
    raise last_error


def _hongguo_item(raw: Mapping[str, Any], rank_key: str, content_form: str) -> dict[str, Any]:
    series_id = _text(raw.get("seriesId") or raw.get("id"))
    title = _text(raw.get("title"))
    position = _int_or_none(raw.get("rank"))
    if not series_id or not title or position is None:
        raise IncompleteDramaRankingError(f"{rank_key} 存在缺少 ID、标题或排名的条目")
    tags = [_text(tag) for tag in raw.get("tags") or [] if _text(tag)]
    inferred_form = content_form
    if inferred_form == "mixed":
        if "漫剧" in tags:
            inferred_form = "comic_drama"
        elif "AI剧" in tags:
            inferred_form = "ai_drama"
    episodes = raw.get("episodeVids") or []
    score_match = re.search(r"\d+(?:\.\d+)?", _text(raw.get("scoreText")))
    item = {
        "site": "hongguo",
        "bookId": series_id,
        "title": title,
        "category": tags[0] if tags else "",
        "synopsis_short": _text(raw.get("description")),
        "rankType": rank_key,
        "rankPosition": position,
        "rankScopeKey": "total",
        "rankScopeName": "总榜",
        "coverUrl": _text(raw.get("cover")),
        "detailUrl": urljoin(HONGGUO_BASE + "/", _text(raw.get("href"))),
        "contentKind": "short_drama",
        "contentForm": inferred_form,
        "heatValue": parse_chinese_count(raw.get("heatText")),
        "heatText": _text(raw.get("heatText")),
        "collectCount": parse_chinese_count(raw.get("favoriteText")),
        "likeCount": parse_chinese_count(raw.get("likeText")),
        "rating": float(score_match.group(0)) if score_match else None,
        "episodeCount": len(episodes) if isinstance(episodes, list) else None,
        "tags": tags,
        "platformLabels": [_text(label) for label in raw.get("statusTags") or [] if _text(label)],
    }
    return {key: value for key, value in item.items() if value not in (None, "", [])}


def scrape_hongguo_ranking(session, rank_key: str,
                            max_pages: int = SHORT_DRAMA_MAX_PAGES_PER_RANK) -> list[dict[str, Any]]:
    config = HONGGUO_RANKINGS[rank_key]
    route = config["route"]
    route_id = "rank_" + route + "/page"
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    total_pages: Optional[int] = None
    for page in range(1, max_pages + 1):
        query = {"__loader": route_id, "__ssrDirect": "true"}
        if page > 1:  # page=1 会被站点规范化重定向并丢失 loader 参数。
            query["page"] = page
        url = f"{HONGGUO_BASE}/rank/{route}?{urlencode(query)}"
        payload = _fetch_hongguo_payload(session, url, route_id)
        if payload.get("isSuccess") is not True:
            raise IncompleteDramaRankingError(f"{rank_key} 第 {page} 页标记为失败")
        pagination = payload.get("pagination") if isinstance(payload.get("pagination"), Mapping) else {}
        current_page = _int_or_none(pagination.get("pageNum"))
        page_total = _int_or_none(pagination.get("totalPages"))
        if current_page != page or page_total is None or page_total < 1:
            raise IncompleteDramaRankingError(f"{rank_key} 第 {page} 页分页元数据异常")
        if total_pages is None:
            total_pages = page_total
            if total_pages > max_pages:
                raise IncompleteDramaRankingError(
                    f"{rank_key} 配置 {max_pages} 页不足，平台当前共有 {total_pages} 页"
                )
        elif page_total != total_pages:
            raise IncompleteDramaRankingError(f"{rank_key} 翻页期间总页数变化")
        rows = payload.get("rankList") or []
        if not isinstance(rows, list) or not rows:
            raise IncompleteDramaRankingError(f"{rank_key} 第 {page} 页为空")
        for raw in rows:
            if not isinstance(raw, Mapping):
                raise IncompleteDramaRankingError(f"{rank_key} 返回非对象条目")
            series_id = _text(raw.get("seriesId") or raw.get("id"))
            if not series_id or series_id in seen:
                raise IncompleteDramaRankingError(f"{rank_key} 出现空或重复作品 ID")
            seen.add(series_id)
            items.append(_hongguo_item(raw, rank_key, config["contentForm"]))
        if page >= total_pages:
            _assert_contiguous(items, rank_key)
            return items
    raise IncompleteDramaRankingError(f"{rank_key} 未到达平台末页")


def _kuaishou_label_data(labels: Any) -> tuple[Optional[int], Optional[int], list[str]]:
    play_count = None
    days_on_chart = None
    texts: list[str] = []
    for label in labels if isinstance(labels, list) else []:
        if not isinstance(label, Mapping):
            continue
        text = _text(label.get("desc"))
        if not text:
            continue
        texts.append(text)
        if "播放" in text:
            play_count = parse_chinese_count(text)
        match = re.search(r"持续在榜\s*(\d+)\s*天", text)
        if match:
            days_on_chart = int(match.group(1))
    return play_count, days_on_chart, texts


def _kuaishou_item(raw: Mapping[str, Any], rank_key: str, position: int) -> dict[str, Any]:
    course_id = _text(raw.get("courseId") or raw.get("jumpCourseId") or raw.get("tubeId"))
    title = _text(raw.get("courseName"))
    rank = _int_or_none(raw.get("rankNo"))
    if not course_id or not title or rank != position:
        raise IncompleteDramaRankingError(f"{rank_key} 第 {position} 条 ID、标题或排名异常")
    play_count, days_on_chart, compute_labels = _kuaishou_label_data(raw.get("computeLabelList"))
    episode_count = parse_chinese_count(raw.get("episodeDesc"))
    launch = raw.get("launchTag") if isinstance(raw.get("launchTag"), Mapping) else {}
    tags = [_text(tag) for tag in raw.get("tagNameList") or [] if _text(tag)]
    content_form = ""
    if rank_key == "kuaishou_real":
        content_form = "real_drama"
    elif rank_key == "kuaishou_comic":
        content_form = "comic_drama"
    item = {
        "site": "kuaishou",
        "bookId": course_id,
        "title": title,
        "category": tags[0] if tags else "",
        "synopsis_short": _text(raw.get("desc")),
        "rankType": rank_key,
        "rankPosition": rank,
        "rankScopeKey": "total",
        "rankScopeName": "总榜",
        "coverUrl": _secure_kuaishou_cover_url(raw.get("coverImg")),
        "detailUrl": _text(raw.get("seriesJumpUrl")),
        "contentKind": "short_drama",
        "contentForm": content_form,
        "heatValue": _int_or_none(raw.get("score")),
        "heatText": _text(raw.get("scoreStr")),
        "playCount": play_count,
        "episodeCount": episode_count,
        "daysOnChart": days_on_chart,
        "tags": tags,
        "platformLabel": _text(launch.get("text")),
        "computeLabels": compute_labels,
        "tubeId": _text(raw.get("tubeId")),
    }
    return {key: value for key, value in item.items() if value not in (None, "", [])}


def scrape_kuaishou_ranking(session, rank_key: str) -> list[dict[str, Any]]:
    config = KUAISHOU_RANKINGS[rank_key]
    query = urlencode({"classifyId": config["classifyId"], "sourceType": 0})
    payload = _get_json(session, KUAISHOU_DRAMA_BILLBOARD + "?" + query, KUAISHOU_HEADERS)
    if payload.get("result") != 1:
        raise IncompleteDramaRankingError(f"{rank_key} 接口返回失败: {payload.get('error_msg')}")
    data = payload.get("data") if isinstance(payload.get("data"), Mapping) else {}
    detail = data.get("tabHotListDetail") if isinstance(data.get("tabHotListDetail"), Mapping) else {}
    tabs = data.get("tabListInfo") if isinstance(data.get("tabListInfo"), list) else []
    selected_index = _int_or_none(data.get("selectTabIndex"))
    selected = tabs[selected_index] if selected_index is not None and 0 <= selected_index < len(tabs) else None
    if not isinstance(selected, Mapping) or _int_or_none(selected.get("id")) != int(config["classifyId"]):
        raise IncompleteDramaRankingError(f"{rank_key} 返回的选中榜单与请求不一致")
    rows = detail.get("content") or []
    if not isinstance(rows, list) or not rows:
        raise IncompleteDramaRankingError(f"{rank_key} 返回空榜")
    items = [
        _kuaishou_item(raw, rank_key, position)
        for position, raw in enumerate(rows, 1)
        if isinstance(raw, Mapping)
    ]
    if len(items) != len(rows):
        raise IncompleteDramaRankingError(f"{rank_key} 返回非对象条目")
    _assert_contiguous(items, rank_key)
    return items


def scrape_all_short_drama_rankings(session, site: str, rank_keys=None,
                                     max_pages: int = SHORT_DRAMA_MAX_PAGES_PER_RANK):
    """采集一个短剧平台的全部指定榜单。"""
    if site == "hongguo":
        configs = HONGGUO_RANKINGS
        scrape = lambda key: scrape_hongguo_ranking(session, key, max_pages=max_pages)
    elif site == "douyin":
        configs = DOUYIN_RANKINGS
        scrape = lambda key: scrape_douyin_ranking(session, key, max_pages=max_pages)
    elif site == "kuaishou":
        configs = KUAISHOU_RANKINGS
        scrape = lambda key: scrape_kuaishou_ranking(session, key)
    else:
        raise ValueError(f"不支持的短剧平台: {site}")
    keys = rank_keys or list(configs)
    result = {}
    for key in keys:
        if key not in configs:
            raise ValueError(f"{site} 不支持榜单 {key}")
        logger.info("[%s] 开始采集 %s", site, key)
        result[key] = scrape(key)
        logger.info("[%s] %s 完整采集 %s 条", site, key, len(result[key]))
    return result
