# S23 Drawing Tablet

Use your Galaxy S23 Ultra S Pen to draw in Windows apps. Install the Android app on the phone and run the Windows companion on your PC. The companion starts the receiver and connects USB for you; you do not need PowerShell or Python.

## Download the apps

1. Open the repository’s [Android build workflow](https://github.com/AlhaFUN/s23-drawing-tablet/actions/workflows/android.yml). Download the **S23-Tablet-App** artifact from the latest successful run and unzip it. It contains `app-debug.apk`.
2. Open the [Windows companion workflow](https://github.com/AlhaFUN/s23-drawing-tablet/actions/workflows/windows-companion.yml). Download the **S23-Tablet-PC** artifact from the latest successful run and unzip it. It contains `S23DrawingTabletPC.exe`.

## First-time setup

1. Connect the phone to the PC with a USB data cable.
2. Enable USB debugging on the phone: open **Settings → About phone → Software information**, tap **Build number** seven times, then open **Settings → Developer options** and turn on **USB debugging**.
3. On the PC, get Google’s [Android SDK Platform-Tools for Windows](https://developer.android.com/tools/releases/platform-tools). Download the Windows ZIP, accept Google’s terms, and extract it. Android Studio is not needed.
4. Run `S23DrawingTabletPC.exe`. Click **Locate adb.exe…** and select `adb.exe` inside the extracted `platform-tools` folder. The companion remembers its location.

The Windows companion is open source but not code-signed, so Windows may show a SmartScreen warning. Download it from this repository’s Actions artifact.

## Connect and draw

1. Unlock the phone. In the PC companion, click **Connect phone**.
2. If the phone asks whether to allow USB debugging, tap **Allow**. The companion starts the Windows receiver, creates the USB connection, and opens the phone app.
3. If the phone app is not installed yet, click **Install phone APK…** in the PC companion and choose `app-debug.apk` from the Android artifact ZIP.
4. Wait for **Connected — ready to draw** on the phone. Draw with the S Pen in the phone’s drawing area; then draw in Paint or another Windows app.

Leave the PC companion open while drawing. Use **Disconnect** when finished. The companion restores the USB connection if the cable is briefly unplugged.

## If it does not connect

- On the phone, **Not connected** means the PC receiver or USB connection is not ready yet.
- Keep the phone unlocked and approve the USB debugging prompt.
- Check that the PC companion says the phone is connected and leave it running.
- If Windows does not detect the phone, try another USB data cable or USB port.

The Android drawing area previews S Pen strokes locally. Strokes reach Windows only after the phone says **Connected — ready to draw**. Finger touches are ignored.

## Notes

- The companion’s first setup needs an internet connection only to download Android Platform-Tools from Google. It does not install Android Studio or Python.
- Wi-Fi is an advanced, manual option; USB is the supported one-click setup.
- The Windows host uses the Windows pointer API. Some drawing apps may not accept synthetic pen input.
