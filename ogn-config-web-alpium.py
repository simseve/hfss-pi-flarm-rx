#!/usr/bin/env python3
"""Alpium OGN station agent.

Runs on every Raspberry Pi receiver as the systemd service
`alpium-ogn-station` (user hfss). Two jobs:

1. Heartbeat: every few minutes, POST the station's health to Alpium with the
   station's OWN api key (written by install.sh at enrollment). Alpium's
   console and its silence alert are built on this.
2. Station UI on :8082: receiver settings and Wi-Fi, for Alpium admins only.
   The firewall (system/firewall.nft) admits it from the tailnet alone, and
   this process refuses any client outside loopback and 100.64.0.0/10 as a
   second line. Root actions go through /usr/local/sbin/alpium-ogn-helper.

The station never holds a shared secret: no manufacturer secret, no reusable
Tailscale key. A station joins with `sudo ./install.sh --code ...`; see
PRODUCTION-DEPLOYMENT.md.
"""
import ipaddress
import json
import os
import re
import subprocess
import threading
import time
from datetime import datetime, timezone

import requests
from flask import Flask, abort, jsonify, render_template_string, request

AGENT_VERSION = "2.0.0"

HOME = os.environ.get("ALPIUM_OGN_HOME", "/home/hfss")
REPO_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.environ.get("OGN_TEMPLATE_CONF", os.path.join(HOME, "rtlsdr-ogn", "Template.conf"))
TEMPLATE_IN = os.path.join(REPO_DIR, "ogn", "Template.conf.in")
CREDENTIALS_FILE = os.path.join(HOME, ".ogn_credentials.json")
HEARTBEAT_LOG_FILE = os.path.join(HOME, ".ogn_heartbeat_log.json")
HELPER = "/usr/local/sbin/alpium-ogn-helper"

DEFAULT_HEARTBEAT_INTERVAL = 300
HEARTBEAT_LOG_KEEP = 100

TAILNET = ipaddress.ip_network("100.64.0.0/10")
CALLSIGN_RE = re.compile(r"^[A-Za-z0-9]{3,9}$")

app = Flask(__name__, static_folder=os.path.join(REPO_DIR, "static"), static_url_path="/static")

_history_lock = threading.Lock()
heartbeat_history = []
heartbeat_state = {"last_ok": None, "last_error": None}


# ---------------------------------------------------------------------------
# Access: loopback and the tailnet only
# ---------------------------------------------------------------------------

@app.before_request
def tailnet_only():
    """Refuse every client that is not local or on the tailnet.

    The firewall already drops them; this holds if the firewall is ever
    flushed. Also refuses state-changing requests that are not JSON, which
    a cross-site form cannot send without a CORS preflight this app never
    answers.
    """
    try:
        addr = ipaddress.ip_address(request.remote_addr or "")
    except ValueError:
        abort(403)
    if not (addr.is_loopback or (addr.version == 4 and addr in TAILNET)):
        abort(403)
    if request.method == "POST" and not request.is_json:
        abort(415)


# ---------------------------------------------------------------------------
# Station facts
# ---------------------------------------------------------------------------

def run(args, timeout=5, **kwargs):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, **kwargs)


def helper(*args, stdin=None):
    """Run the root helper; it always answers one JSON line."""
    try:
        r = run(["sudo", "-n", HELPER, *args], timeout=40, input=json.dumps(stdin) if stdin is not None else None)
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception as e:  # helper missing, sudo refused, garbage output
        return {"success": False, "message": f"Helper failed: {e}"}


def get_tailscale_ip():
    try:
        r = run(["tailscale", "ip", "-4"], timeout=3)
        ip = r.stdout.strip().splitlines()[0] if r.returncode == 0 and r.stdout.strip() else None
        return ip if ip and ipaddress.ip_address(ip) in TAILNET else None
    except Exception:
        return None


def get_serial():
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("Serial"):
                    return line.split(":")[1].strip()[-8:].lower()
    except OSError:
        pass
    return "unknown"


