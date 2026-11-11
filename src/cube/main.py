# main.py (MicroPython / ESP32)
# .\push.ps1

# one button, one led, one timer, and a dream

import time
import esp32
from machine import ADC, I2C, Pin, PWM, lightsleep
from time import sleep_ms
import secrets  # secrets.WIFI_SSID, WIFI_PASSWORD, SERVER_IP, SERVER_PORT
import json

from drivers.lp5814_ledDriver import LP5814
from drivers.lp5811_ledDriver import LP5811
from drivers.piezoElectric import PiezoButton
from drivers.pomodoroTimer import PomodoroTimer
from drivers.alarm import Alarm
from drivers.networkingNode import NetworkingNode  # adjust import to your actual path/name
from drivers.batteryMeasurement import BatteryMeasurement 
from drivers.lsm6dsl import LSM6DSL
from drivers.dataTransfer import DeviceSettings 
import socket

MODE_STOP   = 0
MODE_RUNNING = 1
MODE_CONFIG  = 2
MODE_ERROR   = 3

OFFLINE_RGBW = [0,0,255,0] # default white color, can be changed by server config
OFFLINE_PATTERN = [0x0D, 0x0D, 0x0D, 0x0D] # 4 seconds per breathing stage
DOUBLE_TAP_WINDOW_MS = 400

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

# ---- Networking ----
NETWORK_ENABLED = True
WIFI_CONNECT_TIMEOUT_S = 5
# On battery, turn WiFi off after each request so the cube can light-sleep.
# On USB, WiFi stays connected so taps report faster.
WIFI_OFF_ON_BATTERY = True
# Server reports are queued and only sent once no tap has happened for this
# long. Sending blocks for seconds, and taps during a send cannot be timed, so
# this keeps the network out of the way of double taps.
NETWORK_QUIET_MS = 1000

