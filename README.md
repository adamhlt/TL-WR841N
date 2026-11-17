<div align="center">

# TL-WR841N Firmware Reversing

**Flash dump, firmware layout, extraction and rebuild of a TP-Link TL-WR841N (MIPS).**

![Platform](https://img.shields.io/badge/platform-Linux-0078d7?style=for-the-badge&logo=linux&logoColor=white)
![Arch](https://img.shields.io/badge/arch-MIPS-red?style=for-the-badge)
![Target](https://img.shields.io/badge/target-TP--Link%20TL--WR841N-4c1?style=for-the-badge)

</div>

> The full story (UART discovery, shell, backdoor) is told on my blog (link coming soon). This repository only holds the technical material.

## Tools

| Hardware | Software |
| --- | --- |
| CH341A flash programmer + SOIC8 clip | [binwalk](https://github.com/ReFirmLabs/binwalk) |
| TTL to USB adapter (UART) | `squashfs-tools` (`unsquashfs` / `mksquashfs`) |
| Logic analyser (DSLogic U2 Basic) | DSView, PuTTY / `screen` |

## Repository layout

```
.
├── Firmware/
│   ├── details.txt       # binwalk output
│   └── fwtool.py         # CLI: extract/build the image, Linux only (see below)
├── Firmware Dumps/       # Raw SPI flash dumps, one per router (see below)
├── .gitattributes
├── .gitignore
└── LICENSE
```

## Flash dumps

[`Firmware Dumps/`](Firmware%20Dumps) holds one full 4 MiB SPI dump per physical
router, read with the CH341A. **Each file is a different device**, named after
the SSID that unit broadcasts (`TL-16DC`, `TL-E234`, `TL-FC5A`). They are
byte-identical except for ~100 bytes in the TP-Link header and config areas
(per-device data: MAC, calibration, serial). `dump TL-FC5A.bin` is the
reference image used by `fwtool.py` and analysed below.

## Firmware analysis

```bash
binwalk "Firmware Dumps/dump TL-FC5A.bin"
```

Output saved in [`Firmware/details.txt`](Firmware/details.txt).

### Flash layout (4 MB)

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

## Extract and rebuild

[`Firmware/fwtool.py`](Firmware/fwtool.py) is a single Python CLI that splits
the image, unpacks the rootfs, lets you edit it, then repacks and reassembles a
flashable image.

> **Linux only.** The script shells out to `unsquashfs` / `mksquashfs` and refuses to run on anything else. **On Windows, run it from WSL** (`wsl`, then `cd /mnt/c/...`).

```bash
sudo apt install squashfs-tools    # provides unsquashfs / mksquashfs

cd Firmware
python3 fwtool.py info              # flash layout, magic-byte check, required-tool check
python3 fwtool.py extract [-f]      # split the image into firmware_extract/, unpack the rootfs
python3 fwtool.py build             # repack the rootfs, fix CRCs, reassemble cfw.bin
```

- The input image defaults to `../Firmware Dumps/dump TL-FC5A.bin`; use `-i/--firmware PATH` to point at another dump.
- `info` runs anywhere (useful to check from Windows that you need WSL) and never fails; `extract`/`build` check the OS and the required tools up front and refuse with a clear message (including the `apt install` command) if either is missing.
- Splitting the 9 parts and reassembling the 4 MiB image is pure Python, with a sha256 printed for both the source and the rebuilt image.
- Unpacking/repacking the SquashFS rootfs (part 8) is delegated to `unsquashfs` / `mksquashfs` (`squashfs-tools`, LZMA support required).
- **`build` recomputes the U-Boot uImage CRCs** (header + data CRC32) automatically, so an edited bootloader stays valid. The TP-Link header MD5 is left untouched: a direct CH341A reflash does not check it (only the OEM web updater does).
- Root is **not required**. Without it, `unsquashfs` just skips the rootfs's `/dev` device nodes and warns — regular files, directories and symlinks extract normally, which is enough to edit and repack. Run `extract` as `sudo` only if you specifically need those device nodes recreated (e.g. to get a byte-identical rootfs).
- `extract` refuses to overwrite an existing `firmware_extract/` unless `-f`/`--force` is passed.
- The rebuilt rootfs must fit in the 2883584-byte slot; `build` aborts if it does not.

Flash the resulting `cfw.bin` back with the CH341A and SOIC8 clip.

## Disclaimer

For **educational purposes**, on hardware I own. Do not use these techniques on devices you do not own or have permission to test.

## License

Released under the **GNU GPL v3** — see [LICENSE](LICENSE).
