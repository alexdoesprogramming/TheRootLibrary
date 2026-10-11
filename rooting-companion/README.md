# TheRootLibrary — Rooting Companion

A Windows-first terminal utility for getting started with Android/Meta Quest device debugging. The first version focuses on a clean Rich-powered terminal UI, official Android Platform Tools setup, and ADB device detection.

## Features

- Downloads Android Platform Tools from Google's official HTTPS distribution URL.
- Installs the tools into `%LOCALAPPDATA%\TheRootLibrary\platform-tools` without requiring administrator access.
- Detects ADB already on PATH or in the tool's install directory.
- Lists connected devices and highlights common states such as `device`, `unauthorized`, and `offline`.
- Browses the ZIP archives currently in the repository, downloads and safely extracts a selected archive, then lets you select and launch a `.bat` file inside it.
- Downloads the official Frida server release for the connected Android device's ABI and places the decompressed binary beside `adb.exe` in the Platform Tools folder.
- Fetches the latest Singularity APK from the official GitHub Releases API and installs it to a selected authorized ADB device.
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

## Frida server installer

Choose **Install Frida server into Platform Tools** with an authorized Android device connected. The tool reads the device ABI over ADB, downloads the corresponding official release asset from the Frida GitHub releases, decompresses it, and saves it as `frida-server` beside `adb.exe`. If the `frida` client is available on PATH, it prefers that version so the client and server can match. If no client is found, it uses the latest release and displays a compatibility warning.

This only downloads the server binary to the PC; it does not push or start it on the headset. Frida server/client versions should match. Only use dynamic instrumentation on devices and apps you own or are authorized to test.

## Mod ZIP launcher

Choose **Browse, extract & run a mod ZIP** to select one of the repository's mod archives. The app downloads the chosen ZIP, rejects archive paths that escape the extraction folder, extracts it under `%LOCALAPPDATA%\\TheRootLibrary\\mods`, and lists any `.bat` files found. If there are multiple batch files, choose which one to run. You must type `RUN` to confirm execution.

**Important:** a batch file is executable code and can make changes to Windows, your headset, or connected devices. Only run scripts you trust; review the extracted script first if unsure. The app does not automatically request administrator privileges. The repository's ZIP list is currently defined in `main.py`, so new archives must be added to `MOD_ARCHIVES`.

## Safety

ADB is a powerful debugging interface. Only authorize computers you trust. This tool only installs Platform Tools and queries ADB status; it does not perform rooting or device modification.

## Project layout

- `main.py` — terminal interface and ADB setup/device detection
- `requirements.txt` — Python dependency list

