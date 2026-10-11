from __future__ import annotations

import json
import hashlib
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



DEVICE_PROFILES = APP_DATA / "device_profiles.json"
MOD_WORKSPACE = APP_DATA / "mod_workspace"


def _load_json_file(path: Path, fallback):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value
    except (OSError, json.JSONDecodeError):
        return fallback


def device_profiles(adb: Path, console, pause: Callable[[], None]) -> None:
    """Save and review named local profiles for known Quest devices."""
    console.clear()
    console.print(Panel("Save a local snapshot of a headset's identity/build so you can compare devices later.", title="Device Profiles", border_style="cyan"))
    serial = _choose_device(adb, console)
    if not serial:
        pause()
        return
    try:
        props = _properties(adb, serial)
        profiles = _load_json_file(DEVICE_PROFILES, {})
        if not isinstance(profiles, dict):
            profiles = {}
        old = profiles.get(serial, {})
        table = Table(title=f"Profile — {serial}", box=box.ROUNDED, header_style="bold cyan")
        table.add_column("Property")
        table.add_column("Value", overflow="fold")
        for key, value in props.items():
            table.add_row(key, value)
        table.add_row("First saved", str(old.get("first_saved", datetime.now().isoformat(timespec="seconds"))))
        table.add_row("Last updated", datetime.now().isoformat(timespec="seconds"))
        console.print(table)
        action = console.input("S = save/update profile, V = view saved profiles, B = back › ").strip().lower()
        if action == "s":
            notes = console.input("Profile notes (optional; blank keeps existing notes) › ").strip()
            profiles[serial] = {
                "serial": serial,
                "properties": props,
                "notes": notes or old.get("notes", ""),
                "first_saved": old.get("first_saved", datetime.now().isoformat(timespec="seconds")),
                "last_updated": datetime.now().isoformat(timespec="seconds"),
            }
            APP_DATA.mkdir(parents=True, exist_ok=True)
            DEVICE_PROFILES.write_text(json.dumps(profiles, indent=2, ensure_ascii=False), encoding="utf-8")
            console.print(f"[green]Profile saved locally:[/green] {DEVICE_PROFILES}")
        elif action == "v":
            if not profiles:
                console.print("[yellow]No saved profiles yet.[/yellow]")
            else:
                saved = Table(title="Saved device profiles", box=box.ROUNDED)
                saved.add_column("Serial")
                saved.add_column("Model")
                saved.add_column("Build")
                saved.add_column("Last updated")
                for key, item in profiles.items():
                    values = item.get("properties", {})
                    saved.add_row(key, values.get("Model", "Unknown"), values.get("Build display ID", "Unknown"), item.get("last_updated", "Unknown"))
                console.print(saved)
    except (OSError, subprocess.TimeoutExpired) as exc:
        console.print(f"[red]Device profile operation failed:[/red] {exc}")
    pause()


def live_logcat_viewer(adb: Path, console, pause: Callable[[], None]) -> None:
    """Repeatedly query recent logcat lines with optional text filtering."""
    console.clear()
    console.print(Panel("Refreshable logcat snapshots with optional Unity, IL2CPP, Frida, crash, or custom filters.", title="Live Logcat Viewer", border_style="cyan"))
    serial = _choose_device(adb, console)
    if not serial:
        pause()
        return
    query = console.input("Filter text / regex (blank = common modding errors; B = back) › ").strip()
    if query.lower() in {"b", "back", "q"}:
        return
    pattern_text = query or r"unity|il2cpp|fatal|exception|crash|frida|singularity|error"
    try:
        pattern = re.compile(pattern_text, re.I)
    except re.error as exc:
        console.print(f"[yellow]Invalid regex: {exc}. Using literal text instead.[/yellow]")
        pattern = re.compile(re.escape(pattern_text), re.I)
    while True:
        try:
            result = _run(adb, serial, "logcat", "-d", "-t", "1200", "-v", "time", timeout=30)
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or "logcat returned a non-zero exit code")
            matches = [line for line in result.stdout.splitlines() if pattern.search(line)]
            console.clear()
            console.print(Panel(f"Device: {serial}\nFilter: {pattern_text}\nMatched {len(matches)} of the latest 1200 lines", title="Live Logcat Viewer", border_style="cyan"))
            for line in matches[-100:]:
                console.print(line, markup=False, soft_wrap=True)
            console.print("\n[dim]R = refresh   S = save matching lines   B = back[/dim]")
            action = console.input("Action › ").strip().lower()
            if action in {"b", "back", "q"}:
                return
            if action == "s":
                path = _report_path("quest-live-logcat")
                path.write_text("\n".join(matches) + "\n", encoding="utf-8")
                console.print(f"[green]Saved:[/green] {path}")
                pause()
        except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
            console.print(f"[red]Logcat query failed:[/red] {exc}")
            pause()
            return