def interface_state(iface):
    try:
        link = run(["ip", "link", "show", iface]).stdout
        addr = run(["ip", "-4", "addr", "show", iface]).stdout
    except Exception:
        return {"present": False, "up": False, "ip": None}
    m = re.search(r"inet ([\d.]+)", addr)
    return {"present": bool(link), "up": "state UP" in link, "ip": m.group(1) if m else None}


def station_status():
    status = {"timestamp": datetime.now(timezone.utc).isoformat()}
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            status["cpu_temp"] = round(float(f.read().strip()) / 1000.0, 1)
    except (OSError, ValueError):
        status["cpu_temp"] = None
    try:
        with open("/proc/uptime") as f:
            status["uptime"] = int(float(f.read().split()[0]))
    except (OSError, ValueError):
        status["uptime"] = None
    try:
        import shutil
        du = shutil.disk_usage("/")
        status["disk_usage_percent"] = round(du.used / du.total * 100, 1)
    except OSError:
        status["disk_usage_percent"] = None
    try:
        with open("/proc/meminfo") as f:
            mem = {l.split(":")[0]: int(l.split()[1]) for l in f if ":" in l}
        status["memory_usage_percent"] = round((mem["MemTotal"] - mem["MemAvailable"]) / mem["MemTotal"] * 100, 1)
    except (OSError, KeyError, ValueError, ZeroDivisionError):
        status["memory_usage_percent"] = None
    rf = run(["pgrep", "-x", "ogn-rf"]).returncode == 0
    dec = run(["pgrep", "-x", "ogn-decode"]).returncode == 0
    status.update(ogn_rf_running=rf, ogn_decode_running=dec, ogn_status="online" if rf and dec else "offline")
    status["vpn_ip"] = get_tailscale_ip()
    return status


# ---------------------------------------------------------------------------
# OGN receiver configuration
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {"call": "NOCALL", "latitude": 0.0, "longitude": 0.0, "altitude": 0,
                  "freqcorr": 0.0, "centerfreq": 868.8, "gain": 50.0}


def read_config():
    config = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_FILE) as f:
            # Comments out: upstream's template carries commented examples
            # such as #Call = "NewOGNrx" that must not be read as settings.
            content = re.sub(r"#[^\n]*", "", f.read())
    except OSError:
        return config
    patterns = {
        "call": (r'Call\s*=\s*"([^"]+)"', str),
        "latitude": (r"Latitude\s*=\s*([+\d.-]+)", float),
        "longitude": (r"Longitude\s*=\s*([+\d.-]+)", float),
        "altitude": (r"Altitude\s*=\s*([+\d.-]+)", lambda v: int(float(v))),
        "freqcorr": (r"FreqCorr\s*=\s*([+\d.-]+)", float),
    }
    for key, (pattern, cast) in patterns.items():
        m = re.search(pattern, content)
        if m:
            try:
                config[key] = cast(m.group(1))
            except ValueError:
                pass
    m = re.search(r"OGN:\s*\{[^}]*?CenterFreq\s*=\s*([\d.]+)", content, re.S)
    if m:
        config["centerfreq"] = float(m.group(1))
    m = re.search(r"OGN:\s*\{[^}]*?Gain\s*=\s*([\d.]+)", content, re.S)
    if m:
        config["gain"] = float(m.group(1))
    return config


