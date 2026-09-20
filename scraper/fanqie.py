"""
番茄小说排行榜抓取。

番茄榜单页会在 HTML 中注入 window.__INITIAL_STATE__，榜单数据就放在
rank.book_list 中。这里把它转换成项目统一的书籍结构，后续分析和报告
可以复用现有流水线。
"""

import json
import logging
import os
import re
import subprocess
from datetime import datetime
from urllib.parse import urlencode, urlparse

from config import FANQIE_BASE, FANQIE_RANKINGS, FANQIE_USER_AGENT, FANQIE_MAX_PAGES_PER_RANK


logger = logging.getLogger(__name__)

# 官网页面首屏仅10本，但公开分页接口已验证支持50本/次，完整100名只需两页。
FANQIE_PAGE_SIZE = 50


class IncompleteRankingError(RuntimeError):
    """缺页、版本漂移或重复页必须中止发布，不能当作完整日榜。"""


FANQIE_HEADERS = {
    "User-Agent": FANQIE_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Referer": FANQIE_BASE,
}


FANQIE_FONT_MAP = {
    58670: "0", 58413: "1", 58678: "2", 58371: "3", 58353: "4",
    58480: "5", 58359: "6", 58449: "7", 58540: "8", 58692: "9",
    58712: "a", 58542: "b", 58575: "c", 58626: "d", 58691: "e",
    58561: "f", 58362: "g", 58619: "h", 58430: "i", 58531: "j",
    58588: "k", 58440: "l", 58681: "m", 58631: "n", 58376: "o",
    58429: "p", 58555: "q", 58498: "r", 58518: "s", 58453: "t",
    58397: "u", 58356: "v", 58435: "w", 58514: "x", 58482: "y",
    58529: "z", 58515: "A", 58688: "B", 58709: "C", 58344: "D",
    58656: "E", 58381: "F", 58576: "G", 58516: "H", 58463: "I",
    58649: "J", 58571: "K", 58558: "L", 58433: "M", 58517: "N",
    58387: "O", 58687: "P", 58537: "Q", 58541: "R", 58458: "S",
    58390: "T", 58466: "U", 58386: "V", 58697: "W", 58519: "X",
    58511: "Y", 58634: "Z", 58611: "的", 58590: "一", 58398: "是",
    58422: "了", 58657: "我", 58666: "不", 58562: "人", 58345: "在",
    58510: "他", 58496: "有", 58654: "这", 58441: "个", 58493: "上",
    58714: "们", 58618: "来", 58528: "到", 58620: "时", 58403: "大",
    58461: "地", 58481: "为", 58700: "子", 58708: "中", 58503: "你",
    58442: "说", 58639: "生", 58506: "国", 58663: "年", 58436: "着",
    58563: "就", 58391: "那", 58357: "和", 58354: "要", 58695: "她",
    58372: "出", 58696: "也", 58551: "得", 58445: "里", 58408: "后",
    58599: "自", 58424: "以", 58394: "会", 58348: "家", 58426: "可",
    58673: "下", 58417: "而", 58556: "过", 58603: "天", 58565: "去",
    58604: "能", 58522: "对", 58632: "小", 58622: "多", 58350: "然",
    58605: "于", 58617: "心", 58401: "学", 58637: "么", 58684: "之",
    58382: "都", 58464: "好", 58487: "看", 58693: "起", 58608: "发",
    58392: "当", 58474: "没", 58601: "成", 58355: "只", 58573: "如",
    58499: "事", 58469: "把", 58361: "还", 58698: "用", 58489: "第",
    58711: "样", 58457: "道", 58635: "想", 58492: "作", 58647: "种",
    58623: "开", 58521: "美", 58609: "总", 58530: "从", 58665: "无",
    58652: "情", 58676: "己", 58456: "面", 58581: "最", 58509: "女",
    58488: "但", 58363: "现", 58685: "前", 58396: "些", 58523: "所",
    58471: "同", 58485: "日", 58613: "手", 58533: "又", 58589: "行",
    58527: "意", 58593: "动", 58699: "方", 58707: "期", 58414: "它",
    58596: "头", 58570: "经", 58660: "长", 58364: "儿", 58526: "回",
    58501: "位", 58638: "分", 58404: "爱", 58677: "老", 58535: "因",
    58629: "很", 58577: "给", 58606: "名", 58497: "法", 58662: "间",
    58479: "斯", 58532: "知", 58380: "世", 58385: "什", 58405: "两",
    58644: "次", 58578: "使", 58505: "身", 58564: "者", 58412: "被",
    58686: "高", 58624: "已", 58667: "亲", 58607: "其", 58616: "进",
    58368: "此", 58427: "话", 58423: "常", 58633: "与", 58525: "活",
    58543: "正", 58418: "感", 58597: "见", 58683: "明", 58507: "问",
    58621: "力", 58703: "理", 58438: "尔", 58536: "点", 58384: "文",
    58484: "几", 58539: "定", 58554: "本", 58421: "公", 58347: "特",
    58569: "做", 58710: "外", 58574: "孩", 58375: "相", 58645: "西",
    58592: "果", 58572: "走", 58388: "将", 58370: "月", 58399: "十",
    58651: "实", 58546: "向", 58504: "声", 58419: "车", 58407: "全",
    58672: "信", 58675: "重", 58538: "三", 58465: "机", 58374: "工",
    58579: "物", 58402: "气", 58702: "每", 58553: "并", 58360: "别",
    58389: "真", 58560: "打", 58690: "太", 58473: "新", 58512: "比",
    58653: "才", 58704: "便", 58545: "夫", 58641: "再", 58475: "书",
    58583: "部", 58472: "水", 58478: "像", 58664: "眼", 58586: "等",
    58568: "体", 58674: "却", 58490: "加", 58476: "电", 58346: "主",
    58630: "界", 58595: "门", 58502: "利", 58713: "海", 58587: "受",
    58548: "听", 58351: "表", 58547: "德", 58443: "少", 58460: "克",
    58636: "代", 58585: "员", 58625: "许", 58694: "稜", 58428: "先",
    58640: "口", 58628: "由", 58612: "死", 58446: "安", 58468: "写",
    58410: "性", 58508: "马", 58594: "光", 58483: "白", 58544: "或",
    58495: "住", 58450: "难", 58643: "望", 58486: "教", 58406: "命",
    58447: "花", 58669: "结", 58415: "乐", 58444: "色", 58549: "更",
    58494: "拉", 58409: "东", 58658: "神", 58557: "记", 58602: "处",
    58559: "让", 58610: "母", 58513: "父", 58500: "应", 58378: "直",
    58680: "字", 58352: "场", 58383: "平", 58454: "报", 58671: "友",
    58668: "关", 58452: "放", 58627: "至", 58400: "张", 58455: "认",
    58416: "接", 58552: "告", 58614: "入", 58582: "笑", 58534: "内",
    58701: "英", 58349: "军", 58491: "候", 58467: "民", 58365: "岁",
    58598: "往", 58425: "何", 58462: "度", 58420: "山", 58661: "觉",
    58615: "路", 58648: "带", 58470: "万", 58377: "男", 58520: "边",
    58646: "风", 58600: "解", 58431: "叫", 58715: "任", 58524: "金",
    58439: "快", 58566: "原", 58477: "吃", 58642: "妈", 58437: "变",
    58411: "通", 58451: "师", 58395: "立", 58369: "象", 58706: "数",
    58705: "四", 58379: "失", 58567: "满", 58373: "战", 58448: "远",
    58659: "格", 58434: "士", 58679: "音", 58432: "轻", 58689: "目",
    58591: "条", 58682: "呢",
}


