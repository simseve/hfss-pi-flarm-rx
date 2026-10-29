#!/usr/bin/env bash
# Install, enroll or update an Alpium OGN station on a Raspberry Pi.
#
#   sudo ./install.sh --code OGN-XXXX-XXXX-XXXX-XXXX \
#        --callsign MYSITE --lat 46.0123 --lon 8.9123 --alt 1250
#
# Fresh Pi: installs the OGN receiver (pinned, checksummed), the Alpium
# station agent as a systemd service, the firewall, SSH hardening, and enrolls
# the station: the code (from an Alpium admin, /admin/ogn-stations) is
# exchanged for this station's own credentials and a single-use Tailscale key.
# No shared secret ever lands on the Pi.
#
# Already enrolled: run without --code to update the agent, units and firewall
# in place; with --code to re-enroll (new credentials, new tailnet node).
#
# Options:
#   --code CODE            enrollment code (or env OGN_ENROLL_CODE)
#   --callsign CALL        OGN receiver name, 3-9 letters/digits
#   --lat/--lon/--alt N    antenna position (degrees, metres AMSL)
#   --name NAME            station name shown in Alpium (default: callsign)
#   --enroll-url URL       default https://app.alpium.io/api/v1/ogn-stations/enroll
#   --no-lan-ssh           also close SSH on the local network (tailnet only)
#   --keep-ssh-passwords   do not switch sshd to keys only
#   --skip-ogn             do not (re)install the OGN receiver binaries
#
# Supported: Raspberry Pi OS based on Debian 13 (Trixie) or 12 (Bookworm),
# 32 or 64 bit.
set -euo pipefail

AGENT_USER=hfss
AGENT_HOME=/home/$AGENT_USER
TARGET=$AGENT_HOME/hfss-pi-flarm-rx
ENROLL_URL=https://app.alpium.io/api/v1/ogn-stations/enroll

# OGN receiver binaries: VirusPilot/ogn-pi34 at a pinned commit, each file
# checked against its sha256 before use. Change all four together.
OGN_PI34_COMMIT=223d78c80526d23cae05edb4ba07e99b146a0d96
OGN_SHA_ARM64=52061e5dff1aa3d7ce6e1de041d36e19d6d768c47ea358932846e552b867a8bb
OGN_SHA_ARM=50be39c69c7a368c53d715fcb09b9e1e3dbfee78791a579a95389e1997d2003f
OGN_SHA_EGM=9dcaf4efd6857aaa2e1e2e2c574d3f5264eacf47024cdcd5291c40ddad5e5acc

CODE=${OGN_ENROLL_CODE:-}
CALLSIGN="" LAT="" LON="" ALT="" NAME=""
LAN_SSH=1 HARDEN_SSH=1 SKIP_OGN=0

die() { echo "ERROR: $*" >&2; exit 1; }
step() { echo; echo "== $*"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --code) CODE=$2; shift 2 ;;
    --callsign) CALLSIGN=$2; shift 2 ;;
    --lat) LAT=$2; shift 2 ;;
    --lon) LON=$2; shift 2 ;;
    --alt) ALT=$2; shift 2 ;;
    --name) NAME=$2; shift 2 ;;
    --enroll-url) ENROLL_URL=$2; shift 2 ;;
    --no-lan-ssh) LAN_SSH=0; shift ;;
    --keep-ssh-passwords) HARDEN_SSH=0; shift ;;
    --skip-ogn) SKIP_OGN=1; shift ;;
    -h|--help) sed -n '2,32p' "$0"; exit 0 ;;
    *) die "unknown option $1 (see --help)" ;;
  esac
done

[ "$(id -u)" -eq 0 ] || die "run with sudo"
SRC=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
SERIAL=$(awk -F': ' '/^Serial/{print tolower($2)}' /proc/cpuinfo | tail -c 9 | tr -d '\n')
[[ "$SERIAL" =~ ^[0-9a-f]{8}$ ]] || die "cannot read the Raspberry Pi serial from /proc/cpuinfo"
# shellcheck source=/dev/null
DIST=$(. /etc/os-release && echo "${VERSION_ID:-}")
# Trixie for new stations; Bookworm so a station already in the field can be
# converted in place, without a site visit to reflash it.
case "$DIST" in
  13|12) ;;
  *) die "needs Raspberry Pi OS based on Debian 13 (Trixie) or 12 (Bookworm); this is Debian ${DIST:-unknown}" ;;
