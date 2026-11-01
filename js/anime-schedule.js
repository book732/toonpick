/** Seasonal dates use Korea's calendar; catalogue filters remain independent. */
(() => {
  function _schedulePeriod(_now = new Date()) {
    const _parts = new Intl.DateTimeFormat('en', { timeZone: 'Asia/Seoul', year: 'numeric', month: 'numeric' }).formatToParts(_now);
    return { year: Number(_parts.find(_part => _part.type === 'year').value), quarter: Math.ceil(Number(_parts.find(_part => _part.type === 'month').value) / 3) };
  }

  function _scheduleDate(_date) {
    if (!Number.isInteger(_date?.year)) return '방영일 발표 전';
    if (!Number.isInteger(_date.month) || _date.month < 1 || _date.month > 12) return _date.year + '년 · 상세 일정 미정';
    return _date.year + '년 ' + _date.month + '월' + (Number.isInteger(_date.day) && _date.day >= 1 && _date.day <= 31 ? ' ' + _date.day + '일' : ' · 일자 미정');
  }

  document.addEventListener('DOMContentLoaded', () => {
    const _section = document.getElementById('animeSchedule');
    if (!_section) return;
    const _yearSelect = document.getElementById('scheduleYear');
    const _grid = document.getElementById('scheduleGrid');
    const _message = document.getElementById('scheduleMessage');
    const _retry = document.getElementById('scheduleRetry');
    const _more = document.getElementById('scheduleMore');
    const _formats = { TV: 'TV 시리즈', TV_SHORT: '단편 TV', MOVIE: '극장판', OVA: 'OVA', ONA: '웹 애니메이션', SPECIAL: '스페셜', MUSIC: '뮤직비디오' };
    const _statuses = { NOT_YET_RELEASED: '공개 예정', RELEASING: '방영 중', FINISHED: '방영 완료', HIATUS: '방영 중단', CANCELLED: '제작 취소' };
    let _currentYear, _year, _quarter, _yearTimer, _controller;
    let _page = 0, _version = 0, _items = [], _active = false, _retryAppend = false;
    const _escape = _value => String(_value).replace(/[&<>"']/g, _char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[_char]));

    function _syncYear() {
      const _period = _schedulePeriod();
      if (_currentYear !== _period.year) {
        _currentYear = _period.year;
        if (![_currentYear, _currentYear + 1].includes(_year)) { _year = _currentYear; _quarter = _period.quarter; }
        _yearSelect.replaceChildren(...[_currentYear, _currentYear + 1].map(_value => new Option(_value + '년', _value)));
        _yearSelect.value = String(_year);
        if (_active) void _load();
      }
      clearTimeout(_yearTimer);
      // A daily upper bound avoids the browser's 32-bit timeout overflow.
      _yearTimer = setTimeout(_syncYear, Math.min(86400000, Date.UTC(_currentYear + 1, 0, 1) - 9 * 3600000 - Date.now() + 100));
    }

    function _render() {
      _grid.innerHTML = _items.map(_item => '<article class="schedule-card"><a href="https://anilist.co/anime/' + _item.id + '" target="_blank" rel="noopener noreferrer"><div class="schedule-art"><img src="' + _escape(_item.cover) + '" alt="" width="180" height="240" loading="lazy" decoding="async"><span>' + _escape(_statuses[_item.status] || '일정 확인 중') + '</span></div><h3 title="' + _escape(_item.sourceTitle || _item.title) + '">' + _escape(_item.title) + '</h3><p>' + _escape(_scheduleDate(_item.startDate)) + '</p><small>' + _escape(_formats[_item.format] || '애니메이션') + (_item.translatedTitle ? ' · 번역명' : _item.originalTitle ? ' · 원제' : '') + '<span aria-hidden="true"> ↗</span></small></a></article>').join('');
    }

    async function _load(_append = false) {
      _controller?.abort();
      _controller = new AbortController();
      const _requestController = _controller;
      const _request = ++_version;
      const _nextPage = _append ? _page + 1 : 1;
      const _timer = setTimeout(() => _requestController.abort(), 15000);
      _retryAppend = _append;
      _grid.setAttribute('aria-busy', 'true');
      _retry.hidden = true;
      _more.disabled = true;
      _message.setAttribute('role', 'status');
      _message.textContent = _year + '년 ' + _quarter + '분기 방영 일정을 불러오는 중…';
      if (!_append) { _items = []; _render(); _more.hidden = true; }
      _section.querySelectorAll('[data-quarter]').forEach(_button => _button.setAttribute('aria-pressed', String(Number(_button.dataset.quarter) === _quarter)));
      try {
        const _response = await fetch('/api/generate?' + new URLSearchParams({ resource: 'anime_schedule', language: 'ko', year: _year, quarter: _quarter, page: _nextPage }), { signal: _controller.signal });
        const _data = await _response.json();
        if (!_response.ok) throw new Error(_data.error || '방영 일정을 불러오지 못했어요.');
        if (!Array.isArray(_data.items) || _data.year !== _year || _data.quarter !== _quarter || _data.page !== _nextPage || typeof _data.hasNextPage !== 'boolean' || _data.items.some(_item => !Number.isInteger(_item.id) || _item.id < 1 || typeof _item.title !== 'string' || !/^https:\/\/s[34]\.anilist\.co\/[^\s]*$/.test(_item.cover) && _item.cover !== '/assets/cover-placeholder.svg')) throw new Error('방영 일정 형식을 확인하지 못했어요.');
        if (_request !== _version) return;
        _items = [...new Map([...(_append ? _items : []), ..._data.items].map(_item => [_item.id, _item])).values()];
        _page = _nextPage;
        _render();
        _more.hidden = !_data.hasNextPage;
        _message.textContent = _items.length ? _year + '년 ' + _quarter + '분기 · 발표된 작품 ' + _items.length + '편 표시' : '이 분기에 발표된 작품이 아직 없습니다. 일정이 공개되면 여기에 표시됩니다.';
        document.getElementById('scheduleSource').href = 'https://anilist.co/search/anime?year=' + _year + '&season=' + ['WINTER', 'SPRING', 'SUMMER', 'FALL'][_quarter - 1];
      } catch (_error) {
        if (_request !== _version) return;
        _message.setAttribute('role', 'alert');
        _message.textContent = _error.name === 'AbortError' ? '일정 조회가 지연되고 있어요. 다시 시도해주세요.' : ['SyntaxError', 'TypeError'].includes(_error.name) ? '방영 일정을 불러오지 못했어요. 다시 시도해주세요.' : _error.message;
        _retry.hidden = false;
      } finally {
        clearTimeout(_timer);
        if (_request === _version) { _grid.setAttribute('aria-busy', 'false'); _more.disabled = false; }
      }
    }

    _yearSelect.addEventListener('change', () => { _year = Number(_yearSelect.value); _active = true; void _load(); });
    _section.addEventListener('click', _event => {
      const _button = _event.target.closest('button[data-quarter]');
      if (!_button || Number(_button.dataset.quarter) === _quarter && _active) return;
      _quarter = Number(_button.dataset.quarter); _active = true; void _load();
    });
    _retry.addEventListener('click', () => { void _load(_retryAppend); });
    _more.addEventListener('click', () => { void _load(true); });
    document.addEventListener('visibilitychange', () => { if (!document.hidden) _syncYear(); });
    _syncYear();
    if ('IntersectionObserver' in window) {
      const _observer = new IntersectionObserver(_entries => {
        if (!_entries.some(_entry => _entry.isIntersecting)) return;
        _observer.disconnect();
        if (!_active) { _active = true; void _load(); }
      }, { rootMargin: '300px' });
      _observer.observe(_section);
    } else { _active = true; void _load(); }
  });
})();
