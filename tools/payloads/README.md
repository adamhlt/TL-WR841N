# Payloads

Binaries `vuln.py` copies into the extracted rootfs. Everything here targets
the TL-WR841N SoC: **MIPS 74Kc, big-endian, soft-float** (verified by
decompressing the kernel from the reference dump).

| Payload | Built by | Used by | What it is |
| --- | --- | --- | --- |
| `nc.mips` | `build.sh` | `netcat`, `nc-bind`, `nc-reverse`, `exfil-config` | tiny netcat (`-l -p PORT [-e CMD]`, client mode), no DNS/UDP |
| `proxy.mips` | `build.sh` | `open-proxy` | minimal HTTP CONNECT proxy (LAN pivot) |
| `dropbear.mips` + `dropbearkey.mips` | `build_dropbear.sh` | `dropbear` | SSH server + key generator, key-only auth |

Build them once (Linux/WSL or Docker):

```bash
cd tools/payloads
./build.sh                 # nc.mips + proxy.mips, musl.cc toolchain, see script header
./build_dropbear.sh        # dropbear.mips + dropbearkey.mips (downloads the source)
```

Sanity-check with `file *.mips` (expect `ELF 32-bit MSB executable, MIPS,
statically linked`) and `qemu-mips ./nc.mips -h` if qemu-user is installed.

`vuln.py inject netcat` falls back to the stock busybox `nc` applet when the
firmware has one, so `nc.mips` is only needed for stock TP-Link images (their
busybox ships without `nc`). Built binaries and dropbear source trees are
gitignored (`tools/payloads/*.mips`, `*.tar.bz2`, `dropbear-*/`) — rebuild
them rather than committing toolchain output.
