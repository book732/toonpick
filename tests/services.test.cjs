const _test = require('node:test');
const _assert = require('node:assert/strict');
const _fs = require('node:fs');
const _path = require('node:path');
const _vm = require('node:vm');

const _root = _path.resolve(__dirname, '..');
const _fixture = JSON.parse(_fs.readFileSync(_path.join(_root, 'data/webtoons.json'), 'utf8'));
const _allItems = _fixture.items;
_fixture.items = _fixture.items.slice(0, 14);
const _defaults = { genres: [], mood: '전체', status: '전체', query: '', sort: 'editor' };

function _context(_fetch, _anime = false) {
  const _storage = new Map();
  const _sandbox = _vm.createContext({
    window: { matchMedia: () => ({ matches: false }) }, console,
    localStorage: {
      getItem: _key => _storage.get(_key) ?? null,
      setItem: (_key, _value) => _storage.set(_key, _value)
    },
    fetch: _fetch || (async () => ({ ok: true, json: async () => structuredClone(_fixture) })),
    AbortController, AbortSignal, URL, URLSearchParams, setTimeout, clearTimeout
  });
  for (const _file of [...(_anime === 'boardgame' ? ['boardgames.js'] : _anime ? ['anime.js'] : []), 'storage.js', 'api.js']) {
    _vm.runInContext(_fs.readFileSync(_path.join(_root, 'js', _file), 'utf8'), _sandbox);
  }
  return { _sandbox, _storage, _api: _sandbox.window.ApiService, _manager: _sandbox.window.StorageManager };
}

_test('catalogue contains unique official titles and trusted cover references', () => {
  _assert.equal(new Set(_fixture.items.map(_item => _item.id)).size, _fixture.items.length);
  for (const _item of _fixture.items) {
    if (_item.cover.startsWith('assets/')) {
      const _bytes = _fs.readFileSync(_path.join(_root, _item.cover));
      _assert.equal(_bytes.readUInt16BE(0), 0xffd8);
    } else _assert.equal(new URL(_item.cover).hostname, 'image-comic.pstatic.net');
    _assert.equal(_item.url, 'https://comic.naver.com/webtoon/list?titleId=' + _item.id);
  }
});

_test('board game required titles, aliases, hard filters and collections remain separate', async () => {
  const _catalog = JSON.parse(_fs.readFileSync(_path.join(_root, 'data/boardgames_catalog.json'), 'utf8'));
  const { _api, _manager, _storage } = _context(async () => ({ ok: true, json: async () => structuredClone(_catalog) }), 'boardgame');
  const _defaultsBoard = { ..._defaults, players: 0, maxMinutes: 0, difficulty: 0 };
  const _all = (await _api.generateTripPlan(_defaultsBoard)).data.items;
  _assert.ok(_all.some(_item => _item.slug === 'splendor'));
  _assert.ok(_all.some(_item => _item.slug === 'the-game'));
  _assert.ok(_all.every(_item => _api._isValidItem(_item)));
  _assert.equal((await _api.generateTripPlan({ ..._defaultsBoard, query: '스플랜더' })).data.items[0].slug, 'splendor');
  const _filtered = (await _api.generateTripPlan({ ..._defaultsBoard, players: 2, maxMinutes: 30, difficulty: 2 })).data.items;
  _assert.ok(_filtered.length > 0);
  _assert.ok(_filtered.every(_item => _item.minPlayers <= 2 && (_item.maxPlayers === null || _item.maxPlayers >= 2) && _item.maxMinutes <= 30 && _item.difficulty <= 2));
  _storage.set('toonpick_saved_webtoons', 'webtoon');
  _storage.set('toonpick_saved_anime', 'anime');
  _manager.savePlan(_all[0]);
  _assert.equal(_storage.get('toonpick_saved_webtoons'), 'webtoon');
  _assert.equal(_storage.get('toonpick_saved_anime'), 'anime');
  _assert.equal(_manager.getSavedPlans().length, 1);
  _assert.equal(_api._isValidItem({ ..._all[0], cover: 'assets/boardgames/../../bad.svg' }), false);
});