def parse_fanqie_ranking_page(html, rank_key):
    """解析番茄榜单页 HTML，返回统一书籍列表。"""
    state = extract_initial_state(html)
    rank_state = state.get("rank") if isinstance(state, dict) else {}
    if not isinstance(rank_state, dict):
        return []

    records = _rank_records(rank_state)
    if not records:
        return []

    category_by_id = _category_map(rank_state)
    books = []
    for record in records:
        book = _record_to_book(record, rank_key, len(books) + 1, category_by_id)
        if book:
            books.append(book)

    return books


def extract_initial_state(html):
    """提取 window.__INITIAL_STATE__ 后面的 JSON 对象。"""
    if not html:
        return {}

    match = re.search(r"window\.__INITIAL_STATE__\s*=", html)
    if not match:
        return {}

    decoder = json.JSONDecoder()
    payload = html[match.end():].lstrip()
    try:
        state, _ = decoder.raw_decode(payload)
    except json.JSONDecodeError as exc:
        # 番茄偶尔把可选字段序列化成 JavaScript 的 undefined，导致严格 JSON
        # 解码在榜单中途失败；仅替换值位置的 undefined，不执行任意 JS。
        sanitized = re.sub(r":\s*undefined\b", ": null", payload)
        try:
            state, _ = decoder.raw_decode(sanitized)
        except json.JSONDecodeError:
            logger.warning(f"番茄页面状态 JSON 解析失败: {exc}")
            return {}

    return state if isinstance(state, dict) else {}


