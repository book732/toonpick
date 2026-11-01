const _test = require('node:test');
const _assert = require('node:assert/strict');
const _fs = require('node:fs');
const _path = require('node:path');
const _vm = require('node:vm');

async function _detail(_file) {
  const _source = _fs.readFileSync(_path.join(__dirname, '..', _file), 'utf8');
  const _start = _source.indexOf('  async function _showDetail(');
  const _end = _source.indexOf('  function renderSavedPlansList(', _start);
  const _content = { dataset: {} };
  const _item = { id: 'test', title: 'QA', author: 'author', genre: '판타지',
    status: '휴재', age: '15세 이용가', tags: ['판타지', '판타지', '세계관'],
    cover: '/cover.jpg', description: 'description', url: 'https://comic.naver.com/',
    platform: '네이버웹툰', days: [] };
  const _context = _vm.createContext({
    _isAnime: false, _isBoardGame: false, _aiData: null, _dayNames: {},
    _detailModal: {}, _escape: _value => String(_value), _coverUrl: _value => _value,
    _icon: () => '', _seenButton: () => '', updateSavedBadge() {}, _openDialog() {},
    showToast(_message) { throw new Error(_message); },
    document: { getElementById: () => _content },
    window: { ApiService: { _loadCatalog: async () => ({ items: [_item] }), _isValidItem: () => true } },
  });
  _vm.runInContext(_source.slice(_start, _end), _context);
  await _context._showDetail('test');
  return _content.innerHTML.match(/<div class="detail-chips">(.*?)<\/div>/)[1];
}

_test('detail metadata removes repeated genre chips and preserves distinct information', async () => {
  for (const _file of ['js/app.js', 'public/js/app.js']) {
    const _chips = await _detail(_file);
    _assert.equal((_chips.match(/<span>판타지<\/span>/g) || []).length, 1);
    _assert.ok(_chips.includes('<span>휴재 중</span>'));
    _assert.ok(_chips.includes('<span>15세 이용가</span>'));
    _assert.ok(_chips.includes('<span>세계관</span>'));
  }
});
