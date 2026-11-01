/** Browser-local collections. Existing public method names are retained. */
const STORAGE_KEYS = {
  THEME: 'toonpick_theme',
  SAVED_PLANS: window.TOONPICK_PAGE?.storageKey || (window.TOONPICK_PAGE?.type === 'anime' ? 'toonpick_saved_anime' : 'toonpick_saved_webtoons')
};

const StorageManager = {
  _seenStorageKey: STORAGE_KEYS.SAVED_PLANS + '_seen',

  _getSeenKey(_item) {
    let _title = _item.title.normalize('NFKC').toLowerCase();
    if (window.TOONPICK_PAGE?.type === 'anime') {
      _title = _title.replace(/\([^)]*(?:더빙|자막)[^)]*\)|\[[^\]]*(?:더빙|자막)[^\]]*\]/g, '');
    } else {
      _title = _title.replace(/[\[(](?:개정판|완전판|일반판|컬러판|연재|완결)[\])]/g, '');
    }
    return (_title.replace(/[^\p{L}\p{N}]+/gu, '') || _item.id) + (window.TOONPICK_PAGE?.type === 'anime' ? ':' + _item.format : '');
  },

  _getSeenItems() {
    try {
      const _entries = JSON.parse(localStorage.getItem(this._seenStorageKey) || '[]');
      return Array.isArray(_entries) ? _entries.slice(0, 20000).filter(_entry =>
        _entry && typeof _entry.id === 'string' && /^(?:\d{1,20}|[a-z][a-z0-9]{0,23}:[a-f0-9]{20})$/.test(_entry.id) &&
        typeof _entry.key === 'string' && _entry.key.length > 0 && _entry.key.length <= 500
      ) : [];
    } catch (_) { return []; }
  },

  _getSeenKeys() {
    return new Set(this._getSeenItems().map(_entry => _entry.key));
  },

  _toggleSeen(_item) {
    try {
      const _key = this._getSeenKey(_item);
      const _entries = this._getSeenItems();
      const _seen = _entries.some(_entry => _entry.key === _key);
      const _updated = _entries.filter(_entry => _entry.key !== _key);
      if (!_seen) {
        if (_updated.length >= 20000) return { success: false, error: '본 작품은 최대 20,000개까지 표시할 수 있어요.' };
        _updated.push({ id: _item.id, key: _key });
      }
      localStorage.setItem(this._seenStorageKey, JSON.stringify(_updated));
      return { success: true, seen: !_seen };
    } catch (_) {
      return { success: false, error: '브라우저 저장 공간에 접근할 수 없습니다.' };
    }
  },

  getTheme() {
    try {
      const saved = localStorage.getItem(STORAGE_KEYS.THEME);
      if (saved === 'light' || saved === 'dark') return saved;
    } catch (_) {
      // Reading may be denied in restricted browser contexts.
    }
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  },

  setTheme(theme) {
    try {
      localStorage.setItem(STORAGE_KEYS.THEME, theme);
    } catch (_) {
      // Theme switching remains usable without persistent storage.
    }
  },

  getSavedPlans() {
    try {
      const raw = localStorage.getItem(STORAGE_KEYS.SAVED_PLANS);
      const _entries = raw ? JSON.parse(raw) : [];
      return Array.isArray(_entries) ? _entries.filter(_entry =>
        _entry && typeof _entry.id === 'string' && /^(?:\d+|[a-z][a-z0-9]*:[a-f0-9]{20})$/.test(_entry.id) &&
        typeof _entry.title === 'string' && _entry.data?.id === _entry.id
      ) : [];
    } catch (_) {
      return [];
    }
  },

  savePlan(plan) {
    try {
      const plans = this.getSavedPlans();
      const newEntry = {
        id: plan.id,
        savedAt: new Date().toISOString(),
        title: plan.title,
        data: plan
      };
      const filtered = plans.filter(_entry => _entry.id !== plan.id);
      filtered.unshift(newEntry);
      localStorage.setItem(STORAGE_KEYS.SAVED_PLANS, JSON.stringify(filtered));
      return { success: true, count: filtered.length };
    } catch (_) {
      return { success: false, error: '브라우저 저장 공간에 접근할 수 없습니다.' };
    }
  },

  deletePlan(planId) {
    try {
      const plans = this.getSavedPlans();
      const updated = plans.filter(_entry => _entry.id !== planId);
      localStorage.setItem(STORAGE_KEYS.SAVED_PLANS, JSON.stringify(updated));
      return { success: true, count: updated.length };
    } catch (_) {
      return { success: false, error: '브라우저 저장 공간에 접근할 수 없습니다.' };
    }
  }
};
window.StorageManager = StorageManager;
