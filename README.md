# Stylink

Use a compatible Android phone or tablet stylus as a Windows drawing tablet. Stylink includes an Android app and a standalone Windows companion.

> **Development note:** Stylink was built with AI-assisted coding (“vibe coding”) and tested with a Galaxy S23 Ultra. It has not had an independent security audit, and support for other devices is not yet hardware-tested.

## Install

1. Open the [latest Stylink release](https://github.com/AlhaFUN/Stylink/releases/latest).
2. Download `app-debug.apk` for your Android phone or tablet, then install it. Android may ask you to allow this APK to be installed.
3. Download `Stylink.exe` for your Windows PC, then open it.

Windows may show a SmartScreen message because this community build is not code-signed.

## Connect

1. Connect the phone to the PC with a USB data cable.
2. On the phone, turn on **Settings → Connections → Mobile Hotspot and Tethering → USB tethering**.
3. Open Stylink on the phone and on the PC. In the PC app, click **Connect phone**.
4. The first time, enter the 8-character code shown on the phone. Future connections pair automatically.

No USB debugging, ADB, driver install, manual firewall rule, or command window is needed. Keep both apps open while drawing.

USB tethering is the only supported connection in this version. Wi-Fi discovery and Bluetooth pairing would add setup and connection failure cases, so the app keeps one automatic connection path.

## Draw

- Draw in the phone app's **Drawing pad** with the stylus. Finger touches are ignored. Tap **Full screen** for a larger pad; press Android Back to leave it.
- To preview part of the PC screen, disconnect, click **Select screen area…** in the PC app, and drag around the area. Reconnect to show and draw in that area. **Show full screen** returns mapping to the whole desktop and turns off preview.
- **Image quality** and **FPS limit** in the PC app control the preview. Performance uses a smaller image; higher FPS needs more bandwidth.

## Compatibility and privacy

Stylink requires Android 8 or newer, a stylus Android reports as a stylus or eraser, and USB tethering to Windows. Pressure, tilt, and buttons depend on what the device reports. Passive capacitive pens that appear as fingers are ignored. The Galaxy S23 Ultra is tested; other models need hardware testing.

The first connection pairs the phone and PC with a one-time code. They create a unique key, protected on the phone and for the current Windows user. The source has no shared app-wide password. Connection traffic is not encrypted in transit, so use the direct USB tether rather than a shared network.

## Help

- If the PC app keeps searching, check that USB tethering is on and both apps are open.
- If pairing was reset or the phone app was reinstalled, enter the new code shown on the phone.
- Try another USB data cable or port if Windows does not detect a USB network connection.
- Some drawing programs may ignore synthetic Windows pen input or handle pressure differently.

## Source

- Android app: [`android/`](android/)
- Windows app: [`pc/`](pc/) and [`host/`](host/)
- [Android build workflow](.github/workflows/android.yml)
- [Windows build workflow](.github/workflows/windows-companion.yml)