def _rank_records(rank_state):
    for key in ("book_list", "readRankList", "newRankList"):
        records = rank_state.get(key)
        if isinstance(records, list):
            return records
    return []


def _category_map(rank_state):
    result = {}
    category_types = rank_state.get("rankCategoryTypeList") or {}
    if not isinstance(category_types, dict):
        return result

    for items in category_types.values():
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            category_id = str(item.get("id") or "").strip()
            name = str(item.get("name") or "").strip()
            if category_id and name:
                result[category_id] = name
    return result


def _record_to_book(record, rank_key, position, category_by_id):
    if not isinstance(record, dict):
        return None

    book_id = _text(record.get("bookId"))
    raw_title = _text(record.get("bookName"))
    if not book_id or not raw_title:
        return None

    raw_author = _text(record.get("author"))
    raw_synopsis = _text(record.get("abstract"))
    raw_latest_chapter = _text(record.get("lastChapterTitle"))
    title = decode_fanqie_font_text(raw_title) or raw_title
    author = decode_fanqie_font_text(raw_author)
    synopsis = decode_fanqie_font_text(raw_synopsis)
    latest_chapter = decode_fanqie_font_text(raw_latest_chapter)

    category = (
        _text(record.get("categoryV2")) or
        _text(record.get("category")) or
        category_by_id.get(_text(record.get("curent_category_id"))) or
        category_by_id.get(_text(record.get("pos_category_id"))) or
        ""
    )
    rank_position = _to_int(record.get("currentPos")) or position
    read_count = _to_int(record.get("read_count")) or _to_int(record.get("readCount"))
    word_count = _to_int(record.get("wordNumber"))
    last_update = _timestamp_to_date(record.get("lastChapterUpdateTime"))
    font_encrypted = _contains_private_use_chars(raw_title, raw_author, raw_synopsis, raw_latest_chapter)

    book = {
        "site": "fanqie",
        "bookId": book_id,
        "title": title,
        "author": author,
        "category": category,
        "wordCount": word_count,
        "synopsis_short": synopsis,
        "rankType": rank_key,
        "rankPosition": rank_position,
        "detailUrl": f"{FANQIE_BASE}/page/{book_id}",
        "readCount": read_count,
        "status": _status_label(record.get("creationStatus")),
        "coverUrl": _text(record.get("thumbUri")),
        "latestChapter": latest_chapter,
        "lastUpdateDate": last_update,
        "scrapedAt": datetime.now().isoformat(),
    }

    optional_fields = {
        "rankPosDiff": _to_int(record.get("rankPosDiff")),
        "firstChapterItemId": _text(record.get("firstChapterItemId")),
        "lastChapterItemId": _text(record.get("lastChapterItemId")),
        "authorId": _text(record.get("uid")),
        "fanqieCategoryId": _text(record.get("curent_category_id")) or _text(record.get("pos_category_id")),
    }
    for key, value in optional_fields.items():
        if value not in (None, ""):
            book[key] = value

    # 榜单分类 ID 是榜单维度，不等同于书籍展示分类；服务端据此区分同一榜型下的不同分类榜。
    if book.get("fanqieCategoryId"):
        book["rankScopeKey"] = book["fanqieCategoryId"]
        if category:
            book["rankScopeName"] = category

    if font_encrypted:
        book["fontEncrypted"] = True
        if (title, author, synopsis, latest_chapter) != (
            raw_title,
            raw_author,
            raw_synopsis,
            raw_latest_chapter,
        ):
            book["fontDecoded"] = True

    return {key: value for key, value in book.items() if value not in (None, "", [])}


