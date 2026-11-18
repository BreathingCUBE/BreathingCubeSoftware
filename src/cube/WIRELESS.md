# Cube wireless modes (BLE / WIFI / OFF)

Set `COMMUNICATION_MODE` at the top of `cube_app.py` (`main.py` is only a tiny launcher). Only one radio runs at a time.

| Mode   | What runs                                        | Main loop            |
|--------|--------------------------------------------------|----------------------|
| `BLE`  | `drivers/bleManager.py` (aioble)                 | one asyncio task     |
| `WIFI` | `NetworkingNode` + `NetworkWorker` (REST client) | plain loop + thread  |
| `OFF`  | nothing                                          | plain loop           |

BLE mode needs aioble on the board (one time):

```
py -3.14 -m mpremote connect COM5 mip install aioble
```

## Architecture

```
 IMU INT1 / USB pin ──> poll_wake_pins ─┐
                                        ├─> loop_once()  (physical input first)
 BLE write ─> BLEManager._handle_write  │     process_tap_events()
   parse_command() (cubeCommands.py)    │     process_remote_commands()  <- 1 per pass,
   submit_command() -> remote_commands ─┘                                only when no tap pending
                                              process_network*()  (WIFI only)
                                              apply_command() -> start_session / reset_session /
                                                                 upload_configSettings  (shared with
                                                                 taps and the REST sync reply)
```

BLE handlers never touch I2C, flash, or LEDs. They parse bytes and queue a dict.

## GATT

Service `6e2a0001-8f3b-4c1a-9b4e-2f1c0b5e7a10`

| Characteristic | UUID                                   | Props                  |
|----------------|----------------------------------------|------------------------|
| Command        | `6e2a0002-8f3b-4c1a-9b4e-2f1c0b5e7a10` | write, write w/o resp  |
| Status         | `6e2a0003-8f3b-4c1a-9b4e-2f1c0b5e7a10` | read, notify           |

Commands (UTF-8 text): `start`, `reset`, `stop`, `focus <seconds>`, `toggle`, `status`, `perf`, `perf reset`,
`disconnect`, `color #RRGGBB[XX]`, `time <seconds>`, `task <name>`.
JSON is also accepted: `{"cmd":"start"}` or a server-style settings payload
`{"task_name":"Read","task_color":"#00ff0000","task_time":1500}`.

Status is JSON, e.g.
`{"mode":"START","task":"Read","rgbw":[0,255,0,0],"preset":1500,"elapsed":42,"done":false,"usb":true,"last":"start: ok"}`.
Notifications are truncated to MTU-3 bytes; a Read always returns the full value.

## BLE power strategy

- BLE runs **only while USB-C power is present**. On battery alone the radio
  is fully off and light sleep works exactly as in `OFF` mode.
- Plugging USB in starts advertising (no timeout); unplugging drops any
  connection and `aioble.stop()` powers the radio down.
- After a disconnect the cube advertises again, so the app can reconnect.
- `BLE_ADV_INTERVAL_US` (default 500 ms) trades discovery speed for power.
- `BLE_CONN_IDLE_TIMEOUT_MS` can drop silent links (off by default).
- Stock MicroPython cannot light-sleep with the radio on; on USB the cube
  never light-sleeps anyway (it keeps the serial port alive).

## Testing with nRF Connect

1. Set `COMMUNICATION_MODE = "BLE"`, `PERF_ENABLED = True`, run `.\push.ps1`.
2. Plug in USB-C. Scan in nRF Connect; "BreathingCube" appears within ~1 s.
3. Connect, open the service, enable notifications on Status (the triple-arrow icon).
4. Write to Command as **UTF-8 text** (not hex): `start`, `color #ff000000`, `reset`.
   Status should notify `"last":"start: ok"` etc. and the LEDs should change.
5. Write `perf`, then Read Status, to get the counters (`[count, avg, max]`).
6. Reconnect test: disconnect in the app; the cube advertises again at once.
   Battery test: unplug USB; the link drops and the cube stops
   advertising (no longer in the scan list) until USB is plugged in again.
7. While connected, keep tapping. Taps must feel the same as in `OFF` mode.

## Comparing the three modes

Same session length, same tap script, same LED colour, for each mode:

1. `PERF_ENABLED = True`, flash, wait for boot, `perf reset` (BLE) or reboot.
2. Run the script (e.g. 20 double taps, 5 min breathing, 5 BLE commands / REST syncs).
3. Read the report: serial output every `PERF_REPORT_MS` on USB, or `perf` over BLE.
4. Power: measure battery current with a power analyser / PPK2 in series with the
   battery, USB unplugged (USB disables light sleep). Set `PERF_ENABLED = False`
   for the power runs so the instrumentation itself is not measured.
5. For true tap latency set `PERF_PROBE_PIN` to a free GPIO and scope it
   against IMU INT1 (pin 4): INT1 rising -> probe falling = tap to LED command.

Metrics: `late` (loop wake lateness; BLE/Wi-Fi interference shows here),
`busy`, `tap`, `led`, `cmd`, `ble_conn`, `ble_up`, `ble_link`, `wifi`,
`cpu%`, `bg%`, `sleep%`, `free`/`free_min` (heap bytes). See `drivers/perfMonitor.py`.

## Desktop app (DeliberatePracticeTimer)

`DeliberatePracticeTimer/cubeLink.py` (bleak) connects in a background thread
whenever the cube is on USB-C and advertising.

| App button       | Sent to the cube                                        | Cube does                                   |
|------------------|---------------------------------------------------------|---------------------------------------------|
| SWITCH TO FOCUS  | `{"cmd":"focus","task_time":<min*60>,"task_name":...}`  | saves preset + task, green blink, breathes, rings at the end |
| END FOCUS        | `stop`                                                  | stops timer, red blink, LEDs off            |
| DISCARD          | `stop`                                                  | same as END FOCUS                           |

A command pressed while the cube is not connected is sent on connect, with
the time already spent waiting taken off the focus time.

## Memory notes (why main.py is tiny)

MicroPython's heap starts at 64 KB; the app needs ~75 KB, so the heap grows
into ESP-IDF memory and the BLE controller (~56 KB) no longer fits
(`ble.active(True)` -> `EIO`). Fixes in place:
- `push.ps1` precompiles everything to `.mpy` with mpy-cross (match the firmware version).
- `main.py` switches BLE on before importing `cube_app`, reserving its memory;
  the app switches it off again on battery / WIFI / OFF.
- `gc.threshold(GC_THRESHOLD_BYTES)` keeps the heap from growing into the
  released memory, so BLE can start again when USB is plugged back in.
