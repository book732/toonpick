"""Domestic source integrity, complete search, pagination and grounded recommendations."""

import io
import json
import unittest
from urllib.parse import urlsplit
from unittest.mock import patch

from services import anime as _anime
from services.recommendations import _RecommendationError


class _AnimeTests(unittest.TestCase):
    def test_full_domestic_snapshot_has_unique_source_ids_and_trusted_links(self):
        _data = _anime._read_anime(_anime._PATH.stat().st_mtime_ns)
        self.assertGreaterEqual(len(_data["items"]), 9500)
        self.assertEqual(len(_data["items"]), len({_item["id"] for _item in _data["items"]}))
        self.assertEqual({_p["key"] for _p in _data["platforms"]}, {"laftel", "netflix"})
        for _item in _data["items"]:
            _provider = next(_p for _p in _data["platforms"] if _p["key"] == _item["platformKey"])
            self.assertIn(urlsplit(_item["url"]).hostname, _provider["workHosts"])
            self.assertTrue(_item["id"].startswith(_provider["key"] + ":"))
            self.assertNotIn("anilist.co", _item["url"])

    def test_pagination_exposes_the_entire_collection_without_repeating_ids(self):
        _first = _anime._anime_catalog({})
        self.assertEqual(len(_first["items"]), 120)
        self.assertEqual({_i["platformKey"] for _i in _first["items"]}, {"laftel", "netflix"})
        _ids = []
        for _page in range(1, (_first["matchedCount"] + 119) // 120 + 1):
            _result = _anime._anime_catalog({"page": [str(_page)]})
            _ids.extend(_i["id"] for _i in _result["items"])
        self.assertFalse(_result["pagination"]["hasNextPage"])
        self.assertEqual(len(_ids), _first["matchedCount"])
        self.assertEqual(len(_ids), len(set(_ids)))
        self.assertTrue(all("_searchText" not in _i for _i in _first["items"]))

    def test_duplicate_service_entries_collapse_before_pagination_but_keep_seasons(self):
        _title = "터무니없는 스킬로 이세계 방랑 밥"
        _result = _anime._anime_catalog({"query": [_title]})
        self.assertEqual(sum(_item["title"] == _title for _item in _result["items"]), 1)
        _work = next(_item for _item in _result["items"] if _item["title"] == _title)
        self.assertEqual([_source["platformKey"] for _source in _work["sources"]], ["laftel", "netflix"])
        self.assertTrue(_work["sources"][0]["url"].startswith("https://laftel.net/item/"))
        self.assertTrue(_work["sources"][1]["url"].startswith("https://www.netflix.com/kr/title/"))
        self.assertTrue(any(_item["title"] == _title + " 2" for _item in _result["items"]))
        for _platform in ("laftel", "netflix"):
            _filtered = _anime._anime_catalog({"query": [_title], "platform": [_platform]})
            self.assertEqual(sum(_item["title"] == _title for _item in _filtered["items"]), 1)
            self.assertTrue(all(_item["platformKey"] == _platform for _item in _filtered["items"]))
            self.assertEqual(next(_item for _item in _filtered["items"] if _item["title"] == _title)["sources"], _work["sources"])

    def test_discovery_pages_have_unique_work_keys_and_preserve_raw_source_count(self):
        _first = _anime._anime_catalog({})
        _keys = []
        for _page in range(1, (_first["matchedCount"] + 119) // 120 + 1):
            _result = _anime._anime_catalog({"page": [str(_page)]})
            _keys.extend((_anime._normalize(_item["title"]), _item["format"]) for _item in _result["items"])
        self.assertEqual(len(_keys), len(set(_keys)))
        self.assertEqual(len(_keys), _first["matchedCount"])
        self.assertEqual(_first["catalogCount"], 9869)

    def test_korean_search_reaches_works_beyond_the_initial_page(self):
        _data = _anime._read_anime(_anime._PATH.stat().st_mtime_ns)
        _work = _data["items"][-304]
        _result = _anime._anime_catalog({"query": [_work["title"]]})
        self.assertIn(_work["id"], {_i["id"] for _i in _result["items"]})
        self.assertLess(_result["matchedCount"], _result["catalogCount"])

    def test_platform_format_status_and_genre_filters_are_combined(self):
        _result = _anime._anime_catalog({"platform": ["laftel"], "genre": ["액션", "판타지"], "format": ["TV"], "status": ["완결"]})
        self.assertTrue(_result["items"])
        self.assertTrue(all(_i["platformKey"] == "laftel" and _i["format"] == "TV" and _i["status"] == "완결" and set(_i["genres"]) & {"액션", "판타지"} for _i in _result["items"]))
        _result = _anime._anime_catalog({"platform": ["netflix"]})
        self.assertEqual(_result["matchedCount"], 303)
        self.assertTrue(all(_i["platformKey"] == "netflix" for _i in _result["items"]))

    def test_mood_filter_is_applied_before_pagination_and_banners_sample_both_services(self):
        _result = _anime._anime_catalog({"mood": ["힐링"]})
        self.assertTrue(_result["items"])
        self.assertTrue(all("힐링" in _i["tags"] for _i in _result["items"]))
        self.assertEqual(len(_result["heroItems"]), 60)
        self.assertEqual({_i["platformKey"] for _i in _result["heroItems"]}, {"laftel", "netflix"})

    def test_validation_rejects_unknown_values_and_bad_pages(self):
        for _payload in [{"formats": ["MANGA"]}, {"genres": ["unknown"]}, {"count": True}, {"count": 19}, {"query": "x" * 101}, {"status": "unknown"}, {"platforms": ["anilist"]}]:
            with self.subTest(payload=_payload), self.assertRaises(_RecommendationError):
                _anime._validate_anime(_payload)
        for _page in ["0", "1001", "bad"]:
            with self.assertRaises(_RecommendationError):
                _anime._anime_catalog({"page": [_page]})

    def test_related_seasons_dubs_and_platform_duplicates_share_a_family(self):
        self.assertEqual(_anime._family({"title": "(더빙) 나의 히어로 아카데미아 2기"}), _anime._family({"title": "나의 히어로 아카데미아 1기"}))

    def test_ai_filters_the_full_snapshot_and_receives_bounded_unique_franchises(self):
        def _request(_preferences, _candidates):
            self.assertEqual(len(_candidates), 60)
            self.assertEqual(len({_i["franchiseKey"] for _i in _candidates}), 60)
            self.assertEqual({_i["platformKey"] for _i in _candidates}, {"laftel", "netflix"})
            self.assertTrue(all(_i.get("available", _i["platformKey"] == "netflix") for _i in _candidates))
            return {"summary": "취향에 맞는 작품입니다.", "recommendations": [{"id": _i["id"], "reason": "공식 작품 정보에 맞춰 추천합니다."} for _i in _candidates[:_preferences["count"]]]}, "test"
        with patch.object(_anime, "_request_recommendations", side_effect=_request):
            _result = _anime._recommend_anime({"count": 6})
        self.assertEqual(_result["data"]["retrieval"]["catalogCount"], 9869)
        self.assertEqual(len(_result["data"]["items"]), 6)

    def test_empty_search_skips_ai_and_unknown_detail_ids_never_fetch(self):
        with patch.object(_anime, "_request_recommendations") as _request:
            _result = _anime._recommend_anime({"query": "zzzzzz-no-such-title-92345"})
        self.assertEqual(_result["data"]["source"], "filters")
        _request.assert_not_called()
        with patch("urllib.request.urlopen") as _fetch, self.assertRaises(_RecommendationError):
            _anime._anime_detail("https://evil.example", 1)
        _fetch.assert_not_called()

    def test_selected_detail_is_cached_and_keeps_the_verified_source_identity(self):
        _item = _anime._anime_catalog({"platform": ["laftel"]})["items"][0]
        _response = {"id": int(_item["url"].rsplit("/", 1)[-1]), "content": "공식 줄거리", "production": "공식 제작사"}
        _anime._anime_detail.cache_clear()
        with patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(_response).encode())) as _fetch:
            _detail = _anime._anime_detail(_item["id"], 123)
            _anime._anime_detail(_item["id"], 123)
        _fetch.assert_called_once()
        self.assertEqual(_detail["url"], _item["url"])
        self.assertEqual(_detail["description"], "공식 줄거리")
        _anime._anime_detail.cache_clear()