def apk_inspector_plus(adb: Path, console, pause: Callable[[], None]) -> None:
    """Show package version, install source, APK paths, and available signature metadata."""
    console.clear()
    console.print(Panel("Expanded package metadata from Android's Package Manager; no APK patching or protected-data access.", title="APK Inspector Plus", border_style="cyan"))
    serial = _choose_device(adb, console)
    if not serial:
        pause()
        return
    try:
        result = _run(adb, serial, "shell", "pm", "list", "packages", timeout=30)
        packages = sorted(line.strip().removeprefix("package:") for line in result.stdout.splitlines() if line.startswith("package:"))
        query = console.input("Filter package IDs › ").strip().lower()
        matches = [p for p in packages if query in p.lower()]
        for index, package in enumerate(matches[:150], 1):
            console.print(f"[cyan]{index:>3}.[/cyan] {package}")
        selected = console.input("Exact package ID (blank = back) › ").strip()
        if not selected:
            return
        if selected not in packages:
            console.print("[yellow]Package ID was not found on this device.[/yellow]")
            pause()
            return
        details = _run(adb, serial, "shell", "dumpsys", "package", selected, timeout=30)
        paths = _run(adb, serial, "shell", "pm", "path", selected, timeout=15)
        wanted = re.compile(r"versionCode=|versionName=|firstInstallTime=|lastUpdateTime=|installerPackageName=|initiatingPackageName=|signatures=|SigningInfo|pkgFlags=|userId=", re.I)
        lines = [line.strip() for line in details.stdout.splitlines() if wanted.search(line)]
        table = Table(title=f"APK metadata — {selected}", box=box.ROUNDED, header_style="bold cyan")
        table.add_column("Field")
        table.add_column("Value", overflow="fold")
        table.add_row("Device", serial)
        table.add_row("APK path(s)", paths.stdout.strip() or "Not reported")
        table.add_row("Metadata", "\n".join(lines[:100]) or "No matching fields returned")
        console.print(table)
        path = _report_path("apk-inspector-plus")
        path.write_text(f"Package: {selected}\nDevice: {serial}\nTime: {datetime.now().isoformat(timespec='seconds')}\n\nAPK paths:\n{paths.stdout}\n\nSelected package metadata:\n" + "\n".join(lines) + "\n\nRaw dumpsys output:\n" + details.stdout, encoding="utf-8")
        console.print(f"[green]Full report saved:[/green] {path}")
        console.print("[dim]Signature details vary by Android version and may be omitted by Package Manager. This does not cryptographically verify an APK file.[/dim]")
    except (OSError, subprocess.TimeoutExpired) as exc:
        console.print(f"[red]APK inspection failed:[/red] {exc}")
    pause()