esac
BITS=$(getconf LONG_BIT)
CREDS=$AGENT_HOME/.ogn_credentials.json
if [ -z "$CODE" ] && [ ! -s "$CREDS" ]; then
  [ -t 0 ] || die "not enrolled yet: pass --code"
  read -r -p "Enrollment code from an Alpium admin: " CODE
fi
if [ -n "$CALLSIGN" ] && ! [[ "$CALLSIGN" =~ ^[A-Za-z0-9]{3,9}$ ]]; then
  die "callsign must be 3-9 letters or digits"
fi
echo "Station serial $SERIAL, Debian $DIST, ${BITS}-bit"

# ---------------------------------------------------------------------------
step "1/9 Packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q librtlsdr0 rtl-sdr libfftw3-bin libusb-1.0-0 procserv \
  chrony curl ca-certificates git python3 python3-cryptography python3-requests \
  nftables network-manager sudo openssh-server
echo 'blacklist dvb_usb_rtl28xxu' > /etc/modprobe.d/blacklist-dvb_usb_rtl28xxu.conf

# ---------------------------------------------------------------------------
step "2/9 Agent user and code"
if ! id "$AGENT_USER" >/dev/null 2>&1; then
  adduser --disabled-password --gecos "Alpium OGN station" "$AGENT_USER"
fi
usermod -aG plugdev "$AGENT_USER"
if [ "$SRC" != "$TARGET" ]; then
  mkdir -p "$TARGET"
  cp -a "$SRC/." "$TARGET/"
fi
chown -R "$AGENT_USER:$AGENT_USER" "$TARGET"
# The old provisioning wrote the fleet's shared secrets here. Nothing reads
# them any more; they must not stay on a device in the field.
for old in "$TARGET/.env" "$SRC/.env"; do
  [ -f "$old" ] && shred -u "$old" && echo "   removed old shared-secret file $old"
