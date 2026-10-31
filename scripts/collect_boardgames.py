"""Extend the catalogue from public Korean distributor product facts, excluding accessories."""

import html
import json
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]
_CACHE = _ROOT / ".cache/boardgame-sources"
_HOME = "https://www.koreaboardgames.com"
_CATEGORY = "/product/1depth/list?dspCateFirst=FC00004734"
_EXCLUDE = r"확장|프로모|슬리브|매트|입장권|직소|브릭|그래비트랙스|플레이모빌|루빅|리필|주사위\s*세트|주사위\s*트레이|카드\s*홀더|카드\s*홀다|카드\s*스탠드|카드\s*보호|확팩|오거나이저|액세서리|악세서리|덱\s*박스|덱박스|보관함|트레이딩|컬렉션\s*카드|부스터|지도\s*:|스코어\s*시트|점수표|추가\s*카드|집정관\s*팩|컴포넌트|플레이\s*토큰|토큰\s*세트|리플레이\s*팩|보관\s*박스|선물\s*포장|정리함|공\s*세트|교체용|보충용"


def _canonical_title(_title):
    _title = re.sub(r"\[[^]]*\]|\([^)]*(?:예약|판매|특가|할인|한국어|한글|영문|기념|개정|에디션|판본|핑크|블루|레드|블랙|화이트|민트)[^)]*\)", "", _title)
    _title = re.sub(r"\s*(?:빅\s*박스|클래식|컴팩트|트래블|보이저|딜럭스|디럭스|포켓|틴케이스|미니|한글판|한국어판|영문판|개정\s*\d*판|\d+판|리뉴얼|신판|구판|\d+주년\s*기념판|20\d{2}\s*에디션)\s*$", "", _title)
    _title = re.sub(r"[\W_]+", "", _title).casefold()
    _plain = re.sub(r"신비아파트|포켓몬스터|포켓몬|미키와친구들|마인크래프트|카카오프렌즈|라인프렌즈|동물의숲|슈퍼마리오|케이팝데몬헌터스|티니핑|bts", "", _title)
    _plain = re.sub(r"(?:콤팩트|컴팩트|딜럭스|디럭스|클래식|썸썸)+$", "", _plain)
    if _plain in {"루미큐브", "루미큐브퍼니백", "루미큐브인피니티", "루미큐브더블엑스엘", "루미큐브네오", "루미큐브셀렉트", "루미큐브엑스피", "루미큐브틴", "루미큐브셀렉트빈티지", "루미큐브그래피티", "루미큐브알토"}:
        return "루미큐브"
    if _plain in {"원카드", "도블", "도블공룡", "우노", "자이언트우노", "우노카드게임", "할리갈리", "오델로", "오델로게임파티"}:
        return {"도블공룡": "도블", "자이언트우노": "우노", "우노카드게임": "우노", "오델로게임파티": "오델로"}.get(_plain, _plain)
    if _plain == "루미큐브마이퍼스트":
        return _plain
    if _plain in {"크로키놀", "크로키놀라이트", "크로키놀챔피언십"}:
        return "크로키놀"
    if _plain == "쿠키박스":
        return _plain
    if re.fullmatch(r"키포지.*(?:듀얼스타터팩|스타터세트)", _title):
        return "키포지"
    if re.fullmatch(r"체스앤체커|페레르.*체스세트[ml]?|그랜드마스터카스파로프실버브론즈체스세트", _title):
        return "체스"
    return {"레지스탕스아발론": "아발론", "스플랜더": "스플렌더", "젝스님트": "식스님트"}.get(_title, _title)


def _excluded_title(_title):
    if re.search(r"아컴호러\s*카드", _title) and not re.fullmatch(r"아컴호러\s*카드게임\s*(?:개정판|기본판)?", _title):
        return True
    if re.search(r"스트레치\s*골|언어\s*팩|미니어처\s*(?:세트|팩)|피규어\s*(?:세트|팩)|인서트|업그레이드\s*팩|메탈\s*코인|컬렉터스\s*박스|만들기\s*키트", _title):
        return True
    if re.search(r"\[세트\]|시리즈\s*\d+종|\d+종\s*세트|히어로\s*합본|선물세트|개인판|화폐\s*토큰|게임\s*플레이\s*올인|올인원| \+ ", _title):
        return True
    if re.search(r"독립|단독\s*플레이|스탠드얼론", _title):
        _title = re.sub(r"확장(?:판|팩)?", "", _title)
    return bool(re.search(_EXCLUDE, _title))