def one_click_health_check(adb: Path | None, console, pause: Callable[[], None]) -> None:
    """Run a bundled read-only PC/ADB/Quest check and save one report."""
    console.clear()
    console.print(Panel("One report combining PC environment, ADB, Quest properties, root visibility, Frida, storage, and filtered logs.", title="One-Click Health Check", border_style="cyan"))
    lines = [ "TheRootLibrary One-Click Health Check", f"Time: {datetime.now().isoformat(timespec='seconds')}", f"Computer: {platform.platform()}", "" ]
    if adb is None:
        lines.append("ADB: NOT FOUND")
        console.print("[yellow]ADB was not found. PC-only checks will still be collected.[/yellow]")
    else:
        lines.append(f"ADB executable: {adb}")
        try:
            version = subprocess.run([str(adb), "version"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10, check=False)
            lines.extend(["ADB VERSION", version.stdout.strip() or version.stderr.strip(), ""])
            devices = [(s, state) for s, state in _devices(adb) if state == "device"]
            lines.append(f"Authorized ADB devices: {len(devices)}")
            if devices:
                serial = devices[0][0]
                if len(devices) > 1:
                    console.print(f"[cyan]{len(devices)} authorized devices found; selecting the first for the automated snapshot.[/cyan]")
                    serial = _choose_device(adb, console) or ""
                if serial:
                    lines.extend([f"Selected device: {serial}", "", "QUEST PROPERTIES"])
                    lines.extend(f"{key}: {value}" for key, value in _properties(adb, serial).items())
                    for label, args in [
                        ("ROOT CHECK", ("shell", "su", "-c", "id")),
                        ("FRIDA SERVER", ("shell", "pidof", "frida-server")),
                        ("BATTERY", ("shell", "dumpsys", "battery")),
                        ("STORAGE", ("shell", "df", "-h", "/data")),
                    ]:
                        result = _run(adb, serial, *args, timeout=20)
                        lines.extend(["", label, result.stdout.strip() or result.stderr.strip() or f"exit code {result.returncode}"])
                    logs = _run(adb, serial, "logcat", "-d", "-t", "1200", timeout=45)
                    pattern = re.compile(r"unity|il2cpp|fatal|exception|crash|frida|singularity|error", re.I)
                    filtered = [line for line in logs.stdout.splitlines() if pattern.search(line)]
                    lines.extend(["", "FILTERED LOGCAT", *filtered[-500:]])
            else:
                lines.append("No authorized ADB device was connected.")
        except (OSError, subprocess.TimeoutExpired) as exc:
            lines.append(f"ADB/Quest check failed: {exc}")
    if os.name == "nt":
        try:
            tasks = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15, check=False)
            lines.extend(["", "PCVR PROCESS CHECK"])
            process_names = {line.split('","')[0].strip('"').lower() for line in tasks.stdout.splitlines() if line.strip()}
            for exe in ("vrserver.exe", "vrmonitor.exe", "OVRServer_x64.exe", "VirtualDesktop.Streamer.exe", "ALVR.exe"):
                lines.append(f"{exe}: {'running' if exe.lower() in process_names else 'not detected'}")
        except (OSError, subprocess.TimeoutExpired) as exc:
            lines.append(f"PCVR check failed: {exc}")
    path = _report_path("quest-health-check")
    try:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        console.print(f"[green]Health-check report saved:[/green] {path}")
        console.print(f"Collected {len(lines)} report lines.")
        console.print("[dim]A health check is a snapshot, not a definitive exploit-compatibility or hardware diagnosis. Review logs before sharing.[/dim]")
    except OSError as exc:
        console.print(f"[red]Could not save health-check report:[/red] {exc}")
    pause()


