"""榜单结果导出和内部导入接口客户端。

本模块只负责把扫描器生成的统一书籍数据转换成跨平台的批量导入
协议，并通过一个可选的 HTTP endpoint 推送。抓榜本身仍由现有的
``scrape`` 命令完成，因此榜单请求失败不会被这个客户端吞掉。

导入协议故意使用 ``book_id`` / ``rank_type`` 等稳定的 snake_case 字段，
同时保留 ``extra`` 扩展字段，便于将来接入新的平台而无需修改协议。
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Tuple, Union

import requests

from config import get_rank_name, get_site_name, get_site_rankings


logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0
DEFAULT_RETRIES = 3
RETRY_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _int_or_none(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _iso_utc(value: Any = None) -> str:
    """返回可排序的 UTC ISO 时间，兼容旧输出中的本地时间字符串。"""
    if value:
        text = _text(value)
        if text:
            return text
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _rank_name(site: str, rank_key: str) -> str:
    try:
        configured = get_site_rankings(site).get(rank_key, {})
    except (AttributeError, TypeError):
        configured = {}
    return _text(configured.get("name")) or get_rank_name(rank_key)


def _book_value(book: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        value = book.get(name)
        if value not in (None, "", []):
            return value
    return None


def _normalise_book(book: Mapping[str, Any], *, site: str, rank_type: Optional[str],
                    rank_position: Any = None) -> Optional[dict[str, Any]]:
    """将一个平台书籍记录转换为导入协议中的一行。"""
    book_id = _text(_book_value(book, "bookId", "book_id", "id"))
    title = _text(_book_value(book, "title", "bookName", "book_name"))
    if not book_id or not title:
        return None

    rank_type = _text(rank_type or _book_value(book, "rankType", "rank_type"))
    position = _int_or_none(
        rank_position if rank_position not in (None, "")
        else _book_value(book, "rankPosition", "rank_position")
    )
    item: dict[str, Any] = {
        "book_id": book_id,
        "title": title,
        "author": _text(_book_value(book, "author", "authorName", "author_name")),
        "category": _text(_book_value(book, "category", "cat", "catName", "subCategory")),
        "subcategory": _text(_book_value(book, "rankScopeName", "rank_scope_name", "category", "cat", "catName", "subCategory")),
        "word_count": _int_or_none(_book_value(book, "wordCount", "word_count")),
        "synopsis_short": _text(_book_value(book, "synopsis_short", "synopsis", "description", "abstract")),
        "rank_type": rank_type,
        "rank_position": position,
        "rank_scope_key": _text(_book_value(book, "rankScopeKey", "rank_scope_key", "scopeKey", "scope_key", "fanqieCategoryId")),
        "rank_scope_name": _text(_book_value(book, "rankScopeName", "rank_scope_name", "scopeName", "scope_name")),
        "detail_url": _text(_book_value(book, "detailUrl", "detail_url", "url")),
        "status": _text(_book_value(book, "status", "state")),
        "read_count": _int_or_none(_book_value(book, "readCount", "read_count")),
        "cover_url": _text(_book_value(book, "coverUrl", "cover_url", "thumbUri")),
        "latest_chapter": _text(_book_value(book, "latestChapter", "latest_chapter", "lastChapterTitle")),
    }

    # site 是源级字段，但书行也带上它，方便服务端批量校验和以后重放。
    item["site"] = site

    # 任何平台特有字段都保留下来，避免接入新平台时丢失信息。
    known = {
        "bookId", "book_id", "id", "title", "bookName", "book_name", "author",
        "authorName", "author_name", "category", "cat", "catName", "subCategory",
        "wordCount", "word_count", "synopsis_short", "synopsis", "description", "abstract",
        "rankType", "rank_type", "rankPosition", "rank_position", "detailUrl", "detail_url",
        "url", "status", "state", "readCount", "read_count", "coverUrl", "cover_url",
        "thumbUri", "latestChapter", "latest_chapter", "lastChapterTitle", "site",
        "rankAppearances", "ranks", "rankScopeKey", "rank_scope_key", "scopeKey", "scope_key",
        "rankScopeName", "rank_scope_name", "scopeName", "scope_name", "fanqieCategoryId",
    }
    extra = {str(key): value for key, value in book.items() if key not in known and value not in (None, "", [])}
    if extra:
        item["extra"] = extra
    return item


def _iter_ranked_books(payload: Mapping[str, Any]) -> Iterable[Tuple[str, Mapping[str, Any], Optional[str], Any]]:
    """遍历 payload，优先从 rankings 展开榜单关系。"""
    rankings = payload.get("rankings")
    if isinstance(rankings, Mapping):
        for rank_type, books in rankings.items():
            if not isinstance(books, list):
                continue
            for book in books:
                if not isinstance(book, Mapping):
                    continue
                yield str(rank_type), book, str(rank_type), _book_value(
                    book, "rankPosition", "rank_position", "currentPos", "rankNum"
                )
        return

    books = payload.get("books", payload if isinstance(payload, list) else [])
    if not isinstance(books, list):
        return
    for book in books:
        if not isinstance(book, Mapping):
            continue
        appearances = book.get("rankAppearances")
        if isinstance(appearances, list) and appearances:
            for appearance in appearances:
                if isinstance(appearance, Mapping):
                    yield _text(appearance.get("rankType")), book, appearance.get("rankType"), appearance.get("rankPosition")
        else:
            yield _text(book.get("rankType")), book, book.get("rankType"), book.get("rankPosition")


def build_ingestion_payload(data: Any, *, site: Optional[str] = None) -> dict[str, Any]:
    """构造发送给后端的版本化批量导入 payload。

    同一本书出现在多个榜单时输出多行，关系不会因本地去重而丢失；同一
    榜单中的重复记录则按 ``(site, book_id, rank_type, rank_scope_key)`` 幂等去重。
    """
    if isinstance(data, list):
        source_data: Mapping[str, Any] = {"books": data}
    elif isinstance(data, Mapping):
        source_data = data
    else:
        raise ValueError("输入必须是 JSON 对象或书籍数组")

    resolved_site = _text(site or source_data.get("site")) or "unknown"
    source = {
        "site": resolved_site,
        "site_name": _text(source_data.get("siteName") or source_data.get("site_name")) or get_site_name(resolved_site),
        "snapshot_at": _iso_utc(source_data.get("timestamp") or source_data.get("snapshot_at")),
        "rank_key": _text(source_data.get("rankKey") or source_data.get("rank_key")) or None,
        "rank_name": _text(source_data.get("rankName") or source_data.get("rank_name")) or None,
        "complete": bool(source_data.get("complete", True)),
    }
    # 单榜快照有 rankKey，合并快照则由每一行携带 rank_type。
    if source["rank_key"]:
        source["rank_name"] = source["rank_name"] or _rank_name(resolved_site, source["rank_key"])

    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for rank_type, book, explicit_rank, position in _iter_ranked_books(source_data):
        explicit_rank = explicit_rank or _text(source_data.get("rankKey") or source_data.get("rank_key")) or None
        row = _normalise_book(book, site=resolved_site, rank_type=explicit_rank or rank_type, rank_position=position)
        if not row:
            logger.warning("跳过缺少 book_id/title 的书籍记录")
            continue
        key = (resolved_site, row["book_id"], row.get("rank_type", ""), row.get("rank_scope_key", ""))
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)

    # 每行有 rank_type 时，为服务端补齐该榜单的可读名称；保留 source 的
    # rank_name 用于单榜调用，避免服务端再依赖扫描器配置。
    for row in rows:
        rank_type = row.get("rank_type") or ""
        row["rank_name"] = _rank_name(resolved_site, rank_type) if rank_type else ""

    if not source.get("rank_key"):
        rank_keys = sorted({row["rank_type"] for row in rows if row.get("rank_type")})
        source["rank_keys"] = rank_keys
        source["rank_names"] = {key: _rank_name(resolved_site, key) for key in rank_keys}

    return {
        "schema_version": 1,
        "source": source,
        "books": rows,
        "count": len(rows),
    }


def load_json_file(path: Union[str, os.PathLike]) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_ingestion_result(result: Any, payload: Mapping[str, Any]) -> None:
    """确认独立写入服务接收了完整批次；HTTP200不等于已导入，不接受HTML或静默跳过。"""
    expected = payload.get("count")
    if type(expected) is not int or expected <= 0:
        raise ValueError("不能发布没有有效书籍的榜单快照")
    if not isinstance(result, dict) or type(result.get("accepted")) is not int:
        raise ValueError("导入服务未返回有效的 accepted 数量，不能确认成功")
    if result["accepted"] != expected:
        raise ValueError(f"导入未完整确认：预期 {expected} 条，实际 {result['accepted']} 条；可能为过期快照，请检查后重放")
    ids = result.get("snapshot_ids")
    if (not isinstance(ids, list) or not ids or len(ids) > expected
            or any(type(value) is not int or value <= 0 for value in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError("导入服务未返回有效的快照 ID，不能确认成功")


def write_json_file(payload: Mapping[str, Any], path: Union[str, os.PathLike]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temporary.replace(target)


def post_ingestion(payload: Mapping[str, Any], url: str, *, token: str = "",
                   timeout: float = DEFAULT_TIMEOUT, retries: int = DEFAULT_RETRIES,
                   session: Optional[requests.Session] = None) -> requests.Response:
    """POST 导入请求，网络抖动和 5xx/429 自动指数退避重试。"""
    if not _text(url):
        raise ValueError("未设置榜单导入 URL")
    if retries < 0:
        raise ValueError("retries 不能小于 0")

    http = session or requests.Session()
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-Internal-Token"] = token
        headers["X-Rank-Ingestion-Token"] = token

    last_error: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            response = http.post(url, json=payload, headers=headers, timeout=timeout)
            if response.status_code not in RETRY_STATUS_CODES:
                response.raise_for_status()
                try:
                    envelope = response.json()
                    if isinstance(envelope, dict) and envelope.get("code") not in (None, 200):
                        raise requests.HTTPError(
                            f"导入接口返回业务错误: {envelope.get('code')} {envelope.get('message') or envelope.get('status') or ''}",
                            response=response,
                        )
                except ValueError:
                    pass
                return response
            last_error = requests.HTTPError(
                f"导入接口暂时不可用: HTTP {response.status_code}", response=response
            )
            if attempt >= retries:
                break
            retry_after = response.headers.get("Retry-After", "")
            try:
                delay = min(float(retry_after), 60.0) if retry_after else 2 ** attempt
            except ValueError:
                delay = 2 ** attempt
        except (requests.RequestException, OSError) as exc:
            if isinstance(exc, requests.HTTPError) and exc.response is not None and exc.response.status_code not in RETRY_STATUS_CODES:
                raise
            last_error = exc
            if attempt >= retries:
                break
            delay = 2 ** attempt

        logger.warning("榜单导入请求失败，第 %s/%s 次重试，%.1f 秒后继续", attempt + 1, retries, delay)
        time.sleep(delay)

    assert last_error is not None
    raise last_error


def push_payload(payload: Mapping[str, Any], *, url: Optional[str] = None,
                 token: Optional[str] = None, timeout: float = DEFAULT_TIMEOUT,
                 retries: int = DEFAULT_RETRIES, session: Optional[requests.Session] = None) -> Any:
    """推送并解析 JSON 响应；响应不是 JSON 时返回原始文本。"""
    endpoint = _text(url or os.getenv("RANK_INGEST_URL"))
    secret = _text(token if token is not None else os.getenv("RANK_INGEST_TOKEN"))
    response = post_ingestion(payload, endpoint, token=secret, timeout=timeout, retries=retries, session=session)
    if not response.content:
        return {"status_code": response.status_code}
    try:
        return response.json()
    except ValueError:
        return {"status_code": response.status_code, "text": response.text}
