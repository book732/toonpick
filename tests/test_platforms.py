"""Verify platform identity, metadata adapters and source boundaries without network calls."""

import unittest
import json
import tempfile
import urllib.parse
from pathlib import Path
from unittest.mock import patch

from services import platforms as _service
from services.catalog import _select_candidates


class _PlatformTests(unittest.TestCase):
    def test_collection_search_uses_pagination_and_complete_filter(self):
        _data = {"result": {"is_end": False, "list": [{"series_id": 1, "category_uid": 10, "age_grade": 15, "title": "작품", "sub_category": "판타지"}]}, "result_code": 0}
        with patch.object(_service, "_fetch", return_value=json.dumps(_data)) as _fetch:
            _items, _status = _service._search_platform("kakaopage", "완결테스트", 999001, 2, 100, True)
        _query = urllib.parse.parse_qs(urllib.parse.urlsplit(_fetch.call_args.args[0]).query)
        self.assertEqual(_query["page"], ["2"])
        self.assertEqual(_query["size"], ["100"])
        self.assertEqual(_query["is_complete"], ["true"])
        self.assertEqual(_items[0]["status"], "완결")
        self.assertTrue(_status["hasMore"])

    def test_rejected_search_response_is_unavailable_instead_of_successful_empty_data(self):
        with patch.object(_service, "_fetch", return_value=json.dumps({"code": -93400})):
            _items, _status = _service._search_platform("lezhin", "거절테스트", 999002)
        self.assertEqual(_items, [])
        self.assertEqual(_status["status"], "unavailable")

    def test_official_detail_metadata_is_cached_across_collection_runs(self):
        with tempfile.TemporaryDirectory() as _directory, patch.object(_service, "_CACHE", Path(_directory)), patch.object(_service, "_fetch", return_value='<meta property="og:description" content="작품 줄거리">') as _fetch:
            _first = _service._enrich("ridi", "https://ridibooks.com/books/999001", 991)
            _second = _service._enrich("ridi", "https://ridibooks.com/books/999001", 992)
            self.assertEqual(_first, _second)
            _fetch.assert_called_once()

    def test_registry_contains_unique_domestic_services_and_official_https_links(self):
        self.assertEqual(len(_service._REGISTRY), 19)
        self.assertEqual(len(_service._BY_KEY), 19)
        for _platform in _service._REGISTRY:
            self.assertTrue(_platform["home"].startswith("https://"))
            self.assertTrue(_platform["searchUrl"].startswith("https://"))

    def test_platform_ids_do_not_collide_with_naver_or_another_platform(self):
        _kakao = _service._item(_service._BY_KEY["kakaopage"], "https://page.kakao.com/content/123", "작품", _tags=["판타지"])
        _ridi = _service._item(_service._BY_KEY["ridi"], "https://ridibooks.com/books/123", "작품", _tags=["판타지"])
        self.assertNotEqual(_kakao["id"], _ridi["id"])
        self.assertNotEqual(_kakao["id"], "123")
        self.assertEqual(_kakao["status"], "확인 필요")

    def test_untrusted_work_and_cover_domains_are_rejected(self):
        _platform = _service._BY_KEY["ridi"]
        self.assertIsNone(_service._item(_platform, "https://evil.example/books/123", "작품"))
        self.assertIsNone(_service._item(_platform, "https://ridibooks.com@evil.example/books/123", "작품"))
        _entry = _service._item(_platform, "https://ridibooks.com/books/123", "작품", "https://ridicdn.net.evil.example/test.jpg")
        self.assertEqual(_entry["cover"], "assets/cover-placeholder.svg")

    def test_kakaopage_adapter_excludes_novels_and_restricted_records(self):
        _data = {"result": {"list": [
            {"series_id": 1, "category_uid": 10, "age_grade": 15, "title": "공개 웹툰", "authors": "작가", "thumbnail": "test/resource", "sub_category": "판타지"},
            {"series_id": 2, "category_uid": 11, "age_grade": 0, "title": "웹소설"},
            {"series_id": 3, "category_uid": 10, "age_grade": 19, "title": "제한 작품"},
        ]}}
        _items = _service._parse_json_items(_service._BY_KEY["kakaopage"], _data)
        self.assertEqual([_item["title"] for _item in _items], ["공개 웹툰"])
        self.assertEqual(_items[0]["platform"], "카카오페이지")
        self.assertEqual(_items[0]["genre"], "판타지")

    def test_bomtoon_adapter_uses_comic_titles_and_verified_thumbnails(self):
        _data = {"data": {"results": [{"contentsId": 1, "alias": "example", "title": "작품 제목", "contentsType": "comic", "isAdult": False, "author": ["작가"], "tags": ["판타지"], "thumbnail": [{"thumbnailType": "VERTICAL", "imagePath": "https://image.balcony.studio/example.webp"}]}]}}
        _item = _service._parse_json_items(_service._BY_KEY["bomtoon"], _data)[0]
        self.assertEqual(_item["title"], "작품 제목")
        self.assertEqual(_item["cover"], "https://image.balcony.studio/example.webp")

    def test_html_review_links_do_not_replace_the_actual_title_card(self):
        _html = '<a href="/webtoon/wt_123"><img src="https://img.mrblue.com/cover.jpg" alt="작품 제목"></a><a href="/webtoon/wt_123#review">리뷰 9 건</a>'
        _items = _service._parse_html_items(_service._BY_KEY["mrblue"], _html)
        self.assertEqual(len(_items), 1)
        self.assertEqual(_items[0]["title"], "작품 제목")
        self.assertEqual(_items[0]["cover"], "https://img.mrblue.com/cover.jpg")

    def test_icon_images_do_not_displace_the_actual_cover(self):
        _html = '<a href="comics_comics-123.html"><img src="/icon/up.png" alt="UPDATE"><img src="/covers/123.jpg" alt="작품 제목"></a>'
        _item = _service._parse_html_items(_service._BY_KEY["peanutoon"], _html)[0]
        self.assertEqual(_item["title"], "작품 제목")
        self.assertEqual(_item["cover"], "https://www.peanutoon.com/covers/123.jpg")

    def test_mootoon_adapter_keeps_title_ids_and_excludes_print_comics(self):
        _html = '<a href="/comic/moo_list.mg?tcode=aaa">1 테스트 웹툰 판타지 유지</a><a href="/comic/moo_list.mg?tcode=bbb">2 만화 제목 만화 무협 유지</a><a href="/comic/moo_list.mg?tcode=ccc">3 다른 웹툰 액션 상승 1</a>'
        _items = _service._parse_html_items(_service._BY_KEY["mootoon"], _html)
        self.assertEqual([_item["title"] for _item in _items], ["테스트", "다른"])
        self.assertEqual(len({_item["id"] for _item in _items}), 2)
        self.assertTrue(_items[0]["url"].endswith("?tcode=aaa"))

    def test_navigation_links_are_not_collected_as_titles(self):
        _html = '<a href="/webtoon/ranking">랭킹</a><a href="/webtoon/sat">토요 웹툰</a>'
        self.assertEqual(_service._parse_html_items(_service._BY_KEY["mrblue"], _html), [])

    def test_platform_link_only_state_is_explicit_and_does_not_fetch(self):
        with patch.object(_service, "_fetch") as _fetch:
            _items, _status = _service._search_platform("onestory", "test", 999999)
        self.assertEqual(_items, [])
        self.assertEqual(_status["status"], "link_only")
        _fetch.assert_not_called()

    def test_metadata_html_is_cleaned_without_executing_it(self):
        self.assertEqual(_service._clean_text('<b>작품</b><br>줄거리 &amp; 소개'), '작품 줄거리 & 소개')

    def test_candidate_selection_preserves_platform_choices_and_diversity(self):
        _items = []
        for _key, _url in [("kakaopage", "https://page.kakao.com/content/"), ("ridi", "https://ridibooks.com/books/")]:
            for _index in range(50):
                _items.append(_service._item(_service._BY_KEY[_key], _url + str(_index), _key + " 작품" + str(_index), _tags=["판타지"]))
        _preferences = {"genres": ["판타지"], "mood": "전체", "status": "전체", "notes": "", "platforms": []}
        _selected = _select_candidates(_preferences, {"items": _items}, [])
        self.assertEqual(len(_selected), 36)
        self.assertEqual(sum(_item["platformKey"] == "ridi" for _item in _selected), 18)
        _only_ridi = _select_candidates({**_preferences, "platforms": ["ridi"]}, {"items": _items}, [])
        self.assertTrue(all(_item["platformKey"] == "ridi" for _item in _only_ridi))


if __name__ == "__main__":
    unittest.main()
