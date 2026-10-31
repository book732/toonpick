"""Collect public title metadata and record each domestic platform's actual status."""

import sys
import re
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def _main():
    sys.path.insert(0, str(_ROOT))
    from services.catalog import _CACHE, _get_catalog, _write_json
    from services.platforms import _collect_platforms, _platform_registry

    _catalog = _get_catalog()
    _items, _platforms = _collect_platforms(lambda _message: print(_message, flush=True))
    _by_id = {_item["id"]: _item for _item in _catalog["items"] if not re.search(r"배너|^리뷰\s*\d|^UPDATE$|^TYPE$", _item["title"], re.I)}
    _by_id.update({_item["id"]: _item for _item in _items})
    _catalog = {**_catalog, "updatedAt": datetime.now(timezone.utc).isoformat(), "items": list(_by_id.values()), "platforms": _platforms}
    _catalog["platforms"] = _platform_registry(_catalog)
    _write_json(_CACHE / "catalog.json", _catalog)
    _write_json(_ROOT / "data/webtoons.json", _catalog)
    for _platform in _catalog["platforms"]:
        print(_platform["key"] + ": " + _platform["status"] + ", " + str(_platform["count"]) + " titles", flush=True)


if __name__ == "__main__":
    _main()
