# TheRootLibrary — Rooting Companion

A Windows-first terminal utility for getting started with Android/Meta Quest device debugging. The first version focuses on a clean Rich-powered terminal UI, official Android Platform Tools setup, and ADB device detection.

## Features

- Downloads Android Platform Tools from Google's official HTTPS distribution URL.
- Installs the tools into `%LOCALAPPDATA%\TheRootLibrary\platform-tools` without requiring administrator access.
- Detects ADB already on PATH or in the tool's install directory.
- Lists connected devices and highlights common states such as `device`, `unauthorized`, and `offline`.
- Browses the ZIP archives currently in the repository, downloads and safely extracts a selected archive, then lets you select and launch a `.bat` file inside it.
- Downloads the official Frida server release for the connected Android device's ABI and places the decompressed binary beside `adb.exe` in the Platform Tools folder.
- Pushes the downloaded Frida server to an authorized device and attempts to start it as root, then checks whether a server PID is visible.
- Fetches the latest Singularity APK from the official GitHub Releases API and installs it to a selected authorized ADB device.
- Provides an **APK Installer** for Lightning Launcher, CX File Explorer, CitraVR, Shizuku, Termux, and VLC for Android (ARM64), downloading from their official release/download sources and installing with `adb install -r`.
- Does **not** root devices, unlock bootloaders, flash images, or write to system partitions.

## Requirements

- Windows 10 or 11
- Python 3.10+
- Internet access for the first Platform Tools download

## Run from source

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

Choose **Install / update official Android Platform Tools** from the menu to install or update ADB. You can also use an existing `adb.exe` already on your PATH.

## Quest USB debugging

1. Enable Developer Mode for the headset using the official Meta developer workflow.
2. Connect the headset to the PC using a USB data cable.
3. Put on the headset and accept the USB debugging prompt if shown.
4. Select **Check ADB and connected devices**.

Wireless ADB setup is intentionally not included in this first version.

## Singularity APK installer