_test('anime merged service links retain only distinct trusted official sources', async () => {
  const _catalog = JSON.parse(_fs.readFileSync(_path.join(_root, 'data/anime_domestic.json'), 'utf8'));
  const { _api } = _context(async () => ({ ok: true, json: async () => _catalog }), 'anime');
  await _api._loadCatalog();
  const _item = _catalog.items.find(_entry => _entry.platformKey === 'laftel');
  const _other = _catalog.items.find(_entry => _entry.platformKey === 'netflix');
  const _sources = [_item, _other].map(({ id, platformKey, platform, url }) => ({ id, platformKey, platform, url }));
  _assert.equal(_api._isValidItem({ ..._item, sources: _sources }), true);
  _assert.equal(_api._isValidItem({ ..._item, sources: [_sources[0], _sources[0]] }), false);
  for (const _url of ['javascript:alert(1)', 'https://evil.example/item/1', 'https://laftel.net.evil.example/item/1']) {
    _assert.equal(_api._isValidItem({ ..._item, sources: [{ ..._sources[0], url: _url }] }), false);
  }
});

_test('anime uses its own provider, formats, genre alternatives and storage namespace', async () => {
  const _item = { ..._fixture.items[0], id: 'laftel:' + 'a'.repeat(20), animeId: '1', platformKey: 'laftel', platform: '라프텔', url: 'https://laftel.net/item/1', cover: 'https://thumbnail.laftel.net/test.jpg', genre: '액션', genres: ['액션', '판타지'], format: 'TV', aliases: ['Cowboy Bebop'] };
  let _calls = 0;
  const { _api, _manager, _storage } = _context(async () => {
    _calls++;
    return { ok: true, json: async () => ({ items: [structuredClone(_item)], updatedAt: _fixture.updatedAt, pagination: { page: 1, hasNextPage: true } }) };
  }, true);
  const _payload = { ..._defaults, genres: ['판타지'], formats: ['TV'] };
  _assert.equal((await _api.generateTripPlan(_payload)).data.items.length, 1);
  _assert.equal((await _api.generateTripPlan(_payload)).data.items.length, 1);
  _assert.equal(_calls, 1);
  _assert.equal(_api.generateFallbackPlan({ ..._payload, formats: ['MOVIE'] }).data.items.length, 0);
  _assert.equal(_api._isValidItem({ ..._item, url: 'https://evil.example/anime/1' }), false);
  _storage.set('toonpick_saved_webtoons', 'untouched');
  _assert.equal(_manager.savePlan(_item).success, true);
  _assert.equal(_manager.getSavedPlans()[0].id, _item.id);
  _assert.equal(_storage.get('toonpick_saved_webtoons'), 'untouched');
});

_test('the complete domestic anime snapshot uses valid Korean-service work and cover URLs', () => {
  const { _api } = _context(null, true);
  const _catalog = JSON.parse(_fs.readFileSync(_path.join(_root, 'data/anime_domestic.json'), 'utf8'));
  _assert.equal(_catalog.items.length, 9869);
  _assert.ok(_catalog.items.every(_item => _api._isValidItem(_item)));
  const _netflix = _catalog.items.find(_item => _item.platformKey === 'netflix');
  _assert.equal(_api._isValidItem({ ..._netflix, cover: 'https://nflxso.net.evil.example/cover.jpg' }), false);
  _assert.equal(_api._isValidItem({ ..._netflix, url: 'https://www.netflix.com.evil.example/kr/title/123' }), false);
});