def _text(value):
    if value in (None, ""):
        return ""
    return str(value).strip()


def _to_int(value):
    if value in (None, ""):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    digits = re.sub(r"[^\d-]", "", str(value))
    if not digits or digits == "-":
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def _timestamp_to_date(value):
    timestamp = _to_int(value)
    if not timestamp:
        return ""
    try:
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
    except (OSError, OverflowError, ValueError):
        return ""


def _status_label(value):
    value = _text(value)
    if value == "0":
        return "完结"
    if value == "1":
        return "连载"
    return value


def _contains_private_use_chars(*values):
    text = "".join(_text(value) for value in values)
    return any("\ue000" <= char <= "\uf8ff" for char in text)


def decode_fanqie_font_text(value):
    """将番茄常见私有区字体映射字符还原为普通字符。"""
    text = _text(value)
    if not text:
        return ""

    chars = []
    for char in text:
        code = ord(char)
        if code in FANQIE_FONT_MAP:
            chars.append(FANQIE_FONT_MAP[code])
        elif "\ue000" <= char <= "\uf8ff":
            continue
        else:
            chars.append(char)

    return "".join(chars)


def _build_fanqie_url(rank_key, page=1, scope_key=None):
    config = FANQIE_RANKINGS[rank_key]
    url = config["url"]
    if scope_key:
        url = f"{url.rstrip('/')}_{scope_key}"
    if page != 1:
        raise ValueError("番茄榜单 HTML 不支持 page 参数，翻页必须使用 offset API")
    return url


def _fetch_fanqie_html(session, rank_key, scope_key=None):
    """获取分类导航/首屏状态；HTML 只预置前10本，不用于后续页。"""
    page = 1
    url = _build_fanqie_url(rank_key, page, scope_key)
    logger.info(f"[{rank_key}{':' + str(scope_key) if scope_key else ''}] 番茄榜单请求: page={page}")
    resp = session.safe_get(url, delay_range=(1, 2), extra_headers=FANQIE_HEADERS)
    html = resp.text if resp else ""

    books = parse_fanqie_ranking_page(html, rank_key) if html else []
    if not books:
        logger.info(f"[{rank_key}] requests 未取到可解析数据，尝试 curl 兜底")
        curl_html = _curl_get_text(
            url,
            cookie=session.session.headers.get("Cookie"),
            proxy=session.proxy,
        )
        if curl_html:
            books = parse_fanqie_ranking_page(curl_html, rank_key)
            html = curl_html

    if not books and html:
        _save_debug_html(html, f"fanqie_{rank_key}")
    return html


