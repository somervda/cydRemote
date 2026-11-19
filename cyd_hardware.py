
"""
cyd_hardware.py

ESP32-2432S028R (CYD)
ILI9341 TFT + XPT2046 touchscreen

Display: 320 x 240, landscape
Color: RGB565
"""

from machine import Pin, SPI, SoftSPI, PWM
import framebuf
import time


class CYDDisplay:
    WIDTH = 320
    HEIGHT = 240

    def __init__(self):
        self.width = self.WIDTH
        self.height = self.HEIGHT

        # ILI9341 SPI bus
        self.spi = SPI(
            1,
            baudrate=40000000,
            polarity=0,
            phase=0,
            sck=Pin(14),
            mosi=Pin(13),
            miso=Pin(12)
        )

        self.cs = Pin(15, Pin.OUT, value=1)
        self.dc = Pin(2, Pin.OUT, value=1)

        # Backlight: active high on common CYD boards
        self.backlight = PWM(
            Pin(21),
            freq=1000,
            duty_u16=0
        )

        self._init_display()
        self.fill(0x0000)
        self.brightness(100)

    def _command(self, command, data=None):
        self.cs.value(0)
        self.dc.value(0)
        self.spi.write(bytes((command,)))

        if data is not None:
            self.dc.value(1)
            self.spi.write(data)

        self.cs.value(1)

    def _init_display(self):
        """Initialize ILI9341 in landscape mode."""

        time.sleep_ms(150)

        self._command(0x01)  # Software reset
        time.sleep_ms(150)

        self._command(0xEF, b'\x03\x80\x02')
        self._command(0xCF, b'\x00\xC1\x30')
        self._command(0xED, b'\x64\x03\x12\x81')
        self._command(0xE8, b'\x85\x00\x78')
        self._command(0xCB, b'\x39\x2C\x00\x34\x02')
        self._command(0xF7, b'\x20')
        self._command(0xEA, b'\x00\x00')

        self._command(0xC0, b'\x23')  # Power control
        self._command(0xC1, b'\x10')
        self._command(0xC5, b'\x3E\x28')
        self._command(0xC7, b'\x86')

        # Memory access control: landscape
        self._command(0x36, b'\x28')

        # RGB565 pixel format
        self._command(0x3A, b'\x55')

        self._command(0xB1, b'\x00\x18')
        self._command(0xB6, b'\x08\x82\x27')
        self._command(0xF2, b'\x00')
        self._command(0x26, b'\x01')

        self._command(
            0xE0,
            b'\x0F\x31\x2B\x0C\x0E\x08\x4E\xF1'
            b'\x37\x07\x10\x03\x0E\x09\x00'
        )

        self._command(
            0xE1,
            b'\x00\x0E\x14\x03\x11\x07\x31\xC1'
            b'\x48\x08\x0F\x0C\x31\x36\x0F'
        )

        self._command(0x11)  # Sleep out
        time.sleep_ms(120)

        self._command(0x29)  # Display on
        time.sleep_ms(50)

    def brightness(self, percent):
        """Set backlight brightness from 0 to 100."""
        percent = max(0, min(100, percent))
        self.backlight.duty_u16(
            int(percent * 65535 / 100)
        )

    def _window(self, x0, y0, x1, y1):
        """Select inclusive pixel drawing rectangle."""
        self._command(
            0x2A,
            bytes((
                x0 >> 8, x0 & 255,
                x1 >> 8, x1 & 255
            ))
        )

        self._command(
            0x2B,
            bytes((
                y0 >> 8, y0 & 255,
                y1 >> 8, y1 & 255
            ))
        )

        self.cs.value(0)
        self.dc.value(0)
        self.spi.write(b'\x2C')
        self.dc.value(1)

    def fill_rect(self, x, y, w, h, color):
        """Draw a filled RGB565 rectangle."""

        x = int(x)
        y = int(y)
        w = int(w)
        h = int(h)

        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(self.width, x + w)
        y1 = min(self.height, y + h)

        if x1 <= x0 or y1 <= y0:
            return

        self._window(x0, y0, x1 - 1, y1 - 1)

        pixel = bytes((
            (color >> 8) & 255,
            color & 255
        ))

        # Small reusable transfer block
        block = pixel * 256
        remaining = (x1 - x0) * (y1 - y0)

        while remaining >= 256:
            self.spi.write(block)
            remaining -= 256

        if remaining:
            self.spi.write(pixel * remaining)

        self.cs.value(1)

    def fill(self, color):
        """Fill the entire display."""
        self.fill_rect(
            0, 0,
            self.width, self.height,
            color
        )

    def pixel(self, x, y, color):
        """Draw one pixel."""
        self.fill_rect(x, y, 1, 1, color)

    def text(self, message, x, y, color):
        """
        Draw text using MicroPython's built-in
        8x8 font, without a full-screen framebuffer.
        """
        message = str(message)

        # One 8x8 monochrome glyph buffer
        buf = bytearray(8)
        fb = framebuf.FrameBuffer(
            buf, 8, 8, framebuf.MONO_HLSB
        )

        for char in message:
            fb.fill(0)
            fb.text(char, 0, 0, 1)

            # Draw contiguous foreground runs
            # to reduce SPI transactions.
            for row in range(8):
                start = -1

                for col in range(9):
                    on = (
                        col < 8 and
                        fb.pixel(col, row) != 0
                    )

                    if on and start < 0:
                        start = col

                    elif not on and start >= 0:
                        self.fill_rect(
                            x + start,
                            y + row,
                            col - start,
                            1,
                            color
                        )
                        start = -1

            x += 8


