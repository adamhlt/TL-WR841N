<div align="center">

# TL-WR841N Firmware Reversing

**Flash dump, firmware analysis, extraction, rebuild and lab backdooring of a TP-Link TL-WR841N (MIPS)**

![Platform](https://img.shields.io/badge/Linux-16171C?logo=linux)
![Arch](https://img.shields.io/badge/MIPS-16171C)
![Target](https://img.shields.io/badge/TP--Link%20TL--WR841N-16171C)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-16171C)](LICENSE)

</div>

---

This project dumps the 4 MiB SPI flash of a TP-Link TL-WR841N with a CH341A programmer, maps the firmware layout (U-Boot, LZMA kernel, SquashFS rootfs) and ships a single Python CLI, `fwtool.py`, that splits the image, lets you edit the rootfs, then repacks it and reassembles a flashable image. The kernel and bootloader are confirmed MIPS 74Kc big-endian, so every tool and payload targets that architecture.

The same CLI ecosystem (`vuln.py`) deliberately introduces vulnerabilities into the rebuilt rootfs — netcat bind/reverse shells, telnetd, an SSH backdoor, DNS hijack, cron persistence, ... — through an idempotent and fully revertible injection framework: originals are backed up, boot hooks are delimited by markers, and the whole injection set is tracked in a state file.

The full story (UART discovery, shell, backdoor) is told on [adamhlt.com](https://adamhlt.com/). This repository only holds the technical material.

## Hardware & Software

**Hardware**

- CH341A flash programmer + SOIC8 clip
- TTL to USB adapter (UART)
- Logic analyser (DSLogic U2 Basic)

**Software**

- [binwalk](https://github.com/ReFirmLabs/binwalk) — firmware analysis
- `squashfs-tools` (`unsquashfs` / `mksquashfs`) — rootfs extraction and repack
- DSView, PuTTY / `screen` — logic capture and UART console

## Firmware layout

```bash
binwalk dumps/tl-fc5a.bin
```

Output saved in [`analysis/binwalk.txt`](analysis/binwalk.txt).

| Offset | Size (bytes) | Content |
| --- | --- | --- |
| `0x0` | 12928 | Header |
| `0x3280` (12928) | 48 | U-Boot version string: `U-Boot 1.1.4 (Mar 10 2015 - 15:00:39)` |
| `0x32B0` (12976) | 1312 | CRC32 polynomial table (big endian) |
| `0x37D0` (14288) | 64 | uImage header (Linux / MIPS, LZMA, name `u-boot image`) |
| `0x3810` (14352) | 116720 | LZMA compressed data: U-Boot (93256 bytes uncompressed) |
| `0x20000` (131072) | 512 | TP-Link firmware header |
| `0x20200` (131584) | 1048064 | LZMA compressed data: Linux kernel (2219160 bytes uncompressed) |
| `0x120000` (1179648) | 2883584 | SquashFS 4.0, little endian, LZMA, 560 inodes, block size 128 KB |
| `0x3E0000` (4063232) | 131072 | Config partition |

The kernel entry point is `0x80002000`.

> **Note**
> [`dumps/`](dumps) holds one full 4 MiB SPI dump per physical router, read with the CH341A. Each file is a different device, named after the SSID that unit broadcasts (`tl-16dc.bin`, `tl-e234.bin`, `tl-fc5a.bin`). They are byte-identical except for ~100 bytes in the TP-Link header and config areas (per-device data: MAC, calibration, serial). `tl-fc5a.bin` is the reference image used by the tools.

## Usage

1. Install the requirements: `sudo apt install squashfs-tools`.
2. `python3 fwtool.py info` — flash layout, magic-byte check, required-tool check.
3. `python3 fwtool.py extract [-f]` — split the image into `extracted/` and unpack the rootfs.
4. `python3 vuln.py list` — see what the rootfs supports, then `python3 vuln.py inject netcat nc-bind ...` to introduce vulnerabilities.
5. `python3 fwtool.py build` — repack the rootfs, fix CRCs and reassemble `cfw.bin`.
6. Flash the resulting `cfw.bin` back with the CH341A and SOIC8 clip.

All commands run from `tools/`. `vuln.py inject`/`clean` require Linux or WSL; `list`, `report` and `fwtool.py info` run anywhere.

> **Note**
> **Linux only.** The scripts shell out to `unsquashfs` / `mksquashfs` and refuse to run anywhere else. On Windows, run them from WSL (`wsl`, then `cd /mnt/c/...`). Root is not required: without it, `unsquashfs` just skips the rootfs `/dev` device nodes and warns.

## Vulnerabilities

**Access / backdoors**

- `netcat` — static MIPS-BE `nc` installed as `/usr/bin/nc` (or the stock busybox `nc` applet exposed when present)
- `nc-bind` — bind shell on TCP/4444 (`nc -l -p 4444 -e /bin/sh`), respawned in a loop
- `nc-reverse` — reverse shell to `--host IPv4 --port N`, same respawn loop
- `telnetd` — busybox `telnetd -l /bin/sh`: unauthenticated root shell on TCP/23
- `dropbear` — SSH server on TCP/22 trusting `/root/.ssh/authorized_keys` (attacker key via `--pubkey`)
- `passwordless-root` — empties the root password hash in `/etc/shadow` (or `/etc/passwd`)
- `suid-busybox` — sets the SUID root bit on `/bin/busybox`

**Persistence**

- `cron-persistence` — busybox `crond` re-launches the services every minute: a second persistence vector that survives init-hook removal

**Network**

- `dns-hijack` — points `/etc/resolv.conf` at `--ns` at boot
- `hosts-redirect` — pins `--domain` to `--ip` in `/etc/hosts` at boot
- `firewall-off` — flushes iptables and sets all policies ACCEPT at boot
- `open-proxy` — HTTP CONNECT proxy on TCP/8888 for LAN pivoting

**Exfiltration / anti-forensics**

- `exfil-config` — streams `/etc` to `--host:--port` at boot (tar over nc)
- `logwipe` — truncates `/var/log` and clears the kernel ring buffer at boot

The boot hook is added to the init script found in the rootfs (the `::sysinit:` target, `rcS`, or a new `S99fwvuln`), delimited by `# >>> fwvuln hook` markers; the enabled services live in a generated `/etc/fwvuln.sh`.

## Build

1. Build the payloads once — plain C, cross-compiled to static MIPS big-endian binaries (the SoC is a MIPS 74Kc, big-endian, soft-float):

   ```bash
   cd tools/payloads
   ./build.sh              # nc.mips + proxy.mips
   ./build_dropbear.sh     # dropbear.mips + dropbearkey.mips
   ```

2. `python3 fwtool.py build` reassembles the 4 MiB image (`cfw.bin`) from the 9 parts, recomputing the U-Boot uImage header and data CRC32 automatically.

- **Input:** defaults to `dumps/tl-fc5a.bin`; `-i/--firmware PATH` points at another dump
- **Output:** `tools/cfw.bin`, flashable with the CH341A (the TP-Link header MD5 is left as-is: only the OEM web updater checks it)
- **Injection state:** originals backed up to `extracted/.vuln-backups/`, markers in the boot scripts, state tracked in `extracted/vuln_state.json`; `python3 vuln.py clean` restores the rootfs to its post-extract state
- **Slot limit:** the rebuilt rootfs must fit in its 2883584-byte slot — `build` aborts otherwise

## Disclaimer

For **educational purposes**, on hardware I own. Do not use these techniques on devices you do not own or have permission to test. `vuln.py` intentionally backdoors the image it builds — never flash such a `cfw.bin` to a router you do not own, and never attach it to a network you do not control.

## License

Released under the **GNU GPL v3** — see [LICENSE](LICENSE).
