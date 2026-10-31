"""Collect official title metadata and discover candidates through live site search."""

import json
import os
import re
import tempfile
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from services.platforms import _REGISTRY, _collect_platforms, _platform_registry, _search_platforms


_ROOT = Path(__file__).resolve().parents[1]
_CACHE = Path(tempfile.gettempdir()) / "toonpick" if os.environ.get("VERCEL") else _ROOT / ".cache"
_TTL = 86400
_HEADERS = {"User-Agent": "Mozilla/5.0 ToonPick/1.0", "Referer": "https://comic.naver.com/"}
_REFRESH_LOCK = threading.Lock()
_REFRESHING = False
_LAST_ERROR = ""
_GENRE_MAP = {"로맨스": "로맨스", "순정": "로맨스", "판타지": "판타지", "무협/사극": "무협", "무협": "무협", "스릴러": "스릴러", "일상": "일상", "드라마": "드라마", "스포츠": "스포츠", "액션": "액션", "개그": "개그"}


def _read_json(_url):
    _request = urllib.request.Request(_url, headers=_HEADERS)
    with urllib.request.urlopen(_request, timeout=8) as _response:
        _raw = _response.read(8 * 1024 * 1024 + 1)
    if len(_raw) > 8 * 1024 * 1024:
        raise ValueError("Upstream response is too large")
    return json.loads(_raw)


