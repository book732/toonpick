"""Korean-service anime discovery from a reproducible public catalogue snapshot."""

import json
import random
import re
import urllib.request
from functools import lru_cache
from pathlib import Path

from services.recommendations import _RecommendationError, _request_recommendations, _MOODS

_PATH = Path(__file__).resolve().parents[1] / "data/anime_domestic.json"
_GENRES = {"액션", "모험", "코미디", "드라마", "판타지", "공포", "음악", "미스터리", "로맨스", "SF", "일상", "스포츠", "스릴러", "초자연"}
_FORMATS = {"TV", "MOVIE", "ONA", "OVA", "SPECIAL", "TV_SHORT"}
_STATUSES = {"전체", "완결", "연재", "방영예정", "중단", "휴재"}


def _normalize(_text):
    return re.sub(r"[\W_]+", "", _text).casefold()


def _family(_item):
    _title = re.sub(r"\([^)]*(?:더빙|자막|판권|무삭제)[^)]*\)|\[[^]]*\]", "", _item["title"])
    _title = re.sub(r"\s*(?:(?:시즌|파트)\s*\d+|\d+\s*(?:기|시즌|부))(?:\s.*)?$", "", _title)
    return _normalize(_title)


@lru_cache(maxsize=1)
def _read_anime(_modified):
    _data = json.loads(_PATH.read_text(encoding="utf-8"))
    for _item in _data["items"]:
        _item["franchiseKey"] = _family(_item)
        _item["_searchText"] = _normalize(" ".join([_item["title"], *_item["aliases"], _item["author"], *_item["tags"]]))
        _moods = {"로맨스": "설레는", "액션": "짜릿한", "공포": "몰입되는", "미스터리": "몰입되는", "일상": "힐링", "코미디": "유쾌한", "스포츠": "뭉클한"}
        _item["tags"] = list(dict.fromkeys(_item["tags"] + [_moods[_genre] for _genre in _item["genres"] if _genre in _moods]))
    return _data


def _validate_anime(_payload):
    if not isinstance(_payload, dict):
        raise _RecommendationError("추천 조건은 JSON 객체로 전송해주세요.", 400)
    _genres, _formats, _platforms = (_payload.get(_key, []) for _key in ("genres", "formats", "platforms"))
    _status, _mood = _payload.get("status", "전체"), _payload.get("mood", "전체")
    _count, _query, _notes = _payload.get("count", 6), _payload.get("query", ""), _payload.get("notes", "")
    if (not isinstance(_genres, list) or len(_genres) > len(_GENRES) or any(not isinstance(_v, str) or _v not in _GENRES for _v in _genres)
            or not isinstance(_formats, list) or len(_formats) > len(_FORMATS) or any(not isinstance(_v, str) or _v not in _FORMATS for _v in _formats)
            or not isinstance(_platforms, list) or len(_platforms) > 2 or any(not isinstance(_v, str) or _v not in {"laftel", "netflix"} for _v in _platforms)
            or not isinstance(_status, str) or _status not in _STATUSES or not isinstance(_mood, str) or _mood not in _MOODS
            or type(_count) is not int or not 1 <= _count <= 18 or not isinstance(_query, str) or len(_query) > 100
            or not isinstance(_notes, str) or len(_notes) > 600):
        raise _RecommendationError("애니메이션 장르·플랫폼·형식·방영 상태·추천 개수를 확인해주세요.", 400)
    return {"genres": list(dict.fromkeys(_genres)), "formats": list(dict.fromkeys(_formats)), "platforms": list(dict.fromkeys(_platforms)), "status": _status, "mood": _mood, "count": _count, "query": _query.strip(), "notes": _notes.strip(), "_contentType": "anime"}


def _eligible(_item, _preferences):
    return ((not _preferences["query"] or _normalize(_preferences["query"]) in _item["_searchText"])
            and (not _preferences["genres"] or set(_preferences["genres"]) & set(_item["genres"]))
            and (not _preferences["formats"] or _item["format"] in _preferences["formats"])
            and (not _preferences["platforms"] or _item["platformKey"] in _preferences["platforms"])
            and (_preferences["status"] == "전체" or _item["status"] == _preferences["status"]))


def _public_item(_item):
    return {_key: _value for _key, _value in _item.items() if not _key.startswith("_")}


def _anime_discovery(_preferences, _page=1, _all=False):
    _data = _read_anime(_PATH.stat().st_mtime_ns)
    _items = [_item for _item in _data["items"] if _eligible(_item, _preferences)]
    if not _all and _preferences["mood"] != "전체":
        _items = [_item for _item in _items if _preferences["mood"] in _item["tags"]]
    _items.sort(key=lambda _item: _item["favorites"], reverse=True)
    if not _all:
        _queues = [[_item for _item in _items if _item["platformKey"] == _key] for _key in ("laftel", "netflix")]
        _items = [_group[_offset] for _offset in range(max(map(len, _queues), default=0)) for _group in _queues if _offset < len(_group)]
    _start = (_page - 1) * 120
    _result = {"items": [_public_item(_item) for _item in (_items if _all else _items[_start:_start + 120])], "updatedAt": _data["updatedAt"], "platforms": _data["platforms"], "provider": "국내 감상 서비스", "contentType": "anime", "catalogCount": len(_data["items"]), "matchedCount": len(_items), "countBasis": _data["countBasis"], "pagination": {"page": _page, "hasNextPage": not _all and _start + 120 < len(_items)}}
    if _page == 1 and not _all:
        _result["heroItems"] = []
        # Sample the full collection without shipping ten thousand cards to the browser.
        for _key in ("laftel", "netflix"):
            _pool = [_item for _item in _data["items"] if _item["platformKey"] == _key and _item.get("available", True)]
            _result["heroItems"].extend(_public_item(_item) for _item in random.sample(_pool, min(30, len(_pool))))
    return _result


