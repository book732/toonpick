const _test = require('node:test');
const _assert = require('node:assert/strict');
const _fs = require('node:fs');
const _path = require('node:path');
const _vm = require('node:vm');

function _input(_file) {
  const _source = _fs.readFileSync(_path.join(__dirname, '..', _file), 'utf8');
  const _handlers = new Map();
  const _frames = new Map();
  const _classes = new Set();
  const _capture = new Set();
  let _frameId = 0;
  const _deck = {
    scrollLeft: 300, style: {},
    classList: { add: _name => _classes.add(_name), remove: _name => _classes.delete(_name) },
    addEventListener(_name, _callback) { _handlers.set('deck:' + _name, _callback); },
    setPointerCapture: _id => _capture.add(_id),
    hasPointerCapture: _id => _capture.has(_id),
    releasePointerCapture: _id => _capture.delete(_id),
  };
  const _context = _vm.createContext({
    _deck, _pointerStart: null, _pointerX: 0, _pointerId: null, _dragScroll: 0,
    _dragging: false, _dragFrame: 0, _timer: 0, _settleTimer: 0,
    _suppressClickUntil: 0, _touching: false, _gestureStart: null, _step: 60,
    _settle() {}, _schedule() {}, clearTimeout() {}, setTimeout: () => 1,
    requestAnimationFrame(_callback) { _frames.set(++_frameId, _callback); return _frameId; },
    cancelAnimationFrame: _id => _frames.delete(_id),
    performance: { now: () => 1000 },
    window: { addEventListener(_name, _callback) { _handlers.set('window:' + _name, _callback); } },
  });
  const _start = _source.indexOf('  _deck.addEventListener("pointerdown"');
  const _end = _source.indexOf('  let _lastWidth', _start);
  _assert.ok(_start > 0 && _end > _start);
  _vm.runInContext(_source.slice(_start, _end), _context);
  return { _deck, _frames, _capture, _classes, _handlers, _context };
}

_test('mouse drag batches movement, retains pointer capture, and suppresses only drag clicks', () => {
  for (const _file of ['js/experience.js', 'public/js/experience.js']) {
    const { _deck, _frames, _capture, _classes, _handlers } = _input(_file);
    const _down = _handlers.get('deck:pointerdown');
    const _move = _handlers.get('deck:pointermove');
    const _up = _handlers.get('window:pointerup');
    let _prevented = 0;
    let _stopped = 0;
    const _event = { pointerType: 'mouse', button: 0, pointerId: 7, clientX: 200, preventDefault() { _prevented++; }, stopPropagation() { _stopped++; } };
    _down(_event);
    _move({ ..._event, clientX: 198 });
    _assert.equal(_frames.size, 0);
    _up(_event);
    _handlers.get('deck:click')(_event);
    _assert.equal(_prevented, 0);
    _assert.equal(_stopped, 0);
    _down(_event);
    _move({ ..._event, clientX: 140 });
    _move({ ..._event, clientX: 110 });
    _assert.equal(_frames.size, 1);
    _assert.equal(_deck.scrollLeft, 300);
    _assert(_capture.has(7));
    _up({ pointerId: 99 });
    _assert(_capture.has(7));
    _up(_event);
    _assert.equal(_deck.scrollLeft, 390);
    _assert.equal(_frames.size, 0);
    _assert.equal(_capture.size, 0);
    _assert.equal(_classes.size, 0);
    _assert.equal(_deck.style.scrollSnapType, '');
    _handlers.get('deck:click')(_event);
    _assert.equal(_stopped, 1);
  }
});

_test('touch input stays native, secondary buttons do not drag, and cancellation releases the mouse', () => {
  const { _handlers, _frames, _context, _capture } = _input('js/experience.js');
  const _down = _handlers.get('deck:pointerdown');
  const _move = _handlers.get('deck:pointermove');
  _down({ pointerType: 'mouse', button: 2, pointerId: 3, clientX: 200 });
  _assert.equal(_context._pointerStart, null);
  _down({ pointerType: 'touch', pointerId: 4, clientX: 200 });
  _move({ pointerType: 'touch', pointerId: 4, clientX: 100, preventDefault() { throw new Error('Touch scrolling was blocked'); } });
  _assert.equal(_frames.size, 0);
  _handlers.get('window:pointerup')({ pointerId: 4 });
  _down({ pointerType: 'mouse', button: 0, pointerId: 3, clientX: 200 });
  _move({ pointerId: 3, clientX: 100, preventDefault() {} });
  _handlers.get('window:pointercancel')({ pointerId: 3 });
  _assert.equal(_capture.size, 0);
  _assert.equal(_context._pointerStart, null);
});

_test('rapid navigation decodes only the nearby banner window and reuses already warmed images', () => {
  const _source = _fs.readFileSync(_path.join(__dirname, '../js/experience.js'), 'utf8');
  const _images = Array.from({ length: 36 }, () => ({ dataset: {}, calls: 0, decode() { this.calls++; return Promise.resolve(); } }));
  const _deck = { children: _images.map(_image => ({ querySelector: () => _image })) };
  const _context = _vm.createContext({ _deck, _warmIndex: -1 });
  const _start = _source.indexOf('  function _warmImages(');
  const _end = _source.indexOf('  function _paint(', _start);
  _vm.runInContext(_source.slice(_start, _end) + '\n_warmImages(16); _warmImages(16);', _context);
  _assert.equal(_images.reduce((_sum, _image) => _sum + _image.calls, 0), 9);
  _assert.equal(_images[16].fetchPriority, 'high');
  _assert.equal(_images[20].fetchPriority, 'low');
  _vm.runInContext('_warmImages(19);', _context);
  _assert.equal(_images.reduce((_sum, _image) => _sum + _image.calls, 0), 12);
  _assert.equal(_images[23].loading, 'eager');
  _assert.equal(_images[0].calls, 0);
});
