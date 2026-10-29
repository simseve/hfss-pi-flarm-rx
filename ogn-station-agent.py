#!/usr/bin/python3 -I
"""Alpium OGN station agent.

Runs on every Raspberry Pi receiver as the systemd service
`alpium-ogn-station` (user hfss). It serves NO web pages: Alpium is the
station's interface (its admin console, /admin/ogn-stations). Two jobs:

1. Heartbeat: every few minutes, POST the station's health to Alpium's
   /ogn-stations/heartbeat with the station's OWN api key (written by
   install.sh at enrollment). A fixed set of typed fields: Alpium refuses
   unknown ones. Never /gps/, which is for positions and refuses stations.
   Alpium's console and its silence alert are built on this.
2. Control API on :8082, JSON only, for the Alpium SERVER only. Every request
   must carry an Ed25519 signature made with Alpium's station key, whose
   public half the station received at enrollment. The signature covers the
   station's own device id, the method, the path, a timestamp (60 s window)
   and a single-use nonce, and the body's sha256. Being on the tailnet is
   therefore not enough to command a station. The firewall admits :8082 from
   the tailnet only, and this process refuses any client outside loopback
   and 100.64.0.0/10 as well. The only unsigned call is GET /v1/health from
   loopback, for the installer.

Python standard library plus `cryptography` (python3-cryptography), no web
framework: a short, fixed list of routes, bodies capped at 16 KB, JSON in and
out. Root actions go through /usr/local/sbin/alpium-ogn-helper, which checks
its input again.

The canonical request MUST match `canonical_request` in Alpium's
app/services/ogn_station_control.py byte for byte.
"""
import base64
import hashlib
import ipaddress
import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

AGENT_VERSION = "3.2.0"

HOME = os.environ.get("ALPIUM_OGN_HOME", "/home/hfss")
REPO_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.environ.get("OGN_TEMPLATE_CONF", os.path.join(HOME, "rtlsdr-ogn", "Template.conf"))
TEMPLATE_IN = os.path.join(REPO_DIR, "ogn", "Template.conf.in")
CREDENTIALS_FILE = os.path.join(HOME, ".ogn_credentials.json")
AUTHORIZED_KEYS = os.path.join(HOME, ".ssh", "authorized_keys")
HEARTBEAT_LOG_FILE = os.path.join(HOME, ".ogn_heartbeat_log.json")
HELPER = "/usr/local/sbin/alpium-ogn-helper"
UPDATE_STATE = "/var/lib/alpium-ogn/update-state.json"
UPDATE_LOG = "/var/log/alpium-ogn-update.log"

LISTEN_PORT = 8082
DEFAULT_HEARTBEAT_INTERVAL = 300
HEARTBEAT_LOG_KEEP = 100
MAX_BODY = 16 * 1024
OGN_PAGES = {"rf": 8080, "decode": 8081}
OGN_PAGE_MAX = 512 * 1024

SIGNATURE_CONTEXT = "alpium-ogn-control-v1"
CLOCK_WINDOW = 60          # seconds either side
NONCE_TTL = 2 * CLOCK_WINDOW + 10

TAILNET = ipaddress.ip_network("100.64.0.0/10")
CALLSIGN_RE = re.compile(r"^[A-Za-z0-9]{3,9}$")
NONCE_RE = re.compile(r"^[0-9a-f]{16,64}$")

_history_lock = threading.Lock()
heartbeat_history = []
heartbeat_state = {"last_ok": None, "last_error": None}


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


def read_config(path=None):
    config = dict(DEFAULT_CONFIG)
    try:
        with open(path or CONFIG_FILE) as f:
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
    if not isinstance(d, dict):
        return None, "Expected a JSON object"
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
# Credentials and the control key
# ---------------------------------------------------------------------------

def load_credentials():
    try:
        with open(CREDENTIALS_FILE) as f:
            creds = json.load(f)
        return creds if creds.get("device_id") and creds.get("api_key") else None
    except (OSError, ValueError):
        return None


def control_public_key_line(creds):
    """Alpium's public key as an OpenSSH line, from the credentials file or,
    for a station enrolled before it was stored there, the authorized_keys
    entry the installer wrote for Alpium (comment `alpium-ogn`)."""
    line = (creds or {}).get("control_public_key")
    if line:
        return line
    try:
        with open(AUTHORIZED_KEYS) as f:
            for entry in f:
                m = re.search(r"(ssh-ed25519 [A-Za-z0-9+/=]+) alpium-ogn\s*$", entry)
                if m:
                    return m.group(1)
    except OSError:
        pass
    return None


