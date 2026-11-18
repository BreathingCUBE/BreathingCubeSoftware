'''
Lightweight, optional timing instrumentation for comparing BLE / WIFI / OFF.

Design rules:
- With enabled=False every method returns immediately, so the hooks can stay
  in the main loop permanently.
- Nothing here prints except report(). The controller only calls report()
  while USB power is present and no tap or command is pending.
- No allocation in the hot paths: each Stat is a handful of ints.

What is measured (all on the main loop, using ticks_us):
  late     How late the main loop woke compared with the sleep it asked for.
           In BLE mode this is the time other asyncio tasks (BLE) held the
           CPU, plus light-sleep wake-up time. The best single number for
           "did wireless delay the cube?".
  busy     Time spent in one main-loop pass (taps, timer, commands, LEDs).
  tap      INT1 seen high -> first LP5814 feedback command written.
           Does not include the time INT1 was high before the loop polled
           it; that is bounded by `late` + the poll interval. Use the probe
           pin and a scope on INT1 for the true end-to-end figure.
  led      Duration of each LP5814 command sequence (I2C + interference).
  cmd      Remote command received -> applied on the main loop (ms).
  ble_conn Advertising start -> connected (ms).
  ble_up   Time to bring the BLE radio up (us). This blocks the CPU.
  ble_link Connection duration (ms).
  wifi     REST request handed to the worker -> result (ms).

Shares of wall time since the last reset:
  cpu      busy / elapsed
  bg       late / elapsed (CPU used by other tasks, approximate)
  sleep    time in light sleep / elapsed (the power-relevant one)
'''

import gc
import time

try:
    from machine import Pin
except ImportError:  # Lets the module import on a desktop for tests.
    Pin = None


class Stat:
    def __init__(self):
        self.reset()

    def reset(self):
        self.n = 0
        self.total = 0
        self.max = 0
        self.last = 0

    def add(self, value):
        if value < 0:
            value = 0
        self.n += 1
        self.total += value
        self.last = value
        if value > self.max:
            self.max = value

    def avg(self):
        return self.total // self.n if self.n else 0

    def summary(self):
        return [self.n, self.avg(), self.max]


STAT_NAMES = ("late", "busy", "tap", "led", "cmd",
              "ble_conn", "ble_up", "ble_link", "wifi")
UNITS = {"late": "us", "busy": "us", "tap": "us", "led": "us", "cmd": "ms",
         "ble_conn": "ms", "ble_up": "us", "ble_link": "ms", "wifi": "ms"}
MEM_SAMPLE_MS = 1000


