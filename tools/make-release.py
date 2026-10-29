#!/usr/bin/env python3
"""Build, sign and publish a station release (run on the release machine).

    python3 tools/make-release.py              # build + sign + gh release
    python3 tools/make-release.py --dry-run    # build + sign into dist/ only
    python3 tools/make-release.py --sign-image v3.3.0
                                               # after the Station image workflow
                                               # attached the card image: sign it

The version is AGENT_VERSION in ogn-station-agent.py; the tag is v<version>
and must not exist yet. The tarball is `git archive` of HEAD (so commit
first; a dirty tree is refused). The manifest names the tarball's URL and
sha256 and is signed with the OFFLINE release key, whose public half is
system/release-signing.pub. Stations install only what this key signed
(root helper `update`), and Alpium only offers what verifies.

Signed bytes: b"alpium-ogn-release-v1\\n" + manifest.json exactly as published.

The card image (.github/workflows/station-image.yml) is built on GitHub and
attached to the release with image-info.json; --sign-image signs a
manifest-image.json made from that file's checksums (the image itself never
comes back here), with the context b"alpium-ogn-image-v1\\n". Alpium offers an
image to Raspberry Pi Imager only when that signature verifies.
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


IMAGE_CONTEXT = b"alpium-ogn-image-v1\n"


def load_key(path):
    raw = open(path, "rb").read()
    try:
        return load_ssh_private_key(raw, password=None)
    except (TypeError, ValueError):
        return load_ssh_private_key(raw, password=getpass.getpass("Release key passphrase: ").encode())


def sign_image(tag, key_path):
    """Sign the card image attached to release `tag` by the image workflow."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        got = subprocess.run(["gh", "release", "download", tag, "--repo", REPO, "--pattern", "image-info.json",
                              "--dir", tmp])
        if got.returncode != 0:
            sys.exit(f"No image-info.json on {tag} yet: the Station image workflow builds it in 20-30 minutes "
                     f"after the release (gh run list --repo {REPO} --workflow station-image.yml).")
        info = json.load(open(os.path.join(tmp, "image-info.json")))
    if f"v{info['version']}" != tag:
        sys.exit(f"image-info.json is for {info['version']}, not {tag}")
    manifest = json.dumps({
        "name": f"{NAME}-image",
        "version": info["version"],
        "commit": info["commit"],
        "url": f"https://github.com/{REPO}/releases/download/{tag}/{info['file']}",
        "image_download_size": info["image_download_size"],
        "image_download_sha256": info["image_download_sha256"],
        "extract_size": info["extract_size"],
        "extract_sha256": info["extract_sha256"],
        "init_format": info["init_format"],
        "base_image": info["base_image"],
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }, indent=2) + "\n"
    key = load_key(key_path)
    signature = base64.b64encode(key.sign(IMAGE_CONTEXT + manifest.encode())).decode()
    dist = os.path.join(ROOT, "dist")
    os.makedirs(dist, exist_ok=True)
    open(os.path.join(dist, "manifest-image.json"), "w").write(manifest)
    open(os.path.join(dist, "manifest-image.sig"), "w").write(signature + "\n")
    print(manifest)
    subprocess.run(["gh", "release", "upload", tag, "--repo", REPO, "--clobber",
                    os.path.join(dist, "manifest-image.json"), os.path.join(dist, "manifest-image.sig")], check=True)
    print(f"signed image of {tag}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", default=DEFAULT_KEY)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--notes", default="")
    ap.add_argument("--sign-image", metavar="TAG", help="sign the card image attached to release TAG")
    a = ap.parse_args()
    if a.sign_image:
        return sign_image(a.sign_image, a.key)

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

    key = load_key(a.key)
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
