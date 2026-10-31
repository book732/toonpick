"""Public metadata adapters for domestic platforms; no login or age-gate automation."""

import hashlib
import html
import json
import os
import re
import tempfile
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]
_CACHE = Path(tempfile.gettempdir()) / "toonpick/platforms" if os.environ.get("VERCEL") else _ROOT / ".cache/platforms"
_REGISTRY = json.loads((_ROOT / "data/platforms.json").read_text(encoding="utf-8"))
_BY_KEY = {_platform["key"]: _platform for _platform in _REGISTRY}


def _platform_group(_item):
    _key = _item.get("platformKey", "naver")
    return "naver" if _key in {"naver", "naverseries"} else "kakao" if _key in {"kakaopage", "kakaowebtoon"} else "other"


def _host_allowed(_host, _allowed):
    return any(_host == _entry or (_entry.startswith("*.") and (_host == _entry[2:] or _host.endswith("." + _entry[2:]))) for _entry in _allowed)


def _valid_work_url(_platform, _url):
    _parts = urllib.parse.urlsplit(_url)
    return _parts.scheme == "https" and _parts.hostname in _platform["workHosts"] and not _parts.username and not _parts.password and not _parts.port and bool(re.fullmatch(_platform["workPattern"], _parts.path))


def _fetch(_url, _platform):
    _headers = {"User-Agent": "Mozilla/5.0", "Referer": _platform["home"], "Accept-Language": "ko-KR,ko;q=0.9"}
    if _platform["key"] == "kakaopage":
        _headers["Origin"] = "https://page.kakao.com"
    if _platform["key"] == "toomics":
        _headers = {"User-Agent": "Mozilla/5.0"}
    if _platform["key"] == "bomtoon":
        _headers.update({"x-balcony-id": "BOMTOON_COM", "x-platform": "WEB"})
    if _platform["key"] == "lezhin":
        _headers.update({"x-lz-allowadult": "false", "x-lz-adult": "0", "x-lz-locale": "ko-KR", "x-lz-country": "kr"})
    with urllib.request.urlopen(urllib.request.Request(_url, headers=_headers), timeout=5) as _response:
        _raw = _response.read(3 * 1024 * 1024 + 1)
        _encoding = _response.headers.get_content_charset()
        _final = _response.url
    if len(_raw) > 3 * 1024 * 1024:
        raise ValueError("Public response exceeds limit")
    if urllib.parse.urlsplit(_final).hostname not in {urllib.parse.urlsplit(_url).hostname, *_platform["workHosts"]}:
        raise ValueError("Unexpected redirect host")
    _charset = re.search(br"charset=[\"']?([\w-]+)", _raw[:10000], re.I)
    _encoding = _encoding or (_charset[1].decode() if _charset else "utf-8")
    if _encoding.lower() in {"euc-kr", "ks_c_5601-1987"}:
        _encoding = "cp949"
    return _raw.decode(_encoding, errors="replace")


class _PublicHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta = {}
        self.json_data = []
        self.links = []
        self._anchor = None
        self._script = None

    def handle_starttag(self, tag, attrs):
        _attrs = dict(attrs)
        if tag == "meta":
            self.meta[_attrs.get("property", _attrs.get("name", ""))] = _attrs.get("content", "")
        if tag == "script" and (_attrs.get("id") == "__NEXT_DATA__" or _attrs.get("type") == "application/ld+json"):
            self._script = ""
        if tag == "a":
            if self._anchor:
                self.links.append(self._anchor)
            self._anchor = {"url": _attrs.get("href", ""), "title": _attrs.get("title", ""), "text": "", "cover": ""}
        if tag == "img" and self._anchor:
            _cover = _attrs.get("data-src", _attrs.get("data-original", _attrs.get("src", "")))
            if not self._anchor["cover"] or (re.search(r"/icon/|icon_", self._anchor["cover"]) and not re.search(r"/icon/|icon_", _cover)):
                self._anchor["cover"] = _cover
            if not self._anchor["title"] or re.fullmatch(r"UPDATE|TYPE|NEW|UP", self._anchor["title"], re.I):
                self._anchor["title"] = _attrs.get("alt", "")

    def handle_data(self, data):
        if self._script is not None:
            self._script += data
        elif self._anchor:
            self._anchor["text"] += data + " "

    def handle_endtag(self, tag):
        if tag == "script" and self._script is not None:
            try:
                self.json_data.append(json.loads(self._script))
            except (ValueError, TypeError):
                pass
            self._script = None
        if tag == "a" and self._anchor:
            self.links.append(self._anchor)
            self._anchor = None


