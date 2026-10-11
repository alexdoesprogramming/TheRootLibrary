# TheRootLibrary — Rooting Companion

A Windows-first terminal utility for getting started with Android/Meta Quest device debugging. The first version focuses on a clean Rich-powered terminal UI, official Android Platform Tools setup, and ADB device detection.

## Features

- Downloads Android Platform Tools from Google's official HTTPS distribution URL.
- Installs the tools into `%LOCALAPPDATA%\TheRootLibrary\platform-tools` without requiring administrator access.
- Detects ADB already on PATH or in the tool's install directory.
- Lists connected devices and highlights common states such as `device`, `unauthorized`, and `offline`.
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

## Safety

ADB is a powerful debugging interface. Only authorize computers you trust. This tool only installs Platform Tools and queries ADB status; it does not perform rooting or device modification.

## Project layout

- `main.py` — terminal interface and ADB setup/device detection
- `requirements.txt` — Python dependency list

