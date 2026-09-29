$ErrorActionPreference = 'Stop'

adb devices
if ($LASTEXITCODE -ne 0) {
    throw 'adb failed. Install Android Platform Tools and enable USB debugging.'
}

adb reverse tcp:8765 tcp:8765
if ($LASTEXITCODE -ne 0) {
    throw 'Could not create adb reverse. Check the USB authorization prompt on the phone.'
}

Write-Host 'USB route ready. Configure the Android app to connect to 127.0.0.1:8765.'
