'''
BLE link for the Breathing Cube (aioble + asyncio).

BLE is a secondary interface. These rules keep it out of the way of taps and
LEDs:
- Handlers here only parse bytes and queue a command dict. The main loop
  executes it (LEDs, timer, flash) when no tap is pending.
- The radio runs only during an "advertising window": at boot, after a
  double tap, or while USB power is present (all configurable). When the
  window ends with no connection the radio is shut off completely, so the
  main loop can light-sleep again.
- A connection that stays idle is dropped, so a forgotten phone cannot keep
  the radio (and the CPU) awake all day.
- Bringing the radio up blocks for a while, so it waits until the cube is
  quiet (no tap pending).

asyncio is cooperative. Nothing here can pre-empt the main loop, and the
main loop's own blocking calls (tap feedback sleep, alarm bell) delay this
code, not the other way round. The BLE controller itself runs in its own
FreeRTOS task, so links stay up while Python is busy.

GATT layout (128-bit UUIDs, see below):
  Command   write / write-without-response. UTF-8 text or JSON, see
            drivers/cubeCommands.py.
  Status    read / notify. Compact JSON with the cube state, the result of
            the last command, or perf counters after a "perf" command.
'''

import json
import sys
import time

import bluetooth

try:
    import asyncio
except ImportError:
    import uasyncio as asyncio

import aioble

from drivers.cubeCommands import parse_command

SERVICE_UUID = bluetooth.UUID("6e2a0001-8f3b-4c1a-9b4e-2f1c0b5e7a10")
COMMAND_UUID = bluetooth.UUID("6e2a0002-8f3b-4c1a-9b4e-2f1c0b5e7a10")
STATUS_UUID = bluetooth.UUID("6e2a0003-8f3b-4c1a-9b4e-2f1c0b5e7a10")

# While advertising "forever" (USB power), re-check every chunk so unplugging
# USB starts the normal timeout.
_ADV_CHUNK_MS = 10000
# How often a connected link is checked for idleness.
_IDLE_CHECK_MS = 5000
# Coalesce bursts of status changes into one notification.
_STATUS_MIN_INTERVAL_MS = 100
# Wait this long between "is the cube quiet?" checks before radio start-up.
_QUIET_POLL_MS = 50
# Radio start-up retries (ETIMEDOUT right after a stop).
_RADIO_UP_ATTEMPTS = 4
_RADIO_UP_RETRY_MS = 300


