"""Discover and refresh official webtoon metadata without a manually maintained title list."""

import json
import sys
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]


def _main():
    sys.path.insert(0, str(_ROOT))
    from services.catalog import _collect_catalog

    _catalog = _collect_catalog(lambda _message: print(_message, flush=True))
    (_ROOT / "data/webtoons.json").write_text(
        json.dumps(_catalog, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    print(f"Updated {len(_catalog['items'])} official titles; {_catalog['collection']['failedRequests']} failed requests.")


if __name__ == "__main__":
    _main()