done
# The old agent served a web UI on :8082 with no authentication, as root, and
# the old ogn-pi34 install ran its own ogn-rf/ogn-decode units, which would
# fight rtlsdr-ogn for the dongle. Whatever started them at boot goes.
for unit in /etc/systemd/system/*.service; do
  [ -f "$unit" ] || continue
  case "$(basename "$unit")" in rtlsdr-ogn.service|alpium-ogn-*.service) continue ;; esac
  if grep -qE "ogn-config-web-alpium|ogn-pi34" "$unit"; then
    systemctl disable --now "$(basename "$unit")" 2>/dev/null || true
    rm -f "$unit"
    echo "   removed old unit $(basename "$unit")"
  fi
done
for u in root "$AGENT_USER" pi; do
  if crontab -u "$u" -l 2>/dev/null | grep -q "ogn-config-web-alpium"; then
    crontab -u "$u" -l | grep -v "ogn-config-web-alpium" | crontab -u "$u" -
    echo "   removed old @reboot entry from $u's crontab"
  fi
done
[ -f /etc/rc.local ] && sed -i '/ogn-config-web-alpium/d' /etc/rc.local
pkill -f "ogn-config-web-alpium.py" 2>/dev/null || true
# The old LSB rtlsdr-ogn script started ogn-rf/ogn-decode under procServ from
# ~/ogn-pi34. Stop it while its script still exists, then make sure nothing of
# it is left holding the dongle or ports 50000/50001/8080/8081.
systemctl stop rtlsdr-ogn 2>/dev/null || true
pkill -f "procServ.*ogn-(rf|decode)" 2>/dev/null || true
pkill -x ogn-rf 2>/dev/null || true
pkill -x ogn-decode 2>/dev/null || true
systemctl daemon-reload
rm -f "$TARGET/ogn-config-web-alpium.py"; rm -rf "$TARGET/static"

# ---------------------------------------------------------------------------
step "3/9 OGN receiver"
if [ "$SKIP_OGN" -eq 1 ] && [ -x "$AGENT_HOME/rtlsdr-ogn/ogn-rf" ]; then
  echo "   skipped (--skip-ogn)"
else
  case "$BITS" in
    64) TGZ=rtlsdr-ogn-bin-arm64-0.3.3.tgz; SHA=$OGN_SHA_ARM64 ;;
    32) TGZ=rtlsdr-ogn-bin-ARM-0.3.3.tgz; SHA=$OGN_SHA_ARM ;;
    *) die "unsupported architecture" ;;
  esac
  BASE=https://raw.githubusercontent.com/VirusPilot/ogn-pi34/$OGN_PI34_COMMIT
  TMP=$(mktemp -d)
  curl -fsSL "$BASE/$TGZ" -o "$TMP/ogn.tgz"
  curl -fsSL "$BASE/WW15MGH.DAC" -o "$TMP/WW15MGH.DAC"
  echo "$SHA  $TMP/ogn.tgz" | sha256sum -c --quiet || die "OGN binaries failed their checksum"
  echo "$OGN_SHA_EGM  $TMP/WW15MGH.DAC" | sha256sum -c --quiet || die "EGM grid failed its checksum"
  systemctl stop rtlsdr-ogn 2>/dev/null || true
  # The tarball carries upstream's Template.conf: keep this station's own.
  # A station from the old ogn-pi34 layout keeps its settings too (its
  # FreqCorr is a calibration of THIS dongle; losing it costs reception).
  OLD_CONF=""
  for c in "$AGENT_HOME/rtlsdr-ogn/Template.conf" "$AGENT_HOME"/ogn-pi34/rtlsdr-ogn*/Template.conf; do
    [ -f "$c" ] && { OLD_CONF=$c; break; }
  done
  if [ -n "$OLD_CONF" ]; then
    cp -p "$OLD_CONF" "$TMP/Template.conf.keep"
    echo "   keeping receiver settings from $OLD_CONF"
  fi
  tar xzf "$TMP/ogn.tgz" -C "$AGENT_HOME"
  if [ -f "$TMP/Template.conf.keep" ]; then
    cp -p "$TMP/Template.conf.keep" "$AGENT_HOME/rtlsdr-ogn/Template.conf"
  else
    # Fresh install: start from the agent's defaults (FreqCorr 0, right for
    # TCXO dongles), not the tarball's example (FreqCorr +50).
    rm -f "$AGENT_HOME/rtlsdr-ogn/Template.conf"
  fi
  cp "$TMP/WW15MGH.DAC" "$AGENT_HOME/rtlsdr-ogn/WW15MGH.DAC"
  rm -rf "$TMP"
  sed -e "s#/home/pi#$AGENT_HOME#g" -e "s#\bpi\b#$AGENT_USER#" \
    "$AGENT_HOME/rtlsdr-ogn/rtlsdr-ogn.conf" > /etc/rtlsdr-ogn.conf
  chown -R "$AGENT_USER:$AGENT_USER" "$AGENT_HOME"/rtlsdr-ogn*
fi
# The receiver config: written from the template on first install, then
# owned by the station UI. Position and callsign from the command line win.
CONF=$AGENT_HOME/rtlsdr-ogn/Template.conf
if [ ! -f "$CONF" ] || ! grep -q "Alpium station agent" "$CONF" || [ -n "$CALLSIGN$LAT$LON$ALT" ]; then
  sudo -u "$AGENT_USER" python3 - "$TARGET" "$CONF" "${CALLSIGN}" "${LAT}" "${LON}" "${ALT}" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
import importlib.util
spec = importlib.util.spec_from_file_location("agent", sys.argv[1] + "/ogn-station-agent.py")
agent = importlib.util.module_from_spec(spec); spec.loader.exec_module(agent)
agent.CONFIG_FILE = sys.argv[2]
cfg = agent.read_config()
for key, value in zip(("call", "latitude", "longitude", "altitude"), sys.argv[3:7]):
    if value:
        cfg[key] = value
if cfg["call"] == "NOCALL":
    cfg["call"] = "OGN" + agent.get_serial()[-6:].upper()
