from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

APP_NAME = "TheRootLibrary"
PLATFORM_TOOLS_URL = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
INSTALL_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME / "platform-tools"
console = Console()


def clear_screen() -> None:
    console.clear()


def header() -> None:
    console.print(
        Panel.fit(
            "[bold cyan]THE ROOT LIBRARY[/bold cyan]\n"
            "[dim]Windows rooting companion • ADB setup & device status[/dim]",
            border_style="cyan",
            padding=(1, 4),
        )
    )


def find_adb() -> Path | None:
    local_adb = INSTALL_DIR / "adb.exe"
    if local_adb.is_file():
        return local_adb
    system_adb = shutil.which("adb")
    return Path(system_adb) if system_adb else None


def run_adb(adb: Path, *args: str, timeout: int = 15) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(adb), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def install_platform_tools() -> Path:
    if os.name != "nt":
        raise RuntimeError("This first version supports Windows only.")

    INSTALL_DIR.parent.mkdir(parents=True, exist_ok=True)
    console.print("[cyan]Downloading official Android Platform Tools from Google…[/cyan]")
    request = urllib.request.Request(
        PLATFORM_TOOLS_URL,
        headers={"User-Agent": "TheRootLibrary/0.1"},
    )

    with tempfile.TemporaryDirectory(prefix="rootlibrary-") as temporary:
        temp_dir = Path(temporary)
        archive = temp_dir / "platform-tools.zip"
        with urllib.request.urlopen(request, timeout=60) as response, archive.open("wb") as output:
            shutil.copyfileobj(response, output)

        extracted = temp_dir / "extracted"
        extracted.mkdir()
        with zipfile.ZipFile(archive) as bundle:
            root = extracted.resolve()
            for member in bundle.infolist():
                destination = (extracted / member.filename).resolve()
                if destination != root and root not in destination.parents:
                    raise RuntimeError("The downloaded archive contains an unsafe file path.")
            bundle.extractall(extracted)

        source_dir = extracted / "platform-tools"
        if not (source_dir / "adb.exe").is_file():
            raise RuntimeError("The downloaded archive did not contain adb.exe.")

        INSTALL_DIR.mkdir(parents=True, exist_ok=True)
        for filename in ("adb.exe", "AdbWinApi.dll", "AdbWinUsbApi.dll", "fastboot.exe"):
            source = source_dir / filename
            if source.is_file():
                shutil.copy2(source, INSTALL_DIR / filename)

    console.print(f"[green]✓[/green] Platform Tools installed to [bold]{INSTALL_DIR}[/bold]")
    return INSTALL_DIR / "adb.exe"


def show_adb_status() -> None:
    clear_screen()
    header()
    adb = find_adb()
    if not adb:
        console.print(
            Panel(
                "[yellow]ADB was not found.[/yellow]\n"
                "Choose [bold]Install / update ADB[/bold] from the main menu first.",
                border_style="yellow",
            )
        )
        pause()
        return

    try:
        result = run_adb(adb, "version")
    except (OSError, subprocess.TimeoutExpired) as exc:
        console.print(f"[red]Could not run ADB:[/red] {exc}")
        pause()
        return

    if result.returncode != 0:
        console.print(f"[red]ADB returned an error:[/red] {result.stderr.strip() or result.stdout.strip()}")
        pause()
        return

    console.print(f"[green]ADB executable:[/green] {adb}")
    console.print(f"[green]{result.stdout.splitlines()[0] if result.stdout else 'ADB is available'}[/green]\n")

    try:
        devices = run_adb(adb, "devices", "-l")
    except (OSError, subprocess.TimeoutExpired) as exc:
        console.print(f"[red]Device query failed:[/red] {exc}")
        pause()
        return

    table = Table(title="Connected ADB devices", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("Serial", style="bold")
    table.add_column("Status")
    table.add_column("Details", overflow="fold")
    rows = [
        line.strip()
        for line in devices.stdout.splitlines()[1:]
        if line.strip() and not line.lower().startswith("list of devices")
    ]

    if not rows:
        console.print("[yellow]No ADB devices detected.[/yellow]")
        console.print(
            "[dim]For a Quest: enable Developer Mode, connect USB, put on the headset, "
            "and accept the USB debugging prompt. Wireless ADB is not configured by this tool.[/dim]"
        )
    else:
        for line in rows:
            parts = line.split()
            serial = parts[0]
            status = parts[1] if len(parts) > 1 else "unknown"
            details = " ".join(parts[2:])
            if status == "device":
                status_text = "[green]ready[/green]"
            elif status == "unauthorized":
                status_text = "[yellow]unauthorized — check headset prompt[/yellow]"
            elif status == "offline":
                status_text = "[red]offline[/red]"
            else:
                status_text = status
            table.add_row(serial, status_text, details)
        console.print(table)

    if devices.returncode != 0:
        console.print(f"[red]{devices.stderr.strip()}[/red]")
    pause()


def pause() -> None:
    console.input("\n[dim]Press Enter to return to the menu…[/dim]")


def main_menu() -> None:
    while True:
        clear_screen()
        header()
        adb = find_adb()
        if adb:
            console.print(f"[green]● ADB available[/green] [dim]({adb})[/dim]\n")
        else:
            console.print("[yellow]● ADB not installed[/yellow]\n")

        menu = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
        menu.add_column("Key", style="bold cyan", width=5)
        menu.add_column("Action")
        menu.add_row("1", "Install / update official Android Platform Tools")
        menu.add_row("2", "Check ADB and connected devices")
        menu.add_row("3", "About & safety")
        menu.add_row("Q", "Quit")
        console.print(menu)

        choice = console.input("\n[bold cyan]Select an option › [/bold cyan]").strip().lower()
        if choice == "1":
            clear_screen()
            header()
            try:
                install_platform_tools()
                console.print("[green]ADB setup complete.[/green]")
            except (OSError, urllib.error.URLError, zipfile.BadZipFile, RuntimeError) as exc:
                console.print(f"[red]Installation failed:[/red] {exc}")
            pause()
        elif choice == "2":
            show_adb_status()
        elif choice == "3":
            clear_screen()
            header()
            console.print(
                Panel(
                    "This utility currently installs Google's official Android Platform Tools "
                    "and reports ADB device status. It does not root devices, unlock bootloaders, "
                    "flash images, or write to system partitions.\n\n"
                    "Only approve USB debugging for computers you trust. Rooting and device "
                    "modification are separate steps and are not performed here.",
                    title="About & safety",
                    border_style="cyan",
                )
            )
            pause()
        elif choice in {"q", "quit", "exit"}:
            console.print("[dim]Stay safe, and happy tinkering.[/dim]")
            return
        else:
            console.print("[yellow]Unknown option.[/yellow]")
            pause()


if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        console.print("\n[dim]Exited.[/dim]")
        sys.exit(0)