def load_public_key(line):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.hazmat.primitives.serialization import load_ssh_public_key
    key = load_ssh_public_key(" ".join(line.split()[:2]).encode())
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("control key is not Ed25519")
    return key


def canonical_request(device_id, method, path, timestamp, nonce, body):
    """The exact bytes Alpium signs (ogn_station_control.canonical_request)."""
    return "\n".join([
        SIGNATURE_CONTEXT,
        device_id,
        method.upper(),
        path,
        str(int(timestamp)),
        nonce,
        hashlib.sha256(body or b"").hexdigest(),
    ]).encode("utf-8")


class NonceCache:
    """Nonces seen inside the clock window; a replay inside it is refused."""

    def __init__(self, ttl=NONCE_TTL):
        self.ttl = ttl
        self.seen = {}
        self.lock = threading.Lock()

    def use(self, nonce, now):
        with self.lock:
            for n, exp in list(self.seen.items()):
                if exp < now:
                    del self.seen[n]
            if nonce in self.seen or len(self.seen) > 10000:
                return False
            self.seen[nonce] = now + self.ttl
            return True


NONCES = NonceCache()


def verify_request(headers, method, path, body, device_id, public_key, nonces=NONCES, now=None):
    """None if the request is Alpium's, else the reason it is not."""
    from cryptography.exceptions import InvalidSignature
    now = time.time() if now is None else now
    station = headers.get("X-Alpium-Station")
    ts = headers.get("X-Alpium-Timestamp", "")
    nonce = headers.get("X-Alpium-Nonce", "")
    sig = headers.get("X-Alpium-Signature", "")
    if not (station and ts and nonce and sig):
        return "unsigned"
    if station != device_id:
        return "not for this station"
    if not ts.isdigit() or abs(now - int(ts)) > CLOCK_WINDOW:
        return "timestamp outside the window (check the station clock)"
    if not NONCE_RE.match(nonce):
        return "bad nonce"
    try:
        signature = base64.b64decode(sig, validate=True)
        public_key.verify(signature, canonical_request(device_id, method, path, int(ts), nonce, body))
    except (InvalidSignature, ValueError):
        return "bad signature"
    # Only a VALID request spends its nonce, so a forger cannot burn Alpium's.
    if not nonces.use(nonce, now):
        return "replayed"
    return None


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------

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


def heartbeat_body():
    """What a heartbeat says: the fields Alpium's StationHeartbeat accepts."""
    config = read_config()
    status = station_status()
    body = {
        "agent_version": AGENT_VERSION,
        "station_time": status["timestamp"],
        "callsign": config["call"] if CALLSIGN_RE.match(str(config["call"])) else None,
        "vpn_ip": status["vpn_ip"],
        "latitude": config["latitude"],
        "longitude": config["longitude"],
        "altitude": config["altitude"],
        "ogn_rf_running": status["ogn_rf_running"],
        "ogn_decode_running": status["ogn_decode_running"],
        "cpu_temp": status["cpu_temp"],
        "disk_usage_percent": status["disk_usage_percent"],
        "memory_usage_percent": status["memory_usage_percent"],
        "uptime_seconds": status["uptime"],
    }
    update = (update_info().get("state") or {})
    if update.get("state") in ("queued", "running", "done", "failed"):
        body["update"] = {"state": update["state"], "version": update.get("version"),
                          "error": (update.get("error") or None) and str(update["error"])[:300]}
    return body


def send_heartbeat(creds):
    import requests
    headers = {"Authorization": f"Bearer {creds['api_key']}"}
    if creds.get("cf_access_client_id") and creds.get("cf_access_client_secret"):
        headers["CF-Access-Client-Id"] = creds["cf_access_client_id"]
        headers["CF-Access-Client-Secret"] = creds["cf_access_client_secret"]
    url = f"{creds['server_url'].rstrip('/')}/ogn-stations/heartbeat"
    r = requests.post(url, headers=headers, json=heartbeat_body(), timeout=15)
    record(r.status_code, r.text)
    if r.status_code == 200:
        heartbeat_state["last_ok"] = datetime.now(timezone.utc).isoformat()
        heartbeat_state["last_error"] = None
        try:
            answer = r.json()
            heartbeat_state["registry_callsign"] = answer.get("callsign")
            heartbeat_state["server_time"] = answer.get("server_time")
        except ValueError:
            pass
    else:
        heartbeat_state["last_error"] = f"{r.status_code} {r.text[:200]}"
        print(f"Heartbeat refused: {r.status_code} {r.text[:200]}", flush=True)


