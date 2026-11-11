'''
Docstring for drivers.networkingNode

Manages REST API calls. 


'''

import network
import urequests
import time
import json


class NetworkingNode:

    def __init__(self, ssid, password, server_ip, port=5000):
        self.connected = False
        self.ssid = ssid
        self.password = password
        self.server_ip = server_ip
        self.port = port
        self.wlan = network.WLAN(network.STA_IF)

        self.cube_uuid =  "test-cube-uuid-001"
        self.headers = {
            "X-API-Key": self.cube_uuid  
        }


        print("Server IP:", self.server_ip)
        print("Port:", self.port)

    # WiFi Connection
    def connect_wifi(self, timeout=5):
        if not self.wlan.active():
            self.wlan.active(True)

        if not self.wlan.isconnected():
            print("Connecting to WiFi...")
            self.wlan.connect(self.ssid, self.password)

            start_ms = time.ticks_ms()
            while not self.wlan.isconnected():
                if time.ticks_diff(time.ticks_ms(), start_ms) > timeout * 1000:
                    self.connected = False
                    raise RuntimeError("WiFi connection timeout")
                time.sleep_ms(100)

        print("WiFi connected:", self.wlan.ifconfig())
        self.connected = True

    def disconnect_wifi(self):
        """Power the radio down. WiFi draws far more than the rest of the cube,
        and light sleep cannot keep a connection alive anyway."""
        if self.wlan.active():
            try:
                self.wlan.disconnect()
            except OSError:
                pass
            self.wlan.active(False)
            print("WiFi off")
        self.connected = False


    def ensure_connection(self):
        if not self.wlan.isconnected():
            print("offline mode")
            return False
        return True

    def get_state(self):

        if not self.ensure_connection():
            return None

      # url = f"http://{self.server_ip}:{self.port}/api/esp/config"

        url  = f"https://thecube-api-3nmm.onrender.com/api/task/control"
        print("➡️ Sending GET to:", url)

        try:
            response = urequests.get(url, headers=self.headers)
            print("⬅️ Status:", response.status_code)
            raw = response.text
            print("⬅️ Raw response:", raw)

            data = response.json()
            response.close()
            print("Received config:", data)
            # ---- REQUIRED FIELDS ----
            required_fields = [
                "task_name",
                "task_time",
                "task_color",
                "timing_pattern",
                "alarm_type"
            ]

            # ---- VALIDATE JSON ----
            for field in required_fields:
                if field not in data:
                    print("CONFIG FORMAT ERROR: missing field", field)
                    return None

            # If validation passes, return the JSON unchanged
            return data

        except Exception as e:
            print("GET error:", e)
            return None

    # HTTP POST occurs when buttons is pressed singleTap or doubleTap
    # The purpose of this is to save data into server.

    '''
    EXAMPLE POST JSON PAYLOAD
    {
      "device_id": "cube_01",
      "task": "Meditation",
      "COMMAND": "START",
      "timestamp": 1719954000, # UNIX timestamp in seconds, may be useful for future iterations of project
      "elapsed_seconds": 0,
      "preset time": 1200
    }
    # '''


    def send_command(self, command, presetTime=0, task="Meditation", timeout=10):
        """POST a start/stop/reset event. Returns the server's JSON reply, or
        None if WiFi is down, the request fails, or the server returns an error."""
        if not self.ensure_connection():
            return None

        # url = f"http://{self.server_ip}:{self.port}/api/task/control"

        url  = f"https://thecube-api-3nmm.onrender.com/api/task/control"
        payload = {
            "device_id": "cube_01",
            "task": command.get("task", task),
            "action": command.get("action"),   # "START", "STOP", "RESET"
            "timestamp": time.time(),
            "presetTime": presetTime   # fixed key (no space)
        }

        if "elapsed_seconds" in command:
            payload["elapsed_seconds"] = command["elapsed_seconds"]

        try:
            print(" JSON PAYLOAD X2:", payload)
            # timeout stops a slow server (e.g. Render waking up) from
            # freezing the cube indefinitely.
            response = urequests.post(url, json=payload, headers=self.headers,
                                      timeout=timeout)

            status = response.status_code
            print("Status code:", status)
            try:
                data = response.json()
            except Exception:
                print("Invalid JSON response")
                data = None

            response.close()

            if not 200 <= status < 300:
                print("Server error response:", data)
                return None
            return data   # return actual response (NOT True)

        except Exception as e:
            print("POST error:", e)
            return None   # return None on failure

'''
ALARM 1: SETS OFF AT PRESET TIME.
ALARM 2 SIMPLY DOES NOTHING OTHER THAN PLAYS SOUND. EX, EVERY 1 MINUTE REMINDER MAY PLAY. WILL BE USEFUL FOR FUTURE ITERATIONS OF PROJECT

# Animation timing values (X) correspond to LED auto engine register values:
# 
# 0x0  = 0.00 s   (no pause)
# 0x1  = 0.09 s
# 0x2  = 0.18 s
# 0x3  = 0.36 s
# 0x4  = 0.54 s
# 0x5  = 0.80 s
# 0x6  = 1.07 s
# 0x7  = 1.52 s
# 0x8  = 2.06 s
# 0x9  = 2.50 s
# 0xA  = 3.04 s
# 0xB  = 4.02 s
# 0xC  = 5.01 s
# 0xD  = 5.99 s
# 0xE  = 7.06 s
# 0xF  = 8.05 s

EXAMPLE JSON FILE EXPECTED
{
  "task": {
    "name": "Meditation",
    "preset_time_sec": 20*60
  },

  "led0_W": {
    "max_pwm_percent": 100,
    "animation": {
      "T1_code": 0x0B,  # pause at minimum
      "T2_code": 0x0B,  # ramp up
      "T3_code": 0x0B,  # hold at maximum
      "T4_code": 0x0B   # ramp down
    }
  },

  "led1_B": {
    "max_pwm_percent": 100,
    "animation": {
      "T1_code": 0x04,
      "T2_code": 0x08,
      "T3_code": 0x05,
      "T4_code": 0x08
    }
  },

  "led2_G": {
    "max_pwm_percent": 100,
    "animation": {
      "T1_code": 0x04,
      "T2_code": 0x08,
      "T3_code": 0x05,
      "T4_code": 0x08
    }
  },

  "led3_R": {
    "max_pwm_percent": 100,
    "animation": {
      "T1_code": 0x04,
      "T2_code": 0x08,
      "T3_code": 0x05,
      "T4_code": 0x08
    }
  },

  "alarm1": {
    "enabled": True,
    "type": "bell",
    "time_sec": 1200
  },

  "alarm2": {
    "enabled": True,
    "type": "wood",
    "interval_sec": 60,
    "times_sec": [60,120,180,240,300]
  }
}
'''
