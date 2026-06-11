'''

The battery measurement class is in charge of measuring the BATTERY it does so by turning on a mosfet 

PIN: IO0

Then uses a ADC to measure the battery voltage through PIN: IO5. 

The way that it measures the battery voltage is by turning on the mosfet.( Which should have its own class function)
Then measuring the ADC( which should also have its own class function)

Then another functio would call these 2. Turn on MOSFET FOR 500ms. Measure adc value: at 10 times at 50ms intervals. Then turn off the mosfet. 


'''

import time
from machine import ADC, Pin


class BatteryMeasurement:
    def __init__(
        self,
        mosfet_pin: int,          # IO0 controls MOSFET gate
        adc_pin: int,             # IO5 reads battery voltage through voltage divider
        samples: int,            # Number of ADC samples to average
        sample_interval_ms: int, # Delay between each ADC sample
        mosfet_settle_ms: int   # Time to wait after turning MOSFET on
    ):
        self.mosfet = Pin(mosfet_pin, Pin.OUT)
        self.adc = ADC(Pin(adc_pin))

        self.samples = samples
        self.sample_interval_ms = sample_interval_ms
        self.mosfet_settle_ms = mosfet_settle_ms

        # Make sure MOSFET starts OFF
        self.turn_mosfet_off()

    def turn_mosfet_on(self):
        """
        Turns ON the MOSFET so the battery voltage divider is connected.
        """
        self.mosfet.value(1)

    def turn_mosfet_off(self):
        """
        Turns OFF the MOSFET to save battery power.
        """
        self.mosfet.value(0)

    def read_adc(self) -> int:
        """
        Reads one raw ADC value.
        """
        return self.adc.read()

    def read_adc_average(self) -> int:
        """
        Reads the ADC multiple times and returns the average raw ADC value.
        """
        total = 0

        for _ in range(self.samples):
            total += self.read_adc()
            time.sleep_ms(self.sample_interval_ms)

        return total // self.samples

    def measure_battery_raw(self) -> int:
        """
        Full battery measurement sequence:

        1. Turn on MOSFET
        2. Wait for voltage to settle
        3. Take 10 ADC readings at 50 ms intervals
        4. Turn off MOSFET
        5. Return average ADC value
        """
        self.turn_mosfet_on()
        time.sleep_ms(self.mosfet_settle_ms)

        adc_average = self.read_adc_average()

        self.turn_mosfet_off()

        return adc_average