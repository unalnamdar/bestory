/* Thin fetch wrapper for /api/search/. Sends the CSRF token from the cookie. */
(function (global) {
  'use strict';

  function getCookie(name) {
    var parts = document.cookie ? document.cookie.split('; ') : [];
    for (var i = 0; i < parts.length; i++) {
      var idx = parts[i].indexOf('=');
      if (parts[i].slice(0, idx) === name) return decodeURIComponent(parts[i].slice(idx + 1));
    }
    return '';
  }

  function ApiError(status, code, message, fields, detail) {
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.message = message;
    this.fields = fields || {};
    this.detail = detail || {};
  }
  ApiError.prototype = Object.create(Error.prototype);

  function searchApi(payload, signal) {
    return fetch('/api/search/', {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken'),
      },
      body: JSON.stringify(payload),
      signal: signal,
    }).then(function (res) {
      return res.json().catch(function () { return null; }).then(function (body) {
        if (res.ok && body && body.data) return body;
        var err = (body && body.error) || {};
        throw new ApiError(
          res.status,
          err.code || (res.status === 504 ? 'timeout' : 'unknown'),
          err.message || (res.status === 504
            ? 'Analiz beklenenden uzun sürdü. Lütfen tekrar dene.'
            : 'Beklenmeyen bir hata oluştu. Lütfen tekrar dene.'),
          err.fields,
          err
        );
      });
    });
  }

  global.BestoryApi = { searchApi: searchApi, ApiError: ApiError };
})(window);
