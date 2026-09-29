# S23 Drawing Tablet

Use a Galaxy S23 Ultra and its S Pen as a Windows drawing tablet. The project provides an Android app and a standalone Windows companion app.

## Install the apps

1. Download the latest successful [Android build](https://github.com/AlhaFUN/s23-drawing-tablet/actions/workflows/android.yml). Under **Artifacts**, download **S23-Tablet-App**, unzip it, then install `app-debug.apk` on your phone. Android may ask you to allow this APK to be installed.
2. Download the latest successful [Windows companion build](https://github.com/AlhaFUN/s23-drawing-tablet/actions/workflows/windows-companion.yml). Under **Artifacts**, download **S23-Tablet-PC-Setup**, unzip it, then open `S23DrawingTabletPC.exe`.

Windows may show a SmartScreen message because the community build is not code-signed. Download the app from this project's Actions page.

## Connect over USB tethering

1. Connect the phone and PC with a USB data cable.
2. On the phone, open **Settings → Connections → Mobile Hotspot and Tethering** and turn on **USB tethering**. This setting appears when the phone is connected to the PC.
3. Open **S23 Drawing Tablet** on the phone.
4. Open the Windows companion and click **Connect phone**. Wait for **Connected — ready to draw**.

The PC app finds the phone over the USB-tethered network automatically. This does not use USB debugging, ADB, a driver installer, or an inbound Windows Firewall rule. Keep both apps open while drawing.

## Draw

- Draw in the phone app's **Drawing pad** with the S Pen. Finger touches are ignored. Tap **Full screen** for a larger pad; press Android Back to leave it.
- To show only part of the PC screen on the phone, disconnect, click **Select screen area…** in the PC app, and drag a rectangle. Reconnect to see that area on the phone and map the S Pen to it.
- Click **Show full screen** in the PC app to map the S Pen across the whole Windows desktop and turn off the phone preview.

## If it does not connect

- Make sure USB tethering is on while the phone is plugged into the PC. The phone app should say that USB tethering is on; the PC app will keep looking for it.
- Keep the phone app open and click **Connect phone** in the PC app.
- Try another USB data cable or USB port if Windows does not show a USB network connection.
- Disconnect and reconnect after changing the screen selection.

## Project files

- Android app: [`android/`](android/)
- Windows app and setup guide: [`pc/`](pc/) and [`host/`](host/)
- Android APK workflow: [`.github/workflows/android.yml`](.github/workflows/android.yml)
- Windows app workflow: [`.github/workflows/windows-companion.yml`](.github/workflows/windows-companion.yml)

The Windows host injects synthetic pen input through the Windows pointer API. Some drawing programs may ignore synthetic pen input or handle pressure differently.