def validated_config(d):
    """The receiver settings from a request, or a message saying what is wrong."""
    try:
        cfg = {
            "call": str(d.get("call", "")).strip(),
            "latitude": float(d["latitude"]),
            "longitude": float(d["longitude"]),
            "altitude": int(float(d["altitude"])),
            "freqcorr": float(d.get("freqcorr", 0) or 0),
            "centerfreq": float(d.get("centerfreq", 868.8) or 868.8),
            "gain": float(d.get("gain", 50) or 50),
        }
    except (KeyError, TypeError, ValueError):
        return None, "Every number must be a number"
    if not CALLSIGN_RE.match(cfg["call"]):
        return None, "Callsign: 3-9 letters or digits (http://wiki.glidernet.org/receiver-naming-convention)"
    checks = [
        (-90 <= cfg["latitude"] <= 90, "Latitude out of range"),
        (-180 <= cfg["longitude"] <= 180, "Longitude out of range"),
        (-500 <= cfg["altitude"] <= 9000, "Altitude out of range"),
        (-100 <= cfg["freqcorr"] <= 100, "Frequency correction out of range"),
        (860 <= cfg["centerfreq"] <= 930, "Centre frequency must be 860-930 MHz"),
        (0 <= cfg["gain"] <= 60, "Gain must be 0-60 dB"),
    ]
    for ok, message in checks:
        if not ok:
            return None, message
    return cfg, None


def write_config(cfg):
    with open(TEMPLATE_IN) as f:
        text = f.read()
    for key, value in cfg.items():
        text = text.replace("{" + key + "}", str(value))
    tmp = CONFIG_FILE + ".tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, CONFIG_FILE)


# ---------------------------------------------------------------------------
# Credentials and heartbeat
# ---------------------------------------------------------------------------

def load_credentials():
    try:
        with open(CREDENTIALS_FILE) as f:
            creds = json.load(f)
        return creds if creds.get("device_id") and creds.get("api_key") else None
    except (OSError, ValueError):
        return None


def load_history():
    global heartbeat_history
    try:
        with open(HEARTBEAT_LOG_FILE) as f:
            heartbeat_history = json.load(f)[-HEARTBEAT_LOG_KEEP:]
    except (OSError, ValueError):
        heartbeat_history = []


def record(status_code, text):
    entry = {"timestamp": datetime.now(timezone.utc).isoformat(),
             "response_status": status_code, "response_text": (text or "")[:500]}
    with _history_lock:
        heartbeat_history.append(entry)
        del heartbeat_history[:-HEARTBEAT_LOG_KEEP]
        try:
            with open(HEARTBEAT_LOG_FILE, "w") as f:
                json.dump(heartbeat_history, f)
        except OSError:
            pass


def send_heartbeat(creds):
    config = read_config()
    status = station_status()
    payload = {
        "device_id": creds["device_id"],
        "latitude": config["latitude"],
        "longitude": config["longitude"],
        "altitude": config["altitude"],
        "speed": 0,
        "heading": 0,
        "timestamp": status["timestamp"],
        # Required by POST /gps/; the nil UUID marks a heartbeat, not a flight.
        "flight_id": "00000000-0000-0000-0000-000000000000",
        "device_metadata": {
            "heartbeat": True,
            "agent_version": AGENT_VERSION,
            "station_status": status["ogn_status"],
            "station_lat": config["latitude"],
            "station_lon": config["longitude"],
            "station_altitude": config["altitude"],
            "callsign": config["call"],
            # Alpium pins this only after the tailnet confirms it is ours.
            "vpn_ip": status["vpn_ip"],
            "cpu_temp": status["cpu_temp"],
            "uptime": status["uptime"],
            "disk_usage_percent": status["disk_usage_percent"],
            "memory_usage_percent": status["memory_usage_percent"],
            "ogn_rf_running": status["ogn_rf_running"],
            "ogn_decode_running": status["ogn_decode_running"],
            "timestamp": status["timestamp"],
        },
    }
    headers = {"Authorization": f"Bearer {creds['api_key']}"}
    if creds.get("cf_access_client_id") and creds.get("cf_access_client_secret"):
        headers["CF-Access-Client-Id"] = creds["cf_access_client_id"]
        headers["CF-Access-Client-Secret"] = creds["cf_access_client_secret"]
    r = requests.post(f"{creds['server_url'].rstrip('/')}/gps/", headers=headers, json=payload, timeout=15)
    record(r.status_code, r.text)
    if r.status_code == 200:
        heartbeat_state["last_ok"] = status["timestamp"]
    else:
        heartbeat_state["last_error"] = f"{r.status_code} {r.text[:200]}"
        print(f"Heartbeat refused: {r.status_code} {r.text[:200]}", flush=True)


