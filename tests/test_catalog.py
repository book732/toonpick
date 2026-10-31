"""Verify collection caching, bounded retrieval and official-source validation."""

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from services import catalog as _catalog_service


_METADATA = {
    "titleId": 123456, "titleName": "테스트 작품", "synopsis": "성장하는 주인공의 이야기",
    "communityArtists": [{"name": "작가"}], "thumbnailUrl": "https://image-comic.pstatic.net/webtoon/123456/thumbnail/test.jpg",
    "curationTagList": [{"tagName": "판타지", "curationType": "GENRE_FANTASY"}, {"tagName": "성장", "curationType": "CUSTOM_TAG"}],
    "age": {"description": "15세 이용가"}, "favoriteCount": 100, "finished": False, "rest": False,
    "publishDayOfWeekList": ["MONDAY"],
}
_ITEM = _catalog_service._normalize_item(_METADATA)
_PREFERENCES = {"genres": ["판타지"], "mood": "힐링", "status": "전체", "notes": "성장하는 이야기가 좋아요"}


class _CatalogTests(unittest.TestCase):
    def setUp(self):
        _external = patch.object(_catalog_service, "_search_platforms", return_value=([], []))
        _external.start()
        self.addCleanup(_external.stop)
    def test_official_metadata_is_normalized_without_inventing_titles_or_links(self):
        self.assertEqual(_ITEM["title"], _METADATA["titleName"])
        self.assertEqual(_ITEM["genre"], "판타지")
        self.assertEqual(_ITEM["url"], "https://comic.naver.com/webtoon/list?titleId=123456")
        self.assertIn("성장", _ITEM["tags"])

    def test_untrusted_cover_hosts_and_age_restricted_results_are_excluded(self):
        self.assertIsNone(_catalog_service._normalize_item({**_METADATA, "thumbnailUrl": "https://evil.example/test.jpg"}))
        self.assertIsNone(_catalog_service._normalize_item({**_METADATA, "adult": True}))
        self.assertIsNone(_catalog_service._normalize_item({**_METADATA, "age": {"description": "18세 이용가"}}))

    def test_metadata_cache_avoids_duplicate_network_requests(self):
        with tempfile.TemporaryDirectory() as _directory, patch.object(_catalog_service, "_CACHE", Path(_directory)), patch.object(_catalog_service, "_read_json", return_value=_METADATA) as _request:
            self.assertEqual(_catalog_service._fetch_metadata("123456"), _ITEM)
            self.assertEqual(_catalog_service._fetch_metadata("123456"), _ITEM)
            _request.assert_called_once()

    def test_search_can_hydrate_a_new_title_outside_the_snapshot(self):
        with patch.object(_catalog_service, "_search_query", return_value=(["123456"], "https://comic.naver.com/api/search/webtoon?keyword=test")), patch.object(_catalog_service, "_fetch_metadata", return_value=_ITEM) as _fetch:
            _items, _evidence = _catalog_service._search_web(_PREFERENCES, {"items": []})
        self.assertEqual(_items[0]["id"], "123456")
        self.assertEqual(_items[0]["discovery"], "web")
        self.assertEqual(_evidence["newTitles"], 1)
        self.assertEqual(_evidence["status"], "ok")
        _fetch.assert_called_once_with("123456")

    def test_search_failure_is_reported_without_fabricated_evidence(self):
        with patch.object(_catalog_service, "_search_query", side_effect=OSError("offline")):
            _items, _evidence = _catalog_service._search_web(_PREFERENCES, {"items": []})
        self.assertEqual(_items, [])
        self.assertEqual(_evidence["urls"], [])
        self.assertEqual(_evidence["status"], "unavailable")

    def test_search_uses_bounded_queries_and_keeps_a_context_query(self):
        with patch.object(_catalog_service, "_search_query", return_value=([], "https://comic.naver.com/search")) as _search:
            _, _evidence = _catalog_service._search_web(_PREFERENCES, {"items": []})
        self.assertLessEqual(_search.call_count, 3)
        self.assertIn("성장", _evidence["queries"])
        self.assertIn("힐링", _evidence["queries"])

    def test_ai_candidate_count_is_bounded_and_hard_filters_are_preserved(self):
        _items = [{**_ITEM, "id": str(200000 + _index), "title": "작품" + str(_index), "genre": "판타지" if _index % 2 else "로맨스", "favorites": _index, "status": "완결" if _index % 3 else "연재"} for _index in range(200)]
        _web = {**_ITEM, "id": "999999", "title": "새 작품", "status": "완결", "discovery": "web"}
        _selected = _catalog_service._select_candidates({**_PREFERENCES, "status": "완결"}, {"items": _items}, [_web])
        self.assertEqual(len(_selected), 36)
        self.assertIn("999999", {_item["id"] for _item in _selected})
        self.assertTrue(all(_item["genre"] == "판타지" and _item["status"] == "완결" for _item in _selected))

    def test_fresh_snapshot_does_not_start_background_collection(self):
        _snapshot = {"updatedAt": datetime.now(timezone.utc).isoformat(), "items": [_ITEM] * 101}
        with patch.object(_catalog_service, "_get_catalog", return_value=_snapshot), patch.object(_catalog_service, "_REFRESHING", False), patch.object(_catalog_service.threading, "Thread") as _thread:
            _catalog_service._start_refresh()
            _thread.assert_not_called()

    def test_stale_snapshot_starts_only_one_background_refresh(self):
        _snapshot = {"updatedAt": "2020-01-01T00:00:00+00:00", "items": [_ITEM] * 101}
        with patch.object(_catalog_service, "_get_catalog", return_value=_snapshot), patch.object(_catalog_service, "_REFRESHING", False), patch.object(_catalog_service.threading, "Thread") as _thread:
            _catalog_service._start_refresh()
            _catalog_service._start_refresh()
            _thread.assert_called_once()
            _thread.return_value.start.assert_called_once()


if __name__ == "__main__":
    unittest.main()
