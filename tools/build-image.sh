#!/usr/bin/env bash
# Build the Alpium OGN station card image (Raspberry Pi 4/5, 64-bit).
#
#   sudo tools/build-image.sh [OUTPUT_DIR]
#
# Takes the official Raspberry Pi OS Lite (64-bit) image listed in Raspberry
# Pi Imager's own catalogue, grows it, runs `install.sh --image` inside it
# (everything installed, nothing enrolled, nothing started), and writes:
#   alpium-ogn-station-<version>.img.xz   the image
#   image-info.json                       sizes, sha256s, the base image and
#                                         Imager's init_format for it
# A station flashed with it claims at first boot and waits for an admin's
# approval in Alpium; nothing secret is in the image.
#
# Must run as root on an arm64 Linux machine (GitHub's ubuntu-24.04-arm
# runner): install.sh runs natively in the chroot, no emulation.
set -euo pipefail

OUT=${1:-dist}
OS_LIST=https://downloads.raspberrypi.com/os_list_imagingutility_v4.json
GROW_MB=1536

die() { echo "ERROR: $*" >&2; exit 1; }
[ "$(id -u)" -eq 0 ] || die "run as root"
[ "$(uname -m)" = "aarch64" ] || die "run on an arm64 machine"
for t in curl jq xz losetup parted e2fsck resize2fs sha256sum; do
  command -v "$t" >/dev/null || die "missing $t"
done

REPO=$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)
VERSION=$(sed -n 's/^AGENT_VERSION = "\([0-9.]*\)"$/\1/p' "$REPO/ogn-station-agent.py")
[ -n "$VERSION" ] || die "cannot read AGENT_VERSION"
mkdir -p "$OUT"
OUT=$(cd "$OUT" && pwd)
WORK=$(mktemp -d)
MNT=$WORK/root
LOOP=""
cleanup() {
  set +e
  for m in "$MNT/dev/pts" "$MNT/dev" "$MNT/proc" "$MNT/sys" "$MNT/boot/firmware" "$MNT"; do
    mountpoint -q "$m" && umount -l "$m"
  done
  [ -n "$LOOP" ] && losetup -d "$LOOP"
  rm -rf "$WORK"
}
trap cleanup EXIT

echo "== Base image: Raspberry Pi OS Lite (64-bit) from Imager's catalogue"
# The entry Imager itself offers, found by name in its catalogue tree.
curl -fsSL "$OS_LIST" -o "$WORK/os_list.json"
BASE=$(jq -c '[.. | objects | select(.name? and (.name | test("^Raspberry Pi OS Lite \\(64-bit\\)$")) and .url?)][0]' "$WORK/os_list.json")
[ "$BASE" != "null" ] || die "Raspberry Pi OS Lite (64-bit) not found in $OS_LIST"
BASE_URL=$(jq -r .url <<<"$BASE")
BASE_SHA=$(jq -r .image_download_sha256 <<<"$BASE")
INIT_FORMAT=$(jq -r '.init_format // "systemd"' <<<"$BASE")
echo "   $BASE_URL (init_format $INIT_FORMAT)"
curl -fsSL "$BASE_URL" -o "$WORK/base.img.xz"
echo "$BASE_SHA  $WORK/base.img.xz" | sha256sum -c --quiet || die "base image checksum mismatch"
xz -d -T0 "$WORK/base.img.xz"
IMG=$WORK/base.img

echo "== Grow the root partition by ${GROW_MB} MB"
truncate -s +"${GROW_MB}M" "$IMG"
parted -s "$IMG" resizepart 2 100%
LOOP=$(losetup -fP --show "$IMG")
e2fsck -pf "${LOOP}p2" || true
resize2fs "${LOOP}p2"

echo "== Install the station software in a chroot"
mkdir -p "$MNT"
mount "${LOOP}p2" "$MNT"
mount "${LOOP}p1" "$MNT/boot/firmware"
mount --bind /dev "$MNT/dev"
mount --bind /dev/pts "$MNT/dev/pts"
mount -t proc proc "$MNT/proc"
mount -t sysfs sys "$MNT/sys"
cp --remove-destination /etc/resolv.conf "$MNT/etc/resolv.conf"
mkdir -p "$MNT/tmp/station-src"
git -C "$REPO" archive HEAD | tar -x -C "$MNT/tmp/station-src"
chroot "$MNT" /bin/bash /tmp/station-src/install.sh --image
chroot "$MNT" /bin/bash -c 'apt-get clean; rm -rf /var/lib/apt/lists/* /tmp/station-src'
# The image's resolv.conf is NetworkManager's to write at first boot.
rm -f "$MNT/etc/resolv.conf"
ln -s ../run/NetworkManager/resolv.conf "$MNT/etc/resolv.conf"
cleanup_mounts() {
  for m in "$MNT/dev/pts" "$MNT/dev" "$MNT/proc" "$MNT/sys" "$MNT/boot/firmware" "$MNT"; do umount "$m"; done
}
cleanup_mounts
e2fsck -pf "${LOOP}p2" || true
losetup -d "$LOOP"; LOOP=""

echo "== Compress"
NAME=alpium-ogn-station-$VERSION.img
EXTRACT_SIZE=$(stat -c %s "$IMG")
EXTRACT_SHA=$(sha256sum "$IMG" | cut -d' ' -f1)
mv "$IMG" "$WORK/$NAME"
xz -T0 -6 "$WORK/$NAME"
mv "$WORK/$NAME.xz" "$OUT/"
DL_SIZE=$(stat -c %s "$OUT/$NAME.xz")
DL_SHA=$(sha256sum "$OUT/$NAME.xz" | cut -d' ' -f1)

jq -n --arg version "$VERSION" --arg file "$NAME.xz" --arg base "$BASE_URL" --arg init "$INIT_FORMAT" \
      --argjson extract_size "$EXTRACT_SIZE" --arg extract_sha256 "$EXTRACT_SHA" \
      --argjson download_size "$DL_SIZE" --arg download_sha256 "$DL_SHA" \
      --arg commit "$(git -C "$REPO" rev-parse HEAD)" \
      '{version: $version, file: $file, commit: $commit, base_image: $base, init_format: $init,
        extract_size: $extract_size, extract_sha256: $extract_sha256,
        image_download_size: $download_size, image_download_sha256: $download_sha256}' \
      > "$OUT/image-info.json"
cat "$OUT/image-info.json"
echo "Done: $OUT/$NAME.xz"