_test('the expanded board games have trusted package covers and unknown difficulty never passes a ceiling', () => {
  const { _api } = _context(null, 'boardgame');
  const _catalog = JSON.parse(_fs.readFileSync(_path.join(_root, 'data/boardgames_catalog.json'), 'utf8'));
  const _report = JSON.parse(_fs.readFileSync(_path.join(_root, 'data/boardgames_collection_report.json'), 'utf8'));
  _assert.equal(_catalog.items.length, _report.finalCount);
  _assert.ok(_catalog.items.length > 300);
  _assert.ok(_catalog.items.every(_item => _api._isValidItem(_item)));
  const _unknown = _catalog.items.find(_item => _item.difficulty === 0);
  _assert.equal(_api._matchesBoardGame(_unknown, {difficulty:1}), false);
  _assert.equal(_api._matchesBoardGame(_unknown, {difficulty:3}), false);
  _assert.equal(_api._matchesBoardGame(_unknown, {difficulty:0}), true);
  const _unknownPlayers = _catalog.items.find(_item => _item.minPlayers === null);
  _assert.equal(_api._matchesBoardGame(_unknownPlayers, {players:2}), false);
  _assert.equal(_api._matchesBoardGame(_unknownPlayers, {players:0}), true);
});

_test('anime pagination merges repeated IDs', async () => {
  const _base = { ..._fixture.items[0], id: 'laftel:' + 'a'.repeat(20), animeId: '1', platformKey: 'laftel', platform: '라프텔', url: 'https://laftel.net/item/1', cover: 'https://thumbnail.laftel.net/test.jpg', format: 'TV', genres: ['판타지'] };
  const _new = { ..._base, id: 'laftel:' + 'b'.repeat(20), animeId: '2', url: 'https://laftel.net/item/2' };
  const { _api } = _context(async _url => ({ ok: true, json: async () => ({ items: _url.includes('page=2') ? [structuredClone(_base), structuredClone(_new)] : [structuredClone(_base)], updatedAt: _fixture.updatedAt, pagination: { page: _url.includes('page=2') ? 2 : 1, hasNextPage: false } }) }), true);
  await _api.generateTripPlan(_defaults);
  await _api._loadAnimeCatalog(_defaults, true);
  _assert.equal(_api._catalog.items.length, 2);
  _assert.equal(_api._catalog.pagination.page, 2);
  _assert.equal(_api._catalog.items[1].id, _new.id);
});

_test('a slower anime search cannot replace the newest active query', async () => {
  const _base = { ..._fixture.items[0], id: 'laftel:' + 'a'.repeat(20), animeId: '1', platformKey: 'laftel', platform: '라프텔', url: 'https://laftel.net/item/1', cover: 'https://thumbnail.laftel.net/test.jpg', format: 'TV' };
  const _pending = new Map();
  const { _api } = _context(_url => new Promise(_resolve => _pending.set(new URL(_url, 'http://localhost').searchParams.get('query'), _resolve)), true);
  const _old = _api._loadAnimeCatalog({ ..._defaults, query: 'old' });
  const _latest = _api._loadAnimeCatalog({ ..._defaults, query: 'latest' });
  const _reply = _title => ({ ok: true, json: async () => ({ items: [{ ..._base, title: _title }], updatedAt: _fixture.updatedAt, pagination: { page: 1 } }) });
  _pending.get('latest')(_reply('Latest'));
  await _latest;
  _pending.get('old')(_reply('Old'));
  await _old;
  _assert.equal(_api._catalog.items[0].title, 'Latest');
  _assert.equal((await _api._loadCatalog()).items[0].title, 'Latest');
});

_test('genre alternatives use OR while mood and status use AND', async () => {
  const { _api } = _context();
  const _payload = { ..._defaults, genres: ['로맨스', '개그'], mood: '유쾌한' };
  const _result = await _api.generateTripPlan(_payload);
  _assert.ok(_result.data.items.length > 0);
  _assert.ok(_result.data.items.every(_item => _payload.genres.includes(_item.genre) && _item.tags.includes('유쾌한')));
  const _finished = await _api.generateTripPlan({ ..._payload, status: '완결' });
  _assert.ok(_finished.data.items.every(_item => _item.status === '완결'));
});

_test('conflicting preferences return an empty result without relaxing conditions', async () => {
  const { _api } = _context();
  const _result = await _api.generateTripPlan({ ..._defaults, genres: ['스릴러'], mood: '설레는' });
  _assert.equal(_result.data.items.length, 0);
});

