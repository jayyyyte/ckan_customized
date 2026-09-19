/* Shared helpers for the evn-* modules (loaded first in the bundle). */
(function (window, document) {
  'use strict';

  var evn = window.evn = window.evn || {};

  /* CSRF header for POSTs from JS: CKAN prints the field name and token in <meta> tags. */
  evn.csrfHeaders = function () {
    var nameMeta = document.querySelector('meta[name="csrf_field_name"]');
    var tokenMeta = nameMeta && document.querySelector('meta[name="' + nameMeta.content + '"]');
    return tokenMeta ? { 'X-CSRFToken': tokenMeta.content } : {};
  };

  /* Copy text. navigator.clipboard only exists on HTTPS/localhost; the portal is also
     served over plain HTTP inside the company network, hence the execCommand fallback. */
  evn.copyText = function (text) {
    if (window.navigator.clipboard && window.isSecureContext) {
      return window.navigator.clipboard.writeText(text);
    }
    return new Promise(function (resolve, reject) {
      var area = document.createElement('textarea');
      area.value = text;
      area.setAttribute('readonly', '');
      area.className = 'evn-offscreen';
      document.body.appendChild(area);
      area.select();
      try {
        if (document.execCommand('copy')) { resolve(); } else { reject(new Error('copy failed')); }
      } catch (err) {
        reject(err);
      } finally {
        document.body.removeChild(area);
      }
    });
  };

  /* Show `text` in `label` for a moment, then restore the original text. */
  evn.flashLabel = function (label, text, ms) {
    if (!label) { return; }
    var original = label.getAttribute('data-original') || label.textContent;
    label.setAttribute('data-original', original);
    label.textContent = text;
    window.setTimeout(function () { label.textContent = original; }, ms || 1800);
  };

  /* Mark the page as loading (skeleton styles) before a full navigation. */
  evn.startLoading = function () {
    document.documentElement.classList.add('evn-is-loading');
  };

  /* Load a script or stylesheet once; resolves when ready. */
  var loaded = {};
  evn.load = function (url, type) {
    if (!loaded[url]) {
      loaded[url] = new Promise(function (resolve, reject) {
        var node;
        if (type === 'css') {
          node = document.createElement('link');
          node.rel = 'stylesheet';
          node.href = url;
        } else {
          node = document.createElement('script');
          node.src = url;
          node.async = true;
        }
        node.onload = resolve;
        node.onerror = reject;
        document.head.appendChild(node);
      });
    }
    return loaded[url];
  };
})(window, document);
