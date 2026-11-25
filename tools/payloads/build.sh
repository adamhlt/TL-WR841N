#!/bin/sh
# build.sh - cross-compile the small payloads to static MIPS big-endian binaries.
#   nc.mips     tiny netcat           (netcat / nc-bind / nc-reverse / exfil-config)
#   proxy.mips  minimal HTTP CONNECT  (open-proxy)
#
# The TL-WR841N SoC is a MIPS 74Kc, big-endian, without an FPU: use a
# mips-linux-muslsf (soft-float) toolchain; plain mips-linux-musl works too.
#
# Toolchain options:
#   1) musl.cc tarball (Linux/WSL):
#        wget https://musl.cc/mips-linux-muslsf-cross.tgz
#        tar xzf mips-linux-muslsf-cross.tgz
#        PATH="$PWD/mips-linux-muslsf-cross/bin:$PATH" ./build.sh
#   2) Docker:
#        docker run --rm -v "$PWD":/src -w /src \
#            muslcc/x86_64:mips-linux-muslsf-cross ./build.sh
#   3) musl-cross-make, any other MIPS BE musl/uclibc toolchain: set CROSS=...
#   4) native build (testing only, x86): CC=gcc ./build.sh
set -eu
cd -- "$(dirname -- "$0")"

CC="${CC:-}"
for cross in "${CROSS:-}" mips-linux-muslsf- mips-linux-musl-; do
    [ -n "$cross" ] || continue
    if command -v "${cross}gcc" >/dev/null 2>&1; then
        CC="${cross}gcc"
        break
    fi
done
[ -n "$CC" ] || {
    echo "[x] no MIPS big-endian cross compiler found - see the header of this script" >&2
    exit 1
}

echo "[*] building with $CC"
"$CC" -Os -s -static -Wall -o nc.mips nc.c
"$CC" -Os -s -static -Wall -o proxy.mips proxy.c
echo "[+] wrote nc.mips ($(wc -c < nc.mips) bytes) and proxy.mips ($(wc -c < proxy.mips) bytes)"
