# main.py (MicroPython / ESP32)
# .\push.ps1

# one button, one led, one timer, and a dream

import time
from machine import ADC, I2C, Pin, PWM
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

class CubeController:
    def __init__(self):

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
        # self.network_inst = NetworkingNode(
        #     secrets.WIFI_SSID,
        #     secrets.WIFI_PASSWORD,
        #     secrets.SERVER_IP,
        #     secrets.SERVER_PORT,
        # )

        # THE DIFFERENT MODES ARE PAUSE and RUNNING
        # self.task = self.cubeData.task
        self.mode = "STOP" # believe will need to get deleted
        self.stopWatchPresetTime = self.cubeData.stopWatchPresetTime
        self.RGBW = self.lp.normalize_rgbw(self.cubeData.RGBW)
        self.animation_pattern = self.cubeData.animation_pattern
        print("Loaded RGBW [R, G, B, W]:", self.RGBW)
        self.lsm6dsl_int1 = Pin(4, Pin.IN)
        self.lsm6dsl_int1.irq(
            trigger=Pin.IRQ_RISING,
            handler=self.on_lsm6dsl_int1
        )

    def on_lsm6dsl_int1(self, pin):
        # IRQ callbacks should only set a flag; do not print or use I2C here.
        self.lsm6dsl_irq_pending = True

    def on_usb_sense_irq(self, pin):
        # self.lp.connected_animation()
        self.usb_irq_pending = True


    def process_usb_sense(self):
        if not self.usb_irq_pending:
            return

        self.usb_irq_pending = False
        present = self.isUsb.value() == 0
        self.lp.connected_animation()
        if present != self.usb_power_present:
            self.usb_power_present = present
            print("USB VBUS connected" if present else "USB VBUS disconnected")
            self.lp.connected_animation() if present else self.lp.fail_animation()
            sleep_ms(500)
            
    def handle_single_tap(self):
        """Apply the start/stop action after the tap window expires."""
        print("Handling single tap")
        if self.mode == "RUNNING":
            self.lp.stop_cmd()
            self.timer.pause()
            self.mode = "STOP"
            print("Session stopped")

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
        else:
            print("Ignoring tap while mode is", self.mode)

    def process_tap_events(self):
        """Handle individual tap events and combine quick pairs into double taps."""
        now = time.ticks_ms()

        # Finalize the first tap before handling any newer interrupt. This
        # keeps timeout handling in one place and avoids duplicate branches.
        if (self.tap_waiting_for_second and
                time.ticks_diff(now, self.first_tap_ms) >= DOUBLE_TAP_WINDOW_MS):
            self.tap_waiting_for_second = False
            self.handle_single_tap()

        # No new sensor interrupt is pending; timeout handling above is all
        # that needs to happen on this pass through the main loop.
        if not self.lsm6dsl_irq_pending:
            return

        self.lsm6dsl_irq_pending = False
        tap_source = self.lsm6dsl.read_tap_source()
        print("TAP_SRC = 0x%02X" % tap_source)

        # Ignore interrupts that do not contain the IMU's single-tap flag.
        if not tap_source & self.lsm6dsl.TAP_SRC_SINGLE_TAP:
            print("Interrupt was not identified as a single tap")
            return

        self.testNum += 1
        print("Single tap event:", self.testNum)

        # If a first tap is still pending, this event is within its time window.
        if self.tap_waiting_for_second:
            self.tap_waiting_for_second = False
            if self.mode == "STOP":
                self.handle_double_tap()
                return

        # This tap starts a new double-tap window. Give feedback immediately,
        # while delaying the single-tap action until the window expires.
        if self.mode == "RUNNING":
            self.lp.blink_animation([200, 0, 0, 0])
        elif self.mode == "STOP":
            self.lp.blink_animation([0, 200, 0, 0])

        self.tap_waiting_for_second = True
        self.first_tap_ms = time.ticks_ms()

    def handle_double_tap(self):
        """Reset the session after two single-tap events within the time window."""
        print("Double tap detected; resetting session")
        self.lp.stop_cmd()
        self.timer.reset()
        self.timer.set_time(self.stopWatchPresetTime)
        self.mode = "STOP"
        self.lp.blink_animation([0, 255, 0, 0])

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

    def init_network(self):
        wifi_ok = False
        server_ok = False
        print("Connecting to WiFi and server...")
        try:
            self.lp.loading_animation()
            self.network_inst.connect_wifi()
            wifi_ok = True
        except Exception as e:
            print("Failed to connect to WiFi:", e)
            
        try:
            json_payload = {
                "task": self.task,
                "action": "reset",
                "elapsed_seconds": 1,
            }
            success = self.network_inst.send_command(json_payload)
            if success is not None:
                print("RECEIVED", success)
                #Temporarily using this method to apply server config settings upon connection. Will be changed later.
                self.upload_configSettings(success)

                server_ok = True
        except Exception as e:
            print("Failed to fetch server state:", e)

        self.lp.stop_cmd()
        # FINAL PRINT
        if wifi_ok and server_ok:
            self.connected = True   
            self.controller_success_animation()
            return True
        else:
            self.connected = False
            self.controller_error_animation()
            return False

    def toggle_mode(self):
        if self.mode == MODE_STOP:
            self.mode = MODE_RUNNING
        else:
            self.mode = MODE_STOP


    # ---------- Main loop ----------
    def run(self):
        print("main.py running")
        # self.init_network()
        self.lsm6dsl.init()
        self.lp.stop_cmd()  # Ensure LEDs are off before starting
        while True:
            self.timer.process() 
            self.process_usb_sense()
            self.process_tap_events()
            time.sleep_ms(5)

    def runLSM(self):
        print("LSM6DSL running")
        self.lsm6dsl.init()
        self.lp.stop_cmd()  # Ensure LEDs are off before starting
        while True:
            self.timer.process()
            self.process_usb_sense()
            self.process_tap_events()
            # ax, ay, az = self.lsm6dsl.read_accel_mg()
            # gx, gy, gz = self.lsm6dsl.read_gyro_mdps()

            # print("AX=%0.1f AY=%0.1f AZ=%0.1f | GX=%0.1f GY=%0.1f GZ=%0.1f" %
            #     (ax, ay, az, gx, gy, gz))
            time.sleep_ms(200)

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