_test('search normalizes spacing, case and compatibility characters', async () => {
  const { _api } = _context();
  const _title = await _api.generateTripPlan({ ..._defaults, query: '전지적독자시점' });
  _assert.equal(_title.data.items[0].id, '747269');
  const _author = await _api.generateTripPlan({ ..._defaults, query: 'ｕｍｉ' });
  _assert.equal(_author.data.items[0].id, '747269');
  const _tag = await _api.generateTripPlan({ ..._defaults, query: '세계관' });
  _assert.ok(_tag.data.items.length > 0);
  _assert.ok(_tag.data.items.every(_item => _item.tags.includes('세계관')));
});

_test('Korean title sorting puts Hangul first and orders numeric titles naturally', async () => {
  const { _api } = _context(async () => ({ ok: true, json: async () => structuredClone(_fixture) }));
  await _api._loadCatalog();
  const _titles = ['13 비버', '나의 이야기', '가나다', '2 게임', 'ABC', 'ㄱ 이야기'];
  _api._catalog.items = _titles.map((_title, _index) => ({ ..._api._catalog.items[0], id: String(_index), title: _title }));
  const _items = _api.generateFallbackPlan({ ..._defaults, sort: 'title' }).data.items;
  _assert.deepEqual(Array.from(_items, _item => _item.title), ['ㄱ 이야기', '가나다', '나의 이야기', '2 게임', '13 비버', 'ABC']);
  _assert.deepEqual(Array.from(_api._catalog.items, _item => _item.title), _titles);
});

_test('sorting does not mutate the source editor order', async () => {
  const { _api } = _context();
  const _sorted = await _api.generateTripPlan({ ..._defaults, sort: 'favorites' });
  _assert.ok(_sorted.data.items.every((_item, _index, _items) => !_index || _items[_index - 1].favorites >= _item.favorites));
  const _restored = await _api.generateTripPlan(_defaults);
  _assert.equal(JSON.stringify(_restored.data.items.map(_item => _item.id)), JSON.stringify(_fixture.items.map(_item => _item.id)));
});

_test('default browsing rotates real platforms while explicit sorting and AI order remain intact', async () => {
  const _mixed = structuredClone({ ..._fixture, items: _allItems });
  const { _api } = _context(async () => ({ ok: true, json: async () => _mixed }));
  const _original = _mixed.items.map(_item => _item.id);
  const _result = await _api.generateTripPlan(_defaults);
  const _platformCount = new Set(_mixed.items.map(_item => _item.platformKey || 'naver')).size;
  _assert.equal(new Set(_result.data.items.slice(0, _platformCount).map(_item => _item.platformKey || 'naver')).size, _platformCount);
  _assert.equal(_result.data.items.length, _allItems.length);
  _assert.equal(new Set(_result.data.items.map(_item => _item.id)).size, _allItems.length);
  _assert.deepEqual(_mixed.items.map(_item => _item.id), _original);
  const _ranked = [_result.data.items[3], _result.data.items[0], _result.data.items[1]];
  _assert.equal(JSON.stringify(_api.generateFallbackPlan(_defaults, _ranked).data.items.map(_item => _item.id)), JSON.stringify(_ranked.map(_item => _item.id)));
  const _popular = await _api.generateTripPlan({ ..._defaults, sort: 'favorites' });
  _assert.ok(_popular.data.items.every((_item, _index, _items) => !_index || _items[_index - 1].favorites >= _item.favorites));
});

_test('invalid recommendation inputs are rejected before fetching', async () => {
  let _calls = 0;
  const { _api } = _context(async () => { _calls++; throw new Error('Unexpected fetch'); });
  for (const _payload of [null, { ..._defaults, genres: '로맨스' }, { ..._defaults, genres: ['unknown'] }, { ..._defaults, query: 1 }, { ..._defaults, query: 'a'.repeat(101) }, { ..._defaults, mood: 'unknown' }]) {
    await _assert.rejects(_api.generateTripPlan(_payload));
  }
  _assert.equal(_calls, 0);
});

