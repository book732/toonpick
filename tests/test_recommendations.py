"""Regression coverage for grounded AI recommendations and the HTTP entrypoint."""

import io
import http.client
import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from dev_server import CombinedDevHandler
from services.recommendations import _RecommendationError, _load_catalog, _recommend, _validate_inputs


_ENV = {"AI_API_KEY": "test-secret-placeholder", "AI_MODEL": "gpt-5.5", "AI_API_BASE_URL": "https://gateway.example/v1"}
_PREFERENCES = {"genres": [], "mood": "전체", "status": "전체", "notes": "성장하는 주인공"}
_FIXTURE = {**_load_catalog(), "items": _load_catalog()["items"][:14]}
_ITEM = _FIXTURE["items"][0]


def _completion(_entries=None, _summary="당신을 위한 추천입니다."):
    _content = {"summary": _summary, "recommendations": _entries if _entries is not None else [{"id": _item["id"], "reason": "세계관을 알아가는 주인공의 성장이 취향에 맞아요."} for _item in _FIXTURE["items"][:6]]}
    return io.BytesIO(json.dumps({"choices": [{"message": {"content": json.dumps(_content, ensure_ascii=False)}}]}).encode("utf-8"))


class _RecommendationTests(unittest.TestCase):
    def setUp(self):
        _catalog_patch = patch("services.recommendations._load_catalog", return_value=_FIXTURE)
        _search_patch = patch("services.recommendations._search_web", return_value=([], {"status": "ok", "matched": 0, "queries": [], "urls": [], "newTitles": 0}))
        _catalog_patch.start()
        _search_patch.start()
        self.addCleanup(_catalog_patch.stop)
        self.addCleanup(_search_patch.stop)
    def test_existing_environment_and_proxy_request_format(self):
        with patch.dict(os.environ, _ENV), patch("urllib.request.urlopen", return_value=_completion()) as _request:
            _result = _recommend(_PREFERENCES)
        _call = _request.call_args.args[0]
        _body = json.loads(_call.data)
        self.assertEqual(_call.full_url, "https://gateway.example/v1/chat/completions")
        self.assertEqual(_call.get_header("Authorization"), "Bearer test-secret-placeholder")
        self.assertEqual(_body["model"], "gpt-5.5")
        self.assertIn("max_completion_tokens", _body)
        self.assertNotIn("response_format", _body)
        self.assertNotIn("temperature", _body)
        self.assertNotIn(_ENV["AI_API_KEY"], _body["messages"][1]["content"])
        _prompt = json.loads(_body["messages"][1]["content"])
        self.assertEqual(_prompt["allocation"]["groups"], {"naver": 6, "kakao": 0, "other": 0})
        self.assertTrue(all(_entry["platformGroup"] == "naver" for _entry in _prompt["catalogue"]))
        self.assertEqual(_result["data"]["source"], "ai")
        self.assertEqual(_result["data"]["items"][0]["url"], _ITEM["url"])

    def test_mood_is_judged_by_ai_instead_of_literal_tags(self):
        _payload = {**_PREFERENCES, "genres": ["판타지"], "mood": "힐링"}
        self.assertNotIn("힐링", _ITEM["tags"])
        _entries = [{"id": _item["id"], "reason": "성장하는 이야기가 취향에 맞아요."} for _item in _FIXTURE["items"] if _item["genre"] == "판타지"][:6]
        with patch.dict(os.environ, _ENV), patch("urllib.request.urlopen", return_value=_completion(_entries)):
            self.assertEqual(_recommend(_payload)["data"]["items"][0]["id"], _ITEM["id"])

    def test_genre_and_status_are_enforced_before_the_model(self):
        with patch.dict(os.environ, _ENV), patch("urllib.request.urlopen", return_value=_completion([])) as _request:
            _recommend({**_PREFERENCES, "genres": ["로맨스", "일상"], "status": "완결"})
        _catalogue = json.loads(json.loads(_request.call_args.args[0].data)["messages"][1]["content"])["catalogue"]
        _eligible = {_item["id"] for _item in _FIXTURE["items"] if _item["genre"] in {"로맨스", "일상"} and _item["status"] == "완결"}
        self.assertEqual({_entry["id"] for _entry in _catalogue}, _eligible)

    def test_empty_candidates_do_not_spend_an_api_request(self):
        with patch("urllib.request.urlopen") as _request:
            _result = _recommend({**_PREFERENCES, "genres": ["스포츠"], "status": "휴재"})
        self.assertEqual(_result["data"]["items"], [])
        self.assertEqual(_result["data"]["source"], "filters")
        _request.assert_not_called()

    def test_invalid_inputs_never_reach_the_provider(self):
        for _payload in [None, [], {**_PREFERENCES, "genres": "판타지"}, {**_PREFERENCES, "genres": [{}]}, {**_PREFERENCES, "mood": []}, {**_PREFERENCES, "status": 1}, {**_PREFERENCES, "notes": "x" * 601}]:
            with self.subTest(payload=_payload), patch("urllib.request.urlopen") as _request:
                with self.assertRaises(_RecommendationError) as _error:
                    _recommend(_payload)
                self.assertEqual(_error.exception.status, 400)
                _request.assert_not_called()

    def test_count_defaults_to_six_and_rejects_invalid_numbers(self):
        self.assertEqual(_validate_inputs(_PREFERENCES)["count"], 6)
        for _count in [1, 6, 12, 18]:
            self.assertEqual(_validate_inputs({**_PREFERENCES, "count": _count})["count"], _count)
        for _count in [0, 19, -1, 1.5, True, "6", None]:
            with self.subTest(count=_count), self.assertRaises(_RecommendationError):
                _validate_inputs({**_PREFERENCES, "count": _count})

    def test_requested_count_is_sent_to_provider_and_enforced_on_response(self):
        _entries = [{"id": _item["id"], "reason": "성장하는 이야기가 취향에 맞아요."} for _item in _FIXTURE["items"][:12]]
        with patch.dict(os.environ, _ENV), patch("urllib.request.urlopen", return_value=_completion(_entries)) as _request:
            _result = _recommend({**_PREFERENCES, "count": 12})
        self.assertEqual(len(_result["data"]["items"]), 12)
        self.assertEqual(_result["data"]["retrieval"]["requestedCount"], 12)
        _body = json.loads(_request.call_args.args[0].data)
        self.assertGreater(_body["max_completion_tokens"], 4096)
        self.assertEqual(json.loads(_body["messages"][1]["content"])["allocation"]["groups"]["naver"], 12)
        with patch.dict(os.environ, _ENV), patch("urllib.request.urlopen", return_value=_completion(_entries)):
            with self.assertRaises(_RecommendationError):
                _recommend({**_PREFERENCES, "count": 3})

    def test_missing_credentials_report_configuration_failure(self):
        with patch.dict(os.environ, {"AI_API_KEY": ""}), self.assertRaises(_RecommendationError) as _error:
            _recommend(_PREFERENCES)
        self.assertEqual(_error.exception.status, 503)

    def test_unknown_duplicate_and_malformed_recommendations_are_rejected(self):
        _valid = {"id": _ITEM["id"], "reason": "성장하는 이야기가 취향에 맞아요."}
        for _entries in [[{"id": "unknown", "reason": "test"}], [_valid, _valid], [{"id": _ITEM["id"], "reason": ""}], [{"id": [], "reason": "test"}], [None], [_valid] * 7]:
            with self.subTest(entries=_entries), patch.dict(os.environ, _ENV), patch("urllib.request.urlopen", return_value=_completion(_entries)):
                with self.assertRaises(_RecommendationError):
                    _recommend(_PREFERENCES)

    def test_provider_cannot_return_a_title_outside_the_requested_genre(self):
        with patch.dict(os.environ, _ENV), patch("urllib.request.urlopen", return_value=_completion()):
            with self.assertRaises(_RecommendationError):
                _recommend({**_PREFERENCES, "genres": ["로맨스"]})

    def test_upstream_errors_never_expose_provider_details_or_keys(self):
        for _code, _expected in [(401, 502), (403, 502), (429, 429), (500, 502)]:
            _upstream = urllib.error.HTTPError("https://gateway.example", _code, "error", {}, io.BytesIO(b"test-secret-placeholder"))
            with self.subTest(code=_code), patch.dict(os.environ, _ENV), patch("urllib.request.urlopen", side_effect=_upstream):
                with self.assertRaises(_RecommendationError) as _error:
                    _recommend(_PREFERENCES)
                self.assertEqual(_error.exception.status, _expected)
                self.assertNotIn("test-secret-placeholder", str(_error.exception))

    def test_timeout_and_invalid_json_are_controlled_errors(self):
        for _failure, _expected in [(TimeoutError(), 504), (urllib.error.URLError("offline"), 502)]:
            with patch.dict(os.environ, _ENV), patch("urllib.request.urlopen", side_effect=_failure):
                with self.assertRaises(_RecommendationError) as _error:
                    _recommend(_PREFERENCES)
                self.assertEqual(_error.exception.status, _expected)
        with patch.dict(os.environ, _ENV), patch("urllib.request.urlopen", return_value=io.BytesIO(b"not json")):
            with self.assertRaises(_RecommendationError):
                _recommend(_PREFERENCES)