def mod_workspace(console, pause: Callable[[], None]) -> None:
    """Keep per-game notes, package IDs, script paths, and log/report references."""
    console.clear()
    console.print(Panel(f"Local per-game modding notes and references\n{MOD_WORKSPACE}", title="Mod Workspace", border_style="cyan"))
    MOD_WORKSPACE.mkdir(parents=True, exist_ok=True)
    index_path = MOD_WORKSPACE / "workspace.json"
    entries = _load_json_file(index_path, {})
    if not isinstance(entries, dict):
        entries = {}
    table = Table(title="Saved game workspaces", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("#")
    table.add_column("Game")
    table.add_column("Package ID")
    table.add_column("Updated")
    names = sorted(entries)
    for i, name in enumerate(names, 1):
        item = entries[name]
        table.add_row(str(i), name, item.get("package_id", ""), item.get("updated", ""))
    if names:
        console.print(table)
    else:
        console.print("[dim]No game workspaces yet. Create one to keep notes and useful paths together.[/dim]")
    action = console.input("N = new game, E = edit/view, B = back › ").strip().lower()
    if action in {"b", "back", "q"}:
        return
    if action == "n":
        name = console.input("Game name › ").strip()
        if not name:
            return
        if name in entries:
            console.print("[yellow]That game already has a workspace; choose E to edit it.[/yellow]")
            pause()
            return
        entries[name] = {"package_id": "", "notes": "", "scripts": [], "logs": [], "created": datetime.now().isoformat(timespec="seconds")}
    elif action == "e":
        name = console.input("Exact game name to edit › ").strip()
        if name not in entries:
            console.print("[yellow]Game workspace not found.[/yellow]")
            pause()
            return
    else:
        console.print("[yellow]Unknown action.[/yellow]")
        pause()
        return
    item = entries[name]
    console.print("1. Set package ID   2. Replace notes   3. Add script/path reference   4. Add log/report reference   5. View details   6. Save")
    while True:
        choice = console.input(f"{name} › ").strip().lower()
        if choice in {"6", "b", "q"}:
            break
        if choice == "1":
            item["package_id"] = console.input("Package ID › ").strip()
        elif choice == "2":
            console.print("Enter notes on one line (use semicolons to separate thoughts).")
            item["notes"] = console.input("Notes › ").strip()
        elif choice == "3":
            value = console.input("Script or folder path › ").strip()
            if value:
                item.setdefault("scripts", []).append(value)
        elif choice == "4":
            value = console.input("Log/report path or short reference › ").strip()
            if value:
                item.setdefault("logs", []).append(value)
        elif choice == "5":
            console.print_json(json.dumps(item, indent=2, ensure_ascii=False))
        else:
            console.print("[yellow]Choose 1–6 or B to save.[/yellow]")
    item["updated"] = datetime.now().isoformat(timespec="seconds")
    entries[name] = item
    index_path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-")[:80] or "game"
    note_path = MOD_WORKSPACE / f"{slug}.md"
    note_path.write_text(
        f"# {name}\n\nUpdated: {item['updated']}\n\n"
        f"**Package ID:** {item.get('package_id', '')}\n\n"
        f"## Notes\n{item.get('notes', '')}\n\n"
        "## Script / folder references\n" + "\n".join(f"- {x}" for x in item.get("scripts", [])) + "\n\n"
        "## Log / report references\n" + "\n".join(f"- {x}" for x in item.get("logs", [])) + "\n",
        encoding="utf-8",
    )
    console.print(f"[green]Workspace saved:[/green] {index_path}\nMarkdown notes: {note_path}")
    pause()




def apk_backup_exporter(adb: Path, console, pause: Callable[[], None]) -> None:
    """Pull an installed package's APK split set to the PC and write a hash manifest."""
    console.clear()
    console.print(Panel(
        "Export installed APK files for apps you own or are authorized to archive. This copies APKs only; it does not export private app data.",
        title="APK Backup Exporter", border_style="cyan"
    ))
    serial = _choose_device(adb, console)
    if not serial:
        pause()
        return
    try:
        result = _run(adb, serial, "shell", "pm", "list", "packages", timeout=30)
        packages = sorted(
            line.strip().removeprefix("package:")
            for line in result.stdout.splitlines() if line.startswith("package:")
        )
        query = console.input("Filter package IDs › ").strip().lower()
        matches = [name for name in packages if query in name.lower()]
        for i, name in enumerate(matches[:150], 1):
            console.print(f"[cyan]{i:>3}.[/cyan] {name}")
        package = console.input("Exact package ID to export (blank = back) › ").strip()
        if not package:
            return
        if package not in packages:
            console.print("[yellow]That package is not in the installed package list.[/yellow]")
            pause()
            return
        paths_result = _run(adb, serial, "shell", "pm", "path", package, timeout=20)
        remote_paths = []
        for line in paths_result.stdout.splitlines():
            value = line.strip().removeprefix("package:")
            if value.startswith("/") and ".." not in Path(value).parts:
                remote_paths.append(value)
        if not remote_paths:
            console.print("[red]Android did not report any APK paths for this package.[/red]")
            pause()
            return
        console.print(f"Found {len(remote_paths)} APK file(s) for [bold]{package}[/bold].")
        console.print("[dim]This may include base.apk and split APKs. App-private data is not included.[/dim]")
        if console.input("Type PULL to export these APKs to this PC › ").strip() != "PULL":
            console.print("[dim]Cancelled; no APKs were pulled.[/dim]")
            pause()
            return
        safe_package = re.sub(r"[^A-Za-z0-9._-]+", "_", package)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = REPORT_DIR / "apk-backups" / f"{safe_package}-{stamp}"
        target.mkdir(parents=True, exist_ok=False)
        manifest = [
            "TheRootLibrary APK Backup Manifest",
            f"Time: {datetime.now().isoformat(timespec='seconds')}",
            f"Device: {serial}",
            f"Package: {package}",
            "Note: APK files only; private app data is not included.",
            "",
        ]
        for index, remote in enumerate(remote_paths, 1):
            filename = Path(remote).name or f"split-{index}.apk"
            local = target / filename
            pulled = _run(adb, serial, "pull", remote, str(local), timeout=90)
            if pulled.returncode != 0 or not local.is_file():
                manifest.append(f"FAILED: {remote} — {pulled.stderr.strip() or pulled.stdout.strip()}")
                continue
            digest = hashlib.sha256()
            with local.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            manifest.append(f"{filename} | {local.stat().st_size} bytes | SHA256 {digest.hexdigest()} | source {remote}")
        manifest_path = target / "manifest.txt"
        manifest_path.write_text("\n".join(manifest) + "\n", encoding="utf-8")
        console.print(f"[green]Export finished.[/green] Files and SHA-256 manifest: {target}")
        console.print("[yellow]Keep exported APKs private and respect app licenses and redistribution rules.[/yellow]")
    except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
        console.print(f"[red]APK export failed:[/red] {exc}")
    pause()


def permission_audit(adb: Path, console, pause: Callable[[], None]) -> None:
    """Create a best-effort report of requested and reported permission states."""
    console.clear()
    console.print(Panel(
        "Inspect Package Manager's permission metadata for one installed package. Output varies by Android version.",
        title="App Permission Audit", border_style="cyan"
    ))
    serial = _choose_device(adb, console)
    if not serial:
        pause()
        return
    try:
        result = _run(adb, serial, "shell", "pm", "list", "packages", timeout=30)
        packages = sorted(
            line.strip().removeprefix("package:")
            for line in result.stdout.splitlines() if line.startswith("package:")
        )
        query = console.input("Filter package IDs › ").strip().lower()
        matches = [name for name in packages if query in name.lower()]
        for i, name in enumerate(matches[:150], 1):
            console.print(f"[cyan]{i:>3}.[/cyan] {name}")
        package = console.input("Exact package ID to audit (blank = back) › ").strip()
        if not package:
            return
        if package not in packages:
            console.print("[yellow]Package not found on this device.[/yellow]")
            pause()
            return
        details = _run(adb, serial, "shell", "dumpsys", "package", package, timeout=30)
        permission_lines = [
            line.rstrip() for line in details.stdout.splitlines()
            if re.search(r"android\.permission\.|permission\[|granted=|denied=|runtime permissions|install permissions|requested permissions", line, re.I)
        ]
        if not permission_lines:
            permission_lines = ["No permission fields were exposed in the package dump."]
        path = _report_path("permission-audit")
        path.write_text(
            f"TheRootLibrary Permission Audit\nTime: {datetime.now().isoformat(timespec='seconds')}\n"
            f"Device: {serial}\nPackage: {package}\n\n" + "\n".join(permission_lines) + "\n",
            encoding="utf-8",
        )
        console.print(f"[green]Saved permission metadata report:[/green] {path}")
        for line in permission_lines[:80]:
            console.print(line, markup=False, soft_wrap=True)
        if len(permission_lines) > 80:
            console.print(f"[dim]… {len(permission_lines) - 80} more lines are in the report.[/dim]")
        console.print("[dim]This is a metadata snapshot, not a security verdict or a guarantee of effective runtime access.[/dim]")
    except (OSError, subprocess.TimeoutExpired) as exc:
        console.print(f"[red]Permission audit failed:[/red] {exc}")
    pause()


def crash_triage(adb: Path, console, pause: Callable[[], None]) -> None:
    """Summarize common crash/ANR markers from a bounded logcat snapshot."""
    console.clear()
    console.print(Panel(
        "Scan the latest 3,000 logcat lines for crash, ANR, Unity, IL2CPP, and native signal markers.",
        title="Crash & ANR Triage", border_style="cyan"
    ))
    serial = _choose_device(adb, console)
    if not serial:
        pause()
        return
    query = console.input("Extra filter regex (optional; blank = all crash markers) › ").strip()
    base = r"fatal exception|FATAL EXCEPTION|ANR in |am_anr|tombstone|signal 11|SIGSEGV|SIGABRT|Unity|IL2CPP|crash|AndroidRuntime"
    try:
        pattern = re.compile(f"(?:{base})" + (f"|(?:{query})" if query else ""), re.I)
    except re.error as exc:
        console.print(f"[yellow]Invalid extra regex ({exc}); using built-in crash markers only.[/yellow]")
        pattern = re.compile(base, re.I)
    try:
        result = _run(adb, serial, "logcat", "-d", "-t", "3000", "-v", "time", timeout=45)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "logcat returned a non-zero exit code")
        matches = [line for line in result.stdout.splitlines() if pattern.search(line)]
        categories = {
            "Java fatal exception": re.compile(r"FATAL EXCEPTION|AndroidRuntime", re.I),
            "ANR": re.compile(r"ANR in |am_anr", re.I),
            "Native crash / signal": re.compile(r"tombstone|SIGSEGV|SIGABRT|signal 11", re.I),
            "Unity / IL2CPP": re.compile(r"Unity|IL2CPP", re.I),
        }
        summary = [f"{label}: {sum(1 for line in matches if regex.search(line))}" for label, regex in categories.items()]
        path = _report_path("crash-triage")
        path.write_text(
            f"TheRootLibrary Crash & ANR Triage\nTime: {datetime.now().isoformat(timespec='seconds')}\n"
            f"Device: {serial}\nScanned lines: {len(result.stdout.splitlines())}\nMatched lines: {len(matches)}\n\n"
            + "\n".join(summary) + "\n\nMATCHING LOGCAT\n" + "\n".join(matches[-1000:]) + "\n",
            encoding="utf-8",
        )
        console.print(Panel("\n".join(summary) + f"\n\nMatched lines: {len(matches)}", title="Triage Summary", border_style="cyan"))
        for line in matches[-60:]:
            console.print(line, markup=False, soft_wrap=True)
        console.print(f"\n[green]Full report saved:[/green] {path}")
        console.print("[dim]Log matches are clues, not proof of a single root cause. Review the surrounding logs.[/dim]")
    except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
        console.print(f"[red]Crash triage failed:[/red] {exc}")
    pause()


