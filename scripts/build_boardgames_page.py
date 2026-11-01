"""Build the board-game page and catalogue from the shared page shell."""

import json
import re
import sys
from pathlib import Path


def _controls(_prefix, _form=False):
    _fields = [("players", "함께할 인원", [(0, "인원 무관"), *((_value, str(_value) + "명") for _value in range(1, 13))]), ("maxMinutes", "플레이 시간 상한", [(0, "시간 무관"), *((_value, str(_value) + "분 이하") for _value in [15, 20, 30, 45, 60, 90, 120])]), ("difficulty", "난이도 상한", [(0, "난이도 무관"), (1, "가볍게"), (2, "보통까지"), (3, "도전 포함")])]
    return '<div class="boardgame-filters">' + ''.join('<label for="' + _prefix + _key + '">' + _label + '<select id="' + _prefix + _key + '" ' + ('name="' + _key + '"' if _form else 'data-board-filter="' + _key + '"') + '>' + ''.join('<option value="' + str(_value) + '">' + _name + '</option>' for _value, _name in _options) + '</select></label>' for _key, _label, _options in _fields) + '</div>'


def _main():
    _root = Path(__file__).resolve().parents[1]
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))
    from services.boardgames import _boardgame_catalog
    _catalog = _boardgame_catalog()
    (_root / 'data/boardgames_catalog.json').write_bytes(json.dumps(_catalog, ensure_ascii=False, separators=(',', ':')).encode())
    for _item in _catalog['items']:
        if not _item['cover'].startswith('https://cdnfile.koreaboardgames.com/') and not (_root / _item['cover']).is_file():
            raise FileNotFoundError('Missing board-game cover: ' + _item['cover'])
    _page = (_root / 'index.html').read_text(encoding='utf-8')
    _footer = re.search(r'    <footer class="footer">.*?</footer>', _page, re.S).group(0)
    # Preserve the board-game layout when the shared webtoon section moves.
    _platforms = re.search(r'      <section\s+class="container platforms-section".*?</section>\n', _page, re.S).group(0)
    _platforms = _platforms.replace('<details class="platforms-disclosure">', '<details class="platforms-disclosure" open>')
    _kicker = '<span class="section-kicker orange">DISCOVER YOUR PICK</span>'
    _platforms = _platforms.replace('        ' + _kicker + '\n', '')
    _page = re.sub(r'      <section\s+class="container platforms-section".*?</section>\n', '', _page, count=1, flags=re.S)
    _page = _page.replace('      <section\n        class="container catalog-section"', _platforms + '      <section\n        class="container catalog-section"', 1)
    _page = _page.replace('            <h2 id="catalogTitle">', '            ' + _kicker + '\n            <h2 id="catalogTitle">', 1)
    _page = _page.replace('<script src="js/storage.js" defer>', '<script src="js/boardgames.js" defer></script>\n    <script src="js/storage.js" defer>', 1).replace('<body>', '<body class="boardgame-page">', 1)
    _page = _page.replace('<a href="/" class="content-link active" aria-current="page">', '<a href="/" class="content-link">').replace('<a href="/boardgames" class="content-link">', '<a href="/boardgames" class="content-link active" aria-current="page">')
    _header = re.search(r'    <header class="navbar".*?</header>', _page, re.S).group(0).replace('완결 정주행', '30분 게임').replace('data-view="finished"', 'data-view="quick"')
    _page = _page.replace('오늘의 덕질 — 웹툰 추천', '오늘의 덕질 — 보드게임 추천').replace('다음 한 컷', '다음 한 판')
    _page = _page.replace('웹툰', '보드게임').replace('작품', '게임').replace('제목, 작가, 키워드 검색', '게임 이름, 출판사, 키워드 검색').replace('연재 상태', '플레이 조건')
    _page = _page.replace('어떤 이야기를 좋아하세요', '어떤 게임을 즐기고 싶으세요').replace('취향에 꽂힐, 다음 이야기', '취향에 맞는, 다음 한 판')
    _page = _page.replace('다양한 장르의 보드게임 큐레이션', '함께 즐기는 보드게임 큐레이션').replace('완결 정주행', '30분 게임').replace('data-view="finished"', 'data-view="quick"')
    _page = _page.replace('장르와 분위기별 보드게임 추천, 완결 게임 탐색', '인원과 시간에 맞는 보드게임 추천, 함께할 게임 탐색').replace('오늘의 기분에 꼭', '함께할 사람과 시간에 꼭')
    _page = re.sub(r'<fieldset>\s*<legend>\s*찾아볼 플랫폼.*?</fieldset>', '<fieldset><legend>함께할 플레이 조건</legend>' + _controls('preference', True) + '</fieldset><fieldset hidden><legend>정보 출처</legend><div id="preferencePlatforms"></div></fieldset>', _page, count=1, flags=re.S)
    _moods = ['전체', '가볍게', '머리쓰는', '함께하는', '웃음가득', '긴장감', '차분한']
    _page = re.sub(r'<fieldset>\s*<legend><b>02</b>.*?</fieldset>', '<fieldset><legend><b>02</b> 원하는 플레이 분위기</legend><div class="preference-options">' + ''.join('<label><input type="radio" name="mood" value="' + _mood + '"' + (' checked' if _mood == '전체' else '') + '><span>' + _mood + '</span></label>' for _mood in _moods) + '</div></fieldset>', _page, count=1, flags=re.S)
    _page = re.sub(r'<fieldset>\s*<legend><b>03</b>.*?</fieldset>', '<input type="hidden" name="status" value="전체">', _page, count=1, flags=re.S)
    _page = re.sub(r'(<div class="mood-options" id="moodOptions">).*?(</div>)', r'\1' + ''.join('<button type="button" class="mood-chip" data-mood="' + _mood + '" aria-pressed="false">' + _mood + '</button>' for _mood in ['가볍게', '함께하는', '머리쓰는', '웃음가득']) + r'\2', _page, count=1, flags=re.S)
    _page = _page.replace('<div class="select-group">', _controls('board') + '<div class="select-group">', 1)
    _page = _page.replace('<label class="sr-only" for="platformSelect">플랫폼</label', '<label class="sr-only" for="platformSelect" hidden>플랫폼</label').replace('<select id="platformSelect">', '<select id="platformSelect" hidden>')
    _page = _page.replace('<label class="sr-only" for="statusSelect">플레이 조건</label', '<label class="sr-only" for="statusSelect" hidden>플레이 조건</label').replace('<select id="statusSelect">', '<select id="statusSelect" hidden>')
    _page = re.sub(r'<option value="favorites">.*?</option>', '', _page)
    _page = _page.replace('선택한 개수에 맞춰 네이버·카카오·기타 플랫폼을 고르게 배분합니다.', '인원·표기 시간·난이도 조건을 먼저 적용하고 취향에 맞는 게임을 고릅니다.')
    _page = re.sub(r'<p class="preference-note">.*?</p>', '<p class="preference-note">출판사 기본판 정보를 확인한 편집 목록에서 추천합니다. 시간은 출판사 표기 기준이고 실제 소요 시간은 달라질 수 있습니다. 난이도는 오늘의 덕질의 편집 분류입니다. 조건에 맞는 게임이 적으면 가능한 수만 추천합니다.</p>', _page, count=1, flags=re.S)
    _page = _page.replace('국내 플랫폼 연결 상태를 불러오는 중…', '스플렌더·더 게임과 함께할 게임을 불러오는 중…').replace('이야기는, 플랫폼 너머로', '오늘, 누구와 한 판 할까요?').replace('오늘은 어떤 이야기가 끌리나요?', '어떤 분위기로 한 판 할까요?')
    _page = _page.replace('여러 플랫폼 검색과 AI 분석으로', '플레이 조건 확인과 AI 분석으로').replace('좋아했던 게임이나 원하는 전개를 적어주세요. 예: 유쾌하지만 인물의 성장이 뚜렷한 이야기가 좋아요.', '예: 스플렌더처럼 선택을 고민하는 게임이 좋아요. 더 게임처럼 함께 머리를 맞대는 게임도 찾고 있어요.')
    _page = re.sub(r'(<p id="(?:resultSummary|collectionStatus|platformSummary)"[^>]*>).*?</p>', lambda _match: _match.group(1).replace('>', ' hidden>', 1) + '</p>', _page, flags=re.S)
    _page = re.sub(r'    <footer class="footer">.*?</footer>', lambda _match: _footer, _page, count=1, flags=re.S)
    _page = re.sub(r'    <header class="navbar".*?</header>', lambda _match: _header, _page, count=1, flags=re.S)
    _page = re.sub(r'(src|href)="(assets|js|css)/', r'\1="/\2/', _page)
    _directory = _root / 'boardgames'
    _directory.mkdir(exist_ok=True)
    (_directory / 'index.html').write_bytes(_page.encode())


if __name__ == '__main__':
    _main()
