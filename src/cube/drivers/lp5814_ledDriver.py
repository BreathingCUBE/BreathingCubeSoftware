"""MicroPython LP5814 driver, adapted from Parry's LP5811 driver.

Source: TI LP5814 datasheet SNVSCQ0A, sections 7.3.4, 7.5 and 7.6:
https://www.ti.com/lit/ds/symlink/lp5814.pdf

Migration notes:
* Fixed 7-bit I2C address 0x2C; 8-bit register addresses, no address shifting.
* Register map, commands, initialization and animations are LP5814-specific.
* One pattern and one engine are assigned to each output. Legacy aeu_num=0
  and aeu_select=0 are supported; multi-AEU sequences need a different mapping.
* duration_ms in legacy animation methods STILL means four timing CODES,
  not milliseconds. Codes now use the LP5814 table TIME_MS below.
* Pattern repeat_times: 0 skips slopes, 1 plays once, 2 twice, 15 infinitely.
  Unlike some comments in the old file, 0 does NOT mean play once.
* Physical wiring: OUT0=W, OUT1=B, OUT2=G, OUT3=R.
  fade_leds_manual takes physical [W,B,G,R]; led_all_breathing takes [R,G,B,W].
* LP5811 is a compatibility class alias, not a driver for LP5811 hardware.

Example:
    from LP5814 import LP5814
    led = LP5814(i2c)
    led.init_auto()
    led.led_all_breathing([0, 128, 0, 0], [13, 0, 13, 0])
    led.start_cmd()  # 4 second rise, 4 second fall, repeat indefinitely

Validated with a simulated I2C bus; hardware validation is still required.
"""
import time

SLAVE_ADDRESS = 0x2C
CHIP_ENABLE_REGISTER = 0x00
DEV_CONFIG0_REGISTER = 0x01
DEV_CONFIG1_REGISTER = 0x02
DEV_CONFIG2_REGISTER = 0x03
DEV_CONFIG3_REGISTER = 0x04
DEV_CONFIG4_REGISTER = 0x05
ENGINE_CONFIG0_REGISTER = 0x06
ENGINE_CONFIG4_REGISTER = 0x0A
ENGINE_CONFIG5_REGISTER = 0x0B
ENGINE_CONFIG6_REGISTER = 0x0C
SHUTDOWN_CMD_REG = 0x0D
RESET_REG = 0x0E
UPDATE_CMD_REG = 0x0F
START_CMD_REG = 0x10
STOP_CMD_REG = 0x11
PAUSE_CONTINUE_REG = 0x12
FAULT_CLR_REG = 0x13
MANUAL_DC_START = 0x14
AUTO_DC_START = MANUAL_DC_START  # Shared DC controls on LP5814.
MANUAL_PWM_START = 0x18
PATTERN_START = 0x1C
PATTERN_GAP = 9
FLAG_REGISTER = 0x40
MANUAL_DC_GAP = MANUAL_PWM_GAP = AUTO_DC_GAP = 1
CHIP_DISABLE, CHIP_ENABLE = 0, 1
UPDATE_CMD_VALUE = 0x55
START_CMD_VALUE = 0xFF
STOP_CMD_VALUE = 0xAA
RESET_EN = 0xCC
LED0, LED1, LED2, LED3 = 0, 1, 2, 3
LED_A, LED_B, LED_C, LED_D = LED0, LED1, LED2, LED3
AEU1, AEU2, AEU3 = 0, 1, 2
TIME_MS = (0, 50, 100, 150, 200, 250, 300, 350,
           400, 450, 500, 1000, 2000, 4000, 6000, 8000)


def _check(value, maximum, name):
    if not isinstance(value, int) or not 0 <= value <= maximum:
        raise ValueError('%s must be an integer from 0 to %d' % (name, maximum))
    return value


def _four(values, maximum, name):
    if len(values) != 4:
        raise ValueError(name + ' must contain four values')
    return [_check(v, maximum, name) for v in values]


