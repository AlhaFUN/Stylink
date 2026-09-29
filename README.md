# S23 Drawing Tablet

Use a Galaxy S23 Ultra S Pen to draw in Windows apps. The Android app sends pen events to a small Python receiver on the PC. **USB is the recommended connection** because it needs no Wi-Fi or firewall changes.

## What you need

- Windows 10 version 1809 or newer
- Galaxy S23 Ultra and a USB data cable
- A GitHub account with this repository's Actions enabled, for building the APK
- Python 3.10 or newer

The shared authentication token is hardcoded in the Android app and Python host as `MySecretToken123`. You do not need to set environment variables or edit a configuration file.

## Build and install the Android app

1. Push the project to GitHub. GitHub Actions builds the APK automatically whenever changes are pushed to `main`.
2. On GitHub, open the repository's **Actions** tab and select the latest successful **Build Android APK** run.
3. Under **Artifacts**, download **S23-Tablet-App** and unzip it. The APK inside is named `app-debug.apk`.
4. Copy `app-debug.apk` to your phone and tap it to install. If Android asks, allow installing apps from that file source.

## Connect over USB and draw

1. Open PowerShell in the project folder and start the Windows receiver:

   ```powershell
   py .\host\tablet_host.py
   ```

   Keep this window open. Python packages are not needed.
2. In a second PowerShell window, connect the phone's local port to the PC. The default Android SDK location is shown below:

   ```powershell
   $adb = "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"
   & $adb devices
   & $adb reverse tcp:8765 tcp:8765
   ```

   If the SDK is in another folder, use the `platform-tools\adb.exe` from that folder. `adb reverse` is correct because the phone app connects to the PC; `adb forward` goes the other way.
3. Open **S23 Drawing Tablet** on the phone and draw in Paint or another Windows drawing app.

## Use Wi-Fi instead (optional)

Both devices must be on the same trusted home network.

1. Start the receiver so it accepts connections from the network:

   ```powershell
   py .\host\tablet_host.py --host 0.0.0.0
   ```

2. Find the PC's **IPv4 Address** by running `ipconfig`. In the Android source file, change `HOST` from `127.0.0.1` to that address, then rebuild and reinstall the APK using the commands above.
3. Run PowerShell as Administrator in the project folder and add the firewall rule:

   ```powershell
   Set-ExecutionPolicy -Scope Process Bypass
   .\scripts\firewall-add.ps1
   ```

To remove the rule later, run `scripts/firewall-remove.ps1` as Administrator. The Wi-Fi connection is unencrypted and the token is included in the app, so use USB or a trusted private network; do not expose this receiver to the internet.

## Project files

- Android activity: `android/app/src/main/java/dev/example/galaxytabled/StylusCaptureActivity.kt`
- Android manifest: `android/app/src/main/AndroidManifest.xml`
- Android build files and Gradle wrapper: `android/`
- Windows receiver: `host/tablet_host.py`
- Firewall scripts: `scripts/`

The Windows host injects a synthetic pen through the Win32 pointer API. Some drawing apps require a physical tablet driver and may not accept synthetic pen input.
