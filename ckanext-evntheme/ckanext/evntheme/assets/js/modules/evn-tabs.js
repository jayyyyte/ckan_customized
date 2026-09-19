/* Dataset page tabs. The tabs are plain links (?tab=...) and every panel is
   rendered by the server; this module switches panels in place, keeps the URL in
   sync (history.pushState / popstate) and adds arrow-key navigation.
   Fires `evn:tabshown` (detail.tab) so hidden widgets (chart, map) can resize.

   Usage: <div data-module="evn-tabs"> ... <a role="tab" data-tab="x" aria-controls="tab-x"> ... */
ckan.module('evn-tabs', function () {
  'use strict';
  return {
    initialize: function () {
      this.tabs = Array.prototype.slice.call(this.el[0].querySelectorAll('[role="tab"][data-tab]'));
      if (!this.tabs.length) { return; }
      var self = this;

      this.tabs.forEach(function (tab, index) {
        tab.tabIndex = tab.getAttribute('aria-selected') === 'true' ? 0 : -1;
        tab.addEventListener('click', function (event) {
          if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) { return; }
          event.preventDefault();
          self.show(tab.getAttribute('data-tab'), true);
        });
        tab.addEventListener('keydown', function (event) {
          var step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
          if (!step) { return; }
          event.preventDefault();
          var next = self.tabs[(index + step + self.tabs.length) % self.tabs.length];
          next.focus();
          self.show(next.getAttribute('data-tab'), true);
        });
      });

      window.addEventListener('popstate', function () {
        self.show(new URLSearchParams(window.location.search).get('tab') || 'overview', false);
      });
    },

    show: function (code, pushHistory) {
      var target = null;
      this.tabs.forEach(function (tab) {
        var active = tab.getAttribute('data-tab') === code;
        if (active) { target = tab; }
        tab.setAttribute('aria-selected', String(active));
        tab.tabIndex = active ? 0 : -1;
        var panel = document.getElementById(tab.getAttribute('aria-controls'));
        if (panel) { panel.hidden = !active; }
      });
      if (!target) { return; }
      if (pushHistory && target.href !== window.location.href) {
        window.history.pushState({ tab: code }, '', target.href);
      }
      this.el[0].dispatchEvent(new CustomEvent('evn:tabshown', { bubbles: true, detail: { tab: code } }));
    }
  };
});
