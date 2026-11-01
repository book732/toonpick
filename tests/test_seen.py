"""Seen works are removed before model candidate selection, including service variants."""

import unittest
from unittest.mock import patch

from services import recommendations as _webtoon, anime as _anime, boardgames as _boardgames


class _SeenTests(unittest.TestCase):
    def test_invalid_and_oversized_exclusions_are_rejected_by_every_type(self):
        for _validator in (_webtoon._validate_inputs, _anime._validate_anime, _boardgames._validate_boardgame):
            for _ids in (None, "1", [{}], ["bad"], ["1"] * 20001):
                with self.subTest(_validator=_validator.__name__, _ids=type(_ids).__name__):
                    with self.assertRaises(_webtoon._RecommendationError) as _error:
                        _validator({"genres": [], "mood": "전체", "status": "전체", "excludedIds": _ids})
                    self.assertEqual(_error.exception.status, 400)

    def test_webtoon_filters_other_platform_editions_and_rejects_excluded_model_output(self):
        _original = _webtoon._load_catalog()["items"][0]
        _duplicate = {**_original, "id": "kakao:" + "a" * 20, "title": _original["title"] + " (개정판)"}
        _other = {**_original, "id": "123456789", "title": "새로운 작품"}
        _preferences = {"genres": [], "mood": "전체", "status": "전체", "count": 1, "excludedIds": [_original["id"]]}
        with patch.object(_webtoon, "_load_catalog", return_value={"items": [_original, _other], "updatedAt": "2026-11-01"}), patch.object(_webtoon, "_search_web", return_value=([_duplicate], {})):
            with patch.object(_webtoon, "_request_recommendations", return_value=({"summary": "추천", "recommendations": [{"id": _other["id"], "reason": "새 작품"}]}, "test")) as _request:
                _result = _webtoon._recommend(_preferences)
                self.assertEqual([_item["id"] for _item in _request.call_args.args[1]], [_other["id"]])
                self.assertEqual(_result["data"]["items"][0]["id"], _other["id"])
            with patch.object(_webtoon, "_request_recommendations", return_value=({"summary": "추천", "recommendations": [{"id": _original["id"], "reason": "무시"}]}, "test")):
                with self.assertRaises(_webtoon._RecommendationError):
                    _webtoon._recommend(_preferences)

    def test_anime_excludes_other_service_and_dubbing_but_preserves_next_season(self):
        _raw = _anime._read_anime(_anime._PATH.stat().st_mtime_ns)["items"]
        _title = "나의 히어로 아카데미아"
        _original = next(_item for _item in _raw if _item["title"] == _title)
        _preferences = {"count": 1, "query": _title, "excludedIds": [_original["id"]]}
        with patch.object(_anime, "_request_recommendations", return_value=({"summary": "추천", "recommendations": []}, "test")) as _request:
            _anime._recommend_anime(_preferences)
            _candidates = _request.call_args.args[1]
            self.assertTrue(_candidates)
            _blocked = {_item["id"] for _item in _raw if _item["_workKey"] == _original["_workKey"]}
            self.assertTrue(all(_item["id"] not in _blocked for _item in _candidates))
            self.assertTrue(any("2" in _item["title"] for _item in _candidates))

    def test_boardgame_exclusion_and_all_seen_empty_result_do_not_call_model(self):
        _catalog = _boardgames._boardgame_catalog()
        with patch.object(_boardgames, "_request_recommendations", return_value=({"summary": "추천", "recommendations": []}, "test")) as _request:
            _boardgames._recommend_boardgames({"excludedIds": [_catalog["items"][0]["id"]]})
            self.assertTrue(all(_item["id"] != _catalog["items"][0]["id"] for _item in _request.call_args.args[1]))
            _request.reset_mock()
            _result = _boardgames._recommend_boardgames({"excludedIds": [_item["id"] for _item in _catalog["items"]]})
            self.assertEqual(_result["data"]["items"], [])
            _request.assert_not_called()