class CubeController:
    def __init__(self):
        self.boot_ms = time.ticks_ms()

        # ---- Hardware ----
        # self.onboard_led = Pin(2, Pin.OUT)
        # I2C + LP5814      
        self.i2c = I2C(0, scl=Pin(7), sda=Pin(6))
        self.lp = LP5814(self.i2c, chip_addr=0x2C)
        self.lsm6dsl = LSM6DSL(self.i2c)  # Initialize the LSM6DSL instance
        self.testNum = 0
        self.lsm6dsl_irq_pending = False
        self.tap_waiting_for_second = False
        self.first_tap_ms = 0
        self.last_tap_ms = time.ticks_ms()
        self.pending_reports = []  # (action, elapsed_seconds, sync) waiting to send
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
        # print("Server IP:",  secrets.SERVER_IP)
        # print("Port:", secrets.SERVER_PORT)

        # Networking
        self.network_inst = NetworkingNode(
            secrets.WIFI_SSID,
            secrets.WIFI_PASSWORD,
            secrets.SERVER_IP,
            secrets.SERVER_PORT,
        )

        # THE DIFFERENT MODES ARE PAUSE and RUNNING
        self.task = self.cubeData.task
        self.alarm_type = self.cubeData.alarm_type
        self.mode = "STOP" # believe will need to get deleted
        self.stopWatchPresetTime = self.cubeData.stopWatchPresetTime
        self.RGBW = self.lp.normalize_rgbw(self.cubeData.RGBW)
        self.animation_pattern = self.cubeData.animation_pattern
        print("Loaded RGBW [R, G, B, W]:", self.RGBW)
        # IMU INT1 is latched high until TAP_SRC is read. It has no edge IRQ:
        # poll_wake_pins() reads its level every loop pass, and
        # esp32.wake_on_gpio() wakes the chip from light sleep when it goes
        # high. (A GPIO wake sets the pin's interrupt type to level-high, so an
        # IRQ handler on this pin would fire nonstop while INT1 stays latched.)
        self.lsm6dsl_int1 = Pin(4, Pin.IN)

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
        self.lp.connected_animation() if present else self.lp.fail_animation()
        if not present:
            self.wifi_release()  # Now on battery: drop WiFi so light sleep can run.
            
    def handle_single_tap(self):
        """Apply the start/stop action after the tap window expires."""
        print("Handling single tap")
        # LEDs and timer change now; the server report is queued and sent by
        # process_network() once tapping has stopped.
        if self.mode == "RUNNING":
            self.lp.stop_cmd()
            self.timer.pause()
            self.mode = "STOP"
            print("Session stopped")
            self.queue_report("stop", self.timer.session_elapsed_ms // 1000)

        elif self.mode == "STOP":
            print("Starting timer for", self.stopWatchPresetTime, "seconds")
            self.timer.set_time(self.stopWatchPresetTime)
            self.timer.start()
            self.lp.init_auto()
            # print("Starting breathing with RGBW [R, G, B, W]:", self.RGBW)
            self.lp.led_all_breathing(
                RGBW=self.RGBW,
                duration_ms=self.animation_pattern
            )
            self.mode = "RUNNING"
            self.lp.start_cmd()
            self.queue_report("start", 0)
        else:
            print("Ignoring tap while mode is", self.mode)

    def process_tap_events(self):
        """Recognize a software double tap from two IMU single-tap events."""
        now = time.ticks_ms()

        #if an interrupt occurs, then do the following.
        if self.lsm6dsl_irq_pending:
            self.lsm6dsl_irq_pending = False # reset interrupt so it can happen again
            tap_source = self.lsm6dsl.read_tap_source()
            print("TAP_SRC = 0x%02X" % tap_source)

            if tap_source & self.lsm6dsl.TAP_SRC_SINGLE_TAP:# bit mask for single tap
                self.last_tap_ms = now  # Holds off queued network sends.
                self.testNum += 1
                print("Single tap event:", self.testNum)

                if self.tap_waiting_for_second: #Boolean to check if we are waiting for a second tap
                    elapsed = time.ticks_diff(now, self.first_tap_ms)
                    if elapsed <= DOUBLE_TAP_WINDOW_MS and self.mode == "STOP": # if we are within the double-tap window, handle the double tap
                        self.tap_waiting_for_second = False
                        self.handle_double_tap()
                        return

                    #blocks red light going on twice
                    self.tap_waiting_for_second = False
                    self.handle_single_tap()

                # Give immediate feedback on the first tap while waiting to
                # determine whether another tap follows within the window.
                if self.mode == "RUNNING":
                    self.lp.blink_animation([255, 0, 0, 0])
                elif self.mode == "STOP":
                    self.lp.blink_animation([0, 255, 0, 0])
                self.tap_waiting_for_second = True
                self.first_tap_ms = now
            else:
                print("Interrupt was not identified as a single tap")

        #Once second tap window has expired, handle the first tap as a single tap.
        if (self.tap_waiting_for_second and
                time.ticks_diff(now, self.first_tap_ms) >= DOUBLE_TAP_WINDOW_MS):
            self.tap_waiting_for_second = False
            self.handle_single_tap()

    # ---------- Low power ----------
    def poll_wake_pins(self):
        """Catch IMU taps and USB plug changes by reading pin levels.

        INT1 is latched by the IMU, so a tap stays visible here until TAP_SRC
        is read. Edge IRQs do not fire during light sleep, so the USB sense
        pin is also checked after every wake.
        """
        if self.lsm6dsl_int1.value():
            self.lsm6dsl_irq_pending = True
        if (self.isUsb.value() == 0) != self.usb_power_present:
            self.usb_irq_pending = True

    def low_power_allowed(self):
        if not LOW_POWER_ENABLED:
            return False
        if self.usb_power_present:
            return False  # Keep the USB serial port alive for mpremote.
        if self.network_inst.wlan.active():
            return False  # Light sleep would drop the WiFi connection.
        if time.ticks_diff(time.ticks_ms(), self.boot_ms) < BOOT_GRACE_MS:
            return False
        return True

    def idle(self):
        """Wait until the next loop pass, using light sleep when allowed."""
        if self.lsm6dsl_irq_pending or self.usb_irq_pending:
            return

        if not self.low_power_allowed():
            sleep_ms(10)
            return

        sleep_time = IDLE_SLEEP_MS

        # Do not sleep past the software double-tap deadline.
        if self.tap_waiting_for_second:
            elapsed = time.ticks_diff(time.ticks_ms(), self.first_tap_ms)
            remaining = DOUBLE_TAP_WINDOW_MS - elapsed
            if remaining <= 0:
                return
            sleep_time = min(sleep_time, remaining)

        # Do not sleep past the session end or a reminder.
        next_event = self.timer.ms_until_next_event()
        if next_event is not None:
            if next_event <= 0:
                return
            sleep_time = min(sleep_time, next_event)

        # Do not sleep past the moment queued reports are due to send.
        if self.pending_reports:
            wait = self.ms_until_network_due()
            if wait <= 0:
                return
            sleep_time = min(sleep_time, wait)

        lightsleep(sleep_time)

    def handle_double_tap(self):
        """Reset the session after two single-tap events within the time window."""
        print("Double tap detected; resetting session")
        elapsed_seconds = self.timer.session_elapsed_ms // 1000  # Before reset clears it.
        self.lp.stop_cmd()
        self.timer.reset()
        self.timer.set_time(self.stopWatchPresetTime)
        self.mode = "STOP"
        self.lp.blink_animation([255, 255, 255, 255])

        # Once tapping stops, report the reset and pull any new settings
        # (colour, task, time), showing loading then success/fail on the LEDs.
        self.queue_report("reset", elapsed_seconds, sync=True)

    def controller_success_animation(self):
        print("Success mode: flashing green")
        self.lp.success_animation()

    def controller_error_animation(self):
        print("Error mode: flashing red")
        self.lp.fail_animation()
        
    # ---------- Callbacks ----------
    def on_session_complete(self):
        print("Timer finished")
        self.alarm.bell()
        self.lp.stop_cmd()
        self.timer.pause()
        
    def on_reminder(self):
        print("Reminder!")

    # Takes in the JSON payload cube settings, these settings are then applied onto the cube .
    # The way we should apply it is. We should most def be uploading that data onto the cube JSON file
    def upload_configSettings(self, payload):
        if not isinstance(payload, dict):
            print("Config reply is not a JSON object:", payload)
            return False

        errors = []

        # --- task_name ---
        if not isinstance(payload.get("task_name"), str) or not payload.get("task_name"):
            errors.append("task_name must be a non-empty string")

        # --- task_color ---
        color = payload.get("task_color")

        if not isinstance(color, str):
            errors.append("task_color must be a string")

        elif not (color.startswith("#") and len(color) == 9):
            errors.append("task_color must be format #RRGGBBWW")

        else:
            hex_part = color[1:]
            try:
                int(hex_part, 16)  # validate hex
            except ValueError:
                errors.append("task_color must contain valid hex values")

        # --- task_time ---
        if not isinstance(payload.get("task_time"), int) or payload.get("task_time") <= 0:
            errors.append("task_time must be a positive integer")

        # IF ERRORS → STOP
        if errors:
            print("Validation errors:")
            for err in errors:
                print("-", err)
            return False

        # APPLY SETTINGS
        print("Configuration valid, applying settings...")
        try:
            self.RGBW = self.lp.hex_to_rgbw(color)
            self.stopWatchPresetTime = (int(payload["task_time"]))

            self.task = payload["task_name"].strip()
            # self.animation_pattern = pattern
            # self.alarm.alarmType = payload["alarm_type"].strip().lower()

            self.cubeData.update_from_json(json.dumps({
                "task": self.task,
                "mode": self.mode,
                "stopWatchPresetTime": self.stopWatchPresetTime,
                "RGBW": self.RGBW,
                "animation_pattern": self.animation_pattern,
                "alarm_type": self.alarm_type
            }))
            # Save so the server's settings survive a reboot or offline use.
            self.cubeData.save_to_file(self.cubeData.to_dict())

            return True
        except Exception as e:
            print("Apply error:", e)
            return False
        

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

    # ---------- Networking ----------
    def wifi_connect(self):
        """Connect to WiFi if needed. Returns True when connected."""
        if not NETWORK_ENABLED:
            return False
        try:
            self.network_inst.connect_wifi(timeout=WIFI_CONNECT_TIMEOUT_S)
            return True
        except Exception as e:
            print("Failed to connect to WiFi:", e)
            return False

    def wifi_release(self):
        """On battery, power WiFi down after a request so light sleep can resume."""
        if WIFI_OFF_ON_BATTERY and not self.usb_power_present:
            self.network_inst.disconnect_wifi()

    def queue_report(self, action, elapsed_seconds, sync=False):
        """Queue a server report; process_network() sends it later."""
        if NETWORK_ENABLED:
            self.pending_reports.append((action, int(elapsed_seconds), sync))

    def ms_until_network_due(self):
        """Milliseconds until taps have been quiet for NETWORK_QUIET_MS."""
        return NETWORK_QUIET_MS - time.ticks_diff(time.ticks_ms(), self.last_tap_ms)

    def process_network(self):
        """Send queued reports, but only once tapping has stopped.

        Sending blocks for seconds. Waiting until no tap is pending or being
        timed, and none has happened for NETWORK_QUIET_MS, keeps double taps
        reliable.
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
                self.sync_with_server(action, elapsed_seconds)
            else:
                self.report_session_event(action, elapsed_seconds)
            # Stop if the user tapped during the send; finish once quiet again.
            if self.lsm6dsl_int1.value():
                break

    def report_session_event(self, action, elapsed_seconds):
        """Send a start/stop/reset event to the server.

        Returns the server's JSON reply, or None if it could not be delivered.
        Every call retries WiFi, so one failure never leaves the cube
        permanently offline.
        """
        if not NETWORK_ENABLED:
            return None

        reply = None
        if self.wifi_connect():
            try:
                reply = self.network_inst.send_command(
                    {
                        "task": self.task,
                        "action": action,
                        "elapsed_seconds": int(elapsed_seconds),
                    },
                    presetTime=self.stopWatchPresetTime,
                )
            except Exception as e:
                print("Failed to send", action, ":", e)
        self.wifi_release()

        if reply is None:
            print(action, "was not delivered; continuing offline")
        else:
            print("RECEIVED", reply)
        return reply

    def sync_with_server(self, action="reset", elapsed_seconds=0):
        """Report an event, apply any settings the server sends back, and show
        loading then success/fail on the LEDs."""
        if not NETWORK_ENABLED:
            return False

        print("Syncing with server...")
        self.lp.loading_animation()
        reply = self.report_session_event(action, elapsed_seconds)
        self.lp.stop_cmd()

        if reply is not None:
            self.upload_configSettings(reply)
            self.controller_success_animation()
            return True

        self.controller_error_animation()
        return False

    def init_network(self):
        """Connect at boot and pull the latest settings from the server."""
        # elapsed_seconds=1 matches what the old code sent at boot.
        return self.sync_with_server("reset", 1)

    def toggle_mode(self):
        if self.mode == MODE_STOP:
            self.mode = MODE_RUNNING
        else:
            self.mode = MODE_STOP

    # ---------- Main loop ----------
    def run(self):
        print("main.py running")
        self.lp.stop_cmd()  # Ensure LEDs are off before starting
        self.lsm6dsl.init()
        self.lsm6dsl.gyro_deinit()  # Gyro is unused; taps only need the accelerometer.
        # Wake from light sleep as soon as the IMU raises INT1 for a tap.
        esp32.wake_on_gpio(pins=(self.lsm6dsl_int1,), level=True)
        # Last, so its success/fail animation is left to finish playing.
        self.init_network()
        while True:
            self.poll_wake_pins()
            self.timer.process()
            self.process_usb_sense()
            self.process_tap_events()
            self.process_network()
            self.idle()

    def runLSM(self):
        print("LSM6DSL running")
        self.lsm6dsl.init()
        self.lp.stop_cmd()  # Ensure LEDs are off before starting
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