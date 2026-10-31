/** Browser-local collections. Existing public method names are retained. */
const STORAGE_KEYS = {
  THEME: 'toonpick_theme',
  SAVED_PLANS: window.TOONPICK_PAGE?.storageKey || (window.TOONPICK_PAGE?.type === 'anime' ? 'toonpick_saved_anime' : 'toonpick_saved_webtoons')
};

const StorageManager = {
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
