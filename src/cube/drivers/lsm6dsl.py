import struct
import time


class LSM6DSL:
    # I2C addresses, 7-bit format
    ADDR_LOW = 0x6A
    ADDR_HIGH = 0x6B

    # Registers
    WHO_AM_I = 0x0F
    CTRL1_XL = 0x10
    CTRL2_G = 0x11
    CTRL3_C = 0x12
    STATUS_REG = 0x1E
    TAP_SRC = 0x1C

    OUTX_L_G = 0x22
    OUTX_L_XL = 0x28

    TAP_CFG = 0x58
    TAP_THS_6D = 0x59
    INT_DUR2 = 0x5A
    WAKE_UP_THS = 0x5B
    MD1_CFG = 0x5E
    TAP_SRC_SINGLE_TAP = 0x20
    INT1_SINGLE_TAP = 0x40

    # Expected WHO_AM_I value for LSM6DSL
    WHO_AM_I_VALUE = 0x6A

    # CTRL3_C bits:
    # BDU = bit 6
    # IF_INC = bit 2
    CTRL3_C_BDU_IF_INC = 0x44

    # Accelerometer ODR settings
    XL_ODR_OFF = 0x00
    XL_ODR_12_5HZ = 0x10
    XL_ODR_26HZ = 0x20
    XL_ODR_52HZ = 0x30
    XL_ODR_104HZ = 0x40
    XL_ODR_208HZ = 0x50

    # Accelerometer full-scale bits
    XL_FS_2G = 0x00
    XL_FS_16G = 0x04
    XL_FS_4G = 0x08
    XL_FS_8G = 0x0C

    # Gyro ODR settings
    G_ODR_OFF = 0x00
    G_ODR_12_5HZ = 0x10
    G_ODR_26HZ = 0x20
    G_ODR_52HZ = 0x30
    G_ODR_104HZ = 0x40
    G_ODR_208HZ = 0x50

    # Gyro full-scale bits
    G_FS_245DPS = 0x00
    G_FS_500DPS = 0x04
    G_FS_1000DPS = 0x08
    G_FS_2000DPS = 0x0C

    # Accelerometer sensitivity: mg / LSB
    ACCEL_SENSITIVITY_MG = {
        XL_FS_2G: 0.061,
        XL_FS_4G: 0.122,
        XL_FS_8G: 0.244,
        XL_FS_16G: 0.488,
    }

    # Gyroscope sensitivity: mdps / LSB
    GYRO_SENSITIVITY_MDPS = {
        G_FS_245DPS: 8.75,
        G_FS_500DPS: 17.50,
        G_FS_1000DPS: 35.0,
        G_FS_2000DPS: 70.0,
    }

    def __init__(self, i2c, addr=0x6a):
        self.i2c = i2c

        if addr is None:
            self.addr = self._find_device()
        else:
            self.addr = addr

        self.accel_fs = self.XL_FS_2G
        self.gyro_fs = self.G_FS_245DPS

        who = self.who_am_i()
        print("LSM6DSL WHO_AM_I = 0x%02X" % who)
        if who != self.WHO_AM_I_VALUE:
            raise RuntimeError(
                "LSM6DSL not found. WHO_AM_I = 0x%02X, expected 0x6A" % who
            )

        self.init()

    # ------------------------------------------------------------
    # Low-level register functions
    # ------------------------------------------------------------

    def write_reg(self, reg, value):
        self.i2c.writeto_mem(self.addr, reg, bytes([value]))

    def read_reg(self, reg):
        return self.i2c.readfrom_mem(self.addr, reg, 1)[0]

    def read_regs(self, reg, length):
        return self.i2c.readfrom_mem(self.addr, reg, length)

    def enable_single_tap_int1(self):
        """Enable Z-axis single taps and route each tap to INT1.

        The application can combine two single-tap events into a double tap
        using a software time window.
        """
        self.write_reg(self.MD1_CFG, 0x00)  # Disable routing while configuring.

        # Active-high, push-pull; preserve BDU and auto-increment.
        self.write_reg(self.CTRL3_C, self.read_reg(self.CTRL3_C) & ~0x30)

        # Accelerometer high-performance mode.
        self.write_reg(0x15, self.read_reg(0x15) & ~0x10)

        self.write_reg(self.CTRL1_XL, 0x60)  # 416 Hz, +/-2 g
        self.write_reg(self.TAP_CFG, 0x82)  # Tap interrupt enabled, Z axis only
        self.write_reg(self.TAP_THS_6D, 0x09)  # Tap threshold
        self.write_reg(self.INT_DUR2, 0x06)  # Shock and quiet timing
        self.write_reg(self.WAKE_UP_THS, 0x00)  # Single-tap mode

        self.write_reg(self.MD1_CFG, self.INT1_SINGLE_TAP)

    def read_tap_source(self):
        """Return the TAP_SRC flags for the most recent tap interrupt."""
        return self.read_reg(self.TAP_SRC)

    def enableThresholdINT1_init(self):
        # Standalone motion test: replaces the previous IMU tap configuration.
        self.write_reg(0x5E, 0x00)  # Disable INT1 event routing during setup
        self.write_reg(0x12, self.read_reg(0x12) & ~0x30)  # Active-high, push-pull
        self.write_reg(0x15, self.read_reg(0x15) & ~0x10)  # Accelerometer high-performance

        # self.write_reg(0x10, 0x40)
        self.write_reg(0x58, 0x90)
        self.write_reg(0x5B, 0x02)
        self.write_reg(0x5C, 0x60)

        self.write_reg(0x5E, 0x20)

    # ------------------------------------------------------------
    # Device setup
    # ------------------------------------------------------------

    def _find_device(self):
        devices = self.i2c.scan()

        if self.ADDR_LOW in devices:
            return self.ADDR_LOW

        if self.ADDR_HIGH in devices:
            return self.ADDR_HIGH

        raise RuntimeError(
            "LSM6DSL not found on I2C bus. Devices found: %s" %
            [hex(device) for device in devices]
        )

    def who_am_i(self):
        return self.read_reg(self.WHO_AM_I)

    def init(self):
        # Enable BDU and auto-increment
        self.write_reg(self.CTRL3_C, self.CTRL3_C_BDU_IF_INC)

        # Default setup
        self.accel_init(
            odr=self.XL_ODR_104HZ,
            full_scale=self.XL_FS_2G
        )

        self.gyro_init(
            odr=self.G_ODR_104HZ,
            full_scale=self.G_FS_245DPS
        )

        # self.enableThresholdINT1_init()
        self.enable_single_tap_int1()
        time.sleep_ms(100)

    def accel_init(self, odr=XL_ODR_104HZ, full_scale=XL_FS_2G):
        self.accel_fs = full_scale

        # CTRL1_XL = ODR bits + full-scale bits
        value = odr | full_scale
        self.write_reg(self.CTRL1_XL, value)

    def gyro_init(self, odr=G_ODR_104HZ, full_scale=G_FS_245DPS):
        self.gyro_fs = full_scale

        # CTRL2_G = ODR bits + full-scale bits
        value = odr | full_scale
        self.write_reg(self.CTRL2_G, value)

    # ------------------------------------------------------------
    # Reading raw sensor values
    # ------------------------------------------------------------

    def read_accel_raw(self):
        data = self.read_regs(self.OUTX_L_XL, 6)

        # Sensor sends:
        # X_L, X_H, Y_L, Y_H, Z_L, Z_H
        x, y, z = struct.unpack("<hhh", data)

        return x, y, z

    def read_gyro_raw(self):
        data = self.read_regs(self.OUTX_L_G, 6)

        # Sensor sends:
        # X_L, X_H, Y_L, Y_H, Z_L, Z_H
        x, y, z = struct.unpack("<hhh", data)

        return x, y, z

    # ------------------------------------------------------------
    # Reading converted sensor values
    # ------------------------------------------------------------

    def read_accel_mg(self):
        x, y, z = self.read_accel_raw()
        sensitivity = self.ACCEL_SENSITIVITY_MG[self.accel_fs]

        return (
            x * sensitivity,
            y * sensitivity,
            z * sensitivity,
        )

    def read_accel_g(self):
        x_mg, y_mg, z_mg = self.read_accel_mg()

        return (
            x_mg / 1000.0,
            y_mg / 1000.0,
            z_mg / 1000.0,
        )

    def read_gyro_mdps(self):
        x, y, z = self.read_gyro_raw()
        sensitivity = self.GYRO_SENSITIVITY_MDPS[self.gyro_fs]

        return (
            x * sensitivity,
            y * sensitivity,
            z * sensitivity,
        )

    def read_gyro_dps(self):
        x_mdps, y_mdps, z_mdps = self.read_gyro_mdps()

        return (
            x_mdps / 1000.0,
            y_mdps / 1000.0,
            z_mdps / 1000.0,
        )

    # ------------------------------------------------------------
    # Optional helper functions
    # ------------------------------------------------------------

    def data_ready(self):
        status = self.read_reg(self.STATUS_REG)

        accel_ready = bool(status & 0x01)
        gyro_ready = bool(status & 0x02)
        temp_ready = bool(status & 0x04)

        return accel_ready, gyro_ready, temp_ready

    def accel_deinit(self):
        self.write_reg(self.CTRL1_XL, self.XL_ODR_OFF)

    def gyro_deinit(self):
        self.write_reg(self.CTRL2_G, self.G_ODR_OFF)

    def deinit(self):
        self.accel_deinit()
        self.gyro_deinit()

    