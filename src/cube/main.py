# main.py (MicroPython / ESP32)
# .\push.ps1
#
# Keep this file tiny. The application lives in cube_app.py, which push.ps1
# precompiles to cube_app.mpy.
#
# Memory: MicroPython starts with a 64 KB heap. Loading the app needs more,
# so the heap grows into the ESP-IDF system memory, and afterwards the BLE
# controller (~56 KB) no longer fits (ble.active(True) fails with EIO).
# Switching the controller on *before* loading the app lets it claim its
# memory first. cube_app turns it straight off again when BLE is not wanted
# (on battery, or WIFI/OFF mode); a GC threshold then keeps the Python heap
# from growing into the released memory, so BLE can start again later.

import bluetooth

try:
    bluetooth.BLE().active(True)
except OSError as e:
    print("BLE memory reservation failed:", e)

import cube_app

cube_app.main()
