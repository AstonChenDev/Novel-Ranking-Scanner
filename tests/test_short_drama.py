"""短剧榜单字段映射、分页和完整性保护测试，不访问真实网络。"""

import html
import json
import unittest
from urllib.parse import parse_qs, urlsplit

from scraper.short_drama import (
    IncompleteDramaRankingError,
    discover_douyin_scopes,
    parse_chinese_count,
    scrape_douyin_ranking,
    scrape_hongguo_ranking,
    scrape_kuaishou_ranking,
)


class Response:
    def __init__(self, payload=None, text=""):
        self.payload = payload
        self.text = text

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.urls = []

    def safe_get(self, url, **_kwargs):
        self.urls.append(url)
        if not self.responses:
            raise AssertionError(f"意外的额外请求: {url}")
        return self.responses.pop(0)


def douyin_series(index):
    return {
        "series_id": str(1000 + index),
        "series_name": f"抖音剧{index}",
        "desc": f"简介{index}",
        "hot_value": 9000 - index,
        "cover_url": {"url_list": [f"https://img/{index}.jpg"]},
        "series_content_types_new": [{"series_content_type": 1, "name": "逆袭"}],
        "stats": {
            "play_vv": 100000 + index,
            "collect_vv": 2000 + index,
            "total_episode": 60 + index,
            "updated_to_episode": 60 + index,
            "last_added_item_time": 1700000000,
        },
        "author": {"uid": f"u{index}", "nickname": f"作者{index}", "enterprise_verify_reason": "出品方"},
    }


def hongguo_html(route_id, page, total_pages, rows):
    payload = {"isSuccess": True, "rankList": rows, "pagination": {
        "pageNum": page, "totalPages": total_pages,
        "nextUrl": f"https://hongguoduanju.com/rank/example?page={page + 1}" if page < total_pages else None,
    }}
    args = [route_id, [{
        "key": "content", "routerDataFnName": "p",
        "routerDataFnArgs": [json.dumps(payload, ensure_ascii=False)],
    }]]
    return '<script data-fn-name="mergeLoaderData" data-fn-args="{}"></script>'.format(
        html.escape(json.dumps(args, ensure_ascii=False), quote=True)
    )


def hongguo_row(position, series_id=None):
    return {
        "id": str(series_id or 2000 + position),
        "seriesId": str(series_id or 2000 + position),
        "rank": position,
        "title": f"红果剧{position}",
        "cover": f"https://img/{position}.jpg",
        "href": f"/detail?series_id={series_id or 2000 + position}",
        "heatText": "1.2亿热度" if position == 1 else "8624万热度",
        "scoreText": "评分9.1",
        "favoriteText": "12.3万收藏",
        "likeText": "45.6万点赞",
        "tags": ["萌宝", "漫剧"],
        "description": f"红果简介{position}",
        "episodeVids": ["a", "b", "c"],
        "statusTags": ["新剧"] if position == 1 else [],
    }


def kuaishou_row(position):
    return {
        "rankNo": position,
        "courseId": 3000 + position,
        "courseName": f"快手剧{position}",
        "coverImg": f"https://img/{position}.jpg",
        "desc": f"快手简介{position}",
        "score": 8000 - position,
        "scoreStr": f"{8000 - position}万",
        "episodeDesc": "全88集",
        "tagNameList": ["逆袭"],
        "computeLabelList": [
            {"desc": "1.5亿播放"}, {"desc": f"持续在榜{position + 1}天"},
        ],
        "launchTag": {"text": "新"},
        "seriesJumpUrl": f"kwai://episode/play?serialId={4000 + position}",
        "tubeId": 4000 + position,
    }


class CountParserTest(unittest.TestCase):
    def test_chinese_counts(self):
        self.assertEqual(120_000_000, parse_chinese_count("1.2亿热度"))
        self.assertEqual(86_240_000, parse_chinese_count("8624万热度"))
        self.assertEqual(88, parse_chinese_count("全88集"))
        self.assertIsNone(parse_chinese_count("暂无"))


