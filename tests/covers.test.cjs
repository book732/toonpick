const _test = require('node:test');
const _assert = require('node:assert/strict');
const { _probe } = require('../scripts/prune_webtoon_covers.cjs');

_test('cover validation preserves real images, including binary MIME and split headers', async _t => {
  const _jpeg = Uint8Array.from([0xff, 0xd8, 0xff, 0xe0]);
  for (const _mime of ['image/jpeg', 'application/octet-stream']) {
    _t.mock.method(globalThis, 'fetch', async () => new Response(_jpeg, { headers: { 'Content-Type': _mime } }));
    _assert.equal(await _probe('https://example.com/cover.jpg', '.'), 'ok');
    _t.mock.restoreAll();
  }
  let _offset = 0;
  _t.mock.method(globalThis, 'fetch', async () => new Response(new ReadableStream({
    pull(_controller) {
      if (_offset < _jpeg.length) _controller.enqueue(_jpeg.slice(_offset, ++_offset));
      else _controller.close();
    },
  }), { headers: { 'Content-Type': 'image/jpeg' } }));
  _assert.equal(await _probe('https://example.com/cover.jpg', '.'), 'ok');
});

_test('cover validation rejects unavailable images and HTML while retaining temporary failures', async _t => {
  for (const [_status, _expected] of [[401, 'invalid'], [403, 'invalid'], [404, 'invalid'], [410, 'invalid'], [429, 'unconfirmed'], [500, 'unconfirmed'], [503, 'unconfirmed']]) {
    _t.mock.method(globalThis, 'fetch', async () => new Response('', { status: _status }));
    _assert.equal(await _probe('https://example.com/cover.jpg', '.'), _expected);
    _t.mock.restoreAll();
  }
  _t.mock.method(globalThis, 'fetch', async () => new Response('<html>Not a cover</html>', { headers: { 'Content-Type': 'text/html' } }));
  _assert.equal(await _probe('https://example.com/cover.jpg', '.'), 'invalid');
  _t.mock.restoreAll();
  _t.mock.method(globalThis, 'fetch', async () => { throw new Error('Temporary network failure'); });
  _assert.equal(await _probe('https://example.com/cover.jpg', '.'), 'unconfirmed');
});
