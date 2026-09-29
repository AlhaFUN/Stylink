S23 Drawing Tablet — Windows companion
========================================

1. Install the Android APK on the phone and open the S23 Drawing Tablet app.
2. Connect the phone to the PC using a USB data cable.
3. On the phone open Settings > Connections > Mobile Hotspot and Tethering,
   then turn on USB tethering.
4. Open S23DrawingTabletPC.exe and click Connect phone.
5. Draw on the phone with the S Pen.

USB tethering creates a small network link over the cable. The PC app finds
the phone automatically. USB debugging, ADB, Python, and manual firewall
commands are not needed. No custom tablet driver is installed; Windows uses
the USB network adapter provided by the phone/Windows. Windows Firewall does
not need an inbound rule because the PC connects out to the phone.

SCREEN AREA
-----------
Disconnect before changing the selection. Click “Select screen area...” and
drag around the part of the PC screen to show on the phone. Reconnect to use
that area for both the phone preview and pen mapping. Click “Show full screen”
to turn off the preview and map the pen across the whole Windows desktop.

PHONE DRAW PAD
--------------
Draw on the phone app's pad with the S Pen. Tap “Full screen” for a larger pad;
press Android Back to return to the app screen. Finger touches are ignored.

TROUBLESHOOTING
---------------
Keep both apps open and USB tethering enabled. If the PC app keeps looking,
check that Windows recognized a USB network adapter, then reconnect the cable
or try another USB data cable/port. Some drawing programs may not accept
Windows synthetic pen input.

This standalone EXE is built from the open-source project in pc/ and host/.
Python is not required to run it.