Choose **Download latest Singularity APK & install via ADB** to check the official [Lumince/Singularity releases](https://github.com/Lumince/singularity/releases), automatically select the latest release's APK asset, download it, and sideload it to a selected authorized device using `adb install -r -g`. The tool asks you to type `INSTALL` before proceeding and removes the temporary APK afterward. The release version and asset name are discovered at runtime; no version is hard-coded.

This installs or updates the Singularity app only. It does **not** trigger rooting, press **Root Now**, or change device partitions. Make sure the release is appropriate for your headset and firmware before using the app.


## APK Installer

Choose **APK Installer** from menu option **7** to install one of these apps to a selected authorized ADB device:

- **Lightning Launcher 10.0.1** — [official GitHub release](https://github.com/threethan/LightningLauncher/releases/tag/10.0.1).
- **CX File Explorer** — official [CX File Explorer download page](https://cxfileexplorer.com/?go=download).
- **CitraVR v0.6.0** — [official GitHub release](https://github.com/amwatson/CitraVR/releases/tag/v0.6.0).
- **Shizuku** — latest APK asset discovered from the [official GitHub Releases API](https://github.com/RikkaApps/Shizuku/releases).
- **Termux** — latest universal APK discovered from the [official GitHub Releases API](https://github.com/termux/termux-app/releases). GitHub builds use a shared test key and are not interchangeable with F-Droid/Google Play builds; see the official project notes before switching sources.
- **VLC for Android (ARM64)** — latest ARM64 APK discovered from the [official VideoLAN download directory](https://get.videolan.org/vlc-android/last/).

The installer asks you to choose an authorized device and type `INSTALL` before downloading. It validates the downloaded file, installs with `adb install -r`, and removes the temporary APK afterward. These are ordinary app installs; this option does not root the headset or modify system partitions.

**Not included as APK installs:** SideQuest is a PC companion; Quest Games Optimizer is a paid product that should be obtained through its official purchase channel; AnExplorer VR is distributed through the Meta Store. Those are not treated as downloadable APKs by this menu. Lightning Browser is not listed as a separate APK because it was not verified as a distinct official project.

Menu option **8** remains About & safety.



## Frida server installer

Choose **Install Frida server into Platform Tools** with an authorized Android device connected. The tool reads the device ABI over ADB, downloads the corresponding official release asset from the Frida GitHub releases, decompresses it, and saves it as `frida-server` beside `adb.exe`. If the `frida` client is available on PATH, it prefers that version so the client and server can match. If no client is found, it uses the latest release and displays a compatibility warning.

This option only downloads the server binary to the PC; it does not push or start it on the headset.

### Start Frida server

Choose **Push & try to start Frida server on device** after installing the server binary. The tool lets you select an authorized ADB device, asks you to type `START`, pushes the binary to `/data/local/tmp/frida-server`, applies executable permission, runs `adb shell "/data/local/tmp/frida-server &"`, and checks for a running PID. The headset must already have working root access; this does not root the device. The process may stop after a reboot, and Frida client/server versions should match. Only use dynamic instrumentation on devices and apps you own or are authorized to test.

## Mod ZIP launcher

Choose **Browse, extract & run a mod ZIP** to select one of the repository's mod archives. The app downloads the chosen ZIP, rejects archive paths that escape the extraction folder, extracts it under `%LOCALAPPDATA%\\TheRootLibrary\\mods`, and lists any `.bat` files found. If there are multiple batch files, choose which one to run. You must type `RUN` to confirm execution.

**Important:** a batch file is executable code and can make changes to Windows, your headset, or connected devices. Only run scripts you trust; review the extracted script first if unsure. The app does not automatically request administrator privileges. The repository's ZIP list is currently defined in `main.py`, so new archives must be added to `MOD_ARCHIVES`.

## Safety

ADB is a powerful debugging interface. Only authorize computers you trust. The companion can install the listed APKs and run selected user-confirmed scripts, but it does not perform rooting, unlock bootloaders, flash images, or write to system partitions.

## Project layout

- `main.py` — terminal interface and ADB setup/device detection
- `requirements.txt` — Python dependency list



## Quest Toolkit (menu option 9)

The Quest Toolkit adds these helpers:

- **Quest Inspector:** reads the headset model, device codename, build display ID/fingerprint, Android/SDK version, security patch, ABI, and verified-boot state. It compares the exact build display ID against the local compatibility database.
- **Temporary Root Status:** checks whether `su -c id` confirms root, whether `frida-server` is running, and whether an installed package name contains `singularity`. A failed check is not proof that a method is unsupported.
- **Firmware / Exploit Status Database:** keeps a local, editable database at `%LOCALAPPDATA%\TheRootLibrary\quest_firmware_db.json`. Records can be marked supported, reported, patched, unsupported, or unknown, with notes/source links. It starts empty intentionally: no firmware is marked supported without evidence.
- **Quest Diagnostics:** exports device properties, ADB version, root/Frida checks, and filtered recent logcat lines to a timestamped report.
- **IL2CPP / App Inspector:** searches installed package IDs and exports the selected package's APK paths and package metadata. It is a metadata helper, not an automatic memory dumper.
- **Frida Toolkit:** checks the local Frida client/server and whether the server process is visible on the headset. Existing menu options still handle downloading and attempting to start the server.
- **Wireless ADB:** connects to an already-enabled ADB-over-TCP endpoint. It does not change the headset's wireless debugging settings.
- **PCVR Quick Check:** looks for common SteamVR, Meta Quest Link, Virtual Desktop, ALVR, and Discord processes on Windows.
- **Root Persistence & Safety Guide:** explains temporary-root reboot behavior and cautions around firmware mismatches and partition writes.

All firmware records and diagnostic reports are local to the PC. Review reports before sharing them because logs may contain device identifiers, package names, or other private information. The compatibility database is a notes/evidence tracker, not an exploit verifier. This toolkit does not automatically exploit the headset, unlock a bootloader, flash firmware, or write to boot/system partitions.

## Local data locations

- Firmware database: `%LOCALAPPDATA%\TheRootLibrary\quest_firmware_db.json`
- Diagnostic reports: `%LOCALAPPDATA%\TheRootLibrary\reports`
- Filtered logs: `%LOCALAPPDATA%\TheRootLibrary\logs`
