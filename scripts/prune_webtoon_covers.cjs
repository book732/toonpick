/** Remove catalogue entries whose covers consistently fail real image requests. */
const _fs = require('node:fs/promises');
const _path = require('node:path');

async function _probe(_url, _root) {
  if (!_url.startsWith('https://')) {
    if (!/^assets\/covers\/\d+\.jpg$/.test(_url)) return 'invalid';
    try { await _fs.access(_path.join(_root, _url)); return 'ok'; }
    catch { return 'invalid'; }
  }
  try {
    const _response = await fetch(_url, {
      headers: { 'User-Agent': 'Mozilla/5.0', Referer: 'https://toonpick-green.vercel.app/', Range: 'bytes=0-511' },
      signal: AbortSignal.timeout(10000), redirect: 'follow',
    });
    let _reader;
    try {
      if ([401, 403, 404, 410].includes(_response.status)) return 'invalid';
      if (!_response.ok) return 'unconfirmed';
      const _mime = (_response.headers.get('content-type') || '').split(';')[0].trim();
      if (!_mime.startsWith('image/') && !['application/octet-stream', 'binary/octet-stream', ''].includes(_mime)) return 'invalid';
      _reader = _response.body.getReader();
      const _chunks = [];
      let _length = 0;
      while (_length < 32) {
        const { value: _bytes, done: _done } = await _reader.read();
        if (_bytes?.length) { _chunks.push(Buffer.from(_bytes)); _length += _bytes.length; }
        if (_done) break;
      }
      if (!_length) return 'invalid';
      const _head = Buffer.concat(_chunks, _length);
      return _head[0] === 0xff && _head[1] === 0xd8 ||
        _head.subarray(0, 4).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47])) ||
        _head.subarray(0, 4).toString() === 'GIF8' ||
        _head.subarray(0, 4).toString() === 'RIFF' && _head.subarray(8, 12).toString() === 'WEBP' ||
        _head.subarray(4, 8).toString() === 'ftyp' ||
        _mime === 'image/svg+xml' && /<svg\b/.test(_head.toString()) ? 'ok' : 'invalid';
    } finally {
      if (_reader) await _reader.cancel().catch(() => {});
      else await _response.body?.cancel().catch(() => {});
    }
  } catch { return 'unconfirmed'; }
}

async function _main() {
  const _root = _path.resolve(__dirname, '..');
  const _file = _path.join(_root, 'data/webtoons.json');
  const _before = await _fs.readFile(_file, 'utf8');
  const _catalog = JSON.parse(_before);
  const _urls = [...new Set(_catalog.items.map(_item => _item.cover))];
  const _results = new Map();
  let _next = 0;
  let _checked = 0;
  async function _worker() {
    while (_next < _urls.length) {
      const _url = _urls[_next++];
      let _status = await _probe(_url, _root);
      if (_status === 'invalid') {
        const _retry = await _probe(_url, _root);
        _status = _retry === 'invalid' ? 'invalid' : _retry;
      }
      _results.set(_url, _status);
      if (++_checked % 500 === 0) console.log('Checked ' + _checked + '/' + _urls.length + ' covers.');
    }
  }
  await Promise.all(Array.from({ length: 16 }, _worker));
  const _removed = _catalog.items.filter(_item => _results.get(_item.cover) === 'invalid');
  _catalog.items = _catalog.items.filter(_item => _results.get(_item.cover) !== 'invalid');
  for (const _platform of _catalog.platforms) {
    _platform.count = _catalog.items.filter(_item => (_item.platformKey || 'naver') === _platform.key).length;
  }
  const _report = {
    checkedAt: new Date().toISOString(), before: JSON.parse(_before).items.length,
    remaining: _catalog.items.length, removed: _removed.map(_item => ({ id: _item.id, cover: _item.cover, platformKey: _item.platformKey })),
    unconfirmedUrls: [..._results].filter(([, _status]) => _status === 'unconfirmed').map(([_url]) => _url),
  };
  await _fs.mkdir(_path.join(_root, '.cache'), { recursive: true });
  await _fs.writeFile(_path.join(_root, '.cache/webtoon-cover-audit.json'), JSON.stringify(_report));
  if (await _fs.readFile(_file, 'utf8') !== _before) throw new Error('Catalogue changed during audit; refusing to overwrite it.');
  const _output = JSON.stringify(_catalog) + '\n';
  await _fs.writeFile(_file, _output);
  await _fs.writeFile(_path.join(_root, 'public/data/webtoons.json'), _output);
  console.log(JSON.stringify({ checkedUrls: _urls.length, removed: _removed.length, remaining: _catalog.items.length, unconfirmedUrls: _report.unconfirmedUrls.length }));
}

if (require.main === module) _main().catch(_error => { console.error(_error.message); process.exitCode = 1; });
module.exports = { _probe };
