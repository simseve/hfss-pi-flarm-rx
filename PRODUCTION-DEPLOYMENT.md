# Running a fleet of Alpium OGN stations

How to install, enroll, operate and retire hundreds of Raspberry Pi OGN
receivers, each reachable by Alpium over Tailscale and by nothing else. The
server side is documented in the Alpium repo, `docs/OGN_STATIONS.md`.

## The model

- **No shared secrets on a Pi.** A station joins with an **enrollment code**
  an Alpium admin creates. Alpium answers with credentials that belong to this
  station alone and a **single-use, pre-authorised Tailscale key** tagged
  `tag:ogn`. Losing one Pi loses one station's credentials, which an admin
  revokes with one click (Retire).
- **No web pages; Alpium is the interface.** The station runs a small JSON
  control API (8082) whose only client is Alpium's server, and every request
  must be signed with Alpium's station key (the station received the public
  half at enrollment). Being on the tailnet is not enough to command it.
  Admins manage stations in Alpium (`/admin/ogn-stations`, *Manage*): status,
  receiver settings, network and Wi-Fi, the OGN status pages, the heartbeat
  log, and an SSH shell.
- **Reachable over the tailnet only.** From the tailnet only 22 and 8082 are
  open; the OGN status pages (8080/8081) and procServ (50000/50001) are local
  and the agent relays the status pages to Alpium. SSH is key-only. Who on the
  tailnet may connect is decided by Tailscale ACLs.
- **Survives reboots.** Everything is a systemd service.
- **Alpium notices.** The agent sends a heartbeat every 5 minutes to
  `/api/v1/ogn-stations/heartbeat` (typed fields only; `/gps/` refuses
  stations). A station
  silent for 30 minutes raises a Sentry issue that says whether the Pi is
  still on the tailnet (agent dead: SSH in) or not (power or network: send
  someone).

## One-time setup

### 1. Tailscale policy (admin console, Access controls)

Without explicit rules the default policy lets every tailnet device reach every
other one, so a stolen Pi could reach the Alpium server. Stations must reach
nothing; only the server and the admins reach them:

```jsonc
{
  "tagOwners": {
    "tag:ogn":           ["autogroup:admin", "tag:alpium-server"],
    "tag:alpium-server": ["autogroup:admin"]
  },
  "grants": [
    // Alpium's server: the signed control API and SSH.
    { "src": ["tag:alpium-server"], "dst": ["tag:ogn"], "ip": ["tcp:22", "tcp:8082"] },
    // Admins: SSH only, for a rescue from a laptop.
    { "src": ["autogroup:admin"], "dst": ["tag:ogn"], "ip": ["tcp:22"] }

    // ...your other rules for people and servers. Do NOT add any rule whose
    // src is tag:ogn: a station needs no inbound path to anything.
  ]
}
```

Tag the Alpium host `tag:alpium-server` (its machine page, Edit ACL tags).

### 2. Tailscale OAuth client (Settings, OAuth clients)

Scopes **Auth Keys: write** and **Devices Core: read + write**, tag
`tag:ogn`. Paste the id and secret into Alpium, Admin, Secrets, category
`ogn`: `TAILSCALE_OAUTH_CLIENT_ID`, `TAILSCALE_OAUTH_CLIENT_SECRET`. Until
they are set, enrollment refuses every station with a 503.

### 3. Retire the old secrets

The previous provisioning handed every Pi the same `.env`. After the new code
is deployed:

- revoke the old **reusable** Tailscale auth key (Settings, Keys);
- rotate the **OGN manufacturer secret** (Alpium, manufacturers table); it no
  longer registers stations, and every old Pi held it;
- clear `OGN_PROVISION_PASSPHRASE` and `OGN_PROVISION_CONFIG` in Alpium's
  secrets (`/provision/ogn` now answers 410).

Re-running `install.sh` on an old station shreds its `.env`.

## Installing a station from the image (the fast way)

