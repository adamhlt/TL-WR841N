#!/bin/sh
# build_dropbear.sh - build payloads/dropbear.mips + dropbearkey.mips, statically
# linked for the MIPS big-endian TL-WR841N (used by `vuln.py inject dropbear`).
#
# Needs the same toolchain as build.sh (see its header) plus internet access
# to fetch the dropbear source tarball:
#   DROPBEAR_VER=2024.86 ./build_dropbear.sh     (default version)
#   CC=gcc ./build_dropbear.sh                   (native build, testing only)
#   STATIC= ./build_dropbear.sh                  (dynamic link, testing only)
set -eu
cd -- "$(dirname -- "$0")"
VER="${DROPBEAR_VER:-2024.86}"

CC="${CC:-}"
for cross in "${CROSS:-}" mips-linux-muslsf- mips-linux-musl-; do
    [ -n "$cross" ] || continue
    if command -v "${cross}gcc" >/dev/null 2>&1; then
        CC="${cross}gcc"
        break
    fi
done
[ -n "$CC" ] || {
    echo "[x] no MIPS big-endian cross compiler found - see build.sh for toolchain options" >&2
    exit 1
}

if [ ! -f "dropbear-$VER.tar.bz2" ]; then
    echo "[*] fetching dropbear $VER"
    wget -q --timeout=30 --tries=1 "https://matt.ucc.asn.au/dropbear/releases/dropbear-$VER.tar.bz2"
fi
rm -rf "dropbear-$VER"
tar xjf "dropbear-$VER.tar.bz2"
cd "dropbear-$VER"

echo "[*] configuring with $CC"
./configure CC="$CC" --disable-zlib --disable-syslog LDFLAGS="${STATIC:--static}"

echo "[*] building dropbear + dropbearkey"
make PROGRAMS="dropbear dropbearkey" -j"$(nproc)" >/dev/null

cp dropbear ../dropbear.mips
cp dropbearkey ../dropbearkey.mips
echo "[+] wrote ../dropbear.mips and ../dropbearkey.mips"