def heartbeat_loop():
    """Forever: a station that stops beating is reported by Alpium in 30 min.
    Every exception is caught here, so the loop itself never dies (the old
    agent's did, and HfssHq went silent for five months)."""
    while True:
        interval = DEFAULT_HEARTBEAT_INTERVAL
        try:
            creds = load_credentials()
            if creds:
                interval = int(creds.get("heartbeat_interval") or DEFAULT_HEARTBEAT_INTERVAL)
                send_heartbeat(creds)
        except Exception as e:
            heartbeat_state["last_error"] = str(e)[:300]
            record(0, str(e))
            print(f"Heartbeat error: {e}", flush=True)
        time.sleep(max(60, interval))


# ---------------------------------------------------------------------------
# Control API
# ---------------------------------------------------------------------------
# Each handler takes the parsed JSON body and returns (HTTP status, dict).

def h_health(_body):
    creds = load_credentials()
    return 200, {"status": "ok", "agent_version": AGENT_VERSION, "serial": get_serial(),
                 "enrolled": bool(creds), "device_id": creds["device_id"] if creds else None}


def h_status(_body):
    creds = load_credentials()
    return 200, {
        "agent_version": AGENT_VERSION,
        "serial": get_serial(),
        "device_id": creds["device_id"] if creds else None,
        "server_url": creds.get("server_url") if creds else None,
        "station_time": datetime.now(timezone.utc).isoformat(),
        "heartbeat": dict(heartbeat_state),
        "system": station_status(),
        "config": read_config(),
        "interfaces": {n: interface_state(n) for n in ("eth0", "eth1", "wlan0")},
        "wifi": helper("wifi-list"),
        "update": update_info(),
    }


def update_info():
    """The last signed-release update: state written by the root helper's
    job, and the tail of its log (both world-readable, written only by root)."""
    try:
        with open(UPDATE_STATE) as f:
            state = json.load(f)
    except (OSError, ValueError):
        state = None
    try:
        with open(UPDATE_LOG, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 8192))
            tail = f.read().decode("utf-8", "replace").splitlines()[-40:]
    except OSError:
        tail = []
    return {"state": state, "log": tail}


def h_update(body):
    # Only passes the release on: the root helper verifies the release key's
    # signature and the version, and installs in a job of its own.
    manifest, signature = body.get("manifest"), body.get("signature")
    if not isinstance(manifest, str) or not isinstance(signature, str):
        return 400, {"success": False, "message": "manifest and signature required"}
    r = helper("update", stdin={"manifest": manifest, "signature": signature})
    return (202 if r.get("success") else 400), r


def h_config(body):
    cfg, error = validated_config(body)
    if error:
        return 400, {"success": False, "message": error}
    try:
        write_config(cfg)
    except OSError as e:
        return 500, {"success": False, "message": f"Could not write the configuration: {e}"}
    r = helper("restart-ogn")
    if not r.get("success"):
        return 500, r
    return 200, {"success": True, "message": "Configuration saved, receiver restarted", "config": read_config()}


def h_restart(_body):
    r = helper("restart-ogn")
    return (200 if r.get("success") else 500), r


def h_link(body):
    r = helper("link", str(body.get("interface", "")), str(body.get("action", "")))
    return (200 if r.get("success") else 400), r


def h_wifi_add(body):
    r = helper("wifi-add", stdin={"ssid": body.get("ssid"), "psk": body.get("psk"), "priority": body.get("priority", 1)})
    return (200 if r.get("success") else 400), r


def h_wifi_psk(body):
    r = helper("wifi-set-psk", stdin={"name": body.get("name"), "psk": body.get("psk")})
    return (200 if r.get("success") else 400), r


def h_wifi_delete(body):
    r = helper("wifi-delete", str(body.get("name", "")))
    return (200 if r.get("success") else 400), r


