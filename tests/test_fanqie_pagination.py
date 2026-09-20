"""官网offset分页和完整性保护，不访问真实网络。"""
import json
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from scraper.fanqie import (
    IncompleteRankingError, discover_fanqie_scope_definitions,
    fetch_fanqie_rank_page, scrape_fanqie_ranking,
)
from ingestion import build_ingestion_payload


def record(number, book_id=None):
    return {'bookId': str(book_id or number), 'bookName': f'书{number}', 'currentPos': number,
            'read_count': str(1000-number), 'curent_category_id': 1141, 'categoryV2': '书籍类型'}


def response(start, stop, total=100, version='v1'):
    result = Mock()
    result.json.return_value = {'code': 0, 'data': {'book_list': [record(i) for i in range(start, stop+1)],
                                                   'total_num': total, 'rankVersion': version}}
    return result


class PaginationTest(unittest.TestCase):
    def test_loads_all_100_books_and_pins_version(self):
        session = Mock()
        session.safe_get.side_effect = [response(offset+1, offset+50) for offset in range(0, 100, 50)]
        books = scrape_fanqie_ranking(session, 'male_read', scope_keys=['1141'])
        self.assertEqual(100, len(books))
        self.assertEqual(list(range(1, 101)), [b['rankPosition'] for b in books])
        urls = [parse_qs(urlsplit(call.args[0]).query) for call in session.safe_get.call_args_list]
        self.assertEqual(['0', '50'], [u['offset'][0] for u in urls])
        self.assertNotIn('rank_version', urls[0])
        self.assertTrue(all(u['rank_version']==['v1'] for u in urls[1:]))
        self.assertTrue(all(u['category_id']==['1141'] and u['limit']==['50'] for u in urls))

    def test_short_final_page_is_valid(self):
        session = Mock()
        session.safe_get.side_effect = [response(1, 50, total=57), response(51, 57, total=57)]
        books = scrape_fanqie_ranking(session, 'female_new', max_pages=2, scope_keys=['1141'])
        self.assertEqual(57, len(books))
        query = parse_qs(urlsplit(session.safe_get.call_args.args[0]).query)
        self.assertEqual(['0'], query['gender'])
        self.assertEqual(['1'], query['rankMold'])

    def test_repeat_page_is_an_error_not_successful_truncation(self):
        session = Mock()
        session.safe_get.side_effect = [response(1, 50), response(1, 50)]
        with self.assertRaises(IncompleteRankingError):
            scrape_fanqie_ranking(session, 'male_read', scope_keys=['1141'])

    def test_missing_page_aborts(self):
        session = Mock()
        session.safe_get.side_effect = [response(1, 50), response(51, 50)]
        with self.assertRaisesRegex(IncompleteRankingError, '缺失'):
            scrape_fanqie_ranking(session, 'male_read', scope_keys=['1141'])

    def test_low_page_budget_is_not_a_complete_snapshot(self):
        session = Mock()
        session.safe_get.return_value = response(1, 50)
        with self.assertRaisesRegex(IncompleteRankingError, '配置1页不足'):
            scrape_fanqie_ranking(session, 'male_read', max_pages=1, scope_keys=['1141'])
        session.safe_get.assert_called_once()

    def test_version_drift_and_total_drift_abort(self):
        for second in [response(51, 100, version='v2'), response(51, 99, total=99)]:
            session = Mock()
            session.safe_get.side_effect = [response(1, 50), second]
            with self.assertRaises(IncompleteRankingError):
                scrape_fanqie_ranking(session, 'male_read', scope_keys=['1141'])

    def test_invalid_or_denied_responses_are_not_empty_success(self):
        for payload in [{'code': 403, 'message': 'denied'}, {'code': 0, 'data': {}},
                        {'code':0,'data':{'book_list':[],'rankVersion':'v1','total_num':True}}]:
            session = Mock()
            session.safe_get.return_value.json.return_value = payload
            with self.assertRaises(IncompleteRankingError):
                fetch_fanqie_rank_page(session, 'male_read', '1141')
        session.safe_get.return_value = None
        with self.assertRaises(IncompleteRankingError):
            fetch_fanqie_rank_page(session, 'male_read', '1141')

    def test_string_total_is_supported_and_empty_scope_aborts_publication(self):
        session = Mock()
        session.safe_get.return_value = response(1, 38, total='38')
        self.assertEqual(38, len(scrape_fanqie_ranking(session, 'male_new', scope_keys=['27'])))
        session.safe_get.return_value.json.return_value = {'code':0,'data':{'book_list':None,'total_num':'0','rankVersion':''}}
        with self.assertRaisesRegex(IncompleteRankingError, '空分类'):
            scrape_fanqie_ranking(session, 'male_new', scope_keys=['27'])

    def test_scope_name_is_rank_dimension_not_book_category(self):
        session = Mock()
        session.safe_get.return_value = response(1, 1, total=1)
        books, _, _ = fetch_fanqie_rank_page(session, 'male_read', '1141', scope_name='西方奇幻')
        payload = build_ingestion_payload({'site':'fanqie','rankings':{'male_read':books}})
        self.assertEqual('西方奇幻', payload['books'][0]['subcategory'])
        self.assertEqual('书籍类型', payload['books'][0]['category'])

    def test_navigation_discovers_official_scope_names(self):
        state = {'rank': {'book_list':[record(1)], 'rankCategoryTypeList':{
            'male':[{'id':1141,'name':'西方奇幻'},{'id':1140,'name':'东方仙侠'}]}}}
        html = '<a href="/rank/1_2_1141">西方奇幻</a><a href="/rank/1_2_1140">东方仙侠</a><script>window.__INITIAL_STATE__='+json.dumps(state)+';</script>'
        session = Mock()
        session.safe_get.return_value.text = html
        self.assertEqual([('1141','西方奇幻'),('1140','东方仙侠')], discover_fanqie_scope_definitions(session,'male_read'))

    def test_missing_navigation_is_not_silently_replaced_by_first_ten(self):
        with patch('scraper.fanqie._fetch_fanqie_html', return_value='<html></html>'):
            with self.assertRaises(IncompleteRankingError):
                discover_fanqie_scope_definitions(Mock(), 'male_read')