def _products(_listing):
    _items = []
    for _match in re.finditer(r'<a\s+href="/product/detail\?prdCd=([A-Z0-9]+)"[^>]*>(.*?)</a>', _listing, re.S):
        _title = re.search(r'<div class="item_title">(.*?)</div>', _match[2], re.S)
        if _title:
            _items.append((_match[1], _text(_title[1])))
    return _items


def _page_count(_listing):
    _match = re.search(r'name="totalPageCnt"\s+value="(\d+)"', _listing)
    if not _match or not 1 <= int(_match[1]) <= 200:
        raise ValueError("Invalid catalogue pagination; retained the previous catalogue")
    return int(_match[1])


def _get(_url, _name):
    _path = _CACHE / _name
    if _path.exists():
        return _path.read_text(encoding="utf-8")
    for _attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(_url, headers={"User-Agent": "Mozilla/5.0"}), timeout=25) as _response:
                _body = _response.read(6 * 1024 * 1024).decode()
            _path.write_text(_body, encoding="utf-8")
            time.sleep(0.5)
            return _body
        except Exception:
            if _attempt == 2:
                raise
            time.sleep(3)


def _text(_value):
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", _value))).strip()


def _main():
    _CACHE.mkdir(parents=True, exist_ok=True)
    _path = _ROOT / "data/boardgames.json"
    _data = json.loads(_path.read_text(encoding="utf-8"))
    _verified = {_entry["sku"] for _entry in json.loads((_ROOT / "data/boardgames_verified_products.json").read_text(encoding="utf-8"))}
    _report = {"sourceUrl": _HOME + _CATEGORY, "startedAt": datetime.now(timezone.utc).isoformat(), "previousCount": len(_data["games"]), "target": 1000, "excluded": [], "duplicates": [], "failures": []}
    _first = _get(_HOME + _CATEGORY, "category-FC00004734-1.html")
    _pages = _page_count(_first)
    _all_products = dict(_products(_first))
    # Read the complete supplied category, rather than guessing a fixed page limit.
    with ThreadPoolExecutor(max_workers=3) as _workers:
        _jobs = {_workers.submit(_get, _HOME + _CATEGORY + "&nowPageNo=" + str(_page), "category-FC00004734-" + str(_page) + ".html"): _page for _page in range(2, _pages + 1)}
        _listings = {1: _first}
        for _job in as_completed(_jobs):
            _listings[_jobs[_job]] = _job.result()
        for _page in sorted(_listings):
            _all_products.update(_products(_listings[_page]))
    _report["sourcePages"] = _pages
    _report["sourceProducts"] = len(_all_products)
    _expected = re.search(r'name="recordCnt"\s+value="(\d+)"', _first)
    _report["expectedSourceProducts"] = int(_expected[1]) if _expected else None
    _accessories = set()
    for _category in ("SC00004749", "SC00004746"):
        _url = _HOME + "/product/2depth/list?dspCateFirst=FC00004734&dspCateSecond=" + _category + "&lv3=more"
        _listing = _get(_url, "excluded-" + _category + "-1.html")
        for _page in range(1, _page_count(_listing) + 1):
            _body = _listing if _page == 1 else _get(_url + "&nowPageNo=" + str(_page), "excluded-" + _category + "-" + str(_page) + ".html")
            _accessories.update(_sku for _sku, _title in _products(_body))
    _source_by_name = {_canonical_title(_title): _sku for _sku, _title in _all_products.items() if _sku not in _accessories and not _excluded_title(_title)}
    # Resolve curated entries before indexing imported records to preserve their stable IDs.
    for _game in _data["games"]:
        if _game.get("bggId"):
            continue
        _sku = next((_source_by_name[_canonical_title(_alias)] for _alias in [_game["title"], *_game["aliases"]] if _canonical_title(_alias) in _source_by_name), None)
        if _sku:
            _detail = _get(_HOME + "/product/detail?prdCd=" + _sku, "detail-" + _sku + ".html")
            _bgg = re.search(r"bggId\s*:\s*'(\d+)'", _detail)
            if _bgg:
                _game["bggId"] = _bgg[1]
    _games, _names, _ids = [], {}, {}
    for _game in _data["games"]:
        _name = _canonical_title(_game["title"])
        _bgg_id = _game.get("bggId")
        if _excluded_title(_game["title"]) or _game["url"].split("prdCd=")[-1] in _accessories:
            _report["excluded"].append({"title": _game["title"], "reason": "existing_accessory_or_expansion"})
            continue
        _duplicate = _names.get(_name) or _ids.get(_bgg_id)
        if _duplicate:
            _report["duplicates"].append({"title": _game["title"], "retained": _duplicate["title"]})
            _duplicate["aliases"] = list(dict.fromkeys(_duplicate["aliases"] + _game["aliases"]))
            continue
        _games.append(_game)
        for _alias in [_game["title"], *_game["aliases"]]:
            _names[_canonical_title(_alias)] = _game
        if _bgg_id:
            _ids[_bgg_id] = _game
    _candidates = []
    _existing_skus = {_game["url"].split("prdCd=")[-1] for _game in _games if "prdCd=" in _game["url"]}
    for _sku, _title in _all_products.items():
        if _sku in _accessories or _excluded_title(_title):
            _report["excluded"].append({"sku": _sku, "title": _title, "reason": "accessory_or_expansion"})
        elif _sku not in _existing_skus:
            _candidates.append((_sku, _title))
    print("Category products", len(_all_products), "existing unique games", len(_games), "detail candidates", len(_candidates), flush=True)
    _details = {}
    with ThreadPoolExecutor(max_workers=3) as _workers:
        _jobs = {_workers.submit(_get, _HOME + "/product/detail?prdCd=" + _sku, "detail-" + _sku + ".html"): (_sku, _title) for _sku, _title in _candidates}
        for _index, _job in enumerate(as_completed(_jobs), 1):
            _sku, _title = _jobs[_job]
            try:
                _details[_sku] = _job.result()
            except (OSError, ValueError) as _error:
                _report["failures"].append({"sku": _sku, "title": _title, "error": str(_error)})
            if _index % 25 == 0:
                print("Metadata", _index, "/", len(_jobs), flush=True)
    for _sku, _title in _candidates:
        if _sku not in _details:
            continue
        _url = _HOME + "/product/detail?prdCd=" + _sku
        _detail = _details[_sku]
        _bgg = re.search(r"bggId\s*:\s*'(\d+)'", _detail)
        _name = _canonical_title(_title)
        _duplicate = _names.get(_name) or _ids.get(_bgg[1] if _bgg else None)
        if _duplicate:
            _report["duplicates"].append({"sku": _sku, "title": _title, "retained": _duplicate["title"]})
            _duplicate["aliases"] = list(dict.fromkeys(_duplicate["aliases"] + [_title]))
            _names[_name] = _duplicate
            if _bgg and not _duplicate.get("bggId"):
                _duplicate["bggId"] = _bgg[1]
            if _bgg:
                _ids[_bgg[1]] = _duplicate
            continue
        _facts = { _text(_m[1]): _text(_m[2]) for _m in re.finditer(r'<div class="htit">(.*?)</div>\s*<p class="desc"[^>]*>(.*?)</p>', _detail, re.S)}
        _players = [int(_n) for _n in re.findall(r"\d+", _facts.get("인원", ""))]
        _minutes = [int(_n) for _n in re.findall(r"\d+", _facts.get("소요시간", ""))]
        _age = re.search(r"\d+", _facts.get("연령", ""))
        # Scope artwork to the sticky product summary, excluding shared delivery banners.
        _image = re.search(r'<div class="sticky-buy">.*?<div class="thumb">\s*<img[^>]+src="(https://cdnfile.koreaboardgames.com/[^"?]+\.(?:jpg|jpeg|png|webp))"', _detail, re.S)
        if not _image or not (_players or _bgg or _sku in _verified):
            _report["excluded"].append({"sku": _sku, "title": _title, "reason": "missing_verified_game_identity_or_cover"})
            continue
        _genres = _facts.get("장르", "")
        _mechanisms = [_v.strip() for _v in _facts.get("시스템", "").split(",") if _v.strip()]
        _mapping = {"전략": ["전략", "경제", "문명", "영토", "전쟁", "탐험"], "협력": ["협력"], "파티": ["파티", "유머"], "가족": ["어린이", "가족", "동물"], "추리": ["추리", "미스터리", "살인"], "카드": ["카드"], "퍼즐": ["추상", "퍼즐"], "심리전": ["블러핑", "심리"]}
        _labels = [_k for _k, _words in _mapping.items() if any(_w in _genres + " " + " ".join(_mechanisms) for _w in _words)]
        if len(_players) > 1 and _players[0] == _players[-1] == 2:
            _labels.append("2인")
        _game = {"slug": "kbg-" + (_bgg[1] if _bgg else "product-" + _sku.lower()), "title": _title, "aliases": [_title], "publisher": "코리아보드게임즈 · 국내 유통 정보", "designer": "제작자 정보는 공식 페이지 확인", "minPlayers": min(_players) if _players else None, "maxPlayers": (None if len(_players) == 1 and re.search(r"\+|이상", _facts.get("인원", "")) else max(_players)) if _players else None, "minMinutes": min(_minutes) if _minutes else 0, "maxMinutes": max(_minutes) if _minutes else None, "minAge": int(_age[0]) if _age else None, "difficulty": 0, "editorial": True, "genres": _labels or ["기타"], "mechanisms": _mechanisms, "moods": ["함께하는"] if "협력" in _labels else [], "mode": "협력" if "협력" in _labels else "공식 규칙 확인", "description": _title + ". 공식 표기: " + " · ".join(_k + " " + _v for _k, _v in _facts.items()) + ". 세부 규칙과 구성은 제품 페이지에서 확인해주세요.", "url": _url, "cover": html.unescape(_image[1]), "coverSource": html.unescape(_image[1]), "coverSourcePage": _url, "bggId": _bgg[1] if _bgg else None, "editionNote": "국내 공식 유통사 상품 표기 기준. 난이도 미확인 작품은 난이도 제한 추천에서 제외합니다."}
        _games.append(_game)
        _names[_name] = _game
        if _bgg:
            _ids[_bgg[1]] = _game
        print("Board games", len(_games), _title, flush=True)
    if _report["failures"]:
        raise RuntimeError("Some source requests failed; retained the previous catalogue")
    if len(_all_products) != _report["expectedSourceProducts"] or len(_games) < 30:
        raise RuntimeError("Incomplete source traversal or unexpected catalogue loss; retained the previous catalogue")
    _report["finalCount"] = len(_games)
    _retained_skus = {_game["url"].split("prdCd=")[-1] for _game in _games if "prdCd=" in _game["url"]} & _all_products.keys()
    _excluded_skus = {_entry["sku"] for _entry in _report["excluded"] if "sku" in _entry} - _retained_skus
    _duplicate_skus = {_entry["sku"] for _entry in _report["duplicates"] if "sku" in _entry} - _retained_skus - _excluded_skus
    _unaccounted = _all_products.keys() - _retained_skus - _excluded_skus - _duplicate_skus
    if _unaccounted:
        raise RuntimeError("Unaccounted category products; retained the previous catalogue")
    _report["sourceCounts"] = {"retainedProducts": len(_retained_skus), "excludedProducts": len(_excluded_skus), "duplicateProducts": len(_duplicate_skus)}
    _previous_slugs = {_old["slug"] for _old in _data["games"]}
    _report["newUniqueGames"] = sum(_game["slug"] not in _previous_slugs for _game in _games)
    _report["completedAt"] = datetime.now(timezone.utc).isoformat()
    (_ROOT / "data/boardgames_collection_report.json").write_text(json.dumps(_report, ensure_ascii=False, indent=2), encoding="utf-8")
    _data.update(games=_games, updatedAt=datetime.now(timezone.utc).isoformat())
    _temporary = _path.with_suffix(".tmp")
    _temporary.write_text(json.dumps(_data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    _temporary.replace(_path)
    print("Saved", len(_games), "verified board games", flush=True)


if __name__ == "__main__":
    _main()
