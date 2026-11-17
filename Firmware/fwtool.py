#!/usr/bin/env python3
"""fwtool - extract and rebuild the TP-Link TL-WR841N firmware image.

Linux only. `extract` and `build` shell out to `unsquashfs` / `mksquashfs`
(squashfs-tools, built with LZMA support) to unpack and repack the rootfs
partition; both are checked for up front and the script refuses to run
anywhere but Linux, where that package is one `apt install` away.
On Windows, run it from WSL.

Usage:
    fwtool.py info             print the flash layout, validate magic bytes,
                                report whether the required tools are present
    fwtool.py extract [-f]     split firmware.bin and unpack the SquashFS rootfs
    fwtool.py build            repack the SquashFS and reassemble cfw.bin
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

HERE = Path(__file__).resolve().parent
FLASH_SIZE = 4 * 1024 * 1024

REQUIRED_TOOLS: dict[str, str] = {
    "unsquashfs": "squashfs-tools",
    "mksquashfs": "squashfs-tools",
}

FIRMWARE = "firmware.bin"
BACKUP = "firmware.bck"
EXTRACT_DIR = "firmware_extract"
ROOTFS_DIR = "squashfs-root"
OUTPUT = "cfw.bin"


class FwError(Exception):
    """User-facing error: bad input, missing file, tool failure."""


# --------------------------------------------------------------------------- #
# Layout
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Part:
    index: int
    label: str
    offset: int
    size: int

    @property
    def end(self) -> int:
        return self.offset + self.size

    @property
    def filename(self) -> str:
        return f"firmware_part{self.index}.bin"


PARTS: tuple[Part, ...] = (
    Part(1, "Header", 0x000000, 12928),
    Part(2, "U-Boot version string", 0x003280, 48),
    Part(3, "CRC32 polynomial table", 0x0032B0, 1312),
    Part(4, "uImage header", 0x0037D0, 64),
    Part(5, "U-Boot (LZMA)", 0x003810, 116720),
    Part(6, "TP-Link firmware header", 0x020000, 512),
    Part(7, "Linux kernel (LZMA)", 0x020200, 1048064),
    Part(8, "SquashFS rootfs", 0x120000, 2883584),
    Part(9, "Config", 0x3E0000, 131072),
)
ROOTFS_PART = PARTS[7]

# (offset, expected bytes, description) - sanity checks, not a full parser
MAGICS: tuple[tuple[int, bytes, str], ...] = (
    (0x003280, b"U-Boot 1.1.4", "U-Boot version string"),
    (0x0037D0, bytes.fromhex("27051956"), "uImage magic"),
    (0x003810, b"\x5d", "U-Boot LZMA properties byte"),
    (0x020200, b"\x5d", "Kernel LZMA properties byte"),
    (0x120000, b"hsqs", "SquashFS magic (little endian)"),
)

# contiguity check
_pos = 0
for _p in PARTS:
    assert _p.offset == _pos, f"gap before part {_p.index}"
    _pos = _p.end
assert _pos == FLASH_SIZE
del _pos, _p


def sha256_short(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# Reporting - CLI prints to stdout, the TUI overrides this
# --------------------------------------------------------------------------- #


class Reporter:
    def log(self, msg: str, level: str = "info") -> None:
        prefix = {"info": "[*]", "ok": "[+]", "warn": "[!]", "error": "[x]", "cmd": "   "}
        print(f"{prefix.get(level, '[*]')} {msg}")

    def progress(self, fraction: float, label: str = "") -> None:
        pass


# --------------------------------------------------------------------------- #
# Core operations
# --------------------------------------------------------------------------- #


def read_flash(path: Path) -> bytes:
    if not path.is_file():
        raise FwError(f"firmware not found: {path}")
    data = path.read_bytes()
    if len(data) != FLASH_SIZE:
        raise FwError(f"{path.name} is {len(data)} bytes, expected {FLASH_SIZE} (4 MiB flash dump)")
    return data


def check_layout(data: bytes) -> list[tuple[bool, str]]:
    out = []
    for offset, magic, desc in MAGICS:
        ok = data[offset : offset + len(magic)] == magic
        out.append((ok, f"0x{offset:06X}  {desc}"))
    return out


def check_platform() -> None:
    if not sys.platform.startswith("linux"):
        raise FwError(
            f"fwtool requires Linux (unsquashfs/mksquashfs), detected: {sys.platform}. "
            "On Windows, run it from WSL: `wsl` then `cd /mnt/c/...` (see README)."
        )


def tool_path(name: str) -> Optional[str]:
    return shutil.which(name)


def require_tools(*names: str) -> None:
    missing = [name for name in names if not tool_path(name)]
    if missing:
        packages = sorted({REQUIRED_TOOLS[name] for name in missing})
        raise FwError(
            f"required tool(s) not found in PATH: {', '.join(missing)}. "
            f"Install with: sudo apt install {' '.join(packages)}"
        )


def run_tool(cmd: list[str], rep: Reporter, cwd: Optional[Path] = None) -> int:
    rep.log("$ " + " ".join(cmd), "cmd")
    try:
        proc = subprocess.Popen(
            cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace"
        )
    except OSError as exc:
        raise FwError(f"cannot run {cmd[0]}: {exc}") from exc
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip()
        if line:
            rep.log(line, "cmd")
    return proc.wait()


def remove_dir(path: Path) -> None:
    def onerror(func, p, _exc):
        try:
            os.chmod(p, 0o700)
            func(p)
        except OSError as exc:
            raise FwError(f"cannot remove {p}: {exc}") from exc

    shutil.rmtree(path, onerror=onerror)


def extract(work: Path, rep: Reporter, firmware: Optional[Path] = None, force: bool = False) -> None:
    """Split firmware.bin into its 9 parts, then unpack the SquashFS rootfs."""
    check_platform()
    require_tools("unsquashfs")

    firmware = firmware or (work / FIRMWARE)
    data = read_flash(firmware)
    rep.log(f"Loaded {firmware.name} ({len(data)} bytes, sha256 {sha256_short(data)}...)")

    for ok, text in check_layout(data):
        rep.log(text, "ok" if ok else "warn")

    backup = work / BACKUP
    if not backup.exists():
        shutil.copyfile(firmware, backup)
        rep.log(f"Backup created: {backup.name}", "ok")

    out_dir = work / EXTRACT_DIR
    if out_dir.exists():
        if not force:
            raise FwError(f"{EXTRACT_DIR}/ already exists (pass --force to overwrite)")
        rep.log(f"Removing existing {EXTRACT_DIR}/", "warn")
        remove_dir(out_dir)
    out_dir.mkdir(parents=True)

    total_steps = len(PARTS) + 1
    for i, part in enumerate(PARTS, start=1):
        (out_dir / part.filename).write_bytes(data[part.offset : part.end])
        rep.log(f"part {part.index}  0x{part.offset:06X}  {part.size:>8} B  {part.label}")
        rep.progress(i / total_steps, f"split part {part.index}/{len(PARTS)}")

    rootfs = out_dir / ROOTFS_DIR
    unsquashfs = tool_path("unsquashfs")
    assert unsquashfs  # checked by require_tools() above
    cmd = [unsquashfs, "-d", str(rootfs), str(out_dir / ROOTFS_PART.filename)]
    code = run_tool(cmd, rep)
    if code != 0 and not rootfs.is_dir():
        raise FwError(f"unsquashfs failed (exit code {code})")
    rep.progress(1.0, "extraction complete")
    rep.log(f"Rootfs extracted to {rootfs}", "ok")


def _load_part(out_dir: Path, part: Part) -> bytes:
    path = out_dir / part.filename
    if not path.is_file():
        raise FwError(f"{part.filename} is missing (run extract first)")
    data = path.read_bytes()
    if len(data) != part.size:
        raise FwError(f"{part.filename} is {len(data)} bytes, expected {part.size}")
    return data


def build(work: Path, rep: Reporter, output: Optional[Path] = None) -> Path:
    """Repack the SquashFS rootfs and reassemble cfw.bin."""
    check_platform()
    require_tools("mksquashfs")

    out_dir = work / EXTRACT_DIR
    output = output or (work / OUTPUT)
    if not out_dir.is_dir():
        raise FwError(f"{EXTRACT_DIR}/ not found (run extract first)")

    rootfs = out_dir / ROOTFS_DIR
    rootfs_part_path = out_dir / ROOTFS_PART.filename

    if rootfs.is_dir():
        mksquashfs = tool_path("mksquashfs")
        assert mksquashfs  # checked by require_tools() above
        rep.log("Repacking rootfs with mksquashfs (LZMA)...")
        rebuilt = out_dir / "rootfs.rebuilt.sqsh"
        if rebuilt.exists():
            rebuilt.unlink()
        code = run_tool([mksquashfs, str(rootfs), str(rebuilt), "-comp", "lzma", "-noappend"], rep)
        if code != 0 or not rebuilt.is_file():
            raise FwError(f"mksquashfs failed (exit code {code})")
        if rebuilt.stat().st_size > ROOTFS_PART.size:
            raise FwError(
                f"rebuilt rootfs is {rebuilt.stat().st_size} bytes, "
                f"larger than the {ROOTFS_PART.size}-byte slot (remove files and retry)"
            )
        rootfs_part_path = rebuilt
        rep.log(f"Rootfs repacked: {rebuilt.stat().st_size} bytes", "ok")
    else:
        rep.log(f"{ROOTFS_DIR}/ not found: keeping the existing SquashFS partition unchanged", "warn")
    rep.progress(0.3, "rootfs ready")

    image = bytearray(b"\xff" * FLASH_SIZE)
    total = len(PARTS)
    for i, part in enumerate(PARTS, start=1):
        if part is ROOTFS_PART:
            data = rootfs_part_path.read_bytes()
            if len(data) > part.size:
                raise FwError(f"{rootfs_part_path.name} ({len(data)} B) does not fit in the {part.size}-B slot")
            image[part.offset : part.offset + len(data)] = data
        else:
            data = _load_part(out_dir, part)
            image[part.offset : part.end] = data
        rep.log(f"part {part.index}  0x{part.offset:06X}  placed ({part.label})")
        rep.progress(0.3 + 0.7 * i / total, f"assembling part {part.index}/{total}")

    output.write_bytes(image)
    rep.progress(1.0, "build complete")
    rep.log(f"Built {output} ({len(image)} bytes, sha256 {sha256_short(bytes(image))}...)", "ok")
    return output


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def cmd_info(args: argparse.Namespace) -> int:
    work = Path(args.dir)
    try:
        check_platform()
    except FwError as exc:
        print(f"[!] {exc}")
    print(f"{'#':>2}  {'offset':>10}  {'size':>10}  label")
    for part in PARTS:
        print(f"{part.index:>2}  0x{part.offset:08X}  {part.size:>10}  {part.label}")
    firmware = work / FIRMWARE
    if firmware.is_file():
        data = read_flash(firmware)
        print(f"\n{firmware.name}: {len(data)} bytes, sha256 {sha256_short(data)}...")
        for ok, text in check_layout(data):
            print(("[OK]   " if ok else "[FAIL] ") + text)
    else:
        print(f"\n({firmware} not found, skipping magic-byte check)")
    print()
    for tool in ("unsquashfs", "mksquashfs", "binwalk"):
        path = tool_path(tool)
        if path:
            print(f"{tool}: {path}")
        else:
            pkg = REQUIRED_TOOLS.get(tool)
            hint = f" (sudo apt install {pkg})" if pkg else " (optional)"
            print(f"{tool}: not found{hint}")
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    rep = Reporter()
    try:
        extract(Path(args.dir), rep, force=args.force)
    except FwError as exc:
        rep.log(str(exc), "error")
        return 1
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    rep = Reporter()
    try:
        build(Path(args.dir), rep)
    except FwError as exc:
        rep.log(str(exc), "error")
        return 1
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", default=str(HERE), help="firmware working directory (default: script directory)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("info", help="show the flash layout and validate magic bytes")

    p_extract = sub.add_parser("extract", help="split firmware.bin and unpack the rootfs")
    p_extract.add_argument("-f", "--force", action="store_true", help="overwrite an existing firmware_extract/")

    sub.add_parser("build", help="repack the rootfs and reassemble cfw.bin")

    args = parser.parse_args(argv)
    handlers: dict[str, Callable[[argparse.Namespace], int]] = {
        "info": cmd_info,
        "extract": cmd_extract,
        "build": cmd_build,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
