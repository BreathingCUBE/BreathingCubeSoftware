"""
Author: Parry
Date: Jan 29, 2026

LP5811 LED Driver — Custom I2C Interface

Code adapted from Texas Instruments LP5811 reference implementation:
https://www.ti.com/product/LP5811
https://e2e.ti.com/support/power-management-group/power-management/f/power-management-forum/1384664/faq-lp5813-quick-program-steps-guide-for-lp5813-lp5811

---------------------------------------

This module implements I2C communication for the Texas Instruments LP5811
LED driver.

The LP5811 does NOT use a standard 7-bit I2C register addressing scheme.
Instead, it implements a CUSTOM I2C protocol with a split address format.

ADDRESSING SCHEME
-----------------
Each I2C transaction uses two address bytes composed of:

- 5-bit device (chip) address
- 9-bit register address
- 1-bit R/W flag (0 = write, 1 = read)

Address Byte 1 ( 5-bit device (chip) address + upper 2 bits of register address + R/W flag )
Address Byte 2 ( lower 7 bits of register address )

This driver manually constructs the address bytes and therefore does NOT
use standard I2C memory helpers such as `writeto_mem()` or `readfrom_mem()`.

"""
import time

# ============================================================
# LP5811 / LP5812 I2C Slave Addresses (5-bit addresses)
# ============================================================

SLAVE_ADDRESS_BROADCAST = 0x1B
SLAVE_ADDRESS_U1        = 0x14
SLAVE_ADDRESS_U2        = 0x15
SLAVE_ADDRESS_U3        = 0x16
SLAVE_ADDRESS_U4        = 0x17


# ============================================================
# Device Configuration Registers
# ============================================================

CHIP_ENABLE_REGISTER      = 0x000
DEV_CONFIG0_REGISTER      = 0x001  # Max current & boost voltage
DEV_CONFIG1_REGISTER      = 0x002  # Drive mode & PWM frequency
DEV_CONFIG2_REGISTER      = 0x003
DEV_CONFIG3_REGISTER      = 0x004
DEV_CONFIG5_REGISTER      = 0x006
DEV_CONFIG6_REGISTER      = 0x007
DEV_CONFIG7_REGISTER      = 0x008
DEV_CONFIG8_REGISTER      = 0x009
DEV_CONFIG9_REGISTER      = 0x00A
DEV_CONFIG10_REGISTER     = 0x00B
DEV_CONFIG11_REGISTER     = 0x00C
DEV_CONFIG12_REGISTER     = 0x00D


# ============================================================
# Command Registers
# ============================================================

UPDATE_CMD_REG     = 0x010
START_CMD_REG      = 0x011
STOP_CMD_REG       = 0x012
PAUSE_CMD_REG      = 0x013
CONTINUE_CMD_REG   = 0x014

# ============================================================
# LED Enable Registers
# ============================================================

LED_EN1_REG = 0x020
LED_EN2_REG = 0x021

# ============================================================
# Fault / Reset Registers
# ============================================================

FAULT_CLR_REG = 0x022
RESET_REG     = 0x023

# ============================================================
# Manual DC Registers
# ============================================================

MANUAL_DC_GAP   = 0x001
MANUAL_DC_START = 0x030

# ============================================================
# Manual PWM Registers
# ============================================================

MANUAL_PWM_GAP   = 0x001
MANUAL_PWM_START = 0x040

# ============================================================
# Auto DC Registers
# ============================================================

AUTO_DC_GAP   = 0x001
AUTO_DC_START = 0x050


# ============================================================
# Autonomous Control Registers
# ============================================================

LED_AEU_GAP = 0x01A
AEU_GAP     = 0x008

LED0_PAUSE_TIME        = 0x080
LED0_PLAYBACK_TIME     = 0x081
LED0_AEU1_PWM1         = 0x082
LED0_AEU1_PWM2         = 0x083
LED0_AEU1_PWM3         = 0x084
LED0_AEU1_PWM4         = 0x085
LED0_AEU1_PWM5         = 0x086
LED0_AEU1_SLOPE_TIME1  = 0x087
LED0_AEU1_SLOPE_TIME2  = 0x088
LED0_AEU1_PT1          = 0x089
LED0_AEU2_PWM1         = 0x08A
LED0_AEU2_PWM2         = 0x08B
LED0_AEU2_PWM3         = 0x08C
LED0_AEU2_PWM4         = 0x08D
LED0_AEU2_PWM5         = 0x08E
LED0_AEU2_SLOPE_TIME1  = 0x08F
LED0_AEU2_SLOPE_TIME2  = 0x090
LED0_AEU2_PT1          = 0x091
LED0_AEU3_PWM1         = 0x092
LED0_AEU3_PWM2         = 0x093
LED0_AEU3_PWM3         = 0x094
LED0_AEU3_PWM4         = 0x095
LED0_AEU3_PWM5         = 0x096
LED0_AEU3_SLOPE_TIME1  = 0x097
LED0_AEU3_SLOPE_TIME2  = 0x098
LED0_AEU3_PT1          = 0x099