def h_heartbeat_log(_body):
    with _history_lock:
        return 200, {"logs": list(heartbeat_history)}


def h_ogn_page(port):
    def handler(_body):
        # ogn-rf / ogn-decode serve these on localhost; the firewall closes
        # them to the tailnet, so this relay is the only way to see them.
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as r:
                raw = r.read(OGN_PAGE_MAX + 1)
        except Exception as e:
            return 503, {"success": False, "message": f"OGN page not available: {e}"}
        return 200, {"html": raw[:OGN_PAGE_MAX].decode("utf-8", "replace"), "truncated": len(raw) > OGN_PAGE_MAX}
    return handler


ROUTES = {
    ("GET", "/v1/health"): h_health,
    ("GET", "/v1/status"): h_status,
    ("PUT", "/v1/config"): h_config,
    ("POST", "/v1/receiver/restart"): h_restart,
    ("POST", "/v1/link"): h_link,
    ("POST", "/v1/wifi/add"): h_wifi_add,
    ("POST", "/v1/wifi/psk"): h_wifi_psk,
    ("POST", "/v1/wifi/delete"): h_wifi_delete,
    ("GET", "/v1/heartbeat-log"): h_heartbeat_log,
    ("POST", "/v1/update"): h_update,
    ("GET", "/v1/ogn/rf"): h_ogn_page(OGN_PAGES["rf"]),
    ("GET", "/v1/ogn/decode"): h_ogn_page(OGN_PAGES["decode"]),
}


def client_allowed(addr):
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_loopback or (ip.version == 4 and ip in TAILNET)


def is_loopback(addr):
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_loopback


class Handler(BaseHTTPRequestHandler):
    server_version = "alpium-ogn-station"
    sys_version = ""
    protocol_version = "HTTP/1.1"
    timeout = 20  # per-connection socket timeout: a slow client is dropped

    def log_message(self, fmt, *args):
        print("%s %s" % (self.client_address[0], fmt % args), flush=True)

    def reply(self, status, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def handle_any(self, method):
        addr = self.client_address[0]
        if not client_allowed(addr):
            return self.reply(403, {"success": False, "message": "forbidden"})
        path = self.path
        handler = ROUTES.get((method, path))
        if handler is None:
            return self.reply(404, {"success": False, "message": "no such endpoint"})

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self.reply(400, {"success": False, "message": "bad Content-Length"})
        if length < 0 or length > MAX_BODY:
            return self.reply(413, {"success": False, "message": "body too large"})
        raw = self.rfile.read(length) if length else b""

        if not (method == "GET" and path == "/v1/health" and is_loopback(addr)):
            creds = load_credentials()
            line = control_public_key_line(creds)
            if not creds or not line:
                return self.reply(503, {"success": False, "message": "station not enrolled"})
            try:
                key = load_public_key(line)
            except Exception:
                return self.reply(503, {"success": False, "message": "control key unreadable"})
            reason = verify_request(self.headers, method, path, raw, creds["device_id"], key)
            if reason:
                print(f"Refused {method} {path} from {addr}: {reason}", flush=True)
                return self.reply(401, {"success": False, "message": reason,
                                        "station_time": int(time.time())})

        body = {}
        if raw:
            if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
                return self.reply(415, {"success": False, "message": "JSON only"})
            try:
                body = json.loads(raw)
            except ValueError:
                return self.reply(400, {"success": False, "message": "invalid JSON"})
            if not isinstance(body, dict):
                return self.reply(400, {"success": False, "message": "expected a JSON object"})
        try:
            status, data = handler(body)
        except Exception as e:
            print(f"Handler error on {method} {path}: {e}", flush=True)
            status, data = 500, {"success": False, "message": "internal error"}
        return self.reply(status, data)

    def do_GET(self):
        self.handle_any("GET")

    def do_POST(self):
        self.handle_any("POST")

    def do_PUT(self):
        self.handle_any("PUT")

    def do_DELETE(self):
        self.reply(405, {"success": False, "message": "method not allowed"})

    do_PATCH = do_HEAD = do_OPTIONS = do_DELETE


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 16


def main():
    load_history()
    threading.Thread(target=heartbeat_loop, daemon=True).start()
    Server(("0.0.0.0", LISTEN_PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
