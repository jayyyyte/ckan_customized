/* "Thử API": send the (editable) GET request with fetch and pretty-print the JSON
   answer into #evn-api-response. Only paths of this portal under /api/ are allowed.

   Usage: <form data-module="evn-api-console" data-module-error="..." data-module-invalid="...">
            <input> <button type="submit" hidden>Send</button></form> */
ckan.module('evn-api-console', function () {
  'use strict';

  function pretty(text) {
    try { return JSON.stringify(JSON.parse(text), null, 2); } catch (err) { return text; }
  }

  return {
    options: {
      output: '#evn-api-response',
      error: 'The request failed.',
      invalid: 'Enter a path of this portal starting with /api/.'
    },

    initialize: function () {
      var form = this.el[0];
      var input = form.querySelector('input');
      var button = form.querySelector('button[type="submit"]');
      var output = document.querySelector(this.options.output);
      var options = this.options;
      if (!input || !button || !output) { return; }
      button.hidden = false;

      form.addEventListener('submit', function (event) {
        event.preventDefault();
        var url = new URL(input.value.trim(), window.location.origin);
        if (url.origin !== window.location.origin || url.pathname.indexOf('/api/') === -1) {
          output.textContent = options.invalid;
          return;
        }
        button.disabled = true;
        output.setAttribute('aria-busy', 'true');
        window.fetch(url.href, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
          .then(function (response) { return response.text(); })
          .then(function (text) { output.textContent = pretty(text); })
          .catch(function () { output.textContent = options.error; })
          .then(function () {
            button.disabled = false;
            output.removeAttribute('aria-busy');
          });
      });
    }
  };
});