def _clean_text(_text):
    _text = html.unescape(_text or "")
    _text = re.sub(r"</?(?:br|p|span|b|div|em|strong|i|a)\b[^>]*>", " ", _text, flags=re.I)
    return re.sub(r"[ \t]+", " ", _text).strip()


def _tag_genre(_tags):
    _names = {"로맨스": "로맨스", "순정": "로맨스", "로판": "로맨스", "BL": "로맨스", "GL": "로맨스", "판타지": "판타지", "무협": "무협", "스릴러": "스릴러", "공포": "스릴러", "일상": "일상", "개그": "개그", "코믹": "개그", "드라마": "드라마", "스포츠": "스포츠", "액션": "액션"}
    for _tag in _tags:
        _match = re.search(r"로맨스|판타지|무협|스릴러|스포츠|드라마|액션|일상|개그|순정|로판|BL|GL", _tag)
        if _match:
            return _names[_match[0]]
    return "장르 확인 필요"


def _item(_platform, _url, _title, _cover="", _author="", _description="", _tags=None, _status="확인 필요", _favorites=0):
    if not _title or not _valid_work_url(_platform, _url):
        return None
    _parts = urllib.parse.urlsplit(_cover)
    if _parts.scheme != "https" or not _host_allowed(_parts.hostname or "", _platform["imageHosts"]):
        _cover = "assets/cover-placeholder.svg"
    _tags = [str(_tag) for _tag in (_tags or []) if _tag][:18]
    _genre_name = _tag_genre(_tags)
    _moods = {"로맨스": ["설레는"], "판타지": ["몰입되는"], "무협": ["짜릿한"], "스릴러": ["몰입되는"], "액션": ["짜릿한"], "일상": ["힐링"], "개그": ["유쾌한"], "스포츠": ["뭉클한"]}.get(_genre_name, [])
    return {"id": _platform["key"] + ":" + hashlib.sha256(_url.encode()).hexdigest()[:20], "platformKey": _platform["key"], "platform": _platform["name"], "title": _clean_text(_title)[:150], "author": _author or "작가 정보는 공식 페이지 확인", "description": _clean_text(_description)[:1800], "genre": _genre_name, "tags": list(dict.fromkeys(_moods + _tags)), "status": _status, "days": [], "age": "이용 연령은 공식 페이지 확인", "favorites": max(0, int(_favorites or 0)), "cover": _cover, "url": _url, "source": _url}


def _walk(_value):
    if isinstance(_value, dict):
        yield _value
        for _child in _value.values():
            yield from _walk(_child)
    elif isinstance(_value, list):
        for _child in _value:
            yield from _walk(_child)


