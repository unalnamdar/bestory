/* Rendering. Everything user- or LLM-supplied goes through textContent, never innerHTML. */
(function (global) {
  'use strict';

  var BADGE_LABELS = { best_seller: 'Çok satan', top_rated: 'En yüksek puan', value: 'Fiyat/performans' };

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }

  function isHttps(url) { return typeof url === 'string' && /^https:\/\//i.test(url); }

  function formatPrice(value, currency) {
    try {
      return new Intl.NumberFormat('tr-TR', { style: 'currency', currency: currency, maximumFractionDigits: 0 }).format(value);
    } catch (e) {
      return String(Math.round(value)) + ' ' + currency;
    }
  }

  function priceText(p, currency) {
    var lo = p.price_min, hi = p.price_max;
    if (lo == null && hi == null) return null;
    if (lo == null) return formatPrice(hi, currency);
    if (hi == null || hi === lo) return formatPrice(lo, currency);
    return formatPrice(lo, currency) + ' – ' + formatPrice(hi, currency);
  }

  function formatNumber(n, digits) {
    return new Intl.NumberFormat('tr-TR', { minimumFractionDigits: digits || 0, maximumFractionDigits: digits || 0 }).format(n);
  }

  function brandColor(name) {
    var h = 0, s = String(name || '?');
    for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 360;
    return 'hsl(' + h + ', 45%, 30%)';
  }

  function stars(rating) {
    var wrap = el('span', 'stars');
    wrap.setAttribute('role', 'img');
    wrap.setAttribute('aria-label', '5 üzerinden ' + formatNumber(rating, 1));
    wrap.textContent = '★★★★★';
    var fill = el('span', 'stars__fill', '★★★★★');
    fill.setAttribute('aria-hidden', 'true');
    fill.style.width = Math.max(0, Math.min(100, (rating / 5) * 100)) + '%';
    wrap.appendChild(fill);
    return wrap;
  }

  function list(items, className) {
    var ul = el('ul', className);
    items.forEach(function (t) { ul.appendChild(el('li', null, t)); });
    return ul;
  }

  function priceDate(iso) {
    var d = new Date(iso);
    return isNaN(d.getTime()) ? '' : d.toLocaleDateString('tr-TR', { day: 'numeric', month: 'long', year: 'numeric' });
  }

  function renderCard(p, currency, generatedAt) {
    var card = el('article', 'card');

    var top = el('div', 'card__top');
    top.appendChild(el('span', 'rank', String(p.rank)));
    var initial = (p.brand || p.name || '?').trim().charAt(0).toUpperCase();
    var avatar = el('span', 'avatar', initial);
    avatar.style.background = brandColor(p.brand || p.name);
    avatar.setAttribute('aria-hidden', 'true');
    top.appendChild(avatar);
    var titles = el('div', 'card__titles');
    if (p.brand) titles.appendChild(el('div', 'brand', p.brand));
    // The whole card is clickable: the name is a link to the first https source,
    // and CSS stretches it over the card (see .card__link::after).
    var primary = null;
    (p.sources || []).some(function (s) { if (isHttps(s.url)) { primary = s; return true; } return false; });
    var nameEl = el('h3', 'card__name');
    if (primary) {
      var link = el('a', 'card__link', p.name);
      link.href = primary.url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.appendChild(el('span', 'sr-only', ' (satıcı sayfası, yeni sekmede açılır)'));
      nameEl.appendChild(link);
    } else {
      nameEl.textContent = p.name;
    }
    titles.appendChild(nameEl);
    top.appendChild(titles);
    card.appendChild(top);

    if (p.badges && p.badges.length) {
      var badges = el('div', 'badges');
      p.badges.forEach(function (b) { badges.appendChild(el('span', 'badge badge--' + b, BADGE_LABELS[b] || b)); });
      card.appendChild(badges);
    }

    var ratingRow = el('div', 'rating');
    if (p.rating != null) {
      ratingRow.appendChild(stars(p.rating));
      ratingRow.appendChild(el('strong', null, formatNumber(p.rating, 1)));
      if (p.rating_count != null) ratingRow.appendChild(el('span', 'muted', '(' + formatNumber(p.rating_count) + ' yorum)'));
      if (p.rating_source) ratingRow.appendChild(el('span', 'muted', '· ' + p.rating_source));
    } else {
      ratingRow.appendChild(el('span', 'muted', 'Puan bilgisi bulunamadı'));
    }
    card.appendChild(ratingRow);

    var price = priceText(p, currency);
    card.appendChild(price ? el('div', 'price', price) : el('div', 'price price--na', 'Fiyat bilgisi yok'));
    if (price && p.price_source) {
      // Only set by the server when the price was verified against a real source page.
      var when = priceDate(generatedAt);
      card.appendChild(el('div', 'note', 'Fiyat: ' + p.price_source + (when ? ' · ' + when : '')));
    }

    if (p.popularity_note) card.appendChild(el('p', 'note', p.popularity_note));
    if (p.highlights && p.highlights.length) card.appendChild(list(p.highlights.slice(0, 3), 'highlights'));

    if ((p.pros && p.pros.length) || (p.cons && p.cons.length) || p.why_ranked) {
      var details = el('details');
      details.appendChild(el('summary', null, 'Artılar, eksiler ve gerekçe'));
      if (p.pros && p.pros.length) { details.appendChild(el('h3', null, 'Artılar')); details.appendChild(list(p.pros)); }
      if (p.cons && p.cons.length) { details.appendChild(el('h3', null, 'Eksiler')); details.appendChild(list(p.cons)); }
      if (p.why_ranked) { details.appendChild(el('h3', null, 'Neden bu sırada?')); details.appendChild(el('p', null, p.why_ranked)); }
      card.appendChild(details);
    }

    var sources = el('div', 'sources');
    sources.appendChild(el('div', 'sources__title', 'Kaynaklar'));
    var ul = el('ul');
    var any = false;
    (p.sources || []).forEach(function (s) {
      if (!isHttps(s.url)) return; // only https links are rendered as links
      var a = el('a', null, s.title || s.url);
      a.href = s.url;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      var li = el('li');
      li.appendChild(a);
      ul.appendChild(li);
      any = true;
    });
    if (!any) ul.appendChild(el('li', 'muted', 'Kaynak bağlantısı yok'));
    sources.appendChild(ul);
    card.appendChild(sources);

    return card;
  }

  var SORTERS = {
    recommended: function (a, b) { return a.rank - b.rank; },
    price_asc: function (a, b) { return nullsLast(a.price_min, b.price_min, 1); },
    price_desc: function (a, b) { return nullsLast(a.price_min, b.price_min, -1); },
    rating: function (a, b) { return nullsLast(a.rating, b.rating, -1); },
    reviews: function (a, b) { return nullsLast(a.rating_count, b.rating_count, -1); },
  };

  function nullsLast(x, y, dir) {
    if (x == null && y == null) return 0;
    if (x == null) return 1;
    if (y == null) return -1;
    return (x - y) * dir;
  }

  function sortProducts(products, key) {
    return products.slice().sort(SORTERS[key] || SORTERS.recommended);
  }

  global.BestoryRender = {
    el: el,
    clear: clear,
    renderCard: renderCard,
    sortProducts: sortProducts,
    formatPrice: formatPrice,
  };
})(window);
