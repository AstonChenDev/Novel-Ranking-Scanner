import unittest
from unittest.mock import Mock

import requests

from ingestion import build_ingestion_payload, post_ingestion, validate_ingestion_result


class IngestionPayloadTest(unittest.TestCase):
    def test_publication_requires_positive_complete_acknowledgement(self):
        validate_ingestion_result({'accepted':2,'snapshot_ids':[1,2]}, {'count':2})
        for result in [{'status_code':200,'text':'<html>gateway</html>'}, {'accepted':0,'snapshot_ids':[]},
                       {'accepted':1,'snapshot_ids':[1]}, {'accepted':'2','snapshot_ids':[1]},
                       {'accepted':2,'snapshot_ids':[0]}, {'accepted':2,'snapshot_ids':[1,1]}]:
            with self.subTest(result=result), self.assertRaises(ValueError):
                validate_ingestion_result(result, {'count':2})

    def test_large_ingestion_response_is_summarized_without_modifying_result(self):
        from main import ingestion_result_summary
        response = {'accepted':100,'snapshot_ids':[1,2], 'collection_tasks':[{'id':i} for i in range(100)]}
        self.assertEqual({'accepted':100,'snapshot_count':2,'created_tasks':100}, ingestion_result_summary(response))
        self.assertEqual(100, len(response['collection_tasks']))

    def test_expands_multi_platform_rankings_and_preserves_extra(self):
        payload = build_ingestion_payload({
            "site": "fanqie",
            "siteName": "番茄小说",
            "timestamp": "2026-09-19T08:00:00+08:00",
            "rankings": {
                "male_read": [{
                    "bookId": "1", "bookName": "甲书", "author": "作者",
                    "currentPos": 2, "read_count": "42", "customField": "keep",
                }],
                "male_new": [{
                    "bookId": "1", "bookName": "甲书", "author": "作者",
                    "currentPos": 1,
                }],
            },
        })

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["count"], 2)
        rows = {(row["book_id"], row["rank_type"]): row for row in payload["books"]}
        self.assertEqual(rows[("1", "male_read")]["rank_position"], 2)
        self.assertEqual(rows[("1", "male_read")]["extra"]["customField"], "keep")
        self.assertEqual(rows[("1", "male_new")]["rank_position"], 1)

    def test_expands_rank_appearances_when_only_books_are_available(self):
        payload = build_ingestion_payload({
            "site": "qidian",
            "books": [{
                "bookId": 9, "title": "起点书",
                "rankAppearances": [
                    {"rankType": "newbook", "rankPosition": 3},
                    {"rankType": "strong", "rankPosition": 8},
                ],
            }],
        })
        self.assertEqual(payload["count"], 2)
        self.assertEqual({row["rank_type"] for row in payload["books"]}, {"newbook", "strong"})

    def test_skips_invalid_rows(self):
        payload = build_ingestion_payload({"site": "qidian", "books": [{"title": "缺少ID"}]})
        self.assertEqual(payload["books"], [])

    def test_single_rank_payload_uses_rank_key_when_row_omits_it(self):
        payload = build_ingestion_payload({
            "site": "qidian",
            "rank_key": "newbook",
            "books": [{"book_id": "10", "title": "新书"}],
        })
        self.assertEqual(payload["source"]["rank_key"], "newbook")
        self.assertEqual(payload["books"][0]["rank_type"], "newbook")

    def test_scope_key_keeps_same_book_in_two_category_rankings(self):
        payload = build_ingestion_payload({
            "site": "fanqie",
            "rankings": {
                "male_read": [
                    {"bookId": "1", "title": "同书", "fanqieCategoryId": "1141", "currentPos": 1},
                    {"bookId": "1", "title": "同书", "fanqieCategoryId": "1142", "currentPos": 2},
                ],
            },
        })
        self.assertEqual(payload["count"], 2)
        self.assertEqual({row["rank_scope_key"] for row in payload["books"]}, {"1141", "1142"})

    def test_short_drama_author_fields_are_normalized_without_losing_extensions(self):
        payload = build_ingestion_payload({
            "site": "douyin",
            "timestamp": "2026-09-23T08:30:00+08:00",
            "rankings": {
                "douyin_hot": [{
                    "bookId": "series-1", "title": "短剧甲", "author": "剧场账号",
                    "category": "逆袭", "synopsis_short": "简介", "rankPosition": 1,
                    "rankScopeKey": "1", "rankScopeName": "总榜",
                    "contentKind": "short_drama", "contentForm": "comic_drama",
                    "publisher": "出品公司", "heatValue": 8000000, "playCount": 120000000,
                    "collectCount": 340000, "episodeCount": 88, "durationSeconds": 7200,
                    "isCharged": False, "isExclusive": True,
                    "tags": ["逆袭", "年代"], "creatorId": "creator-1",
                }],
            },
        })
        row = payload["books"][0]
        self.assertEqual("short_drama", row["content_kind"])
        self.assertEqual("comic_drama", row["content_form"])
        self.assertEqual(120000000, row["play_count"])
        self.assertEqual(340000, row["collect_count"])
        self.assertEqual(88, row["episode_count"])
        self.assertIs(row["is_charged"], False)
        self.assertIs(row["is_exclusive"], True)
        self.assertEqual(["逆袭", "年代"], row["tags"])
        self.assertEqual("creator-1", row["extra"]["creatorId"])


class IngestionHttpTest(unittest.TestCase):
    def test_retries_transient_failure(self):
        response_503 = Mock(status_code=503, headers={}, content=b"busy")
        response_200 = Mock(status_code=200, headers={}, content=b'{"accepted": 1}')
        response_200.raise_for_status.return_value = None
        session = Mock()
        session.post.side_effect = [response_503, response_200]

        result = post_ingestion(
            {"schema_version": 1, "source": {}, "books": []},
            "http://internal.test/ingest",
            retries=1,
            session=session,
        )

        self.assertIs(result, response_200)
        self.assertEqual(session.post.call_count, 2)
        self.assertEqual(session.post.call_args.kwargs["headers"]["Content-Type"], "application/json")

    def test_sends_bearer_and_internal_token(self):
        response = Mock(status_code=200, headers={}, content=b"{}")
        response.raise_for_status.return_value = None
        session = Mock()
        session.post.return_value = response

        post_ingestion({}, "http://internal.test/ingest", token="secret", retries=0, session=session)

        headers = session.post.call_args.kwargs["headers"]
        self.assertEqual(headers["Authorization"], "Bearer secret")
        self.assertEqual(headers["X-Internal-Token"], "secret")

    def test_raises_on_non_retryable_http_error(self):
        response = Mock(status_code=400, headers={}, content=b"bad")
        response.raise_for_status.side_effect = requests.HTTPError("400", response=response)
        session = Mock()
        session.post.return_value = response

        with self.assertRaises(requests.HTTPError):
            post_ingestion({}, "http://internal.test/ingest", retries=3, session=session)
        session.post.assert_called_once()


if __name__ == "__main__":
    unittest.main()
