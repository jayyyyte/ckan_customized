/* Data preview switcher: Table (server-rendered) / Chart / Map.
   Chart.js and Leaflet are vendored under public/evntheme/vendor and only loaded
   the first time their view is opened, so the dataset page stays light.

   Chart: sum of a numeric column grouped by another column, over the first rows
   returned by datastore_search. Map: every GeoJSON resource of the dataset.

   Usage: see templates/evntheme/dataset/preview.html */
ckan.module('evn-viz', function () {
  'use strict';

  var CHART_ROWS = 500;
  var CHART_BARS = 20;
  var DEFAULT_CENTER = [16.0, 106.5]; // Viet Nam, used when a GeoJSON file has no features
  var DEFAULT_ZOOM = 5;

  function css(name) {
    return window.getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function parseJSON(text, fallback) {
    try { return JSON.parse(text); } catch (err) { return fallback; }
  }

  function toNumber(value) {
    if (typeof value === 'number') { return value; }
    var parsed = parseFloat(String(value).replace(',', '.'));
    return isNaN(parsed) ? null : parsed;
  }

  function fillSelect(select, values, selected) {
    select.innerHTML = '';
    values.forEach(function (value) {
      var option = document.createElement('option');
      option.value = value;
      option.textContent = value;
      option.selected = value === selected;
      select.appendChild(option);
    });
  }

  return {
    options: {
      chartSrc: '',
      leafletSrc: '',
      leafletCss: '',
      tiles: '',
      api: '',
      error: 'Could not load the data for this view.'
    },

    initialize: function () {
      var root = this.el[0];
      var self = this;
      this.buttons = Array.prototype.slice.call(root.querySelectorAll('[data-viz]'));
      if (!this.buttons.length) { return; }
      this.buttons.forEach(function (button) { button.hidden = false; });

      root.addEventListener('click', function (event) {
        var button = event.target.closest('[data-viz]');
        if (button) { self.show(button.getAttribute('data-viz')); }
      });
      document.addEventListener('evn:tabshown', function (event) {
        if (event.detail.tab === 'preview') { self.refresh(); }
      });

      var selected = root.querySelector('[data-viz][aria-selected="true"]');
      if (selected) { this.show(selected.getAttribute('data-viz')); }
    },

    panel: function (kind) {
      return this.el[0].querySelector('[data-viz-panel="' + kind + '"]');
    },

    show: function (kind) {
      var self = this;
      this.current = kind;
      this.buttons.forEach(function (button) {
        var active = button.getAttribute('data-viz') === kind;
        button.setAttribute('aria-selected', String(active));
        var panel = self.panel(button.getAttribute('data-viz'));
        if (panel) { panel.hidden = !active; }
      });
      this.refresh();
    },

    /* Draw (or resize) the current view once it is actually visible. */
    refresh: function () {
      var panel = this.panel(this.current);
      if (!panel || panel.offsetParent === null) { return; }
      if (this.current === 'chart') { this.renderChart(panel); }
      if (this.current === 'map') { this.renderMap(panel); }
    },

    fail: function (panel, err) {
      if (window.console) { window.console.error('evn-viz:', err); }
      var note = document.createElement('p');
      note.className = 'evn-alert evn-alert--error';
      note.setAttribute('role', 'alert');
      note.textContent = this.options.error;
      panel.appendChild(note);
    },

    /* --- Chart --------------------------------------------------------------- */

    renderChart: function (panel) {
      var self = this;
      if (this.chartReady) { this.chartReady.then(function () { if (self.chart) { self.chart.resize(); } }); return; }

      var fields = parseJSON(panel.getAttribute('data-fields'), []);
      var numeric = parseJSON(panel.getAttribute('data-numeric'), []);
      var xSelect = panel.querySelector('[data-chart-x]');
      var ySelect = panel.querySelector('[data-chart-y]');
      var groupable = fields.filter(function (f) { return numeric.indexOf(f) === -1; });
      fillSelect(xSelect, groupable.length ? groupable : fields, (groupable[0] || fields[0]));
      fillSelect(ySelect, numeric, numeric[0]);

      var url = this.options.api + '?resource_id=' + encodeURIComponent(panel.getAttribute('data-resource-id')) +
        '&limit=' + CHART_ROWS;
      this.chartReady = Promise.all([
        window.evn.load(this.options.chartSrc),
        window.fetch(url, { credentials: 'same-origin' }).then(function (r) { return r.json(); })
      ]).then(function (results) {
        var records = results[1].result.records;
        var draw = function () { self.drawChart(panel, records, xSelect.value, ySelect.value); };
        xSelect.addEventListener('change', draw);
        ySelect.addEventListener('change', draw);
        draw();
      }).catch(function (err) { self.fail(panel, err); });
    },

    drawChart: function (panel, records, xField, yField) {
      var totals = {};
      records.forEach(function (record) {
        var value = toNumber(record[yField]);
        if (value === null) { return; }
        var key = record[xField] === null || record[xField] === undefined ? '—' : String(record[xField]);
        totals[key] = (totals[key] || 0) + value;
      });
      var rows = Object.keys(totals).map(function (key) { return [key, totals[key]]; })
        .sort(function (a, b) { return b[1] - a[1]; })
        .slice(0, CHART_BARS);

      var ink = css('--evn-ink-2');
      var font = { family: css('--evn-font-body') || 'sans-serif', size: 12 };
      var config = {
        type: 'bar',
        data: {
          labels: rows.map(function (r) { return r[0]; }),
          datasets: [{ label: yField, data: rows.map(function (r) { return r[1]; }),
                       backgroundColor: css('--evn-blue'), borderRadius: 6, maxBarThickness: 42 }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { ticks: { color: ink, font: font }, grid: { display: false } },
            y: { ticks: { color: ink, font: font }, grid: { color: css('--evn-line') } }
          }
        }
      };
      if (this.chart) { this.chart.destroy(); }
      this.chart = new window.Chart(panel.querySelector('canvas'), config);
    },

    /* --- Map ----------------------------------------------------------------- */

    renderMap: function (panel) {
      var self = this;
      if (this.mapReady) { this.mapReady.then(function () { if (self.map) { self.map.invalidateSize(); } }); return; }

      var urls = parseJSON(panel.getAttribute('data-geojson'), []);
      this.mapReady = Promise.all([
        window.evn.load(this.options.leafletCss, 'css'),
        window.evn.load(this.options.leafletSrc)
      ]).then(function () {
        return Promise.all(urls.map(function (url) {
          return window.fetch(url, { credentials: 'same-origin' }).then(function (r) { return r.json(); });
        }));
      }).then(function (collections) {
        var L = window.L;
        var color = css('--evn-blue');
        var map = self.map = L.map(panel.querySelector('.evn-viz__map'), { scrollWheelZoom: false });
        // CKAN turns an empty data-module-* attribute into `true`: only a string is a tile URL.
        if (typeof self.options.tiles === 'string' && self.options.tiles) {
          L.tileLayer(self.options.tiles, { maxZoom: 18, attribution: '&copy; OpenStreetMap' }).addTo(map);
        }
        var layer = L.featureGroup(collections.map(function (data) {
          return L.geoJSON(data, {
            style: { color: color, weight: 2 },
            pointToLayer: function (feature, latlng) {
              return L.circleMarker(latlng, { radius: 7, color: '#fff', weight: 2, fillColor: color, fillOpacity: 0.9 });
            },
            onEachFeature: function (feature, item) {
              var props = feature.properties || {};
              var name = props.ten || props.name || props.title;
              if (name) { item.bindTooltip(String(name)); }
            }
          });
        }));
        // The map needs a view before vector layers are added (they project on add).
        var bounds = layer.getBounds();
        if (bounds.isValid()) {
          map.fitBounds(bounds, { padding: [24, 24] });
        } else {
          map.setView(DEFAULT_CENTER, DEFAULT_ZOOM);
        }
        layer.addTo(map);
      }).catch(function (err) { self.fail(panel, err); });
    }
  };
});
