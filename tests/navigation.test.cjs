const _test = require('node:test');
const _assert = require('node:assert/strict');
const _fs = require('node:fs');
const _vm = require('node:vm');
const _path = require('node:path');

_test('menu navigation applies its filters once and scrolls only after results are ready', async () => {
  for (const _file of ['js/app.js', 'public/js/app.js']) {
    const _source = _fs.readFileSync(_path.join(__dirname, '..', _file), 'utf8');
    const _code = _source.slice(_source.indexOf('  async function _navigateView('), _source.indexOf('  function _openDialog('));
    for (const [_view, _board, _expected] of [['popular', false, { sort: 'favorites' }], ['finished', false, { status: '완결' }], ['quick', true, { maxMinutes: 30 }]]) {
      const _state = {};
      const _scrolls = [];
      let _resolve, _requests = 0;
      const _context = _vm.createContext({
        URL, _state, _isBoardGame: _board,
        _reset(_reload) { _assert.equal(_reload, false); },
        _setBrowseView(_value) { _assert.equal(_value, _view); },
        _refresh() { _requests++; return new Promise(_done => { _resolve = _done; }); },
        window: { location: { href: 'https://example.com/anime' }, history: { pushState() {} } },
        document: { getElementById: _id => ({ scrollIntoView: () => _scrolls.push(_id) }) },
      });
      _vm.runInContext(_code, _context);
      const _pending = _context._navigateView(_view);
      _assert.equal(_requests, 1);
      _assert.deepEqual(_state, _expected);
      _assert.equal(_scrolls.length, 0);
      _resolve(true);
      await _pending;
      _assert.deepEqual(_scrolls, ['featured']);
    }
  }
});
