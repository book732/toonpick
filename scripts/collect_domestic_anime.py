"""Refresh public Korean service metadata without collecting playback resources."""

import hashlib
import html
import json
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]
_CACHE = _ROOT / ".cache/domestic-anime"
_GENRES = {"개그": "코미디", "치유": "일상", "로맨스": "로맨스", "추리": "미스터리", "스릴러": "스릴러", "공포": "공포", "SF": "SF", "액션": "액션", "모험": "모험", "음악": "음악", "스포츠": "스포츠", "일상": "일상", "드라마": "드라마", "판타지": "판타지", "코미디": "코미디"}
_FORMATS = {"TVA": ("TV", "TV 시리즈"), "극장판": ("MOVIE", "극장판"), "OVA": ("OVA", "OVA"), "WEB": ("ONA", "웹 애니메이션")}
_PLATFORMS = [
    {"key": "laftel", "name": "라프텔", "home": "https://laftel.net/", "searchUrl": "https://laftel.net/search?keyword={query}", "workHosts": ["laftel.net"], "workPattern": "^/item/[0-9]+(?:/.*)?$", "imageHosts": ["thumbnail.laftel.net"], "status": "ok"},
    {"key": "netflix", "name": "넷플릭스", "home": "https://www.netflix.com/kr/browse/genre/7424", "workHosts": ["www.netflix.com"], "workPattern": "^/(?:kr/)?title/[0-9]+$", "imageHosts": ["*.nflxso.net", "assets.nflxext.com"], "status": "ok"},
]


def _get(_url, _name):
    _path = _CACHE / _name
    if _path.exists():
        _body = _path.read_text(encoding="utf-8")
        if _name.startswith("netflix-") and _name != "netflix-anime.html" and len(_body) > 100000:
            _body = "".join(re.findall(r'<script[^>]+type="application/ld\+json"[^>]*>.*?</script>', _body, re.S))
            _path.write_text(_body, encoding="utf-8")
        return _body
    for _attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(_url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "ko-KR,ko;q=0.9"}), timeout=25) as _response:
                _body = _response.read(6 * 1024 * 1024).decode()
            if _name.startswith("netflix-") and _name != "netflix-anime.html":
                _body = "".join(re.findall(r'<script[^>]+type="application/ld\+json"[^>]*>.*?</script>', _body, re.S))
            _path.write_text(_body, encoding="utf-8")
            time.sleep(0.8)
            return _body
        except Exception:
            if _attempt == 2:
                raise
            time.sleep(3 * (_attempt + 1))


def _base(_key, _id, _title, _cover, _url):
    return {"id": _key + ":" + hashlib.sha256(_url.encode()).hexdigest()[:20], "animeId": _key + ":" + str(_id), "title": _title, "aliases": [_title], "author": "제작사 정보 확인 필요", "description": "", "genre": "장르 확인 필요", "genres": [], "tags": [], "format": "TV", "formatLabel": "TV 시리즈", "year": None, "episodes": None, "duration": None, "status": "확인 필요", "days": [], "age": "공식 감상 서비스에서 이용 연령 확인", "favorites": 0, "score": None, "platformKey": _key, "platform": next(_p["name"] for _p in _PLATFORMS if _p["key"] == _key), "cover": _cover, "url": _url, "source": _url, "relations": [], "watchLinks": [{"platform": next(_p["name"] for _p in _PLATFORMS if _p["key"] == _key), "url": _url}], "availability": "공식 목록 확인"}


