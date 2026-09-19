/* "Copy" button for a code block. Hidden in the HTML, shown when this module runs.

   Usage: <button hidden data-module="evn-copy" data-module-target="#pre-id" data-module-done="Copied">
            <svg/><span>Copy</span></button> */
ckan.module('evn-copy', function () {
  'use strict';
  return {
    options: {
      target: null,
      done: 'Copied'
    },

    initialize: function () {
      var button = this.el[0];
      var target = this.options.target && document.querySelector(this.options.target);
      if (!target) { return; }
      var done = this.options.done;
      button.hidden = false;
      button.addEventListener('click', function () {
        window.evn.copyText(target.innerText).then(function () {
          window.evn.flashLabel(button.querySelector('span'), done);
        });
      });
    }
  };
});
