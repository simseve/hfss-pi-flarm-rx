// Station UI behaviour. A file, not an inline <script>: Alpium's proxy serves
// this page under `script-src 'self'`, where inline scripts never run.
// Every URL is RELATIVE ("api/save", not "/api/save") so the page works both
// opened directly on the tailnet and inside Alpium's console proxy.
(function () {
  'use strict';

  function show(j) {
    var box = document.getElementById('status');
    box.innerHTML = '';
    var div = document.createElement('div');
    div.className = 'status ' + (j && j.success ? 'success' : 'error');
    div.textContent = (j && j.message) || 'Request failed';
    box.appendChild(div);
  }

  function post(path, body) {
    return fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    }).then(function (r) { return r.json(); })
      .catch(function (e) { return { success: false, message: String(e) }; });
  }

  function reloadSoon(j, ms) {
    show(j);
    if (j.success) setTimeout(function () { location.reload(); }, ms || 1500);
  }

  document.querySelectorAll('[data-link]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var iface = btn.getAttribute('data-link');
      var action = btn.getAttribute('data-action');
      if (action === 'down' && !confirm('Turn ' + iface + ' off? If the station reaches the internet through it, you lose it until someone is on site.')) return;
      post('api/wifi/toggle', { interface: iface, action: action }).then(function (j) { reloadSoon(j, 2000); });
    });
  });

  document.querySelectorAll('[data-wifi-edit]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var name = btn.getAttribute('data-wifi-edit');
      var psk = prompt('New password for ' + name + ':');
      if (!psk) return;
      post('api/wifi/edit', { name: name, psk: psk }).then(function (j) { reloadSoon(j); });
    });
  });

  document.querySelectorAll('[data-wifi-delete]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var name = btn.getAttribute('data-wifi-delete');
      if (!confirm('Delete ' + name + '?')) return;
      post('api/wifi/delete', { name: name }).then(function (j) { reloadSoon(j); });
    });
  });

  var wifiForm = document.getElementById('wifiForm');
  if (wifiForm) wifiForm.addEventListener('submit', function (e) {
    e.preventDefault();
    var d = Object.fromEntries(new FormData(wifiForm));
    post('api/wifi/add', d).then(function (j) { if (j.success) wifiForm.reset(); reloadSoon(j); });
  });

  var cfgForm = document.getElementById('f');
  if (cfgForm) cfgForm.addEventListener('submit', function (e) {
    e.preventDefault();
    var b = document.getElementById('b');
    b.disabled = true;
    post('api/save', Object.fromEntries(new FormData(cfgForm))).then(function (j) {
      b.disabled = false;
      reloadSoon(j, 2000);
    });
  });

  var logsBtn = document.getElementById('logsBtn');
  if (logsBtn) logsBtn.addEventListener('click', function () {
    var box = document.getElementById('heartbeat-logs');
    if (box.style.display !== 'none') { box.style.display = 'none'; return; }
    fetch('api/hfss/heartbeat-logs').then(function (r) { return r.json(); }).then(function (j) {
      var list = document.getElementById('logs-container');
      list.innerHTML = '';
      (j.logs || []).slice().reverse().forEach(function (log) {
        var entry = document.createElement('div');
        entry.className = 'log-entry';
        var head = document.createElement('div');
        head.textContent = log.timestamp + '  status ' + log.response_status;
        head.style.color = log.response_status === 200 ? '#14f195' : '#ff006e';
        var pre = document.createElement('pre');
        pre.textContent = (log.response_text || '').slice(0, 2000);
        entry.appendChild(head);
        entry.appendChild(pre);
        list.appendChild(entry);
      });
      box.style.display = 'block';
    });
  });
})();