def _main():
    _CACHE.mkdir(parents=True, exist_ok=True)
    _items = {}
    _offset = 0
    while True:
        _data = json.loads(_get("https://laftel.net/api/search/v1/discover/?sort=rank&size=100&offset=" + str(_offset), "page-" + str(_offset) + ".json"))
        for _rank, _record in enumerate(_data["results"], _offset):
            _url = "https://laftel.net/item/" + str(_record["id"])
            _entry = _base("laftel", _record["id"], _record["name"], _record["img"], _url)
            _raw_genres = _record.get("genres", [])
            _entry["genres"] = list(dict.fromkeys(_GENRES[_g] for _g in _raw_genres if _g in _GENRES))
            _entry["genre"] = next(iter(_entry["genres"]), "장르 확인 필요")
            _entry["tags"] = _raw_genres
            _entry["format"], _entry["formatLabel"] = _FORMATS.get(_record.get("medium"), ("SPECIAL", "스페셜"))
            _entry["status"] = "완결" if _record.get("is_ending") else "연재" if _record.get("is_viewing") and _record.get("is_episode_existed") else "확인 필요"
            _entry["age"] = _record.get("content_rating") or _entry["age"]
            _entry["available"] = bool(_record.get("is_viewing") and not _record.get("is_expired"))
            _entry["availability"] = "라프텔 감상 가능 표시" if _entry["available"] else "라프텔 작품 정보 · 감상 여부 확인 필요"
            _entry["favorites"] = max(0, _data["count"] - _rank)
            _entry["description"] = " · ".join(_raw_genres) + " · " + _entry["formatLabel"] + ". 줄거리는 공식 작품 페이지에서 확인해주세요."
            # Only the first discovery pages need richer summaries for initial recommendations.
            if _rank < 100:
                _detail = json.loads(_get("https://laftel.net/api/items/v4/" + str(_record["id"]) + "/", "detail-" + str(_record["id"]) + ".json"))
                _entry["description"] = re.sub(r"\s+", " ", _detail.get("content") or _entry["description"]).strip()[:1800]
                _entry["author"] = _detail.get("production") or _entry["author"]
                _entry["seriesId"] = str(_detail.get("series_id") or _entry["animeId"])
                _year = re.search(r"(19|20)\d{2}", _detail.get("air_year_quarter") or "")
                _entry["year"] = int(_year[0]) if _year else None
            _items[_entry["id"]] = _entry
        print("Laftel", _offset + len(_data["results"]), "/", _data["count"], flush=True)
        _offset += len(_data["results"])
        if not _data.get("next") or not _data["results"]:
            break
    _page = _get("https://www.netflix.com/kr/browse/genre/7424", "netflix-anime.html")
    _netflix_urls = set(re.findall(r'href="(https://www.netflix.com/kr/title/\d+)"', _page))
    with ThreadPoolExecutor(max_workers=3) as _workers:
        _jobs = [_workers.submit(_get, _url, "netflix-" + _url.rsplit("/", 1)[-1] + ".html") for _url in _netflix_urls]
        for _index, _job in enumerate(as_completed(_jobs), 1):
            try:
                _job.result()
            except (OSError, ValueError):
                pass
            if _index % 25 == 0:
                print("Netflix metadata", _index, "/", len(_jobs), flush=True)
    _by_title = {}
    for _item in _items.values():
        _name = re.sub(r"\([^)]*\)|\[[^]]*\]|\s*\d+기.*$", "", _item["title"])
        _by_title.setdefault(re.sub(r"\W", "", _name).casefold(), _item)
    for _match in re.finditer(r'<a\b[^>]*href="(https://www.netflix.com/kr/title/(\d+))"[^>]*>(.*?)</a>', _page, re.S):
        _url, _id, _body = _match.groups()
        if any(_item["animeId"] == "netflix:" + _id for _item in _items.values()):
            continue
        _name = re.search(r"<p\b[^>]*>(.*?)</p>", _body, re.S)
        _image = re.search(r"background-image:url\((https://[^)]+)\)", _body)
        if not _name or not _image:
            continue
        _title = html.unescape(re.sub(r"<[^>]+>", "", _name[1]))
        _entry = _base("netflix", _id, _title, html.unescape(_image[1]), _url)
        _entry["description"] = "넷플릭스 한국 애니메이션 공식 목록에 소개된 작품입니다. 줄거리와 국내 재생 가능 여부는 공식 페이지에서 확인해주세요."
        _related = _by_title.get(re.sub(r"\W", "", _title).casefold())
        if _related:
            _entry["genres"], _entry["genre"], _entry["tags"] = _related["genres"], _related["genre"], _related["tags"]
        try:
            _detail_page = _get(_url, "netflix-" + _id + ".html")
            for _script in re.findall(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', _detail_page, re.S):
                _detail = json.loads(_script)
                if _detail.get("@type") not in {"Movie", "TVSeries"}:
                    continue
                _entry["format"] = "MOVIE" if _detail["@type"] == "Movie" else "TV"
                _entry["formatLabel"] = "극장판" if _entry["format"] == "MOVIE" else "TV 시리즈"
                _entry["description"] = _detail.get("description") or _entry["description"]
                _entry["age"] = _detail.get("contentRating") or _entry["age"]
                _entry["author"] = " / ".join(_person["name"] for _person in _detail.get("creators", []) if _person.get("name")) or _entry["author"]
                _entry["availability"] = "넷플릭스 한국 공식 작품 페이지 확인 · 재생 여부는 서비스 확인"
        except (OSError, ValueError, TypeError):
            pass
        _entry["favorites"] = 5000
        _items[_entry["id"]] = _entry
        print("Netflix", _title, flush=True)
    for _platform in _PLATFORMS:
        _platform["count"] = sum(_item["platformKey"] == _platform["key"] for _item in _items.values())
    _output = {"items": list(_items.values()), "platforms": _PLATFORMS, "updatedAt": datetime.now(timezone.utc).isoformat(), "contentType": "anime", "sources": ["https://laftel.net/search", "https://www.netflix.com/kr/browse/genre/7424"], "countBasis": "플랫폼별 시즌·극장판·더빙판 작품 항목. 재생 권한은 각 서비스에서 확인."}
    _path = _ROOT / "data/anime_domestic.json"
    _temporary = _path.with_suffix(".tmp")
    _temporary.write_text(json.dumps(_output, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    _temporary.replace(_path)
    print("Saved", len(_items), "domestic-service entries", flush=True)


if __name__ == "__main__":
    _main()
