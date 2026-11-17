"""Textual TUI for fwtool. Imported lazily by fwtool.py when no subcommand is given."""
from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Footer, Header, Log, ProgressBar, Static

import fwtool
from fwtool import FwError, PARTS, Reporter, build, check_layout, extract, read_flash, tool_path


class TuiReporter(Reporter):
    def __init__(self, log_widget: Log, bar: ProgressBar) -> None:
        self.log_widget = log_widget
        self.bar = bar

    def log(self, msg: str, level: str = "info") -> None:
        style = {"ok": "[green]+[/]", "warn": "[yellow]![/]", "error": "[red]x[/]", "cmd": " ", "info": "*"}
        self.log_widget.write_line(f"{style.get(level, '*')} {msg}")

    def progress(self, fraction: float, label: str = "") -> None:
        self.bar.update(total=100, progress=round(fraction * 100))


class FwToolApp(App):
    CSS = """
    Screen { layout: vertical; }
    #body { height: 1fr; }
    #layout { width: 60%; border: round $primary; }
    #side { width: 40%; }
    #actions { height: auto; padding: 1; border: round $primary; }
    #log { height: 1fr; border: round $primary; }
    Button { margin: 0 1 1 0; }
    #status { padding: 0 1; height: auto; }
    """
    BINDINGS = [
        ("i", "do_info", "Info"),
        ("e", "do_extract", "Extract"),
        ("b", "do_build", "Build"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, work: Path) -> None:
        super().__init__()
        self.work = work

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="body"):
            with Vertical(id="layout"):
                yield Static(f" Flash layout - {self.work / fwtool.FIRMWARE}", id="layout-title")
                yield DataTable(id="table")
            with Vertical(id="side"):
                with Vertical(id="actions"):
                    yield Static(id="status")
                    yield ProgressBar(id="bar", show_eta=False)
                    with Horizontal():
                        yield Button("Extract (e)", id="extract", variant="primary")
                        yield Button("Build (b)", id="build", variant="success")
                        yield Button("Refresh (i)", id="info")
                yield Log(id="log", highlight=True)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#table", DataTable)
        table.add_columns("#", "offset", "size", "label")
        self.action_do_info()

    def _reporter(self) -> TuiReporter:
        return TuiReporter(self.query_one("#log", Log), self.query_one("#bar", ProgressBar))

    def _set_status(self, text: str) -> None:
        self.query_one("#status", Static).update(text)

    def action_do_info(self) -> None:
        table = self.query_one("#table", DataTable)
        table.clear()
        for part in PARTS:
            table.add_row(str(part.index), f"0x{part.offset:06X}", str(part.size), part.label)

        log_widget = self.query_one("#log", Log)
        firmware = self.work / fwtool.FIRMWARE
        if firmware.is_file():
            try:
                data = read_flash(firmware)
            except FwError as exc:
                self._set_status(f"[red]{exc}[/]")
                return
            log_widget.write_line(f"* {firmware.name}: {len(data)} bytes")
            for ok, text in check_layout(data):
                log_widget.write_line(("[green]OK[/]   " if ok else "[red]FAIL[/] ") + text)
        else:
            log_widget.write_line(f"! {firmware} not found")

        tools = ", ".join(f"{t}={'yes' if tool_path(t) else 'no'}" for t in ("unsquashfs", "mksquashfs"))
        self._set_status(f"Ready. Tools: {tools}")

    def action_do_extract(self) -> None:
        self._set_status("[yellow]Extracting...[/]")
        try:
            extract(self.work, self._reporter(), force=True)
        except FwError as exc:
            self._set_status(f"[red]Extract failed: {exc}[/]")
            return
        self._set_status("[green]Extract done.[/]")

    def action_do_build(self) -> None:
        self._set_status("[yellow]Building...[/]")
        try:
            out = build(self.work, self._reporter())
        except FwError as exc:
            self._set_status(f"[red]Build failed: {exc}[/]")
            return
        self._set_status(f"[green]Built {out.name}.[/]")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        {"extract": self.action_do_extract, "build": self.action_do_build, "info": self.action_do_info}[
            event.button.id
        ]()


def run(work: Path) -> int:
    FwToolApp(work).run()
    return 0
