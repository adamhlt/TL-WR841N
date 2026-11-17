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
| TTL to USB adapter (UART) | `dd`, `squashfs-tools` (`unsquashfs` / `mksquashfs`) |
| Logic analyser (DSLogic U2 Basic) | DSView, PuTTY / `screen` |

## Repository layout

```
.
├── Firmware/
│   ├── firmware.bin   # Reference dump
│   ├── details.txt    # binwalk output
│   ├── extract.sh     # Split and unpack the image
│   └── rebuild.sh     # Repack and rebuild a custom image
├── Firmware Dumps/    # Raw flash dumps
└── LICENSE
```

## Firmware analysis

```bash
binwalk Firmware/firmware.bin
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

Sizes are those used by `extract.sh` / `rebuild.sh`. The kernel entry point is `0x80002000`.

## Extract and rebuild

```bash
cd Firmware

# Split firmware.bin into 9 parts and unpack the SquashFS
# (a backup firmware.bck is created automatically)
./extract.sh

# ... modify firmware_extract/squashfs-root/ ...

# Repack the SquashFS (LZMA) and reassemble a 4 MB image: cfw.bin
./rebuild.sh
```

Requirements: `dd`, `squashfs-tools`, `sudo`.

- `extract.sh` writes `firmware_extract/firmware_part1.bin` to `firmware_part9.bin`, then runs `unsquashfs` on part 8.
- `rebuild.sh` creates a 4 MB `0xFF`-filled `cfw.bin`, copies parts 1 to 7 and 9 back at their original offsets, and rebuilds part 8 with `mksquashfs -comp lzma`.
- The repacked SquashFS must fit in its 2883584-byte slot.

Flash `cfw.bin` back with the CH341A and SOIC8 clip.

## Disclaimer

For **educational purposes**, on hardware I own. Do not use these techniques on devices you do not own or have permission to test.

## License

See [LICENSE](LICENSE).
