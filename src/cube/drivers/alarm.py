'''
Docstring for drivers.alarm


This class is in charge of setting alarms such as potentially 
vibration motors, or speakers
'''



from machine import PWM, Pin
from time import sleep_ms


class Alarm:
    """
    Alarm driver for speaker (and optional vibration motor).

    Responsibilities:
    - Generate audible alarm patterns using PWM
    - No timing logic (external controller decides WHEN)
    """

    def __init__(self, speaker_pin=18, freq=4000):
        self.speaker = PWM(Pin(speaker_pin))
        self.speaker.freq(freq)
        self.speaker.duty_u16(0)  # silent by default
        self.alarmType = "bell"

    # ============================================
    # Low-level control
    # ============================================

    def _on(self, duty=30000):
        self.speaker.duty_u16(duty)

    def _off(self):
        self.speaker.duty_u16(0)

    def stop(self):
        """Immediately silence the speaker."""
        self._off()

    # ============================================
    # Alarm patterns
    # ============================================

    def beep(self, duration_ms=200, duty=30000):
        """Single short beep."""
        self._on(duty)
        sleep_ms(duration_ms)
        self._off()

    def tick_tock(self, ticks=6):
        """
        Soft mechanical clock tick
        """
        for _ in range(ticks):
            self.speaker.freq(800)
            self._on(18000)
            sleep_ms(40)
            self._off()
            sleep_ms(600)


    def bell(self, frequency=4000, duration_ms=1000, repeats=4,
             pause_ms=150, duty=32768):
        """Play four 1-second bursts at the piezo's tested 4 kHz resonance."""
        if frequency <= 0 or duration_ms <= 0 or repeats < 1 or pause_ms < 0:
            raise ValueError("Invalid bell timing or frequency")
        if not 0 < duty <= 65535:
            raise ValueError("duty must be from 1 to 65535")

        self.speaker.freq(frequency)
        try:
            for burst in range(repeats):
                self.speaker.duty_u16(duty)
                sleep_ms(duration_ms)
                self._off()
                if burst < repeats - 1:
                    sleep_ms(pause_ms)
        finally:
            self._off()