def fetch_fanqie_rank_page(session, rank_key, scope_key, offset=0, rank_version="", scope_name=""):
    """请求官网使用的公开分页接口；固定版本，保留真实名次，不生成签名或绕过验证。"""
    if scope_key is None or not str(scope_key).isdigit():
        raise IncompleteRankingError("缺少有效分类 ID，不能请求番茄榜单分页")
    if type(offset) is not int or offset < 0:
        raise ValueError("offset 必须是非负整数")
    definition = FANQIE_RANKINGS[rank_key]
    params = {
        "app_id": 2503, "rank_list_type": 3, "offset": offset, "limit": FANQIE_PAGE_SIZE,
        "category_id": str(scope_key), "rank_version": str(rank_version),
        "gender": 1 if definition["gender"] == "male" else 0,
        "rankMold": 2 if definition["rankType"] == "read" else 1,
    }
    url = f"{FANQIE_BASE}/api/rank/category/list?{urlencode(params)}"
    headers = {**FANQIE_HEADERS, "Accept": "application/json", "Referer": _build_fanqie_url(rank_key, scope_key=scope_key)}
    response = session.safe_get(url, delay_range=(1, 2), extra_headers=headers)
    if response is None:
        raise IncompleteRankingError(f"{rank_key}/{scope_key} offset={offset} 请求失败")
    try:
        payload = response.json()
    except ValueError as error:
        raise IncompleteRankingError(f"{rank_key}/{scope_key} 未返回 JSON，可能需要人工验证") from error
    if not isinstance(payload, dict) or payload.get("code") != 0 or not isinstance(payload.get("data"), dict):
        raise IncompleteRankingError(f"{rank_key}/{scope_key} 上游返回错误，停止导入")
    data = payload["data"]
    records = data.get("book_list")
    total = data.get("total_num")
    # 官网不足100名的分类有时返回字符串总数（如 "38"），完整100名则返回整数。
    if isinstance(total, str) and total.isdecimal():
        total = int(total)
    version = _text(data.get("rankVersion"))
    if type(total) is int and total == 0 and records is None:
        records = []
    if type(total) is int and total == 0 and not records and not version:
        version = str(rank_version or "empty")
    if not isinstance(records, list) or type(total) is not int or total < 0 or not version:
        raise IncompleteRankingError(f"{rank_key}/{scope_key} 缺少榜单总数、版本或书籍数组")
    if rank_version and version != str(rank_version):
        raise IncompleteRankingError(f"{rank_key}/{scope_key} 翻页期间榜单版本变化，拒绝混合快照")
    if len(records) > FANQIE_PAGE_SIZE:
        raise IncompleteRankingError(f"{rank_key}/{scope_key} 返回数量超过请求页大小")
    books = []
    for index, record in enumerate(records, offset + 1):
        book = _record_to_book(record, rank_key, index, {str(scope_key): scope_name})
        if book is None:
            raise IncompleteRankingError(f"{rank_key}/{scope_key} 书籍字段不完整")
        if book['rankPosition'] != index:
            raise IncompleteRankingError(f"{rank_key}/{scope_key} 名次不连续，预期{index}，实际{book['rankPosition']}")
        book["rankScopeKey"] = str(scope_key)
        book["rankScopeName"] = scope_name or book.get("category") or str(scope_key)
        book["sourceRankVersion"] = version
        books.append(book)
    return books, total, version


def fetch_fanqie_ranking(session, rank_key, page=1, scope_key=None):
    """兼容单页调用；后续页使用真实分页接口而不是无效的 ?page=。"""
    if scope_key:
        return fetch_fanqie_rank_page(session, rank_key, scope_key, (page-1)*FANQIE_PAGE_SIZE)[0]
    if page != 1:
        raise IncompleteRankingError("翻页必须指定分类 ID")
    return parse_fanqie_ranking_page(_fetch_fanqie_html(session, rank_key), rank_key)


