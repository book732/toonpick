"""Calendar rollover, bounded queries and safe seasonal response handling."""

import copy
import io
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from services import anime_schedule as _schedule
from services.recommendations import _RecommendationError

_ITEM = {"id": 123, "title": {"native": "作品", "english": "Work"}, "synonyms": ["작품"], "seasonYear": 2027, "season": "WINTER", "startDate": {"year": 2027, "month": 1, "day": None}, "status": "NOT_YET_RELEASED", "format": "TV", "isAdult": False, "coverImage": {"large": "https://s4.anilist.co/file/cover.jpg"}}


def _response(_items, _more=False):
    return io.BytesIO(json.dumps({"data": {"Page": {"media": _items, "pageInfo": {"hasNextPage": _more}}}}).encode())


class _ScheduleTests(unittest.TestCase):
    def setUp(self):
        _schedule._fetch_schedule.cache_clear()

    def test_korean_new_year_and_quarter_boundaries(self):
        self.assertEqual(_schedule._schedule_period(datetime(2026, 12, 31, 14, 59, tzinfo=timezone.utc)), (2026, 4))
        self.assertEqual(_schedule._schedule_period(datetime(2026, 12, 31, 15, 0, tzinfo=timezone.utc)), (2027, 1))
        self.assertEqual(_schedule._schedule_period(datetime(2027, 3, 31, 15, 0, tzinfo=timezone.utc)), (2027, 2))

    def test_only_current_and_next_year_are_allowed_before_network(self):
        with patch.object(_schedule, "_schedule_period", return_value=(2027, 1)), patch.object(_schedule, "_fetch_schedule") as _fetch:
            for _params in ({"year": ["2026"]}, {"year": ["2029"]}, {"quarter": ["5"]}, {"page": ["0"]}, {"year": ["bad"]}):
                with self.subTest(params=_params), self.assertRaises(_RecommendationError) as _error:
                    _schedule._anime_schedule(_params)
                self.assertEqual(_error.exception.status, 400)
            _fetch.assert_not_called()

    def test_live_query_keeps_partial_dates_korean_names_and_hour_cache(self):
        with patch.object(_schedule.urllib.request, "urlopen", return_value=_response([_ITEM], True)) as _fetch, patch.object(_schedule, "_schedule_period", return_value=(2026, 4)), patch.object(_schedule.time, "time", return_value=3601):
            _data = _schedule._anime_schedule({"year": ["2027"], "quarter": ["1"]})
            _schedule._anime_schedule({"year": ["2027"], "quarter": ["1"]})
            _fetch.assert_called_once()
            self.assertEqual(json.loads(_fetch.call_args.args[0].data)["variables"], {"year": 2027, "season": "WINTER", "page": 1})
        self.assertEqual(_data["items"][0]["title"], "작품")
        self.assertIsNone(_data["items"][0]["startDate"]["day"])
        self.assertEqual(_data["items"][0]["url"], "https://anilist.co/anime/123")
        self.assertTrue(_data["hasNextPage"])

    def test_duplicates_adult_and_other_quarters_are_excluded_and_covers_are_safe(self):
        _unsafe = copy.deepcopy(_ITEM)
        _unsafe["coverImage"]["large"] = "https://evil.example/cover.jpg"
        with patch.object(_schedule.urllib.request, "urlopen", return_value=_response([_unsafe, _ITEM, {**_ITEM, "id": 124, "isAdult": True}, {**_ITEM, "id": 125, "season": "SUMMER"}])):
            _data = _schedule._fetch_schedule(2027, 1, 1, 1)
        self.assertEqual(len(_data["items"]), 1)
        self.assertEqual(_data["items"][0]["cover"], "/assets/cover-placeholder.svg")

    def test_unannounced_quarter_is_empty_and_outage_is_an_error(self):
        with patch.object(_schedule.urllib.request, "urlopen", return_value=_response([])):
            self.assertEqual(_schedule._fetch_schedule(2027, 4, 1, 1)["items"], [])
        with patch.object(_schedule.urllib.request, "urlopen", side_effect=OSError("provider unavailable")), self.assertRaises(_RecommendationError) as _error:
            _schedule._fetch_schedule(2027, 3, 1, 1)
        self.assertEqual(_error.exception.status, 502)

    def test_korean_names_take_priority_and_translations_keep_the_source_title(self):
        _untranslated = {**_ITEM, "synonyms": []}
        with patch.object(_schedule, "_schedule_aliases", return_value={}), patch.object(_schedule, "_schedule_translations", return_value={"123": "작품 번역"}), patch.object(_schedule.urllib.request, "urlopen", return_value=_response([_untranslated])):
            _item = _schedule._fetch_schedule(2027, 1, 1, 1)["items"][0]
        self.assertEqual(_item["title"], "작품 번역")
        self.assertEqual(_item["sourceTitle"], "作品")
        self.assertTrue(_item["translatedTitle"])
        self.assertFalse(_item["originalTitle"])
        _schedule._fetch_schedule.cache_clear()
        with patch.object(_schedule, "_schedule_aliases", return_value={"123": "한국 공식명"}), patch.object(_schedule, "_schedule_translations", return_value={"123": "작품 번역"}), patch.object(_schedule.urllib.request, "urlopen", return_value=_response([_untranslated])):
            _item = _schedule._fetch_schedule(2027, 1, 1, 1)["items"][0]
        self.assertEqual(_item["title"], "한국 공식명")
        self.assertFalse(_item["translatedTitle"])