class LP5814:
    def __init__(self, i2c, chip_addr=SLAVE_ADDRESS):
        self.i2c = i2c
        self.chip_addr = chip_addr
        self._current_rgb = [0, 0, 0, 0]  # Physical OUT0..3 / W,B,G,R.

    def write_reg(self, reg, value):
        _check(reg, 0x40, 'LP5814 register')
        _check(value, 255, 'register value')
        self.i2c.writeto_mem(self.chip_addr, reg, bytes([value]))
        if MANUAL_PWM_START <= reg < MANUAL_PWM_START + 4:
            self._current_rgb[reg - MANUAL_PWM_START] = value

    def read_reg(self, reg):
        _check(reg, 0x40, 'LP5814 register')
        return self.i2c.readfrom_mem(self.chip_addr, reg, 1)[0]

    def ping(self):
        """Check communication, not unique chip identity."""
        try:
            self.read_reg(CHIP_ENABLE_REGISTER)
            return True
        except OSError:
            return False

    def update_cmd(self):
        self.write_reg(UPDATE_CMD_REG, UPDATE_CMD_VALUE)

    def start_cmd(self):
        self.continue_cmd()
        self.write_reg(START_CMD_REG, START_CMD_VALUE)

    def stop_cmd(self):
        self.write_reg(STOP_CMD_REG, STOP_CMD_VALUE)
        # Wait for hardware to finish stopping before changing patterns.
        started = time.ticks_ms()
        while self.read_reg(FLAG_REGISTER) & 0x04:
            if time.ticks_diff(time.ticks_ms(), started) >= 100:
                raise RuntimeError('LP5814 engine did not stop')
            time.sleep_ms(1)

    def pause_cmd(self):
        self.write_reg(PAUSE_CONTINUE_REG, 1)

    def continue_cmd(self):
        self.write_reg(PAUSE_CONTINUE_REG, 0)

    def reset(self):
        self.write_reg(RESET_REG, RESET_EN)
        self._current_rgb = [0, 0, 0, 0]
        time.sleep_ms(2)

    def _init(self, auto, peak_current, initial_pwm, exponential):
        # _check(peak_current, 255, 'peak_current')
        # _check(initial_pwm, 255, 'initial_pwm')
        time.sleep_ms(2)  # Power-up margin.
        self.write_reg(CHIP_ENABLE_REGISTER, CHIP_ENABLE)
        self.stop_cmd()
        self.continue_cmd()
        self.write_reg(DEV_CONFIG1_REGISTER, 0)  # Blank while configuring.
        self.update_cmd()
        self.write_reg(DEV_CONFIG0_REGISTER, 0)  # 25.5 mA full-scale DC.
        self.write_reg(DEV_CONFIG2_REGISTER, 0)  # No hardware manual fade.
        self.write_reg(DEV_CONFIG3_REGISTER,0xFF) #exponential for everything
        self.write_reg(DEV_CONFIG4_REGISTER, 0xE4)  # OUTn -> ENGINEn.
        for channel in range(4):
            self.write_reg(MANUAL_DC_START + channel, peak_current)
            self.write_reg(MANUAL_PWM_START + channel, initial_pwm)
            self.write_reg(ENGINE_CONFIG0_REGISTER + channel, channel)
            base = PATTERN_START + channel * PATTERN_GAP
            for offset in range(PATTERN_GAP):
                self.write_reg(base + offset, 0)
        # Enable just order0 in each engine, assigned to matching pattern.
        self.write_reg(ENGINE_CONFIG4_REGISTER, 0x11 if auto else 0)
        self.write_reg(ENGINE_CONFIG5_REGISTER, 0x11 if auto else 0)
        self.write_reg(ENGINE_CONFIG6_REGISTER, 0)  # No extra engine repeats.
        self.write_reg(FAULT_CLR_REG, 0x03)  # Clear prior POR/TSD flags.
        self.write_reg(DEV_CONFIG1_REGISTER, 0x0F)
        self.update_cmd()
        if self.read_reg(FLAG_REGISTER) & 0x02:
            raise RuntimeError('LP5814 thermal shutdown flag is set')
        return True

    def init_auto(self, peak_current=255, exponential=True):
        """Initialize stopped, blank animations; peak_current scales 25.5 mA."""
        return self._init(True, peak_current, 0, exponential)

    def init_manual(self, peak_current=255, initial_pwm=0x10, exponential=True):
        """Initialize manual mode; default PWM matches the original driver."""
        return self._init(False, peak_current, initial_pwm, exponential)

    def set_pwm(self, led_num, value):
        self.write_reg(MANUAL_PWM_START + _check(led_num, 3, 'led_num'), value)

    def set_rgbw(self, RGBW):
        r, g, b, w = self.normalize_rgbw(RGBW)
        for channel, value in enumerate((w, b, g, r)):
            self.set_pwm(channel, value)

    def fade_leds_manual(self, target_rgb, duration_ms, steps=64):
        """Blocking software fade in physical [W,B,G,R] order, manual mode only."""
        target = _four(target_rgb, 255, 'target_rgb')
        if not isinstance(duration_ms, int) or duration_ms < 0:
            raise ValueError('duration_ms must be a nonnegative integer')
        if not isinstance(steps, int) or steps < 1:
            raise ValueError('steps must be a positive integer')
        start = self._current_rgb[:]
        started = time.ticks_ms()
        for step in range(1, steps + 1):
            wait = duration_ms * step // steps - time.ticks_diff(time.ticks_ms(), started)
            if wait > 0:
                time.sleep_ms(wait)
            for channel in range(4):
                self.set_pwm(channel, start[channel] +
                             (target[channel] - start[channel]) * step // steps)

    def aeu_pause_time_set(self, led_num, pause_time_start, pause_time_end,
                           playback_times, aeu_select):
        """Legacy wrapper: configure the one pattern allocated to this output.

        playback_times is PATTERN_PT, not a second nested engine repeat count.
        Timing arguments are LP5814 codes from 0 to 15.
        """
        _check(led_num, 3, 'led_num')
        if aeu_select != 0:
            raise ValueError('LP5814 wrapper supports one pattern per LED: aeu_select=0')
        _check(pause_time_start, 15, 'pause_time_start')
        _check(pause_time_end, 15, 'pause_time_end')
        _check(playback_times, 15, 'playback_times')
        self.stop_cmd()
        base = PATTERN_START + led_num * PATTERN_GAP
        self.write_reg(base, (pause_time_start << 4) | pause_time_end)
        self.write_reg(base + 1, playback_times)

    def aeu_set(self, led_num, aeu_num, pwm1, pwm2, pwm3, pwm4, pwm5,
                t1, t2, t3, t4, pt):
        """Legacy AEU1 -> PATTERNn. pt is LP5814 pattern play count (0..15).

        Only aeu_num=0 is supported; additional LP5811 AEUs do not map
        independently when all four LP5814 patterns are allocated to outputs.
        """
        _check(led_num, 3, 'led_num')
        if aeu_num != 0:
            raise ValueError('LP5814 wrapper supports only aeu_num=0')
        points = [_check(v, 255, 'PWM') for v in (pwm1, pwm2, pwm3, pwm4, pwm5)]
        _four((t1, t2, t3, t4), 15, 'timing codes')
        _check(pt, 15, 'pt')
        self.stop_cmd()
        base = PATTERN_START + led_num * PATTERN_GAP
        for offset, value in enumerate(points):
            self.write_reg(base + 2 + offset, value)
        self.write_reg(base + 7, (t2 << 4) | t1)
        self.write_reg(base + 8, (t4 << 4) | t3)
        self.write_reg(base + 1, pt)

    def led_dot_breathing(self, led_num, gs_start, gs_end, duration_ms,
                          repeat_times=0xF):
        """Configure one output. duration_ms holds four LP5814 timing codes.

        Stages: rise, hold high, fall, hold low. Call start_cmd afterwards.
        Repeat count 1 = once; 15 = infinite; 0 = no slopes.
        """
        times = _four(duration_ms, 15, 'duration_ms timing codes')
        _check(gs_start, 255, 'gs_start')
        _check(gs_end, 255, 'gs_end')
        self.aeu_pause_time_set(led_num, 0, 0, repeat_times, 0)
        self.aeu_set(led_num, 0, gs_start, gs_end, gs_end, gs_start, gs_start,
                     times[0], times[1], times[2], times[3], repeat_times)

    def led_all_breathing(self, RGBW, duration_ms=None, repeat_times=0xF):
        """Configure all LEDs from [R,G,B,W]; call start_cmd afterwards.

        Default is 2 s per stage. Explicit duration_ms values are timing codes,
        despite the retained legacy argument name. See TIME_MS above.
        """
        r, g, b, w = self.normalize_rgbw(RGBW)
        times = _four((12, 12, 12, 12) if duration_ms is None else duration_ms,
                      15, 'duration_ms timing codes')
        _check(repeat_times, 15, 'repeat_times')
        for channel, value in enumerate((w, b, g, r)):
            self.led_dot_breathing(channel, 0, value, times, repeat_times)

    def hex_to_rgbw(self, hex_color):
        """Parse #RRGGBBWW into [R,G,B,W], with no implicit color mixing."""
        if not isinstance(hex_color, str) or len(hex_color) != 9 or hex_color[0] != '#':
            raise ValueError('hex_color must be format #RRGGBBWW')
        try:
            return [int(hex_color[i:i + 2], 16) for i in (1, 3, 5, 7)]
        except ValueError:
            raise ValueError('Invalid HEX values in color')

    def normalize_rgbw(self, rgbw):
        """Normalize #RRGGBB/#RRGGBBWW strings or four-channel values."""
        if isinstance(rgbw, str):
            if len(rgbw) == 7 and rgbw.startswith('#'):
                rgbw += '00'
            values = self.hex_to_rgbw(rgbw)
        elif isinstance(rgbw, (list, tuple)) and len(rgbw) == 4:
            values = list(rgbw)
        else:
            raise ValueError('RGBW must be #RRGGBB, #RRGGBBWW, or four channel values')
        return _four(values, 255, 'RGBW')

    def success_animation(self):
        self.init_auto()
        self.led_all_breathing([0, 255, 0, 0], [2, 3, 4, 5], 1)
        self.start_cmd()

    def fail_animation(self):
        self.init_auto()
        self.led_all_breathing([255, 0, 0, 0], [2, 3, 4, 5], 1)
        self.start_cmd()

    def loading_animation(self):
        self.init_auto()
        self.led_all_breathing([126, 126, 0, 0], [15, 15, 15, 15], 15)
        self.start_cmd()

    def broken_animation(self):
        self.init_auto()
        self.led_all_breathing([126, 0, 0, 0], [15, 15, 15, 15], 15)
        self.start_cmd()


# Compatibility for existing imports after replacing your old module's contents.
# Old explicit 5-bit chip_addr arguments must be removed or changed to 0x2C.
LP5811 = LP5814