def apk_hash_lab(console, pause: Callable[[], None]) -> None:
    """Calculate a local APK's SHA-256 hash and optionally compare it to an expected digest."""
    console.clear()
    console.print(Panel(
        "Calculate a SHA-256 digest for an APK or other file on this PC. The file is read locally and never uploaded.",
        title="APK Hash Lab", border_style="cyan"
    ))
    raw_path = console.input("Full file path (B = back) › ").strip().strip('"')
    if raw_path.lower() in {"b", "back", "q"} or not raw_path:
        return
    path = Path(raw_path).expanduser()
    if not path.is_file():
        console.print("[yellow]That file path does not point to an existing file.[/yellow]")
        pause()
        return
    try:
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
                size += len(chunk)
        actual = digest.hexdigest()
        console.print(f"[bold]File:[/bold] {path.name}")
        console.print(f"[bold]Size:[/bold] {size:,} bytes")
        console.print(f"[bold]SHA-256:[/bold] [cyan]{actual}[/cyan]")
        expected = console.input("Expected SHA-256 to compare (blank = skip) › ").strip().lower()
        if expected:
            expected = expected.removeprefix("sha256:")
            if not re.fullmatch(r"[0-9a-f]{64}", expected):
                console.print("[yellow]Expected digest must be 64 hexadecimal characters.[/yellow]")
            elif actual == expected:
                console.print("[green]MATCH — digest is identical.[/green]")
            else:
                console.print("[red]MISMATCH — digest differs.[/red]")
        console.print("[dim]A matching hash only proves the bytes match the supplied digest; trust depends on where that digest came from.[/dim]")
    except OSError as exc:
        console.print(f"[red]Could not read file:[/red] {exc}")
    pause()


