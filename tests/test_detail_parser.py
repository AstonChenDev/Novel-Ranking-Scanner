import unittest

from scraper.detail import has_useful_detail, parse_book_detail


class DetailParserTest(unittest.TestCase):
    def test_parse_rating_when_score_markup_exists(self):
        html = """
        <html>
          <body>
            <h1>甲书</h1>
            <div class="book-score">评分 8.7 分 123人评分</div>
          </body>
        </html>
        """

        detail = parse_book_detail(html, "1")

        self.assertEqual(detail["rating"], 8.7)
        self.assertEqual(detail["ratingCount"], 123)

    def test_minimal_detail_cache_is_not_useful(self):
        self.assertFalse(has_useful_detail({
            "bookId": "1",
            "detailUrl": "https://book.qidian.com/info/1/",
            "scrapedAt": "2026-06-02T12:00:00",
        }))
        self.assertTrue(has_useful_detail({
            "bookId": "1",
            "rating": 8.7,
        }))


if __name__ == "__main__":
    unittest.main()
