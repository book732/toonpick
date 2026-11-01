"""Render the anime entrypoint from the shared catalogue page shell."""

import re
from pathlib import Path


def _main():
    _root = Path(__file__).resolve().parents[1]
    _html = (_root / "index.html").read_text(encoding="utf-8")
    _html = _html.replace('<script src="js/storage.js" defer>', '<script src="js/anime.js" defer></script>\n    <script src="js/storage.js" defer>', 1)
    _html = _html.replace('<body>', '<body class="anime-page">', 1)
    _html = _html.replace('<link rel="stylesheet" href="css/style.css" />', '<link rel="stylesheet" href="css/style.css" /><link rel="stylesheet" href="css/anime-schedule.css" />', 1)
    _html = _html.replace('<script src="js/app.js" defer>', '<script src="js/anime-schedule.js" defer></script>\n    <script src="js/app.js" defer>', 1)
    _schedule = '''      <section class="container anime-schedule" id="animeSchedule" aria-labelledby="scheduleTitle">
        <div class="schedule-heading"><div><span class="section-kicker orange">ON THE CALENDAR</span><h2 id="scheduleTitle">분기별 방영 미리보기</h2><p>올해와 다음 해, 기다리는 애니메이션을 미리 만나보세요.</p></div><label class="schedule-year" for="scheduleYear">방영 연도<select id="scheduleYear"></select></label></div>
        <div class="schedule-quarters" role="group" aria-label="방영 분기"><button type="button" data-quarter="1" aria-pressed="false">1분기</button><button type="button" data-quarter="2" aria-pressed="false">2분기</button><button type="button" data-quarter="3" aria-pressed="false">3분기</button><button type="button" data-quarter="4" aria-pressed="false">4분기</button></div>
        <p class="schedule-message" id="scheduleMessage" role="status" aria-live="polite">발표된 방영 일정을 확인하세요.</p>
        <div class="schedule-grid" id="scheduleGrid" aria-busy="false"></div>
        <div class="schedule-controls"><button class="btn btn-outline" type="button" id="scheduleRetry" hidden>다시 불러오기</button><button class="btn btn-outline" type="button" id="scheduleMore" hidden>방영 작품 더 보기</button></div>
        <p class="schedule-note">1분기 1–3월 · 2분기 4–6월 · 3분기 7–9월 · 4분기 10–12월<br>해외 최초 공개 분기 기준이며 국내 공개일·플랫폼은 다를 수 있습니다. 발표 전 일정은 표시되지 않으며 편성은 변경될 수 있어요. <a id="scheduleSource" href="https://anilist.co/search/anime" target="_blank" rel="noopener noreferrer">일정 출처: AniList ↗</a></p>
      </section>
'''
    _html = _html.replace('      <section\n        class="container catalog-section"', _schedule + '      <section\n        class="container catalog-section"', 1)
    _html = _html.replace('<a href="/" class="content-link active" aria-current="page">', '<a href="/" class="content-link">').replace('<a href="/anime" class="content-link">', '<a href="/anime" class="content-link active" aria-current="page">')
    _html = _html.replace('오늘의 덕질 — 웹툰 추천', '오늘의 덕질 — 애니메이션 추천')
    _html = _html.replace('다음 한 컷이', '다음 한 편이').replace('맞는 웹툰을', '맞는 애니메이션을').replace('웹툰 큐레이션', '애니메이션 큐레이션')
    _html = _html.replace('취향에 맞는 다음 웹툰을 발견하세요. 장르와 분위기별 웹툰 추천, 완결 작품 탐색, 나만의 보관함까지 오늘의 덕질에서.', '장르와 분위기에 맞는 애니메이션을 발견하세요. TV 시리즈·극장판 탐색과 AI 추천, 시즌 정보와 나만의 보관함까지.')
    _html = _html.replace('완결 정주행', '방영 완료작').replace('연재 상태', '방영 상태').replace('연재 중', '방영 중').replace('완결 작품', '방영 완료').replace('휴재 작품', '휴방 작품')
    _html = _html.replace('<option value="휴재">휴방 작품</option>', '<option value="휴재">휴방 작품</option><option value="방영예정">방영 예정</option><option value="중단">제작 중단</option>')
    _html = _html.replace('제목, 작가, 키워드 검색', '한국어 제목, 장르, 키워드 검색').replace('제목 또는 작가', '제목 또는 제작사')
    _formats = '<label class="sr-only" for="formatSelect">작품 형식</label><select id="formatSelect"><option value="전체">모든 형식</option><option value="TV">TV 시리즈</option><option value="MOVIE">극장판</option><option value="ONA">웹 애니메이션</option><option value="OVA">OVA</option><option value="SPECIAL">스페셜</option><option value="TV_SHORT">단편 TV</option></select>'
    _html = _html.replace('<div class="select-group">', '<div class="select-group">' + _formats, 1)
    _html = re.sub(r'<fieldset>\s*<legend>\s*찾아볼 플랫폼.*?</fieldset>', '<fieldset><legend>작품 형식 <span>선택하지 않으면 전체</span></legend><div class="preference-options" id="preferenceFormats"></div></fieldset><fieldset><legend>찾아볼 감상 서비스</legend><div class="preference-options" id="preferencePlatforms"></div></fieldset>', _html, count=1, flags=re.S)
    _html = _html.replace('선택한 개수에 맞춰 네이버·카카오·기타 플랫폼을 고르게 배분합니다.', '선택한 개수만큼 취향에 맞는 작품을 고르고 같은 시리즈의 시즌 중복을 줄입니다.')
    _html = _html.replace('완결만 정주행할래요', '방영 완료작만 볼래요')
    _html = re.sub(r'<p class="preference-note">.*?</p>', '<p class="preference-note">라프텔·넷플릭스 한국 공식 목록을 기준으로 추천합니다. 시즌·더빙판·플랫폼별 항목을 포함합니다. 현재 재생 가능 여부와 이용 연령은 각 서비스에서 확인해주세요. 취향과 요청사항은 AI에 전달됩니다.</p>', _html, count=1, flags=re.S)
    _html = _html.replace('여러 플랫폼 검색과 AI 분석으로', '작품 정보 조회와 AI 분석으로')
    _html = re.sub(r'      <section\s+class="container platforms-section".*?</section>\n', '', _html, count=1, flags=re.S)
    _html = _html.replace('            <span class="section-kicker orange">DISCOVER YOUR PICK</span>\n', '')
    _html = _html.replace('관심등록순', '인기순')
    _html = re.sub(r'(src|href)="(assets|js|css)/', r'\1="/\2/', _html)
    _directory = _root / "anime"
    _directory.mkdir(exist_ok=True)
    (_directory / "index.html").write_bytes(_html.encode("utf-8"))


if __name__ == "__main__":
    _main()