def _write_json(_path, _value):
    _path.parent.mkdir(parents=True, exist_ok=True)
    _temporary = _path.with_name(_path.name + "." + str(threading.get_ident()) + ".tmp")
    _temporary.write_text(json.dumps(_value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    _temporary.replace(_path)


def _normalize_item(_metadata):
    _id = str(_metadata.get("titleId", ""))
    if not _id.isdigit() or not _metadata.get("titleName"):
        return None
    _age = _metadata.get("age", {}).get("description", "이용 연령은 공식 페이지 확인")
    if _metadata.get("adult") or _metadata.get("nineteen") or "19" in _age or "18" in _age:
        return None
    _tag_data = _metadata.get("curationTagList", _metadata.get("tagList", []))
    _tags = [_entry["tagName"] for _entry in _tag_data if isinstance(_entry.get("tagName"), str)]
    _official_genres = [_entry["tagName"] for _entry in _tag_data if str(_entry.get("curationType", "")).startswith("GENRE_")]
    _genre = next((_GENRE_MAP[_tag] for _tag in _official_genres if _tag in _GENRE_MAP), "드라마")
    if any(_tag in {"무협", "무협/사극"} for _tag in _tags):
        _genre = "무협"
    _moods = {"로맨스": ["설레는"], "무협": ["짜릿한"], "액션": ["짜릿한"], "스릴러": ["몰입되는"], "일상": ["힐링"], "개그": ["유쾌한"], "스포츠": ["뭉클한"]}.get(_genre, [])
    for _keywords, _mood in [(("힐링",), "힐링"), (("개그",), "유쾌한"), (("설렘", "로맨스"), "설레는"), (("미스터리", "세계관"), "몰입되는"), (("우정", "가족", "성장"), "뭉클한")]:
        if any(_keyword in _tag for _keyword in _keywords for _tag in _tags):
            _moods.append(_mood)
    _cover = _metadata.get("thumbnailUrl", "")
    _parsed = urllib.parse.urlsplit(_cover)
    if _parsed.scheme != "https" or _parsed.hostname != "image-comic.pstatic.net":
        return None
    _authors = " / ".join(_artist["name"] for _artist in _metadata.get("communityArtists", []) if isinstance(_artist.get("name"), str))
    return {
        "id": _id, "title": _metadata["titleName"], "author": _authors or _metadata.get("displayAuthor", _metadata.get("author", "작가 정보 확인 중")),
        "description": _metadata.get("synopsis", ""), "genre": _genre,
        "tags": list(dict.fromkeys(_moods + _tags))[:18],
        "status": "완결" if _metadata.get("finished", _metadata.get("finish")) else "휴재" if _metadata.get("rest") else "연재",
        "days": _metadata.get("publishDayOfWeekList", []), "age": _age,
        "favorites": int(_metadata.get("favoriteCount", 0)), "platform": "네이버웹툰", "platformKey": "naver", "cover": _cover,
        "url": "https://comic.naver.com/webtoon/list?titleId=" + _id,
        "source": "https://comic.naver.com/api/article/list/info?titleId=" + _id,
    }


def _fetch_metadata(_id):
    if not str(_id).isdigit():
        raise ValueError("Invalid title ID")
    _path = _CACHE / "metadata" / (str(_id) + ".json")
    if _path.exists() and time.time() - _path.stat().st_mtime < _TTL:
        return json.loads(_path.read_text(encoding="utf-8"))
    _item = _normalize_item(_read_json("https://comic.naver.com/api/article/list/info?titleId=" + str(_id)))
    if _item:
        _write_json(_path, _item)
    return _item


@lru_cache(maxsize=4)
def _read_snapshot(_path, _modified):
    return json.loads(Path(_path).read_text(encoding="utf-8"))


def _get_catalog():
    _path = _CACHE / "catalog.json"
    if not _path.exists():
        _path = _ROOT / "data/webtoons.json"
    return _read_snapshot(str(_path), _path.stat().st_mtime_ns)


def _collect_catalog(_progress=None):
    _existing = _get_catalog()
    _ids = dict.fromkeys(_item["id"] for _item in _existing["items"] if _item["id"].isdigit())
    _weekdays = _read_json("https://comic.naver.com/api/webtoon/titlelist/weekday?order=user")
    for _items in _weekdays["titleListMap"].values():
        for _item in _items:
            if not _item.get("adult"):
                _ids[str(_item["titleId"])] = None
    _url = "https://comic.naver.com/api/webtoon/titlelist/finished?order=user&page="
    _first = _read_json(_url + "1")
    _pages = _first["pageInfo"]["totalPages"]
    if not isinstance(_pages, int) or not 1 <= _pages <= 300:
        raise ValueError("Invalid upstream pagination")
    _failures = 0
    with ThreadPoolExecutor(max_workers=4) as _executor:
        _futures = [_executor.submit(_read_json, _url + str(_page)) for _page in range(2, _pages + 1)]
        _batches = [_first]
        for _future in as_completed(_futures):
            try:
                _batches.append(_future.result())
            except Exception:
                _failures += 1
        for _batch in _batches:
            for _item in _batch.get("titleList", []):
                if not _item.get("adult"):
                    _ids[str(_item["titleId"])] = None
    if _progress:
        _progress("Discovered " + str(len(_ids)) + " title IDs; fetching official metadata.")
    _by_id = {_item["id"]: _item for _item in _existing["items"]}
    with ThreadPoolExecutor(max_workers=6) as _executor:
        _futures = {_executor.submit(_fetch_metadata, _id): _id for _id in _ids}
        for _index, _future in enumerate(as_completed(_futures), 1):
            try:
                _item = _future.result()
                if _item:
                    _by_id[_item["id"]] = _item
            except Exception:
                _failures += 1
            if _progress and _index % 200 == 0:
                _progress("Fetched " + str(_index) + "/" + str(len(_ids)) + " titles.")
    if len(_by_id) < 100:
        raise RuntimeError("Not enough official metadata was collected; retaining the previous catalogue")
    # Keep established editor picks first while expanding all remaining titles automatically.
    _seed = ["747269", "769209", "761722", "703844", "777767", "774866", "796152", "651673", "650305", "747271", "654774", "679519", "701081", "703846"]
    _seed_order = {_id: _index for _index, _id in enumerate(_seed)}
    _items = sorted(_by_id.values(), key=lambda _item: (_seed_order.get(_item["id"], len(_seed)), -_item["favorites"], _item["id"]))
    _other_items, _platforms = _collect_platforms(_progress)
    _by_id = {_item["id"]: _item for _item in _items}
    _by_id.update({_item["id"]: _item for _item in _other_items})
    _catalog = {"updatedAt": datetime.now(timezone.utc).isoformat(), "items": list(_by_id.values()), "platforms": _platforms, "collection": {"provider": "국내 웹툰 플랫폼", "discovered": len(_ids), "failedRequests": _failures, "refreshHours": 24}}
    _catalog["platforms"] = _platform_registry(_catalog)
    _write_json(_CACHE / "catalog.json", _catalog)
    return _catalog


def _start_refresh():
    global _REFRESHING
    with _REFRESH_LOCK:
        _catalog = _get_catalog()
        _updated = datetime.fromisoformat(_catalog["updatedAt"]).timestamp()
        if _REFRESHING or (len(_catalog["items"]) > 100 and time.time() - _updated < _TTL):
            return
        _REFRESHING = True
    def _worker():
        global _REFRESHING, _LAST_ERROR
        try:
            _collect_catalog()
            _LAST_ERROR = ""
        except Exception:
            _LAST_ERROR = "작품 목록 갱신이 지연되어 마지막으로 수집한 정보를 제공합니다."
        finally:
            with _REFRESH_LOCK:
                _REFRESHING = False
    threading.Thread(target=_worker, daemon=True, name="toonpick-catalog-refresh").start()


def _catalog_response():
    _start_refresh()
    _catalog = _get_catalog()
    return {**_catalog, "platforms": _platform_registry(_catalog), "refreshing": _REFRESHING, "refreshMessage": _LAST_ERROR}


@lru_cache(maxsize=128)
def _search_query(_query, _bucket):
    _url = "https://comic.naver.com/api/search/webtoon?" + urllib.parse.urlencode({"keyword": _query, "page": 1})
    _data = _read_json(_url)
    return [str(_item["titleId"]) for _item in _data.get("searchList", []) if _item.get("webtoonLevelCode") == "WEBTOON" and not _item.get("adult") and not _item.get("nineteen")], _url


def _search_web(_preferences, _catalog):
    _notes = _preferences.get("notes", "")
    _compact_notes = re.sub(r"\s+", "", _notes)
    _queries = [_item["title"] for _item in _catalog["items"] if re.sub(r"\s+", "", _item["title"]) in _compact_notes]
    _stop = {"웹툰", "추천", "싶어요", "좋아요", "이야기", "작품", "같은", "있는", "보고", "그리고", "해주세요"}
    _words = [re.sub(r"(?:하는|하고|있는|에서|처럼|같은|으로|와|과|을|를|이|가|은|는|한)$", "", _word) for _word in re.findall(r"[가-힣a-zA-Z0-9]{2,18}", _notes)]
    _queries += [_word for _word in _words if len(_word) >= 2 and _word not in _stop]
    _context = [_preferences["mood"]] if _preferences["mood"] != "전체" else _preferences["genres"][:1] or ["성장"]
    _queries = list(dict.fromkeys(list(dict.fromkeys(_queries))[:2] + _context))[:3]
    _ids, _urls, _failures = [], [], 0
    _selected = _preferences.get("platforms", [])
    _keys = _selected or [_platform["key"] for _platform in _REGISTRY]
    with ThreadPoolExecutor(max_workers=4) as _executor:
        _external = _executor.submit(_search_platforms, _queries[0], [_key for _key in _keys if _key != "naver"]) if any(_key != "naver" for _key in _keys) else None
        _futures = [_executor.submit(_search_query, _query, int(time.time() // 600)) for _query in _queries] if "naver" in _keys else []
        for _future in _futures:
            try:
                _found, _url = _future.result()
                _ids.extend(_found)
                _urls.append(_url)
            except Exception:
                _failures += 1
    _by_id = {_item["id"]: _item for _item in _catalog["items"]}
    _items = []
    _unique = list(dict.fromkeys(_ids))
    with ThreadPoolExecutor(max_workers=4) as _executor:
        _missing_ids = [_id for _id in _unique if _id not in _by_id][:8]
        _missing = {_id: _executor.submit(_fetch_metadata, _id) for _id in _missing_ids}
        for _id in _unique:
            if _id not in _by_id and _id not in _missing:
                continue
            try:
                _item = _by_id.get(_id) or _missing[_id].result()
                if _item:
                    _items.append({**_item, "discovery": "web"})
            except Exception:
                _failures += 1
    _statuses = [{"key": "naver", "status": "ok" if _urls else "unavailable", "matched": len(_items), "url": "https://comic.naver.com/search?keyword=" + urllib.parse.quote(_queries[0])}] if "naver" in _keys else []
    if _external:
        _other_items, _other_statuses = _external.result()
        _items.extend({**_item, **_by_id.get(_item["id"], {}), "discovery": "web"} for _item in _other_items)
        _statuses.extend(_other_statuses)
        _urls.extend(_status["url"] for _status in _other_statuses if _status["status"] == "ok")
        _failures += sum(_status["status"] == "unavailable" for _status in _other_statuses)
    return _items, {"queries": _queries, "urls": _urls, "matched": len(_items), "newTitles": sum(_item["id"] not in _by_id for _item in _items), "status": "unavailable" if not _urls else "partial" if _failures else "ok", "provider": "국내 플랫폼 공식 검색·공개 목록", "platforms": _statuses}


def _story_key(_item):
    _title = unicodedata.normalize("NFKC", _item["title"]).casefold()
    _title = re.sub(r"[\[(](?:개정판|완전판|일반판|컬러판|연재|완결)[\])]", "", _title)
    return re.sub(r"[\W_]+", "", _title) or _item["id"]


def _select_candidates(_preferences, _catalog, _web_items):
    def _eligible(_item):
        return (not _preferences["genres"] or _item["genre"] in _preferences["genres"]) and (_preferences["status"] == "전체" or _item["status"] == _preferences["status"]) and (not _preferences.get("platforms") or _item.get("platformKey", "naver") in _preferences["platforms"])
    _tokens = list(dict.fromkeys(re.findall(r"[가-힣a-zA-Z0-9]{2,18}", _preferences.get("notes", "").lower())))
    def _score(_item):
        _text = (_item["title"] + " " + " ".join(_item["tags"]) + " " + _item["description"]).lower()
        return sum(4 if _token in _item["title"].lower() else 1 for _token in _tokens if _token in _text) + (3 if _preferences["mood"] in _item["tags"] else 0)
    _local = sorted((_item for _item in _catalog["items"] if _eligible(_item)), key=lambda _item: (_score(_item), _item["favorites"]), reverse=True)
    _web = sorted((_item for _item in _web_items if _eligible(_item)), key=_score, reverse=True)
    _merged = {_item["id"]: _item for _item in _local}
    _merged.update({_item["id"]: _item for _item in _web})
    _groups = {}
    for _item in sorted(_merged.values(), key=lambda _entry: (_entry.get("discovery") == "web", _score(_entry), _entry["favorites"]), reverse=True):
        _groups.setdefault(_item.get("platformKey", "naver"), []).append(_item)
    _candidates = []
    _limit = max(36, _preferences.get("count", 6) * 4)
    _stories = set()
    _offsets = {_key: 0 for _key in _groups}
    while len(_candidates) < _limit and any(_offsets[_key] < len(_group) for _key, _group in _groups.items()):
        for _key, _group in _groups.items():
            while _offsets[_key] < len(_group):
                _item = _group[_offsets[_key]]
                _offsets[_key] += 1
                _story = _story_key(_item)
                if _story not in _stories:
                    _stories.add(_story)
                    _candidates.append(_item)
                    break
            if len(_candidates) == _limit:
                break
    return _candidates