_test('recommendation count supports one to eighteen with a default of six', async () => {
  const { _api } = _context();
  for (const _count of [1, 6, 12, 18]) _assert.equal(_api.validateInputs({ ..._defaults, count: _count }).isValid, true);
  for (const _count of [0, 19, -1, 2.5, '6', null]) _assert.equal(_api.validateInputs({ ..._defaults, count: _count }).isValid, false);
  const _items = _fixture.items.slice(0, 12).map(_item => ({ ..._item, recommendationReason: '취향에 맞는 작품입니다.' }));
  let _posted;
  const { _api: _liveApi } = _context(async (_url, _options) => {
    if (_options?.method === 'POST') {
      _posted = JSON.parse(_options.body);
      return { ok: true, json: async () => ({ success: true, data: { source: 'ai', model: 'test', summary: '추천 결과', updatedAt: _fixture.updatedAt, items: _items } }) };
    }
    return { ok: true, json: async () => structuredClone(_fixture) };
  });
  _assert.equal((await _liveApi.generateTripPlan({ ..._defaults, ai: true, count: 12 })).data.items.length, 12);
  _assert.equal(_posted.count, 12);
  await _assert.rejects(_liveApi.generateTripPlan({ ..._defaults, ai: true, count: 3 }), /데이터/);
});

_test('concurrent recommendations share one catalogue request', async () => {
  let _calls = 0;
  const { _api } = _context(async () => {
    _calls++;
    return { ok: true, json: async () => structuredClone(_fixture) };
  });
  await Promise.all([_api.generateTripPlan(_defaults), _api.generateTripPlan({ ..._defaults, genres: ['무협'] })]);
  _assert.equal(_calls, 1);
});

_test('failed catalogue requests can be retried', async () => {
  let _calls = 0;
  const { _api } = _context(async () => {
    if (++_calls === 1) throw new Error('offline');
    return { ok: true, json: async () => structuredClone(_fixture) };
  });
  await _assert.rejects(_api.generateTripPlan(_defaults));
  _assert.equal((await _api.generateTripPlan(_defaults)).data.items.length, _fixture.items.length);
  _assert.equal(_calls, 2);
});

_test('untrusted catalogue links are rejected', async () => {
  const _broken = structuredClone(_fixture);
  _broken.items[0].url = 'javascript:alert(1)';
  const { _api } = _context(async () => ({ ok: true, json: async () => _broken }));
  await _assert.rejects(_api.generateTripPlan(_defaults), /형식/);
});

_test('catalogue loading times out and remains retryable', async () => {
  const { _api, _sandbox } = _context((_url, _options) => new Promise((_resolve, _reject) => {
    _options.signal.addEventListener('abort', () => _reject(Object.assign(new Error('aborted'), { name: 'AbortError' })));
  }));
  _vm.runInContext('API_CONFIG.TIMEOUT_MS = 5', _sandbox);
  await _assert.rejects(_api.generateTripPlan(_defaults), /초과/);
  _assert.equal(_api._catalogPromise, null);
});

_test('collections preserve more than five items, deduplicate by ID and delete correctly', () => {
  const { _manager } = _context();
  for (const _item of _fixture.items) _assert.equal(_manager.savePlan(_item).success, true);
  _manager.savePlan(_fixture.items[0]);
  _assert.equal(_manager.getSavedPlans().length, _fixture.items.length);
  _assert.equal(_manager.deletePlan(_fixture.items[0].id).success, true);
  _assert.ok(!_manager.getSavedPlans().some(_item => _item.id === _fixture.items[0].id));
});

_test('corrupted storage is ignored and write failures are reported', () => {
  const { _manager, _storage, _sandbox } = _context();
  for (const _raw of ['{broken', '{}', '[null, 42, {"id": "bad"}]']) {
    _storage.set('toonpick_saved_webtoons', _raw);
    _assert.equal(_manager.getSavedPlans().length, 0);
  }
  _sandbox.localStorage.setItem = () => { throw new Error('quota'); };
  _assert.equal(_manager.savePlan(_fixture.items[0]).success, false);
  _assert.equal(_manager.deletePlan(_fixture.items[0].id).success, false);
});

