/* Submit the form as soon as one of its <select>s changes (sort order, file picker).
   Without JS the form keeps a <noscript> "Apply" button.

   Usage: <form data-module="evn-autosubmit">...</form> */
ckan.module('evn-autosubmit', function () {
  'use strict';
  return {
    initialize: function () {
      var form = this.el[0];
      form.addEventListener('change', function (event) {
        if (event.target.tagName === 'SELECT') {
          window.evn.startLoading();
          form.submit();
        }
      });
    }
  };
});
