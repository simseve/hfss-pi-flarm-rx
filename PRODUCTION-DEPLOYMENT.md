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
- **Reachable over the tailnet only.** The station UI (8082), the OGN status
  pages (8080/8081) and procServ (50000/50001) are closed to the local network
  by the firewall; the agent also refuses non-tailnet clients itself. SSH is
  key-only. Who on the tailnet may connect is decided by Tailscale ACLs.
- **Survives reboots.** Everything is a systemd service.
- **Alpium notices.** The agent sends a heartbeat every 5 minutes. A station
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
    // Alpium's server and the admins may open a station's pages and shell.
    { "src": ["tag:alpium-server", "autogroup:admin"],
      "dst": ["tag:ogn"], "ip": ["tcp:22", "tcp:8080-8082"] }

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

## Installing a station

1. Flash **Raspberry Pi OS Lite (Trixie, Debian 13)**, 32 or 64 bit. In
   Raspberry Pi Imager, set a user, Wi-Fi if needed, and **your SSH public
   key** (password SSH is switched off by the installer).
2. Get a code: Alpium, `/admin/ogn-stations`, *Enroll new stations*. One code
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

The callsign follows http://wiki.glidernet.org/receiver-naming-convention.
Position and callsign can also be set later in the station UI. The station
shows up in Alpium within 5 minutes, as `OGN_STATION_<serial>` on the tailnet
as `ogn-<serial>`.

| Option | Effect |
|---|---|
| `--no-lan-ssh` | SSH from the tailnet only (no on-site rescue over the LAN) |
| `--keep-ssh-passwords` | leave sshd's password login on |
| `--skip-ogn` | do not reinstall the OGN binaries |
| `--enroll-url URL` | another Alpium instance |

## Operating

- **Open a station**: Alpium console, Station UI / OGN Demodulator / SSH.
  The console pins each station's Tailscale address after checking it against
  the tailnet, and the Pi's SSH host key on first connection.
- **Update a station**: on the Pi, as an admin user (not hfss, which has no
  sudo by design): `cd /home/hfss/hfss-pi-flarm-rx && sudo git pull && sudo ./install.sh`.
  Without `--code` it keeps the enrollment and re-applies agent, units,
  helper and firewall.
- **Reinstalled Pi / new SD card**: run the installer with a new code. The
  old credentials stop working, the old tailnet node is removed, and the
  console's pins reset.
- **Lost or stolen**: Alpium console, Retire. Credentials revoked, tailnet
  node deleted, no more alerts.

## What runs on a station

| Unit | What | User |
|---|---|---|
| `rtlsdr-ogn` | ogn-rf + ogn-decode under procServ (OGN 0.3.3, pinned + checksummed) | hfss |
| `alpium-ogn-station` | agent: heartbeat + UI on :8082 | hfss |
| `alpium-ogn-firewall` | nftables table `inet alpium_ogn` | root, oneshot |
| `tailscaled` | tailnet node `ogn-<serial>`, tag:ogn | root |

The agent's only root access is `/usr/local/sbin/alpium-ogn-helper` (restart
the receiver, Wi-Fi through NetworkManager keyfiles, interface up/down with a
refusal to drop the last default route), allowed by `/etc/sudoers.d/alpium-ogn`.

Files: `~hfss/.ogn_credentials.json` (0600, this station's credentials),
`~hfss/rtlsdr-ogn/Template.conf` (receiver settings, written by the UI from
`ogn/Template.conf.in`), `/etc/alpium-ogn/firewall.nft`.

## Troubleshooting

```bash
systemctl status alpium-ogn-station rtlsdr-ogn tailscaled
journalctl -u alpium-ogn-station -n 50
curl -s http://127.0.0.1:8082/api/health | python3 -m json.tool
tailscale status
sudo nft list table inet alpium_ogn
telnet localhost 50000      # ogn-rf console
telnet localhost 50001      # ogn-decode console
rtl_test -t                 # is the dongle seen
```

- Heartbeat 401/403: credentials revoked (station retired or re-enrolled
  elsewhere). Re-enroll with a new code.
- Not on the tailnet after enrollment: the single-use key expired (1 hour)
  before `tailscale up` ran. Re-run the installer with a new code.
