'''
Docstring for drivers.alarm


This class is in charge of setting alarms such as potentially 
vibration motors, or speakers
'''



import math
from machine import PWM, Pin
from time import sleep_ms, ticks_ms, ticks_add, ticks_diff

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

    def wooden_tick_tock(
        self,
        ticks=2,
        tick_frequency=400,
        tock_frequency=320,
        pulse_ms=25,
        pause_ms=220,
        duty=3000,
    ):
        """Play short, quiet alternating clicks for a wooden clock-like sound."""
        if ticks < 1 or tick_frequency <= 0 or tock_frequency <= 0:
            raise ValueError("ticks and frequencies must be positive")
        if pulse_ms <= 0 or pause_ms < 0:
            raise ValueError("pulse_ms must be positive and pause_ms non-negative")
        if not 0 < duty <= 65535:
            raise ValueError("duty must be from 1 to 65535")

        try:
            for index in range(ticks):
                frequency = tick_frequency if index % 2 == 0 else tock_frequency
                self.speaker.freq(frequency)
                self._on(duty)
                sleep_ms(pulse_ms)
                self._off()
                if index < ticks - 1:
                    sleep_ms(pause_ms)
        finally:
            self._off()

    def bell(self, frequency=4000, duration_ms=1000, repeats=20,
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

            

    def wooden_clack(self, body_hz=1100, attack_duty=16000):
        """Play one short woodblock-like strike. Blocks for about 58 ms."""
        if body_hz <= 0 or not 1 <= attack_duty <= 32768:
            raise ValueError("body_hz must be positive and attack_duty must be 1..32768")

        previous_hz = self.speaker.freq()
        try:
            # Stick hitting the block: a brief, bright attack.
            self.speaker.freq(4000)
            self._on(attack_duty)
            sleep_ms(2)

            # Hollow body: hold one pitch while its strength decays.
            self.speaker.freq(body_hz)
            for divisor, duration_ms in ((2, 5), (4, 8), (8, 13), (16, 30)):
                self._on(attack_duty // divisor)
                sleep_ms(duration_ms)
        finally:
            self._off()
            self.speaker.freq(previous_hz)

    # Notes in the piezo's loud 2-4 kHz range (Hz).
    NOTE_C7 = 2093
    NOTE_E7 = 2637
    NOTE_G7 = 3136
    NOTE_C8 = 4186

    def _wait(self, ms, stop_check=None, slice_ms=20):
        """sleep_ms() that returns True early once stop_check() is true."""
        end = ticks_add(ticks_ms(), ms)
        while True:
            left = ticks_diff(end, ticks_ms())
            if left <= 0:
                return False
            if stop_check is not None and stop_check():
                return True
            sleep_ms(min(slice_ms, left))

    def rising_phrase(self, notes=(2093, 2637, 3136, 4186), note_ms=140,
                      last_note_ms=400, gap_ms=30, duty=32768, stop_check=None):
        """End of focus: a rising C-E-G-C phrase, played once (~0.9 s).

        stop_check() is polled between notes; returns True if it stopped
        the sound early (e.g. the user tapped the cube).
        """
        previous_hz = self.speaker.freq()
        try:
            for i, hz in enumerate(notes):
                if stop_check is not None and stop_check():
                    return True
                self.speaker.freq(hz)
                self._on(duty)
                sleep_ms(last_note_ms if i == len(notes) - 1 else note_ms)
                self._off()
                sleep_ms(gap_ms)
            return False
        finally:
            self._off()
            self.speaker.freq(previous_hz)

    def singing_bowl(self, hz=4000, duration_ms=1800, duty=32768,
                     wobble_hz=5, wobble_depth_hz=12, step_ms=10,
                     stop_check=None):
        """One bowl strike: a tone that fades out with a slight shimmer.

        Returns True if stop_check() stopped it early.
        """
        previous_hz = self.speaker.freq()
        steps = max(1, duration_ms // step_ms)
        decay = 0.01 ** (1 / steps)  # Down to 1% of the start level at the end.
        level = float(duty)
        try:
            for i in range(steps):
                if stop_check is not None and i % 4 == 0 and stop_check():
                    return True
                t = i * step_ms / 1000
                self.speaker.freq(int(hz + wobble_depth_hz *
                                      math.sin(2 * math.pi * wobble_hz * t)))
                self._on(int(level))
                sleep_ms(step_ms)
                level *= decay
            return False
        finally:
            self._off()
            self.speaker.freq(previous_hz)

    def chirp(self, start_hz, end_hz, duration_ms=160, duty=16000, step_ms=4):
        """Quick pitch slide from start_hz to end_hz. Blocks for duration_ms."""
        previous_hz = self.speaker.freq()
        steps = max(1, duration_ms // step_ms)
        ratio = end_hz / start_hz
        try:
            for i in range(steps + 1):
                # Exponential slide: even steps in pitch, sounds smoother.
                self.speaker.freq(int(start_hz * ratio ** (i / steps)))
                self._on(duty)
                sleep_ms(step_ms)
        finally:
            self._off()
            self.speaker.freq(previous_hz)

    def chirp_up(self):
        """'Session started'."""
        self.chirp(1500, 4000)

    def chirp_down(self):
        """'Session stopped'."""
        self.chirp(4000, 1500)

    def breath_tone(self, hz, duration_ms=400, peak_duty=1200, step_ms=10):
        """Very soft swell that rises and falls. Blocks for duration_ms."""
        previous_hz = self.speaker.freq()
        steps = max(2, duration_ms // step_ms)
        half = steps // 2
        self.speaker.freq(hz)
        try:
            for i in range(steps):
                level = i / half if i < half else (steps - i) / (steps - half)
                self._on(int(peak_duty * level * level))  # Squared: smoother swell.
                sleep_ms(step_ms)
        finally:
            self._off()
            self.speaker.freq(previous_hz)

    def inhale_cue(self):
        self.breath_tone(1200)

    def exhale_cue(self):
        self.breath_tone(900)