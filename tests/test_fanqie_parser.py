import json
import unittest

from scraper.fanqie import (
    decode_fanqie_font_text,
    extract_initial_state,
    parse_fanqie_ranking_page,
)


def make_fanqie_html(state):
    return (
        "<html><body><script>"
        f"window.__INITIAL_STATE__={json.dumps(state, ensure_ascii=False)};"
        "</script></body></html>"
    )


class FanqieParserTest(unittest.TestCase):
    def test_extract_initial_state(self):
        state = {"rank": {"book_list": []}}

        parsed = extract_initial_state(make_fanqie_html(state))

        self.assertEqual(parsed, state)

    def test_parse_rank_book_list(self):
        html = make_fanqie_html({
            "rank": {
                "rankCategoryTypeList": {
                    "male": [{"id": "1141", "name": "西方奇幻"}],
                },
                "book_list": [
                    {
                        "bookId": "7629316029604170777",
                        "bookName": "金龙领主",
                        "author": "作者甲",
                        "abstract": "西幻领主种田经营。",
                        "wordNumber": "179867",
                        "read_count": "146337",
                        "currentPos": 2,
                        "creationStatus": "1",
                        "curent_category_id": 1141,
                        "lastChapterTitle": "第85章 小小的叶莉西娅",
                        "lastChapterUpdateTime": "1780318103",
                    }
                ],
            }
        })

        books = parse_fanqie_ranking_page(html, "male_read")

        self.assertEqual(len(books), 1)
        self.assertEqual(books[0]["site"], "fanqie")
        self.assertEqual(books[0]["bookId"], "7629316029604170777")
        self.assertEqual(books[0]["title"], "金龙领主")
        self.assertEqual(books[0]["category"], "西方奇幻")
        self.assertEqual(books[0]["wordCount"], 179867)
        self.assertEqual(books[0]["readCount"], 146337)
        self.assertEqual(books[0]["rankPosition"], 2)
        self.assertEqual(books[0]["status"], "连载")
        self.assertEqual(
            books[0]["detailUrl"],
            "https://fanqienovel.com/page/7629316029604170777",
        )

    def test_marks_private_use_font_text(self):
        html = make_fanqie_html({
            "rank": {
                "book_list": [
                    {
                        "bookId": "1",
                        "bookName": "掌娇娇",
                        "author": "支云",
                        "abstract": "简介：。",
                    }
                ],
            }
        })

        books = parse_fanqie_ranking_page(html, "female_read")

        self.assertEqual(books[0]["title"], "掌上娇娇")
        self.assertEqual(books[0]["synopsis_short"], "简介：我在世界。")
        self.assertTrue(books[0]["fontEncrypted"])
        self.assertTrue(books[0]["fontDecoded"])

    def test_decode_fanqie_font_text(self):
        text = "领：苦痛，养"

        self.assertEqual(decode_fanqie_font_text(text), "领主：我在苦痛世界，养成少女")


if __name__ == "__main__":
    unittest.main()