def _parse_json_items(_platform, _data):
    _key = _platform["key"]
    _items = []
    for _record in _walk(_data):
        _entry = None
        if _key == "kakaopage" and "series_id" in _record and _record.get("category_uid") == 10 and _record.get("age_grade", 19) < 18:
            _cover = "https://dn-img-page.kakao.com/download/resource?" + urllib.parse.urlencode({"kid": _record.get("thumbnail", ""), "filename": "th3"})
            _entry = _item(_platform, "https://page.kakao.com/content/" + str(_record["series_id"]), _record.get("title"), _cover, _record.get("authors", ""), _record.get("description", ""), [_record.get("sub_category", "")])
        elif _key == "kakaowebtoon" and "seoId" in _record and "title" in _record and not _record.get("adult"):
            _url = "https://webtoon.kakao.com/content/" + urllib.parse.quote(_record["seoId"], safe="") + "/" + str(_record["id"])
            _entry = _item(_platform, _url, _record["title"], _record.get("featuredCharacterImageA", ""), " / ".join(dict.fromkeys(_artist["name"] for _artist in _record.get("authors", []) if _artist.get("type") != "PUBLISHER")), _record.get("catchphraseTwoLines", ""), [_record.get("genre", "")])
        elif _key == "bomtoon" and "contentsId" in _record and _record.get("contentsType") in {"comic", "cartoon"} and not _record.get("isAdult"):
            _covers = _record.get("thumbnail", [])
            _cover = next((_image["imagePath"] for _image in _covers if _image.get("thumbnailType") == "VERTICAL"), _covers[0].get("imagePath", "") if _covers else "")
            _entry = _item(_platform, "https://www.bomtoon.com/detail/" + str(_record["alias"]), _record.get("title"), _cover, " / ".join(_record.get("author", [])), "", _record.get("tags", []))
        elif _key == "lezhin" and "alias" in _record and "genres" in _record and "id" in _record and not _record.get("adult"):
            _cover = "https://ccdn.lezhin.com/v2/comics/" + str(_record["id"]) + "/images/tall.jpg"
            _entry = _item(_platform, "https://www.lezhin.com/ko/comic/" + _record["alias"], _record.get("title"), _cover, " / ".join(_artist["name"] for _artist in _record.get("artists", []) if _artist.get("role") not in {"publisher", "label"}), "", _record.get("genres", []) + _record.get("tags", []), _favorites=_record.get("subscriptions", 0))
        elif _key == "ridi" and "ageLimit" in _record and isinstance(_record.get("title"), dict) and not _record.get("isAdultOnly") and _record.get("ageLimit", 19) < 18:
            if not any(_category.get("genre") in {"webtoon", "bl_webtoon", "romance_webtoon"} or _category.get("id") in {4800, 4900, 4100} for _category in _record.get("categories", [])) and _record.get("style", {}).get("layout") not in {"default-webtoon", "webtoon"}:
                continue
            _id = str(_record["id"])
            _entry = _item(_platform, "https://ridibooks.com/books/" + _id, _record["title"].get("main"), "https://img.ridicdn.net/cover/" + _id + "/xxlarge", " / ".join(_artist["name"] for _artist in _record.get("authors", [])), _record.get("introduction", {}).get("description", ""), [_category.get("name", "") for _category in _record.get("categories", [])])
        if _entry:
            _items.append(_entry)
    _deduplicated = {}
    for _entry in _items:
        _deduplicated.setdefault(_entry["id"], _entry)
    return list(_deduplicated.values())


def _parse_html_items(_platform, _document):
    _parser = _PublicHTML()
    _parser.feed(_document)
    _items = []
    if _platform["key"] == "ridi":
        for _data in _parser.json_data:
            _items.extend(_parse_json_items(_platform, _data))
        return _items
    for _anchor in _parser.links:
        _url = urllib.parse.urljoin(_platform["home"], html.unescape(_anchor["url"]))
        if _platform["key"] == "toomics" and "/index/bannerTracking" in _url:
            _url = urllib.parse.urljoin(_platform["home"], urllib.parse.parse_qs(urllib.parse.urlsplit(_url).query).get("u", [""])[0])
        _parts = urllib.parse.urlsplit(_url)
        _query = urllib.parse.parse_qs(_parts.query)
        _query = { _name: _query[_name][0] for _name in ("productNo", "webtoon_num", "tcode") if _name in _query }
        _url = urllib.parse.urlunsplit((_parts.scheme, _parts.netloc, _parts.path.rstrip("/"), urllib.parse.urlencode(_query), ""))
        if not _valid_work_url(_platform, _url):
            continue
        _title = re.sub(r"\s+", " ", _anchor["title"] or _anchor["text"]).strip()
        if not _title or _title in {"표지", "썸네일", "cover", "이미지"}:
            continue
        _cover = urllib.parse.urljoin(_platform["home"], html.unescape(_anchor["cover"]))
        _tags = re.findall(r"#([^#\s]+)", _anchor["text"])
        if _platform["key"] == "mootoon":
            if " 웹툰 " not in _title:
                continue
            _title, _category = _title.split(" 웹툰 ", 1)
            _title = re.sub(r"^\d+\s+", "", _title)
            _tags = [_category.split()[0]]
        _entry = _item(_platform, _url, _title, _cover, _tags=_tags, _status="완결" if "완결" in _anchor["text"] else "확인 필요")
        if _entry:
            _items.append(_entry)
    _deduplicated = {}
    for _entry in _items:
        _deduplicated.setdefault(_entry["id"], _entry)
    return list(_deduplicated.values())


