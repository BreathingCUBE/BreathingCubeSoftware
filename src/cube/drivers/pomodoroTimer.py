'''
Docstring for drivers.pomodoroTimer


Features for pomodoro timer

-set time
-start timer
-pause timer
-add time
-reset timer
-probably needs some sort of interupt or callback function

Probably set the timer to go up, then trigger when  = setTime.


There will be 2 timers in this class. 
1. Session duration <-- counts up. And triggers interrupt upon reaching set time.
2. Reminder duration ( should be programmed so be completely programmable)

'''


import time


class PomodoroTimer:
    """
    Pomodoro timer driven by time.ticks_ms() (MicroPython).

    ticks_ms() keeps counting through machine.lightsleep(), unlike the
    hardware machine.Timer peripherals, so the timer stays accurate when the
    main loop puts the ESP32-C3 into light sleep between passes.

    Features:
    - Set session time (counts UP)
    - Start / pause / reset
    - Add time dynamically
    - Session complete callback
    - Reminder timer (programmable, repeating or one-shot)
    """

    def __init__(self,
                 on_session_complete=None,
                 on_reminder=None):
        # ---- Callbacks (run from process(), in main context) ----
        self.on_session_complete = on_session_complete
        self.on_reminder = on_reminder

        # ---- Session timer state ----
        self.set_time_ms = 0
        self.session_elapsed_ms = 0
        self.session_running = False
        self.session_done = False
        self._session_base_ms = 0      # elapsed time banked before the current run
        self._session_started_ms = 0   # ticks_ms() when the current run started

        # ---- Reminder timer state ----
        self.reminder_interval_ms = None
        self.reminder_elapsed_ms = 0
        self.reminder_enabled = False
        self.reminder_repeat = True
        self._reminder_started_ms = 0

    # ==================================================
    # Session control
    # ==================================================

    def set_time(self, seconds: int):
        """Set session duration (seconds)."""
        self.set_time_ms = seconds * 1000
        self.session_elapsed_ms = 0
        self._session_base_ms = 0
        self._session_started_ms = time.ticks_ms()
        self.session_done = False

    def start(self):
        """Start or resume the session timer."""
        if self.set_time_ms <= 0:
            raise ValueError("Call set_time() before start()")
        if self.session_running:
            return

        self._session_base_ms = self.session_elapsed_ms
        self._session_started_ms = time.ticks_ms()
        self.session_running = True

    def pause(self):
        """Pause session timer."""
        if self.session_running:
            self._update_session_elapsed()
        self.session_running = False

    def reset(self):
        """Reset session timer."""
        self.pause()
        self.session_elapsed_ms = 0
        self._session_base_ms = 0
        self.session_done = False

    def add_time(self, seconds: int):
        """Add time to session duration."""
        self.set_time_ms += seconds * 1000

    # ==================================================
    # Reminder control
    # ==================================================

    def set_reminder(self, interval_seconds: int, repeat: bool = True):
        """
        Configure reminder timer.
        interval_seconds: reminder period
        repeat: True = periodic, False = one-shot
        """
        self.reminder_interval_ms = interval_seconds * 1000
        self.reminder_elapsed_ms = 0
        self.reminder_enabled = True
        self.reminder_repeat = repeat
        self._reminder_started_ms = time.ticks_ms()

    def disable_reminder(self):
        self.reminder_enabled = False

    # ==================================================
    # Main processing (call from main loop)
    # ==================================================

    def _update_session_elapsed(self):
        running_ms = time.ticks_diff(time.ticks_ms(), self._session_started_ms)
        self.session_elapsed_ms = self._session_base_ms + running_ms

    def process(self):
        """
        Fire any due callbacks.
        Call this regularly from the main loop.
        """

        # ---- Session timer ----
        if self.session_running and not self.session_done:
            self._update_session_elapsed()

            if self.session_elapsed_ms >= self.set_time_ms:
                self.session_done = True
                self.session_running = False

                if self.on_session_complete:
                    self.on_session_complete()

        # ---- Reminder timer ----
        if self.reminder_enabled and self.reminder_interval_ms:
            now = time.ticks_ms()
            self.reminder_elapsed_ms = time.ticks_diff(now, self._reminder_started_ms)

            if self.reminder_elapsed_ms >= self.reminder_interval_ms:
                if self.on_reminder:
                    self.on_reminder()

                if self.reminder_repeat:
                    self._reminder_started_ms = time.ticks_add(
                        self._reminder_started_ms, self.reminder_interval_ms)
                    self.reminder_elapsed_ms = 0
                else:
                    self.disable_reminder()

    def ms_until_next_event(self):
        """Milliseconds until the next session end or reminder, or None if idle.

        The main loop uses this so light sleep never oversleeps a deadline.
        """
        now = time.ticks_ms()
        waits = []

        if self.session_running and not self.session_done:
            elapsed = self._session_base_ms + time.ticks_diff(now, self._session_started_ms)
            waits.append(self.set_time_ms - elapsed)

        if self.reminder_enabled and self.reminder_interval_ms:
            elapsed = time.ticks_diff(now, self._reminder_started_ms)
            waits.append(self.reminder_interval_ms - elapsed)

        if not waits:
            return None
        return max(0, min(waits))