def quest_features_menu(adb: Path | None, install_dir: Path, console, pause: Callable[[], None]) -> None:
    while True:
        console.clear()
        console.print(Panel(
            "[bold cyan]THE ROOT LIBRARY  •  QUEST TOOLKIT[/bold cyan]\n"
            "Device diagnostics, root/Frida helpers, app research, and per-game notes.\n"
            "[dim]Read-only checks by default • no automatic exploit, flashing, or boot/system writes[/dim]",
            title="QUEST TOOLKIT  /  v0.7",
            subtitle="Select a tool • B returns",
            border_style="cyan",
            padding=(1, 2),
        ))
        if adb is None:
            console.print(Panel("[yellow]ADB unavailable[/yellow] — install Platform Tools from the main menu to use headset tools.", border_style="yellow"))
        else:
            try:
                connected = _devices(adb)
                ready = sum(1 for _, state in connected if state == "device")
                console.print(Panel(
                    f"[green]{ready} authorized device(s) ready[/green]  •  {len(connected)} ADB endpoint(s) listed  •  [dim]{adb}[/dim]",
                    title="CONNECTION STATUS",
                    border_style="green" if ready else "yellow",
                ))
            except (OSError, subprocess.TimeoutExpired):
                console.print(Panel("[yellow]Could not query ADB status right now.[/yellow]", border_style="yellow"))
        menu = Table(box=box.ROUNDED, header_style="bold cyan", padding=(0, 1), expand=True)
        menu.add_column("KEY", style="bold cyan", width=5, justify="center")
        menu.add_column("TOOL", style="bold")
        menu.add_column("PURPOSE", style="dim", overflow="fold")
        menu.add_row("1", "Quest build fingerprint & compatibility checker", "Model, firmware, compatibility notes")
        menu.add_row("2", "Temporary root / Singularity / Frida status", "Read-only root and process checks")
        menu.add_row("3", "Firmware & exploit status database", "Local evidence tracker")
        menu.add_row("4", "Diagnostic report + filtered logcat export", "Collect logs and device details")
        menu.add_row("5", "IL2CPP / app package inspector", "Find packages and metadata")
        menu.add_row("6", "Frida client/server diagnostics", "Check local and headset Frida")
        menu.add_row("7", "Connect to existing wireless ADB endpoint", "Connect only; does not enable it")
        menu.add_row("8", "PCVR runtime quick check", "SteamVR, Meta, ALVR, Virtual Desktop")
        menu.add_row("9", "Root persistence & safety guide", "Temporary root and partition cautions")
        menu.add_row("10", "Live Quest dashboard (battery, storage, memory)", "Battery, storage, memory, uptime")
        menu.add_row("11", "Capture Quest screenshot to PC", "Save headset display as PNG")
        menu.add_row("12", "Export installed third-party app inventory", "TXT + JSON package inventory")
        menu.add_row("13", "Device profiles (save/compare headset builds)", "Remember device snapshots locally")
        menu.add_row("14", "Live logcat viewer (filter + save)", "Refresh filtered logs")
        menu.add_row("15", "APK Inspector Plus (version/install/signature metadata)", "Version, paths, install/signature fields")
        menu.add_row("16", "One-click health check (combined report)", "PC + headset diagnostics in one file")
        menu.add_row("17", "Per-game mod workspace (notes, paths, package IDs)", "Keep modding notes organized locally")
        menu.add_row("18", "APK Backup Exporter (pull installed APK/splits)", "Export APKs + SHA-256 manifest")
        menu.add_row("19", "App Permission Audit", "Export permission metadata for a package")
        menu.add_row("20", "Crash & ANR Triage", "Summarize Unity/IL2CPP/Android crash logs")
        menu.add_row("21", "Local APK Hash Lab", "Calculate/compare SHA-256 offline")
        menu.add_row("B", "Back to main menu", "Return to the main menu")
        console.print(menu)
        choice = console.input("Select an option › ").strip().lower()
        if choice in {"b", "back", "q"}:
            return
        if choice == "8":
            pcvr_check(console, pause)
            continue
        if choice in {"10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "20"}:
            if choice == "17":
                mod_workspace(console, pause)
                continue
            if choice == "18" and adb is None:
                console.print("[yellow]ADB was not found. Install Platform Tools from the main menu first.[/yellow]")
                pause()
                continue
            if choice == "19" and adb is None:
                console.print("[yellow]ADB was not found. Install Platform Tools from the main menu first.[/yellow]")
                pause()
                continue
            if choice == "20" and adb is None:
                console.print("[yellow]ADB was not found. Install Platform Tools from the main menu first.[/yellow]")
                pause()
                continue
            if choice == "16":
                one_click_health_check(adb, console, pause)
                continue
            if choice == "13" and adb is None:
                console.print("[yellow]ADB was not found. Install Platform Tools from the main menu first.[/yellow]")
                pause()
                continue
            if choice == "14" and adb is None:
                console.print("[yellow]ADB was not found. Install Platform Tools from the main menu first.[/yellow]")
                pause()
                continue
            if choice == "15" and adb is None:
                console.print("[yellow]ADB was not found. Install Platform Tools from the main menu first.[/yellow]")
                pause()
                continue
            if adb is None:
                console.print("[yellow]ADB was not found. Install Platform Tools from the main menu first.[/yellow]")
                pause()
                continue
            if choice == "13":
                device_profiles(adb, console, pause)
            elif choice == "14":
                live_logcat_viewer(adb, console, pause)
            elif choice == "15":
                apk_inspector_plus(adb, console, pause)
            elif choice == "10":
                quest_live_dashboard(adb, console, pause)
            elif choice == "11":
                capture_quest_screenshot(adb, console, pause)
            elif choice == "12":
                export_app_inventory(adb, console, pause)
            elif choice == "18":
                apk_backup_exporter(adb, console, pause)
            elif choice == "19":
                permission_audit(adb, console, pause)
            elif choice == "20":
                crash_triage(adb, console, pause)
            continue
        if choice == "21":
            apk_hash_lab(console, pause)
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