@lru_cache(maxsize=512)
def _enrich(_key, _url, _bucket):
    _platform = _BY_KEY[_key]
    if not _valid_work_url(_platform, _url):
        raise ValueError("Invalid official title URL")
    _path = _CACHE / "metadata" / (_key + "-" + hashlib.sha256(_url.encode()).hexdigest()[:20] + ".json")
    if _path.exists() and time.time() - _path.stat().st_mtime < 86400:
        return json.loads(_path.read_text(encoding="utf-8"))
    _parser = _PublicHTML()
    _parser.feed(_fetch(_url, _platform))
    _path.parent.mkdir(parents=True, exist_ok=True)
    _temporary = _path.with_suffix(".tmp")
    _temporary.write_text(json.dumps(_parser.meta, ensure_ascii=False), encoding="utf-8")
    _temporary.replace(_path)
    return _parser.meta


def _search_url(_platform, _query):
    return _platform["searchUrl"].replace("{query}", urllib.parse.quote(_query, safe=""))


@lru_cache(maxsize=192)
def _search_platform(_key, _query, _bucket, _page=0, _size=25, _complete=False):
    _platform = _BY_KEY[_key]
    _adapter = _platform["adapter"]
    _url = _search_url(_platform, _query)
    if _adapter in {"link", "naver"}:
        return [], {"key": _key, "status": "link_only", "url": _url, "matched": 0}
    if _adapter == "kakaopage":
        _api = "https://bff-page.kakao.com/api/gateway/api/v2/search/series?" + urllib.parse.urlencode({"keyword": _query, "category_uid": 10, "is_complete": str(_complete).lower(), "sort_type": "ACCURACY", "page": _page, "size": _size})
    elif _adapter == "kakaowebtoon":
        _api = "https://gateway-kw.kakao.com/search/v2/content?" + urllib.parse.urlencode({"limit": _size, "offset": _page * _size, "word": _query})
    elif _adapter == "bomtoon":
        _api = "https://www.bomtoon.com/api/balcony-search-api/search?" + urllib.parse.urlencode({"searchText": _query, "contentsType": "COMIC", "page": _page, "size": _size, "device": "WEB", "isExcludeAdult": "true", "onlyComplete": str(_complete).lower(), "isSearchTool": "true", "sortType": "ACCURACY"})
    elif _adapter == "lezhin":
        _api = "https://www.lezhin.com/lz-api/v2/advanced-search?" + urllib.parse.urlencode({"q": urllib.parse.quote(_query, safe=""), "t": "all", "order": "popular", "offset": _page * _size, "limit": _size})
    else:
        _api = _url
        if _page:
            _parts = urllib.parse.urlsplit(_api)
            _parameters = urllib.parse.parse_qsl(_parts.query) + [("page", str(_page + 1))]
            _api = urllib.parse.urlunsplit((_parts.scheme, _parts.netloc, _parts.path, urllib.parse.urlencode(_parameters), ""))
    try:
        _body = _fetch(_api, _platform)
        _data = json.loads(_body) if _adapter in {"kakaopage", "kakaowebtoon", "bomtoon", "lezhin"} else None
        if _data is not None and (_data.get("code", 0) != 0 or str(_data.get("result_code", 0)) != "0"):
            raise ValueError("Public search rejected the request")
        _items = _parse_json_items(_platform, _data) if _data is not None else _parse_html_items(_platform, _body)
        if _complete and _adapter in {"kakaopage", "bomtoon"}:
            _items = [{**_item, "status": "완결"} for _item in _items]
        if "{query}" not in _platform["searchUrl"]:
            _items = [_item for _item in _items if _query in _item["title"] or _query in " ".join(_item["tags"])]
        _has_more = len(_items) >= _size
        if _adapter == "kakaopage":
            _has_more = not _data.get("result", {}).get("is_end", True)
        elif _adapter == "kakaowebtoon":
            _has_more = not _data.get("meta", {}).get("pagination", {}).get("last", True)
        elif _adapter == "lezhin":
            _has_more = bool(_data.get("hasNext"))
        elif _adapter == "bomtoon":
            _has_more = (_page + 1) * _size < _data.get("data", {}).get("totalResults", 0)
        return _items[:_size], {"key": _key, "status": "ok", "url": _url, "matched": len(_items[:_size]), "hasMore": _has_more, "mode": "search" if "{query}" in _platform["searchUrl"] else "public_list"}
    except Exception:
        return [], {"key": _key, "status": "unavailable", "url": _url, "matched": 0}


