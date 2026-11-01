"""Publisher-sourced tabletop metadata and recommendations with hard group constraints."""

import hashlib
import json
import re
import random
from functools import lru_cache
from pathlib import Path

from services.recommendations import _RecommendationError, _request_recommendations, _validate_excluded_ids


_PATH = Path(__file__).resolve().parents[1] / "data/boardgames.json"
_GENRES = {"전략", "협력", "파티", "가족", "추리", "카드", "퍼즐", "2인", "심리전"}
_MOODS = {"전체", "가볍게", "머리쓰는", "함께하는", "웃음가득", "긴장감", "차분한"}
_DIFFICULTIES = {0: "정보 없음", 1: "가볍게", 2: "보통", 3: "도전"}
_HOSTS = ['www.spacecowboys-games.com', 'www.nsv.de', 'www.nextmove-games.com', 'www.czechgames.com', 'www.blueorangegames.com', 'www.hans-im-glueck.de', 'www.asmodee.ca', 'www.lookout-spiele.de', 'www.rprod.com', 'store.asmodee.com', 'www.cocktailgames.com', 'blog.amigo-spiele.de', 'www.gamewright.com', 'www.catan.com', 'www.zmangames.com', 'www.asmodee.co.uk', 'www.alderac.com', 'pandasaurusgames.com', 'www.amigo-spiele.de', 'oinkgames.com', 'pegasusna.com']
_HOSTS.append("www.koreaboardgames.com")
_PROVIDER = {"key": "boardgames", "name": "공식 게임 정보", "workHosts": _HOSTS, "workPattern": "^/.*$", "imageHosts": ["cdnfile.koreaboardgames.com"]}


@lru_cache(maxsize=1)
def _read_boardgames(_modified):
    _data = json.loads(_PATH.read_text(encoding="utf-8"))
    _items = []
    for _game in _data["games"]:
        _id = "boardgames:" + hashlib.sha256(_game["slug"].encode()).hexdigest()[:20]
        _items.append({**_game, "id": _id, "author": _game["publisher"] + " · " + _game["designer"], "platformKey": "boardgames", "platform": "공식 게임 정보", "genre": _game["genres"][0], "tags": _game["moods"] + _game["mechanisms"], "status": "전체", "days": [], "age": str(_game["minAge"]) + "세 이상 · 출판사 표기" if _game["minAge"] is not None else "이용 연령 확인 필요", "favorites": 0, "cover": _game["cover"], "source": _game["url"], "difficultyLabel": _DIFFICULTIES[_game["difficulty"]], "playersLabel": "인원 정보 확인 필요" if _game["minPlayers"] is None else str(_game["minPlayers"]) + ("명 이상" if _game["maxPlayers"] is None else "명" if _game["minPlayers"] == _game["maxPlayers"] else "~" + str(_game["maxPlayers"]) + "명"), "timeLabel": "시간 정보 확인 필요" if _game["maxMinutes"] is None else str(_game["minMinutes"]) + ("분" if _game["minMinutes"] == _game["maxMinutes"] else "~" + str(_game["maxMinutes"]) + "분")})
    return {"items": _items, "platforms": [_PROVIDER], "updatedAt": _data["updatedAt"], "contentType": "boardgame"}


def _boardgame_catalog():
    return _read_boardgames(_PATH.stat().st_mtime_ns)


def _validate_boardgame(_payload):
    if not isinstance(_payload, dict):
        raise _RecommendationError("보드게임 추천 조건은 JSON 객체로 전송해주세요.", 400)
    _genres = _payload.get("genres", [])
    _mood = _payload.get("mood", "전체")
    _notes = _payload.get("notes", "")
    _count = _payload.get("count", 6)
    _players = _payload.get("players", 0)
    _minutes = _payload.get("maxMinutes", 0)
    _difficulty = _payload.get("difficulty", 0)
    if (not isinstance(_genres, list) or len(_genres) > len(_GENRES) or any(not isinstance(_genre, str) or _genre not in _GENRES for _genre in _genres)
            or not isinstance(_mood, str) or _mood not in _MOODS or not isinstance(_notes, str) or len(_notes) > 600
            or type(_count) is not int or not 1 <= _count <= 18 or type(_players) is not int or not 0 <= _players <= 12
            or type(_minutes) is not int or _minutes not in {0, 15, 20, 30, 45, 60, 90, 120}
            or type(_difficulty) is not int or not 0 <= _difficulty <= 3):
        raise _RecommendationError("보드게임 장르·인원·시간·난이도·추천 개수를 확인해주세요.", 400)
    return {"genres": _genres, "mood": _mood, "notes": _notes.strip(), "count": _count, "players": _players, "maxMinutes": _minutes, "difficulty": _difficulty, "_contentType": "boardgame", "excludedIds": _validate_excluded_ids(_payload)}


