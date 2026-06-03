import unittest

from main import build_report_book_snapshot
from report.markdown import generate_report


class ReportMarkdownTest(unittest.TestCase):
    def test_report_includes_book_samples_when_available(self):
        books = build_report_book_snapshot([
            {
                "bookId": "1",
                "title": "甲书",
                "author": "张三",
                "category": "玄幻",
                "wordCount": 150000,
                "rating": 8.6,
                "ratingCount": 123,
                "tags": ["重生", "异世"],
                "coverUrl": "https://img.example.com/cover.jpg",
                "synopsis_short": "少年醒来，发现自己站在异世界的城门前。",
                "detailUrl": "https://book.qidian.com/info/1/",
                "rankAppearances": [{"rankType": "sanjiang", "rankPosition": 1}],
            }
        ])

        report = generate_report({
            "timestamp": "2026-06-02T12:00:00",
            "bookCount": 1,
            "books": books,
            "analyses": {
                "genre": {
                    "total": [{"category": "玄幻", "count": 1, "pct": 100.0}],
                    "byRank": {"sanjiang": [{"category": "玄幻", "count": 1, "pct": 100.0}]},
                    "topCategories": ["玄幻"],
                    "categoryCount": 1,
                }
            },
        })

        self.assertIn("## 二、重点书目速览", report)
        self.assertIn("[《甲书》](https://book.qidian.com/info/1/)", report)
        self.assertIn("少年醒来", report)
        self.assertIn("三江推荐#1", report)
        self.assertIn("## 十、原件：逐本书籍档案", report)
        self.assertIn("| 评分 | 8.6分 |", report)
        self.assertIn('"ratingCount": 123', report)
        self.assertIn('"tags": [', report)

    def test_report_without_books_still_generates_analysis_sections(self):
        report = generate_report({
            "timestamp": "2026-06-02T12:00:00",
            "bookCount": 1,
            "analyses": {
                "genre": {
                    "total": [{"category": "都市", "count": 1, "pct": 100.0}],
                    "byRank": {},
                    "topCategories": ["都市"],
                    "categoryCount": 1,
                }
            },
        })

        self.assertIn("## 三、分类分布", report)
        self.assertNotIn("重点书目速览", report)
        self.assertNotIn("原件：逐本书籍档案", report)

    def test_book_snapshot_preserves_unknown_fields(self):
        books = build_report_book_snapshot([
            {
                "bookId": "1",
                "title": "甲书",
                "customField": {"nested": "value"},
                "synopsis_short": "完整简介不应被截断。",
                "rankType": "sanjiang",
            }
        ])

        self.assertEqual(books[0]["customField"], {"nested": "value"})
        self.assertEqual(books[0]["synopsis"], "完整简介不应被截断。")

    def test_fanqie_report_uses_site_and_rank_names(self):
        report = generate_report({
            "site": "fanqie",
            "siteName": "番茄小说",
            "timestamp": "2026-06-03T12:00:00",
            "bookCount": 1,
            "books": [
                {
                    "bookId": "1",
                    "site": "fanqie",
                    "title": "甲书",
                    "rankAppearances": [{"rankType": "male_read", "rankPosition": 1}],
                }
            ],
            "analyses": {},
        })

        self.assertIn("# 番茄小说排行榜分析报告", report)
        self.assertIn("男频阅读榜#1", report)

    def test_fanqie_report_decodes_font_mapped_text(self):
        report = generate_report({
            "site": "fanqie",
            "siteName": "番茄小说",
            "timestamp": "2026-06-03T12:00:00",
            "bookCount": 1,
            "books": [
                {
                    "bookId": "1",
                    "site": "fanqie",
                    "title": "领：苦痛",
                    "synopsis_short": "养",
                    "rankAppearances": [{"rankType": "male_read", "rankPosition": 1}],
                }
            ],
            "analyses": {},
        })

        self.assertIn("领主：我在苦痛世界", report)
        self.assertIn("养成少女", report)
        self.assertNotIn("", report)


if __name__ == "__main__":
    unittest.main()
