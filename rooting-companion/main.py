from __future__ import annotations

import os
import json
import lzma
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import urllib.parse
import urllib.error
import zipfile
from pathlib import Path

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

APP_NAME = "TheRootLibrary"
PLATFORM_TOOLS_URL = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
INSTALL_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME / "platform-tools"
MOD_INSTALL_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME / "mods"
MODS_BASE_URL = "https://raw.githubusercontent.com/alexdoesprogramming/TheRootLibrary/main/"
MOD_ARCHIVES = [
    "Big Scary Root (1).zip",
    "Bwah (2).zip",
    "Creepy Baboon.zip",
    "Fearing Gorilla (1).zip",
    "GTAG (1).zip",
    "Lethal Ape Redu.zip",
    "Lethal Ape Redux (1).zip",
    "Sandbox.zip",
    "Scary Baboon (1).zip",
    "Teddys Pizza.zip",
]
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



def install_frida_server() -> None:
    """Download the matching official Frida server binary beside adb.exe."""
    clear_screen()
    header()
    adb = find_adb()
    if not adb:
        console.print("[yellow]ADB is not installed. Install Platform Tools first.[/yellow]")
        pause()
        return

    try:
        result = run_adb(adb, "devices")
    except (OSError, subprocess.TimeoutExpired) as exc:
        console.print(f"[red]Could not query ADB devices:[/red] {exc}")
        pause()
        return

    devices = []
    for line in result.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            devices.append(parts[0])

    if not devices:
        console.print("[yellow]No authorized ADB device detected.[/yellow]")
        console.print("[dim]Connect the headset/device, accept the USB debugging prompt, and retry.[/dim]")
        pause()
        return

    if len(devices) == 1:
        serial = devices[0]
    else:
        console.print("[bold]Choose the target device:[/bold]")
        for index, serial_value in enumerate(devices, start=1):
            console.print(f"  [cyan]{index}.[/cyan] {serial_value}")
        choice = console.input("Device number (or B to cancel) › ").strip().lower()
        if choice in {"b", "back", "q"}:
            return
        if not choice.isdigit() or not 1 <= int(choice) <= len(devices):
            console.print("[yellow]Invalid selection.[/yellow]")
            pause()
            return
        serial = devices[int(choice) - 1]

    try:
        abi_result = run_adb(adb, "-s", serial, "shell", "getprop", "ro.product.cpu.abi")
    except (OSError, subprocess.TimeoutExpired) as exc:
        console.print(f"[red]Could not read device architecture:[/red] {exc}")
        pause()
        return
    abi = abi_result.stdout.strip().splitlines()[0] if abi_result.stdout.strip() else ""
    abi_map = {
        "arm64-v8a": "android-arm64",
        "armeabi-v7a": "android-arm",
        "armeabi": "android-arm",
        "x86_64": "android-x86_64",
        "x86": "android-x86",
    }
    frida_arch = abi_map.get(abi)
    if not frida_arch:
        console.print(f"[red]Unsupported or unknown Android ABI:[/red] {abi or 'not reported'}")
        pause()
        return

    # Prefer the Frida client version available on this PC; server/client versions should match.
    client_version = None
    frida_client = shutil.which("frida")
    if frida_client:
        try:
            client_result = subprocess.run(
                [frida_client, "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if client_result.returncode == 0:
                client_version = client_result.stdout.strip().splitlines()[0].strip().lstrip("v")
        except (OSError, subprocess.TimeoutExpired):
            pass

    api_headers = {
        "User-Agent": "TheRootLibrary/0.3",
        "Accept": "application/vnd.github+json",
    }
    release_url = (
        f"https://api.github.com/repos/frida/frida/releases/tags/{urllib.parse.quote(client_version)}"
        if client_version
        else "https://api.github.com/repos/frida/frida/releases/latest"
    )
    try:
        request = urllib.request.Request(release_url, headers=api_headers)
        with urllib.request.urlopen(request, timeout=30) as response:
            release = json.load(response)
        tag = str(release.get("tag_name", "")).lstrip("v")
        expected_name = f"frida-server-{tag}-{frida_arch}.xz"
        assets = release.get("assets", [])
        asset = next((item for item in assets if item.get("name") == expected_name), None)
        if not asset:
            raise RuntimeError(
                f"Official Frida release {tag or '(unknown)'} has no asset named {expected_name}."
            )
        asset_url = asset.get("browser_download_url")
        if not asset_url or not asset_url.startswith("https://github.com/frida/frida/releases/"):
            raise RuntimeError("The release asset URL was missing or unexpected.")

        console.print(f"[cyan]Device:[/cyan] {serial}  [cyan]ABI:[/cyan] {abi}")
        console.print(f"[cyan]Frida server version:[/cyan] {tag}")
        if not client_version:
            console.print(
                "[yellow]No Frida client was found on PATH. Use a matching Frida client version "
                "before connecting to this server.[/yellow]"
            )
        elif tag != client_version:
            console.print(
                f"[yellow]Client version {client_version} differs from server version {tag}; "
                "connections may fail.[/yellow]"
            )

        destination = INSTALL_DIR / "frida-server"
        if destination.exists():
            confirm_replace = console.input(
                f"[yellow]{destination} already exists. Replace it? [y/N] [/yellow]"
            ).strip().lower()
            if confirm_replace != "y":
                console.print("[dim]Cancelled; existing file was left untouched.[/dim]")
                pause()
                return

        INSTALL_DIR.mkdir(parents=True, exist_ok=True)
        compressed_path = INSTALL_DIR / "frida-server.xz"
        console.print("[cyan]Downloading official Frida server release…[/cyan]")
        request = urllib.request.Request(asset_url, headers={"User-Agent": "TheRootLibrary/0.3"})
        with urllib.request.urlopen(request, timeout=60) as response, compressed_path.open("wb") as output:
            shutil.copyfileobj(response, output)

        temporary_binary = INSTALL_DIR / "frida-server.tmp"
        try:
            with lzma.open(compressed_path, "rb") as compressed, temporary_binary.open("wb") as output:
                shutil.copyfileobj(compressed, output)
            if temporary_binary.stat().st_size == 0:
                raise RuntimeError("The decompressed Frida server binary is empty.")
            temporary_binary.replace(destination)
        finally:
            compressed_path.unlink(missing_ok=True)
            temporary_binary.unlink(missing_ok=True)

        console.print(f"[green]✓ Frida server installed beside ADB:[/green] {destination}")
        console.print(
            "[dim]This only places the Android binary on your PC. It does not push or start "
            "Frida server on the device.[/dim]"
        )
    except (OSError, urllib.error.URLError, json.JSONDecodeError, lzma.LZMAError, RuntimeError) as exc:
        console.print(f"[red]Frida server installation failed:[/red] {exc}")
    pause()


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



def safe_extract_zip(archive: Path, destination: Path) -> None:
    """Extract a ZIP while rejecting paths that escape the destination."""
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            target = (destination / member.filename).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError(f"Unsafe path in ZIP archive: {member.filename}")
        bundle.extractall(destination)


def download_mod_archive(filename: str) -> Path:
    MOD_INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = MOD_INSTALL_DIR / filename
    url = MODS_BASE_URL + urllib.parse.quote(filename)
    request = urllib.request.Request(url, headers={"User-Agent": "TheRootLibrary/0.2"})
    console.print(f"[cyan]Downloading {filename} from TheRootLibrary…[/cyan]")
    with urllib.request.urlopen(request, timeout=60) as response, archive_path.open("wb") as output:
        shutil.copyfileobj(response, output)
    if not zipfile.is_zipfile(archive_path):
        archive_path.unlink(missing_ok=True)
        raise RuntimeError("The downloaded file is not a valid ZIP archive.")
    return archive_path


def choose_and_run_mod() -> None:
    clear_screen()
    header()
    console.print(
        Panel(
            "[yellow]Mod ZIPs can contain scripts that modify your headset or PC.[/yellow]\n"
            "Only run a mod you trust. The selected ZIP will be extracted locally, "
            "then you will choose a BAT file to run. This tool will not automatically elevate privileges.",
            title="Mod launcher safety",
            border_style="yellow",
        )
    )
    table = Table(title="Mods in TheRootLibrary", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("#", style="bold cyan", width=4)
    table.add_column("Mod archive")
    for index, filename in enumerate(MOD_ARCHIVES, start=1):
        table.add_row(str(index), filename)
    console.print(table)
    console.print("[dim]B = back to menu[/dim]")
    choice = console.input("\n[bold cyan]Select a mod › [/bold cyan]").strip().lower()
    if choice in {"b", "back", "q", "quit"}:
        return
    if not choice.isdigit() or not 1 <= int(choice) <= len(MOD_ARCHIVES):
        console.print("[yellow]Invalid selection.[/yellow]")
        pause()
        return

    filename = MOD_ARCHIVES[int(choice) - 1]
    try:
        archive = download_mod_archive(filename)
        extract_dir = MOD_INSTALL_DIR / Path(filename).stem
        if extract_dir.exists():
            console.print(f"[yellow]Existing extraction found:[/yellow] {extract_dir}")
            overwrite = console.input("Delete and re-extract this folder? [y/N] ").strip().lower()
            if overwrite != "y":
                console.print("[dim]Cancelled; existing files were left untouched.[/dim]")
                pause()
                return
            shutil.rmtree(extract_dir)
        safe_extract_zip(archive, extract_dir)
    except (OSError, urllib.error.URLError, zipfile.BadZipFile, RuntimeError) as exc:
        console.print(f"[red]Could not prepare mod:[/red] {exc}")
        pause()
        return

    batch_files = sorted(
        (path for path in extract_dir.rglob("*") if path.is_file() and path.suffix.lower() == ".bat"),
        key=lambda path: str(path).lower(),
    )
    if not batch_files:
        console.print("[yellow]No .bat file was found in this archive.[/yellow]")
        console.print(f"[dim]Extracted files are in: {extract_dir}[/dim]")
        pause()
        return

    console.print(f"\n[green]Extracted to:[/green] {extract_dir}")
    console.print("[bold]Batch files found:[/bold]")
    for index, batch_file in enumerate(batch_files, start=1):
        console.print(f"  [cyan]{index}.[/cyan] {batch_file.relative_to(extract_dir)}")
    selected = "1"
    if len(batch_files) > 1:
        selected = console.input("\nSelect the BAT to run (or B to cancel) › ").strip().lower()
        if selected in {"b", "back", "q", "quit"}:
            return
        if not selected.isdigit() or not 1 <= int(selected) <= len(batch_files):
            console.print("[yellow]Invalid selection.[/yellow]")
            pause()
            return

    batch_file = batch_files[int(selected) - 1]
    console.print(
        Panel(
            f"[bold]{batch_file.relative_to(extract_dir)}[/bold]\n\n"
            "This runs the selected Windows batch script. Review the script first if you do not "
            "know what it does. The script may use ADB or make changes outside this application.",
            title="Confirm execution",
            border_style="red",
        )
    )
    confirm = console.input("Run this BAT now? Type RUN to confirm › ").strip()
    if confirm != "RUN":
        console.print("[dim]Cancelled. Nothing was executed.[/dim]")
        pause()
        return

    try:
        console.print("[cyan]Launching batch file…[/cyan]")
        completed = subprocess.run(
            ["cmd.exe", "/c", str(batch_file)],
            cwd=str(batch_file.parent),
            check=False,
        )
        console.print(f"\n[dim]Batch process exited with code {completed.returncode}.[/dim]")
    except OSError as exc:
        console.print(f"[red]Could not launch batch file:[/red] {exc}")
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
        menu.add_row("3", "Browse, extract & run a mod ZIP")
        menu.add_row("4", "Install Frida server into Platform Tools")
        menu.add_row("5", "About & safety")
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
            choose_and_run_mod()
        elif choice == "4":
            install_frida_server()
        elif choice == "5":
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
