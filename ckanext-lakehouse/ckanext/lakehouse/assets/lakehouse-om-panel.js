/* "Technical catalog" tab: fetch its HTML from /dataset/<id>/openmetadata the first
   time the tab is shown (ckanext-evntheme's evn-tabs fires `evn:tabshown`), so a slow
   OpenMetadata never delays the dataset page. When the tab is the one opened by the
   URL, the server has rendered it already (data-module-loaded="true").

   Usage: <div data-module="lakehouse-om-panel" data-module-url="..." data-module-loaded="false"> */
ckan.module('lakehouse-om-panel', function () {
  'use strict';
  return {
    options: { url: '', loaded: false, error: 'Error' },

    initialize: function () {
      if (this.options.loaded === true || this.options.loaded === 'true') { return; }
      var self = this;
      var panel = this.el[0].closest('[role="tabpanel"]');
      if (panel && !panel.hidden) { this.load(); return; }
      this.onShown = function (event) {
        if (event.detail && event.detail.tab === 'openmetadata') { self.load(); }
      };
      document.addEventListener('evn:tabshown', this.onShown);
    },

    load: function () {
      if (this.loading) { return; }
      this.loading = true;
      if (this.onShown) { document.removeEventListener('evn:tabshown', this.onShown); }
      var el = this.el[0];
      var self = this;
      fetch(this.options.url, { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } })
        .then(function (response) {
          if (!response.ok) { throw new Error('HTTP ' + response.status); }
          return response.text();
        })
        .then(function (html) {
          el.innerHTML = html;  // server-rendered, escaped by Jinja
        })
        .catch(function () {
          var box = document.createElement('p');
          box.className = 'lh-om__notice';
          box.setAttribute('role', 'alert');
          box.textContent = self.options.error;
          el.innerHTML = '';
          el.appendChild(box);
        })
        .then(function () { el.setAttribute('aria-busy', 'false'); });
    }
  };
});