class PerfMonitor:
    def __init__(self, enabled=False, probe_pin=None, mode=""):
        self.enabled = enabled
        self.mode = mode
        self.stats = {}
        for name in STAT_NAMES:
            self.stats[name] = Stat()
        self.counts = {}
        # Optional GPIO that goes high when a tap is seen and low once the
        # LED feedback command is written. Scope it against IMU INT1.
        self.probe = None
        if enabled and probe_pin is not None and Pin is not None:
            self.probe = Pin(probe_pin, Pin.OUT, value=0)
        self._wifi_pending = []
        self.reset()

    # ---------- bookkeeping ----------
    def reset(self):
        for stat in self.stats.values():
            stat.reset()
        self.counts = {}
        self._t_reset = time.ticks_us()
        self._pass_t = 0
        self._expected_wake = None
        self._sleep_t = 0
        self._sleep_light = False
        self._light_us = 0
        self._busy_us = 0
        self._late_us = 0
        self._tap_t = 0
        self._mem_t = time.ticks_ms()
        self.mem_min = None
        self._last_report = time.ticks_ms()

    def count(self, name):
        if self.enabled:
            self.counts[name] = self.counts.get(name, 0) + 1

    def t0(self):
        return time.ticks_us() if self.enabled else 0

    # ---------- main loop ----------
    def pass_start(self):
        if not self.enabled:
            return
        now = time.ticks_us()
        if self._expected_wake is not None:
            late = time.ticks_diff(now, self._expected_wake)
            if late < 0:
                late = 0  # Woke early (tap or USB), which is good.
            self.stats["late"].add(late)
            self._late_us += late
            if self._sleep_light:
                self._light_us += time.ticks_diff(now, self._sleep_t) - late
            self._expected_wake = None
        self._pass_t = now

    def pass_end(self):
        if not self.enabled:
            return
        busy = time.ticks_diff(time.ticks_us(), self._pass_t)
        self.stats["busy"].add(busy)
        self._busy_us += busy
        if time.ticks_diff(time.ticks_ms(), self._mem_t) >= MEM_SAMPLE_MS:
            self.sample_mem()

    def will_sleep(self, ms, light):
        if not self.enabled:
            return
        now = time.ticks_us()
        self._sleep_t = now
        self._sleep_light = light
        self._expected_wake = time.ticks_add(now, ms * 1000)

    def will_yield(self):
        """An asyncio sleep_ms(0): any delay is other tasks' CPU time."""
        self.will_sleep(0, False)

    # ---------- events ----------
    def tap_begin(self):
        if not self.enabled:
            return
        self._tap_t = time.ticks_us()
        if self.probe:
            self.probe.value(1)

    def tap_end(self):
        if not self.enabled or not self._tap_t:
            return
        if self.probe:
            self.probe.value(0)
        self.stats["tap"].add(time.ticks_diff(time.ticks_us(), self._tap_t))
        self._tap_t = 0

    def led_done(self, t0):
        if self.enabled:
            self.stats["led"].add(time.ticks_diff(time.ticks_us(), t0))

    def cmd_applied(self, rx_ms):
        if self.enabled and rx_ms is not None:
            self.stats["cmd"].add(time.ticks_diff(time.ticks_ms(), rx_ms))

    def add(self, name, value):
        if self.enabled:
            self.stats[name].add(value)

    def wifi_sent(self):
        if self.enabled:
            self._wifi_pending.append(time.ticks_ms())

    def wifi_done(self, ok):
        if not self.enabled:
            return
        self.count("wifi_ok" if ok else "wifi_fail")
        if self._wifi_pending:
            self.stats["wifi"].add(time.ticks_diff(time.ticks_ms(), self._wifi_pending.pop(0)))

    def sample_mem(self):
        self._mem_t = time.ticks_ms()
        free = gc.mem_free()
        if self.mem_min is None or free < self.mem_min:
            self.mem_min = free

    # ---------- output ----------
    def summary(self):
        """Compact dict, also sent over BLE. Stats are [count, avg, max]."""
        elapsed = time.ticks_diff(time.ticks_us(), self._t_reset) or 1
        out = {
            "mode": self.mode,
            "s": elapsed // 1000000,
            "cpu": self._busy_us * 1000 // elapsed / 10,
            "bg": self._late_us * 1000 // elapsed / 10,
            "sleep": self._light_us * 1000 // elapsed / 10,
            "free": gc.mem_free(),
            "free_min": self.mem_min,
        }
        for name, stat in self.stats.items():
            if stat.n:
                out[name] = stat.summary()
        if self.counts:
            out["n"] = self.counts
        return out

    def due(self, interval_ms):
        if not self.enabled or not interval_ms:
            return False
        return time.ticks_diff(time.ticks_ms(), self._last_report) >= interval_ms

    def report(self):
        if not self.enabled:
            return
        self._last_report = time.ticks_ms()
        s = self.summary()
        print("--- perf [%s] %ds  cpu %s%%  bg %s%%  sleep %s%%  free %d (min %s)" % (
            s["mode"], s["s"], s["cpu"], s["bg"], s["sleep"], s["free"], s["free_min"]))
        for name in STAT_NAMES:
            stat = self.stats[name]
            if stat.n:
                print("  %-8s n=%-6d avg=%-8d max=%-8d %s" % (
                    name, stat.n, stat.avg(), stat.max, UNITS[name]))
        if self.counts:
            print("  counts", self.counts)