class DouyinTest(unittest.TestCase):
    def test_complete_cursor_pagination_and_field_mapping(self):
        session = FakeSession([
            Response({"status_code": 0, "update_time": 7, "series_infos": [douyin_series(1), douyin_series(2)],
                      "has_more": True, "offset": 2}),
            Response({"status_code": 0, "update_time": 7, "series_infos": [douyin_series(3)],
                      "has_more": False, "offset": 3}),
        ])
        items = scrape_douyin_ranking(session, "douyin_hot", max_pages=2)
        self.assertEqual([1, 2, 3], [item["rankPosition"] for item in items])
        self.assertEqual("short_drama", items[0]["contentKind"])
        self.assertEqual(100001, items[0]["playCount"])
        self.assertEqual(2001, items[0]["collectCount"])
        self.assertEqual("出品方", items[0]["publisher"])
        offsets = [parse_qs(urlsplit(url).query)["offset"][0] for url in session.urls]
        self.assertEqual(["0", "2"], offsets)

    def test_stalled_cursor_duplicate_and_page_budget_abort(self):
        for second in (
            {"status_code": 0, "series_infos": [douyin_series(1)], "has_more": False, "offset": 2},
            None,
        ):
            first = {"status_code": 0, "series_infos": [douyin_series(1)], "has_more": True, "offset": 1}
            responses = [Response(first)] + ([Response(second)] if second else [])
            with self.subTest(second=second), self.assertRaises(IncompleteDramaRankingError):
                scrape_douyin_ranking(FakeSession(responses), "douyin_hot", max_pages=len(responses))

    def test_discovers_current_board_scopes(self):
        payload = {"status_code": 0, "billboard_type_list": [
            {"type": 1, "sub_billboard_list": [{"type": 1, "name": "总榜"}, {"type": 101, "name": "都市逆袭"}]},
        ]}
        self.assertEqual([("1", "总榜"), ("101", "都市逆袭")],
                         discover_douyin_scopes(FakeSession([Response(payload)]), "douyin_hot"))


class HongguoTest(unittest.TestCase):
    def test_complete_html_pagination_and_author_value_fields(self):
        route_id = "rank_hot-drama/page"
        session = FakeSession([
            Response(text=hongguo_html(route_id, 1, 2, [hongguo_row(1), hongguo_row(2)])),
            Response(text=hongguo_html(route_id, 2, 2, [hongguo_row(3)])),
        ])
        items = scrape_hongguo_ranking(session, "hongguo_hot_all", max_pages=2)
        self.assertEqual(3, len(items))
        first = items[0]
        self.assertEqual(120_000_000, first["heatValue"])
        self.assertEqual(123_000, first["collectCount"])
        self.assertEqual(456_000, first["likeCount"])
        self.assertEqual(9.1, first["rating"])
        self.assertEqual(3, first["episodeCount"])
        self.assertEqual(["新剧"], first["platformLabels"])
        self.assertTrue(first["detailUrl"].startswith("https://hongguoduanju.com/"))

    def test_low_page_budget_and_duplicate_abort(self):
        route_id = "rank_hot-drama/page"
        with self.assertRaises(IncompleteDramaRankingError):
            scrape_hongguo_ranking(
                FakeSession([Response(text=hongguo_html(route_id, 1, 2, [hongguo_row(1)]))]),
                "hongguo_hot_all", max_pages=1,
            )
        with self.assertRaises(IncompleteDramaRankingError):
            scrape_hongguo_ranking(
                FakeSession([
                    Response(text=hongguo_html(route_id, 1, 2, [hongguo_row(1)])),
                    Response(text=hongguo_html(route_id, 2, 2, [hongguo_row(2, series_id=2001)])),
                ]),
                "hongguo_hot_all", max_pages=2,
            )


class KuaishouTest(unittest.TestCase):
    def test_single_response_is_complete_platform_top_list(self):
        payload = {"result": 1, "data": {"tabHotListDetail": {
            "id": 13, "content": [kuaishou_row(1), kuaishou_row(2)],
        }, "selectTabIndex": 0, "tabListInfo": [{"id": 13, "desc": "全网热播榜", "index": 0}]}}
        session = FakeSession([Response(payload)])
        items = scrape_kuaishou_ranking(session, "kuaishou_all_hot")
        self.assertEqual(2, len(items))
        self.assertEqual(150_000_000, items[0]["playCount"])
        self.assertEqual(2, items[0]["daysOnChart"])
        self.assertEqual(88, items[0]["episodeCount"])
        self.assertEqual("新", items[0]["platformLabel"])
        self.assertEqual(1, len(session.urls))

    def test_rank_gap_aborts(self):
        first, third = kuaishou_row(1), kuaishou_row(3)
        payload = {"result": 1, "data": {"tabHotListDetail": {"id": 0, "content": [first, third]},
                                          "selectTabIndex": 0,
                                          "tabListInfo": [{"id": 13, "desc": "全网热播榜", "index": 0}]}}
        with self.assertRaises(IncompleteDramaRankingError):
            scrape_kuaishou_ranking(FakeSession([Response(payload)]), "kuaishou_all_hot")


if __name__ == "__main__":
    unittest.main()
