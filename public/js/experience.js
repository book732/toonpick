/** Balanced single-card discovery with native touch scrolling and bounded DOM. */
(() => {
  const _host = document.querySelector(".hero-art");
  const _deck = _host.querySelector(".hero-deck");
  const _play = document.getElementById("heroPlay");
  const _next = document.getElementById("heroNext");
  const _previous = document.getElementById("heroPrevious");
  const _tagline = document.getElementById("heroTagline");
  const _motion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const _type = window.TOONPICK_PAGE?.type || "webtoon";
  const _copy = {
    webtoon: {
      category: "WEBTOON CLUB",
      lines: [
        "오늘의 취향은 어느 컷에 숨어 있을까요?",
        "스크롤 끝에서 새로운 최애를 만나요.",
        "가벼운 터치 하나, 새로운 세계 하나.",
        "오늘 마음에 닿을 이야기를 펼쳐보세요.",
        "익숙한 장르 밖에도 재미는 있으니까.",
        "설렘도 반전도, 취향대로 한 컷.",
        "작은 말풍선에서 시작되는 큰 몰입.",
        "처음 보는 제목이 최애가 되는 순간.",
        "이야기 한 조각으로 오늘을 다르게.",
        "다음에 읽을 즐거움이 여기 있어요.",
      ],
    },
    anime: {
      category: "ANIME NIGHT",
      lines: [
        "오늘 밤의 오프닝을 골라볼까요?",
        "엔딩 뒤에도 남을 이야기를 만나세요.",
        "새로운 세계로 향하는 재생 버튼.",
        "한 장면이 오래도록 마음에 남을 때.",
        "어떤 세계의 주인공을 만나고 싶나요?",
        "익숙한 일상에 낯선 모험 한 편.",
        "다음 최애와의 우연한 만남.",
        "웃고 울고 빠져들, 오늘의 한 편.",
        "장르를 넘어 마음이 움직이는 순간.",
        "취향이라는 자막으로 읽는 새로운 세계.",
      ],
    },
    boardgame: {
      category: "GAME TABLE",
      lines: [
        "오늘 테이블 위에는 어떤 재미를 올릴까요?",
        "한 수의 고민이 한 판의 추억으로.",
        "함께 웃을 준비, 주사위는 준비됐어요.",
        "승부도 협력도, 오늘의 기분대로.",
        "손에 든 카드보다 중요한 건 함께하는 시간.",
        "처음 만나는 게임, 금세 가까워지는 사이.",
        "조용한 두뇌전부터 시끌벅적한 파티까지.",
        "화면을 잠시 내려놓고 한 판 어때요?",
        "다음 모임의 주인공이 될 게임을 찾아요.",
        "작은 상자 하나에 담긴 커다란 즐거움.",
      ],
    },
  }[_type];
  const _known = new Map();
  let _source;
  let _sourceLength = 0;
  let _groups = [];
  let _groupOrder = [];
  let _families = new Map();
  let _shown = [];
  let _lines = [];
  let _lastLine = "";
  let _timer;
  let _busy = false;
  let _paused = false;
  let _hovered = false;
  let _focused = false;
  let _inView = true;
  let _slide = 0;
  let _pageIndex = 0;
  let _settleTimer;
  let _pointerStart = null;
  let _suppressClickUntil = 0;
  let _lastDrawn = [];
  let _step = 1;
  let _paintFrame = 0;
  let _currentId = "";

  function _shuffle(_items) {
    const _result = [..._items];
    for (let _index = _result.length - 1; _index > 0; _index--) {
      const _other = Math.floor(Math.random() * (_index + 1));
      [_result[_index], _result[_other]] = [_result[_other], _result[_index]];
    }
    return _result;
  }

  function _setLine() {
    if (!_lines.length) {
      _lines = _shuffle(_copy.lines);
      if (_lines.at(-1) === _lastLine)
        [_lines[0], _lines[_lines.length - 1]] = [_lines.at(-1), _lines[0]];
    }
    _lastLine = _lines.pop();
    _tagline.textContent = _lastLine;
  }

  function _schedule() {
    clearTimeout(_timer);
    const _running =
      !_paused &&
      !_motion.matches &&
      !_hovered &&
      !_focused &&
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
      _image.draggable = false;
      _image.src = _item.cover.startsWith("assets/") ? "/" + _item.cover : _item.cover;
      _image.alt = _item.title + " 표지";
      const _label = document.createElement("span");
      _label.textContent = _item.title;
      _button.append(_image, _label);
      _page.append(_button);
    }
    if (_before) _deck.prepend(_page);
    else _deck.append(_page);
  }

  function _paint() {
    _paintFrame = 0;
    const _position = _deck.scrollLeft / _step;
    [..._deck.children].forEach((_entry, _index) => {
      const _offset = Math.max(-2, Math.min(2, _index - _position));
      const _pose = _offset.toFixed(3);
      if (_entry.dataset.offset === _pose) return;
      _entry.dataset.offset = _pose;
      const _distance = Math.abs(_offset);
      const _focus = Math.max(0, 1 - _distance);
      _entry.style.zIndex = String(30 - Math.round(_distance * 10));
      _entry.style.setProperty("--_card-scale", (1 - Math.min(1, _distance) * .2).toFixed(3));
      _entry.style.setProperty("--_card-angle", (_offset * 13 - _focus * 2).toFixed(2) + "deg");
      _entry.style.setProperty("--_card-opacity", Math.max(0, Math.min(1, 2 - _distance)).toFixed(3));
      _entry.style.setProperty("--_card-brightness", (.88 + _focus * .12).toFixed(3));
      _entry.style.setProperty("--_caption-opacity", Math.max(0, 1 - _distance * 2).toFixed(3));
      _entry.classList.toggle("is-current", _distance < .5);
    });
  }

  function _layout() {
    _step = _deck.clientWidth * .22 || 1;
    _deck.style.setProperty("--_hero-step", _step + "px");
    _deck.style.setProperty("--_hero-inset", (_deck.clientWidth - _step) / 2 + "px");
    _deck.style.setProperty("--_hero-card-width", _deck.clientWidth * .46 + "px");
    _deck.scrollTo({ left: _pageIndex * _step, behavior: "instant" });
    _paint();
  }

  function _settle() {
    if (!_deck.children.length || _pointerStart !== null) return;
    const _index = Math.max(0, Math.min(_deck.children.length - 1, Math.round(_deck.scrollLeft / _step)));
    const _item = _known.get(_deck.children[_index].firstElementChild.dataset.detail);
    if (_item.id !== _currentId) {
      if (_slide) _setLine();
      _currentId = _item.id;
      _deck.dataset.slide = String(++_slide);
      document.getElementById("heroSlideNumber").textContent = String(_slide).padStart(2, "0");
    }
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
    if (Math.abs(_deck.scrollLeft - _target) > 1) _deck.scrollTo({ left: _target, behavior: "instant" });
    [..._deck.children].forEach((_entry, _position) => {
      const _visible = Math.abs(_position - _pageIndex) <= 1;
      _entry.inert = !_visible;
      _entry.setAttribute("aria-hidden", String(!_visible));
      _entry.setAttribute("aria-current", String(_position === _pageIndex));
    });
    _shown = [..._deck.children].slice(Math.max(0, _pageIndex - 1), _pageIndex + 2).map((_entry) => _known.get(_entry.firstElementChild.dataset.detail));
    _deck.dataset.size = String(_shown.length);
    _host.dataset.ready = "true";
    _previous.disabled = _pageIndex === 0;
    _next.disabled = _known.size <= 1 || (_known.size <= 3 && _pageIndex === _deck.children.length - 1);
    _paint();
    _busy = false;
    _schedule();
  }

  function _advance(_animate, _manual = false, _direction = 1) {
    if (_busy || !_known.size) return;
    if (!_manual && (_paused || _hovered || _focused || document.hidden || !_inView || document.querySelector("dialog[open]"))) return;
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
      for (const _item of _items) {
        if (!_item.cover || _item.cover.includes("cover-placeholder.svg"))
          continue;
        if (!_known.has(_item.id)) {
          _known.set(_item.id, _item);
          _added = true;
        }
      }
      if (!_added) return;
      _rebuild();
      if (!_shown.length) _advance(false, true);
      else _schedule();
    },
    _getItem(_id) {
      return _known.get(_id);
    },
  };

  document.getElementById("heroCategory").textContent = _copy.category;
  _host.setAttribute("aria-roledescription", "캐러셀");
  _host.setAttribute("role", "region");
  _next.setAttribute(
    "aria-label",
    _type === "boardgame" ? "다음 게임 한 장 보기" : "다음 작품 한 장 보기",
  );
  _setLine();
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
  _deck.addEventListener("pointerdown", () => {
    _pointerStart = _deck.scrollLeft;
    clearTimeout(_timer);
  }, { passive: true });
  function _release() {
    if (_pointerStart === null) return;
    if (Math.abs(_deck.scrollLeft - _pointerStart) > 12) _suppressClickUntil = performance.now() + 350;
    _pointerStart = null;
    clearTimeout(_settleTimer);
    _settleTimer = setTimeout(_settle, 160);
  }
  window.addEventListener("pointerup", _release, { passive: true });
  window.addEventListener("pointercancel", _release, { passive: true });
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
