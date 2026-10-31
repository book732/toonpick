"""Board-game catalogue integrity and group constraints without external network calls."""

import json
import unittest
from urllib.parse import urlsplit
from unittest.mock import patch

from services import boardgames as _service
from services.recommendations import _RecommendationError
from scripts import collect_boardgames as _collector


class _BoardGameTests(unittest.TestCase):
    def test_required_games_are_present_as_original_base_games(self):
        _catalog = _service._boardgame_catalog()
        _items = {_item["slug"]: _item for _item in _catalog["items"]}
        _report = json.loads((_service._PATH.parent / 'boardgames_collection_report.json').read_text(encoding='utf-8'))
        self.assertEqual(len(_items), _report['finalCount'])
        self.assertGreater(len(_items), 300)
        self.assertEqual(_report['sourceProducts'], _report['expectedSourceProducts'])
        self.assertFalse(_report['failures'])
        self.assertTrue({"wingspan", "cascadia", "harmonies", "the-mind", "scout", "heat"} <= _items.keys())
        self.assertEqual(len(_items), len(_catalog["items"]))
        self.assertEqual(len({_item["id"] for _item in _items.values()}), len(_items))
        _imported = [_item for _item in _items.values() if _item['slug'].startswith('kbg-')]
        self.assertGreaterEqual(len({_item['cover'] for _item in _imported}), 260)
        self.assertEqual((_items["splendor"]["minPlayers"], _items["splendor"]["maxPlayers"], _items["splendor"]["maxMinutes"]), (2, 4, 30))
        self.assertIn("스플랜더", _items["splendor"]["aliases"])
        self.assertEqual((_items["the-game"]["minPlayers"], _items["the-game"]["maxPlayers"]), (1, 5))
        self.assertEqual(_items["the-game"]["mode"], "협력")
        self.assertTrue(_items["splendor"]["featured"] and _items["the-game"]["featured"])
        for _item in _items.values():
            _url = urlsplit(_item["url"])
            self.assertEqual(_url.scheme, "https")
            self.assertIn(_url.hostname, _service._HOSTS)
            self.assertTrue(_item["id"].startswith("boardgames:"))

    def test_validation_rejects_invalid_filters_and_boolean_numbers(self):
        for _payload in [{"players": True}, {"players": 13}, {"players": -1}, {"maxMinutes": 17}, {"difficulty": 4}, {"count": 0}, {"genres": ["판타지"]}, {"mood": "unknown"}]:
            with self.subTest(payload=_payload), self.assertRaises(_RecommendationError):
                _service._validate_boardgame(_payload)

    def test_player_time_and_difficulty_limits_are_enforced_together(self):
        _preferences = _service._validate_boardgame({"players": 2, "maxMinutes": 30, "difficulty": 2})
        _eligible = [_item for _item in _service._boardgame_catalog()["items"] if _service._eligible_boardgame(_item, _preferences)]
        _slugs = {_item["slug"] for _item in _eligible}
        self.assertIn("splendor", _slugs)
        self.assertIn("the-game", _slugs)
        self.assertNotIn("codenames", _slugs)
        self.assertNotIn("seven-wonders-duel", _slugs)
        self.assertNotIn("hanabi", _slugs)
        self.assertTrue(all(_item["maxMinutes"] <= 30 and _item["difficulty"] <= 2 for _item in _eligible))

    def test_solo_and_open_ended_team_counts_use_base_game_ranges(self):
        _catalog = _service._boardgame_catalog()["items"]
        _solo = [_item["slug"] for _item in _catalog if _service._eligible_boardgame(_item, _service._validate_boardgame({"players": 1}))]
        self.assertTrue({"the-game", "wingspan", "cascadia", "harmonies", "heat", "micromacro-crime-city"} <= set(_solo))
        self.assertTrue(all(_item['minPlayers'] <= 1 for _item in _catalog if _item['slug'] in _solo))
        _large = [_item["slug"] for _item in _catalog if _service._eligible_boardgame(_item, _service._validate_boardgame({"players": 12}))]
        self.assertTrue({"codenames", "codenames-duet"} <= set(_large))
        self.assertTrue(all(_item['maxPlayers'] is None or _item['maxPlayers'] >= 12 for _item in _catalog if _item['slug'] in _large))

    def test_ai_only_receives_eligible_games_and_can_return_fewer_when_pool_is_small(self):
        _game = next(_item for _item in _service._boardgame_catalog()["items"] if _item["slug"] == "the-game")
        _response = {"summary": "혼자 도전할 수 있어요.", "recommendations": [{"id": _game["id"], "reason": "1인 규칙을 지원하는 숫자 카드 게임이에요."}]}
        with patch.object(_service, "_request_recommendations", return_value=(_response, "test")) as _request:
            _result = _service._recommend_boardgames({"players": 1, "maxMinutes": 20, "difficulty": 1, "count": 6})
        self.assertEqual(_request.call_args.args[0]["count"], 1)
        self.assertEqual(_request.call_args.args[0]["_contentType"], "boardgame")
        self.assertEqual([_item["slug"] for _item in _request.call_args.args[1]], ["the-game"])
        self.assertEqual(_result["data"]["retrieval"]["requestedCount"], 6)
        self.assertEqual(len(_result["data"]["items"]), 1)
        self.assertNotIn("quota", _result["data"]["retrieval"])

    def test_impossible_conditions_skip_ai_and_model_cannot_override_player_count(self):
        with patch.object(_service, "_request_recommendations") as _request:
            _result = _service._recommend_boardgames({"players": 1, "genres": ["파티"], "difficulty": 3})
        self.assertEqual(_result["data"]["source"], "filters")
        _request.assert_not_called()
        _game = next(_item for _item in _service._boardgame_catalog()["items"] if _item["slug"] == "splendor")
        with patch.object(_service, "_request_recommendations", return_value=({"summary": "잘못된 추천", "recommendations": [{"id": _game["id"], "reason": "테스트"}]}, "test")):
            with self.assertRaises(_RecommendationError):
                _service._recommend_boardgames({"players": 1})

    def test_unknown_difficulty_is_not_treated_as_easy(self):
        _catalog = _service._boardgame_catalog()['items']
        _unknown = [_item for _item in _catalog if not _item['difficulty']]
        self.assertGreaterEqual(len(_unknown), 270)
        self.assertTrue(all(_item['difficultyLabel'] == '정보 없음' for _item in _unknown))
        self.assertTrue(all(not _service._eligible_boardgame(_item, _service._validate_boardgame({'difficulty': 3})) for _item in _unknown))

    def test_large_pool_is_bounded_before_ai_and_keeps_requested_count(self):
        def _request(_preferences, _candidates):
            self.assertEqual(len(_candidates), 90)
            self.assertEqual(len({_item['id'] for _item in _candidates}), 90)
            return {'summary': '조건에 맞는 게임입니다.', 'recommendations': [{'id': _item['id'], 'reason': '공식 플레이 조건에 맞습니다.'} for _item in _candidates[:6]]}, 'test'
        with patch.object(_service, '_request_recommendations', side_effect=_request):
            _result = _service._recommend_boardgames({'count': 6})
        self.assertEqual(_result['data']['retrieval']['catalogCount'], len(_service._boardgame_catalog()['items']))
        self.assertEqual(len(_result['data']['items']), 6)

    def test_catalogue_has_no_repeated_provider_ids_or_canonical_titles(self):
        _items = _service._boardgame_catalog()['items']
        _ids = [_item['bggId'] for _item in _items if _item.get('bggId')]
        self.assertEqual(len(_ids), len(set(_ids)))
        _names = [_collector._canonical_title(_item['title']) for _item in _items]
        self.assertEqual(len(_names), len(set(_names)))
        self.assertTrue(all(not _collector._excluded_title(_item['title']) for _item in _items))

    def test_packaging_variants_collapse_but_distinct_games_stay_separate(self):
        for _left, _right in [('레지스탕스 아발론 빅 박스', '아발론 클래식'), ('스플랜더', '스플렌더'), ('루미큐브 클래식', '루미큐브 트래블'), ('[예약판매] 카탄 개정판', '카탄')]:
            self.assertEqual(_collector._canonical_title(_left), _collector._canonical_title(_right))
        self.assertNotEqual(_collector._canonical_title('스플렌더'), _collector._canonical_title('스플렌더 듀얼'))
        self.assertNotEqual(_collector._canonical_title('코드네임'), _collector._canonical_title('코드네임 듀엣'))

    def test_accessories_are_rejected_without_excluding_real_dice_or_puzzle_games(self):
        for _title in ['브금 카드 홀더', '보드게임 주사위 트레이', '아크 노바 확장: 마린 월드', '보호 슬리브', '보관 박스', '직소 퍼즐 1000피스', '네메시스 락다운 스트레치 골', '디센트 용인 백부장 미니어처 세트', '아컴호러 카드 독립: 한탕과 허탕', '[세트] 스플렌더 + 딕싯']:
            self.assertTrue(_collector._excluded_title(_title), _title)
        for _title in ['다이스 챌린저', '러시아워', '우봉고', '퍼즐 게임', '더 게임', '아컴호러 카드게임 개정판', '독립 확장 게임']:
            self.assertFalse(_collector._excluded_title(_title), _title)

    def test_unknown_player_counts_never_satisfy_a_player_limit(self):
        _item = next(_item for _item in _service._boardgame_catalog()['items'] if _item['minPlayers'] is None)
        self.assertEqual(_item['playersLabel'], '인원 정보 확인 필요')
        self.assertFalse(_service._eligible_boardgame(_item, _service._validate_boardgame({'players': 2})))
        self.assertTrue(_service._eligible_boardgame(_item, _service._validate_boardgame({})))

    def test_licensed_packaging_variants_do_not_replace_distinct_rule_sets(self):
        for _title in ['루미큐브 퍼니백', '루미큐브 인피니티', '루미큐브 셀렉트 빈티지']:
            self.assertEqual(_collector._canonical_title(_title), _collector._canonical_title('루미큐브 클래식'))
        self.assertEqual(_collector._canonical_title('할리갈리 포켓몬'), _collector._canonical_title('할리갈리'))
        self.assertNotEqual(_collector._canonical_title('루미큐브 워드'), _collector._canonical_title('루미큐브'))
        self.assertNotEqual(_collector._canonical_title('우노 플립'), _collector._canonical_title('우노'))

    def test_category_parser_uses_product_entries_and_actual_pagination(self):
        _html = '<input name="totalPageCnt" value="30"><a href="/product/detail?prdCd=PD2026000001ABCD"><div class="item_title">다이스 &amp; 카드</div></a><a href="/magazine">다른 링크</a>'
        self.assertEqual(_collector._page_count(_html), 30)
        self.assertEqual(_collector._products(_html), [('PD2026000001ABCD', '다이스 & 카드')])
        for _invalid in ['', '<input name="totalPageCnt" value="0">', '<input name="totalPageCnt" value="100000">']:
            with self.assertRaises(ValueError):
                _collector._page_count(_invalid)


if __name__ == "__main__":
    unittest.main()
