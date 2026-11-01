"""Read seasonal broadcast metadata without implying Korean streaming availability."""

import json
import re
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from services.recommendations import _RecommendationError

_SEASONS = ("WINTER", "SPRING", "SUMMER", "FALL")
_KST = timezone(timedelta(hours=9))
_QUERY = """query($year:Int,$season:MediaSeason,$page:Int){
  Page(page:$page,perPage:8){pageInfo{hasNextPage}
    media(type:ANIME,seasonYear:$year,season:$season,isAdult:false,sort:POPULARITY_DESC){
      id title{native romaji english} synonyms seasonYear season startDate{year month day}
      status format isAdult coverImage{large}
    }
  }
}"""


def _schedule_period(_now=None):
    _now = (_now or datetime.now(_KST)).astimezone(_KST)
    return _now.year, (_now.month - 1) // 3 + 1


@lru_cache(maxsize=1)
def _schedule_aliases():
    return json.loads((Path(__file__).resolve().parents[1] / "data/anime_aliases.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=64)
def _fetch_schedule(_year, _quarter, _page, _bucket):
    _request = urllib.request.Request("https://graphql.anilist.co", data=json.dumps({"query": _QUERY, "variables": {"year": _year, "season": _SEASONS[_quarter - 1], "page": _page}}).encode(), headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "ToonPick/1.0"})
    try:
        with urllib.request.urlopen(_request, timeout=12) as _response:
            _data = json.loads(_response.read(2 * 1024 * 1024))
        _result = _data["data"]["Page"]
        if _data.get("errors") or not isinstance(_result["media"], list) or not isinstance(_result["pageInfo"]["hasNextPage"], bool):
            raise ValueError("Invalid seasonal response")
        _items, _seen = [], set()
        for _item in _result["media"]:
            _id = _item["id"]
            if type(_id) is not int or _id < 1 or _id in _seen or _item.get("isAdult") is True or _item.get("seasonYear") != _year or _item.get("season") != _SEASONS[_quarter - 1]:
                continue
            _titles = _item["title"]
            _korean = _schedule_aliases().get(str(_id)) or next((_name for _name in _item.get("synonyms", []) if isinstance(_name, str) and re.search(r"[가-힣]", _name)), None)
            _title = _korean or _titles.get("native") or _titles.get("english") or _titles.get("romaji")
            if not isinstance(_title, str) or not _title.strip():
                continue
            _cover = (_item.get("coverImage") or {}).get("large") or ""
            _url = urlsplit(_cover)
            if _url.scheme != "https" or _url.hostname not in {"s4.anilist.co", "s3.anilist.co"} or _url.username or _url.password or _url.port:
                _cover = "/assets/cover-placeholder.svg"
            _date = _item.get("startDate") or {}
            _items.append({"id": _id, "title": _title[:240], "originalTitle": not bool(_korean), "cover": _cover, "url": "https://anilist.co/anime/" + str(_id), "format": _item.get("format"), "status": _item.get("status"), "startDate": {_key: _date.get(_key) if type(_date.get(_key)) is int else None for _key in ("year", "month", "day")}})
            _seen.add(_id)
        return {"items": _items, "hasNextPage": _result["pageInfo"]["hasNextPage"], "year": _year, "quarter": _quarter, "page": _page, "updatedAt": datetime.now(_KST).isoformat(), "source": "AniList", "sourceUrl": "https://anilist.co/search/anime?year=" + str(_year) + "&season=" + _SEASONS[_quarter - 1]}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise _RecommendationError("방영 일정을 불러오지 못했어요. 잠시 후 다시 시도해주세요.", 502) from None


def _anime_schedule(_parameters):
    _current_year, _current_quarter = _schedule_period()
    try:
        _year = int(_parameters.get("year", [str(_current_year)])[0])
        _quarter = int(_parameters.get("quarter", [str(_current_quarter)])[0])
        _page = int(_parameters.get("page", ["1"])[0])
    except (ValueError, TypeError, IndexError):
        raise _RecommendationError("연도와 분기를 확인해주세요.", 400) from None
    if _year not in (_current_year, _current_year + 1) or not 1 <= _quarter <= 4 or not 1 <= _page <= 100:
        raise _RecommendationError("올해와 다음 해의 1~4분기만 조회할 수 있어요.", 400)
    return {**_fetch_schedule(_year, _quarter, _page, int(time.time() // 3600)), "currentYear": _current_year}