class BLEManager:
    def __init__(self, submit_command, get_status, perf,
                 is_quiet=None, keep_advertising=None,
                 name="BreathingCube",
                 adv_interval_us=500000,
                 adv_timeout_ms=30000,
                 conn_idle_timeout_ms=120000,
                 mtu=185,
                 command_max_len=128):
        """
        submit_command(cmd) -> bool   Queue a command dict for the main loop.
        get_status() -> dict          Snapshot of cube state (RAM only).
        perf                          PerfMonitor (may be disabled).
        is_quiet() -> bool            False while a tap is being handled.
        keep_advertising() -> bool    True to advertise with no timeout.
        adv_timeout_ms                None advertises forever (no light sleep).
        conn_idle_timeout_ms          None never drops an idle connection.
        """
        self._submit = submit_command
        self._get_status = get_status
        self._perf = perf
        self._is_quiet = is_quiet
        self._keep_advertising = keep_advertising
        self.name = name
        self.adv_interval_us = adv_interval_us
        self.adv_timeout_ms = adv_timeout_ms
        self.conn_idle_timeout_ms = conn_idle_timeout_ms
        self.mtu = mtu
        self.command_max_len = command_max_len

        # Built in _radio_up(): aioble.stop() tears down the write-capture
        # task, and only constructing a new capture characteristic restarts it.
        self._service = None
        self._command_char = None
        self._status_char = None

        self._window_event = asyncio.Event()
        self._status_event = asyncio.Event()
        self._deadline_ms = time.ticks_ms()
        self._last_activity_ms = 0
        self.radio_on = False
        self.connection = None
        self._last_result = None
        self._task = None
        self._window_task = None

    # ---------- Called from the main loop (same thread, never blocks) ----------
    def start(self):
        """Create the supervisor task. Call from inside the asyncio loop."""
        if self._task is None:
            self._task = asyncio.create_task(self._supervisor())

    def request_window(self, reason=""):
        """Advertise (or keep advertising) for adv_timeout_ms from now."""
        if self.adv_timeout_ms is not None:
            self._deadline_ms = time.ticks_add(time.ticks_ms(), self.adv_timeout_ms)
        if not self.radio_on and reason:
            print("BLE advertising requested:", reason)
        self._window_event.set()

    def stop_radio(self, reason=""):
        """Stop advertising, drop any connection and power the radio down.

        Returns at once; the supervisor task finishes the shutdown on its
        next turn (busy() stays True until then).
        """
        self._window_event.clear()
        if self._window_task is not None:
            if reason:
                print("BLE stopping:", reason)
            self._window_task.cancel()
        elif not self.radio_on:
            # main.py switches the controller on at boot to reserve its
            # memory. Nothing is using it, so power it straight down.
            try:
                bluetooth.BLE().active(False)
            except OSError:
                pass

    def busy(self):
        """True while the radio is on or about to be, so no light sleep."""
        return (self.radio_on or self._window_event.is_set()
                or self._window_task is not None)

    def is_connected(self):
        return self.connection is not None

    def report_result(self, result):
        """Main loop finished a command; publish it with the status."""
        self._last_result = result
        self.notify_status()

    def notify_status(self):
        if self.radio_on:
            self._status_event.set()

    # ---------- Radio power ----------
    async def _radio_up(self):
        if self.radio_on:
            return
        t0 = self._perf.t0()
        self._service = aioble.Service(SERVICE_UUID)
        self._command_char = aioble.BufferedCharacteristic(
            self._service, COMMAND_UUID,
            write=True, write_no_response=True, capture=True,
            max_len=self.command_max_len)
        self._status_char = aioble.Characteristic(
            self._service, STATUS_UUID, read=True, notify=True)
        # register_services() activates the radio (blocking, tens to
        # hundreds of ms) and builds the GATT table, which is lost on stop.
        # Re-activating soon after a stop can time out on the ESP32-C3
        # (ETIMEDOUT), so wait and retry a few times.
        for attempt in range(_RADIO_UP_ATTEMPTS):
            try:
                aioble.register_services(self._service)
                break
            except OSError as e:
                if attempt == _RADIO_UP_ATTEMPTS - 1:
                    raise
                print("BLE start retry:", e)
                self._perf.count("ble_retry")
                await asyncio.sleep_ms(_RADIO_UP_RETRY_MS)
        try:
            aioble.config(gap_name=self.name, mtu=self.mtu)
        except Exception as e:
            print("BLE config warning:", e)
        self.radio_on = True
        self._publish(self._status_payload(), notify=False)
        self._perf.add("ble_up", time.ticks_diff(time.ticks_us(), t0) if t0 else 0)
        self._perf.count("ble_on")

    def _radio_down(self):
        if not self.radio_on:
            return
        self.connection = None
        self.radio_on = False
        try:
            aioble.stop()  # Radio off; also clears aioble's server state.
        except Exception as e:
            print("BLE stop warning:", e)
        self._perf.count("ble_off")
        print("BLE radio off")

    # ---------- Tasks ----------
    async def _supervisor(self):
        while True:
            await self._window_event.wait()
            # Radio start-up blocks the CPU, so let a tap finish first.
            while self._is_quiet is not None and not self._is_quiet():
                await asyncio.sleep_ms(_QUIET_POLL_MS)
            if not self._window_event.is_set():
                continue  # stop_radio() was called while waiting.
            # Run the window as its own task so stop_radio() can cancel it.
            self._window_task = asyncio.create_task(self._run_window())
            try:
                await self._window_task
            except asyncio.CancelledError:
                pass  # stop_radio(): fall through to power down.
            except Exception as e:
                # Never let BLE take the cube down. Stop the radio and wait
                # for the next request.
                print("BLE error:", e)
                sys.print_exception(e)
                self._perf.count("ble_err")
            finally:
                self._window_task = None
                self._window_event.clear()
                self._radio_down()

    def _remaining_ms(self):
        """ms left in the window, or None for no timeout."""
        if self.adv_timeout_ms is None:
            return None
        if self._keep_advertising is not None and self._keep_advertising():
            return None
        return time.ticks_diff(self._deadline_ms, time.ticks_ms())

    async def _run_window(self):
        await self._radio_up()
        while True:
            remaining = self._remaining_ms()
            if remaining is not None and remaining <= 0:
                return
            timeout = _ADV_CHUNK_MS if remaining is None else min(remaining, _ADV_CHUNK_MS)

            adv_t = time.ticks_ms()
            self._perf.count("ble_adv")
            try:
                conn = await aioble.advertise(
                    self.adv_interval_us,
                    name=self.name,
                    services=[SERVICE_UUID],
                    timeout_ms=timeout,
                )
            except asyncio.TimeoutError:
                continue  # Re-check the window and keep advertising.
            if conn is None:
                return  # Advertising was cancelled.

            self._perf.add("ble_conn", time.ticks_diff(time.ticks_ms(), adv_t))
            await self._serve(conn)
            # Give the phone a full window to reconnect after a disconnect.
            if self.adv_timeout_ms is not None:
                self._deadline_ms = time.ticks_add(time.ticks_ms(), self.adv_timeout_ms)

    async def _serve(self, conn):
        print("BLE connected")
        self.connection = conn
        self._perf.count("ble_connect")
        started = time.ticks_ms()
        self._last_activity_ms = started
        self._status_event.set()  # Fresh status for the new client.
        command_task = asyncio.create_task(self._command_loop(conn))
        status_task = asyncio.create_task(self._status_loop())
        idle_task = None
        if self.conn_idle_timeout_ms is not None:
            idle_task = asyncio.create_task(self._idle_watchdog(conn))
        try:
            # No timeout here: a timeout inside aioble's disconnected()
            # cancels the waiting task, which would look like stop_radio().
            await conn.disconnected(timeout_ms=None)
        finally:
            command_task.cancel()
            status_task.cancel()
            if idle_task is not None:
                idle_task.cancel()
            self.connection = None
            self._perf.count("ble_disconnect")
            self._perf.add("ble_link", time.ticks_diff(time.ticks_ms(), started))
            print("BLE disconnected")

    async def _idle_watchdog(self, conn):
        """Drop a link that has sent nothing for conn_idle_timeout_ms."""
        while conn.is_connected():
            await asyncio.sleep_ms(_IDLE_CHECK_MS)
            if (time.ticks_diff(time.ticks_ms(), self._last_activity_ms)
                    >= self.conn_idle_timeout_ms):
                print("BLE link idle; disconnecting")
                self._perf.count("ble_idle_drop")
                try:
                    bluetooth.BLE().gap_disconnect(conn._conn_handle)
                except Exception:
                    pass
                return

    async def _command_loop(self, conn):
        while True:
            _, data = await self._command_char.written()
            self._last_activity_ms = time.ticks_ms()
            self._handle_write(conn, data)

    async def _status_loop(self):
        while True:
            await self._status_event.wait()
            self._status_event.clear()
            self._publish(self._status_payload(), notify=True)
            await asyncio.sleep_ms(_STATUS_MIN_INTERVAL_MS)

    # ---------- Command handling (short, no I2C / flash / LEDs) ----------
    def _handle_write(self, conn, data):
        self._perf.count("ble_rx")
        try:
            cmd = parse_command(data)
        except ValueError as e:
            self._perf.count("ble_bad")
            self.report_result("error: %s" % e)
            return

        op = cmd["op"]
        if op == "status":
            self.notify_status()
        elif op == "perf":
            self._publish(self._perf.summary(), notify=True)
        elif op == "perf_reset":
            self._perf.reset()
            self.report_result("perf reset")
        elif op == "disconnect":
            asyncio.create_task(conn.disconnect())
        else:
            cmd["rx_ms"] = time.ticks_ms()
            if not self._submit(cmd):
                self._perf.count("ble_busy")
                self.report_result("error: busy")

    def _status_payload(self):
        status = self._get_status()
        if self._last_result is not None:
            status["last"] = self._last_result
        return status

    def _publish(self, obj, notify):
        """Store obj as the Status value; notify subscribers if asked.

        Notifications are cut to MTU - 3 bytes; a read returns the whole value.
        """
        if not self.radio_on:
            return
        try:
            self._status_char.write(json.dumps(obj).encode(), send_update=notify)
        except Exception as e:
            print("BLE status write failed:", e)
