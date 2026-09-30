VirtualDT — Windows companion
===============================

1. Install the Android APK and open VirtualDT on your phone.
2. Connect the phone to the PC with a USB data cable.
3. Turn on USB tethering in the phone's Settings.
4. Open VirtualDT.exe and click Connect phone.
5. The first time, enter the one-time code shown in the phone app. Future
   connections pair automatically.

USB debugging, ADB, Python, and manual firewall commands are not needed. No
tablet driver is installed. The PC connects out to the phone over USB tethering.

PREVIEW QUALITY AND FPS
-----------------------
Select a screen area, then choose Performance, Balanced, or High detail and an
FPS limit in the Windows app. Performance sends a smaller JPEG preview. These
settings apply the next time you connect. The selected area is both the phone
preview and the target area for pen mapping.

SCREEN AREA
-----------
Disconnect before changing the selection. Click “Select screen area...” and
drag around the part of the PC screen to show on your phone. Reconnect to use
that area for both the phone preview and pen mapping. Click “Show full screen”
to turn off the preview and map the pen across the whole Windows desktop.

PHONE DRAW PAD
--------------
Draw on the phone app's pad with a supported Android stylus. Tap “Full screen”
for a larger pad; press Android Back to return to the app. Finger touches are
ignored.

PAIRING AND PRIVACY
-------------------
The phone and PC create a unique key when paired. The phone protects its key
with Android Keystore and the Windows app protects its key for the current
Windows user. No shared password is built into the apps. The connection is
restricted to USB tethering and does not use Wi-Fi. Traffic on that tether is
not encrypted, so keep the service on the direct USB connection.

COMPATIBILITY
-------------
Works with Android 8+ devices whose stylus appears to apps as a stylus or
eraser, and that support USB tethering. Pressure, tilt, and buttons depend on
the device. Passive capacitive pens reported as fingers are ignored. The
Samsung Galaxy S23 Ultra is tested; other models need hardware testing.

Some drawing programs may ignore synthetic Windows pen input. Adapter names
also vary by phone maker and may affect automatic USB tether detection.

This standalone app is built from the open-source VirtualDT project. Python is
not required to run it.
