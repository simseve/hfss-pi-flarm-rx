# Alpium OGN station (Raspberry Pi)

An Open Glider Network receiver (RTL-SDR dongle + 868 MHz antenna) that also
reports to Alpium and is managed from Alpium's console over Tailscale. The
station serves no web pages: Alpium is its interface, and it accepts commands
only when they are signed by Alpium.

```bash
sudo apt-get install -y git
sudo git clone https://github.com/simseve/hfss-pi-flarm-rx /home/hfss/hfss-pi-flarm-rx
cd /home/hfss/hfss-pi-flarm-rx
sudo ./install.sh --code OGN-XXXX-XXXX-XXXX-XXXX --callsign MYSITE --lat 46.01 --lon 8.91 --alt 1250
```

The code comes from an Alpium admin (`/admin/ogn-stations`, *Enroll new
stations*). Needs Raspberry Pi OS Lite based on Debian 13 (Trixie); Debian 12
(Bookworm) is accepted so a station already in the field converts in place.

Everything else, from the Tailscale policy to retiring a lost station, is in
[PRODUCTION-DEPLOYMENT.md](PRODUCTION-DEPLOYMENT.md).

## Layout

| Path | What |
|---|---|
| `install.sh` | install / enroll / update (idempotent) |
| `ogn-station-agent.py` | station agent: heartbeat + signed JSON control API on :8082 (tailnet only, no pages) |
| `ogn/Template.conf.in` | receiver config template (OGN 0.3.3) |
| `system/` | systemd units, root helper, sudoers rule, firewall, sshd drop-in |

OGN binaries come from [VirusPilot/ogn-pi34](https://github.com/VirusPilot/ogn-pi34)
at a pinned commit, verified by sha256 in `install.sh`.