def _curl_get_text(url, cookie=None, proxy=None):
    cmd = [
        "curl",
        "-L",
        "-sS",
        "--compressed",
        "--max-time",
        "30",
        "-A",
        FANQIE_USER_AGENT,
        "-H",
        f"Referer: {FANQIE_BASE}",
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


def _save_debug_html(html, rank_key):
    debug_dir = os.path.join("output", "debug")
    os.makedirs(debug_dir, exist_ok=True)
    path = os.path.join(debug_dir, f"{rank_key}_debug_{datetime.now().strftime('%H%M%S')}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info(f"调试HTML已保存: {path}")


def discover_fanqie_scope_definitions(session, rank_key):
    """从榜单首页发现平台提供的稳定分类 ID。"""
    url = _build_fanqie_url(rank_key)
    html = _fetch_fanqie_html(session, rank_key)
    if not html:
        raise IncompleteRankingError(f"{rank_key} 无法获取分类导航")
    category_names = _category_map(extract_initial_state(html).get("rank", {}))
    base = urlparse(FANQIE_RANKINGS[rank_key]["url"]).path.rstrip("/")
    escaped = re.escape(base)
    scopes = []
    for match in re.finditer(rf'href=["\'](?:https?://[^"\']+)?{escaped}_(\d+)["\']', html):
        scope = match.group(1)
        if scope not in scopes:
            scopes.append(scope)
    if not scopes:
        raise IncompleteRankingError(f"{rank_key} 未发现分类导航，拒绝把首屏当完整榜单")
    return [(scope, category_names.get(scope, "")) for scope in scopes]


def discover_fanqie_scopes(session, rank_key):
    return [scope for scope, _name in discover_fanqie_scope_definitions(session, rank_key)]


def scrape_fanqie_ranking(session, rank_key, max_pages=FANQIE_MAX_PAGES_PER_RANK, scope_keys=None):
    """抓完指定榜型全部分类；任何分类缺页均中止，避免覆盖为不完整日榜。"""
    if type(max_pages) is not int or not 1 <= max_pages <= 100:
        raise ValueError("max_pages 必须是1～100的整数")
    config = FANQIE_RANKINGS[rank_key]
    rank_name = config["name"]
    books = []
    scopes = [(str(scope), "") for scope in scope_keys] if scope_keys is not None else discover_fanqie_scope_definitions(session, rank_key)
    if not scopes:
        raise IncompleteRankingError(f"{rank_key} 没有可抓取的分类")

    logger.info(f"{'=' * 50}")
    logger.info(f"开始爬取: 番茄小说 {rank_name} ({rank_key})")
    logger.info(f"最大页数: {max_pages}")

    for scope_key, scope_name in scopes:
        seen = set()
        scope_books = []
        total = None
        version = ""
        for page in range(1, max_pages + 1):
            page_books, page_total, page_version = fetch_fanqie_rank_page(
                session, rank_key, scope_key, len(scope_books), version, scope_name,
            )
            if total is not None and page_total != total:
                raise IncompleteRankingError(f"{rank_key}/{scope_key} 翻页期间总数改变")
            total, version = page_total, page_version
            if total == 0:
                # 现有导入协议依赖书行标识scope，无法表达“同日把某分类清空”。
                # 在支持显式空scope发布前，必须中止，不能丢掉该分类后仍声称整榜完整。
                raise IncompleteRankingError(f"{rank_key}/{scope_key} 返回空分类，当前协议不能安全发布空分类快照")
            if total > max_pages*FANQIE_PAGE_SIZE:
                raise IncompleteRankingError(f"{rank_key}/{scope_key} 共{total}本，配置{max_pages}页不足；请增加 --pages")
            expected = min(FANQIE_PAGE_SIZE, total-len(scope_books))
            if len(page_books) != expected:
                raise IncompleteRankingError(f"{rank_key}/{scope_key} 第{page}页缺失，预期{expected}本，实际{len(page_books)}本")
            for book in page_books:
                book_id = book.get("bookId")
                if not book_id or book_id in seen:
                    raise IncompleteRankingError(f"{rank_key}/{scope_key} 第{page}页出现重复书籍，拒绝发布")
                seen.add(book_id)
                scope_books.append(book)
            logger.info("[%s/%s] 已获取 %s/%s 本", rank_key, scope_key, len(scope_books), total)
            if len(scope_books) == total:
                break
        if len(scope_books) != total:
            raise IncompleteRankingError(f"{rank_key}/{scope_key} 未获取完整榜单")
        books.extend(scope_books)

    logger.info(f"[番茄 {rank_name}] 共获取 {len(books)} 本（去重后）")
    return books


def scrape_all_fanqie_rankings(session, rank_keys=None, max_pages=FANQIE_MAX_PAGES_PER_RANK):
    """爬取所有（或指定）番茄排行榜。"""
    keys = rank_keys or list(FANQIE_RANKINGS.keys())
    all_data = {}

    for key in keys:
        if key not in FANQIE_RANKINGS:
            logger.warning(f"未知番茄榜单: {key}，跳过")
            continue

        all_data[key] = scrape_fanqie_ranking(session, key, max_pages=max_pages)

    return all_data