def _eligible_boardgame(_item, _preferences):
    return ((not _preferences["genres"] or set(_preferences["genres"]) & set(_item["genres"]))
            and (not _preferences["players"] or (_item["minPlayers"] is not None and _item["minPlayers"] <= _preferences["players"] and (_item["maxPlayers"] is None or _preferences["players"] <= _item["maxPlayers"])))
            and (not _preferences["maxMinutes"] or (_item["maxMinutes"] is not None and _item["maxMinutes"] <= _preferences["maxMinutes"]))
            and (not _preferences["difficulty"] or 0 < _item["difficulty"] <= _preferences["difficulty"]))


def _recommend_boardgames(_payload):
    _preferences = _validate_boardgame(_payload)
    _catalog = _boardgame_catalog()
    _excluded = set(_preferences["excludedIds"])
    _candidates = [_item for _item in _catalog["items"] if _item["id"] not in _excluded and _eligible_boardgame(_item, _preferences)]
    _tokens = re.findall(r"[가-힣A-Za-z0-9]{2,18}", _preferences["notes"].lower())
    _candidates.sort(key=lambda _item: (sum(_token in (_item["description"] + " ".join(_item["tags"])).lower() for _token in _tokens), _preferences["mood"] in _item["moods"], _item.get("featured", False)), reverse=True)
    _matched = len(_candidates)
    if len(_candidates) > 90:
        _candidates = _candidates[:30] + random.sample(_candidates[30:], 60)
    _retrieval = {"catalogCount": len(_catalog["items"]), "candidateCount": len(_candidates), "requestedCount": _preferences["count"], "search": {"status": "not_requested", "matched": _matched, "provider": "출판사·국내 공식 유통사 정보", "platforms": []}}
    if not _candidates:
        return {"success": True, "data": {"items": [], "summary": "현재 목록에서 인원·시간·난이도 조건에 맞는 게임을 찾지 못했습니다. 조건을 조정해보세요.", "source": "filters", "updatedAt": _catalog["updatedAt"], "retrieval": _retrieval}}
    _preferences["count"] = min(_preferences["count"], len(_candidates))
    _result, _model = _request_recommendations(_preferences, _candidates)
    _summary = _result.get("summary") if isinstance(_result, dict) else None
    _entries = _result.get("recommendations") if isinstance(_result, dict) else None
    if not isinstance(_summary, str) or not _summary.strip() or len(_summary) > 240 or not isinstance(_entries, list) or (_entries and len(_entries) != _preferences["count"]):
        raise _RecommendationError("보드게임 추천 형식이 올바르지 않습니다. 다시 시도해주세요.")
    _by_id = {_item["id"]: _item for _item in _candidates}
    _seen, _items = set(), []
    for _entry in _entries:
        _id = _entry.get("id") if isinstance(_entry, dict) else None
        _reason = _entry.get("reason") if isinstance(_entry, dict) else None
        if not isinstance(_id, str) or _id not in _by_id or _id in _seen or not isinstance(_reason, str) or not _reason.strip() or len(_reason) > 240:
            raise _RecommendationError("조건에 맞지 않거나 중복된 보드게임이 추천되었습니다. 다시 시도해주세요.")
        _seen.add(_id)
        _items.append({**_by_id[_id], "recommendationReason": _reason.strip()})
    return {"success": True, "data": {"items": _items, "summary": _summary.strip(), "source": "ai", "model": _model, "updatedAt": _catalog["updatedAt"], "retrieval": _retrieval}}
