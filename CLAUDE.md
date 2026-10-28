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

`sudo ./install.sh --code <enrollment code>` on Raspberry Pi OS Trixie. It
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
- **Tailnet only.** `system/firewall.nft` drops everything inbound except the
  tailnet, Tailscale's UDP port and (optionally) SSH; the agent refuses
  non-tailnet clients too and refuses non-JSON POSTs (cross-site forms).
- **Least privilege.** The agent runs as hfss; its only root path is
  `system/alpium-ogn-helper` through `/etc/sudoers.d/alpium-ogn`, and the
  helper validates every argument. Wi-Fi passwords go into NetworkManager
  keyfiles (0600), never onto a command line.
- **The UI has no inline script and uses relative URLs.** Alpium serves it
  through a sandboxed proxy under `script-src 'self'`; an inline script or an
  absolute `/api/...` URL silently breaks it there.
- OGN status pages are on 8080/8081 (upstream 0.3.3 defaults to 8082/8083,
  which would collide with the agent).