_test('invalid saved themes fall back to the system preference', () => {
  const { _manager, _storage } = _context();
  _storage.set('toonpick_theme', 'invalid');
  _assert.equal(_manager.getTheme(), 'light');
  _manager.setTheme('dark');
  _assert.equal(_manager.getTheme(), 'dark');
});

function _aiResponse(_items = [{ ..._fixture.items[0], recommendationReason: '취향에 맞는 성장 이야기예요.' }]) {
  return { success: true, data: { items: _items, source: 'ai', model: 'gpt-5.5', summary: 'AI가 고른 이야기입니다.', updatedAt: _fixture.updatedAt } };
}

_test('AI requests use the server endpoint and send only reader preferences', async () => {
  let _posted;
  const { _api } = _context(async (_url, _options) => {
    if (_url === '/api/generate?resource=catalog') return { ok: true, json: async () => structuredClone(_fixture) };
    _assert.equal(_url, '/api/generate');
    _posted = JSON.parse(_options.body);
    return { ok: true, json: async () => _aiResponse() };
  });
  const _result = await _api.generateTripPlan({ ..._defaults, ai: true, notes: '성장 이야기' });
  _assert.deepEqual(Object.keys(_posted).sort(), ['type', 'genres', 'mood', 'status', 'notes', 'platforms', 'count', 'excludedIds'].sort());
  _assert.equal(_posted.count, 6);
  _assert.equal(_posted.type, 'webtoon');
  _assert.equal(_posted.notes, '성장 이야기');
  _assert.equal(_result.data.source, 'ai');
  _assert.ok(_result.data.items[0].recommendationReason);
});

_test('AI results resolve trusted titles and links from the local catalogue', async () => {
  const _unsafe = _aiResponse([{ ..._fixture.items[0], title: '<script>bad</script>', url: 'javascript:bad()', recommendationReason: '이야기 추천' }]);
  const { _api } = _context(async _url => ({ ok: true, json: async () => _url === '/api/generate?resource=catalog' ? structuredClone(_fixture) : _unsafe }));
  const _result = await _api.generateTripPlan({ ..._defaults, ai: true });
  _assert.equal(_result.data.items[0].title, _fixture.items[0].title);
  _assert.equal(_result.data.items[0].url, _fixture.items[0].url);
});

_test('seen marks persist independently of collections, toggle equivalent editions and isolate categories', () => {
  for (const _type of [false, true, 'boardgame']) {
    const { _manager, _storage, _sandbox } = _context(null, _type);
    const _item = { ..._fixture.items[0], title: '테스트 (자막)', format: 'TV' };
    _manager.savePlan(_item);
    _assert.equal(_manager._toggleSeen(_item).seen, true);
    _assert.equal(_manager._getSeenKeys().has(_manager._getSeenKey(_item)), true);
    _vm.runInContext(_fs.readFileSync(_path.join(_root, 'js/storage.js'), 'utf8'), _vm.createContext({ window: _sandbox.window, localStorage: _sandbox.localStorage }));
    _assert.equal(_sandbox.window.StorageManager._getSeenItems().length, 1);
    _assert.equal(_manager.getSavedPlans().length, 1);
    _assert.ok(_storage.has(_manager._seenStorageKey));
    if (_type === true) {
      _assert.equal(_manager._getSeenKey({ ..._item, title: '테스트 (더빙)' }), _manager._getSeenKey(_item));
      _assert.notEqual(_manager._getSeenKey({ ..._item, title: '테스트 2기' }), _manager._getSeenKey(_item));
      _assert.notEqual(_manager._getSeenKey({ ..._item, format: 'MOVIE' }), _manager._getSeenKey(_item));
    }
    _assert.equal(_manager._toggleSeen(_item).seen, false);
    _assert.equal(_manager._getSeenItems().length, 0);
    for (const _other of ['toonpick_saved_webtoons_seen', 'toonpick_saved_anime_seen', 'toonpick_saved_boardgames_seen']) {
      if (_other !== _manager._seenStorageKey) _assert.equal(_storage.has(_other), false);
    }
    _storage.set(_manager._seenStorageKey, '[null,{"id":"bad","key":"x"}]');
    _assert.equal(_manager._getSeenItems().length, 0);
    _sandbox.localStorage.setItem = () => { throw new Error('denied'); };
    _assert.equal(_manager._toggleSeen(_item).success, false);
  }
});

