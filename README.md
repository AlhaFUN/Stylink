# S23 Drawing Tablet

Use the S Pen on a Galaxy S23 Ultra to draw in Windows apps. The phone sends pen input to the small Windows receiver included here. The app shows the connection status and previews your S Pen strokes on the phone.

## Get the APK

1. Open the repository’s [Android build workflow](https://github.com/AlhaFUN/s23-drawing-tablet/actions/workflows/android.yml).
2. Open the latest successful **Build Android APK** run.
3. Download the **S23-Tablet-App** artifact and unzip it.
4. Copy `app-debug.apk` to your phone and tap it to install. If Android asks, allow installation from that source.

You do not need Android Studio to build or install the APK.

## Connect the phone to Windows over USB

Do these steps before drawing in a Windows app:

1. On the PC, install Python 3.10 or newer if needed. Download or clone this project and open PowerShell in its folder.
2. Start the Windows receiver and keep this PowerShell window open:

   ```powershell
   py .\host\tablet_host.py
   ```

   It should say **Listening**.
3. Download Google’s [Android SDK Platform-Tools for Windows](https://developer.android.com/tools/releases/platform-tools) and unzip the folder somewhere easy to find, for example `C:\platform-tools`. This small download includes `adb`; Android Studio is not required.
4. Connect the phone with a USB data cable. If USB debugging is not enabled yet, on the phone open **Settings → About phone → Software information**, tap **Build number** seven times, then open **Settings → Developer options** and turn on **USB debugging**. Approve the prompt on the phone.
5. In a second PowerShell window, run these commands. Change `C:\platform-tools` if you extracted the folder somewhere else:

   ```powershell
   $adb = "C:\platform-tools\adb.exe"
   & $adb devices
   & $adb reverse tcp:8765 tcp:8765
   ```

   If the phone shows **unauthorized**, unlock it and approve the USB debugging prompt, then run the last two commands again.
6. Open **S23 Drawing Tablet** on the phone. Its status should change to **Connected — ready to draw**. Draw with the S Pen inside **S Pen drawing area**, then draw in Paint or another Windows drawing app.

## What the phone screen means

- **Not connected** means the Windows receiver is not reachable yet. Make sure its PowerShell window still says **Listening**, the phone is authorized in `adb devices`, and you ran `adb reverse`.
- The drawing area previews S Pen strokes on the phone. Those strokes reach Windows only when the app says **Connected — ready to draw**.
- Finger touches are ignored; use the S Pen.

## Wi-Fi connection (optional)

USB is simpler and does not need a firewall rule. To use Wi-Fi, both devices must be on the same trusted home network. The app’s `HOST` value in `android/app/src/main/java/dev/example/galaxytabled/StylusCaptureActivity.kt` must be changed to the PC’s IPv4 address, then a new APK must be built and installed. Start the receiver with `py .\host\tablet_host.py --host 0.0.0.0` and allow its port through Windows Firewall. The included firewall scripts are in `scripts/`. Do not expose the receiver to the internet.

The host uses the Windows pointer API to send pen input. Some drawing apps may require a physical tablet driver and may not accept synthetic pen input.
