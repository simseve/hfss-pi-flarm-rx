#!/usr/bin/env python3
"""Build, sign and publish a station release (run on the release machine).

    python3 tools/make-release.py              # build + sign + gh release
    python3 tools/make-release.py --dry-run    # build + sign into dist/ only

The version is AGENT_VERSION in ogn-station-agent.py; the tag is v<version>
and must not exist yet. The tarball is `git archive` of HEAD (so commit
first; a dirty tree is refused). The manifest names the tarball's URL and
sha256 and is signed with the OFFLINE release key, whose public half is
system/release-signing.pub. Stations install only what this key signed
(root helper `update`), and Alpium only offers what verifies.

Signed bytes: b"alpium-ogn-release-v1\\n" + manifest.json exactly as published.
"""
import argparse
import base64
import getpass
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

from cryptography.hazmat.primitives.serialization import load_ssh_private_key

REPO = "simseve/hfss-pi-flarm-rx"
NAME = "hfss-pi-flarm-rx"
CONTEXT = b"alpium-ogn-release-v1\n"
DEFAULT_KEY = os.path.expanduser("~/.ssh/alpium_ogn_release_ed25519")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", default=DEFAULT_KEY)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--notes", default="")
    a = ap.parse_args()

    version = re.search(r'^AGENT_VERSION = "(\d+\.\d+\.\d+)"$',
                        open(os.path.join(ROOT, "ogn-station-agent.py")).read(), re.M).group(1)
    tag = f"v{version}"
    if git("status", "--porcelain"):
        sys.exit("Working tree not clean: commit first (the release is git archive of HEAD)")
    if not a.dry_run and git("tag", "-l", tag):
        sys.exit(f"Tag {tag} exists: bump AGENT_VERSION")
    commit = git("rev-parse", "HEAD")

    dist = os.path.join(ROOT, "dist")
    os.makedirs(dist, exist_ok=True)
    tarball = f"{NAME}-{version}.tar.gz"
    path = os.path.join(dist, tarball)
    subprocess.run(["git", "archive", "--format=tar.gz", f"--prefix={NAME}/", "-o", path, "HEAD"], cwd=ROOT, check=True)
    data = open(path, "rb").read()

    manifest = json.dumps({
        "name": NAME,
        "version": version,
        "commit": commit,
        "url": f"https://github.com/{REPO}/releases/download/{tag}/{tarball}",
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }, indent=2) + "\n"

    raw = open(a.key, "rb").read()
    try:
        key = load_ssh_private_key(raw, password=None)
    except (TypeError, ValueError):
        key = load_ssh_private_key(raw, password=getpass.getpass("Release key passphrase: ").encode())
    signature = base64.b64encode(key.sign(CONTEXT + manifest.encode())).decode()

    pub = open(os.path.join(ROOT, "system", "release-signing.pub")).read().split()[:2]
    from cryptography.hazmat.primitives.serialization import load_ssh_public_key
    load_ssh_public_key(" ".join(pub).encode()).verify(base64.b64decode(signature), CONTEXT + manifest.encode())

    open(os.path.join(dist, "manifest.json"), "w").write(manifest)
    open(os.path.join(dist, "manifest.sig"), "w").write(signature + "\n")
    print(manifest)
    print(f"signed, {len(data)} bytes, {dist}")
    if a.dry_run:
        return
    subprocess.run(["gh", "release", "create", tag, "--repo", REPO, "--target", commit,
                    "--title", f"Station {version}", "--notes", a.notes or f"Station software {version}",
                    path, os.path.join(dist, "manifest.json"), os.path.join(dist, "manifest.sig")],
                   cwd=ROOT, check=True)
    print(f"published {tag}")


if __name__ == "__main__":
    main()
