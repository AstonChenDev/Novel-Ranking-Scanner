import unittest

from analysis.cross_rank import analyze_cross_rank
from analysis.genre import analyze_genre
from main import merge_ranking_data


class RankMetadataTest(unittest.TestCase):
    def test_merge_ranking_data_preserves_multi_rank_appearances(self):
        books = merge_ranking_data({
            "sanjiang": [
                {"bookId": "1", "title": "甲", "category": "玄幻", "rankPosition": 3},
            ],
            "strong": [
                {"bookId": "1", "title": "甲", "category": "玄幻", "rankPosition": 1},
                {"bookId": "2", "title": "乙", "category": "都市", "rankPosition": 2},
            ],
        })

        by_id = {book["bookId"]: book for book in books}

        self.assertEqual(len(books), 2)
        self.assertEqual(by_id["1"]["ranks"], ["sanjiang", "strong"])
        self.assertEqual(
            by_id["1"]["rankAppearances"],
            [
                {"rankType": "sanjiang", "rankPosition": 3},
                {"rankType": "strong", "rankPosition": 1},
            ],
        )

    def test_cross_rank_reads_rank_appearances(self):
        result = analyze_cross_rank([
            {
                "bookId": "1",
                "title": "甲",
                "rankAppearances": [
                    {"rankType": "sanjiang", "rankPosition": 3},
                    {"rankType": "strong", "rankPosition": 1},
                ],
            },
            {
                "bookId": "2",
                "title": "乙",
                "rankAppearances": [{"rankType": "newbook", "rankPosition": 4}],
            },
        ])

        self.assertEqual(result["totalUniqueBooks"], 2)
        self.assertEqual(result["distribution"], [
            {"rankCount": 1, "bookCount": 1},
            {"rankCount": 2, "bookCount": 1},
        ])
        self.assertEqual(result["multiRankBooks"][0]["ranks"], ["sanjiang", "strong"])

    def test_genre_by_rank_counts_each_appearance(self):
        result = analyze_genre([
            {
                "bookId": "1",
                "title": "甲",
                "category": "玄幻",
                "rankAppearances": [
                    {"rankType": "sanjiang", "rankPosition": 3},
                    {"rankType": "strong", "rankPosition": 1},
                ],
            },
            {
                "bookId": "2",
                "title": "乙",
                "category": "都市",
                "rankAppearances": [{"rankType": "sanjiang", "rankPosition": 4}],
            },
        ])

        sanjiang = {item["category"]: item["count"] for item in result["byRank"]["sanjiang"]}
        strong = {item["category"]: item["count"] for item in result["byRank"]["strong"]}

        self.assertEqual(sanjiang, {"玄幻": 1, "都市": 1})
        self.assertEqual(strong, {"玄幻": 1})


if __name__ == "__main__":
    unittest.main()
