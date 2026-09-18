/* Copy the text of `data-module-target` to the clipboard.
 * navigator.clipboard only exists in secure contexts (https or localhost); the K8s
 * NodePort URL is plain http, so fall back to a hidden textarea + execCommand. */
ckan.module("lakehouse_theme-copy", function ($) {
  function fallbackCopy(text) {
    var area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    var ok = document.execCommand("copy");
    document.body.removeChild(area);
    return ok ? Promise.resolve() : Promise.reject();
  }

  return {
    options: { target: null, done: "Copied" },

    initialize: function () {
      $.proxyAll(this, /_on/);
      this.el.on("click", this._onClick);
    },

    _onClick: function () {
      var el = this.el;
      var original = el.html();
      var done = this.options.done;
      var text = $(this.options.target).text();
      var copy = window.isSecureContext && navigator.clipboard
        ? navigator.clipboard.writeText(text)
        : fallbackCopy(text);
      copy.then(function () {
        el.text(done);
        setTimeout(function () { el.html(original); }, 1500);
      });
    }
  };
});