def heartbeat_loop():
    """Forever: a station that stops beating is reported by Alpium in 30 min."""
    while True:
        creds = load_credentials()
        interval = DEFAULT_HEARTBEAT_INTERVAL
        if creds:
            interval = int(creds.get("heartbeat_interval") or DEFAULT_HEARTBEAT_INTERVAL)
            try:
                send_heartbeat(creds)
            except Exception as e:
                heartbeat_state["last_error"] = str(e)
                record(0, str(e))
                print(f"Heartbeat error: {e}", flush=True)
        time.sleep(max(60, interval))


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

PAGE = """<!DOCTYPE html>
<html><head><title>OGN station {{ creds.device_id if creds else '' }}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="static/station.css?v={{ version }}">
</head><body><div class="container"><div class="header"><h1>OGN Receiver - Alpium</h1></div>
<div class="content"><div id="status"></div>

<div class="form-section">
<h2>Alpium</h2>
{% if creds %}
<div class="hfss-status hfss-registered">Enrolled</div>
<div class="info-box">
<strong>Station ID:</strong> {{ creds.device_id }}<br>
<strong>Server:</strong> {{ creds.server_url }}<br>
<strong>Tailscale IP:</strong> {{ status.vpn_ip or 'not connected' }}<br>
<strong>Last heartbeat accepted:</strong> {{ hb.last_ok or 'not yet' }}<br>
{% if hb.last_error %}<strong>Last error:</strong> {{ hb.last_error }}<br>{% endif %}
<strong>Agent:</strong> {{ version }}
</div>
<button class="btn" id="logsBtn" type="button">Heartbeat log</button>
<div id="heartbeat-logs" style="display:none;margin-top:20px;"><div id="logs-container"></div></div>
{% else %}
<div class="hfss-status hfss-notregistered">Not enrolled</div>
<div class="info-box">Enroll this station on the Pi with
<code>sudo ./install.sh --code OGN-XXXX-XXXX-XXXX-XXXX</code>, using a code from an Alpium admin.</div>
{% endif %}
</div>

<div class="form-section">
<h2>Network</h2>
<div class="info-box">
{% for name, st in ifaces.items() if st.present %}
<span class="wifi-status wifi-{{ 'on' if st.up else 'off' }}">{{ name }}: {{ 'UP' if st.up else 'DOWN' }} {{ st.ip or '' }}</span>
{% endfor %}
</div>
{% for name, st in ifaces.items() if st.present %}
<button class="btn {{ 'btn-danger' if st.up else 'btn-success' }}" type="button" data-link="{{ name }}" data-action="{{ 'down' if st.up else 'up' }}">Turn {{ name }} {{ 'off' if st.up else 'on' }}</button>
{% endfor %}
</div>

<div class="form-section">
<h2>Wi-Fi networks</h2>
{% if wifi.success %}
<ul class="network-list">
{% for net in wifi.networks %}
<li class="network-item"><div class="network-info"><div class="network-ssid">{{ net.name }}</div>
<div class="network-status">Priority {{ net.priority }}</div></div>
<button class="btn btn-small" type="button" data-wifi-edit="{{ net.name }}">Password</button>
<button class="btn btn-small btn-danger" type="button" data-wifi-delete="{{ net.name }}">Delete</button></li>
{% endfor %}
</ul>
<h3 style="margin-top:20px">Add network</h3>
<form id="wifiForm">
<div class="form-group"><label>SSID</label><input name="ssid" maxlength="32" required></div>
<div class="form-group"><label>Password</label><input type="password" name="psk" minlength="8" maxlength="64" required></div>
<div class="form-group"><label>Priority (higher = preferred)</label><input type="number" name="priority" value="1"></div>
<button type="submit" class="btn">Add network</button>
</form>
{% else %}
<div class="info-box">{{ wifi.message }}</div>
{% endif %}
</div>

<form id="f"><div class="form-section"><h2>Station</h2>
<div class="form-group"><label>Callsign (3-9 letters/digits)</label><input name="call" value="{{ config.call }}" maxlength="9" required></div></div>
<div class="form-section"><h2>Antenna position</h2>
<div class="form-group"><label>Latitude</label><input type="number" name="latitude" value="{{ config.latitude }}" step="0.000001" required></div>
<div class="form-group"><label>Longitude</label><input type="number" name="longitude" value="{{ config.longitude }}" step="0.000001" required></div>
<div class="form-group"><label>Altitude (m AMSL)</label><input type="number" name="altitude" value="{{ config.altitude }}" required></div></div>
<div class="form-section"><h2>RF</h2>
<div class="form-group"><label>Frequency correction (ppm)</label><input type="number" name="freqcorr" value="{{ config.freqcorr }}" step="0.1"></div>
<div class="form-group"><label>Centre frequency (MHz)</label><input type="number" name="centerfreq" value="{{ config.centerfreq }}" step="0.1"></div>
<div class="form-group"><label>Start gain (dB)</label><input type="number" name="gain" value="{{ config.gain }}" step="0.1"></div></div>
<button type="submit" class="btn" id="b">Save and restart receiver</button></form>
</div></div>
<script src="static/station.js?v={{ version }}"></script>
</body></html>"""


