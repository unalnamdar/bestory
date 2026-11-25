/* Search page controller: form -> API -> skeleton -> cards, client-side sorting, URL sync. */
(function () {
  'use strict';

  var R = window.BestoryRender;
  var form = document.getElementById('search-form');
  var results = document.getElementById('results');
  var qInput = document.getElementById('q');
  var customInput = document.getElementById('custom');
  var counter = document.getElementById('custom-count');
  var customHint = document.getElementById('custom-hint');
  var minPrice = document.getElementById('min-price');
  var maxPrice = document.getElementById('max-price');
  var minRating = document.getElementById('min-rating');
  var minRatingValue = document.getElementById('min-rating-value');
  var limitSelect = document.getElementById('limit');
  var countrySelect = document.getElementById('country-select');
  var submitBtn = document.getElementById('submit-btn');
  var filtersBox = document.getElementById('filters');
  var examples = document.getElementById('examples');

  var STAGES = ['Mağazalar taranıyor…', 'Puanlar karşılaştırılıyor…', 'Liste hazırlanıyor…'];
  var COUNTRY_KEY = 'bestory-country';
  var state = { data: null, sort: 'recommended', cached: false, remaining: null, controller: null, timer: null, lastPayload: null };

  /* ---------- form helpers ---------- */

  function mode() { return form.querySelector('input[name="mode"]:checked').value; }

  function setMode(value) {
    var radio = form.querySelector('input[name="mode"][value="' + value + '"]');
    if (radio) radio.checked = true;
    updateCustomHint();
  }

  function updateCustomHint() {
    customHint.textContent = mode() === 'custom' ? '(zorunlu)' : '(opsiyonel)';
  }

  function updateCounter() { counter.textContent = customInput.value.length + ' / 300'; }

  function updateRatingLabel() {
    var v = parseFloat(minRating.value);
    minRatingValue.textContent = v < 3 ? 'Fark etmez' : v.toFixed(1).replace('.', ',') + '+';
  }

  function numberOrNull(input) {
    var v = input.value.trim();
    if (v === '') return null;
    var n = Number(v);
    return isFinite(n) ? n : null;
  }

  function getPayload() {
    var rating = parseFloat(minRating.value);
    return {
      query: qInput.value.trim(),
      country: countrySelect.value,
      mode: mode(),
      filters: {
        min_price: numberOrNull(minPrice),
        max_price: numberOrNull(maxPrice),
        min_rating: rating >= 3 ? Math.round(rating * 10) / 10 : null,
        limit: parseInt(limitSelect.value, 10),
      },
      custom_criteria: customInput.value.trim(),
    };
  }

  /* ---------- errors on fields ---------- */

  var FIELD_ERRORS = {
    'query': ['q-error', qInput],
    'custom_criteria': ['custom-error', customInput],
    'filters.max_price': ['price-error', maxPrice],
    'filters.min_price': ['price-error', minPrice],
  };

  function clearFieldErrors() {
    ['q-error', 'custom-error', 'price-error'].forEach(function (id) {
      var n = document.getElementById(id);
      n.hidden = true;
      n.textContent = '';
    });
    [qInput, customInput, minPrice, maxPrice].forEach(function (i) { i.removeAttribute('aria-invalid'); });
  }

  function showFieldErrors(fields) {
    var first = null, shown = false;
    Object.keys(fields).forEach(function (name) {
      var target = FIELD_ERRORS[name];
      if (!target) return;
      var box = document.getElementById(target[0]);
      box.textContent = fields[name];
      box.hidden = false;
      target[1].setAttribute('aria-invalid', 'true');
      if (!first) first = target[1];
      shown = true;
      if (target[0] === 'price-error') filtersBox.open = true;
    });
    if (first) first.focus();
    return shown;
  }

  function validateClient(payload) {
    var fields = {};
    if (payload.query.length < 2) fields.query = 'Lütfen ne almak istediğini yaz (en az 2 karakter).';
    if (payload.mode === 'custom' && !payload.custom_criteria) fields.custom_criteria = 'Özel modda ek isteklerini yazman gerekiyor.';
    var f = payload.filters;
    if (f.min_price != null && f.max_price != null && f.min_price > f.max_price) {
      fields['filters.max_price'] = 'En düşük bütçe, en yüksek bütçeden büyük olamaz.';
    }
    return fields;
  }

  /* ---------- results area states ---------- */

  function stopLoading() {
    if (state.timer) { clearInterval(state.timer); state.timer = null; }
    results.setAttribute('aria-busy', 'false');
    submitBtn.disabled = false;
  }

  function showLoading() {
    R.clear(results);
    results.setAttribute('aria-busy', 'true');
    submitBtn.disabled = true;

    var box = R.el('div', 'loading-box');
    var stage = R.el('p', 'stage', STAGES[0]);
    box.appendChild(stage);
    box.appendChild(R.el('p', 'hint', 'Analiz 20–60 saniye sürebilir. Lütfen sayfayı kapatma.'));
    results.appendChild(box);

    var grid = R.el('div', 'grid');
    for (var i = 0; i < 6; i++) {
      var c = R.el('div', 'card skeleton');
      c.setAttribute('aria-hidden', 'true');
      c.appendChild(R.el('div', 'bar bar--lg'));
      c.appendChild(R.el('div', 'bar bar--md'));
      c.appendChild(R.el('div', 'bar bar--sm'));
      c.appendChild(R.el('div', 'bar bar--md'));
      grid.appendChild(c);
    }
    results.appendChild(grid);

    var n = 0;
    state.timer = setInterval(function () {
      n = (n + 1) % STAGES.length;
      stage.textContent = STAGES[n];
    }, 6000);
  }

  function showError(err) {
    stopLoading();
    R.clear(results);
    var box = R.el('div', 'alert');
    box.setAttribute('role', 'alert');
    var titles = {
      not_a_product: 'Bu bir ürün gibi görünmüyor',
      rate_limited: 'Günlük arama limitine ulaştın',
      timeout: 'Analiz çok uzun sürdü',
      provider_error: 'Sonuçlar derlenemedi',
      invalid: 'Aramayı kontrol et',
    };
    box.appendChild(R.el('h2', null, titles[err.code] || 'Bir sorun oluştu'));
    box.appendChild(R.el('p', null, err.message || 'Beklenmeyen bir hata oluştu. Lütfen tekrar dene.'));

    var actions = R.el('div', 'alert__actions');
    var retry = R.el('button', 'btn btn-primary', 'Tekrar dene');
    retry.type = 'button';
    retry.addEventListener('click', function () { run(state.lastPayload || getPayload()); });
    actions.appendChild(retry);
    // The server only sends signup_url for anonymous users once the page exists.
    var signupUrl = err.detail && err.detail.signup_url;
    if (err.code === 'rate_limited' && typeof signupUrl === 'string' && signupUrl.charAt(0) === '/') {
      var join = R.el('a', 'btn btn-secondary', 'Ücretsiz üye ol');
      join.href = signupUrl;
      actions.appendChild(join);
    }
    box.appendChild(actions);
    results.appendChild(box);
  }

  function showResults() {
    stopLoading();
    R.clear(results);
    var data = state.data;

    var head = R.el('div', 'results__head');
    var summary = R.el('div', 'results__summary');
    summary.appendChild(R.el('h2', null, '“' + data.query + '” için sonuçlar'));
    if (data.summary) summary.appendChild(R.el('p', null, data.summary));
    var meta = R.el('div', 'results__meta');
    var countryName = countrySelect.options[countrySelect.selectedIndex]
      ? countrySelect.options[countrySelect.selectedIndex].text : data.country;
    meta.appendChild(R.el('span', 'tag', countryName + ' · ' + data.currency));
    if (state.cached) meta.appendChild(R.el('span', 'tag', 'önbellekten'));
    if (typeof state.remaining === 'number') {
      meta.appendChild(R.el('span', 'tag', 'Kalan arama hakkın: ' + state.remaining));
    }
    summary.appendChild(meta);
    head.appendChild(summary);

    var sort = R.el('div', 'sort');
    var label = R.el('label', null, 'Sırala:');
    label.setAttribute('for', 'sort-select');
    var select = R.el('select', 'select');
    select.id = 'sort-select';
    [['recommended', 'Önerilen sıra'], ['price_asc', 'Fiyat ↑'], ['price_desc', 'Fiyat ↓'],
     ['rating', 'Puan'], ['reviews', 'Yorum sayısı']].forEach(function (o) {
      var opt = R.el('option', null, o[1]);
      opt.value = o[0];
      if (o[0] === state.sort) opt.selected = true;
      select.appendChild(opt);
    });
    select.addEventListener('change', function () { state.sort = select.value; renderGrid(); });
    sort.appendChild(label);
    sort.appendChild(select);
    head.appendChild(sort);
    results.appendChild(head);

    var grid = R.el('div', 'grid');
    grid.id = 'product-grid';
    results.appendChild(grid);
    renderGrid();

    if (data.data_note) results.appendChild(R.el('p', 'data-note', data.data_note));
    examples.hidden = true;
  }

  function renderGrid() {
    var grid = document.getElementById('product-grid');
    if (!grid) return;
    R.clear(grid);
    R.sortProducts(state.data.products, state.sort).forEach(function (p) {
      grid.appendChild(R.renderCard(p, state.data.currency, state.data.generated_at));
    });
  }

  /* ---------- URL sync ---------- */

  function syncUrl(payload) {
    var p = new URLSearchParams();
    p.set('q', payload.query);
    p.set('country', payload.country);
    p.set('mode', payload.mode);
    var f = payload.filters;
    if (f.min_price != null) p.set('min_price', f.min_price);
    if (f.max_price != null) p.set('max_price', f.max_price);
    if (f.min_rating != null) p.set('min_rating', f.min_rating);
    if (f.limit !== 10) p.set('limit', f.limit);
    if (payload.custom_criteria) p.set('custom', payload.custom_criteria);
    history.replaceState(null, '', '?' + p.toString());
  }

  function loadFromUrl() {
    var p = new URLSearchParams(location.search);
    var q = (p.get('q') || '').trim();
    if (p.get('country') && countrySelect.querySelector('option[value="' + p.get('country').toUpperCase() + '"]')) {
      countrySelect.value = p.get('country').toUpperCase();
    }
    if (p.get('mode')) setMode(p.get('mode'));
    if (p.get('min_price')) minPrice.value = p.get('min_price');
    if (p.get('max_price')) maxPrice.value = p.get('max_price');
    if (p.get('min_rating')) minRating.value = p.get('min_rating');
    if (p.get('limit') === '5') limitSelect.value = '5';
    if (p.get('custom')) customInput.value = p.get('custom').slice(0, 300);
    if (p.get('min_price') || p.get('max_price') || p.get('min_rating') || p.get('limit')) filtersBox.open = true;
    updateCounter();
    updateRatingLabel();
    updateCustomHint();
    if (q) {
      qInput.value = q;
      submit();
    }
  }

  /* ---------- run ---------- */

  function run(payload) {
    if (state.controller) state.controller.abort();
    state.controller = new AbortController();
    var timeout = setTimeout(function () { state.controller.abort(); }, 150000);
    state.lastPayload = payload;
    syncUrl(payload);
    showLoading();

    window.BestoryApi.searchApi(payload, state.controller.signal).then(function (body) {
      clearTimeout(timeout);
      state.data = body.data;
      state.cached = !!body.cached;
      state.remaining = typeof body.remaining === 'number' ? body.remaining : null;
      state.sort = 'recommended';
      showResults();
    }).catch(function (err) {
      clearTimeout(timeout);
      if (err && err.name === 'AbortError') {
        err = { code: 'timeout', message: 'Analiz beklenenden uzun sürdü. Lütfen tekrar dene.' };
      } else if (!(err instanceof window.BestoryApi.ApiError)) {
        err = { code: 'network', message: 'Sunucuya ulaşılamadı. İnternet bağlantını kontrol edip tekrar dene.' };
      } else if (err.code === 'invalid' && Object.keys(err.fields).length && showFieldErrors(err.fields)) {
        stopLoading();
        R.clear(results);
        return;
      }
      showError(err);
    });
  }

  function submit() {
    clearFieldErrors();
    var payload = getPayload();
    var fields = validateClient(payload);
    if (Object.keys(fields).length) {
      showFieldErrors(fields);
      return;
    }
    run(payload);
  }

  /* ---------- wiring ---------- */

  form.addEventListener('submit', function (e) { e.preventDefault(); submit(); });
  customInput.addEventListener('input', updateCounter);
  minRating.addEventListener('input', updateRatingLabel);
  form.querySelectorAll('input[name="mode"]').forEach(function (r) { r.addEventListener('change', updateCustomHint); });
  examples.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-example]');
    if (!btn) return;
    qInput.value = btn.getAttribute('data-example');
    qInput.focus();
  });
  countrySelect.addEventListener('change', function () {
    try { localStorage.setItem(COUNTRY_KEY, countrySelect.value); } catch (e) { /* ignore */ }
  });

  // Remember the user's last country unless the URL or server already chose one.
  try {
    var saved = localStorage.getItem(COUNTRY_KEY);
    if (saved && !new URLSearchParams(location.search).get('country') &&
        countrySelect.querySelector('option[value="' + saved + '"]')) {
      countrySelect.value = saved;
    }
  } catch (e) { /* ignore */ }

  updateCounter();
  updateRatingLabel();
  updateCustomHint();
  loadFromUrl();
})();
