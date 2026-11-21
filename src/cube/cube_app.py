# cube_app.py (MicroPython / ESP32) - the cube application.
# main.py only imports this; push.ps1 precompiles it to cube_app.mpy so the
# board never compiles this large file (that used up the RAM BLE needs).
# .\push.ps1

# one button, one led, one timer, and a dream

import gc
import time
import esp32
from machine import ADC, I2C, Pin, PWM, lightsleep, unique_id
from time import sleep_ms
# import secrets  # secrets.WIFI_SSID, WIFI_PASSWORD, SERVER_IP, SERVER_PORT
import json

from drivers.lp5814_ledDriver import LP5814
from drivers.lp5811_ledDriver import LP5811
from drivers.piezoElectric import PiezoButton
from drivers.pomodoroTimer import PomodoroTimer
from drivers.alarm import Alarm
# from drivers.networkingNode import NetworkingNode  # adjust import to your actual path/name
# from drivers.networkWorker import NetworkWorker
from drivers.batteryMeasurement import BatteryMeasurement 
from drivers.lsm6dsl import LSM6DSL
from drivers.dataTransfer import DeviceSettings
from drivers.perfMonitor import PerfMonitor
from drivers.lp5814_ledDriver import TIME_MS
# import socket

# ---- Wireless ----
# Only one wireless interface runs at a time.
#   "BLE"  - BLE commands/status via aioble (drivers/bleManager.py). Wi-Fi off.
#   "WIFI" - the REST client below (NetworkingNode + NetworkWorker). BLE off.
#   "OFF"  - both radios off, for the longest battery life.
COMMUNICATION_MODE = "BLE"

# BLE power: the radio runs only while USB-C power is present. On battery
# alone it is fully off, so light sleep works as before. Unplugging USB drops
# any connection and powers the radio down.
# Stable ID from the chip's factory serial number. The phone app uses it to
# find this cube's profile in Firebase (cubes/{CUBE_ID}), so no login is needed.
CUBE_ID = "cube-" + "".join("%02x" % b for b in unique_id())
# The advertised name ends in the last 4 ID digits so a phone can tell cubes apart.
BLE_NAME = "BreathingCube-" + CUBE_ID[-4:].upper()
BLE_ADV_INTERVAL_US = 500000       # Longer = less power, slower discovery.
BLE_CONN_IDLE_TIMEOUT_MS = None    # Drop a silent link after this. None = never.
BLE_MTU = 185
REMOTE_QUEUE_MAX = 4               # Remote commands waiting for the main loop.
LOOP_POLL_MS = 10                  # Loop interval while light sleep is not allowed.
# Collect garbage after this many bytes are allocated. Without it the ESP32
# port grows its heap (before collecting) into memory BLE needs. See main.py.
GC_THRESHOLD_BYTES = 4096

# ---- Performance instrumentation (drivers/perfMonitor.py) ----
PERF_ENABLED = False
PERF_REPORT_MS = 10000      # Print a summary this often, only while on USB. 0 = never.
PERF_PROBE_PIN = None       # Optional free GPIO pulsed tap->LED, for a scope.

if COMMUNICATION_MODE not in ("BLE", "WIFI", "OFF"):
    raise ValueError("COMMUNICATION_MODE must be BLE, WIFI or OFF")

if COMMUNICATION_MODE == "BLE":
    try:
        import asyncio
    except ImportError:
        import uasyncio as asyncio
    from drivers.bleManager import BLEManager
elif COMMUNICATION_MODE == "WIFI":
    import secrets  # secrets.WIFI_SSID, WIFI_PASSWORD, SERVER_IP, SERVER_PORT
    from drivers.networkingNode import NetworkingNode
    from drivers.networkWorker import NetworkWorker

MODE_RESET = "RESET"
MODE_START = "START"
MODE_CONFIG  = 2
MODE_ERROR   = 3

OFFLINE_RGBW = [0,0,255,0] # default white color, can be changed by server config
# CONFIGURED_RGBW = [255,153,255,255] # default green color, can be changed by server config
OFFLINE_PATTERN = [0x0D, 0x0D, 0x0D, 0x0D] # 4 seconds per breathing stage
DOUBLE_TAP_WINDOW_MS = 700
TAP_FEEDBACK_MS = 700  # LP5814 timing codes [2, 3, 4, 5] total 700 ms.
TAP_FEEDBACK_BRIGHTNESS = 150