@app.route("/")
def index():
    return render_template_string(
        PAGE,
        creds=load_credentials(),
        status=station_status(),
        hb=heartbeat_state,
        config=read_config(),
        ifaces={n: interface_state(n) for n in ("eth0", "eth1", "wlan0")},
        wifi=helper("wifi-list"),
        version=AGENT_VERSION,
    )


@app.route("/api/save", methods=["POST"])
def save():
    cfg, error = validated_config(request.get_json(silent=True) or {})
    if error:
        return jsonify(success=False, message=error)
    try:
        write_config(cfg)
    except OSError as e:
        return jsonify(success=False, message=f"Could not write the configuration: {e}")
    r = helper("restart-ogn")
    if not r.get("success"):
        return jsonify(r)
    return jsonify(success=True, message="Configuration saved, receiver restarted")


@app.route("/api/wifi/toggle", methods=["POST"])
def wifi_toggle():
    d = request.get_json(silent=True) or {}
    action = {"on": "up", "off": "down"}.get(d.get("action"), d.get("action"))
    return jsonify(helper("link", str(d.get("interface", "")), str(action)))


@app.route("/api/wifi/add", methods=["POST"])
def wifi_add():
    d = request.get_json(silent=True) or {}
    return jsonify(helper("wifi-add", stdin={"ssid": d.get("ssid"), "psk": d.get("psk"), "priority": d.get("priority", 1)}))


@app.route("/api/wifi/edit", methods=["POST"])
def wifi_edit():
    d = request.get_json(silent=True) or {}
    return jsonify(helper("wifi-set-psk", stdin={"name": d.get("name"), "psk": d.get("psk")}))


@app.route("/api/wifi/delete", methods=["POST"])
def wifi_delete():
    d = request.get_json(silent=True) or {}
    return jsonify(helper("wifi-delete", str(d.get("name", ""))))


@app.route("/api/hfss/register", methods=["POST"])
def hfss_register():
    # Kept so an old page says why it stopped working.
    return jsonify(success=False, message="Stations enroll with sudo ./install.sh --code <code from an Alpium admin>"), 410


@app.route("/api/hfss/heartbeat-logs")
def heartbeat_logs():
    with _history_lock:
        return jsonify(success=True, logs=list(heartbeat_history))


@app.route("/api/health")
def health():
    creds = load_credentials()
    status = station_status()
    return jsonify(
        status="ok",
        agent_version=AGENT_VERSION,
        serial=get_serial(),
        enrolled=bool(creds),
        device_id=creds["device_id"] if creds else None,
        heartbeat=heartbeat_state,
        system=status,
        config=read_config(),
    )


if __name__ == "__main__":
    load_history()
    threading.Thread(target=heartbeat_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=8082, debug=False, threaded=True)
