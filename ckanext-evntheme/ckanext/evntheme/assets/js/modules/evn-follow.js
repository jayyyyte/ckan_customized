/* Follow / unfollow a dataset without leaving the page.
   CKAN 2.11's follow endpoints are POST-only and answer with an htmx fragment, so a
   plain form cannot be used; this module POSTs and flips the button state.

   Usage: <button data-module="evn-follow" aria-pressed="false"
                  data-module-follow-url="..." data-module-unfollow-url="..."
                  data-module-label-follow="Follow" data-module-label-following="Following"
                  data-module-error="..."><span class="evn-follow__label">Follow</span></button> */
ckan.module('evn-follow', function () {
  'use strict';
  return {
    options: {
      followUrl: '',
      unfollowUrl: '',
      labelFollow: 'Follow',
      labelFollowing: 'Following',
      error: 'Could not update, please try again.'
    },

    initialize: function () {
      var button = this.el[0];
      var options = this.options;
      var label = button.querySelector('.evn-follow__label');

      button.addEventListener('click', function () {
        var following = button.getAttribute('aria-pressed') === 'true';
        button.disabled = true;
        window.fetch(following ? options.unfollowUrl : options.followUrl, {
          method: 'POST',
          credentials: 'same-origin',
          headers: window.evn.csrfHeaders()
        }).then(function (response) {
          if (!response.ok) { throw new Error('HTTP ' + response.status); }
          button.setAttribute('aria-pressed', String(!following));
          label.textContent = following ? options.labelFollow : options.labelFollowing;
        }).catch(function () {
          window.evn.flashLabel(label, options.error, 2600);
        }).then(function () {
          button.disabled = false;
        });
      });
    }
  };
});
