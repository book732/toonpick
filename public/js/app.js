/** UI controller. Delegate repeated card events and cache shared catalogue data. */
document.addEventListener('DOMContentLoaded', () => {
  const _isAnime = window.TOONPICK_PAGE?.type === 'anime';
  const _isBoardGame = window.TOONPICK_PAGE?.type === 'boardgame';
  const form = document.getElementById('travelForm');
  const submitBtn = document.getElementById('submitBtn');
  const resetBtn = document.getElementById('resetBtn');
  const resultContainer = document.getElementById('resultContainer');
  const resultSummary = document.getElementById('resultSummary');
  const alertContainer = document.getElementById('alertContainer');
  const alertMessage = document.getElementById('alertMessage');
  const themeToggleBtn = document.getElementById('themeToggleBtn');
  const savedPlansBtn = document.getElementById('savedPlansBtn');
  const savedCountBadge = document.getElementById('savedCountBadge');
  const savedModal = document.getElementById('savedModal');
  const savedPlansList = document.getElementById('savedPlansList');
  const toastContainer = document.getElementById('toastContainer');
  const _searchInput = document.getElementById('searchInput');
  const _statusSelect = document.getElementById('statusSelect');
  const _sortSelect = document.getElementById('sortSelect');
  const _detailModal = document.getElementById('detailModal');
  const _preferenceModal = document.getElementById('preferenceModal');
  const _emptyState = document.getElementById('emptyState');
  const _preferenceError = document.getElementById('preferenceError');
  const _preferenceNotes = document.getElementById('preferenceNotes');
  const _recommendationStatus = document.getElementById('recommendationStatus');
  const _recommendationFloating = document.getElementById('recommendationFloating');
  const _recommendationExperience = document.getElementById('recommendationExperience');
  const _pickMotionToggle = document.getElementById('pickMotionToggle');
  const _recommendationCopy = _isBoardGame ? {
    theme: 'boardgame', eyebrow: 'SHUFFLE. DISCOVER. PLAY.', title: ['다음 한 판의 설렘을', '섞고 있어요'], label: '보드게임 AI 추천 중',
    messages: ['머리를 맞댈까요, 멋지게 한 수 둘까요? 다음 한 판을 기대해주세요.', '카드는 섞이고, 새로운 승부의 예감은 커지고 있어요.', '함께 웃고 고민할 게임, 이번엔 무엇일까요?']
  } : _isAnime ? {
    theme: 'anime', eyebrow: 'YOUR NEXT EPISODE AWAITS', title: ['당신의 다음 최애,', '곧 등장할지도'], label: '애니메이션 AI 추천 중',
    messages: ['오프닝부터 빠져들 새로운 세계를 기대해주세요.', '엔딩 크레딧이 올라가도 오래 남을 이야기, 만나볼까요?', '새로운 세계, 새로운 인물. 다음 최애의 자리를 비워두세요.']
  } : {
    theme: 'webtoon', eyebrow: 'JUST ONE MORE CHAPTER', title: ['다음 컷이 궁금한', '이야기를 찾는 중'], label: '웹툰 AI 추천 중',
    messages: ['한 컷의 설렘, 한 번의 반전. 어떤 이야기가 기다리고 있을까요?', '딱 한 화만 보려다 밤을 새울지도 몰라요.', '스크롤을 멈출 수 없는 다음 이야기, 기대해도 좋아요.']
  };
  let _recommendationTimer;
  let _recommendationStarted = 0;
  const _submitLabel = submitBtn.innerHTML;
  const _resultCount = document.getElementById('resultCount');
  const _activeFilter = document.getElementById('activeFilter');
  const _state = { genres: [], mood: '전체', status: '전체', query: '', sort: 'editor', platforms: [], formats: [], count: 6, players: 0, maxMinutes: 0, difficulty: 0 };
  const _platformSelect = document.getElementById('platformSelect');
  let _platformControlsReady = false;
  const _dayNames = { MONDAY: '월', TUESDAY: '화', WEDNESDAY: '수', THURSDAY: '목', FRIDAY: '금', SATURDAY: '토', SUNDAY: '일' };
  let _requestVersion = 0;
  let _toastTimer;
  let _searchTimer;
  let _isSubmitting = false;
  let _aiData = null;
  let _lastRequestAI = false;
  let _visibleCount = 24;
  let _lastRenderData = null;
  const _loadMoreBtn = document.getElementById('loadMoreBtn');

  function _escape(_value) {
    return String(_value).replace(/[&<>"']/g, _char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[_char]));
  }

  function _icon(_name) {
    return '<svg class="icon" aria-hidden="true"><use href="#icon-' + _name + '"/></svg>';
  }

  function _coverUrl(_url) {
    return (_isAnime || _isBoardGame) && _url.startsWith('assets/') ? '/' + _url : _url;
  }

  function initTheme() {
    applyTheme(window.StorageManager.getTheme());
  }

  function applyTheme(theme) {
    document.body.classList.toggle('dark-theme', theme === 'dark');
    document.querySelector('meta[name="theme-color"]').setAttribute('content', getComputedStyle(document.body).getPropertyValue('--page').trim());
    themeToggleBtn.setAttribute('aria-label', theme === 'dark' ? '라이트 모드로 전환' : '다크 모드로 전환');
    themeToggleBtn.setAttribute('aria-pressed', String(theme === 'dark'));
    window.StorageManager.setTheme(theme);
  }

  function showAlert(type, title, message) {
    alertMessage.textContent = message;
    alertContainer.hidden = false;
  }

  function hideAlert() {
    alertContainer.hidden = true;
  }

  function setLoadingState(isLoading) {
    resultContainer.setAttribute('aria-busy', String(isLoading));
  }

  function _showRecommendationExperience() {
    if (!_recommendationStarted) return;
    _recommendationFloating.hidden = true;
    if (!_recommendationExperience.open) _recommendationExperience.showModal();
  }

  function _setRecommendationLoading(_loading) {
    clearInterval(_recommendationTimer);
    _recommendationStarted = _loading ? Date.now() : 0;
    _recommendationStatus.hidden = !_loading;
    _recommendationFloating.hidden = true;
    form.setAttribute('aria-busy', String(_loading));
    form.querySelectorAll('input, textarea, select, fieldset').forEach(_element => { _element.disabled = _loading; });
    if (!_loading) {
      if (_recommendationExperience.open) _recommendationExperience.close();
      return;
    }
    _recommendationExperience.dataset.theme = _recommendationCopy.theme;
    _pickMotionToggle.hidden = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    _recommendationFloating.dataset.theme = _recommendationCopy.theme;
    document.querySelectorAll('[data-loading-scene]').forEach(_scene => { _scene.hidden = _scene.dataset.loadingScene !== _recommendationCopy.theme; });
    document.getElementById('pickLoadingEyebrow').textContent = _recommendationCopy.eyebrow;
    document.getElementById('pickLoadingTitle').innerHTML = _recommendationCopy.title.map(_line => '<span>' + _escape(_line) + '</span>').join('');
    document.getElementById('recommendationFloatingLabel').textContent = _recommendationCopy.label;
    document.getElementById('pickLoadingCount').textContent = '요청 ' + _state.count + '개';
    const _stage = document.getElementById('recommendationStage');
    const _message = document.getElementById('pickLoadingMessage');
    const _tick = () => {
      const _seconds = Math.floor((Date.now() - _recommendationStarted) / 1000);
      document.getElementById('recommendationElapsed').textContent = _seconds + '초 경과';
      document.getElementById('recommendationFloatingElapsed').textContent = _seconds + '초 경과';
      document.getElementById('pickLoadingElapsed').textContent = _seconds + '초 경과';
      const _text = _seconds >= 60 ? '평소보다 시간이 걸리고 있어요. 작게 해두고 둘러보셔도 괜찮아요.' : _seconds >= 30 ? '아직 AI 응답을 기다리고 있어요. 도착하면 추천 결과를 바로 보여드릴게요.' : _recommendationCopy.messages[Math.floor(_seconds / 8) % _recommendationCopy.messages.length];
      if (_message.textContent !== _text) _message.textContent = _text;
      if (_stage.textContent !== _text) _stage.textContent = _text;
    };
    _tick();
    _recommendationTimer = setInterval(_tick, 1000);
    _showRecommendationExperience();
  }

  function showToast(message, duration = 3000) {
    clearTimeout(_toastTimer);
    toastContainer.textContent = message;
    _toastTimer = setTimeout(() => { toastContainer.textContent = ''; }, duration);
  }

  function updateSavedBadge() {
    const _saved = new Set(window.StorageManager.getSavedPlans().map(_entry => _entry.id));
    savedCountBadge.textContent = String(_saved.size);
    document.querySelectorAll('[data-save]').forEach(_button => {
      const _isSaved = _saved.has(_button.dataset.save);
      _button.setAttribute('aria-pressed', String(_isSaved));
      const _item = window.ApiService._catalog?.items.find(_entry => _entry.id === _button.dataset.save);
      _button.setAttribute('aria-label', (_item?.title || '작품') + (_isSaved ? ' 보관함에서 삭제' : ' 보관함에 저장'));
      if (_button.classList.contains('detail-save')) {
        _button.innerHTML = _icon('bookmark') + (_isSaved ? '보관함에서 빼기' : '보관함에 담기');
      }
    });
  }

  function _card(_item, _index, _saved) {
    const _id = _escape(_item.id);
    const _title = _escape(_item.title);
    const _genreLabel = _isAnime || _isBoardGame ? [...new Set([..._state.genres.filter(_genre => _item.genres.includes(_genre)), ..._item.genres])].slice(0, 2).join(' · ') : _item.genre;
    const _platformLabel = _isAnime ? _animeSources(_item).map(_source => '<a class="platform-link" href="' + _escape(_source.url) + '" target="_blank" rel="noopener noreferrer"><span class="platform-mark" data-platform="' + _escape(_source.platformKey) + '" aria-hidden="true">' + _escape(_source.platform.slice(0, 1)) + '</span>' + _escape(_source.platform) + ' ↗</a>').join('') : '<span class="platform-mark" data-platform="' + _escape(_item.platformKey || 'naver') + '" aria-label="' + _escape(_item.platform) + '">' + _escape(_item.platform.slice(0, 1)) + '</span><span>' + _escape(_item.platform) + '</span>';
    const _label = _state.sort === 'favorites' ? '관심 ' + new Intl.NumberFormat('ko-KR', { notation: 'compact' }).format(_item.favorites) :
      _item.recommendationReason ? 'AI PICK ' + String(_index + 1).padStart(2, '0') :
      _state.mood !== '전체' ? _state.mood + ' 이야기' : 'PICK ' + String(_index + 1).padStart(2, '0');
    return '<article class="webtoon-card">' +
      '<div class="card-art"><button type="button" class="card-cover-button" data-detail="' + _id + '" aria-label="' + _title + ' 상세 보기">' +
      '<img src="' + _escape(_coverUrl(_item.cover)) + '" alt="' + _title + ' 표지" width="240" height="320" loading="lazy" decoding="async"></button>' +
      '<span class="card-label">' + _escape(_label) + '</span>' +
      '<button class="card-save" type="button" data-save="' + _id + '" aria-pressed="' + _saved.has(_item.id) + '" aria-label="' + _title + (_saved.has(_item.id) ? ' 보관함에서 삭제' : ' 보관함에 저장') + '">' + _icon('bookmark') + '</button></div>' +
      '<h3><button class="card-title" type="button" data-detail="' + _id + '">' + _title + '</button></h3>' +
      '<p class="card-author" title="' + _escape(_item.author) + '">' + _escape(_item.author) + '</p>' +
      (_isAnime ? '<p class="anime-original">' + _escape([_item.formatLabel, _item.year ? _item.year + '년' : '', _item.episodes ? _item.episodes + '화' : ''].filter(Boolean).join(' · ')) + '</p>' : '') +
      (_isBoardGame ? '<p class="anime-original">' + _escape(_item.playersLabel + ' · ' + _item.timeLabel) + '</p><div class="card-meta"><span>' + _escape(_genreLabel) + '</span><span>' + _escape(_item.mode) + '</span><span>난이도 ' + _escape(_item.difficultyLabel) + '</span></div>' :
      '<div class="card-meta">' + _platformLabel + '<span class="meta-divider"></span><span>' + _escape(_genreLabel) + '</span><span>' + _escape(_isAnime ? ({ '완결': '방영 완료', '연재': '방영 중', '휴재': '휴방', '방영예정': '방영 예정' }[_item.status] || _item.status) : _item.status) + '</span></div>') +
      '<div class="card-tags">' + (_item.discovery === 'web' ? '<span class="orange">공식 검색 발견</span>' : '') + _item.tags.slice(0, 2).map(_tag => '<span>#' + _escape(_tag) + '</span>').join('') + '</div>' +
      (_item.recommendationReason ? '<p class="card-reason"><b>AI 추천 이유</b>' + _escape(_item.recommendationReason) + '</p>' : '') + '</article>';
  }

  function renderResult(data) {
    window._ToonpickExperience._setCatalog(window.ApiService._catalog.heroItems || window.ApiService._catalog.items);
    _renderPlatforms(data.retrieval?.search?.platforms);
    _lastRenderData = data;
    const _saved = new Set(window.StorageManager.getSavedPlans().map(_entry => _entry.id));
    resultContainer.innerHTML = data.items.slice(0, _visibleCount).map((_item, _index) => _card(_item, _index, _saved)).join('');
    _loadMoreBtn.hidden = data.items.length <= _visibleCount && !(_isAnime && !_aiData && window.ApiService._catalog.pagination?.hasNextPage);
    _loadMoreBtn.textContent = '작품 더 보기 · ' + Math.min(_visibleCount, data.items.length) + ' / ' + data.items.length;
    _emptyState.hidden = data.items.length > 0;
    _resultCount.innerHTML = (_isAnime && !_aiData ? '검색 결과 ' : '전체 ') + '<b>' + (_isAnime && !_aiData ? window.ApiService._catalog.matchedCount ?? data.items.length : data.items.length) + '</b> ' + (_isBoardGame ? '게임' : '작품');
    const _filters = [..._state.platforms.map(_key => window.ApiService._platforms[_key]?.name || _key), ..._state.formats.map(_key => window.TOONPICK_PAGE?.formats[_key] || _key), ..._state.genres, _state.mood !== '전체' ? _state.mood : '', _state.status !== '전체' ? (_isAnime && _state.status === '완결' ? '방영 완료' : _state.status) : ''].filter(Boolean);
    if (_isBoardGame) {
      if (_state.players) _filters.push(_state.players + '명');
      if (_state.maxMinutes) _filters.push(_state.maxMinutes + '분 이하');
      if (_state.difficulty) _filters.push('난이도 ' + ['무관', '가볍게', '보통', '도전'][_state.difficulty] + '까지');
      document.querySelectorAll('[data-board-filter]').forEach(_select => { _select.value = String(_state[_select.dataset.boardFilter]); });
    }
    _activeFilter.textContent = _filters.join(' · ');
    _activeFilter.hidden = !_filters.length;
    resetBtn.hidden = !_aiData && !_filters.length && !_state.query && _state.sort === 'editor';
    resultSummary.textContent = _state.query ? '“' + _state.query + '” 검색 결과예요.' :
      data.summary ? data.summary :
      _filters.length ? _filters.join(' · ') + ' 취향으로 고른 이야기예요.' : _isBoardGame ? '' : '장르를 넘나드는 에디터의 추천을 만나보세요.';
    resultSummary.hidden = !resultSummary.textContent;
    const _recommendationLabel = document.getElementById('recommendationLabel');
    _recommendationLabel.textContent = data.source === 'ai' ? 'AI 맞춤 추천 · ' + data.model : '';
    _recommendationLabel.parentElement.hidden = data.source !== 'ai';
    const _retrieval = data.retrieval;
    const _collectionStatus = document.getElementById('collectionStatus');
    _collectionStatus.textContent = _retrieval ? '자동 수집 ' + _retrieval.catalogCount.toLocaleString('ko-KR') + '작품 · 공식 검색 ' + _retrieval.search.matched + '작품 확인 · AI 후보 ' + _retrieval.candidateCount + '작품' + (_retrieval.search.status === 'unavailable' ? ' · 검색 연결 지연' : _retrieval.search.status === 'partial' ? ' · 검색 일부 지연' : '') :
      '';
    if (_isAnime) {
      _collectionStatus.textContent = _retrieval ? '국내 서비스 목록 ' + _retrieval.catalogCount.toLocaleString('ko-KR') + '개 · AI 후보 ' + _retrieval.candidateCount + '개 · 요청 ' + _retrieval.requestedCount + '개 · 결과 ' + data.items.length + '개' : '국내 서비스 목록 ' + (window.ApiService._catalog.catalogCount || data.items.length).toLocaleString('ko-KR') + '개 · 시즌·더빙판·플랫폼별 항목 포함 · 재생 가능 여부는 서비스 확인';
      if (document.getElementById('formatSelect')) document.getElementById('formatSelect').value = _state.formats.length === 1 ? _state.formats[0] : '전체';
    }
    if (_isBoardGame) {
      _collectionStatus.textContent = _retrieval ? '요청 ' + _retrieval.requestedCount + '개 · 추천 ' + data.items.length + '개' : '';
    }
    _collectionStatus.hidden = !_collectionStatus.textContent;
    if (_retrieval?.quota && data.source === 'ai') {
      const _counts = _retrieval.quota.actual;
      _collectionStatus.textContent += ' · 추천 배분 네이버 ' + _counts.naver + ' / 카카오 ' + _counts.kakao + ' / 기타 ' + _counts.other;
      if (data.items.length < _retrieval.requestedCount) _collectionStatus.textContent += ' · 요청 ' + _retrieval.requestedCount + '개 중 조건에 맞는 ' + data.items.length + '개';
    }
    document.querySelectorAll('[data-genre]').forEach(_button => {
      const _selected = _state.genres.length === 0 ? _button.dataset.genre === '전체' : _state.genres.includes(_button.dataset.genre);
      _button.classList.toggle('active', _selected);
      _button.setAttribute('aria-pressed', String(_selected));
    });
    document.querySelectorAll('[data-mood]').forEach(_button => {
      _button.setAttribute('aria-pressed', String(_button.dataset.mood === _state.mood));
    });
    _statusSelect.value = _state.status;
    _sortSelect.value = _state.sort;
    let _selectedPlatforms = _platformSelect.querySelector('[value="selected"]');
    if (_state.platforms.length > 1) {
      if (!_selectedPlatforms) {
        _selectedPlatforms = new Option('', 'selected');
        _selectedPlatforms.hidden = true;
        _platformSelect.add(_selectedPlatforms);
      }
      _selectedPlatforms.textContent = _state.platforms.length + '개 플랫폼 적용';
      _platformSelect.value = 'selected';
    } else {
      _selectedPlatforms?.remove();
      _platformSelect.value = _state.platforms[0] || '전체';
    }
    const _updated = new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeZone: 'Asia/Seoul' }).format(new Date(data.updatedAt));
    document.getElementById('catalogFootnote').textContent =
      _isBoardGame ? '게임 정보: ' + _updated + ' 출판사·국내 공식 유통사 표기 확인. 시간은 실제 플레이에 따라 달라집니다. 난이도 미확인 게임은 난이도 제한 추천에서 제외합니다. 표지는 출판사·공식 유통사 제품 이미지입니다.' : _isAnime ? '작품 정보: 라프텔·넷플릭스 한국 공식 목록 · ' + _updated + ' 수집. 동일 제목·형식은 한 번만 표시하며 시즌·극장판은 별도 작품입니다. 목록 등록은 현재 재생 가능 여부를 보장하지 않습니다.' : '작품 정보: ' + _updated + ' 수집 기준. 플랫폼별 공개 검색·목록을 활용합니다. 연재 상태·이용 연령이 확인되지 않은 경우 공식 페이지에서 확인해주세요.';
  }

  function _renderPlatforms(_latest = []) {
    if (_isBoardGame) {
      document.getElementById('platformSummary').textContent = '';
      document.getElementById('platformSummary').hidden = true;
      document.getElementById('platformDirectory').innerHTML = '<div class="anime-information">공식 페이지에서 확인된 인원·시간 정보를 사용합니다. 인원이나 시간이 미확인인 게임은 해당 제한이 있는 추천에서 제외합니다. 난이도와 유형은 오늘의 덕질 편집 분류입니다. 상세 화면에서 판본과 출처를 확인할 수 있어요.</div>';
      return;
    }
    if (_isAnime) {
      const _platforms = window.ApiService._catalog.platforms || Object.values(window.ApiService._platforms);
      if (!_platformControlsReady) {
        _platformSelect.innerHTML = '<option value="전체">모든 플랫폼</option>' + _platforms.map(_platform => '<option value="' + _platform.key + '">' + _escape(_platform.name) + '</option>').join('');
        document.getElementById('preferencePlatforms').innerHTML = _platforms.map(_platform => '<label><input type="checkbox" name="platform" value="' + _platform.key + '"><span>' + _escape(_platform.name) + '</span></label>').join('');
        _platformControlsReady = true;
      }
      return;
    }
    const _platforms = Object.values(window.ApiService._platforms).filter(_platform => _platform.count > 0);
    if (!_platformControlsReady) {
      _platformSelect.innerHTML = '<option value="전체">모든 플랫폼</option>' + _platforms.map(_platform => '<option value="' + _platform.key + '">' + _escape(_platform.name) + '</option>').join('');
      document.getElementById('preferencePlatforms').innerHTML = _platforms.map(_platform => '<label><input type="checkbox" name="platform" value="' + _platform.key + '"><span>' + _escape(_platform.name) + '</span></label>').join('');
      _platformControlsReady = true;
    }
    const _latestMap = new Map((_latest || []).map(_entry => [_entry.key, _entry]));
    document.getElementById('platformDirectory').innerHTML = _platforms.map(_platform => {
      const _stateInfo = _latestMap.get(_platform.key) || _platform;
      const _status = _stateInfo.status === 'unavailable' ? '<span class="platform-state">조회 지연 · 공식 사이트 연결</span>' : '';
      const _query = _state.query || _preferenceNotes.value.trim().slice(0, 30) || '웹툰';
      const _url = (_platform.searchUrl || _platform.home || 'https://comic.naver.com/').replace('{query}', encodeURIComponent(_query));
      return '<a class="platform-card" href="' + _escape(_url) + '" target="_blank" rel="noopener noreferrer"><img class="platform-logo" src="/assets/platforms/' + _escape(_platform.key) + '.png" alt="" width="32" height="32" loading="lazy" decoding="async"><strong><span class="platform-name">' + _escape(_platform.name) + '</span><span aria-hidden="true">↗</span></strong>' + _status + '<small>' + (_platform.count || 0).toLocaleString('ko-KR') + '개 작품</small></a>';
    }).join('');
    document.getElementById('platformSummary').textContent = _platforms.length + '개 플랫폼의 작품을 한곳에서 둘러보세요.';
  }

  async function _refresh(_useAI = false) {
    if (_useAI && _recommendationStarted) { _showRecommendationExperience(); return false; }
    _visibleCount = 24;
    const _preferences = { ..._state, genres: [..._state.genres], platforms: [..._state.platforms], formats: [..._state.formats] };
    const _version = ++_requestVersion;
    _lastRequestAI = _useAI;
    setLoadingState(true);
    hideAlert();
    if (_useAI) {
      _setRecommendationLoading(true);
      submitBtn.textContent = _isBoardGame ? 'AI가 함께할 게임을 고르는 중…' : 'AI가 이야기를 고르는 중…';
    }
    try {
      const _result = await window.ApiService.generateTripPlan(
        { ..._preferences, ai: _useAI, notes: _useAI ? _preferenceNotes.value.trim() : undefined },
        () => {}, _useAI ? null : _aiData?.items || null
      );
      if (!_useAI && _version !== _requestVersion) return false;
      if (_useAI) {
        // Browsing while minimized must not discard the pending recommendation.
        ++_requestVersion;
        clearTimeout(_searchTimer);
        Object.assign(_state, _preferences);
        _searchInput.value = _state.query;
        _lastRequestAI = true;
        _aiData = _result.data;
      }
      renderResult(_aiData ? { ..._aiData, items: _result.data.items } : _result.data);
      return true;
    } catch (_error) {
      if (_useAI || _version === _requestVersion) {
        if (_useAI) { ++_requestVersion; _lastRequestAI = true; }
        resultContainer.replaceChildren();
        _loadMoreBtn.hidden = true;
        _emptyState.hidden = true;
        _resultCount.textContent = '불러오기 실패';
        resultSummary.hidden = true;
        document.getElementById('collectionStatus').hidden = true;
        if (!window.ApiService._catalog && !_isAnime && !_isBoardGame) {
          document.getElementById('platformSummary').textContent = '플랫폼 정보를 불러오지 못했어요.';
        }
        showAlert('error', '작품 정보 오류', _error.message);
      }
      return false;
    } finally {
      if (_useAI || _version === _requestVersion) setLoadingState(false);
      if (_useAI) {
        _setRecommendationLoading(false);
        submitBtn.innerHTML = _submitLabel;
      }
    }
  }

  function _reset() {
    clearTimeout(_searchTimer);
    _aiData = null;
    Object.assign(_state, { genres: [], mood: '전체', status: '전체', query: '', sort: 'editor', platforms: [], formats: [], count: 6, players: 0, maxMinutes: 0, difficulty: 0 });
    _searchInput.value = '';
    form.reset();
    document.querySelectorAll('.nav-link').forEach(_link => _link.classList.toggle('active', _link.dataset.view === 'all'));
    void _refresh();
  }

  function _openDialog(_dialog) {
    document.querySelectorAll('dialog[open]').forEach(_open => { if (_open !== _dialog) _open.close(); });
    if (!_dialog.open) _dialog.showModal();
    if (_dialog === _preferenceModal) _recommendationFloating.hidden = true;
  }

  function _animeSources(_item) {
    return (_item.sources || [_item]).filter(_source => window.ApiService._isValidAnimeSource(_source));
  }

  async function _showDetail(_id) {
    try {
      const _catalog = await window.ApiService._loadCatalog();
      const _item = _catalog.items.find(_entry => _entry.id === _id) || window._ToonpickExperience._getItem(_id) || window.StorageManager.getSavedPlans().find(_entry => _entry.id === _id)?.data;
      if (!window.ApiService._isValidItem(_item)) return;
      const _reason = _aiData?.items.find(_entry => _entry.id === _id)?.recommendationReason;
      const _days = _isBoardGame ? _item.mode : _isAnime ? ({ '완결': '해당 시즌·극장판 방영 완료', '연재': '방영 중', '휴재': '휴방', '방영예정': '방영 예정' }[_item.status] || _item.status) : _item.status === '완결' ? '완결 작품' :
        _item.status === '휴재' ? '휴재 중' : _item.status === '연재' ? (_item.days.length ? _item.days.map(_day => _dayNames[_day] || '').filter(Boolean).join('·') + '요일 연재' : '연재 중') : '연재 상태는 공식 페이지 확인';
      document.getElementById('detailContent').innerHTML =
        '<div class="detail-layout"><img class="detail-cover" src="' + _escape(_coverUrl(_item.cover)) + '" alt="' + _escape(_item.title) + ' 표지" width="180" height="240">' +
        '<div class="detail-copy"><span class="section-kicker orange">YOUR NEXT CHAPTER</span><h2 id="detailTitle">' + _escape(_item.title) + '</h2>' +
        '<p class="detail-author">' + _escape(_item.author) + '</p><div class="detail-chips">' +
        [...new Set([_item.genre, _days, _item.age, ...(_isBoardGame ? [_item.playersLabel, _item.timeLabel, '편집 난이도: ' + _item.difficultyLabel] : []), ...(_isAnime ? [_item.formatLabel, _item.year ? _item.year + '년' : '', _item.episodes ? _item.episodes + '화' : ''] : []), ..._item.tags].filter(Boolean))].map(_tag => '<span>' + _escape(_tag) + '</span>').join('') +
        '</div></div></div>' + (_reason ? '<p class="card-reason"><b>AI 추천 이유</b>' + _escape(_reason) + '</p>' : '') +
        (_isAnime ? '<p class="anime-original">' + _escape(_item.availability || '공식 서비스에서 감상 가능 여부 확인') + '</p>' : '') +
        '<p class="detail-description">' + _escape(_item.description) + '</p>' +
        (_isBoardGame && _item.editionNote ? '<p class="anime-original">판본 안내: ' + _escape(_item.editionNote) + '</p>' : '') +
        (_isAnime && _item.relations?.length ? '<p class="anime-original">관련 시즌·작품: ' + _item.relations.slice(0, 8).map(_relation => '<a href="' + _escape(_relation.url) + '" target="_blank" rel="noopener noreferrer">' + _escape(_relation.title) + ' ↗</a>').join(' · ') + '</p>' : '') +
        '<div class="detail-actions">' + (_isAnime ? _animeSources(_item).map((_source, _index) => '<a class="btn ' + (_index === 0 ? 'btn-primary' : 'btn-outline') + '" href="' + _escape(_source.url) + '" target="_blank" rel="noopener noreferrer">' + _escape(_source.platform) + ' 작품 정보 ↗</a>').join('') : '<a class="btn btn-primary" href="' + _escape(_item.url) + '" target="_blank" rel="noopener noreferrer">' + (_isBoardGame ? '출판사 게임 정보 · 규칙 ↗' : _escape(_item.platform) + '에서 보기 ↗') + '</a>') +
        '<button type="button" class="btn btn-outline detail-save" data-save="' + _escape(_item.id) + '">' + _icon('bookmark') + '보관함에 담기</button></div>' +
        '<p class="detail-source">출처: <a href="' + _escape(_item.url) + '" target="_blank" rel="noopener noreferrer">' + _escape(_isBoardGame ? _item.publisher : _item.platform) + (_isBoardGame ? ' 게임 정보 ↗' : _isAnime ? ' 작품 정보 ↗' : ' 공식 작품 페이지 ↗') + '</a>.' + (_isBoardGame && _item.coverSourcePage ? ' <a href="' + _escape(_item.coverSourcePage) + '" target="_blank" rel="noopener noreferrer">제품 표지 출처 ↗</a>.' : '') + '<br>' + (_isBoardGame ? '시간은 출판사 표기 기준이며 플레이에 따라 달라집니다. 난이도는 오늘의 덕질 편집 분류입니다. 제품 표지의 권리는 각 원저작권자에게 있습니다. 언어·발매 지역에 따라 패키지가 다를 수 있습니다.' : _isAnime ? '방영 완료는 해당 시즌 기준입니다. 감상 가능 여부와 이용 연령은 감상 서비스에서 확인해주세요.' : '표지·줄거리의 권리는 원저작권자에게 있습니다. 연재 상태와 이용 연령은 공식 페이지에서 확인해주세요.') + '</p>';
      updateSavedBadge();
      _openDialog(_detailModal);
      if (_isAnime && _item.platformKey === 'laftel') {
        const _detailId = _item.id;
        document.getElementById('detailContent').dataset.item = _detailId;
        void fetch('/api/generate?resource=anime_detail&id=' + encodeURIComponent(_detailId), { signal: AbortSignal.timeout(10000) }).then(_response => _response.ok ? _response.json() : null).then(_detail => {
          if (!_detail || !window.ApiService._isValidItem(_detail) || !_detailModal.open || document.getElementById('detailContent').dataset.item !== _detailId) return;
          document.querySelector('#detailContent .detail-description').textContent = _detail.description;
          document.querySelector('#detailContent .detail-author').textContent = _detail.author;
        }).catch(() => {});
      } else document.getElementById('detailContent').dataset.item = _item.id;
    } catch (_error) {
      showToast(_error.message);
    }
  }

  function renderSavedPlansList() {
    const _catalog = window.ApiService._catalog;
    const _items = window.StorageManager.getSavedPlans().map(_entry =>
      _catalog?.items.find(_item => _item.id === _entry.id) || _entry.data
    ).filter(_item => window.ApiService._isValidItem(_item));
    savedPlansList.innerHTML = _items.length ? _items.map(_item =>
      '<article class="saved-row"><button type="button" data-detail="' + _escape(_item.id) + '" aria-label="' + _escape(_item.title) + ' 상세 보기"><img src="' + _escape(_coverUrl(_item.cover)) + '" alt="" width="52" height="68"></button>' +
      '<div class="saved-row-copy"><h3><button type="button" data-detail="' + _escape(_item.id) + '">' + _escape(_item.title) + '</button></h3><p>' + _escape(_item.genre) + ' · ' + _escape(_item.author) + '</p></div>' +
      '<button class="remove-button" type="button" data-save="' + _escape(_item.id) + '" aria-label="' + _escape(_item.title) + ' 보관함에서 삭제">삭제</button></article>'
    ).join('') : '<div class="empty-state"><span>♡</span><h3>다음 이야기를 모아볼까요?</h3><p>작품의 북마크 버튼을 누르면 여기에 담겨요.</p><button class="btn btn-outline" type="button" data-close>작품 둘러보기 ↗</button></div>';
  }

  async function _toggleSave(_id) {
    try {
      const _catalog = await window.ApiService._loadCatalog();
      const _item = _catalog.items.find(_entry => _entry.id === _id) || window._ToonpickExperience._getItem(_id) || window.StorageManager.getSavedPlans().find(_entry => _entry.id === _id)?.data;
      if (!_item) return;
      const _isSaved = window.StorageManager.getSavedPlans().some(_entry => _entry.id === _id);
      const _result = _isSaved ? window.StorageManager.deletePlan(_id) : window.StorageManager.savePlan(_item);
      if (!_result.success) { showToast(_result.error); return; }
      updateSavedBadge();
      if (savedModal.open) {
        renderSavedPlansList();
        savedModal.querySelector('[data-save], [data-close]')?.focus();
      }
      showToast(_isSaved ? '보관함에서 작품을 꺼냈어요.' : '다음에 볼 이야기로 보관했어요.');
    } catch (_error) {
      showToast(_error.message);
    }
  }

  document.getElementById('preferenceGenres').innerHTML = window.ApiService._genres.map(_genre =>
    '<label><input type="checkbox" name="genre" value="' + _genre + '"><span>' + _genre + '</span></label>'
  ).join('');
  document.getElementById('genreTabs').innerHTML = ['전체', ...window.ApiService._genres].map(_genre => '<button type="button" class="genre-tab" data-genre="' + _genre + '" aria-pressed="false">' + _genre + '</button>').join('');
  if (_isAnime) {
    document.getElementById('preferenceFormats').innerHTML = Object.entries(window.TOONPICK_PAGE.formats).map(([_key, _name]) => '<label><input type="checkbox" name="format" value="' + _key + '"><span>' + _name + '</span></label>').join('');
    document.getElementById('formatSelect').addEventListener('change', _event => { _aiData = null; _state.formats = _event.target.value === '전체' ? [] : [_event.target.value]; void _refresh(); });
  }
  if (_isBoardGame) {
    document.querySelectorAll('[data-board-filter]').forEach(_select => {
      _select.addEventListener('change', () => { _aiData = null; _state[_select.dataset.boardFilter] = Number(_select.value); void _refresh(); });
    });
  }
  _loadMoreBtn.addEventListener('click', async () => {
    _loadMoreBtn.disabled = true;
    try {
      if (_isAnime && !_aiData && window.ApiService._catalog.pagination?.hasNextPage && _visibleCount + 24 > _lastRenderData.items.length) {
        _loadMoreBtn.textContent = '다음 작품을 불러오는 중…';
        await window.ApiService._loadAnimeCatalog(_state, true);
        const _result = window.ApiService.generateFallbackPlan(_state);
        _lastRenderData = _result.data;
      }
      _visibleCount += 24;
      if (_lastRenderData) renderResult(_lastRenderData);
    } catch (_error) { showToast(_error.message); }
    finally { _loadMoreBtn.disabled = false; }
  });

  // One listener handles both static hero buttons and dynamically rendered cards.
  let _openContentMenu = null;
  function _animateContentMenu(_menu, _opening) {
    _menu.getAnimations().forEach(_animation => _animation.cancel());
    _menu.inert = !_opening;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { _menu.hidden = !_opening; return; }
    _menu.hidden = false;
    const _collapsed = { opacity: 0, transform: 'translateY(-6px)', clipPath: 'inset(0 0 100% 0 round 12px)' };
    const _expanded = { opacity: 1, transform: 'translateY(0)', clipPath: 'inset(0 0 0 0 round 12px)' };
    const _animation = _menu.animate(_opening ? [_collapsed, _expanded] : [_expanded, _collapsed], { duration: 220, easing: 'cubic-bezier(.2,.8,.2,1)' });
    if (!_opening) void _animation.finished.then(() => { _menu.hidden = true; }).catch(() => {});
  }
  function _closeContentMenu(_restoreFocus = false) {
    if (!_openContentMenu) return;
    _animateContentMenu(document.getElementById(_openContentMenu.dataset.contentMenu), false);
    _openContentMenu.setAttribute('aria-expanded', 'false');
    if (_restoreFocus) _openContentMenu.focus();
    _openContentMenu = null;
  }
  document.addEventListener('keydown', _event => {
    if (_event.key === 'Escape' && _openContentMenu) { _event.preventDefault(); _closeContentMenu(true); }
  });
  document.addEventListener('focusin', _event => {
    if (_openContentMenu && !_openContentMenu.closest('.content-menu').contains(_event.target)) _closeContentMenu();
  });
  document.addEventListener('click', _event => {
    const _button = _event.target.closest('button');
    if (_button?.dataset.contentMenu) {
      const _wasOpen = _openContentMenu === _button;
      _closeContentMenu();
      if (!_wasOpen) {
        _openContentMenu = _button;
        _animateContentMenu(document.getElementById(_button.dataset.contentMenu), true);
        _button.setAttribute('aria-expanded', 'true');
      }
      return;
    }
    _closeContentMenu();
    if (!_button) return;
    if (_button.hasAttribute('data-recommendation-minimize')) { _recommendationExperience.close(); return; }
    if (_button.hasAttribute('data-recommendation-open')) { _showRecommendationExperience(); return; }
    if (_button.hasAttribute('data-close')) { _button.closest('dialog')?.close(); return; }
    if (_button.hasAttribute('data-open-saved')) { void _openSavedPlans(); return; }
    if (_button.dataset.save) { void _toggleSave(_button.dataset.save); return; }
    if (_button.dataset.detail) { void _showDetail(_button.dataset.detail); return; }
    if (_button.hasAttribute('data-preferences')) {
      if (_recommendationStarted) { _showRecommendationExperience(); return; }
      _preferenceError.hidden = true;
      form.querySelectorAll('[name="genre"]').forEach(_input => { _input.checked = _state.genres.includes(_input.value); });
      form.querySelectorAll('[name="mood"]').forEach(_input => { _input.checked = _input.value === _state.mood; });
      form.querySelectorAll('[name="status"]').forEach(_input => { _input.checked = _input.value === (_state.status === '완결' ? '완결' : '전체'); });
      form.querySelectorAll('[name="platform"]').forEach(_input => { _input.checked = _state.platforms.includes(_input.value); });
      form.querySelectorAll('[name="format"]').forEach(_input => { _input.checked = _state.formats.includes(_input.value); });
      if (_isBoardGame) for (const _name of ['players', 'maxMinutes', 'difficulty']) form.elements[_name].value = String(_state[_name]);
      _openDialog(_preferenceModal);
      return;
    }
    if (_button.dataset.genre) {
      _aiData = null;
      _state.genres = _button.dataset.genre === '전체' ? [] : [_button.dataset.genre];
      void _refresh();
    }
    if (_button.dataset.mood) {
      _aiData = null;
      _state.mood = _state.mood === _button.dataset.mood ? '전체' : _button.dataset.mood;
      void _refresh();
      document.querySelector('.mood-section').scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });
  document.addEventListener('error', _event => {
    const _image = _event.target;
    if (_image.tagName === 'IMG' && !_image.dataset.fallback) {
      _image.dataset.fallback = 'true';
      _image.src = _coverUrl('assets/cover-placeholder.svg');
    }
  }, true);

  document.querySelectorAll('dialog').forEach(_dialog => {
    _dialog.addEventListener('click', _event => {
      if (_event.target !== _dialog) return;
      const _rect = _dialog.getBoundingClientRect();
      if (_event.clientX < _rect.left || _event.clientX > _rect.right || _event.clientY < _rect.top || _event.clientY > _rect.bottom) _dialog.close();
    });
  });

  themeToggleBtn.addEventListener('click', () => {
    applyTheme(document.body.classList.contains('dark-theme') ? 'light' : 'dark');
  });
  async function _openSavedPlans() {
    try {
      await window.ApiService._loadCatalog();
      renderSavedPlansList();
      _openDialog(savedModal);
    } catch (_error) { showToast(_error.message); }
  }
  savedPlansBtn.addEventListener('click', _openSavedPlans);
  document.querySelectorAll('.nav-link').forEach(_link => {
    _link.addEventListener('click', () => {
      _reset();
      document.querySelectorAll('.nav-link').forEach(_entry => _entry.classList.toggle('active', _entry === _link));
      if (_link.dataset.view === 'finished') {
        _state.status = '완결';
        void _refresh();
      }
      if (_isBoardGame && _link.dataset.view === 'quick') { _state.maxMinutes = 30; void _refresh(); }
      if (_link.dataset.view === 'genre') document.querySelector('[data-genre="' + window.ApiService._genres[0] + '"]')?.focus({ preventScroll: true });
    });
  });
  _searchInput.addEventListener('input', () => {
    clearTimeout(_searchTimer);
    _searchTimer = setTimeout(() => { _state.query = _searchInput.value.trim(); void _refresh(); }, _isAnime ? 450 : 120);
  });
  document.getElementById('searchForm').addEventListener('submit', _event => {
    _event.preventDefault();
    clearTimeout(_searchTimer);
    _state.query = _searchInput.value.trim();
    void _refresh();
  });
  _statusSelect.addEventListener('change', () => { _aiData = null; _state.status = _statusSelect.value; void _refresh(); });
  _sortSelect.addEventListener('change', () => { _state.sort = _sortSelect.value; void _refresh(); });
  _platformSelect.addEventListener('change', () => { _aiData = null; _state.platforms = _platformSelect.value === '전체' ? [] : [_platformSelect.value]; void _refresh(); });
  resetBtn.addEventListener('click', _reset);
  document.getElementById('emptyResetBtn').addEventListener('click', _reset);
  document.getElementById('retryBtn').addEventListener('click', () => { void _refresh(_lastRequestAI); });

  form.addEventListener('submit', async _event => {
    _event.preventDefault();
    if (_isSubmitting) return;
    _isSubmitting = true;
    submitBtn.disabled = true;
    _preferenceError.hidden = true;
    clearTimeout(_searchTimer);
    const _formData = new FormData(form);
    Object.assign(_state, { genres: _formData.getAll('genre'), mood: _formData.get('mood'), status: _formData.get('status'), platforms: _formData.getAll('platform'), formats: _formData.getAll('format'), count: Number(_formData.get('count')), query: '', sort: 'editor' });
    if (_isBoardGame) Object.assign(_state, { players: Number(_formData.get('players')), maxMinutes: Number(_formData.get('maxMinutes')), difficulty: Number(_formData.get('difficulty')) });
    _searchInput.value = '';
    try {
      if (await _refresh(true)) {
        _preferenceModal.close();
        document.getElementById('featured').scrollIntoView({ behavior: 'smooth' });
        const _heading = document.getElementById('catalogTitle');
        _heading.setAttribute('tabindex', '-1');
        _heading.focus({ preventScroll: true });
        showToast(_aiData?.source === 'ai' ? 'AI가 추천 이유와 함께 이야기를 골랐어요.' : '선택한 조건에 맞는 작품을 확인했어요.');
      } else {
        _preferenceError.textContent = alertMessage.textContent;
        _preferenceError.hidden = false;
        _openDialog(_preferenceModal);
      }
    } finally {
      _isSubmitting = false;
      submitBtn.disabled = false;
    }
  });

  _preferenceModal.addEventListener('close', () => { _recommendationFloating.hidden = !_recommendationStarted || _recommendationExperience.open; });
  _recommendationExperience.addEventListener('close', () => {
    if (!_recommendationStarted || _recommendationExperience.open) return;
    _preferenceModal.close();
    _recommendationFloating.hidden = false;
    _recommendationFloating.querySelector('button').focus({ preventScroll: true });
  });
  _pickMotionToggle.addEventListener('click', () => {
    const _paused = _recommendationExperience.dataset.paused !== 'true';
    _recommendationExperience.dataset.paused = String(_paused);
    _pickMotionToggle.setAttribute('aria-pressed', String(_paused));
    _pickMotionToggle.textContent = _paused ? '▶ 애니메이션 다시 재생' : 'Ⅱ 애니메이션 멈추기';
  });

  window.addEventListener('storage', _event => {
    if (_event.key === STORAGE_KEYS.SAVED_PLANS || _event.key === null) {
      updateSavedBadge();
      if (savedModal.open) renderSavedPlansList();
    }
    if (_event.key === STORAGE_KEYS.THEME) applyTheme(window.StorageManager.getTheme());
  });
  initTheme();
  updateSavedBadge();
  const _entryView = new URLSearchParams(window.location.search).get('view');
  if (_entryView === 'popular' && !_isBoardGame) _state.sort = 'favorites';
  if (_entryView === 'finished' && !_isBoardGame) _state.status = '완결';
  if (_entryView === 'quick' && _isBoardGame) _state.maxMinutes = 30;
  if (['genre', 'finished', 'quick'].includes(_entryView)) {
    document.querySelectorAll('.nav-link').forEach(_link => _link.classList.toggle('active', _link.dataset.view === _entryView));
  }
  void _refresh();
});