_test('AI sends seen IDs and filters marks made while the request is pending without hiding discovery', async () => {
  let _posted;
  let _manager;
  const _contextResult = _context(async (_url, _options) => {
    if (!_options?.body) return { ok: true, json: async () => structuredClone(_fixture) };
    _posted = JSON.parse(_options.body);
    _manager._toggleSeen(_fixture.items[1]);
    return { ok: true, json: async () => _aiResponse() };
  });
  _manager = _contextResult._manager;
  _manager._toggleSeen(_fixture.items[0]);
  const _result = await _contextResult._api.generateTripPlan({ ..._defaults, ai: true });
  _assert.deepEqual(_posted.excludedIds, [_fixture.items[0].id]);
  _assert.ok(_result.data.items.every(_item => ![_fixture.items[0].id, _fixture.items[1].id].includes(_item.id)));
  _assert.ok(_contextResult._api.generateFallbackPlan(_defaults).data.items.some(_item => _item.id === _fixture.items[0].id));
});

_test('AI failures remain failures instead of silently returning local recommendations', async () => {
  const { _api } = _context(async _url => _url === '/api/generate?resource=catalog' ?
    { ok: true, json: async () => structuredClone(_fixture) } :
    { ok: false, json: async () => ({ success: false, error: 'AI busy' }) });
  await _assert.rejects(_api.generateTripPlan({ ..._defaults, ai: true }), /AI busy/);
});

_test('AI duplicate IDs, unknown IDs and missing reasons are rejected', async () => {
  const _entry = { ..._fixture.items[0], recommendationReason: '성장하는 이야기' };
  for (const _items of [[_entry, _entry], [{ ..._entry, id: 'unknown' }], [{ ..._entry, recommendationReason: '' }]]) {
    const { _api } = _context(async _url => ({ ok: true, json: async () => _url === '/api/generate?resource=catalog' ? structuredClone(_fixture) : _aiResponse(_items) }));
    await _assert.rejects(_api.generateTripPlan({ ..._defaults, ai: true }));
  }
});

_test('semantic AI recommendations survive local search and sorting without literal mood filtering', async () => {
  const { _api } = _context();
  await _api._loadCatalog();
  const _items = [{ ..._api._catalog.items[0], recommendationReason: '의외로 따뜻한 관계' }];
  const _result = _api.generateFallbackPlan({ ..._defaults, mood: '힐링', query: '전지적', sort: 'title' }, _items);
  _assert.equal(_result.data.items.length, 1);
  _assert.equal(_result.data.items[0].recommendationReason, '의외로 따뜻한 관계');
});

_test('AI request timeout covers the full response and does not return mock results', async () => {
  const { _api, _sandbox } = _context(async (_url, _options) => {
    if (_url === '/api/generate?resource=catalog') return { ok: true, json: async () => structuredClone(_fixture) };
    return new Promise((_resolve, _reject) => _options.signal.addEventListener('abort', () => _reject(Object.assign(new Error('aborted'), { name: 'AbortError' }))));
  });
  _vm.runInContext('API_CONFIG.AI_TIMEOUT_MS = 5', _sandbox);
  await _assert.rejects(_api.generateTripPlan({ ..._defaults, ai: true }), /초과/);
});