def _search_platforms(_query, _keys=None):
    _keys = _keys or [_platform["key"] for _platform in _REGISTRY if _platform["key"] != "naver"]
    _items, _statuses = [], []
    with ThreadPoolExecutor(max_workers=6) as _executor:
        _futures = [_executor.submit(_search_platform, _key, _query, int(time.time() // 600)) for _key in _keys if _key in _BY_KEY and _key != "naver"]
        for _future in _futures:
            _found, _status = _future.result()
            _items.extend({**_item, "discovery": "web"} for _item in _found)
            _statuses.append(_status)
    return _items, _statuses


def _collect_platforms(_progress=None):
    _items, _health = {}, {}
    _queries = ["판타지", "로맨스", "무협", "액션", "드라마", "스릴러", "공포", "스포츠", "일상", "개그", "BL", "학원", "회귀", "성장", "복수", "이세계", "모험", "가족"]
    def _collect(_platform):
        _key = _platform["key"]
        _found, _status = {}, {"key": _key, "status": "link_only"}
        if _platform["adapter"] in {"link", "naver"}:
            return [], _status
        _status["status"] = "unavailable"
        _size = 100 if _key in {"kakaopage", "kakaowebtoon"} else 30
        _terms = _queries if "{query}" in _platform["searchUrl"] else ["웹툰"]
        _failed = 0
        _requests = 0
        for _complete in ([False, True] if _key in {"kakaopage", "bomtoon"} else [False]):
            for _query in _terms:
                for _page in range(8 if _key in {"kakaopage", "kakaowebtoon", "lezhin", "bomtoon"} else 4):
                    _batch, _latest = _search_platform(_key, _query, int(time.time() // 600), _page, _size, _complete)
                    _requests += 1
                    _failed += _latest["status"] == "unavailable"
                    if _latest["status"] == "ok":
                        _status = _latest
                    _new = 0
                    for _entry in _batch:
                        _new += _entry["id"] not in _found
                        if _entry["id"] in _found and _entry["status"] == "확인 필요":
                            _entry = {**_entry, "status": _found[_entry["id"]]["status"]}
                        _found[_entry["id"]] = _entry
                    if _latest["status"] != "ok" or not _latest.get("hasMore") or (_page and not _new and not _complete):
                        break
            if _progress:
                _progress(_key + ": discovered " + str(len(_found)) + " titles; " + str(_requests) + " public pages.")
        return list(_found.values()), {**_status, "failedRequests": _failed, "pages": _requests}
    with ThreadPoolExecutor(max_workers=4) as _executor:
        for _found, _status in _executor.map(_collect, _REGISTRY):
            _items.update({_item["id"]: _item for _item in _found})
            _health[_status["key"]] = _status
    # Public home lists also contribute titles when no keyword search is exposed.
    for _platform in _REGISTRY:
        if _platform["adapter"] == "html":
            try:
                _paths = {"toptoon": ["/weekly", "/ranking"], "toomics": ["/webtoon/weekly", "/webtoon/finish/all", "/webtoon/toon_list/display/G2"], "peanutoon": ["/cmweek.html", "/cmgenre.html"]}.get(_platform["key"], [])
                for _url in [_platform["home"], *(urllib.parse.urljoin(_platform["home"], _path) for _path in _paths)]:
                    try:
                        for _item in _parse_html_items(_platform, _fetch(_url, _platform)):
                            _items.setdefault(_item["id"], _item)
                    except Exception:
                        continue
                if any(_item["platformKey"] == _platform["key"] for _item in _items.values()):
                    _health[_platform["key"]] = {"key": _platform["key"], "status": "ok", "mode": "public_list"}
            except Exception:
                pass
    _values = list(_items.values())
    if _progress:
        _progress("Enriching " + str(len(_values)) + " public title records with cached official metadata.")
    def _describe(_entry):
        # Search already supplies a full synopsis and artwork for these records.
        if _entry["platformKey"] in {"kakaowebtoon", "ridi"} and len(_entry["description"]) >= 80:
            return _entry
        try:
            _meta = _enrich(_entry["platformKey"], _entry["url"], int(time.time() // 86400))
            _description = _meta.get("og:description", "")
            if _description and not any(_generic in _description for _generic in ["오리지널 독점 웹툰", "웹툰, 웹소설, 전자책 모두", "한국 일본 최신 웹툰"]):
                _entry = {**_entry, "description": _clean_text(_description)[:1800]}
            _title = _clean_text(_meta.get("og:title", ""))
            _title = re.sub(r"\s*[-|]\s*(?:웹툰|만화|미스터블루|리디|레진|탑툰|봄툰|피너툰|북큐브).*$", "", _title)
            _title = re.sub(r"^(?:피너툰|북큐브|레진코믹스)\s*[-|:]\s*", "", _title)
            _title = re.sub(r"^\[탑툰\]\s*|::피너툰$", "", _title)
            if _entry["platformKey"] == "mootoon":
                _match = re.fullmatch(r"(.+)\s+\((.+)\)\s*:\s*무툰", _title)
                if _match:
                    _entry = {**_entry, "title": _match[1], "author": _match[2]}
                _title = ""
            if _BY_KEY[_entry["platformKey"]]["adapter"] == "html" and _title and _title not in {_entry["platform"], "카카오페이지", "피너툰 (Peanutoon)"} and not _title.startswith("피너툰 (Peanutoon)"):
                _entry = {**_entry, "title": _title[:150]}
            _extra_tags = re.findall(r"#([가-힣A-Za-z/]+)", _description)
            _extra_tags = [_tag.strip() for _tag in _extra_tags if _tag.strip()]
            if _entry["genre"] == "장르 확인 필요" and _extra_tags:
                _entry = {**_entry, "genre": _tag_genre(_extra_tags), "tags": list(dict.fromkeys(_entry["tags"] + _extra_tags))[:18]}
            _cover = _meta.get("og:image", "")
            if _cover and urllib.parse.urlsplit(_cover).scheme == "https" and not re.search(r"(?:logo|ogImage|/icon|shared/)", _cover, re.I) and _host_allowed(urllib.parse.urlsplit(_cover).hostname or "", _BY_KEY[_entry["platformKey"]]["imageHosts"]):
                _entry = {**_entry, "cover": _cover}
        except Exception:
            pass
        if re.search(r"배너|^리뷰\s*\d|^UPDATE$|^TYPE$|^썸네일$", _entry["title"], re.I):
            return None
        return _entry
    with ThreadPoolExecutor(max_workers=8) as _executor:
        _values = []
        for _index, _entry in enumerate(_executor.map(_describe, list(_items.values())), 1):
            if _entry:
                _values.append(_entry)
            if _progress and _index % 250 == 0:
                _progress("Enriched " + str(_index) + "/" + str(len(_items)) + " titles.")
    _counts = {_platform["key"]: sum(_item["platformKey"] == _platform["key"] for _item in _values) for _platform in _REGISTRY}
    _platforms = [{**_platform, **_health.get(_platform["key"], {"status": "link_only"}), "count": _counts[_platform["key"]]} for _platform in _REGISTRY if _platform["key"] != "naver"]
    _CACHE.mkdir(parents=True, exist_ok=True)
    _path = _CACHE / "snapshot.json"
    _temporary = _path.with_suffix(".tmp")
    _temporary.write_text(json.dumps({"items": _values, "platforms": _platforms}, ensure_ascii=False), encoding="utf-8")
    _temporary.replace(_path)
    return _values, _platforms


def _platform_registry(_catalog):
    _states = {_platform["key"]: _platform for _platform in _catalog.get("platforms", [])}
    return [{**_platform, **_states.get(_platform["key"], {}), "count": sum((_item.get("platformKey", "naver") == _platform["key"]) for _item in _catalog["items"]), "status": _states.get(_platform["key"], {}).get("status", "ok" if _platform["key"] == "naver" else "link_only")} for _platform in _REGISTRY]
