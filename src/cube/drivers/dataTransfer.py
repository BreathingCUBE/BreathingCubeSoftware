import json

SETTINGS_FILE = "settings.json"

SETTINGS = {
    "task": "Nothing",
    "mode": "RUNNING",
    "stopWatchPresetTime": 20 * 60,
    "RGBW": "#FFFFFF",
    "animation_pattern":  [0x08, 0x08, 0x08, 0x08] ,
    "alarm_type": "nothing"
}
'''

1: Upload: Finished!!
What is next?

2. We have the download from file, but it needs to be properly integrated into main code.
    2.1: So this class has a bunch of files.
3. We also need to ability to upload to file. 
    3.1: So this means RX wirelessly -> update class variables -> save to file. Which I believe should be mostly complete
    3.1.1: save_to_file file

'''


class DeviceSettings:
    # when an instance of this class is created. It tries to upload from settings.
    def __init__(self):
        self._load_defaults()

        if not self._load_or_create_settings():
            self.save_to_file(self.to_dict())
        else:
            print(f"Settings loaded successfully from {SETTINGS_FILE}.")

    # Attempt to load settings from file, if it fails, return False to indicate defaults should be used.
    def _load_or_create_settings(self):
        try:
            self.load_from_file()
            return True
        except (OSError, ValueError) as exc:
            print(f"Settings load failed ({exc}). Writing defaults to {SETTINGS_FILE}.")
            return False

    # opens up json file, then loads into class variables.
    def load_from_file(self):
        with open(SETTINGS_FILE, "r") as f:
            data = json.load(f)

        self.task = data.get("task", self.task)
        self.mode = data.get("mode", self.mode)
        self.stopWatchPresetTime = data.get("stopWatchPresetTime", self.stopWatchPresetTime)
        self.RGBW = data.get("RGBW", self.RGBW)
        self.animation_pattern = data.get("animation_pattern", self.animation_pattern)
        self.alarm_type = data.get("alarm_type", self.alarm_type)

    # Load default settings from the SETTINGS dictionary
    def _load_defaults(self):
        self.task = SETTINGS["task"]
        self.mode = SETTINGS["mode"]
        self.stopWatchPresetTime = SETTINGS["stopWatchPresetTime"]
        self.RGBW = SETTINGS["RGBW"]
        self.animation_pattern = SETTINGS["animation_pattern"]
        self.alarm_type = SETTINGS["alarm_type"]

    # Convert the current settings to a dictionary for saving
    def to_dict(self):
        return {
            "task": self.task,
            "mode": self.mode,
            "stopWatchPresetTime": self.stopWatchPresetTime,
            "RGBW": self.RGBW,
            "animation_pattern": self.animation_pattern,
            "alarm_type": self.alarm_type,
        }

    # Update settings from a JSON string
    def update_from_json(self, json_data):
        data = json.loads(json_data)

        self.task = data.get("task", self.task)
        self.mode = data.get("mode", self.mode)
        self.stopWatchPresetTime = data.get("stopWatchPresetTime", self.stopWatchPresetTime)
        self.RGBW = data.get("RGBW", self.RGBW)
        self.animation_pattern = data.get("animation_pattern", self.animation_pattern)
        self.alarm_type = data.get("alarm_type", self.alarm_type)

    def save_to_file(self, data):
        with open(SETTINGS_FILE, "w") as f:
            json.dump(data, f)