# ---- Low power ----
# Light sleep only runs on battery. While USB power is present the chip stays
# awake, because light sleep shuts off the ESP32-C3's USB serial port and
# mpremote/push.ps1 can no longer connect.
LOW_POWER_ENABLED = True
# Taps wake the chip immediately through a GPIO wake on IMU INT1, so this only
# limits how long a USB plug-in can go unnoticed.
IDLE_SLEEP_MS = 1000      # Longest single light sleep.
USB_DEBOUNCE_MS = 20      # The USB sense pin must hold a new level this long to count.
BOOT_GRACE_MS = 5000      # Stay awake this long after boot so the board can always be reached.

# ---- Networking (COMMUNICATION_MODE = "WIFI") ----
WIFI_CONNECT_TIMEOUT_S = 5
# On battery, turn WiFi off after each request so the cube can light-sleep.
# On USB, WiFi stays connected so taps report faster.
WIFI_OFF_ON_BATTERY = True
# Server reports are queued and only sent once no tap has happened for this
# long. Sending blocks for seconds, and taps during a send cannot be timed, so
# this keeps the network out of the way of double taps.
NETWORK_QUIET_MS = 1000
# How to read the last two digits of an 8-digit task_color like "#ffaa00ff":
#   "RGBA" - opacity, as web colour pickers send it; the white LED stays off.
#   "RGBW" - white LED level.
SERVER_COLOR_FORMAT = "RGBA"
LIGHTS_ENABLED = True

# ---- Sounds (drivers/alarm.py) ----
SOUNDS_ENABLED = True         # Master switch for every sound below.
# Session start: rising chirp. Session stop: falling chirp.
SESSION_END_SOUND = "phrase"   # "phrase", "bowl", "bell" or "none"
BREATH_CUES_ENABLED = False    # Soft tone on each inhale/exhale. Off by default.
BREATH_CUE_MAX_LATE_MS = 300   # Skip a cue that is this late instead of playing it off-beat.

