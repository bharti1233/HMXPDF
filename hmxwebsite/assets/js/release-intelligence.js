/* HMXPDF — release intelligence dashboard.
 *
 * Reads the static dataset committed at data/release-intelligence.json.
 * Values are rendered with textContent only; no remote calls, no cookies,
 * no identifiers, and no third-party script.
 */
(function () {
  'use strict';

  var panel = document.getElementById('intel-panel');
  if (!panel) return;

  function $(id) {
    return document.getElementById(id);
  }

  function setVisible(el, visible) {
    if (el) el.hidden = !visible;
  }

  function setText(id, value) {
    var el = $(id);
    if (el) el.textContent = value;
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function safeHttpsUrl(value) {
    if (typeof value !== 'string') return '';
    try {
      var url = new URL(value);
      return url.protocol === 'https:' ? url.href : '';
    } catch (error) {
      return '';
    }
  }

  function formatNumber(value) {
    if (typeof value !== 'number' || !isFinite(value)) return '—';
    try {
      return new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(value);
    } catch (error) {
      return String(value);
    }
  }

  function parseDate(value) {
    if (!value) return null;
    var date = new Date(value);
    return isNaN(date.getTime()) ? null : date;
  }

  function formatDate(value) {
    var date = parseDate(value);
    if (!date) return '—';
    try {
      return new Intl.DateTimeFormat(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
      }).format(date);
    } catch (error) {
      return date.toDateString();
    }
  }

  function formatTimestamp(value) {
    var date = parseDate(value);
    if (!date) return '—';
    try {
      return (
        new Intl.DateTimeFormat(undefined, {
          year: 'numeric',
          month: 'short',
          day: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
          timeZone: 'UTC',
          timeZoneName: 'short'
        }).format(date)
      );
    } catch (error) {
      return date.toISOString();
    }
  }

  function progressRow(label, valueText, percent) {
    var row = el('div', 'intel-row');
    var head = el('div', 'intel-row__head');
    head.appendChild(el('span', 'intel-row__name', label));
    head.appendChild(el('span', 'intel-row__value', valueText));
    row.appendChild(head);
    var bar = document.createElement('progress');
    bar.className = 'intel-progress';
    bar.max = 100;
    bar.value = Math.max(0, Math.min(100, Number(percent) || 0));
    bar.setAttribute('aria-label', label + ': ' + valueText);
    row.appendChild(bar);
    return row;
  }

  function linkOrText(value, text, className) {
    var url = safeHttpsUrl(value);
    if (!url) return el('span', className, text);
    var link = el('a', className, text);
    link.href = url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    return link;
  }

  function renderReleaseRows(releases, labels) {
    var tbody = $('intel-release-rows');
    if (!tbody) return;
    tbody.textContent = '';
    if (!releases.length) {
      var empty = el('tr');
      var cell = el('td', '', 'No published release has been recorded yet.');
      cell.colSpan = 5;
      empty.appendChild(cell);
      tbody.appendChild(empty);
      return;
    }
    releases.forEach(function (release) {
      var row = el('tr');
      var name = el('td');
      name.appendChild(linkOrText(release.url, release.tag || 'Untitled', ''));
      row.appendChild(name);
      row.appendChild(el('td', '', formatDate(release.published_at)));
      row.appendChild(el('td', 'intel-num', formatNumber(release.apk_downloads)));
      row.appendChild(el('td', 'intel-num', (release.share_percent || 0).toFixed(1) + '%'));
      var top = release.top_asset;
      var topLabel = top
        ? (labels[top.abi] || top.abi) + ' · ' + formatNumber(top.download_count)
        : 'No APK asset';
      row.appendChild(el('td', '', topLabel));
      tbody.appendChild(row);
    });
  }

  function renderAbi(abi, labels) {
    var host = $('intel-abi-list');
    if (!host) return;
    host.textContent = '';
    var keys = Object.keys(abi || {});
    if (!keys.length) {
      host.appendChild(el('p', 'intel-note', 'No APK download counter is available yet.'));
      return;
    }
    keys.forEach(function (key) {
      var item = abi[key] || {};
      host.appendChild(
        progressRow(
          labels[key] || key,
          formatNumber(item.downloads) + ' · ' + (item.percent || 0).toFixed(1) + '%',
          item.percent
        )
      );
    });
  }

  function renderTrend(snapshots) {
    var host = $('intel-trend');
    if (!host) return;
    host.textContent = '';
    if (!snapshots || !snapshots.length) {
      host.appendChild(el('p', 'intel-note', 'No snapshot has been recorded yet.'));
      return;
    }
    var max = 0;
    snapshots.forEach(function (snapshot) {
      var value = Number(snapshot.total_apk_downloads) || 0;
      if (value > max) max = value;
    });
    snapshots.forEach(function (snapshot) {
      var value = Number(snapshot.total_apk_downloads) || 0;
      var percent = max > 0 ? (value * 100) / max : 0;
      host.appendChild(progressRow(snapshot.date, formatNumber(value), percent));
    });
    if (snapshots.length === 1) {
      host.appendChild(
        el(
          'p',
          'intel-note mt-3',
          'The first snapshot is the baseline. A trend becomes meaningful after several daily captures.'
        )
      );
    }
  }

  function renderComparison(rows) {
    var tbody = $('intel-comparison');
    if (!tbody) return;
    tbody.textContent = '';
    if (!rows || !rows.length) {
      var empty = el('tr');
      var cell = el('td', '', 'No comparable releases yet.');
      cell.colSpan = 3;
      empty.appendChild(cell);
      tbody.appendChild(empty);
      return;
    }
    rows
      .slice()
      .reverse()
      .forEach(function (row) {
        var tr = el('tr');
        tr.appendChild(el('td', '', row.tag || '—'));
        tr.appendChild(el('td', 'intel-num', formatNumber(row.apk_downloads)));
        var delta = row.delta_from_previous;
        tr.appendChild(
          el(
            'td',
            'intel-num',
            typeof delta === 'number' ? (delta > 0 ? '+' : '') + formatNumber(delta) : '—'
          )
        );
        tbody.appendChild(tr);
      });
  }

  function renderCloud(cloud) {
    var data = cloud && typeof cloud === 'object' ? cloud : {};
    var runs = Array.isArray(data.runs) ? data.runs : [];
    var passed = runs.filter(function (run) {
      return run && run.status === 'passed';
    }).length;
    var failed = runs.filter(function (run) {
      return run && run.status === 'failed';
    }).length;

    if (data.status === 'not_configured' || !runs.length) {
      setText('intel-cloud-status', 'Not configured');
      setText('intel-cloud-meta', 'No cloud run recorded');
      setText(
        'intel-cloud-summary',
        'Cloud device testing is implemented as an opt-in workflow. It has not run because Google Cloud access is not configured.'
      );
    } else {
      setText('intel-cloud-status', passed + ' / ' + runs.length + ' passed');
      setText('intel-cloud-meta', failed ? failed + ' failed run(s)' : 'No failed run recorded');
      setText('intel-cloud-summary', 'Aggregate outcomes from the cloud device test workflow.');
    }

    var tbody = $('intel-cloud-runs');
    if (!tbody) return;
    tbody.textContent = '';
    if (!runs.length) {
      var empty = el('tr');
      var cell = el('td', '', 'No run recorded. Missing data is not a pass.');
      cell.colSpan = 4;
      empty.appendChild(cell);
      tbody.appendChild(empty);
      return;
    }
    runs.slice(0, 20).forEach(function (run) {
      var tr = el('tr');
      var runCell = el('td');
      var label = run.run_id ? String(run.run_id) : 'Run';
      var url = safeHttpsUrl(run.run_url);
      if (url) {
        var link = el('a', '', label);
        link.href = url;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        runCell.appendChild(link);
      } else {
        runCell.textContent = label;
      }
      tr.appendChild(runCell);
      tr.appendChild(el('td', '', run.device || '—'));
      tr.appendChild(el('td', '', run.android_version || '—'));
      tr.appendChild(el('td', '', run.status || 'unknown'));
      tbody.appendChild(tr);
    });
  }

  function renderUnavailable(items) {
    var host = $('intel-unavailable');
    if (!host) return;
    host.textContent = '';
    if (!items || !items.length) {
      host.appendChild(el('li', '', 'No unavailable metric was reported.'));
      return;
    }
    items.forEach(function (item) {
      var li = el('li');
      li.appendChild(el('strong', 'text-white', item.metric + ': '));
      li.appendChild(document.createTextNode('unavailable — ' + (item.reason || 'not collected')));
      host.appendChild(li);
    });
  }

  function renderDisclaimers(items) {
    var host = $('intel-disclaimers');
    if (!host) return;
    host.textContent = '';
    (items || []).forEach(function (item) {
      host.appendChild(el('li', '', item));
    });
  }

  function render(data) {
    var labels = data.abi_labels || {};
    var totals = data.totals || {};
    var latest = data.latest_release;

    setVisible($('intel-loading'), false);
    setVisible($('intel-content'), true);
    setVisible($('intel-error'), false);
    panel.setAttribute('aria-busy', 'false');

    setText('intel-refresh', formatTimestamp(data.generated_at_utc));
    setText('intel-total-downloads', formatNumber(totals.apk_downloads));
    setText('intel-releases', formatNumber(totals.releases));
    setText(
      'intel-releases-meta',
      formatNumber(totals.releases_with_apk) + ' with APK assets · ' + formatNumber(totals.assets) + ' assets'
    );

    if (latest) {
      setText('intel-latest', latest.tag || '—');
      setText(
        'intel-latest-meta',
        formatDate(latest.published_at) + ' · ' + formatNumber(latest.apk_downloads) + ' APK downloads'
      );
    } else {
      setText('intel-latest', 'None');
      setText('intel-latest-meta', 'No published release recorded');
    }

    var source = safeHttpsUrl(data.source_url);
    var sourceLink = $('intel-source-link');
    if (source && sourceLink) sourceLink.href = source;

    renderReleaseRows(Array.isArray(data.releases) ? data.releases : [], labels);
    renderAbi(data.downloads_by_abi, labels);
    renderTrend(Array.isArray(data.snapshots) ? data.snapshots : []);
    renderComparison(Array.isArray(data.release_comparison) ? data.release_comparison : []);
    renderCloud(data.cloud_tests);
    renderUnavailable(data.unavailable_metrics);
    renderDisclaimers(data.disclaimers);
  }

  function showError() {
    setVisible($('intel-loading'), false);
    setVisible($('intel-content'), false);
    setVisible($('intel-error'), true);
    panel.setAttribute('aria-busy', 'false');
    setText('intel-refresh', 'unavailable');
  }

  fetch('data/release-intelligence.json', {
    cache: 'no-store',
    headers: { Accept: 'application/json' }
  })
    .then(function (response) {
      if (!response.ok) throw new Error('Dataset returned ' + response.status);
      return response.json();
    })
    .then(function (data) {
      if (!data || typeof data !== 'object' || !data.totals) throw new Error('Invalid dataset');
      render(data);
    })
    .catch(showError);
})();
