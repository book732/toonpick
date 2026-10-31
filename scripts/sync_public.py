"""Keep Vercel's static directory aligned with the local development entrypoint."""

import shutil
from pathlib import Path


def _main():
    _root = Path(__file__).resolve().parents[1]
    _public = _root / "public"
    _public.mkdir(exist_ok=True)
    from build_anime_page import _main as _build_anime
    _build_anime()
    from build_boardgames_page import _main as _build_boardgames
    _build_boardgames()
    shutil.copy2(_root / "index.html", _public / "index.html")
    for _directory in ("css", "js", "assets", "data", "anime", "boardgames"):
        shutil.copytree(_root / _directory, _public / _directory, dirs_exist_ok=True)
    print("Synced HTML, styles, scripts, catalogue and assets to public/.")


if __name__ == "__main__":
    _main()