1. In Raspberry Pi Imager: *App options → Content repository → Use custom
   URL* → `https://app.alpium.io/api/v1/ogn-stations/imager.json`, then choose
   **Alpium OGN station**. In the OS customisation set an admin user with your
   SSH public key, the Wi-Fi (the site's, or your phone hotspot), the time zone.
2. Put the card in, connect antenna and network (Ethernet, Wi-Fi, a 4G
   router, or a USB 4G modem whose APN you set later in Alpium), power on.
3. In Alpium, `/admin/ogn-stations`, *Waiting for approval*: the Pi appears
   with its serial within a couple of minutes. Check the serial against the
   Pi, set its callsign, **Approve**. It joins within a minute.

Nothing secret is on the card; an unapproved Pi gets nothing.

## Installing a station with the installer


1. Flash **Raspberry Pi OS Lite (Trixie, Debian 13)**, 32 or 64 bit
   (Bookworm is accepted too, see *Converting an old station*). In
   Raspberry Pi Imager, set a user, Wi-Fi if needed, and **your SSH public
   key** (password SSH is switched off by the installer).
2. Optional: get a code (Alpium, `/admin/ogn-stations`, *Enroll new stations*).
   Without one, the installer ends with the station *Waiting for approval*. One code
   per station, or one code for N stations when flashing a batch on a bench
   (short validity). Codes are shown once.
3. On the Pi:

```bash
sudo apt-get install -y git
sudo git clone https://github.com/simseve/hfss-pi-flarm-rx /home/hfss/hfss-pi-flarm-rx
cd /home/hfss/hfss-pi-flarm-rx
sudo ./install.sh --code OGN-XXXX-XXXX-XXXX-XXXX \
     --callsign MYSITE --lat 46.0123 --lon 8.9123 --alt 1250
```

The callsign follows http://wiki.glidernet.org/receiver-naming-convention;
Alpium keeps it unique across the fleet and may answer with a placeholder if
it is taken. Both can be changed later in Alpium. The station
shows up in Alpium within 5 minutes, as `OGN_STATION_<serial>` on the tailnet
as `ogn-<serial>`.

| Option | Effect |
|---|---|
| `--no-lan-ssh` | SSH from the tailnet only (no on-site rescue over the LAN) |
| `--keep-ssh-passwords` | leave sshd's password login on |
| `--skip-ogn` | do not reinstall the OGN binaries |
| `--enroll-url URL` | another Alpium instance |

### Converting an old station

A station from the old setup (ogn-pi34 under ~hfss/ogn-pi34, the Flask UI
started with `nohup sudo`) converts in place: clone this repo next to it and
run the installer with a code. It stops and removes the old agent and the old
`ogn-rf`/`ogn-decode` units (whatever unit, crontab or rc.local line started
them), shreds the old `.env`, and keeps the receiver settings from the old
`Template.conf`, FreqCorr included (a calibration of that dongle).

## Operating

- **Open a station**: Alpium console, *Manage* (status, receiver settings,
  network, OGN pages, heartbeat log) or *SSH*. Alpium pins each station's
  Tailscale address after checking it against the tailnet, and the Pi's SSH
  host key on first connection.
- **Update stations**: from Alpium, *Station software* on
  `/admin/ogn-stations`: pick a release, select a few outdated stations as a
  canary, check they report the new version, then the rest. Each station
  verifies the release signature itself, refuses a downgrade and installs in
  the background (`journalctl -u alpium-ogn-update`,
  `/var/log/alpium-ogn-update.log`). By hand, as before: `sudo ./install.sh`
  without `--code` keeps the enrollment and re-applies agent, units, helper
  and firewall.
- **Reinstalled Pi / new SD card in the same Pi**: run the installer with a
  new code. It is the same station (same serial): the old credentials stop
  working, the old tailnet node is removed, the pins reset, the callsign stays.
- **Replacing the Pi** (dead board, upgrade): in Alpium, *Manage*, *Identity*,
  *Replace hardware*, and install the new Pi with that code. It becomes the
  same station: id, callsign, tailnet name, history and position. A code for
  new stations refuses a Pi whose id already belongs to another board.
- **Callsigns** are Alpium's: unique in the fleet, chosen at enrollment (the
  one you pass with `--callsign` if free, else a placeholder `ALPRX…`), and
  changed in *Manage*, *Identity*. Name a receiver after its site
  (http://wiki.glidernet.org/receiver-naming-convention).
- **Lost or stolen**: Alpium console, Retire. Credentials revoked, tailnet
  node deleted, no more alerts.

## Field Wi-Fi and 4G

- **Field Wi-Fi**: set once in Alpium (*Field Wi-Fi*, typically your phone
  hotspot; on an iPhone switch on *Maximize Compatibility*) and pushed to
  every station at the lowest priority. In the field, switch on the hotspot
  and a station with no other network comes online through it.
- **4G**: a 4G router next to the Pi needs nothing. A USB modem (ModemManager
  is installed) gets its APN and SIM PIN in Alpium, *Manage → Network*.

## Building the image

The `Station image` workflow builds it for every published release
(`tools/build-image.sh`, GitHub arm64 runner) and attaches it with
`image-info.json`. Then, on the release machine:

```bash
python3 tools/make-release.py --sign-image v3.3.0
```

Alpium offers an image to Imager only once that signature is published.

## Releasing

On the release machine, which holds the offline release key
(`~/.ssh/alpium_ogn_release_ed25519`; its public half is
`system/release-signing.pub`):

```bash
# bump AGENT_VERSION in ogn-station-agent.py, commit, push, then
python3 tools/make-release.py --dry-run   # build + sign into dist/, check
python3 tools/make-release.py             # tag vX.Y.Z and publish with gh
```

The release is `git archive` of HEAD plus `manifest.json` (version, commit,
tarball URL, sha256) and `manifest.sig`. Nothing else can make a release: not
Alpium, not a station. Lose the key and stations can still be updated by
hand; leak it and rotate it (a release signed by the old key that ships the
new public key).

## What runs on a station

| Unit | What | User |
|---|---|---|
| `rtlsdr-ogn` | ogn-rf + ogn-decode under procServ (OGN 0.3.3, pinned + checksummed) | hfss |
| `alpium-ogn-station` | agent: heartbeat + signed control API on :8082 | hfss |
| `alpium-ogn-firewall` | nftables table `inet alpium_ogn` | root, oneshot |
| `tailscaled` | tailnet node `ogn-<serial>`, tag:ogn | root |
| `alpium-ogn-update` | transient: installs a signed release, then exits | root |

The agent is `ogn-station-agent.py`: Python standard library plus
`cryptography`, no web framework, bodies capped at 16 KB. Its only root access is `/usr/local/sbin/alpium-ogn-helper` (restart
the receiver, Wi-Fi through NetworkManager keyfiles, interface up/down with a
refusal to drop the last default route), allowed by `/etc/sudoers.d/alpium-ogn`.

Files: `~hfss/.ogn_credentials.json` (0600, this station's credentials),
`~hfss/rtlsdr-ogn/Template.conf` (receiver settings, written by the UI from
`ogn/Template.conf.in`), `/etc/alpium-ogn/firewall.nft`.

## Troubleshooting

```bash
systemctl status alpium-ogn-station rtlsdr-ogn tailscaled
journalctl -u alpium-ogn-station -n 50
curl -s http://127.0.0.1:8082/v1/health | python3 -m json.tool   # the one unsigned call
curl -s http://127.0.0.1:8081/ | head                            # OGN status, local only
tailscale status
sudo nft list table inet alpium_ogn
telnet localhost 50000      # ogn-rf console
telnet localhost 50001      # ogn-decode console
rtl_test -t                 # is the dongle seen
```

- Alpium says "Station refused the server's signature": the station's clock
  is more than 60 s off (`timedatectl`, chrony) or it was enrolled against
  another Alpium. The refusal reason is in `journalctl -u alpium-ogn-station`.
- Heartbeat 401/403: credentials revoked (station retired or re-enrolled
  elsewhere). Re-enroll with a new code.
- Not on the tailnet after enrollment: the single-use key expired (1 hour)
  before `tailscale up` ran. Re-run the installer with a new code.
