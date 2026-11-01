const _test = require('node:test');
const _assert = require('node:assert/strict');
const _fs = require('node:fs');
const _path = require('node:path');
const _vm = require('node:vm');

function _banner(_type = 'webtoon', _file = 'js/experience.js') {
  const _root = _path.resolve(__dirname, '..');
  const _source = _fs.readFileSync(_path.join(_root, _file), 'utf8');
  const _start = _source.indexOf('  _host.setAttribute("aria-roledescription"');
  _assert.ok(_start > 0);
  const _deck = { replaceChildren() { this.cleared = true; } };
  const _host = { querySelector: () => _deck, dataset: {} };
  const _window = { TOONPICK_PAGE: { type: _type }, matchMedia: () => ({ matches: true }) };
  const _context = _vm.createContext({
    window: _window, clearTimeout,
    document: { querySelector: () => _host, getElementById: () => ({}) },
  });
  // Exercise real admission and selection without browser animation timers.
  _vm.runInContext(_source.slice(0, _start) +
    '  _advance = () => {}; _schedule = () => {};\n' +
    '  window._testBanner = { _known, _draw };\n})();', _context);
  return { _experience: _window._ToonpickExperience, ..._window._testBanner, _deck };
}

_test('webtoon banner excludes adult and unverified entries from every draw', () => {
  for (const _file of ['js/experience.js', 'public/js/experience.js']) {
    const { _experience, _known, _draw, _deck } = _banner('webtoon', _file);
    const _base = { cover: 'https://example.com/cover.jpg', title: '작품', tags: [], age: '전체연령가' };
    const _safe = [
      { ..._base, id: 'all' },
      { ..._base, id: 'twelve', age: '12세 이용가' },
      { ..._base, id: 'fifteen', age: '15세 이용가' },
    ];
    const _blocked = [
      { ..._base, id: 'adult-age', age: '19세 이용가' },
      { ..._base, id: 'unknown-age', age: '이용 연령은 공식 페이지 확인' },
      { ..._base, id: 'missing-age', age: undefined },
      { ..._base, id: 'adult-flag', adult: true },
      { ..._base, id: 'is-adult-flag', isAdult: true },
      { ..._base, id: 'nineteen-flag', nineteen: true },
      { ..._base, id: 'adult-title', title: '작품 [19금]' },
      { ..._base, id: 'adult-tag', tags: ['성인'] },
      { ..._base, id: 'adult-genre', genre: 'ADULT' },
      { ..._base, id: 'placeholder', cover: '/assets/cover-placeholder.svg' },
    ];
    _experience._setCatalog([..._safe, ..._blocked]);
    _assert.deepEqual([..._known.keys()].sort(), _safe.map(_item => _item.id).sort());
    for (let _index = 0; _index < 100; _index++) {
      const _chosen = _draw();
      _assert.equal(_chosen.length, 1);
      _assert.ok(_safe.some(_item => _item.id === _chosen[0].id));
    }
    _experience._setCatalog([{ ..._safe[0], age: '19세 이용가' }]);
    _assert.equal(_known.has('all'), false);
    _assert.equal(_deck.cleared, true);
    const { _experience: _emptyExperience, _known: _emptyKnown, _draw: _emptyDraw } = _banner('webtoon', _file);
    _emptyExperience._setCatalog(_blocked);
    _assert.equal(_emptyKnown.size, 0);
    _assert.equal(_emptyDraw().length, 0);
  }
});

_test('webtoon banner filtering preserves anime and board-game catalogues', () => {
  for (const _type of ['anime', 'boardgame']) {
    const { _experience, _known } = _banner(_type);
    _experience._setCatalog([{ id: 'other', title: 'Other', cover: 'cover.jpg', age: '19세 이용가' }]);
    _assert.equal(_known.has('other'), true);
  }
});
