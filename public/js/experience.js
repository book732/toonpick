/** Balanced single-card discovery with native touch scrolling and bounded DOM. */
(() => {
  const _host = document.querySelector(".hero-art");
  const _deck = _host.querySelector(".hero-deck");
  const _play = document.getElementById("heroPlay");
  const _next = document.getElementById("heroNext");
  const _previous = document.getElementById("heroPrevious");
  const _motion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const _type = window.TOONPICK_PAGE?.type || "webtoon";
  const _known = new Map();
  let _source;
  let _sourceLength = 0;
  let _groups = [];
  let _groupOrder = [];
  let _families = new Map();
  let _shown = [];
  let _timer;
  let _busy = false;
  let _paused = false;
  let _hovered = false;
  let _focused = false;
  let _inView = true;
  let _pageIndex = 0;
  let _settleTimer;
  let _pointerStart = null;
  let _suppressClickUntil = 0;
  let _lastDrawn = [];
  let _step = 1;
  let _paintFrame = 0;
  let _touching = false;
  let _gestureStart = null;
  let _layoutFrame = 0;
  let _pointerId = null;
  let _pointerX = 0;
  let _dragging = false;
  let _dragFrame = 0;
  let _dragScroll = 0;
  let _warmIndex = -1;
  let _warmDecoded = false;
  let _painted = [];

  function _shuffle(_items) {
    const _result = [..._items];
    for (let _index = _result.length - 1; _index > 0; _index--) {
      const _other = Math.floor(Math.random() * (_index + 1));
      [_result[_index], _result[_other]] = [_result[_other], _result[_index]];
    }
    return _result;
  }

  function _isBannerEligible(_item) {
    if (_type !== "webtoon") return true;
    // Unknown ratings must never enter the public webtoon banner.
    return /^(?:전체연령가|전체이용가|(?:7|12|15)세\s*이용가)$/.test(String(_item.age || "").trim()) &&
      !_item.adult && !_item.isAdult && !_item.nineteen &&
      !/성인|청소년\s*(?:이용|관람)\s*불가|(?:18|19)\s*(?:세|금|\+)|\b(?:ADULT|NSFW|R[- ]?18|R[- ]?19)\b/i.test(
        [_item.title, _item.genre, ...(_item.tags || [])].join(" "),
      );
  }

  function _schedule() {
    clearTimeout(_timer);
    const _running =
      !_paused &&
      !_motion.matches &&
      !_hovered &&
      !_focused &&
      !_touching &&
      !_dragging &&
      !document.hidden &&
      _inView &&
      !document.querySelector("dialog[open]");
    _host.classList.toggle("is-quiet", !_running);
    _play.hidden = _motion.matches;
    _play.textContent = _paused ? "▶ 재생" : "Ⅱ 멈추기";
    _play.setAttribute("aria-pressed", String(_paused));
    if (_running && !_busy && _known.size > 3)
      _timer = setTimeout(() => {
        void _advance(true);
      }, 7000);
  }

  function _rebuild() {
    const _byPlatform = new Map();
    _families = new Map();
    function _root(_id) {
      if (!_families.has(_id)) _families.set(_id, _id);
      let _parent = _id;
      while (_families.get(_parent) !== _parent)
        _parent = _families.get(_parent);
      _families.set(_id, _parent);
      return _parent;
    }
    for (const _item of _known.values()) {
      if (_type === "anime")
        for (const _relation of _item.relations || []) {
          if (
            ["PREQUEL", "SEQUEL", "PARENT", "ALTERNATIVE"].includes(
              _relation.type,
            )
          )
            _families.set(_root(_relation.id), _root(_item.animeId));
        }
    }
    if (_type === "anime")
      for (const _item of _known.values())
        _families.set(_item.animeId, _root(_item.animeId));
    for (const _item of _known.values()) {
      const _key =
        _type === "webtoon"
          ? _item.platformKey || "naver"
          : _type === "anime"
            ? _item.franchiseKey || _families.get(_item.animeId)
            : "all";
      if (!_byPlatform.has(_key)) _byPlatform.set(_key, []);
      _byPlatform.get(_key).push(_item);
    }
    _groups = [..._byPlatform.values()].map((_items) => ({
      items: _items,
      deck: _shuffle(_items),
    }));
    _groupOrder = [];
  }

  function _draw() {
    const _chosen = [];
    const _recent = _lastDrawn.slice(-Math.min(2, _known.size - 1));
    const _avoid = new Set(_recent.map((_item) => _item.id));
    const _usedFamilies = new Set(_type === "anime" && _groups.length >= 3
      ? _recent.map((_item) => _item.franchiseKey || _families.get(_item.animeId) || _item.animeId)
      : []);
    const _deferred = [];
    const _deferredIds = new Set();
    for (
      let _attempt = 0;
      _attempt < _known.size * 2 && _chosen.length < 1;
      _attempt++
    ) {
      if (!_groupOrder.length) _groupOrder = _shuffle(_groups);
      const _group = _groupOrder.pop();
      if (!_group.deck.length)
        _group.deck = _shuffle(
          _group.items.filter(
            (_item) => !_avoid.has(_item.id) && !_deferredIds.has(_item.id),
          ),
        );
      if (!_group.deck.length) continue;
      const _item = _group.deck.pop();
      const _family =
        _type === "anime"
          ? _item.franchiseKey || _families.get(_item.animeId) || _item.animeId
          : _item.id;
      if (_avoid.has(_item.id) || _usedFamilies.has(_family)) {
        if (!_deferredIds.has(_item.id)) {
          _deferred.push([_group, _item]);
          _deferredIds.add(_item.id);
        }
        continue;
      }
      _avoid.add(_item.id);
      _usedFamilies.add(_family);
      _chosen.push(_item);
    }
    for (const [_group, _item] of _deferred) _group.deck.unshift(_item);
    return _chosen;
  }

  function _appendPage(_before = false) {
    const _history = _lastDrawn;
    if (_before) _lastDrawn = [..._deck.children].slice(0, 2).map((_entry) => _known.get(_entry.firstElementChild.dataset.detail));
    const _items = _draw();
    _lastDrawn = _before ? _history : [..._history, ..._items].slice(-2);
    if (!_items.length) return;
    const _page = document.createElement("div");
    _page.className = "hero-page";
    _page.inert = true;
    _page.setAttribute("role", "group");
    _page.setAttribute("aria-label", "작품 카드");
    for (const _item of _items) {
      const _button = document.createElement("button");
      _button.className = "hero-cover";
      _button.type = "button";
      _button.title = _item.title;
      _button.dataset.detail = _item.id;
      _button.setAttribute("aria-label", _item.title + " 상세 보기");
      const _image = new Image(240, 320);
      _image.loading = "lazy";
      _image.decoding = "async";
      _image.fetchPriority = "low";
      _image.draggable = false;
      if (_type === "boardgame") {
        _image.addEventListener("load", () => {
          _button.style.setProperty("--_cover-aspect", String(_image.naturalWidth / _image.naturalHeight));
        }, { once: true });
      }
      _image.dataset.src = _item.cover.startsWith("assets/") ? "/" + _item.cover : _item.cover;
      _image.alt = _item.title + " 표지";
      const _label = document.createElement("span");
      _label.textContent = _item.title;
      _button.append(_image, _label);
      _page.append(_button);
    }
    if (_before) _deck.prepend(_page);
    else _deck.append(_page);
    _warmIndex = -1;
  }

  function _warmImages(_index, _decode = true) {
    if (_warmIndex === _index && (!_decode || _warmDecoded)) return;
    _warmIndex = _index;
    _warmDecoded = _decode;
    // Fetch ahead during scrolling; explicitly decode only after scrolling settles.
    for (let _distance = 0; _distance <= 4; _distance++) {
      for (const _position of _distance ? [_index + _distance, _index - _distance] : [_index]) {
        const _image = _deck.children[_position]?.querySelector("img");
        if (!_image) continue;
        _image.fetchPriority = _distance <= 1 ? "high" : "low";
        _image.loading = "eager";
        if (!_image.src && _image.dataset.src) _image.src = _image.dataset.fallback ? "/assets/cover-placeholder.svg" : _image.dataset.src;
        if (!_decode || _distance > 1 || _image.dataset.warmed) continue;
        _image.dataset.warmed = "true";
        void _image.decode().catch(() => { delete _image.dataset.warmed; });
      }
    }
    if (_decode) {
      for (let _position = 0; _position < _deck.children.length; _position++) {
        if (Math.abs(_position - _index) <= 4) continue;
        const _image = _deck.children[_position].querySelector("img");
        _image.removeAttribute("src");
        delete _image.dataset.warmed;
      }
    }
  }

  function _paint() {
    cancelAnimationFrame(_paintFrame);
    _paintFrame = 0;
    const _position = _deck.scrollLeft / _step;
    _warmImages(Math.round(_position), false);
    const _visible = [];
    const _first = Math.max(0, Math.floor(_position) - 1);
    const _last = Math.min(_deck.children.length - 1, Math.ceil(_position) + 1);
    // Limit composited layers and per-frame writes to the cards actually on screen.
    for (let _index = _first; _index <= _last; _index++) {
      const _entry = _deck.children[_index];
      _visible.push(_entry);
      const _offset = _index - _position;
      const _pose = _offset.toFixed(3);
      if (_entry._paintPose === _pose) continue;
      if (_entry._paintPose == null) _entry.classList.add("is-nearby");
      _entry._paintPose = _pose;
      const _distance = Math.abs(_offset);
      const _focus = Math.max(0, 1 - _distance);
      const _cover = _entry.firstElementChild;
      _entry.style.zIndex = String(30 - Math.round(_distance * 10));
      _cover.style.transform = "translate3d(-50%, 0, 0) rotate(" + (_offset * 13 - _focus * 2).toFixed(2) + "deg) scale(" + (1 - Math.min(1, _distance) * .2).toFixed(3) + ")";
      _cover.style.opacity = Math.max(0, Math.min(1, 2 - _distance)).toFixed(3);
      _cover.lastElementChild.style.opacity = Math.max(0, 1 - _distance * 2).toFixed(3);
      if (_entry._paintCurrent !== (_distance < .5)) {
        _entry._paintCurrent = _distance < .5;
        _entry.classList.toggle("is-current", _entry._paintCurrent);
      }
    }
    for (const _entry of _painted) {
      if (_visible.includes(_entry)) continue;
      _entry.classList.remove("is-nearby", "is-current");
      _entry.firstElementChild.style.opacity = "0";
      _entry.firstElementChild.style.transform = "";
      _entry._paintPose = null;
      _entry._paintCurrent = false;
    }
    _painted = _visible;
  }

  function _layout() {
    cancelAnimationFrame(_layoutFrame);
    _busy = _deck.children.length > 0;
    clearTimeout(_timer);
    _deck.style.scrollSnapType = "none";
    _gestureStart = null;
    _step = _deck.clientWidth * .26 || 1;
    _deck.style.setProperty("--_hero-step", _step + "px");
    _deck.style.setProperty("--_hero-inset", (_deck.clientWidth - _step) / 2 + "px");
    _deck.style.setProperty("--_hero-card-width", _deck.clientWidth * .55 + "px");
    _deck.scrollTo({ left: _pageIndex * _step, behavior: "instant" });
    _paint();
    // Restore snapping after layout so viewport changes keep the same selected card.
    _layoutFrame = requestAnimationFrame(() => {
      _layoutFrame = 0;
      _deck.style.scrollSnapType = "";
      _deck.scrollTo({ left: _pageIndex * _step, behavior: "instant" });
      _settle();
    });
  }

  function _settle() {
    if (!_deck.children.length || _pointerStart !== null || _touching || _layoutFrame) return;
    _gestureStart = null;
    const _index = Math.max(0, Math.min(_deck.children.length - 1, Math.round(_deck.scrollLeft / _step)));
    _pageIndex = _index;
    // Extend both directions while keeping the same visible nodes and at most 36 cards.
    if (_known.size > 3) {
      while (_pageIndex < 4) {
        _appendPage(true);
        _pageIndex++;
      }
      while (_deck.children.length - _pageIndex < 8) _appendPage();
      while (_deck.children.length > 36) {
        if (_pageIndex > 18) {
          _deck.firstElementChild.remove();
          _pageIndex--;
        } else _deck.lastElementChild.remove();
      }
    }
    const _target = _pageIndex * _step;
    _warmIndex = -1;
    if (Math.abs(_deck.scrollLeft - _target) > 1) _deck.scrollTo({ left: _target, behavior: "instant" });
    [..._deck.children].forEach((_entry, _position) => {
      const _visible = Math.abs(_position - _pageIndex) <= 1;
      _entry.inert = !_visible;
      _entry.setAttribute("aria-hidden", String(!_visible));
      _entry.setAttribute("aria-current", String(_position === _pageIndex));
    });
    _shown = [..._deck.children].slice(Math.max(0, _pageIndex - 1), _pageIndex + 2).map((_entry) => _known.get(_entry.firstElementChild.dataset.detail));
    _lastDrawn = [..._deck.children].slice(-2).map((_entry) => _known.get(_entry.firstElementChild.dataset.detail));
    _deck.dataset.size = String(_shown.length);
    _host.dataset.ready = "true";
    _previous.disabled = _pageIndex === 0;
    _next.disabled = _known.size <= 1 || (_known.size <= 3 && _pageIndex === _deck.children.length - 1);
    _paint();
    _warmImages(_pageIndex);
    _busy = false;
    _schedule();
  }

  function _advance(_animate, _manual = false, _direction = 1) {
    if (_busy || !_known.size) return;
    if (!_manual && (_paused || _hovered || _focused || _touching || document.hidden || !_inView || document.querySelector("dialog[open]"))) return;
    if (!_shown.length) {
      _deck.replaceChildren();
      for (let _index = 0; _index < (_known.size > 3 ? 18 : _known.size); _index++) _appendPage();
      _pageIndex = _known.size > 3 ? 6 : Math.min(1, _known.size - 1);
      _layout();
      _settle();
      return;
    }
    const _target = Math.max(0, Math.min(_deck.children.length - 1, _pageIndex + _direction));
    _busy = true;
    clearTimeout(_timer);
    _deck.scrollTo({ left: _target * _step, behavior: _animate && !_motion.matches ? "smooth" : "instant" });
    clearTimeout(_settleTimer);
    _settleTimer = setTimeout(_settle, 180);
  }

  window._ToonpickExperience = {
    _setCatalog(_items) {
      if (_source === _items && _sourceLength === _items.length) return;
      _source = _items;
      _sourceLength = _items.length;
      let _added = false;
      let _removed = false;
      for (const _item of _items) {
        if (!_isBannerEligible(_item)) {
          _removed = _known.delete(_item.id) || _removed;
          continue;
        }
        if (!_item.cover || _item.cover.includes("cover-placeholder.svg"))
          continue;
        if (!_known.has(_item.id)) {
          _known.set(_item.id, _item);
          _added = true;
        }
      }
      if (!_added && !_removed) return;
      if (_removed) {
        clearTimeout(_timer);
        clearTimeout(_settleTimer);
        _deck.replaceChildren();
        _shown = [];
        _lastDrawn = [];
        _host.dataset.ready = "false";
        _busy = false;
      }
      _rebuild();
      if (!_shown.length) _advance(false, true);
      else _schedule();
    },
    _getItem(_id) {
      return _known.get(_id);
    },
  };

  _host.setAttribute("aria-roledescription", "캐러셀");
  _host.setAttribute("role", "region");
  _next.setAttribute(
    "aria-label",
    _type === "boardgame" ? "다음 게임 한 장 보기" : "다음 작품 한 장 보기",
  );
  _next.addEventListener("click", () => {
    _advance(true, true);
  });
  _previous.addEventListener("click", () => _advance(true, true, -1));
  _deck.tabIndex = 0;
  _deck.setAttribute("aria-label", "한 장씩 넘기는 작품 배너. 좌우로 밀거나 방향키로 넘기세요.");
  _deck.addEventListener("keydown", (_event) => {
    if (!["ArrowLeft", "ArrowRight"].includes(_event.key)) return;
    _event.preventDefault();
    _advance(true, true, _event.key === "ArrowLeft" ? -1 : 1);
  });
  _deck.addEventListener("scroll", () => {
    if (!_paintFrame) _paintFrame = requestAnimationFrame(_paint);
    _busy = true;
    clearTimeout(_timer);
    clearTimeout(_settleTimer);
    _settleTimer = setTimeout(_settle, 140);
  }, { passive: true });
  _deck.addEventListener("pointerdown", (_event) => {
    if (_event.pointerType === "mouse" && _event.button !== 0) return;
    _pointerStart = _deck.scrollLeft;
    _pointerX = _event.clientX;
    _pointerId = _event.pointerType === "mouse" ? _event.pointerId : null;
    _dragScroll = _pointerStart;
    clearTimeout(_timer);
  }, { passive: true });
  _deck.addEventListener("pointermove", (_event) => {
    if (_pointerId === null || _event.pointerId !== _pointerId || _pointerStart === null) return;
    const _distance = _pointerX - _event.clientX;
    if (!_dragging && Math.abs(_distance) < 6) return;
    if (!_dragging) {
      _dragging = true;
      _deck.setPointerCapture(_pointerId);
      _deck.style.scrollSnapType = "none";
      _deck.classList.add("is-dragging");
    }
    _event.preventDefault();
    _dragScroll = _pointerStart + _distance;
    if (!_dragFrame) _dragFrame = requestAnimationFrame(() => {
      _dragFrame = 0;
      _deck.scrollLeft = _dragScroll;
    });
  }, { passive: false });
  function _release(_event) {
    if (_pointerStart === null) return;
    if (_pointerId !== null && _event.pointerId !== undefined && _event.pointerId !== _pointerId) return;
    if (_dragging) {
      cancelAnimationFrame(_dragFrame);
      _dragFrame = 0;
      _deck.scrollLeft = _dragScroll;
      _deck.style.scrollSnapType = "";
      _deck.classList.remove("is-dragging");
      if (_deck.hasPointerCapture(_pointerId)) _deck.releasePointerCapture(_pointerId);
      _suppressClickUntil = performance.now() + 350;
    } else if (Math.abs(_deck.scrollLeft - _pointerStart) > 12) _suppressClickUntil = performance.now() + 350;
    _dragging = false;
    _pointerId = null;
    _pointerStart = null;
    clearTimeout(_settleTimer);
    _settleTimer = setTimeout(_settle, 160);
  }
  window.addEventListener("pointerup", _release, { passive: true });
  window.addEventListener("pointercancel", _release, { passive: true });
  window.addEventListener("blur", _release);
  _deck.addEventListener("touchstart", () => {
    _touching = true;
    _gestureStart = _deck.scrollLeft / _step;
    _schedule();
  }, { passive: true });
  function _endTouch() {
    _touching = false;
    if (_gestureStart !== null && Math.abs(_deck.scrollLeft - _gestureStart * _step) > 12) _suppressClickUntil = performance.now() + 350;
    clearTimeout(_settleTimer);
    _settleTimer = setTimeout(_settle, 180);
  }
  _deck.addEventListener("touchend", _endTouch, { passive: true });
  _deck.addEventListener("touchcancel", _endTouch, { passive: true });
  _deck.addEventListener("click", (_event) => {
    if (performance.now() >= _suppressClickUntil) return;
    _event.preventDefault();
    _event.stopPropagation();
  }, true);
  let _lastWidth = 0;
  new ResizeObserver(() => {
    if (_deck.clientWidth === _lastWidth) return;
    _lastWidth = _deck.clientWidth;
    _layout();
  }).observe(_deck);
  _play.addEventListener("click", () => {
    _paused = !_paused;
    _schedule();
  });
  _host.addEventListener("mouseenter", () => {
    if (!window.matchMedia("(hover: hover)").matches) return;
    _hovered = true;
    _schedule();
  });
  _host.addEventListener("mouseleave", () => {
    _hovered = false;
    _schedule();
  });
  _host.addEventListener("focusin", () => {
    _focused = true;
    _schedule();
  });
  _host.addEventListener("focusout", (_event) => {
    _focused = _host.contains(_event.relatedTarget);
    _schedule();
  });
  document.addEventListener("visibilitychange", _schedule);
  _motion.addEventListener("change", _schedule);
  // Native dialogs pause the background showcase and resume it after closing.
  new MutationObserver(_schedule).observe(document.body, {
    attributes: true,
    subtree: true,
    attributeFilter: ["open"],
  });
  const _visibility = new IntersectionObserver(
    (_entries) => {
      _inView = _entries[0].isIntersecting;
      _schedule();
    },
    { threshold: 0.15 },
  );
  _visibility.observe(_host);
  if (!_motion.matches) {
    const _reveal = new IntersectionObserver(
      (_entries) => {
        for (const _entry of _entries)
          if (_entry.isIntersecting) {
            _entry.target.dataset.reveal = "visible";
            _reveal.unobserve(_entry.target);
          }
      },
      { threshold: 0.06 },
    );
    document
      .querySelectorAll("main > section:not(.hero-section)")
      .forEach((_section) => {
        _section.dataset.reveal = "pending";
        _reveal.observe(_section);
      });
  }
  _schedule();
})();
