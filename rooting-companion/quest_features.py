from __future__ import annotations

import json
import os
import platform
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Callable

from rich import box
from rich.panel import Panel
from rich.table import Table

APP_DATA = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "TheRootLibrary"
QUEST_DB = APP_DATA / "quest_firmware_db.json"
REPORT_DIR = APP_DATA / "reports"
LOG_DIR = APP_DATA / "logs"

# Empty by design: builds are not called supported until a maintainer/user records evidence.
DEFAULT_DB = {"schema": 1, "builds": []}
QUEST_PROPERTIES = {
    "ro.product.model": "Model",
    "ro.product.device": "Device codename",
    "ro.product.manufacturer": "Manufacturer",
    "ro.build.display.id": "Build display ID",
    "ro.build.fingerprint": "Build fingerprint",
    "ro.build.version.release": "Android version",
    "ro.build.version.sdk": "Android SDK",
    "ro.build.version.security_patch": "Security patch",
    "ro.product.cpu.abi": "CPU ABI",
    "ro.boot.verifiedbootstate": "Verified boot state",
}


def _run(adb: Path, serial: str, *args: str, timeout: int = 20):
    return subprocess.run(
        [str(adb), "-s", serial, *args], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout, check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def _devices(adb: Path) -> list[tuple[str, str]]:
    result = subprocess.run(
        [str(adb), "devices"], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=15, check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    found = []
    for line in result.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2:
            found.append((parts[0], parts[1]))
    return found


def _choose_device(adb: Path, console) -> str | None:
    try:
        devices = [(serial, state) for serial, state in _devices(adb) if state == "device"]
    except (OSError, subprocess.TimeoutExpired) as exc:
        console.print(f"[red]ADB device query failed:[/red] {exc}")
        return None
    if not devices:
        console.print("[yellow]No authorized ADB device found. Check Developer Mode, the debugging prompt, and the cable/network.[/yellow]")
        return None
    if len(devices) == 1:
        return devices[0][0]
    table = Table(title="Authorized ADB devices", box=box.ROUNDED)
    table.add_column("#", style="cyan")
    table.add_column("Serial")
    for i, (serial, _) in enumerate(devices, 1):
        table.add_row(str(i), serial)
    console.print(table)
    choice = console.input("Device number (B to cancel) › ").strip().lower()
    if choice in {"b", "back", "q"}:
        return None
    if choice.isdigit() and 1 <= int(choice) <= len(devices):
        return devices[int(choice) - 1][0]
    console.print("[yellow]Invalid selection.[/yellow]")
    return None


def _properties(adb: Path, serial: str) -> dict[str, str]:
    values = {}
    for prop, label in QUEST_PROPERTIES.items():
        try:
            result = _run(adb, serial, "shell", "getprop", prop, timeout=10)
            values[label] = result.stdout.strip() or "(not reported)"
        except (OSError, subprocess.TimeoutExpired):
            values[label] = "(query failed)"
    return values


def _load_db() -> dict:
    APP_DATA.mkdir(parents=True, exist_ok=True)
    if not QUEST_DB.exists():
        return dict(DEFAULT_DB)
    try:
        data = json.loads(QUEST_DB.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("builds"), list):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return dict(DEFAULT_DB)


def _save_db(data: dict) -> None:
    APP_DATA.mkdir(parents=True, exist_ok=True)
    temp = QUEST_DB.with_suffix(".json.tmp")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(QUEST_DB)


def _compat_status(build: str) -> tuple[str, str]:
    data = _load_db()
    for item in data.get("builds", []):
        if str(item.get("build", "")).strip().lower() == build.strip().lower():
            status = str(item.get("status", "unknown")).lower()
            notes = str(item.get("notes", ""))
            return status.upper(), notes
    return "UNKNOWN / UNTESTED", "No entry for this exact build is in the local database."


def _report_path(prefix: str, suffix: str = ".txt") -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return REPORT_DIR / f"{prefix}-{stamp}{suffix}"


def inspect_quest(adb: Path, console, pause: Callable[[], None]) -> None:
    console.clear()
    console.print(Panel("Quest build fingerprint, device properties, and compatibility status", title="Quest Inspector", border_style="cyan"))
    serial = _choose_device(adb, console)
    if not serial:
        pause()
        return
    try:
        props = _properties(adb, serial)
        build = props.get("Build display ID", "")
        status, notes = _compat_status(build)
        table = Table(title=f"Quest details — {serial}", box=box.ROUNDED, header_style="bold cyan")
        table.add_column("Property")
        table.add_column("Value", overflow="fold")
        for key, value in props.items():
            table.add_row(key, value)
        table.add_row("Local compatibility record", status)
        console.print(table)
        console.print(f"[dim]Database note: {notes or 'No notes recorded.'}[/dim]")
        console.print(Panel("Compatibility labels are community/local records, not proof an exploit is safe. UNKNOWN means this tool has no verified record; it does not mean impossible.", border_style="yellow"))
        save = console.input("Save these details as a diagnostic report? [y/N] ").strip().lower()
        if save == "y":
            path = _report_path("quest-inspector")
            path.write_text(
                f"TheRootLibrary Quest Inspector\nTime: {datetime.now().isoformat(timespec='seconds')}\nSerial: {serial}\n\n"
                + "\n".join(f"{k}: {v}" for k, v in props.items())
                + f"\nLocal compatibility: {status}\nDatabase note: {notes}\n",
                encoding="utf-8",
            )
            console.print(f"[green]Saved:[/green] {path}")
    except (OSError, subprocess.TimeoutExpired) as exc:
        console.print(f"[red]Inspection failed:[/red] {exc}")
    pause()


def root_status(adb: Path, console, pause: Callable[[], None]) -> None:
    console.clear()
    console.print(Panel("Read-only checks for temporary root, Singularity, and Frida", title="Root Status", border_style="cyan"))
    serial = _choose_device(adb, console)
    if not serial:
        pause()
        return
    checks = []
    try:
        su = _run(adb, serial, "shell", "su", "-c", "id", timeout=10)
        root_ok = su.returncode == 0 and "uid=0" in su.stdout
        checks.append(("Root check (su -c id)", "ROOT ACCESS CONFIRMED" if root_ok else "Not confirmed / unavailable"))
        frida = _run(adb, serial, "shell", "pidof", "frida-server", timeout=10)
        checks.append(("Frida server", f"Running (PID {frida.stdout.strip()})" if frida.returncode == 0 and frida.stdout.strip() else "Not detected"))
        packages = _run(adb, serial, "shell", "pm", "list", "packages", timeout=20)
        found = [line.strip().removeprefix("package:") for line in packages.stdout.splitlines() if "singularity" in line.lower()]
        checks.append(("Singularity package", ", ".join(found) if found else "Not detected (package-name search)"))
        for label, value in checks:
            color = "green" if "CONFIRMED" in value or "Running" in value else "yellow"
            console.print(f"[bold]{label}:[/bold] [{color}]{value}[/{color}]")
        console.print("\n[dim]A failed su check does not prove the exploit is unsupported; temporary root may not be active, or su may not be exposed to ADB shell.[/dim]")
    except (OSError, subprocess.TimeoutExpired) as exc:
        console.print(f"[red]Status check failed:[/red] {exc}")
    pause()


def manage_firmware_db(console, pause: Callable[[], None]) -> None:
    while True:
        console.clear()
        console.print(Panel(f"Local Quest firmware database\n{QUEST_DB}", title="Firmware / Exploit Status", border_style="cyan"))
        data = _load_db()
        table = Table(box=box.ROUNDED, header_style="bold cyan")
        table.add_column("Build")
        table.add_column("Status")
        table.add_column("Model")
        table.add_column("Notes", overflow="fold")
        for item in data.get("builds", []):
            table.add_row(str(item.get("build", "")), str(item.get("status", "unknown")).upper(),
                          str(item.get("model", "Any")), str(item.get("notes", "")))
        if not data.get("builds"):
            console.print("[yellow]No builds recorded yet. Unknown builds are never automatically marked supported.[/yellow]")
        else:
            console.print(table)
        console.print("1. Add/update a build record   2. Export database JSON   B. Back")
        choice = console.input("Select › ").strip().lower()
        if choice in {"b", "q", "back"}:
            return
        if choice == "1":
            build = console.input("Exact build display ID (required) › ").strip()
            if not build:
                console.print("[yellow]Build ID cannot be empty.[/yellow]")
                pause()
                continue
            model = console.input("Model (e.g. Quest 2; optional) › ").strip() or "Any"
            console.print("Status options: supported, reported, patched, unsupported, unknown")
            status = console.input("Evidence status › ").strip().lower()
            if status not in {"supported", "reported", "patched", "unsupported", "unknown"}:
                console.print("[yellow]Invalid status.[/yellow]")
                pause()
                continue
            notes = console.input("Evidence/source notes (include link if available) › ").strip()
            builds = data.get("builds", [])
            existing = next((item for item in builds if str(item.get("build", "")).lower() == build.lower()), None)
            record = {"build": build, "model": model, "status": status, "notes": notes, "updated": datetime.now().date().isoformat()}
            if existing is None:
                builds.append(record)
            else:
                existing.update(record)
            data["builds"] = builds
            _save_db(data)
            console.print("[green]Firmware record saved locally.[/green]")
            pause()
        elif choice == "2":
            path = _report_path("quest-firmware-database", ".json")
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            console.print(f"[green]Exported:[/green] {path}")
            pause()


def quest_diagnostics(adb: Path, console, pause: Callable[[], None]) -> None:
    console.clear()
    console.print(Panel("ADB environment, headset properties, root state, and selected log output", title="Quest Diagnostics", border_style="cyan"))
    serial = _choose_device(adb, console)
    if not serial:
        pause()
        return
    lines = [f"TheRootLibrary Quest Diagnostics", f"Time: {datetime.now().isoformat(timespec='seconds')}",
             f"Computer: {platform.platform()}", f"ADB: {adb}", f"Serial: {serial}", ""]
    try:
        version = subprocess.run([str(adb), "version"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10, check=False)
        lines.extend(["ADB VERSION", version.stdout.strip(), ""])
        lines.extend(["QUEST PROPERTIES"])
        lines.extend(f"{k}: {v}" for k, v in _properties(adb, serial).items())
        lines.append("")
        su = _run(adb, serial, "shell", "su", "-c", "id", timeout=10)
        lines.extend(["ROOT CHECK", su.stdout.strip() or su.stderr.strip() or f"exit code {su.returncode}", ""])
        frida = _run(adb, serial, "shell", "pidof", "frida-server", timeout=10)
        lines.extend(["FRIDA SERVER", frida.stdout.strip() or "not detected", ""])
        logs = _run(adb, serial, "logcat", "-d", "-t", "2000", timeout=60)
        patterns = re.compile(r"unity|il2cpp|fatal|exception|crash|frida|singularity|root", re.I)
        selected_logs = [line for line in logs.stdout.splitlines() if patterns.search(line)]
        lines.extend(["FILTERED LOGCAT (up to 2000 recent lines queried)", *selected_logs[-1000:]])
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = _report_path("quest-diagnostics")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        console.print(f"[green]Diagnostic report saved:[/green] {path}")
        console.print(f"Filtered log lines included: {min(len(selected_logs), 1000)}")
        console.print("[dim]Reports can contain device identifiers, app names, and private log data. Review before sharing.[/dim]")
    except (OSError, subprocess.TimeoutExpired) as exc:
        console.print(f"[red]Diagnostics failed:[/red] {exc}")
    pause()


def inspect_apps(adb: Path, console, pause: Callable[[], None]) -> None:
    console.clear()
    console.print(Panel("List installed package IDs and inspect an app's APK paths/metadata for modding research.", title="IL2CPP / App Inspector", border_style="cyan"))
    serial = _choose_device(adb, console)
    if not serial:
        pause()
        return
    try:
        result = _run(adb, serial, "shell", "pm", "list", "packages", timeout=30)
        packages = sorted(line.strip().removeprefix("package:") for line in result.stdout.splitlines() if line.startswith("package:"))
        query = console.input("Filter package IDs (blank shows all) › ").strip().lower()
        matches = [p for p in packages if query in p.lower()]
        table = Table(title=f"Packages ({len(matches)} shown)", box=box.ROUNDED)
        table.add_column("#", style="cyan")
        table.add_column("Package ID", overflow="fold")
        for i, package in enumerate(matches[:200], 1):
            table.add_row(str(i), package)
        console.print(table)
        if not matches:
            console.print("[yellow]No package IDs matched.[/yellow]")
            pause()
            return
        selected = console.input("Enter package ID to inspect (blank to return) › ").strip()
        if not selected:
            pause()
            return
        if selected not in packages:
            console.print("[yellow]That package is not in the device package list.[/yellow]")
            pause()
            return
        details = _run(adb, serial, "shell", "dumpsys", "package", selected, timeout=30)
        paths = _run(adb, serial, "shell", "pm", "path", selected, timeout=15)
        path = _report_path("app-inspector")
        path.write_text(
            f"Package: {selected}\nDevice: {serial}\nTime: {datetime.now().isoformat(timespec='seconds')}\n\nAPK paths:\n{paths.stdout}\n\nPackage metadata:\n{details.stdout}\n",
            encoding="utf-8",
        )
        console.print(f"[green]Package metadata saved:[/green] {path}")
        console.print("[dim]This collects metadata only; it does not dump protected app memory or bypass app security.[/dim]")
    except (OSError, subprocess.TimeoutExpired) as exc:
        console.print(f"[red]App inspection failed:[/red] {exc}")
    pause()


def frida_diagnostics(adb: Path, install_dir: Path, console, pause: Callable[[], None]) -> None:
    console.clear()
    console.print(Panel("Check local Frida client/server files and the selected Quest's process state.", title="Frida Toolkit", border_style="cyan"))
    client = None
    try:
        client = subprocess.run(["frida", "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        pass
    server = install_dir / "frida-server"
    console.print(f"Frida client on PATH: {client.stdout.strip() if client and client.returncode == 0 else 'not found'}")
    console.print(f"Local server binary: {server if server.is_file() else 'not found'}")
    if server.is_file():
        console.print(f"Server file size: {server.stat().st_size:,} bytes")
    serial = _choose_device(adb, console)
    if serial:
        try:
            pid = _run(adb, serial, "shell", "pidof", "frida-server", timeout=10)
            console.print(f"Headset server: {pid.stdout.strip() if pid.stdout.strip() else 'not detected'}")
            if client and client.returncode == 0 and server.is_file():
                console.print("[dim]Compare the client/server versions; Frida usually requires matching versions.[/dim]")
        except (OSError, subprocess.TimeoutExpired) as exc:
            console.print(f"[red]Device check failed:[/red] {exc}")
    pause()


def wireless_adb(adb: Path, console, pause: Callable[[], None]) -> None:
    console.clear()
    console.print(Panel("Connect to an already-enabled ADB-over-TCP endpoint. This does not enable wireless debugging on the headset.", title="Wireless ADB", border_style="cyan"))
    endpoint = console.input("Headset IP and port (example 192.168.1.10:5555; B to cancel) › ").strip()
    if endpoint.lower() in {"b", "q", "back"}:
        return
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+:\d{1,5}", endpoint):
        console.print("[yellow]Expected host:port format.[/yellow]")
        pause()
        return
    try:
        host, port = endpoint.rsplit(":", 1)
        if not port.isdigit() or not 1 <= int(port) <= 65535:
            raise ValueError
        result = subprocess.run([str(adb), "connect", f"{host}:{port}"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15, check=False)
        console.print(result.stdout.strip() or result.stderr.strip() or f"ADB exited with code {result.returncode}")
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        console.print(f"[red]ADB connect failed:[/red] {exc}")
    pause()


def pcvr_check(console, pause: Callable[[], None]) -> None:
    console.clear()
    console.print(Panel("Read-only check for common PCVR processes on Windows.", title="PCVR Quick Check", border_style="cyan"))
    if os.name != "nt":
        console.print("[yellow]Process-name checks are designed for Windows.[/yellow]")
        pause()
        return
    try:
        result = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15, check=False)
        running = {line.split('","')[0].strip('"').lower() for line in result.stdout.splitlines() if line.strip()}
        targets = {
            "vrserver.exe": "SteamVR server",
            "vrmonitor.exe": "SteamVR monitor",
            "OVRServer_x64.exe": "Meta Quest Link runtime",
            "VirtualDesktop.Streamer.exe": "Virtual Desktop Streamer",
            "ALVR Launcher.exe": "ALVR launcher",
            "ALVR.exe": "ALVR",
            "Discord.exe": "Discord (voice/chat)",
        }
        table = Table(box=box.ROUNDED, header_style="bold cyan")
        table.add_column("Component")
        table.add_column("Status")
        for exe, label in targets.items():
            present = exe.lower() in running
            table.add_row(label, "[green]Running[/green]" if present else "[dim]Not detected[/dim]")
        console.print(table)
        console.print("[dim]Not detected does not mean broken; apps may use different process names or may simply be closed.[/dim]")
    except (OSError, subprocess.TimeoutExpired) as exc:
        console.print(f"[red]PCVR check failed:[/red] {exc}")
    pause()



def quest_live_dashboard(adb: Path, console, pause: Callable[[], None]) -> None:
    """Show a quick read-only snapshot of the selected Quest."""
    console.clear()
    console.print(Panel("Live snapshot of device health and runtime details. Read-only ADB queries.", title="Quest Dashboard", border_style="cyan"))
    serial = _choose_device(adb, console)
    if not serial:
        pause()
        return
    try:
        props = _properties(adb, serial)
        battery = _run(adb, serial, "shell", "dumpsys", "battery", timeout=15)
        storage = _run(adb, serial, "shell", "df", "-h", "/data", timeout=15)
        memory = _run(adb, serial, "shell", "cat", "/proc/meminfo", timeout=15)
        uptime = _run(adb, serial, "shell", "cat", "/proc/uptime", timeout=10)
        table = Table(title=f"Quest status — {serial}", box=box.ROUNDED, header_style="bold cyan")
        table.add_column("Metric")
        table.add_column("Value", overflow="fold")
        for key in ("Model", "Device codename", "Build display ID", "Android version", "Security patch"):
            table.add_row(key, props.get(key, "Not reported"))
        battery_lines = {}
        for line in battery.stdout.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                battery_lines[key.strip()] = value.strip()
        table.add_row("Battery level", battery_lines.get("level", "Not reported") + "%")
        table.add_row("Charging status", battery_lines.get("status", "Not reported"))
        table.add_row("Temperature", (battery_lines.get("temperature", "Not reported") + " (tenths °C)") if battery_lines.get("temperature") else "Not reported")
        storage_lines = [line.strip() for line in storage.stdout.splitlines() if line.strip()]
        table.add_row("Storage (/data)", " | ".join(storage_lines[-1].split()) if len(storage_lines) > 1 else "Not reported")
        mem = {}
        for line in memory.stdout.splitlines():
            match = re.match(r"^(MemTotal|MemAvailable):\\s+(\\d+)\\s+kB", line)
            if match:
                mem[match.group(1)] = int(match.group(2))
        if "MemTotal" in mem:
            total = mem["MemTotal"] / 1024
            available = mem.get("MemAvailable", 0) / 1024
            table.add_row("Memory", f"{available:,.0f} MiB available / {total:,.0f} MiB total")
        table.add_row("Uptime", uptime.stdout.strip().split()[0] + " seconds" if uptime.stdout.strip() else "Not reported")
        console.print(table)
        console.print("[dim]Battery temperature is reported in tenths of a degree Celsius by Android (e.g. 325 = 32.5°C). Values may be unavailable on some firmware.[/dim]")
    except (OSError, subprocess.TimeoutExpired) as exc:
        console.print(f"[red]Dashboard query failed:[/red] {exc}")
    pause()


def capture_quest_screenshot(adb: Path, console, pause: Callable[[], None]) -> None:
    """Save a screenshot captured from the connected Quest to the PC."""
    console.clear()
    console.print(Panel("Capture the headset display and save the PNG on this PC.", title="Quest Screenshot", border_style="cyan"))
    serial = _choose_device(adb, console)
    if not serial:
        pause()
        return
    try:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        path = _report_path("quest-screenshot", ".png")
        result = subprocess.run(
            [str(adb), "-s", serial, "exec-out", "screencap", "-p"],
            capture_output=True, timeout=30, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0 or not result.stdout.startswith(b"\\x89PNG\\r\\n\\x1a\\n"):
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(detail or "ADB did not return a valid PNG screenshot.")
        path.write_bytes(result.stdout)
        console.print(f"[green]Screenshot saved:[/green] {path}")
        console.print("[dim]Check the image before sharing; it may show personal notifications or account information.[/dim]")
    except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
        console.print(f"[red]Screenshot capture failed:[/red] {exc}")
    pause()


def export_app_inventory(adb: Path, console, pause: Callable[[], None]) -> None:
    """Export installed package IDs from the selected Quest as TXT and JSON."""
    console.clear()
    console.print(Panel("Export the installed package list for app inventory and modding research.", title="App Inventory Export", border_style="cyan"))
    serial = _choose_device(adb, console)
    if not serial:
        pause()
        return
    try:
        result = _run(adb, serial, "shell", "pm", "list", "packages", "-3", timeout=30)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Package Manager query failed.")
        packages = sorted(
            line.strip().removeprefix("package:")
            for line in result.stdout.splitlines()
            if line.strip().startswith("package:")
        )
        if not packages:
            console.print("[yellow]No third-party packages were returned; firmware may restrict this query.[/yellow]")
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        txt_path = REPORT_DIR / f"quest-app-inventory-{stamp}.txt"
        json_path = REPORT_DIR / f"quest-app-inventory-{stamp}.json"
        metadata = {
            "device_serial": serial,
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "scope": "third-party packages (pm list packages -3)",
            "count": len(packages),
            "packages": packages,
        }
        txt_path.write_text(
            f"TheRootLibrary — Quest App Inventory\\nDevice: {serial}\\n"
            f"Exported: {metadata['exported_at']}\\nPackages: {len(packages)}\\n\\n"
            + "\\n".join(packages) + "\\n",
            encoding="utf-8",
        )
        json_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
        console.print(f"[green]Exported {len(packages)} package IDs:[/green]")
        console.print(f"  TXT:  {txt_path}")
        console.print(f"  JSON: {json_path}")
    except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
        console.print(f"[red]Inventory export failed:[/red] {exc}")
    pause()

def quest_features_menu(adb: Path | None, install_dir: Path, console, pause: Callable[[], None]) -> None:
    while True:
        console.clear()
        console.print(Panel("Quest-only diagnostics and workflow helpers. No boot/system partition writes.", title="QUEST TOOLKIT", border_style="cyan"))
        menu = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
        menu.add_column("Key", style="bold cyan", width=5)
        menu.add_column("Feature")
        menu.add_row("1", "Quest build fingerprint & compatibility checker")
        menu.add_row("2", "Temporary root / Singularity / Frida status")
        menu.add_row("3", "Firmware & exploit status database")
        menu.add_row("4", "Diagnostic report + filtered logcat export")
        menu.add_row("5", "IL2CPP / app package inspector")
        menu.add_row("6", "Frida client/server diagnostics")
        menu.add_row("7", "Connect to existing wireless ADB endpoint")
        menu.add_row("8", "PCVR runtime quick check")
        menu.add_row("9", "Root persistence & safety guide")
        menu.add_row("10", "Live Quest dashboard (battery, storage, memory)")
        menu.add_row("11", "Capture Quest screenshot to PC")
        menu.add_row("12", "Export installed third-party app inventory")
        menu.add_row("B", "Back to main menu")
        console.print(menu)
        choice = console.input("Select an option › ").strip().lower()
        if choice in {"b", "back", "q"}:
            return
        if choice == "8":
            pcvr_check(console, pause)
            continue
        if choice in {"10", "11", "12"}:
            if adb is None:
                console.print("[yellow]ADB was not found. Install Platform Tools from the main menu first.[/yellow]")
                pause()
                continue
            if choice == "10":
                quest_live_dashboard(adb, console, pause)
            elif choice == "11":
                capture_quest_screenshot(adb, console, pause)
            elif choice == "12":
                export_app_inventory(adb, console, pause)
            continue
        if choice == "9":
            console.clear()
            console.print(Panel(
                "TEMPORARY ROOT NOTES\n\n"
                "• Temporary root commonly disappears after a reboot; rerun the documented method only if your exact build is supported.\n"
                "• Singularity being installed does not prove root is active or that the current firmware is supported.\n"
                "• Do not flash images or write to /boot, /system, or other partitions based on generic advice.\n"
                "• Keep verified stock firmware/recovery instructions for your exact model and build.\n"
                "• Compatibility labels in this tool are local notes, not automatic exploit validation.\n"
                "• A game warning about a modified/rooted device is separate from whether the headset is physically bricked.",
                title="Root Persistence & Safety", border_style="yellow"))
            pause()
            continue
        if adb is None:
            console.print("[yellow]ADB was not found. Install Platform Tools from the main menu first.[/yellow]")
            pause()
            continue
        if choice == "1":
            inspect_quest(adb, console, pause)
        elif choice == "2":
            root_status(adb, console, pause)
        elif choice == "3":
            manage_firmware_db(console, pause)
        elif choice == "4":
            quest_diagnostics(adb, console, pause)
        elif choice == "5":
            inspect_apps(adb, console, pause)
        elif choice == "6":
            frida_diagnostics(adb, install_dir, console, pause)
        elif choice == "7":
            wireless_adb(adb, console, pause)
        else:
            console.print("[yellow]Unknown option.[/yellow]")
            pause()
