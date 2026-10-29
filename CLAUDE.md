# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an OGN (Open Glider Network) receiver setup repository for Raspberry Pi, designed to receive FLARM aircraft tracking signals using RTL-SDR hardware. The system consists of two main components working together via a FIFO pipe:
- **ogn-rf**: Receives and demodulates RF signals from RTL-SDR dongle
- **ogn-decode**: Decodes OGN/FLARM packets and forwards to APRS network

## Architecture

The system operates as a pipeline:
1. RTL-SDR dongle captures RF signals at 868 MHz (EU) or 915 MHz (US/Canada)
2. `ogn-rf` demodulates signals and outputs to `ogn-rf.fifo`
3. `ogn-decode` reads from FIFO, decodes aircraft data, and transmits to APRS server
4. Data appears on live.glidernet.org map after 10-15 minutes

Both processes run as systemd services and communicate via named pipe.

## Key Configuration

**Template.conf** contains all receiver settings:
- `RF.FreqCorr`: Frequency correction in PPM (calibrate with gsm_scan)
- `RF.OGN.CenterFreq`: 868.2 (EU), 868.4 (alternate), 915.0 (US/Canada)
- `RF.OGN.Gain`: RF gain setting (typically 40.0)
- `Position`: Station coordinates (latitude/longitude/altitude in meters)
- `APRS.Call`: Station callsign (max 9 chars)
- `APRS.Server`: aprs.glidernet.org:14580
- `APRS.Pass`: APRS passcode from https://apps.magicbug.co.uk/passcode/
- `HTTP.Port`: Web interface port (default 8080)

## Installation and fleet operation

`sudo ./install.sh --code <enrollment code>` on Raspberry Pi OS Trixie (or
Bookworm, to convert a station in the field). It
installs OGN 0.3.3 from VirusPilot/ogn-pi34 at a PINNED commit with sha256
checks (never an unpinned clone: upstream's script is interactive and assumes
/home/pi), runs everything as systemd services under the `hfss` user, and
enrolls the station with Alpium. See PRODUCTION-DEPLOYMENT.md, and
docs/OGN_STATIONS.md in the Alpium repo for the server side.

Rules that keep a fleet safe (do not undo them):

- **No shared secret on a Pi.** Enrollment exchanges a one-time code for this
  station's own credentials and a single-use `tag:ogn` Tailscale key. The old
  `.env` (manufacturer secret, reusable Tailscale key) is gone; the installer
  shreds it.
- **No web pages. Alpium is the interface.** `ogn-station-agent.py` is a JSON
  control API on :8082 (standard library + `cryptography`, no web framework).
  Every request must be signed by Alpium's Ed25519 station key; the public
  half (`control_public_key`) arrives at enrollment. `canonical_request` must
  stay byte-identical to `app/services/ogn_station_control.py` in Alpium (60 s
  window, single-use nonce, device id and body hash bound). The only unsigned
  call is `GET /v1/health` from loopback. Do not add an HTML page or an
  unsigned endpoint.
- **Tailnet only.** `system/firewall.nft` admits 22 and 8082 from the tailnet
  and nothing else (OGN's 8080/8081 and procServ are local; the agent relays
  the status pages), plus Tailscale's UDP port and (optionally) LAN SSH; the
  agent refuses non-tailnet clients too.
- **Least privilege.** The agent runs as hfss; its only root path is
  `system/alpium-ogn-helper` through `/etc/sudoers.d/alpium-ogn`, and the
  helper validates every argument. Wi-Fi passwords go into NetworkManager
  keyfiles (0600), never onto a command line.
- OGN status pages are on 8080/8081 (upstream 0.3.3 defaults to 8082/8083,
  which would collide with the agent).
- **Updates are signed releases.** `tools/make-release.py` signs
  `manifest.json` with the OFFLINE release key; `system/alpium-ogn-helper
  update` (root) verifies it against `/etc/alpium-ogn/release.pub`, refuses a
  version not newer than `/etc/alpium-ogn/version` and a URL outside this
  repo's releases, and installs in the transient unit `alpium-ogn-update`.
  Never let the agent, Alpium or anything unsigned trigger an install. Bump
  `AGENT_VERSION` for every release; `install.sh` must keep working with no
  options, since that is how an update runs it.
- **Identity is Alpium's.** The station id, tailnet name and callsign come
  from Alpium at enrollment (the installer sends the Pi's full serial and
  model, and writes back the callsign it is given). Never derive a callsign
  on the station or change it locally; Alpium changes it through the signed
  config call.
- **Heartbeats go to `/ogn-stations/heartbeat`, never `/gps/`.** The body is
  Alpium's `StationHeartbeat` (app/services/ogn_station_heartbeat.py), which
  refuses unknown keys: add a field on the Alpium side first, then here.
- **First boot claims, never a secret on the card.** Without credentials the
  agent claims (`/ogn-stations/claim`, signed with its own key in
  `~/.ogn_claim_key`) until an admin approves its serial; `canonical claim`
  must match Alpium's `ogn_station_claim.canonical_claim`. `install.sh --image`
  must stay chroot-safe (no serial, no systemd, no host keys): guard anything
  live with `LIVE`.
