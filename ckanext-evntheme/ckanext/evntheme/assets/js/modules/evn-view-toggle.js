/* List / grid switch for dataset results; the choice is remembered in localStorage.
   The control is `hidden` in the HTML and only shown when this module runs.

   Usage: <div data-module="evn-view-toggle" data-module-target="#list-id" hidden>
            <button data-view="list">...</button><button data-view="grid">...</button></div> */
ckan.module('evn-view-toggle', function () {
  'use strict';
  var STORAGE_KEY = 'evn.datasetView';

  function read() {
    try { return window.localStorage.getItem(STORAGE_KEY); } catch (err) { return null; }
  }

  function write(view) {
    try { window.localStorage.setItem(STORAGE_KEY, view); } catch (err) { /* private mode */ }
  }

  return {
    options: {
      target: null
    },

    initialize: function () {
      var group = this.el[0];
      var list = this.options.target && document.querySelector(this.options.target);
      if (!list) { return; }
      var buttons = Array.prototype.slice.call(group.querySelectorAll('[data-view]'));

      function apply(view) {
        list.classList.toggle('evn-dataset-list--grid', view === 'grid');
        buttons.forEach(function (button) {
          button.setAttribute('aria-pressed', String(button.getAttribute('data-view') === view));
        });
      }

      apply(read() === 'grid' ? 'grid' : 'list');
      group.hidden = false;
      group.addEventListener('click', function (event) {
        var button = event.target.closest('[data-view]');
        if (!button) { return; }
        var view = button.getAttribute('data-view');
        apply(view);
        write(view);
      });
    }
  };
});