_test('AI timeout during JSON body reading retains the timeout message', async () => {
  const { _api, _sandbox } = _context(async (_url, _options) => {
    if (_url === '/api/generate?resource=catalog') return { ok: true, json: async () => structuredClone(_fixture) };
    return { ok: true, json: () => new Promise((_resolve, _reject) => {
      _options.signal.addEventListener('abort', () => _reject(Object.assign(new Error('aborted'), { name: 'AbortError' })));
    }) };
  });
  _vm.runInContext('API_CONFIG.AI_TIMEOUT_MS = 5', _sandbox);
  await _assert.rejects(_api.generateTripPlan({ ..._defaults, ai: true }), /초과/);
});

_test('live catalogue falls back to the synchronized snapshot on static hosting', async () => {
  const _urls = [];
  const { _api } = _context(async _url => {
    _urls.push(_url);
    return _url.includes('resource=catalog') ? { ok: false, status: 404 } : { ok: true, json: async () => structuredClone(_fixture) };
  });
  _assert.equal((await _api.generateTripPlan(_defaults)).data.items.length, 14);
  _assert.deepEqual(_urls, ['/api/generate?resource=catalog', 'data/webtoons.json']);
});

_test('AI can accept a verified new official title absent from the browser snapshot', async () => {
  const _new = { ..._fixture.items[0], id: '999999', title: '새로 발견한 작품', url: 'https://comic.naver.com/webtoon/list?titleId=999999', cover: 'https://image-comic.pstatic.net/webtoon/999999/thumbnail/test.jpg', discovery: 'web', recommendationReason: '실시간 검색에서 확인한 작품이에요.' };
  const { _api } = _context(async _url => ({ ok: true, json: async () => _url.includes('resource=catalog') ? structuredClone(_fixture) : _aiResponse([_new]) }));
  const _result = await _api.generateTripPlan({ ..._defaults, ai: true });
  _assert.equal(_result.data.items[0].id, '999999');
  _assert.equal(_result.data.items[0].discovery, 'web');
  _assert.ok(_api._catalog.items.some(_item => _item.id === '999999'));
});

_test('untrusted remote covers are rejected even when the title ID is numeric', () => {
  const { _api } = _context();
  _assert.equal(_api._isValidItem({ ..._fixture.items[0], cover: 'https://evil.example/cover.jpg' }), false);
  _assert.equal(_api._isValidItem({ ..._fixture.items[0], cover: 'https://image-comic.pstatic.net@evil.example/cover.jpg' }), false);
});

_test('domestic platform selection filters real collected titles', async () => {
  const _kakao = _allItems.find(_item => _item.platformKey === 'kakaopage');
  _assert.ok(_kakao);
  const { _api } = _context(async () => ({ ok: true, json: async () => ({ ...structuredClone(_fixture), items: [...structuredClone(_fixture.items), structuredClone(_kakao)] }) }));
  await _api._loadCatalog();
  const _result = await _api.generateTripPlan({ ..._defaults, platforms: ['kakaopage'] });
  _assert.equal(_result.data.items.length, 1);
  _assert.equal(_result.data.items[0].platform, '카카오페이지');
});

_test('cross-platform URLs must match the registered service and ID namespace', async () => {
  const { _api } = _context();
  await _api._loadCatalog();
  const _kakao = _allItems.find(_item => _item.platformKey === 'kakaopage');
  _assert.ok(_api._isValidItem(_kakao));
  _assert.equal(_api._isValidItem({ ..._kakao, url: 'https://evil.example/content/123' }), false);
  _assert.equal(_api._isValidItem({ ..._kakao, platformKey: 'ridi' }), false);
  _assert.equal(_api._isValidItem({ ..._kakao, id: '123' }), false);
});

_test('collections persist namespaced platform IDs without changing legacy IDs', () => {
  const { _manager } = _context();
  const _kakao = _allItems.find(_item => _item.platformKey === 'kakaopage');
  _manager.savePlan(_fixture.items[0]);
  _manager.savePlan(_kakao);
  _assert.equal(_manager.getSavedPlans().length, 2);
  _assert.ok(_manager.getSavedPlans().some(_entry => _entry.id === _kakao.id));
});
