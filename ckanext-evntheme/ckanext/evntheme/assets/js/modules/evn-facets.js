/* Facet sidebar: ticking a checkbox navigates to its CKAN add/remove URL at once
   (data-href), and on small screens the "Bộ lọc" panel starts collapsed.

   Usage: <details data-module="evn-facets" open> ... <input type="checkbox" data-href="..."> */
ckan.module('evn-facets', function () {
  'use strict';
  return {
    options: {
      collapseBelow: 768
    },

    initialize: function () {
      var panel = this.el[0];
      var query = '(max-width: ' + (this.options.collapseBelow - 0.02) + 'px)';
      if (window.matchMedia(query).matches) {
        panel.open = false;
      }
      panel.addEventListener('change', function (event) {
        var input = event.target;
        if (input.matches('input[type="checkbox"][data-href]')) {
          window.evn.startLoading();
          window.location.assign(input.getAttribute('data-href'));
        }
      });
    }
  };
});
