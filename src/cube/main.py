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
        self.init_lp5814():
            
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
        # self.lsm6dsl_int1.irq(
        #     trigger=Pin.IRQ_RISING,
        #     handler=self.on_lsm6dsl_int1
        # )

   
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
    def process_lsm6dsl_interrupt(self):
        if not self.lsm6dsl_irq_pending:
            return

        self.lsm6dsl_irq_pending = False
        self.testNum += 1
        print("Interrupt detected! Count:", self.testNum)
        # self.lp.success_animation()
        # self.lp.connected_animation()
        sleep_ms(500)
        if self.mode == "RUNNING":
            self.lp.stop_cmd()
            self.timer.pause()
            self.mode = "STOP"

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

        # --- timing_pattern ---
        # pattern = payload.get("timing_pattern")
        # Pattern to be added in future iterations, currently set to default pattern.
        # if not isinstance(pattern, list):
        #     errors.append("timing_pattern must be a list")
        # else:
        #     if len(pattern) != 4:
        #         errors.append("timing_pattern must have exactly 4 elements")

        #     if not all(isinstance(x, int) and 1 <= x <= 15 for x in pattern):
        #         errors.append("timing_pattern values must be integers 1–15")

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

        # --- alarm_type --- to be added
        # if not isinstance(payload.get("alarm_type"), str) or not payload.get("alarm_type"):
        #     errors.append("alarm_type must be a non-empty string")

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

    # ---------- Upon single tap, will toggle mode and send respective commands to server----------
    def handle_single_tap(self):
        self.toggle_mode()
        action = "stop" if self.mode == MODE_RUNNING else "start"
        json_payload = {
            "task": self.task,
            "action": action,
            "elapsed_seconds": int(self.timer.session_elapsed_ms / 1000)  # convert ms to seconds
        }

        # Send REST command at end so it does not stop animation. 

        print("RX: ", json_payload)
        if(self.network_inst.connected == False):   
            success = None
        else:
            print("mode: " + str(self.mode))
            success = self.network_inst.send_command(json_payload)
        if success is not None:

            print("RECEIVED", success)
            self.network_inst.connected = True
        else: 
            print(str(self.mode) + " Command failed to send, entering disconnection mode")
            self.network_inst.connected = False
            self.RGBW = OFFLINE_RGBW # default white color, can be changed by server config
            self.animation_pattern = OFFLINE_PATTERN # default animation pattern, can be changed by server config 

        if self.mode == MODE_RUNNING:# then STOP
            self.lp.stop_cmd()
            self.timer.pause()

        elif self.mode == MODE_STOP: # then START
            self.timer.set_time(self.stopWatchPresetTime)
            self.timer.start()
            self.lp.init_auto()
            self.lp.led_all_breathing(
                RGBW=self.RGBW,
                duration_ms=self.animation_pattern
            )
            self.lp.start_cmd()

    def handle_double_tap(self):
        # Send REST command
        self.mode = MODE_STOP
        self.toggle_mode()
        self.lp.stop_cmd()
        self.timer.pause()
        # JSON payload upon reset
        # Cube:{
        #     "task": "Meditation",      
        #     "action": "reset"
        # }
        json_payload = {
            "task": self.task,
            "action": "reset",
        }

        if self.init_network() == True:
            print("Network is connected ")
        else:
            print(str(self.mode) + " Command failed to send, entering disconnection mode")
            # self.network_inst.connected = False
            self.RGBW = OFFLINE_RGBW # default white color, can be changed by server config
            self.animation_pattern = OFFLINE_PATTERN # default animation pattern, can be changed by server config 
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
            self.process_lsm6dsl_interrupt()
            # press = self.piezo.buttonPress()
            # if press == 1:
            #     self.handle_single_tap()
            #     press = 0
            # elif press == 2:
            #     self.handle_double_tap()
            #     press = 0

            time.sleep_ms(5)
    def runLSM(self):
        print("LSM6DSL running")
        self.lsm6dsl.init()
        self.lp.stop_cmd()  # Ensure LEDs are off before starting
        while True:
            self.timer.process()
            self.process_usb_sense()
            self.process_lsm6dsl_interrupt()
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