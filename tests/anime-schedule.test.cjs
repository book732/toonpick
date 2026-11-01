const _test = require('node:test');
const _assert = require('node:assert/strict');
const _fs = require('node:fs');
const _path = require('node:path');
const _vm = require('node:vm');

function _helpers() {
  const _context = _vm.createContext({ window: {}, document: { addEventListener() {} }, Intl, Date });
  const _source = _fs.readFileSync(_path.join(__dirname, '../js/anime-schedule.js'), 'utf8');
  _vm.runInContext(_source.replace("  document.addEventListener('DOMContentLoaded'", "  window._test = { _schedulePeriod, _scheduleDate };\n  document.addEventListener('DOMContentLoaded'"), _context);
  return _context.window._test;
}

_test('seasonal UI uses Korea midnight and all four quarter boundaries', () => {
  const { _schedulePeriod } = _helpers();
  for (const [_date, _year, _quarter] of [
    ['2026-12-31T14:59:59Z', 2026, 4], ['2026-12-31T15:00:00Z', 2027, 1],
    ['2027-03-31T15:00:00Z', 2027, 2], ['2027-06-30T15:00:00Z', 2027, 3], ['2027-09-30T15:00:00Z', 2027, 4],
  ]) {
    const _period = _schedulePeriod(new Date(_date));
    _assert.equal(_period.year, _year);
    _assert.equal(_period.quarter, _quarter);
  }
});

_test('unknown dates never become fabricated January 1 releases', () => {
  const { _scheduleDate } = _helpers();
  _assert.equal(_scheduleDate({}), '방영일 발표 전');
  _assert.equal(_scheduleDate({ year: 2027 }), '2027년 · 상세 일정 미정');
  _assert.equal(_scheduleDate({ year: 2027, month: 1, day: null }), '2027년 1월 · 일자 미정');
  _assert.equal(_scheduleDate({ year: 2027, month: 1, day: 10 }), '2027년 1월 10일');
});
