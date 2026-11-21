"""Read battery voltage through the board's resistor divider."""

import time
from machine import ADC, Pin


class BatteryMeasurement:
    ADC_MAX = 4095
    ADC_FULL_SCALE_UV = 2_500_000  # Nominal 11 dB range; used for raw-count estimates.
    DIVIDER_TOP_OHMS = 10_000
    DIVIDER_BOTTOM_OHMS = 12_000

    def __init__(
        self,
        adc_pin: int,
        samples: int = 10,
        sample_interval_ms: int = 50,
    ):
        if samples <= 0:
            raise ValueError("samples must be positive")
        if sample_interval_ms < 0:
            raise ValueError("sample_interval_ms must be non-negative")

        self.adc = ADC(Pin(adc_pin))
        self.adc.atten(ADC.ATTN_11DB)
        self.adc.width(ADC.WIDTH_12BIT)
        self.samples = samples
        self.sample_interval_ms = sample_interval_ms

    @classmethod
    def raw_to_battery_voltage(cls, raw: int) -> float:
        """Estimate battery volts from a 12-bit ADC reading (nominal calibration)."""
        if not isinstance(raw, int) or not 0 <= raw <= cls.ADC_MAX:
            raise ValueError("raw ADC value must be an integer from 0 to 4095")

        adc_voltage = raw * cls.ADC_FULL_SCALE_UV / cls.ADC_MAX
        divider_ratio = (
            cls.DIVIDER_TOP_OHMS + cls.DIVIDER_BOTTOM_OHMS
        ) / cls.DIVIDER_BOTTOM_OHMS
        return adc_voltage * divider_ratio / 1_000_000

    def read_adc(self) -> int:
        """Read one raw 12-bit ADC value."""
        return self.adc.read()

    def read_adc_average(self) -> int:
        """Return the average of several raw ADC readings."""
        total = 0
        for sample in range(self.samples):
            total += self.read_adc()
            if sample + 1 < self.samples:
                time.sleep_ms(self.sample_interval_ms)
        return total // self.samples

    def measure_battery_raw(self) -> int:
        """Return the averaged raw ADC count."""
        return self.read_adc_average()

    def measure(self) -> float:
        """Return calibrated battery voltage in volts using ADC microvolt readings."""
        total_uv = 0
        for sample in range(self.samples):
            total_uv += self.adc.read_uv()
            if sample + 1 < self.samples:
                time.sleep_ms(self.sample_interval_ms)

        adc_voltage = total_uv / self.samples / 1_000_000
        divider_ratio = (
            self.DIVIDER_TOP_OHMS + self.DIVIDER_BOTTOM_OHMS
        ) / self.DIVIDER_BOTTOM_OHMS
        return adc_voltage * divider_ratio