cfg, error = agent.validated_config(cfg)
if error:
    sys.exit("Receiver configuration: " + error)
agent.write_config(cfg)
print("   receiver configured as", cfg["call"], cfg["latitude"], cfg["longitude"], cfg["altitude"])
PY
fi
install -m 0644 "$TARGET/system/rtlsdr-ogn.service" /etc/systemd/system/rtlsdr-ogn.service
rm -f /etc/init.d/rtlsdr-ogn

# ---------------------------------------------------------------------------
step "4/9 Root helper"
install -o root -g root -m 0755 "$TARGET/system/alpium-ogn-helper" /usr/local/sbin/alpium-ogn-helper
install -o root -g root -m 0440 "$TARGET/system/sudoers-alpium-ogn" /etc/sudoers.d/alpium-ogn.new
visudo -cf /etc/sudoers.d/alpium-ogn.new >/dev/null || { rm -f /etc/sudoers.d/alpium-ogn.new; die "sudoers rule invalid"; }
mv /etc/sudoers.d/alpium-ogn.new /etc/sudoers.d/alpium-ogn

# ---------------------------------------------------------------------------
step "5/9 Tailscale"
if ! command -v tailscale >/dev/null 2>&1; then
  curl -fsSL https://tailscale.com/install.sh | sh
fi
systemctl enable --now tailscaled

# ---------------------------------------------------------------------------
TS_KEY="" SSH_KEY=""
if [ -n "$CODE" ]; then
  step "6/9 Enrollment"
  CALL_NOW=$(awk -F'"' '/Call *=/{print $2; exit}' "$CONF")
  BODY=$(python3 - "$CODE" "$SERIAL" "${NAME:-$CALL_NOW}" "$CALL_NOW" "$CONF" "$TARGET" <<'PY'
import json, re, sys
code, serial, name, call, conf, target = sys.argv[1:7]
text = open(conf).read()
def num(key):
    m = re.search(key + r"\s*=\s*([+\d.-]+)", text)
    return float(m.group(1)) if m else None
version = re.search(r'AGENT_VERSION = "([^"]+)"', open(target + "/ogn-station-agent.py").read())
print(json.dumps({"code": code, "serial": serial, "name": name or None, "callsign": call or None,
                  "latitude": num("Latitude"), "longitude": num("Longitude"), "altitude": num("Altitude"),
                  "agent_version": version.group(1) if version else None}))
PY
)
  RESP=$(mktemp)
  HTTP=$(curl -sS -o "$RESP" -w '%{http_code}' -H 'Content-Type: application/json' \
         --data-binary @- "$ENROLL_URL" <<<"$BODY") || HTTP=000
  if [ "$HTTP" != "200" ]; then
    echo "   Alpium answered $HTTP: $(head -c 300 "$RESP")"; rm -f "$RESP"
    die "enrollment failed"
  fi
  # Station credentials to a 0600 file owned by the agent; the Tailscale key
  # and the server's SSH key are used below and never stored.
  eval "$(python3 - "$RESP" "$CREDS" <<'PY'
import json, os, shlex, sys
r = json.load(open(sys.argv[1]))
keep = {k: r.get(k) for k in ("device_id", "api_key", "mqtt_username", "mqtt_password", "server_url",
                              "heartbeat_interval", "cf_access_client_id", "cf_access_client_secret")}
# Alpium's public key: every control request must be signed with its pair.
keep["control_public_key"] = r.get("control_public_key") or r["ssh_public_key"]
fd = os.open(sys.argv[2] + ".new", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f:
    json.dump(keep, f, indent=2)
os.replace(sys.argv[2] + ".new", sys.argv[2])
print("TS_KEY=" + shlex.quote(r["tailscale_authkey"]))
print("TS_HOST=" + shlex.quote(r["tailscale_hostname"]))
print("TS_TAG=" + shlex.quote(r["tailscale_tag"]))
print("SSH_KEY=" + shlex.quote(r["ssh_public_key"]))
print("DEVICE_ID=" + shlex.quote(r["device_id"]))
PY
)"
  shred -u "$RESP"
  chown "$AGENT_USER:$AGENT_USER" "$CREDS"
  echo "   enrolled as $DEVICE_ID"

  tailscale logout >/dev/null 2>&1 || true
  tailscale up --reset --auth-key="$TS_KEY" --hostname="$TS_HOST" \
    --advertise-tags="$TS_TAG" --ssh=false --accept-dns=false --accept-routes=false
  unset TS_KEY
  echo "   on the tailnet as $TS_HOST ($(tailscale ip -4 | head -1))"