class _QuietHandler(CombinedDevHandler):
    def log_message(self, *_args):
        pass


class _HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._server = ThreadingHTTPServer(("127.0.0.1", 0), _QuietHandler)
        cls._thread = threading.Thread(target=cls._server.serve_forever, daemon=True)
        cls._thread.start()
        cls._url = "http://127.0.0.1:" + str(cls._server.server_port) + "/api/generate"

    @classmethod
    def tearDownClass(cls):
        cls._server.shutdown()
        cls._server.server_close()
        cls._thread.join()

    def test_webtoon_request_is_dispatched_through_existing_endpoint(self):
        _request = urllib.request.Request(self._url, data=json.dumps({"type": "webtoon", **_PREFERENCES}).encode("utf-8"), headers={"Content-Type": "application/json"})
        with patch("api.generate._recommend", return_value={"success": True, "data": {"items": []}}) as _recommendation:
            with urllib.request.urlopen(_request) as _response:
                self.assertTrue(json.load(_response)["success"])
            self.assertEqual(_recommendation.call_args.args[0]["type"], "webtoon")

    def test_live_catalogue_uses_the_same_server_entrypoint(self):
        with patch("api.generate._catalog_response", return_value={"items": [], "refreshing": False}):
            with urllib.request.urlopen(self._url + "?resource=catalog") as _response:
                self.assertEqual(json.load(_response), {"items": [], "refreshing": False})

    def test_anime_catalogue_and_ai_requests_use_separate_dispatch(self):
        with patch("api.generate._anime_catalog", return_value={"items": [], "contentType": "anime"}) as _catalog:
            with urllib.request.urlopen(self._url + "?resource=anime_catalog&format=TV") as _response:
                self.assertEqual(json.load(_response)["contentType"], "anime")
            self.assertEqual(_catalog.call_args.args[0]["format"], ["TV"])
        _request = urllib.request.Request(self._url, data=json.dumps({"type": "anime", "count": 6}).encode())
        with patch("api.generate._recommend_anime", return_value={"success": True, "data": {"items": []}}) as _recommendation:
            with urllib.request.urlopen(_request) as _response:
                self.assertTrue(json.load(_response)["success"])
            self.assertEqual(_recommendation.call_args.args[0]["type"], "anime")

    def test_anime_schedule_dispatch_caches_success_and_never_caches_errors(self):
        with patch("api.generate._anime_schedule", return_value={"items": [], "year": 2027}) as _schedule:
            with urllib.request.urlopen(self._url + "?resource=anime_schedule&year=2027&quarter=2") as _response:
                self.assertEqual(json.load(_response)["year"], 2027)
                self.assertIn("s-maxage=3600", _response.headers["Cache-Control"])
            self.assertEqual(_schedule.call_args.args[0]["quarter"], ["2"])
        with patch("api.generate._anime_schedule", side_effect=_RecommendationError("일정 조회 지연", 502)):
            with self.assertRaises(urllib.error.HTTPError) as _error:
                urllib.request.urlopen(self._url + "?resource=anime_schedule")
            self.assertEqual(_error.exception.code, 502)
            self.assertEqual(_error.exception.headers["Cache-Control"], "no-store")
            _error.exception.close()

    def test_vercel_catalogue_redirects_to_static_snapshot_without_collection(self):
        with patch.dict(os.environ, {"VERCEL": "1"}), patch("api.generate._catalog_response") as _catalog, patch.object(urllib.request.HTTPRedirectHandler, "redirect_request", return_value=None):
            with self.assertRaises(urllib.error.HTTPError) as _error:
                urllib.request.urlopen(self._url + "?resource=catalog")
        self.assertEqual(_error.exception.code, 307)
        self.assertEqual(_error.exception.headers["Location"], "/data/webtoons.json")
        self.assertEqual(_error.exception.read(), b"")
        _error.exception.close()
        _catalog.assert_not_called()

    def test_boardgame_catalogue_and_ai_use_existing_endpoint_with_own_dispatch(self):
        with patch("api.generate._boardgame_catalog", return_value={"items": [], "contentType": "boardgame"}):
            with urllib.request.urlopen(self._url + "?resource=boardgame_catalog") as _response:
                self.assertEqual(json.load(_response)["contentType"], "boardgame")
        _request = urllib.request.Request(self._url, data=json.dumps({"type": "boardgame", "players": 2, "count": 6}).encode())
        with patch("api.generate._recommend_boardgames", return_value={"success": True, "data": {"items": []}}) as _recommendation:
            with urllib.request.urlopen(_request) as _response:
                self.assertTrue(json.load(_response)["success"])
            self.assertEqual(_recommendation.call_args.args[0]["players"], 2)

    def test_input_errors_are_returned_as_json_with_correct_status(self):
        for _body, _status in [(b"[]", 400), (b"not-json", 400)]:
            _request = urllib.request.Request(self._url, data=_body)
            with self.assertRaises(urllib.error.HTTPError) as _error:
                urllib.request.urlopen(_request)
            self.assertEqual(_error.exception.code, _status)
            self.assertFalse(json.load(_error.exception)["success"])
            _error.exception.close()

        # Reject the declared length without uploading a megabyte after an early 413.
        _connection = http.client.HTTPConnection(self._url.removeprefix("http://").split("/", 1)[0])
        try:
            _connection.putrequest("POST", "/api/generate")
            _connection.putheader("Content-Length", "1048577")
            _connection.endheaders()
            _response = _connection.getresponse()
            self.assertEqual(_response.status, 413)
            self.assertFalse(json.load(_response)["success"])
        finally:
            _connection.close()

    def test_seen_list_larger_than_the_old_body_limit_reaches_recommendations(self):
        _ids = ["kakao:" + format(_index, "020x") for _index in range(1000)]
        _body = json.dumps({"type": "webtoon", **_PREFERENCES, "excludedIds": _ids}).encode()
        self.assertGreater(len(_body), 16384)
        with patch("api.generate._recommend", return_value={"success": True, "data": {"items": []}}) as _recommendation:
            with urllib.request.urlopen(urllib.request.Request(self._url, data=_body)) as _response:
                self.assertTrue(json.load(_response)["success"])
            self.assertEqual(_recommendation.call_args.args[0]["excludedIds"], _ids)

    def test_recommendation_failure_is_returned_without_fake_results(self):
        _request = urllib.request.Request(self._url, data=json.dumps({"type": "webtoon", **_PREFERENCES}).encode("utf-8"))
        with patch("api.generate._recommend", side_effect=_RecommendationError("AI busy", 429)):
            with self.assertRaises(urllib.error.HTTPError) as _error:
                urllib.request.urlopen(_request)
        self.assertEqual(_error.exception.code, 429)
        self.assertEqual(json.load(_error.exception), {"success": False, "error": "AI busy"})
        _error.exception.close()


if __name__ == "__main__":
    unittest.main()