def _anime_page(_preferences, _page=1):
    return _anime_discovery(_preferences, _page)


def _anime_catalog(_parameters):
    _preferences = _validate_anime({"genres": _parameters.get("genre", []), "formats": _parameters.get("format", []), "platforms": _parameters.get("platform", []), "mood": _parameters.get("mood", ["전체"])[0], "status": _parameters.get("status", ["전체"])[0], "query": _parameters.get("query", [""])[0]})
    try:
        _page = int(_parameters.get("page", ["1"])[0])
    except (ValueError, TypeError):
        raise _RecommendationError("페이지 번호를 확인해주세요.", 400) from None
    if not 1 <= _page <= 1000:
        raise _RecommendationError("페이지 번호를 확인해주세요.", 400)
    return _anime_page(_preferences, _page)


@lru_cache(maxsize=128)
def _anime_detail(_id, _bucket):
    _data = _read_anime(_PATH.stat().st_mtime_ns)
    _item = next((_entry for _entry in _data["items"] if _entry["id"] == _id), None)
    if not _item:
        raise _RecommendationError("작품을 찾을 수 없습니다.", 404)
    _result = _public_item(_item)
    if _item["platformKey"] == "laftel":
        # Fetch only the selected work; never download playback or account resources.
        _source_id = _item["url"].rsplit("/", 1)[-1]
        try:
            _request = urllib.request.Request("https://laftel.net/api/items/v4/" + _source_id + "/", headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(_request, timeout=8) as _response:
                _detail = json.loads(_response.read(1024 * 1024))
            if _detail.get("id") == int(_source_id):
                _result["description"] = re.sub(r"\s+", " ", _detail.get("content") or _item["description"]).strip()[:2500]
                _result["author"] = _detail.get("production") or _item["author"]
        except (OSError, ValueError, TypeError):
            pass
    return _result


def _recommend_anime(_payload):
    _preferences = _validate_anime(_payload)
    _catalog = _anime_discovery(_preferences, _all=True)
    _items = _catalog["items"]
    _viewable = [_item for _item in _items if _item.get("available", _item["platformKey"] == "netflix")]
    if not _preferences["query"] and len(_viewable) >= _preferences["count"]:
        _items = _viewable
    _tokens = [_normalize(_token) for _token in re.findall(r"[가-힣A-Za-z0-9]{2,24}", _preferences["notes"])]
    _items.sort(key=lambda _item: (sum(_token in _normalize(_item["title"] + " ".join(_item["tags"]) + _item["description"]) for _token in _tokens), _item.get("available", _item["platformKey"] == "netflix"), _item["favorites"]), reverse=True)
    _budget = max(60, _preferences["count"] * 4)
    _groups = [[_item for _item in _items if _item["platformKey"] == _key] for _key in ("laftel", "netflix")]
    # Keep relevant entry points and rotate the remaining candidates for discovery.
    for _index, _group in enumerate(_groups):
        _groups[_index] = _group[:15] + random.sample(_group[15:], len(_group[15:]))
    _candidates, _seen = [], set()
    for _offset in range(max(map(len, _groups), default=0)):
        for _group in _groups:
            if _offset >= len(_group):
                continue
            _item = _group[_offset]
            if _item["franchiseKey"] not in _seen:
                _seen.add(_item["franchiseKey"])
                _candidates.append(_item)
                if len(_candidates) == _budget:
                    break
        if len(_candidates) == _budget:
            break
    _retrieval = {"catalogCount": _catalog["catalogCount"], "candidateCount": len(_candidates), "requestedCount": _preferences["count"], "search": {"status": "ok", "matched": len(_items), "provider": "라프텔 · 넷플릭스 한국 공식 목록", "platforms": _catalog["platforms"], "urls": ["https://laftel.net/search", "https://www.netflix.com/kr/browse/genre/7424"]}}
    if not _candidates:
        return {"success": True, "data": {"items": [], "summary": "조건에 맞는 애니메이션을 찾지 못했습니다. 장르나 플랫폼 조건을 조정해보세요.", "source": "filters", "updatedAt": _catalog["updatedAt"], "retrieval": _retrieval}}
    _preferences["count"] = min(_preferences["count"], len(_candidates))
    _result, _model = _request_recommendations(_preferences, _candidates)
    _entries = _result.get("recommendations") if isinstance(_result, dict) else None
    _summary = _result.get("summary") if isinstance(_result, dict) else None
    if not isinstance(_summary, str) or not _summary.strip() or len(_summary) > 240 or not isinstance(_entries, list) or (_entries and len(_entries) != _preferences["count"]):
        raise _RecommendationError("애니메이션 추천 응답 형식이 올바르지 않습니다. 다시 시도해주세요.")
    _by_id = {_item["id"]: _item for _item in _candidates}
    _seen, _items = set(), []
    for _entry in _entries:
        _id = _entry.get("id") if isinstance(_entry, dict) else None
        _reason = _entry.get("reason") if isinstance(_entry, dict) else None
        if not isinstance(_id, str) or _id not in _by_id or _id in _seen or not isinstance(_reason, str) or not _reason.strip() or len(_reason) > 240:
            raise _RecommendationError("유효하지 않은 애니메이션이 추천되었습니다. 다시 시도해주세요.")
        _seen.add(_id)
        _items.append({**_by_id[_id], "recommendationReason": _reason.strip()})
    return {"success": True, "data": {"items": _items, "summary": _summary.strip(), "source": "ai", "model": _model, "updatedAt": _catalog["updatedAt"], "retrieval": _retrieval}}
