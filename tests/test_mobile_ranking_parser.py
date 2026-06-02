import json
import unittest

from scraper.ranking import parse_mobile_ranking_page


def make_mobile_html(page_data):
    context = {"pageContext": {"pageProps": {"pageData": page_data}}}
    return (
        '<script>var name = "x-waf-captcha-referer";</script>'
        '<html><body><script id="vite-plugin-ssr_pageContext" '
        f'type="application/json">{json.dumps(context, ensure_ascii=False)}</script></body></html>'
    )


class MobileRankingParserTest(unittest.TestCase):
    def test_parse_records_from_mobile_ssr(self):
        html = make_mobile_html({
            "records": [
                {
                    "bid": 1049113654,
                    "bName": "北洋之梦",
                    "bAuth": "大罗罗",
                    "cat": "历史",
                    "cnt": "27.25万字",
                    "desc": "穿越成了北洋总统预备班的学渣",
                    "rankNum": 1,
                }
            ]
        })

        books = parse_mobile_ranking_page(html, "sanjiang")

        self.assertEqual(len(books), 1)
        self.assertEqual(books[0]["bookId"], "1049113654")
        self.assertEqual(books[0]["title"], "北洋之梦")
        self.assertEqual(books[0]["wordCount"], 272500)
        self.assertEqual(books[0]["rankPosition"], 1)

    def test_parse_rank_home_fallback_key(self):
        html = make_mobile_html({
            "newbRank": [
                {
                    "bid": "1049138081",
                    "bName": "太虚至尊之众神之战",
                    "bAuth": "荒古霸主",
                    "cat": "玄幻",
                    "cnt": "17.67万字",
                    "rankNum": 1,
                }
            ]
        })

        books = parse_mobile_ranking_page(html, "newbook")

        self.assertEqual(len(books), 1)
        self.assertEqual(books[0]["category"], "玄幻")

    def test_skip_time_marker_records(self):
        html = make_mobile_html({
            "records": [
                {"isTime": True, "sTime": "2026.05.31", "bid": ""},
                {
                    "bid": "1048640442",
                    "bName": "临圣",
                    "bAuth": "卖报小郎君",
                    "cat": "仙侠",
                    "cnt": "15.52万字",
                },
            ]
        })

        books = parse_mobile_ranking_page(html, "strong")

        self.assertEqual(len(books), 1)
        self.assertEqual(books[0]["rankPosition"], 1)


if __name__ == "__main__":
    unittest.main()
