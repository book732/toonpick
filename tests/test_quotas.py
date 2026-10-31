"""Enforce group allocation, shortage redistribution and cross-platform story identity."""

import unittest
from unittest.mock import patch

from services.catalog import _select_candidates, _story_key
from services.platforms import _platform_group
from services.recommendations import _quota_plan, _recommend, _RecommendationError


_PREFERENCES = {"genres": [], "mood": "전체", "status": "전체", "notes": "", "platforms": []}


def _item(_key, _index, _title=None):
    return {"id": _key + str(_index), "platformKey": _key, "title": _title or _key + str(_index), "platform": _key, "genre": "판타지", "status": "연재", "tags": [], "description": "", "favorites": 100 - _index}


class _QuotaTests(unittest.TestCase):
    def test_naver_and_kakao_brands_share_their_group_quota(self):
        self.assertEqual([_platform_group(_item(_key, 1)) for _key in ["naver", "naverseries", "kakaopage", "kakaowebtoon", "ridi"]], ["naver", "naver", "kakao", "kakao", "other"])

    def test_default_allocation_is_two_per_group_with_two_other_platforms(self):
        _items = [_item(_key, _index) for _key in ["naver", "kakaopage", "lezhin", "ridi"] for _index in range(8)]
        self.assertEqual(_quota_plan(_items), {"groups": {"naver": 2, "kakao": 2, "other": 2}, "otherPlatformMinimum": 2})

    def test_requested_counts_scale_allocation_without_exceeding_capacity(self):
        _items = [_item(_key, _index) for _key in ["naver", "kakaopage", "lezhin", "ridi", "bomtoon", "mrblue", "bookcube", "mootoon"] for _index in range(20)]
        for _count in range(1, 19):
            _allocation = _quota_plan(_items, _count)
            self.assertEqual(sum(_allocation["groups"].values()), _count)
            self.assertLessEqual(max(_allocation["groups"].values()) - min(_allocation["groups"].values()), 1)
        self.assertEqual(_quota_plan(_items, 18), {"groups": {"naver": 6, "kakao": 6, "other": 6}, "otherPlatformMinimum": 6})

    def test_missing_group_slots_are_redistributed_and_small_pools_are_not_inflated(self):
        _items = [_item("naver", 1)] + [_item("kakaopage", _index) for _index in range(8)]
        self.assertEqual(_quota_plan(_items)["groups"], {"naver": 1, "kakao": 5, "other": 0})
        self.assertEqual(_quota_plan(_items[:2])["groups"], {"naver": 1, "kakao": 1, "other": 0})
        self.assertEqual(sum(_quota_plan([])["groups"].values()), 0)

    def test_explicit_single_platform_selection_remains_valid(self):
        _items = [_item("ridi", _index) for _index in range(10)]
        self.assertEqual(_quota_plan(_items), {"groups": {"naver": 0, "kakao": 0, "other": 6}, "otherPlatformMinimum": 1})

    def test_same_story_is_removed_before_capacity_calculation_without_losing_seasons(self):
        _items = [_item("naver", 1, "같은 작품"), _item("kakaopage", 1, "같은작품 [개정판]"), _item("ridi", 1, "같은 작품 시즌2")]
        self.assertEqual(_story_key(_items[0]), _story_key(_items[1]))
        self.assertNotEqual(_story_key(_items[0]), _story_key(_items[2]))
        _selected = _select_candidates(_PREFERENCES, {"items": _items}, [])
        self.assertEqual(len(_selected), 2)
        self.assertEqual(sum(_quota_plan(_selected)["groups"].values()), 2)

    def test_group_quota_and_other_platform_minimum_are_enforced_on_model_output(self):
        _items = [_item(_key, _index) for _key in ["naver", "kakaopage", "lezhin", "ridi"] for _index in range(6)]
        _cases = [
            ([_items[0], _items[1], _items[6], _items[7], _items[12], _items[18]], True),
            (_items[:6], False),
            ([_items[0], _items[1], _items[6], _items[7], _items[12], _items[13]], False),
            ([_items[0], _items[6]], False),
        ]
        for _selected, _valid in _cases:
            _result = {"summary": "추천 결과", "recommendations": [{"id": _entry["id"], "reason": "취향에 맞는 작품입니다."} for _entry in _selected]}
            with self.subTest(valid=_valid, ids=[_entry["id"] for _entry in _selected]), patch("services.recommendations._load_catalog", return_value={"items": _items, "updatedAt": "2026-10-31T00:00:00Z"}), patch("services.recommendations._search_web", return_value=([], {})), patch("services.recommendations._request_recommendations", return_value=(_result, "test")):
                if _valid:
                    _data = _recommend(_PREFERENCES)["data"]
                    self.assertEqual(_data["retrieval"]["quota"]["actual"], {"naver": 2, "kakao": 2, "other": 2})
                else:
                    with self.assertRaises(_RecommendationError):
                        _recommend(_PREFERENCES)

    def test_genre_status_and_selected_platforms_take_priority_over_quota(self):
        _items = [_item(_key, _index) for _key in ["naver", "kakaopage", "ridi"] for _index in range(8)]
        _selected = _select_candidates({**_PREFERENCES, "genres": ["판타지"], "status": "연재", "platforms": ["ridi"]}, {"items": _items}, [])
        self.assertTrue(all(_entry["platformKey"] == "ridi" and _entry["status"] == "연재" and _entry["genre"] == "판타지" for _entry in _selected))
        self.assertEqual(_quota_plan(_selected)["groups"], {"naver": 0, "kakao": 0, "other": 6})


if __name__ == "__main__":
    unittest.main()