class CYDTouch:
    """
    XPT2046 resistive touchscreen.

    read_raw() returns raw ADC coordinates.
    read() returns calibrated display coordinates
    or None when the screen is not touched.
    """

    def __init__(
        self,
        width=320,
        height=240,
        x_min=200,
        x_max=3900,
        y_min=200,
        y_max=3900,
        swap_xy=False,
        invert_x=False,
        invert_y=False
    ):
        self.width = width
        self.height = height

        self.x_min = x_min
        self.x_max = x_max
        self.y_min = y_min
        self.y_max = y_max

        self.swap_xy = swap_xy
        self.invert_x = invert_x
        self.invert_y = invert_y

        # Touchscreen uses separate software SPI.
        self.spi = SoftSPI(
            baudrate=1000000,
            polarity=0,
            phase=0,
            sck=Pin(25),
            mosi=Pin(32),
            miso=Pin(39)
        )

        self.cs = Pin(33, Pin.OUT, value=1)
        self.irq = Pin(36, Pin.IN)

        self.tx = bytearray(3)
        self.rx = bytearray(3)

    def _read_adc(self, command):
        """Read one 12-bit XPT2046 ADC value."""
        self.tx[0] = command
        self.tx[1] = 0
        self.tx[2] = 0

        self.cs.value(0)

        self.spi.write_readinto(self.tx, self.rx)

        self.cs.value(1)

        return (
            (self.rx[1] << 8) | self.rx[2]
        ) >> 3 & 0x0FFF

    def read_raw(self):
        """Read averaged raw coordinates while touched."""

        # XPT2046 PENIRQ is active low.
        if self.irq.value() != 0:
            return None

        xs = []
        ys = []

        for _ in range(5):
            # X channel and Y channel
            x = self._read_adc(0xD0)
            y = self._read_adc(0x90)

            if 0 < x < 4095 and 0 < y < 4095:
                xs.append(x)
                ys.append(y)

        if len(xs) < 3:
            return None

        # Median suppresses occasional bad samples.
        xs.sort()
        ys.sort()

        return xs[len(xs) // 2], ys[len(ys) // 2]

    def read(self):
        """Return calibrated (x, y), or None."""
        point = self.read_raw()

        if point is None:
            return None

        x, y = point

        if self.swap_xy:
            x, y = y, x

        if self.x_max == self.x_min:
            return None

        if self.y_max == self.y_min:
            return None

        x = (x - self.x_min) * (
            self.width - 1
        ) // (self.x_max - self.x_min)

        y = (y - self.y_min) * (
            self.height - 1
        ) // (self.y_max - self.y_min)

        if self.invert_x:
            x = self.width - 1 - x

        if self.invert_y:
            y = self.height - 1 - y

        # Ignore coordinates outside the display.
        if not (0 <= x < self.width):
            return None

        if not (0 <= y < self.height):
            return None

        return int(x), int(y)
