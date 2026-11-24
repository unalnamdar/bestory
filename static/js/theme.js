/* Theme toggle: system -> light -> dark. Initial theme is set by the inline head script. */
(function () {
  'use strict';
  var KEY = 'bestory-theme';
  var ORDER = ['system', 'light', 'dark'];
  var LABELS = { system: 'otomatik', light: 'açık', dark: 'koyu' };
  var root = document.documentElement;
  var btn = document.getElementById('theme-toggle');
  var mq = window.matchMedia('(prefers-color-scheme: dark)');

  function getPref() {
    try { return localStorage.getItem(KEY) || 'system'; } catch (e) { return 'system'; }
  }

  function apply(pref) {
    var dark = pref === 'dark' || (pref === 'system' && mq.matches);
    root.setAttribute('data-theme', dark ? 'dark' : 'light');
    root.setAttribute('data-theme-pref', pref);
    if (btn) {
      var next = ORDER[(ORDER.indexOf(pref) + 1) % ORDER.length];
      btn.setAttribute('aria-label', 'Tema: ' + LABELS[pref] + '. ' + LABELS[next] + ' temaya geçmek için tıkla');
    }
  }

  if (btn) {
    btn.addEventListener('click', function () {
      var next = ORDER[(ORDER.indexOf(getPref()) + 1) % ORDER.length];
      try { localStorage.setItem(KEY, next); } catch (e) { /* storage unavailable */ }
      apply(next);
    });
  }

  // Live update when the OS theme changes and the preference is "system".
  var onChange = function () { if (getPref() === 'system') apply('system'); };
  if (mq.addEventListener) mq.addEventListener('change', onChange);
  else if (mq.addListener) mq.addListener(onChange);

  apply(getPref());
})();