class CubeController:
    def __init__(self):
        self.boot_ms = time.ticks_ms()
        self.comm_mode = COMMUNICATION_MODE
        self.perf = PerfMonitor(PERF_ENABLED, PERF_PROBE_PIN, COMMUNICATION_MODE)
        self.disable_unused_radios()

        # ---- Hardware ----
        # self.onboard_led = Pin(2, Pin.OUT)
        # I2C + LP5814      
        self.batteryMeasurement = BatteryMeasurement(
            adc_pin=1,
            samples=10,
            sample_interval_ms=50,
        )
        self.i2c = I2C(0, scl=Pin(7), sda=Pin(6))
        self.lp = LP5814(self.i2c, chip_addr=0x2C)
        self.lsm6dsl = LSM6DSL(self.i2c)  # Initialize the LSM6DSL instance
        self.testNum = 0
        self.lsm6dsl_irq_pending = False
        self.polled_tap_source = None  # TAP_SRC already read by poll_wake_pins().
        self.tap_waiting_for_second = False
        self.first_tap_ms = 0
        self.last_tap_ms = time.ticks_ms()
        self.pending_reports = []  # (action, elapsed_seconds, sync) waiting to send
        # Commands from BLE (or any other link), executed by the main loop.
        self.remote_commands = []
        self.last_command_result = None
        self.init_lp5814()
        
        # Inputs
        # self.piezo = PiezoButton(pin=0) # This is now a MOSFET so it will not really work

        self.alarm = Alarm(speaker_pin=10)
        self.cubeData = DeviceSettings()
        # Timer (callbacks point to controller methods)
        self.timer = PomodoroTimer(
            on_session_complete=self.on_session_complete,
            on_reminder=self.on_reminder,
        )

        self.isUsb = Pin(21, Pin.IN)
        self.usb_irq_pending = False
        # This input is active-low: 0 means USB VBUS is present.
        self.usb_power_present = self.isUsb.value() == 0
        print("USB VBUS present:", self.usb_power_present)

        self.isUsb.irq(
            trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING,
            handler=self.on_usb_sense_irq,
        )
        # Networking (WIFI mode only). Background thread does all WiFi/HTTP work.
        self.network_inst = None
        self.net_worker = None
        self.sync_in_progress = False
        if self.comm_mode == "WIFI":
            self.network_inst = NetworkingNode(
                secrets.WIFI_SSID,
                secrets.WIFI_PASSWORD,
                secrets.SERVER_IP,
                secrets.SERVER_PORT,
            )
            self.net_worker = NetworkWorker(self.network_inst, WIFI_CONNECT_TIMEOUT_S)

        # BLE (BLE mode only). Its tasks start in run_async().
        self.ble = None
        if self.comm_mode == "BLE":
            self.ble = BLEManager(
                submit_command=self.submit_command,
                get_status=self.status_snapshot,
                perf=self.perf,
                is_quiet=self.physical_input_idle,
                name=BLE_NAME,
                adv_interval_us=BLE_ADV_INTERVAL_US,
                adv_timeout_ms=None,  # Advertise for as long as USB is present.
                conn_idle_timeout_ms=BLE_CONN_IDLE_TIMEOUT_MS,
                mtu=BLE_MTU,
            )

        # The controller toggles between reset and start states.
        self.task = self.cubeData.task
        self.alarm_type = self.cubeData.alarm_type
        self.mode = MODE_RESET
        self.stopWatchPresetTime = self.cubeData.stopWatchPresetTime
        self.RGBW = self.lp.normalize_rgbw(self.cubeData.RGBW)
        self.animation_pattern = self.cubeData.animation_pattern
        print("Loaded RGBW [R, G, B, W]:", self.RGBW)
        # IMU INT1 goes high for ~11 ms per tap (measured; not latched).
        # It has no edge IRQ: poll_wake_pins() reads its level and TAP_SRC
        # every loop pass, and esp32.wake_on_gpio() wakes the chip from light
        # sleep when it goes high. (A GPIO wake sets the pin's interrupt type
        # to level-high, so an IRQ handler on this pin would fire nonstop
        # while INT1 is high.)
        self.lsm6dsl_int1 = Pin(4, Pin.IN)

        print("Battery voltage:", self.batteryMeasurement.measure())  # Save power until a measurement is requested.
        # self.alarm.bell();
        # self.alarm.wooden_tick_tock()

        self.next_breath_cue_ms = None
        self.breath_cue_inhale = True

        
        self.alarm.wooden_clack(650)
        self.alarm.wooden_clack(1000)
        self.alarm.wooden_clack(1100)

    def disable_unused_radios(self):
        """Make sure only the selected wireless interface can be on."""
        if self.comm_mode != "BLE":
            try:
                import bluetooth
                bluetooth.BLE().active(False)
            except Exception as e:
                print("BLE off failed:", e)
        # Wi-Fi is off at boot. Calling WLAN() would initialise the Wi-Fi
        # driver (and allocate its memory) just to switch it off, which in BLE
        # mode fails for lack of RAM, so only do it in OFF mode.
        if self.comm_mode == "OFF":
            try:
                import network
                network.WLAN(network.STA_IF).active(False)
            except Exception as e:
                print("WiFi off failed:", e)

    def on_usb_sense_irq(self, pin):
        # self.lp.connected_animation()
        self.usb_irq_pending = True


    def process_usb_sense(self):
        if not self.usb_irq_pending:
            return

        self.usb_irq_pending = False

        # Ignore glitches: only act if the pin still shows the new level
        # after a short wait.
        present = self.isUsb.value() == 0
        if present == self.usb_power_present:
            return
        sleep_ms(USB_DEBOUNCE_MS)
        if (self.isUsb.value() == 0) != present:
            return

        self.usb_power_present = present
        print("USB VBUS connected" if present else "USB VBUS disconnected")
        if not present:
            self.wifi_release()  # Now on battery: drop WiFi so light sleep can run.
        self.update_ble_power()

    def update_ble_power(self):
        """BLE runs only on USB power; battery alone keeps the radio off."""
        if not self.ble:
            return
        if self.usb_power_present:
            self.ble.request_window("USB power")
        else:
            self.ble.stop_radio("on battery")
            
    def process_tap_events(self):
        """Recognize a software double tap from two IMU single-tap events."""
        now = time.ticks_ms()

        #if an interrupt occurs, then do the following.
        if self.lsm6dsl_irq_pending:
            self.lsm6dsl_irq_pending = False # reset interrupt so it can happen again
            if self.polled_tap_source is not None:
                # poll_wake_pins() already read (and so cleared) TAP_SRC.
                tap_source = self.polled_tap_source
                self.polled_tap_source = None
            else:
                tap_source = self.lsm6dsl.read_tap_source()
            print("TAP_SRC = 0x%02X" % tap_source)

            # SINGLE_TAP is only set during the ~11 ms INT1 pulse. A tap read
            # after the pulse shows just its axis bit, which still counts.
            if tap_source & (self.lsm6dsl.TAP_SRC_SINGLE_TAP | self.lsm6dsl.TAP_SRC_AXES):
                self.last_tap_ms = now  # Holds off queued network sends.
                self.testNum += 1
                print("Single tap event:", self.testNum)

                if self.tap_waiting_for_second: #Boolean to check if we are waiting for a second tap
                    elapsed = time.ticks_diff(now, self.first_tap_ms)
                    if elapsed <= DOUBLE_TAP_WINDOW_MS:
                        self.tap_waiting_for_second = False
                        self.handle_double_tap()
                        return

                # A single tap has no effect; only a second tap in the window
                # can change the state.
                self.tap_waiting_for_second = True
                self.first_tap_ms = now
                # No sound here: the speaker's vibration stops the IMU from
                # detecting the second tap. Sounds play only once the double
                # tap is confirmed (start_session / reset_session).
                if LIGHTS_ENABLED:
                    if self.mode == MODE_START:
                        self.led_feedback([TAP_FEEDBACK_BRIGHTNESS // 2, 0, 0, 0])  # // keeps it a whole number.
                    else:
                        # self.led_feedback([value // 2 for value in CONFIGURED_RGBW])
                        self.led_feedback([value // 2 for value in self.RGBW])
            else:
                print("Interrupt was not identified as a single tap")
            self.perf.tap_end()  # No-op if feedback already ended it.

        # Expired first taps are intentionally discarded.
        if (self.tap_waiting_for_second and
                time.ticks_diff(now, self.first_tap_ms) >= DOUBLE_TAP_WINDOW_MS):
            self.tap_waiting_for_second = False
            if LIGHTS_ENABLED and self.mode == MODE_START:
                self.start_breathing_lights()

    # ---------- Low power ----------
    def poll_wake_pins(self):
        """Catch IMU taps and USB plug changes by reading pin levels.

        INT1 is only an ~11 ms pulse per tap (the IMU does not latch it), so
        a loop pass that comes later than that misses the pin. With BLE on,
        passes are 20-30 ms apart. The tap's axis bit in TAP_SRC does stay
        set until read, so it is checked too (one short I2C read per pass).
        Edge IRQs do not fire during light sleep, so the USB sense pin is
        also checked after every wake.
        """
        if not self.lsm6dsl_irq_pending:
            if self.lsm6dsl_int1.value():
                self.perf.tap_begin()
                self.lsm6dsl_irq_pending = True
            else:
                src = self.lsm6dsl.read_tap_source()
                if src & (self.lsm6dsl.TAP_SRC_SINGLE_TAP | self.lsm6dsl.TAP_SRC_AXES):
                    self.perf.tap_begin()
                    self.polled_tap_source = src  # The read cleared it; keep it.
                    self.lsm6dsl_irq_pending = True
        if (self.isUsb.value() == 0) != self.usb_power_present:
            self.usb_irq_pending = True

    def low_power_allowed(self):
        if not LOW_POWER_ENABLED:
            return False
        if self.usb_power_present:
            return False  # Keep the USB serial port alive for mpremote.
        if self.network_busy():
            return False  # Light sleep would freeze the send and drop WiFi.
        if self.ble and self.ble.busy():
            return False  # Light sleep and an active BLE radio do not mix.
        if time.ticks_diff(time.ticks_ms(), self.boot_ms) < BOOT_GRACE_MS:
            return False
        return True

    def light_sleep_budget(self):
        """How long the loop may wait before its next pass.

        0 = run the next pass now, None = light sleep is not allowed (poll
        every LOOP_POLL_MS instead), otherwise milliseconds of light sleep.
        """
        if self.lsm6dsl_irq_pending or self.usb_irq_pending:
            return 0
        if self.remote_commands_ready():
            return 0

        if not self.low_power_allowed():
            return None

        sleep_time = IDLE_SLEEP_MS

        # Do not sleep past the software double-tap deadline.
        if self.tap_waiting_for_second:
            elapsed = time.ticks_diff(time.ticks_ms(), self.first_tap_ms)
            remaining = DOUBLE_TAP_WINDOW_MS - elapsed
            if remaining <= 0:
                return 0
            sleep_time = min(sleep_time, remaining)

        # Do not sleep past the session end or a reminder.
        next_event = self.timer.ms_until_next_event()
        if next_event is not None:
            if next_event <= 0:
                return 0
            sleep_time = min(sleep_time, next_event)

        # Do not sleep past the moment queued reports are due to send.
        if self.pending_reports:
            wait = self.ms_until_network_due()
            if wait <= 0:
                return 0
            sleep_time = min(sleep_time, wait)

        # Do not sleep past the next breathing cue.
        if self.next_breath_cue_ms is not None:
            wait = time.ticks_diff(self.next_breath_cue_ms, time.ticks_ms())
            if wait <= 0:
                return 0
            sleep_time = min(sleep_time, wait)

        return sleep_time

    def idle(self):
        """Wait until the next loop pass, using light sleep when allowed."""
        budget = self.light_sleep_budget()
        if budget == 0:
            return
        if budget is None:
            self.perf.will_sleep(LOOP_POLL_MS, False)
            sleep_ms(LOOP_POLL_MS)
            return
        self.perf.will_sleep(budget, True)
        lightsleep(budget)

    async def idle_async(self):
        """idle() for BLE mode: waits by yielding to the BLE tasks.

        Light sleep only happens with the BLE radio off, when no BLE task
        needs to run, so blocking the event loop there is harmless.
        """
        budget = self.light_sleep_budget()
        if budget == 0:
            self.perf.will_yield()
            await asyncio.sleep_ms(0)
            return
        if budget is None:
            self.perf.will_sleep(LOOP_POLL_MS, False)
            await asyncio.sleep_ms(LOOP_POLL_MS)
            return
        self.perf.will_sleep(budget, True)
        lightsleep(budget)
        await asyncio.sleep_ms(0)

    def handle_double_tap(self):
        """Toggle between starting a session and resetting it."""
        if self.mode == MODE_START:
            print("Double tap detected; resetting session")
            self.reset_session()
        else:
            print("Double tap detected; starting session")
            self.start_session()

    # Session changes shared by taps and remote commands (BLE).
    def start_session(self):
        self.mode = MODE_START
        t = time.ticks_ms()
        if LIGHTS_ENABLED:
            self.led_feedback(self.RGBW)
        if SOUNDS_ENABLED:
            self.alarm.chirp_up()  # Plays during the LED blink, not after it.
        if LIGHTS_ENABLED:
            sleep_ms(max(0, TAP_FEEDBACK_MS - time.ticks_diff(time.ticks_ms(), t)))
            self.start_breathing_lights()
        self.start_breath_cues()
        self.timer.set_time(self.stopWatchPresetTime)
        self.timer.start()
        self.queue_report("start", 0)
        self.comm_state_changed()

    def reset_session(self):
        elapsed_seconds = self.timer.session_elapsed_ms // 1000  # Before reset clears it.
        self.timer.reset()
        self.timer.set_time(self.stopWatchPresetTime)
        self.mode = MODE_RESET
        self.next_breath_cue_ms = None
        t = time.ticks_ms()
        if LIGHTS_ENABLED:
            self.led_feedback([255, 0, 0, 0])
        if SOUNDS_ENABLED:
            self.alarm.chirp_down()
        if LIGHTS_ENABLED:
            sleep_ms(max(0, TAP_FEEDBACK_MS - time.ticks_diff(time.ticks_ms(), t)))
            self.lp.shutdown()
        # Report the reset and pull any new settings (WIFI mode only).
        self.queue_report("reset", elapsed_seconds, sync=True)
        self.comm_state_changed()

    def led_feedback(self, rgbw):
        """One-shot LED blink; also closes the tap -> LED timing measurement."""
        t0 = self.perf.t0()
        self.lp.blink_animation(rgbw)
        self.perf.led_done(t0)
        self.perf.tap_end()

    def start_breathing_lights(self):
        t0 = self.perf.t0()
        self.lp.init_auto(exponential=False)
        self.lp.led_all_breathing(
            RGBW=self.RGBW,
            duration_ms=self.animation_pattern
        )
        self.lp.start_cmd()
        self.perf.led_done(t0)

    def controller_success_animation(self):
        print("Success mode: flashing green")
        if LIGHTS_ENABLED:
            self.lp.success_animation()

    def controller_error_animation(self):
        print("Error mode: flashing red")
        if LIGHTS_ENABLED:
            self.lp.fail_animation()
        
    # ---------- Callbacks ----------
    def on_session_complete(self):
        print("Timer finished")
        self.next_breath_cue_ms = None
        if SOUNDS_ENABLED:
            self.play_session_end_sound()
        if LIGHTS_ENABLED:
            self.lp.stop_cmd()
        self.timer.pause()
        self.comm_state_changed()

    def on_reminder(self):
        print("Reminder!")

    # ---------- Sounds (drivers/alarm.py) ----------
    def play_session_end_sound(self):
        # A tap silences the sound. INT1 stays latched, so the tap is still
        # handled normally afterwards.
        tapped = lambda: self.lsm6dsl_int1.value()
        if SESSION_END_SOUND == "phrase":
            self.alarm.rising_phrase(stop_check=tapped)
        elif SESSION_END_SOUND == "bowl":
            self.alarm.singing_bowl(stop_check=tapped)
        elif SESSION_END_SOUND == "bell":
            self.alarm.bell()

    def breath_stage_ms(self):
        """Breathing stages in ms: rise (inhale), hold, fall (exhale), hold."""
        return [TIME_MS[code] for code in self.animation_pattern]

    def start_breath_cues(self):
        """Start inhale/exhale cues in step with the breathing pattern.

        The LED pattern starts with "rise" (inhale), so the first cue is now.
        """
        self.breath_cue_inhale = True
        if SOUNDS_ENABLED and BREATH_CUES_ENABLED:
            self.next_breath_cue_ms = time.ticks_ms()
        else:
            self.next_breath_cue_ms = None

    def process_breath_cues(self):
        if self.next_breath_cue_ms is None or self.mode != MODE_START:
            return
        if self.tap_waiting_for_second or self.lsm6dsl_irq_pending:
            return  # Never delay a tap.
        late = time.ticks_diff(time.ticks_ms(), self.next_breath_cue_ms)
        if late < 0:
            return
        rise, hold_high, fall, hold_low = self.breath_stage_ms()
        if late <= BREATH_CUE_MAX_LATE_MS:
            if self.breath_cue_inhale:
                self.alarm.inhale_cue()
            else:
                self.alarm.exhale_cue()
        wait = rise + hold_high if self.breath_cue_inhale else fall + hold_low
        self.breath_cue_inhale = not self.breath_cue_inhale
        # Step from the planned time, not from now, so cues don't drift.
        self.next_breath_cue_ms = time.ticks_add(self.next_breath_cue_ms, max(1, wait))

    def parse_server_color(self, color):
        """Turn the server's task_color into [R, G, B, W] for the LEDs.

        Accepts #RRGGBB or #RRGGBBXX. What XX means is set by
        SERVER_COLOR_FORMAT: "RGBA" treats it as opacity (white LED off),
        "RGBW" uses it as the white LED level.
        """
        if not isinstance(color, str) or not color.startswith("#") or len(color) not in (7, 9):
            raise ValueError("task_color must be #RRGGBB or #RRGGBBXX, got %r" % (color,))
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
        if len(color) == 9 and SERVER_COLOR_FORMAT == "RGBW":
            w = int(color[7:9], 16)
        else:
            w = 0
        return [r, g, b, w]

    # Takes the JSON reply from a reset/double tap, applies each valid setting
    # to the cube, and saves them to settings.json so they survive a reboot.
    def upload_configSettings(self, payload):
        if not isinstance(payload, dict):
            print("Config reply is not a JSON object:", payload)
            return False

        print("Applying server settings from:", payload)
        applied = []

        # --- task_name ---
        task_name = payload.get("task_name")
        if isinstance(task_name, str) and task_name.strip():
            self.task = task_name.strip()
            applied.append("task")
        elif "task_name" in payload:
            print("- Ignored task_name (must be a non-empty string):", task_name)

        # --- task_color ---
        if "task_color" in payload:
            try:
                self.RGBW = self.lp.normalize_rgbw(self.parse_server_color(payload["task_color"]))
                applied.append("RGBW")
            except (ValueError, TypeError) as e:
                print("- Ignored task_color:", e)

        # --- task_time (seconds) ---
        task_time = payload.get("task_time")
        if isinstance(task_time, int) and task_time > 0:
            self.stopWatchPresetTime = task_time  # Used on the next start.
            applied.append("stopWatchPresetTime")
        elif "task_time" in payload:
            print("- Ignored task_time (must be a positive integer):", task_time)

        if not applied:
            print("No valid settings in server reply; nothing changed")
            return False

        # Save to settings.json so the settings survive a reboot or offline use.
        try:
            self.cubeData.task = self.task
            self.cubeData.stopWatchPresetTime = self.stopWatchPresetTime
            self.cubeData.RGBW = list(self.RGBW)
            self.cubeData.save_to_file(self.cubeData.to_dict())
        except Exception as e:
            print("Settings applied but could not be saved:", e)

        print("Applied:", ", ".join(applied))
        print("  task =", self.task)
        print("  RGBW [R, G, B, W] =", self.RGBW)
        print("  stopWatchPresetTime =", self.stopWatchPresetTime, "s")
        return True

    def init_lp5814(self) -> bool:
        if not self.lp.ping():
            print("LP5814 not detected (NACK)")
            return False
        print("LP5814 detected (ACK)")
        return True        
    # ---------- Setup ----------
    def init_lp5811(self) -> bool:
        if not self.lp.ping():
            print("LP5811 not detected (NACK)")
            return False
        print("LP5811 detected (ACK)")
        return True

    # ---------- Networking (WIFI mode) ----------
    # All WiFi and HTTP work runs in self.net_worker's background thread, so
    # nothing here blocks the main loop. Replies come back through
    # process_network_results(), which runs on the main thread and is the
    # only place that reacts to them with LEDs or settings.
    # Every method is a no-op unless COMMUNICATION_MODE == "WIFI".

    def wifi_off_after_send(self):
        """On battery, turn WiFi off after each send so light sleep can resume."""
        return WIFI_OFF_ON_BATTERY and not self.usb_power_present

    def wifi_release(self):
        """On battery, power WiFi down (done by the worker thread)."""
        if self.net_worker and self.wifi_off_after_send():
            self.net_worker.wifi_off()

    def queue_report(self, action, elapsed_seconds, sync=False):
        """Queue a server report; process_network() hands it to the worker."""
        if self.net_worker:
            self.pending_reports.append((action, int(elapsed_seconds), sync))

    def ms_until_network_due(self):
        """Milliseconds until taps have been quiet for NETWORK_QUIET_MS."""
        return NETWORK_QUIET_MS - time.ticks_diff(time.ticks_ms(), self.last_tap_ms)

    def process_network(self):
        """Hand queued reports to the worker once tapping has stopped.

        Sending no longer blocks the loop, but the HTTPS handshake still uses
        a lot of CPU. Starting it only after the double-tap window keeps tap
        timing accurate.
        """
        if not self.pending_reports:
            return
        if self.tap_waiting_for_second or self.lsm6dsl_irq_pending:
            return
        if self.ms_until_network_due() > 0:
            return

        while self.pending_reports:
            action, elapsed_seconds, sync = self.pending_reports.pop(0)
            if sync:
                print("Syncing with server...")
                if LIGHTS_ENABLED:
                    self.lp.loading_animation()
                self.sync_in_progress = True
            self.perf.wifi_sent()
            self.net_worker.send(
                {
                    "task": self.task,
                    "action": action,
                    "elapsed_seconds": elapsed_seconds,
                },
                self.stopWatchPresetTime,
                sync=sync,
                wifi_off_after=self.wifi_off_after_send(),
            )

    def process_network_results(self):
        """React to finished sends (main thread only: LEDs, settings)."""
        if not self.net_worker:
            return
        for action, sync, reply in self.net_worker.take_results():
            self.perf.wifi_done(reply is not None)
            if reply is None:
                print(action, "was not delivered; continuing offline")
            else:
                print("RECEIVED", reply)

            if not sync:
                continue

            # Reset/boot sync: replace the loading animation with the result.
            self.sync_in_progress = False
            if LIGHTS_ENABLED:
                self.lp.stop_cmd()
            if reply is not None:
                self.upload_configSettings(reply)
                self.controller_success_animation()
            else:
                self.controller_error_animation()

    def network_busy(self):
        """True while reports are queued, sending, or WiFi is still on."""
        if not self.net_worker:
            return False
        return (bool(self.pending_reports)
                or not self.net_worker.idle()
                or self.network_inst.wlan.active())

    def init_network(self):
        """At boot, report in and pull the latest settings from the server.

        Runs in the background; the loading animation shows until the reply
        arrives, then green (success) or red (failed).
        """
        # elapsed_seconds=1 matches what the old code sent at boot.
        self.queue_report("reset", 1, sync=True)
        self.last_tap_ms = time.ticks_add(time.ticks_ms(), -NETWORK_QUIET_MS)  # Send now.
        self.process_network()

    # ---------- Remote commands (BLE, shared application logic) ----------
    # The BLE link only parses bytes and calls submit_command(). Everything
    # that touches LEDs, the timer, I2C or flash happens here, on the main
    # loop, and only while no tap is being handled.

    def submit_command(self, cmd):
        """Queue a parsed command (see drivers/cubeCommands.py). Never blocks."""
        if len(self.remote_commands) >= REMOTE_QUEUE_MAX:
            return False
        self.remote_commands.append(cmd)
        return True

    def physical_input_idle(self):
        """True when no tap or USB change is waiting to be handled."""
        return not (self.lsm6dsl_irq_pending or self.tap_waiting_for_second
                    or self.usb_irq_pending)

    def remote_commands_ready(self):
        return bool(self.remote_commands) and self.physical_input_idle()

    def process_remote_commands(self):
        """Run at most one remote command per pass, after physical input."""
        if not self.remote_commands_ready():
            return
        cmd = self.remote_commands.pop(0)
        try:
            result = self.apply_command(cmd)
        except Exception as e:
            print("Command failed:", cmd.get("op"), e)
            result = "error: %s" % e
        self.perf.count("cmd_" + cmd.get("op", "?"))
        self.perf.cmd_applied(cmd.get("rx_ms"))
        self.last_command_result = "%s: %s" % (cmd.get("op"), result)
        if self.ble:
            self.ble.report_result(self.last_command_result)

    def apply_command(self, cmd):
        """Execute one command with the same methods the taps and server use."""
        op = cmd.get("op")
        if op == "start":
            if self.mode == MODE_START:
                return "already started"
            self.start_session()
            return "ok"
        if op in ("reset", "stop"):
            if self.mode != MODE_START:
                return "already stopped"
            self.reset_session()
            return "ok"
        if op == "focus":
            # Desktop app "Switch to Focus": save the preset (and task name),
            # then (re)start the session so the alarm rings after task_time
            # while the breathing animation plays.
            if not self.upload_configSettings(cmd.get("payload")):
                return "no valid settings"
            if self.mode == MODE_START:
                self.timer.reset()  # Restart from zero with the new preset.
            self.start_session()
            return "ok %ds" % self.stopWatchPresetTime
        if op == "toggle":
            self.handle_double_tap()
            return "ok"
        if op == "settings":
            old_rgbw = list(self.RGBW)
            if not self.upload_configSettings(cmd.get("payload")):
                return "no valid settings"
            # Show a new colour right away if a session is breathing.
            if LIGHTS_ENABLED and self.mode == MODE_START and self.RGBW != old_rgbw:
                self.start_breathing_lights()
            self.comm_state_changed()
            return "ok"
        return "unknown op"

    def status_snapshot(self):
        """Cube state for the BLE Status characteristic (RAM only, no I/O)."""
        elapsed = self.timer.session_elapsed_ms
        if self.timer.session_running:
            elapsed = self.timer._session_base_ms + time.ticks_diff(
                time.ticks_ms(), self.timer._session_started_ms)
        return {
            "mode": self.mode,
            "task": self.task,
            "rgbw": self.RGBW,
            "preset": self.stopWatchPresetTime,
            "elapsed": elapsed // 1000,
            "done": self.timer.session_done,
            "usb": self.usb_power_present,
            "id": CUBE_ID,
        }

    def comm_state_changed(self):
        """Tell the active link that the cube's state changed."""
        if self.ble:
            self.ble.notify_status()

    def toggle_mode(self):
        if self.mode == MODE_RESET:
            self.mode = MODE_START
        else:
            self.mode = MODE_RESET

    # ---------- Main loop ----------
    def setup(self):
        print("main.py running, communication mode:", self.comm_mode)
        if LIGHTS_ENABLED:
            self.lp.stop_cmd()
        else:
            self.lp.init_auto(exponential=False)  # Initialize at zero brightness.
        self.lsm6dsl.init()
        self.lsm6dsl.gyro_deinit()  # Gyro is unused; taps only need the accelerometer.
        # Wake from light sleep as soon as the IMU raises INT1 for a tap.
        esp32.wake_on_gpio(pins=(self.lsm6dsl_int1,), level=True)
        gc.collect()
        gc.threshold(GC_THRESHOLD_BYTES)

    def loop_once(self):
        """One pass of the cube's work. Physical input is handled first."""
        self.perf.pass_start()
        self.poll_wake_pins()
        self.timer.process()
        self.process_usb_sense()
        self.process_tap_events()
        self.process_breath_cues()
        self.process_remote_commands()
        self.process_network()
        self.process_network_results()
        self.perf.pass_end()
        self.maybe_report_perf()

    def maybe_report_perf(self):
        # Print only when the serial port is alive and nothing is waiting.
        if (self.usb_power_present and self.perf.due(PERF_REPORT_MS)
                and self.physical_input_idle() and not self.remote_commands):
            self.perf.report()

    def run(self):
        self.setup()
        if self.comm_mode == "BLE":
            asyncio.run(self.run_async())
            return
        # Last, so its success/fail animation is left to finish playing.
        if self.net_worker:
            self.init_network()
        while True:
            self.loop_once()
            self.idle()

    async def run_async(self):
        """BLE mode: the same loop as run(), as one asyncio task.

        The BLE tasks only run while this task awaits in idle_async(), so a
        long pass here (tap feedback, alarm bell) delays BLE, never the other
        way round.
        """
        self.ble.start()
        self.update_ble_power()
        while True:
            self.loop_once()
            await self.idle_async()

    def runLSM(self):
        print("LSM6DSL running")
        self.lsm6dsl.init()
        if LIGHTS_ENABLED:
            self.lp.stop_cmd()
        else:
            self.lp.init_auto(exponential=False)  # Initialize at zero brightness.
        while True:
            self.poll_wake_pins()
            self.timer.process()
            self.process_usb_sense()
            self.process_tap_events()
            # ax, ay, az = self.lsm6dsl.read_accel_mg()
            # gx, gy, gz = self.lsm6dsl.read_gyro_mdps()

            # print("AX=%0.1f AY=%0.1f AZ=%0.1f | GX=%0.1f GY=%0.1f GZ=%0.1f" %
            #     (ax, ay, az, gx, gy, gz))
            self.idle()

def main():
    controller = CubeController()
    controller.run()

def test():
    i2c = I2C(0, scl=Pin(7), sda=Pin(6))

    print("Scanning I2C bus...")
    devices = i2c.scan()

    if not devices:
        print("No I2C devices found")
    else:
        print("Found devices at addresses:")
        for addr in devices:
            print("0x%02x" % addr)


if __name__ == "__main__":
    main()
    # test()