else
  step "6/9 Enrollment: already enrolled ($(python3 -c "import json;print(json.load(open('$CREDS'))['device_id'])")), skipped"
fi

# ---------------------------------------------------------------------------
step "7/9 SSH"
install -d -o "$AGENT_USER" -g "$AGENT_USER" -m 0700 "$AGENT_HOME/.ssh"
AUTH=$AGENT_HOME/.ssh/authorized_keys
touch "$AUTH"
if [ -n "$SSH_KEY" ]; then
  # Alpium's key, usable from the tailnet only and for a shell only.
  grep -v ' alpium-ogn$' "$AUTH" > "$AUTH.new" || true
  echo "from=\"100.64.0.0/10\",no-agent-forwarding,no-port-forwarding,no-X11-forwarding $SSH_KEY" >> "$AUTH.new"
  mv "$AUTH.new" "$AUTH"
fi
chown "$AGENT_USER:$AGENT_USER" "$AUTH"; chmod 0600 "$AUTH"
if [ "$HARDEN_SSH" -eq 1 ]; then
  if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "$AGENT_USER" ] && \
     [ ! -s "$(getent passwd "$SUDO_USER" | cut -d: -f6)/.ssh/authorized_keys" ]; then
    echo "   NOTE: $SUDO_USER has no SSH key. With passwords off, on-site SSH needs a key"
    echo "         (or the keyboard). Re-run with --keep-ssh-passwords to keep them."
  fi
  install -m 0644 "$TARGET/system/sshd-alpium-ogn.conf" /etc/ssh/sshd_config.d/10-alpium-ogn.conf
else
  rm -f /etc/ssh/sshd_config.d/10-alpium-ogn.conf
fi
sshd -t || { rm -f /etc/ssh/sshd_config.d/10-alpium-ogn.conf; die "sshd config invalid; left unchanged"; }
systemctl reload ssh 2>/dev/null || systemctl reload sshd

# ---------------------------------------------------------------------------
step "8/9 Firewall"
install -d -m 0755 /etc/alpium-ogn
if [ "$LAN_SSH" -eq 1 ]; then
  install -m 0644 "$TARGET/system/firewall.nft" /etc/alpium-ogn/firewall.nft
else
  grep -v 'comment "lan-ssh"' "$TARGET/system/firewall.nft" > /etc/alpium-ogn/firewall.nft
fi
nft -c -f /etc/alpium-ogn/firewall.nft || die "firewall rules invalid"
install -m 0644 "$TARGET/system/alpium-ogn-firewall.service" /etc/systemd/system/alpium-ogn-firewall.service

# ---------------------------------------------------------------------------
step "9/9 Services"
install -m 0644 "$TARGET/system/alpium-ogn-station.service" /etc/systemd/system/alpium-ogn-station.service
systemctl daemon-reload
systemctl enable alpium-ogn-firewall rtlsdr-ogn alpium-ogn-station
systemctl restart alpium-ogn-firewall
systemctl restart rtlsdr-ogn
systemctl restart alpium-ogn-station

sleep 5
echo
for s in alpium-ogn-firewall rtlsdr-ogn alpium-ogn-station tailscaled; do
  printf '   %-22s %s\n' "$s" "$(systemctl is-active "$s" || true)"
done
if curl -fsS http://127.0.0.1:8082/v1/health >/dev/null; then
  echo "   station agent answers on :8082 (signed control API, no web pages)"
else
  echo "   WARNING: station agent not answering yet; see: journalctl -u alpium-ogn-station"
fi
echo
echo "Done. The station appears in Alpium (/admin/ogn-stations) within 5 minutes."
