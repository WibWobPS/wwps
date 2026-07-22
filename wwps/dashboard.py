from __future__ import annotations

import json

from aiohttp import web

from . import config, metrics

PAGE = """<!doctype html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>WWPS status</title>
<style>
:root {
  color-scheme: dark;
  --surface-0: #121211;
  --surface-1: #1a1a19;
  --surface-2: #232322;
  --border:    #32322f;
  --text-primary: #ffffff;
  --text-secondary: #c3c2b7;
  --text-muted: #8a8a80;
  --series-1: #3987e5;
  --series-2: #c98500;
  --good: #0ca30c;
  --warning: #fab219;
  --serious: #ec835a;
  --critical: #d03b3b;
}
@media (prefers-color-scheme: light) {
  :root:where(:not([data-theme="dark"])) {
    color-scheme: light;
    --surface-0: #f4f3f0;
    --surface-1: #fcfcfb;
    --surface-2: #f0efec;
    --border:    #dedcd6;
    --text-primary: #0b0b0b;
    --text-secondary: #52514e;
    --text-muted: #75736d;
    --series-1: #2a78d6;
    --series-2: #eda100;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 24px;
  background: var(--surface-0);
  color: var(--text-primary);
  font: 14px/1.5 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
}
header { display: flex; align-items: baseline; gap: 16px; margin-bottom: 20px; }
h1 { font-size: 15px; font-weight: 600; margin: 0; letter-spacing: .01em; }
.sub { color: var(--text-muted); font-size: 12px; }
.dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block;
       margin-right: 6px; vertical-align: baseline; }
.grid { display: grid; gap: 12px; }
.kpis { grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); margin-bottom: 12px; }
.cols { grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); }
.panel {
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 14px 16px;
}
.panel h2 {
  font-size: 11px; font-weight: 600; letter-spacing: .08em;
  text-transform: uppercase; color: var(--text-muted);
  margin: 0 0 12px;
}
.hero { font-size: 48px; font-weight: 600; line-height: 1.1; }
.hero-unit { font-size: 13px; color: var(--text-secondary); margin-top: 2px; }
.tile-label { font-size: 11px; letter-spacing: .06em; text-transform: uppercase;
              color: var(--text-muted); margin-bottom: 6px; }
.tile-value { font-size: 24px; font-weight: 600; }
.tile-note { font-size: 12px; color: var(--text-secondary); margin-top: 2px; }
table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
th {
  text-align: left; font-size: 11px; font-weight: 600; letter-spacing: .06em;
  text-transform: uppercase; color: var(--text-muted);
  padding: 0 8px 8px 0; border-bottom: 1px solid var(--border);
}
td { padding: 7px 8px 7px 0; border-bottom: 1px solid var(--surface-2); font-size: 13px; }
td.num { text-align: right; }
tbody tr:last-child td { border-bottom: none; }
.bar-track { height: 6px; background: var(--surface-2); border-radius: 3px; min-width: 60px; }
.bar-fill { height: 6px; background: var(--series-1); border-radius: 3px; }
.legend { display: flex; gap: 16px; margin-bottom: 8px; font-size: 12px;
          color: var(--text-secondary); }
.events li { list-style: none; padding: 6px 0; border-bottom: 1px solid var(--surface-2);
             font-size: 13px; display: flex; gap: 8px; }
.events ul { margin: 0; padding: 0; }
.events time { color: var(--text-muted); font-variant-numeric: tabular-nums;
               flex-shrink: 0; }
.empty { color: var(--text-muted); font-size: 13px; }
button {
  background: var(--surface-2); color: var(--text-secondary);
  border: 1px solid var(--border); border-radius: 4px;
  font: inherit; font-size: 11px; letter-spacing: .06em; text-transform: uppercase;
  padding: 3px 10px; cursor: pointer;
}
button:hover { color: var(--text-primary); }
.panel-head { display: flex; justify-content: space-between; align-items: center; }
.panel-head h2 { margin-bottom: 12px; }
svg { display: block; width: 100%; height: 150px; overflow: visible; }
.grid-line { stroke: var(--border); stroke-width: 1; }
.axis-label { fill: var(--text-muted); font-size: 10px; }
.mark-label { font-size: 11px; font-weight: 600; }
.crosshair { stroke: var(--text-muted); stroke-width: 1; stroke-dasharray: 3 3; }
.tooltip {
  position: fixed; pointer-events: none; opacity: 0;
  background: var(--surface-2); border: 1px solid var(--border);
  border-radius: 4px; padding: 6px 9px; font-size: 12px;
  color: var(--text-primary); white-space: nowrap; z-index: 10;
  font-variant-numeric: tabular-nums;
}
.hidden { display: none; }
</style>
</head>
<body>
<header>
  <h1>WWPS status</h1>
  <span class="sub" id="ident"></span>
  <span class="sub" id="uptime"></span>
</header>

<section class="grid cols" style="grid-template-columns: minmax(220px, 1fr) 3fr;">
  <div class="panel">
    <h2>Requests, last minute</h2>
    <div class="hero" id="hero">0</div>
    <div class="hero-unit">requests per minute</div>
  </div>
  <div class="grid kpis" id="kpis"></div>
</section>

<section class="grid cols" style="margin-top: 12px;">
  <div class="panel">
    <div class="panel-head">
      <h2>Request rate</h2>
      <button data-toggle="rate">Table</button>
    </div>
    <div id="rate-chart"></div>
    <div id="rate-table" class="hidden"></div>
  </div>
  <div class="panel">
    <div class="panel-head">
      <h2>Latency</h2>
      <button data-toggle="lat">Table</button>
    </div>
    <div class="legend">
      <span><span class="dot" style="background: var(--series-1)"></span>p50</span>
      <span><span class="dot" style="background: var(--series-2)"></span>p95</span>
    </div>
    <div id="lat-chart"></div>
    <div id="lat-table" class="hidden"></div>
  </div>
</section>

<section class="grid cols" style="margin-top: 12px;">
  <div class="panel">
    <h2>Endpoints</h2>
    <div id="endpoints"></div>
  </div>
  <div class="panel">
    <h2>Counters</h2>
    <div id="counters"></div>
  </div>
</section>

<section class="panel" style="margin-top: 12px;">
  <h2>Recent events</h2>
  <div class="events" id="events"></div>
</section>

<div class="tooltip" id="tip"></div>

<script>
const tip = document.getElementById('tip');
let latencyHistory = [];

function fmt(n) {
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
  if (n >= 10000) return (n / 1000).toFixed(1) + 'K';
  return String(n);
}

function duration(seconds) {
  const d = Math.floor(seconds / 86400), h = Math.floor(seconds % 86400 / 3600);
  const m = Math.floor(seconds % 3600 / 60), s = seconds % 60;
  if (d) return d + 'd ' + h + 'h';
  if (h) return h + 'h ' + m + 'm';
  if (m) return m + 'm ' + s + 's';
  return s + 's';
}

function statusColor(rate) {
  if (rate >= 5) return 'var(--critical)';
  if (rate >= 1) return 'var(--warning)';
  return 'var(--good)';
}

function tile(label, value, note, color) {
  const c = color ? ' style="color:' + color + '"' : '';
  return '<div class="panel"><div class="tile-label">' + label + '</div>' +
         '<div class="tile-value"' + c + '>' + value + '</div>' +
         (note ? '<div class="tile-note">' + note + '</div>' : '') + '</div>';
}

function linechart(target, series, opts) {
  const w = 600, h = 150, padL = 34, padR = 46, padB = 18, padT = 8;
  const points = series[0].values.length;
  if (!points) { target.innerHTML = '<p class="empty">No data yet.</p>'; return; }
  let max = 0;
  series.forEach(s => s.values.forEach(v => { if (v > max) max = v; }));
  if (max <= 0) max = opts.minMax || 1;
  max = max * 1.15;

  const x = i => padL + (i / Math.max(points - 1, 1)) * (w - padL - padR);
  const y = v => padT + (1 - v / max) * (h - padT - padB);

  let svg = '<svg viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="none" ' +
            'role="img" aria-label="' + opts.label + '">';
  for (let g = 0; g <= 2; g++) {
    const gy = padT + (g / 2) * (h - padT - padB);
    svg += '<line class="grid-line" x1="' + padL + '" y1="' + gy + '" x2="' +
           (w - padR) + '" y2="' + gy + '"/>';
    svg += '<text class="axis-label" x="0" y="' + (gy + 3) + '">' +
           fmt(Math.round(max * (1 - g / 2))) + '</text>';
  }
  series.forEach(s => {
    const d = s.values.map((v, i) => (i ? 'L' : 'M') + x(i).toFixed(1) + ' ' +
              y(v).toFixed(1)).join(' ');
    svg += '<path d="' + d + '" fill="none" stroke="' + s.color +
           '" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>';
    const last = s.values[s.values.length - 1];
    svg += '<circle cx="' + x(points - 1).toFixed(1) + '" cy="' + y(last).toFixed(1) +
           '" r="3" fill="' + s.color + '"/>';
    svg += '<text class="mark-label" x="' + (w - padR + 6) + '" y="' +
           (y(last) + 4).toFixed(1) + '" fill="' + s.color + '">' +
           s.format(last) + '</text>';
  });
  svg += '<line class="crosshair" id="' + opts.id + '-cross" x1="0" y1="' + padT +
         '" x2="0" y2="' + (h - padB) + '" opacity="0"/>';
  svg += '<rect x="' + padL + '" y="0" width="' + (w - padL - padR) + '" height="' + h +
         '" fill="transparent" id="' + opts.id + '-hit"/>';
  svg += '</svg>';
  target.innerHTML = svg;

  const hit = document.getElementById(opts.id + '-hit');
  const cross = document.getElementById(opts.id + '-cross');
  hit.addEventListener('mousemove', ev => {
    const box = hit.getBoundingClientRect();
    const ratio = (ev.clientX - box.left) / box.width;
    const idx = Math.max(0, Math.min(points - 1, Math.round(ratio * (points - 1))));
    cross.setAttribute('opacity', '1');
    cross.setAttribute('x1', x(idx));
    cross.setAttribute('x2', x(idx));
    tip.style.opacity = '1';
    tip.style.left = (ev.clientX + 12) + 'px';
    tip.style.top = (ev.clientY - 34) + 'px';
    tip.innerHTML = opts.tooltip(idx);
  });
  hit.addEventListener('mouseleave', () => {
    cross.setAttribute('opacity', '0');
    tip.style.opacity = '0';
  });
}

function seriesTable(rows, headers) {
  let html = '<table><thead><tr>';
  headers.forEach(h => html += '<th' + (h.num ? ' class="num"' : '') + '>' + h.label + '</th>');
  html += '</tr></thead><tbody>';
  rows.forEach(r => {
    html += '<tr>';
    r.forEach((cell, i) => html += '<td' + (headers[i].num ? ' class="num"' : '') + '>' +
              cell + '</td>');
    html += '</tr>';
  });
  return html + '</tbody></table>';
}

function render(data) {
  document.getElementById('ident').textContent =
    data.server + ' - ' + data.mode + ' - version ' + data.version;
  document.getElementById('uptime').textContent = 'up ' + duration(data.uptime_seconds);
  document.getElementById('hero').textContent = fmt(data.rate_per_minute);

  document.getElementById('kpis').innerHTML =
    tile('Total requests', fmt(data.requests_total), null, null) +
    tile('Error rate', data.error_rate.toFixed(2) + '%',
         fmt(data.requests_failed) + ' failed', statusColor(data.error_rate)) +
    tile('Latency p95', data.latency_p95.toFixed(0) + ' ms',
         'p99 ' + data.latency_p99.toFixed(0) + ' ms', null) +
    tile('Accounts cached', fmt(data.gauges.accounts_cached || 0),
         'flush ' + (data.gauges.flush_duration_ms || 0) + ' ms', null) +
    tile('Battles', fmt(data.counters.battles_finished || 0),
         fmt(data.counters.battles_started || 0) + ' started', null) +
    tile('Rejected', fmt((data.counters.auth_rejected || 0) +
         (data.counters.cheat_clear_time || 0) + (data.counters.cheat_score_cap || 0) +
         (data.counters.cheat_befriend || 0)), 'auth and cheat checks',
         ((data.counters.auth_rejected || 0) + (data.counters.cheat_clear_time || 0) +
          (data.counters.cheat_score_cap || 0) + (data.counters.cheat_befriend || 0))
           ? 'var(--serious)' : null);

  const reqs = data.series.map(p => p.requests);
  const errs = data.series.map(p => p.errors);
  linechart(document.getElementById('rate-chart'),
    [{ values: reqs, color: 'var(--series-1)', format: v => v + '/s' }],
    { id: 'rate', label: 'Requests per second over the last minute', minMax: 5,
      tooltip: i => reqs[i] + ' req/s, ' + errs[i] + ' failed' });
  document.getElementById('rate-table').innerHTML = seriesTable(
    data.series.slice(-12).reverse().map(p => [
      new Date(p.t * 1000).toLocaleTimeString(), p.requests, p.errors]),
    [{ label: 'Time' }, { label: 'Requests', num: true }, { label: 'Failed', num: true }]);

  latencyHistory.push({ p50: data.latency_p50, p95: data.latency_p95 });
  if (latencyHistory.length > 60) latencyHistory.shift();
  linechart(document.getElementById('lat-chart'),
    [{ values: latencyHistory.map(p => p.p50), color: 'var(--series-1)',
       format: v => v.toFixed(0) + ' ms' },
     { values: latencyHistory.map(p => p.p95), color: 'var(--series-2)',
       format: v => v.toFixed(0) + ' ms' }],
    { id: 'lat', label: 'Request latency percentiles', minMax: 10,
      tooltip: i => 'p50 ' + latencyHistory[i].p50.toFixed(0) + ' ms, p95 ' +
                    latencyHistory[i].p95.toFixed(0) + ' ms' });
  document.getElementById('lat-table').innerHTML = seriesTable(
    latencyHistory.slice(-12).reverse().map((p, i) => [
      i === 0 ? 'now' : i * 2 + 's ago', p.p50.toFixed(0), p.p95.toFixed(0)]),
    [{ label: 'Age' }, { label: 'p50 ms', num: true }, { label: 'p95 ms', num: true }]);

  const top = data.endpoints;
  const maxCount = top.length ? top[0].count : 1;
  document.getElementById('endpoints').innerHTML = top.length ? seriesTable(
    top.map(e => [
      e.path,
      '<div class="bar-track"><div class="bar-fill" style="width:' +
        (e.count / maxCount * 100).toFixed(1) + '%"></div></div>',
      e.count, e.errors, e.p95.toFixed(0)]),
    [{ label: 'Path' }, { label: 'Share' }, { label: 'Count', num: true },
     { label: 'Failed', num: true }, { label: 'p95 ms', num: true }])
    : '<p class="empty">No requests yet.</p>';

  const counters = Object.entries(data.counters).sort((a, b) => b[1] - a[1]);
  document.getElementById('counters').innerHTML = counters.length ? seriesTable(
    counters.map(([k, v]) => [k.replace(/_/g, ' '), fmt(v)]),
    [{ label: 'Counter' }, { label: 'Value', num: true }])
    : '<p class="empty">No counters yet.</p>';

  const levels = { critical: 'var(--critical)', serious: 'var(--serious)',
                   warning: 'var(--warning)', good: 'var(--good)' };
  document.getElementById('events').innerHTML = data.events.length
    ? '<ul>' + data.events.map(e =>
        '<li><time>' + new Date(e.ts * 1000).toLocaleTimeString() + '</time>' +
        '<span><span class="dot" style="background:' +
        (levels[e.level] || 'var(--text-muted)') + '"></span>' +
        e.level + '</span><span>' + e.message + '</span></li>').join('') + '</ul>'
    : '<p class="empty">Nothing logged yet.</p>';
}

document.querySelectorAll('button[data-toggle]').forEach(btn => {
  btn.addEventListener('click', () => {
    const key = btn.dataset.toggle;
    const chart = document.getElementById(key + '-chart');
    const table = document.getElementById(key + '-table');
    const showTable = chart.classList.toggle('hidden');
    table.classList.toggle('hidden', !showTable);
    btn.textContent = showTable ? 'Chart' : 'Table';
  });
});

async function poll() {
  try {
    const res = await fetch('data' + location.search, { cache: 'no-store' });
    if (res.ok) render(await res.json());
  } catch (err) {
    document.getElementById('uptime').textContent = 'disconnected';
  }
}
poll();
setInterval(poll, 2000);
</script>
</body>
</html>
"""


def _authorized(request: web.Request) -> bool:
    if not config.dashboard_token:
        return True
    provided = (request.query.get("token")
                or request.headers.get("X-Dashboard-Token"))
    return provided == config.dashboard_token


def _deny() -> web.Response:
    return web.Response(status=401, text="Unauthorized", content_type="text/plain")


async def page(request: web.Request) -> web.Response:
    if not _authorized(request):
        return _deny()
    return web.Response(text=PAGE, content_type="text/html", charset="utf-8")


async def data(request: web.Request) -> web.Response:
    if not _authorized(request):
        return _deny()
    payload = metrics.snapshot()
    payload["server"] = config.server_name or "WWPS"
    payload["mode"] = "Wibble Wobble" if config.is_wibwob else "Puni Puni"
    payload["version"] = config.game_version or "unknown"
    return web.Response(text=json.dumps(payload), content_type="application/json")


async def prometheus(request: web.Request) -> web.Response:
    if not _authorized(request):
        return _deny()
    return web.Response(text=metrics.prometheus(), content_type="text/plain")