# ============================================================
# Status / Flag Registers
# ============================================================

TSD_CONFIG_STATUS = 0x300
LOD_STATUS1       = 0x301
LOD_STATUS2       = 0x302
LSD_STATUS1       = 0x303
LSD_STATUS2       = 0x304


# ============================================================
# Test Registers
# ============================================================

OTP_CONFIG_REGISTER      = 0x352
SRAM_CONFIG_REGISTER     = 0x353
CLOCK_GATING_EN_REGISTER = 0x354


# ============================================================
# Register Values
# ============================================================

CHIP_DISABLE = 0x00
CHIP_ENABLE  = 0x01

LOD_CLEAR_EN = 0x01
LSD_CLEAR_EN = 0x02
RESET_EN     = 0x66


# ============================================================
# LED Index Values
# ============================================================

LED0  = 0x00
LED1  = 0x01
LED2  = 0x02
LED3  = 0x03

LED_A = LED0 #white
LED_B = LED1 #blue
LED_C = LED2 #green 
LED_D = LED3 #red


# ============================================================
# Command Values
# ============================================================

UPDATE_CMD_VALUE   = 0x55
START_CMD_VALUE    = 0xFF
STOP_CMD_VALUE     = 0xAA
PAUSE_CMD_VALUE    = 0x33
CONTINUE_CMD_VALUE = 0xCC 


# ============================================================
# Autonomous Execution Units
# ============================================================

AEU1 = 0x00
AEU2 = 0x01
AEU3 = 0x02

