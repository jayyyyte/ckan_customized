/* "Chia sẻ": native share sheet when the browser has one, otherwise copy the link.

   Usage: <button hidden data-module="evn-share" data-module-url="..." data-module-title="..."
                  data-module-done="Link copied"><svg/><span>Share</span></button> */
ckan.module('evn-share', function () {
  'use strict';
  return {
    options: {
      url: '',
      title: '',
      done: 'Link copied'
    },

    initialize: function () {
      var button = this.el[0];
      var options = this.options;
      var url = options.url || window.location.href;
      button.hidden = false;
      button.addEventListener('click', function () {
        if (window.navigator.share) {
          window.navigator.share({ title: options.title, url: url }).catch(function () { /* cancelled */ });
          return;
        }
        window.evn.copyText(url).then(function () {
          window.evn.flashLabel(button.querySelector('span'), options.done);
        });
      });
    }
  };
});
