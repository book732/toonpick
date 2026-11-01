/** Catalogue browsing and server-side AI recommendations. Credentials stay on the server. */
const API_CONFIG = {
  ENDPOINT: window.TOONPICK_PAGE?.fallbackEndpoint || 'data/webtoons.json',
  CATALOG_ENDPOINT: window.TOONPICK_PAGE?.catalogEndpoint || '/api/generate?resource=catalog',
  TIMEOUT_MS: 20000,
  RECOMMEND_ENDPOINT: '/api/generate',
  AI_TIMEOUT_MS: 120000
};

const ApiService = {
  _catalog: null,
  _catalogPromise: null,
  _animeCache: new Map(),
  _animeRequestVersion: 0,
  _platforms: window.TOONPICK_PAGE?.platforms || { naver: { key: 'naver', name: '네이버웹툰', workHosts: ['comic.naver.com'], workPattern: '^/webtoon/list$', imageHosts: ['image-comic.pstatic.net'] } },
  _genres: window.TOONPICK_PAGE?.genres || ['판타지', '로맨스', '무협', '스릴러', '일상', '드라마', '스포츠', '액션', '개그'],
  _moods: window.TOONPICK_PAGE?.moods || ['전체', '설레는', '짜릿한', '힐링', '몰입되는', '유쾌한', '뭉클한'],

  validateInputs(formData) {
    if (!formData || !Array.isArray(formData.genres) ||
        formData.genres.some(_genre => !this._genres.includes(_genre)) ||
        !this._moods.includes(formData.mood) ||
        !(window.TOONPICK_PAGE?.statuses || ['전체', '연재', '완결', '휴재']).includes(formData.status) ||
        typeof formData.query !== 'string' || formData.query.length > 100 ||
        !['editor', 'favorites', 'title'].includes(formData.sort) ||
        (formData.notes !== undefined && (typeof formData.notes !== 'string' || formData.notes.length > 600)) ||
        (formData.count !== undefined && (!Number.isInteger(formData.count) || formData.count < 1 || formData.count > 18)) ||
        (formData.players !== undefined && (!Number.isInteger(formData.players) || formData.players < 0 || formData.players > 12)) ||
        (formData.maxMinutes !== undefined && ![0, 15, 20, 30, 45, 60, 90, 120].includes(formData.maxMinutes)) ||
        (formData.difficulty !== undefined && (!Number.isInteger(formData.difficulty) || formData.difficulty < 0 || formData.difficulty > 3)) ||
        (formData.formats !== undefined && (!Array.isArray(formData.formats) || formData.formats.some(_format => !Object.hasOwn(window.TOONPICK_PAGE?.formats || {}, _format)))) ||
        (formData.platforms !== undefined && (!Array.isArray(formData.platforms) || formData.platforms.some(_key => !Object.hasOwn(this._platforms, _key))))) {
      return { isValid: false, message: '추천 조건을 확인하고 다시 선택해주세요.' };
    }
    return { isValid: true };
  },

  async _loadCatalog() {
    if (this._catalogPromise) return this._catalogPromise;
    this._catalogPromise = (async () => {
      const _controller = new AbortController();
      const _timer = setTimeout(() => _controller.abort(), API_CONFIG.TIMEOUT_MS);
      try {
        let _response = await fetch(API_CONFIG.CATALOG_ENDPOINT, { signal: _controller.signal });
        if (_response.status === 404 || _response.status === 501) {
          if (window.TOONPICK_PAGE?.type === 'anime') throw new Error('애니메이션 API가 필요합니다. Python 개발 서버로 실행해주세요.');
          _response = await fetch(API_CONFIG.ENDPOINT, { signal: _controller.signal });
        }
        if (!_response.ok) throw new Error('작품 정보를 불러오지 못했습니다. 다시 시도해주세요.');
        const _catalog = await _response.json();
        if (Array.isArray(_catalog.platforms)) {
          for (const _platform of _catalog.platforms) {
            if (/^[a-z][a-z0-9]*$/.test(_platform.key) && typeof _platform.name === 'string' && Array.isArray(_platform.workHosts) && Array.isArray(_platform.imageHosts) && typeof _platform.workPattern === 'string') this._platforms[_platform.key] = _platform;
          }
        }
        if (!Array.isArray(_catalog.items) || (!_catalog.items.length && window.TOONPICK_PAGE?.type !== 'anime') ||
            !Number.isFinite(Date.parse(_catalog.updatedAt)) ||
            _catalog.items.some(_item => !this._isValidItem(_item))) throw new Error('작품 정보 형식이 올바르지 않습니다.');
        // Build the normalized search index once for every catalogue load.
        for (const _item of _catalog.items) {
          _item._searchText = this._normalize([_item.title, ...(_item.aliases || []), _item.author, _item.genre, ..._item.tags].join(' '));
        }
        this._catalog = _catalog;
        return _catalog;
      } catch (_error) {
        this._catalogPromise = null;
        if (_error.name === 'AbortError') throw new Error('작품 정보를 불러오는 시간이 초과되었습니다. 다시 시도해주세요.');
        throw new Error(_error.message || '네트워크 연결을 확인해주세요.');
      } finally {
        clearTimeout(_timer);
      }
    })();
    return this._catalogPromise;
  },

  _normalize(_text) {
    return _text.normalize('NFKC').toLocaleLowerCase('ko-KR').replace(/\s+/g, '');
  },

  async _loadAnimeCatalog(payload, _append = false) {
    const _version = ++this._animeRequestVersion;
    const _previousCatalog = this._catalog;
    const _parameters = new URLSearchParams({ resource: 'anime_catalog', status: payload.status, query: payload.query, mood: payload.mood });
    for (const _genre of payload.genres) _parameters.append('genre', _genre);
    for (const _format of payload.formats || []) _parameters.append('format', _format);
    for (const _platform of payload.platforms || []) _parameters.append('platform', _platform);
    const _key = _parameters.toString();
    if (!_append && this._animeCache.has(_key) && Date.now() - this._animeCache.get(_key)._cachedAt < 600000) {
      this._catalog = this._animeCache.get(_key);
      this._catalogPromise = Promise.resolve(this._catalog);
      return this._catalog;
    }
    _parameters.set('page', String(_append ? (_previousCatalog.pagination?.page || 1) + 1 : 1));
    const _response = await fetch('/api/generate?' + _parameters, { signal: AbortSignal.timeout(API_CONFIG.TIMEOUT_MS) });
    const _catalog = await _response.json();
    if (!_response.ok) throw new Error(_catalog.error || '애니메이션 정보를 불러오지 못했습니다.');
    if (!Array.isArray(_catalog.items) || !Number.isFinite(Date.parse(_catalog.updatedAt)) || [..._catalog.items, ...(_catalog.heroItems || [])].some(_item => !this._isValidItem(_item))) throw new Error('애니메이션 정보 형식이 올바르지 않습니다.');
    for (const _item of _catalog.items) _item._searchText = this._normalize([_item.title, ...(_item.aliases || []), _item.author, ..._item.tags].join(' '));
    if (_append) {
      const _byId = new Map([..._previousCatalog.items, ..._catalog.items].map(_item => [_item.id, _item]));
      _catalog.items = [..._byId.values()];
      _catalog.heroItems = _previousCatalog.heroItems;
    }
    _catalog._cachedAt = Date.now();
    if (_version === this._animeRequestVersion) {
      this._catalog = _catalog;
      this._catalogPromise = Promise.resolve(_catalog);
    }
    this._animeCache.set(_key, _catalog);
    if (this._animeCache.size > 12) this._animeCache.delete(this._animeCache.keys().next().value);
    return _catalog;
  },

  _isValidAnimeSource(_source) {
    if (!_source || !['laftel', 'netflix'].includes(_source.platformKey) ||
        typeof _source.id !== 'string' || !new RegExp('^' + _source.platformKey + ':[a-f0-9]{20}$').test(_source.id)) return false;
    const _platform = this._platforms[_source.platformKey];
    if (!_platform || _source.platform !== _platform.name) return false;
    try {
      const _url = new URL(_source.url);
      return _url.protocol === 'https:' && _platform.workHosts.includes(_url.hostname) &&
        !_url.username && !_url.password && !_url.port && new RegExp(_platform.workPattern).test(_url.pathname);
    } catch (_) { return false; }
  },

  _isValidItem(_item) {
    if (!_item || typeof _item.id !== 'string' || !/^(?:\d+|[a-z][a-z0-9]*:[a-f0-9]{20})$/.test(_item.id) ||
        !['title', 'author', 'description', 'genre', 'status', 'age', 'cover'].every(_key => typeof _item[_key] === 'string') ||
        !Array.isArray(_item.tags) || !_item.tags.every(_tag => typeof _tag === 'string') ||
        !Array.isArray(_item.days) || !_item.days.every(_day => typeof _day === 'string') ||
        !Number.isFinite(_item.favorites)) return false;
    const _key = _item.platformKey || 'naver';
    const _platform = this._platforms[_key];
    if (!_platform || _item.platform !== _platform.name) return false;
    if (window.TOONPICK_PAGE?.type === 'anime' && _item.sources !== undefined &&
        (!Array.isArray(_item.sources) || !_item.sources.length || _item.sources.length > 2 ||
         new Set(_item.sources.map(_source => _source?.platformKey)).size !== _item.sources.length ||
         _item.sources.some(_source => !this._isValidAnimeSource(_source)))) return false;
    if (_key === 'naver') {
      if (!/^\d+$/.test(_item.id) || _item.url !== 'https://comic.naver.com/webtoon/list?titleId=' + _item.id) return false;
    } else {
      if (!_item.id.startsWith(_key + ':')) return false;
      try {
        const _work = new URL(_item.url);
        if (_work.protocol !== 'https:' || !_platform.workHosts.includes(_work.hostname) || _work.username || _work.password || _work.port || !new RegExp(_platform.workPattern).test(_work.pathname)) return false;
      } catch (_) { return false; }
    }
    if (_item.cover === 'assets/cover-placeholder.svg') return true;
    if (window.TOONPICK_PAGE?.type === 'boardgame' && typeof _item.slug === 'string' && /^[a-z0-9-]+$/.test(_item.slug) && ['jpg', 'png', 'webp'].some(_extension => _item.cover === 'assets/boardgames/' + _item.slug + '.' + _extension)) return true;
    if (_item.cover === 'assets/covers/' + _item.id + '.jpg') return true;
    try {
      const _cover = new URL(_item.cover);
      return _cover.protocol === 'https:' && _platform.imageHosts.some(_host => _cover.hostname === _host || (_host.startsWith('*.') && (_cover.hostname === _host.slice(2) || _cover.hostname.endsWith('.' + _host.slice(2))))) && !_cover.username && !_cover.password && !_cover.port;
    } catch (_) { return false; }
  },

  async generateTripPlan(payload, onProgressUpdate = () => {}, _source = null) {
    const validation = this.validateInputs(payload);
    if (!validation.isValid) throw new Error(validation.message);
    if (window.TOONPICK_PAGE?.type === 'anime' && !payload.ai && _source === null) await this._loadAnimeCatalog(payload);
    else await this._loadCatalog();
    if (payload.ai === true) return this._requestRecommendations(payload, onProgressUpdate);
    const _result = this.generateFallbackPlan(payload, _source);
    onProgressUpdate({ percent: 100, text: '취향에 맞는 이야기를 골랐어요.' });
    return _result;
  },

  async _requestRecommendations(payload, onProgressUpdate) {
    const _excludedIds = window.StorageManager._getSeenItems().map(_entry => _entry.id);
    const _controller = new AbortController();
    const _timer = setTimeout(() => _controller.abort(), API_CONFIG.AI_TIMEOUT_MS);
    onProgressUpdate({ percent: 10, text: 'AI가 취향과 작품 줄거리를 함께 살펴보고 있어요.' });
    try {
      const _response = await fetch(API_CONFIG.RECOMMEND_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify({ type: window.TOONPICK_PAGE?.type || 'webtoon', genres: payload.genres, mood: payload.mood, status: payload.status, notes: payload.notes || '', platforms: payload.platforms || [], count: payload.count ?? 6, excludedIds: _excludedIds, ...(window.TOONPICK_PAGE?.type === 'anime' ? { formats: payload.formats || [] } : {}), ...(window.TOONPICK_PAGE?.type === 'boardgame' ? { players: payload.players || 0, maxMinutes: payload.maxMinutes || 0, difficulty: payload.difficulty || 0 } : {}) }),
        signal: _controller.signal
      });
      let _result;
      try { _result = await _response.json(); }
      catch (_error) {
        if (_error.name === 'AbortError') throw _error;
        throw new Error('AI 추천 서버의 응답이 올바르지 않습니다. 개발 서버로 실행했는지 확인해주세요.');
      }
      if (!_response.ok || !_result.success) throw new Error(typeof _result.error === 'string' ? _result.error : 'AI 추천에 실패했습니다. 다시 시도해주세요.');
      const _data = _result.data;
      if (!_data || !Array.isArray(_data.items) || _data.items.length > (payload.count ?? 6) ||
          !['ai', 'filters'].includes(_data.source) || typeof _data.summary !== 'string' ||
          _data.summary.length > 240 || !Number.isFinite(Date.parse(_data.updatedAt)) ||
          (_data.source === 'ai' && typeof _data.model !== 'string')) {
        throw new Error('AI 추천 데이터가 올바르지 않습니다. 다시 시도해주세요.');
      }
      const _seen = new Set();
      const _items = _data.items.map(_entry => {
        const _item = this._catalog.items.find(_candidate => _candidate.id === _entry?.id) || (this._isValidItem(_entry) ? _entry : null);
        if (!_item || _seen.has(_item.id) || typeof _entry.recommendationReason !== 'string' ||
            !_entry.recommendationReason.trim() || _entry.recommendationReason.length > 240 ||
            (payload.genres.length && !payload.genres.some(_genre => (_item.genres || [_item.genre]).includes(_genre))) ||
            (payload.formats?.length && !payload.formats.includes(_item.format)) ||
            !this._matchesBoardGame(_item, payload) ||
            (payload.status !== '전체' && _item.status !== payload.status) ||
            (payload.platforms?.length && !payload.platforms.includes(_item.platformKey || 'naver'))) {
          throw new Error('AI 추천에 유효하지 않은 작품이 포함되어 있습니다.');
        }
        _seen.add(_item.id);
        const _resolved = { ..._item, recommendationReason: _entry.recommendationReason, discovery: _entry.discovery === 'web' ? 'web' : 'catalog' };
        _resolved._searchText = this._normalize([_resolved.title, ...(_resolved.aliases || []), _resolved.author, _resolved.genre, ..._resolved.tags].join(' '));
        if (!this._catalog.items.some(_candidate => _candidate.id === _resolved.id)) this._catalog.items.push(_resolved);
        return _resolved;
      });
      onProgressUpdate({ percent: 100, text: 'AI가 추천할 이야기를 골랐어요.' });
      // Recheck local state after the request; the reader may mark a work while AI is loading.
      const _currentSeen = window.StorageManager._getSeenKeys();
      return { success: true, data: { ..._data, items: _items.filter(_item => !_currentSeen.has(window.StorageManager._getSeenKey(_item))) } };
    } catch (_error) {
      if (_error.name === 'AbortError') throw new Error('AI 추천 시간이 초과되었습니다. 다시 추천받아주세요.');
      throw _error;
    } finally {
      clearTimeout(_timer);
    }
  },

  _matchesBoardGame(_item, payload) {
    return window.TOONPICK_PAGE?.type !== 'boardgame' ||
      ((!payload.players || (_item.minPlayers !== null && _item.minPlayers <= payload.players && (_item.maxPlayers === null || payload.players <= _item.maxPlayers))) &&
       (!payload.maxMinutes || (_item.maxMinutes !== null && _item.maxMinutes <= payload.maxMinutes)) &&
       (!payload.difficulty || (_item.difficulty > 0 && _item.difficulty <= payload.difficulty)));
  },

  generateFallbackPlan(payload, _source = null) {
    const validation = this.validateInputs(payload);
    if (!validation.isValid) throw new Error(validation.message);
    if (!this._catalog) throw new Error('작품 정보를 먼저 불러와주세요.');
    const _query = this._normalize(payload.query);
    const _items = (_source || this._catalog.items).filter(_item =>
      (!payload.genres.length || payload.genres.some(_genre => (_item.genres || [_item.genre]).includes(_genre))) &&
      (_source !== null || payload.mood === '전체' || _item.tags.includes(payload.mood)) &&
      (payload.status === '전체' || _item.status === payload.status) &&
      (!payload.platforms?.length || payload.platforms.includes(_item.platformKey || 'naver')) &&
      (!payload.formats?.length || payload.formats.includes(_item.format)) &&
      this._matchesBoardGame(_item, payload) &&
      (!_query || window.TOONPICK_PAGE?.type === 'anime' || _item._searchText.includes(_query))
    );
    if (payload.sort === 'favorites') _items.sort((_a, _b) => _b.favorites - _a.favorites);
    if (payload.sort === 'title') {
      const _collator = new Intl.Collator('ko', { numeric: true });
      const _rank = _title => /^[가-힣ㄱ-ㅎㅏ-ㅣ]/u.test(_title.trimStart()) ? 0 : 1;
      _items.sort((_a, _b) => _rank(_a.title) - _rank(_b.title) || _collator.compare(_a.title, _b.title));
    }
    if (payload.sort === 'editor' && _source === null) {
      // Rotate platform queues only for catalogue browsing; preserve the AI's order.
      const _groups = new Map();
      for (const _item of _items) {
        const _key = _item.platformKey || 'naver';
        if (!_groups.has(_key)) _groups.set(_key, []);
        _groups.get(_key).push(_item);
      }
      const _queues = [..._groups.values()];
      const _interleaved = [];
      for (let _offset = 0; _interleaved.length < _items.length; _offset++) {
        for (const _queue of _queues) if (_offset < _queue.length) _interleaved.push(_queue[_offset]);
      }
      _items.splice(0, _items.length, ..._interleaved);
    }
    return { success: true, data: { items: _items, updatedAt: this._catalog.updatedAt } };
  }
};
window.ApiService = ApiService;