from machine import I2C
import time
class LP5811:
    def __init__(self, i2c: I2C, chip_addr: int = 0b11011):
        """
        chip_addr: 5-bit LP5811 device address (A4..A0)
                   Examples:
                     0x14 → U1
                     0x15 → U2
                     0x16 → U3
                     0x17 → U4
                     0x1B → Broadcast
        """
        self.i2c = i2c
        self.chip_addr = chip_addr & 0x1F  # enforce 5-bit address
        self._current_rgb = [0, 0, 0,0]  # Track current RGBW    values for fades
    # ------------------------------------------------------------------
    # Address construction
    # ------------------------------------------------------------------

    def _build_addr7(self, reg: int) -> int:
        """
        Build 7-bit I2C address for LP5811.

        Format (7-bit):
        [101][A4 A3][R9 R8]
        """
        r9_r8 = (reg >> 8) & 0x03
        return (self.chip_addr << 2) | r9_r8

    # ------------------------------------------------------------------
    # Register access
    # ------------------------------------------------------------------

    def write_reg(self, reg: int, value: int):
        """
        Write one byte to a 10-bit register.
        """
        addr7 = self._build_addr7(reg)
        reg_lsb = reg & 0xFF

        self.i2c.writeto(
            addr7,
            bytes([reg_lsb, value & 0xFF])
        )

    def read_reg(self, reg: int) -> int:
        """
        Read one byte from a 10-bit LP5811 register.
        """
        addr7 = self._build_addr7(reg)
        reg_lsb = reg & 0xFF

        # Write register pointer (no stop if supported)
        self.i2c.writeto(addr7, bytes([reg_lsb]), False)

        # Read one byte
        data = self.i2c.readfrom(addr7, 1)

        return data[0]


    def start_cmd(self):
        """Equivalent to Start_CMD()"""
        print("Sending START command to LP5811")
        self.write_reg(START_CMD_REG, START_CMD_VALUE)

    def stop_cmd(self):
        """Equivalent to Stop_CMD()"""
        print("Sending STOP command to LP5811")
        self.write_reg(STOP_CMD_REG, STOP_CMD_VALUE)

    def pause_cmd(self):
        """Equivalent to Pause_CMD()"""
        self.write_reg(PAUSE_CMD_REG, PAUSE_CMD_VALUE)

    def continue_cmd(self):
        """Equivalent to Continue_CMD()"""
        self.write_reg(CONTINUE_CMD_REG, CONTINUE_CMD_VALUE)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def ping(self) -> bool:
        # Check if the LP5811 ACKs by reading a known register.
        try:
            _ = self.read_reg(0x000)  # Chip Enable register
            return True
        except OSError:
                return False
    def aeu_pause_time_set(self,
                        led_num: int,
                        pause_time_start: int,
                        pause_time_end: int,
                        playback_times: int,   # 0x0–0xF, 0xF = infinite
                        aeu_select: int):       # 0–3
        """
        Configure AEU pause times and playback control for one LED.

        aeu_select:
            0 = AEU1
            1 = AEU1 + AEU2
            2 = AEU1 + AEU2 + AEU3
            3 = AEU1 + AEU2 + AEU3 (same as 2)
        """

        # ---- Pause time register ----
        pause_time_value = ((pause_time_end & 0x0F) << 4) | (pause_time_start & 0x0F)
        pause_reg = LED0_PAUSE_TIME + led_num * 26 #0X80
        self.write_reg(pause_reg, pause_time_value)

        # ---- Playback register ----
        playback_value = ((aeu_select & 0x03) << 4) | (playback_times & 0x0F)
        playback_reg = LED0_PLAYBACK_TIME + led_num * 26
        self.write_reg(playback_reg, playback_value)

    def aeu_set(self,
                led_num: int,aeu_num: int,      # 0,1,2 → AEU1,2,3
                pwm1: int,pwm2: int,pwm3: int,pwm4: int,pwm5: int,
                t1: int,t2: int,t3: int,t4: int,# 0–15
                pt: int):          # playback time 0h = 0 time, 1h = 1 time, 2h = 2 times, 3h = infinite times
        """
        Configure one AEU (animation engine unit) for one LED.
        """

        # ---- Base address for this LED + AEU ----
        base_addr = LED0_AEU1_PWM1 + led_num * 26 + aeu_num * 8

        # ---- Pack slope times ----
        slope_time1 = ((t2 & 0x0F) << 4) | (t1 & 0x0F)
        slope_time2 = ((t4 & 0x0F) << 4) | (t3 & 0x0F)

        # ---- Write PWM points ----
        self.write_reg(base_addr + 0, pwm1 & 0xFF)
        self.write_reg(base_addr + 1, pwm2 & 0xFF)
        self.write_reg(base_addr + 2, pwm3 & 0xFF)
        self.write_reg(base_addr + 3, pwm4 & 0xFF)
        self.write_reg(base_addr + 4, pwm5 & 0xFF)

        # ---- Write slope times ----
        self.write_reg(base_addr + 5, slope_time1)
        self.write_reg(base_addr + 6, slope_time2)

        # ---- Write playback time ----
        self.write_reg(base_addr + 7, pt & 0x0F)



    #initialization sequence for auto mode
    def init_auto(self):
        self.write_reg(CHIP_ENABLE_REGISTER, 0x01)   # Chip_Enable_Register
        self.write_reg(DEV_CONFIG0_REGISTER, 0x00)   # Dev_Config0_Register current limit 25mA, set 0x00 , 0x01
        self.write_reg(DEV_CONFIG1_REGISTER, 0x80)   # 24KHz pwm freq in direct drive mode
        self.write_reg(DEV_CONFIG3_REGISTER, 0x0F)   # auto mode, on all LED's
        self.write_reg(DEV_CONFIG5_REGISTER, 0x0F)   # Enable exponential curve dimming mode for all LED's
        
        self.write_reg(DEV_CONFIG12_REGISTER, 0x00)   # lsd_threshold = 0.65Vcc, shut off if cathode voltage surpasses set amount. Also enabled short and open fault
        time.sleep_ms(5)
        self.write_reg(UPDATE_CMD_REG, UPDATE_CMD_VALUE)   # Update LED params

        #Check config error status. See if any fault had been tripped
        status = self.read_reg(TSD_CONFIG_STATUS)  # TSD_CONFIG_STATUS
        if status != 0x00:
            raise RuntimeError("LP5811 config error: status=0x%02X" % status)
        # Enable all LEDs
        self.write_reg(LED_EN1_REG, 0x0F)
        # Set peak current for LEDs
        peak_current = 0xFF #CLASS VARIABLES
        pwm_duty = 0x20 #CLASS VARIABLES

        # self.write_reg(AUTO_DC_START, peak_current)
        for i in range(4):#MAX current for all LED's
            self.write_reg(AUTO_DC_START + i, peak_current)

        # programming fading settings
        # self.write_reg(LED0_PAUSE_TIME, 0xBB) #4 second pause at beginning and ending
        # self.write_reg(LED0_PLAYBACK_TIME, 0x0F) #use 1 AEU, infinite loop.

        return True

    #initialization sequence for manual mode
    def init_manual(self):
        self.write_reg(CHIP_ENABLE_REGISTER, 0x01)   # Chip_Enable_Register
        self.write_reg(DEV_CONFIG0_REGISTER, 0x00)   # Dev_Config0_Register current limit 25mA, set 0x00
        self.write_reg(DEV_CONFIG1_REGISTER, 0x80)   # 24KHz pwm freq in direct drive mode
        self.write_reg(DEV_CONFIG3_REGISTER, 0x00)   # manual mode, on all LED's
        self.write_reg(DEV_CONFIG5_REGISTER, 0x0F)  # Enable exponential curve dimming mode for all LED's
        # lsd_threshold = 0.65Vcc, shut off if cathode voltage surpasses set amount. Also enabled short and open fault
        self.write_reg(DEV_CONFIG12_REGISTER, 0x0D)   
        self.write_reg(UPDATE_CMD_REG, UPDATE_CMD_VALUE)   # Update LED params

        #Check config error status. See if any fault had been tripped
        status = self.read_reg(TSD_CONFIG_STATUS)  # TSD_CONFIG_STATUS
        if status != 0x00:
            raise RuntimeError("LP5811 config error: status=0x%02X" % status)
        # Enable all LEDs
        self.write_reg(LED_EN1_REG, 0x0F)
        # Set peak current for LEDs
        peak_current = 0xFF
        for reg in range(MANUAL_DC_START , MANUAL_DC_START + 4):
            self.write_reg(reg, peak_current)
        # Set PWM duty cycle for all LEDs
        pwm_duty = 0x10
        for reg in range(MANUAL_PWM_START, MANUAL_PWM_START + 4):
            self.write_reg(reg, pwm_duty)

        # self.write_reg(UPDATE_CMD_REG, UPDATE_CMD_VALUE)   # Update LED params
        return True

    def fade_leds_manual(self, target_rgb: list, duration_ms: int, steps: int = 64):
        """
        Fade LEDs from current RGB to target RGB using manual PWM.

        target_rgb  : [W, R, G, B] target values (0–255)
        duration_ms : total fade time in milliseconds
        steps       : number of fade steps
        """

        start_register = MANUAL_PWM_START
        delay_ms = duration_ms // steps

        start_rgb = self._current_rgb.copy()

        for step in range(steps + 1):
            for i in range(4):
                value = start_rgb[i] + (target_rgb[i] - start_rgb[i]) * step // steps
                self.write_reg(start_register + i, value)

            time.sleep_ms(delay_ms)

        # Save state
        self._current_rgb = target_rgb.copy()


    ##function to call for AUTOMODE

    def led_dot_breathing(self,
                        led_num: int,
                        gs_start: int,
                        gs_end: int,
                        duration_ms: list,
                        repeat_times: int = 0xF # 0x01 
                        ):
        """
        Configure a 3-AEU breathing animation for one LED.

        led_num  : 0–3 (LED0–LED3)
        gs_start : starting PWM value (0–255)
        gs_end   : ending PWM value (0–255)
        duration_ms : list of 4 duration values for each segment of the animation (0–15, representing 0–4000ms)
        LP5811 timing codes: [0h:0s, 1h:0.09s, 2h:0.18s, 3h:0.36s, 4h:0.54s, 5h:0.80s, 6h:1.07s, 7h:1.52s, 8h:2.06s, 9h:2.50s, Ah:3.04s, Bh:4.02s, Ch:5.01s, Dh:5.99s, Eh:7.06s, Fh:8.05s]
        Repeat times: (0X01 = play once, 0X02 = play twice,  0X03 = infinite)

        """

        # Pause time + playback control
        # Pause at start = 2, pause at end = 2
        # Playback times = 0xF (infinite)
        # AEU_select = 3 → use AEU1 + AEU2 + AEU3
        self.aeu_pause_time_set(
            led_num=led_num,
            pause_time_start=0, # does not matter for 1 AEU
            pause_time_end=0, # does not matter for 1 AEU
            playback_times=repeat_times,#0XF - infinite playback , 0x00 PLAY ONCE
            aeu_select=0
        )
        # ---- AEU1 ---
        self.aeu_set(
            led_num=led_num,
            aeu_num=0,
            pwm1=gs_start,pwm2=gs_end,pwm3=gs_end,pwm4=gs_start,pwm5=gs_start,
            t1=duration_ms[0], t2=duration_ms[1], t3=duration_ms[2], t4=duration_ms[3],
            pt=repeat_times # infinite playback
            )
    def hex_to_rgbw(self, hex_color: str):
        """
        Convert HEX color (#RRGGBBWW) to RGBW.

        Parameters
        ----------
        hex_color : str
            Color string like "#ffaa00ff"

        Returns
        -------
        list
            [r, g, b, w] values from 0–255
        """

        if not isinstance(hex_color, str):
            raise ValueError("hex_color must be a string")

        if not (hex_color.startswith("#") and len(hex_color) == 9):
            raise ValueError("hex_color must be format #RRGGBBWW")

        try:
            r = int(hex_color[1:3], 16)
            g = int(hex_color[3:5], 16)
            b = int(hex_color[5:7], 16)
            w = int(hex_color[7:9], 16)
        except ValueError:
            raise ValueError("Invalid HEX values in color")

        return [r, g, b, w]

    def success_animation(self):
        self.init_auto()
        self.led_all_breathing(RGBW=[0, 255, 0, 0], duration_ms=[0x02, 0x03, 0x04, 0x05], repeat_times=0x00)  # Green breathing, fast, play once
        time.sleep_ms(5) # 5ms delay to ensure settings are applied before starting
        self.start_cmd()

    def fail_animation(self):
        self.init_auto()
        self.led_all_breathing(RGBW=[255, 0, 0, 0], duration_ms=[0x02, 0x03, 0x04, 0x05], repeat_times=0x00)  # Red breathing, fast, play once   
        time.sleep_ms(5) # 5ms delay to ensure settings are applied before starting
        self.start_cmd()
    #animation for when trying to connect to server/wifi
    def loading_animation(self):
        self.init_auto()
        self.led_all_breathing(RGBW=[126, 126, 0, 0], duration_ms=[0x0F, 0x0F, 0x0F, 0x0F], repeat_times=0x02)  # YELLOW slow breathing, play infinite
        time.sleep_ms(5) # 5ms delay to ensure settings are applied before starting
        self.start_cmd()
    
    # Animation for when device is broken and cannot be operated
    def broken_animation(self):
        self.init_auto()
        self.led_all_breathing(RGBW=[126, 0, 0, 0], duration_ms=[0x0F, 0x0F, 0x0F, 0x0F], repeat_times=0x02)  # Green breathing, fast, play once
        time.sleep_ms(5) # 5ms delay to ensure settings are applied before starting
        self.start_cmd()

    def led_all_breathing(self, RGBW:list , duration_ms:list = [0x08,0x08,0x08,0x08], repeat_times: int = 0xF):

        print("Setting breathing animation: RGBW=%s, duration_ms=%s, repeat_times=%s" % (RGBW, duration_ms, repeat_times))
        # Convert RGBW → WBGR
        # [R, G, B, W] → [W, B, G, R]
        R, G, B, W = RGBW
        WBGR = [W, B, G, R]
        # duration_ms = [1,2,3,4]
        #RGBW gives target brightness for each LED
        self.led_dot_breathing(LED0, 0, WBGR[0], duration_ms, repeat_times)  # W
        self.led_dot_breathing(LED1, 0, WBGR[1], duration_ms, repeat_times)  # B
        self.led_dot_breathing(LED2, 0, WBGR[2], duration_ms, repeat_times)  # G
        self.led_dot_breathing(LED3, 0, WBGR[3], duration_ms, repeat_times)  # R

        self.write_reg(UPDATE_CMD_REG, UPDATE_CMD_VALUE)


        time.sleep_ms(5) # 5ms delay to ensure settings are applied before starting
        # self.write_reg(START_CMD_REG, START_CMD_VALUE)   # Update LED params