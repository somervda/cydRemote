
import json
import time

from machine import Pin, SPI
from ili9341 import Display, color565
from xpt2046 import Touch


class CYD:
    """
    JSON-driven button interface for ESP32-2432S028R.

    Uses:
        ili9341.Display
        xpt2046.Touch

    Button presses return their callback_id.
    """

    def __init__(self, callback=None):

        self.callback = callback

        self.buttons = []
        self.screen_id = None

        self.width = 320
        self.height = 240

        self.last_press = 0
        self.debounce_ms = 250
        self.touch_active = False
        
        self.backlight_timeout_ms = None
        self.backlight_last_activity = time.ticks_ms()
        self.backlight_enabled = True

        self._init_display()
        self._init_touch()
        self.draw_screen()

    # -----------------------------------------
    # Initialize ILI9341 display
    # -----------------------------------------

    def _init_display(self):

        self.spi_display = SPI(
            1,
            baudrate=40000000,
            polarity=0,
            phase=0,
            sck=Pin(14),
            mosi=Pin(13),
            miso=Pin(12)
        )

        self.display = Display(
            self.spi_display,
            dc=Pin(2),
            cs=Pin(15),
            rst=Pin(4, Pin.OUT),
            width=320,
            height=240,
            rotation=0
        )

        self.backlight = Pin(21, Pin.OUT)
        self.set_backlight(True)

    def set_backlight(self, enabled):
        """Turn the display backlight on or off."""

        self.backlight_enabled = bool(enabled)
        self.backlight.value(1 if self.backlight_enabled else 0)

        if self.backlight_enabled:
            self.backlight_last_activity = time.ticks_ms()

    def _check_backlight_timeout(self):

        if (
            self.backlight_timeout_ms is not None
            and self.backlight_enabled
            and time.ticks_diff(
                time.ticks_ms(),
                self.backlight_last_activity
            ) >= self.backlight_timeout_ms
        ):
            self.set_backlight(False)

    # -----------------------------------------
    # Initialize XPT2046 touchscreen
    # -----------------------------------------

    def _init_touch(self):

        self.spi_touch = SPI(
            2,
            baudrate=1000000,
            polarity=0,
            phase=0,
            sck=Pin(25),
            mosi=Pin(32),
            miso=Pin(39)
        )

        self.touch = Touch(
            self.spi_touch,
            cs=Pin(33),
            int_pin=Pin(36),
            width=self.width,
            height=self.height,
            x_min=100,
            x_max=1900,
            y_min=100,
            y_max=1900
        )

    # -----------------------------------------
    # Convert hex color to RGB565
    # -----------------------------------------

    def _hex_to_color(self, value):

        if not isinstance(value, str):
            return color565(255, 255, 255)

        value = value.lstrip("#")

        if len(value) != 6:
            return color565(255, 255, 255)

        try:
            r = int(value[0:2], 16)
            g = int(value[2:4], 16)
            b = int(value[4:6], 16)
        except ValueError:
            return color565(255, 255, 255)

        return color565(r, g, b)

    # -----------------------------------------
    # Load JSON screen definition
    # -----------------------------------------

    def load_screen(self, filename):

        with open(filename, "r") as file:
            config = json.load(file)

        self.screen_id = config.get(
            "screen_id", "unknown"
        )

        resolution = config.get("resolution", {})

        self.width = resolution.get("width", 320)
        self.height = resolution.get("height", 240)

        self.buttons = config.get("buttons", [])

        self.draw_screen()

    # -----------------------------------------
    # Draw complete screen
    # -----------------------------------------

    def draw_screen(self):

        self.display.clear(
            color565(0, 0, 0)
        )

        for button in self.buttons:
            self.draw_button(button)

    # -----------------------------------------
    # Clear screen and write a line of text
    # -----------------------------------------

    def write_line(self, text, x, y):

        background = color565(0, 0, 0)
        foreground = color565(255, 255, 255)

        self.display.clear(background)

        max_chars = (self.width - x) // 8
        if max_chars <= 0:
            return

        lines = []
        for paragraph in str(text).split("\n"):
            paragraph = paragraph.lstrip()

            while len(paragraph) > max_chars and len(lines) < 20:
                split_at = paragraph.rfind(" ", 0, max_chars)
                if split_at > 0:
                    lines.append(paragraph[:split_at])
                    paragraph = paragraph[split_at + 1:].lstrip()
                else:
                    lines.append(paragraph[:max_chars])
                    paragraph = paragraph[max_chars:].lstrip()

            if len(lines) >= 20:
                break
            lines.append(paragraph)

        for line_number, line in enumerate(lines[:20]):
            self.display.draw_text8x8(
                x,
                y + (line_number * 12),
                line,
                foreground,
                background=background
            )

    # -----------------------------------------
    # Draw individual button
    # -----------------------------------------

    def draw_button(self, button):

        position = button.get("position", {})
        size = button.get("size", {})
        style = button.get("style", {})

        x = position.get("x", 0)
        y = position.get("y", 0)

        width = size.get("width", 80)
        height = size.get("height", 40)

        label = str(button.get("label", ""))

        bg = self._hex_to_color(
            style.get("background_color", "#1976D2")
        )

        fg = self._hex_to_color(
            style.get("text_color", "#FFFFFF")
        )

        self.display.fill_rectangle(
            x, y, width, height, bg
        )

        # Built-in 8x8 font
        text_width = len(label) * 8

        text_x = x + max(
            0, (width - text_width) // 2
        )

        text_y = y + max(
            0, (height - 8) // 2
        )

        self.display.draw_text8x8(
            text_x,
            text_y,
            label,
            fg,
            background=bg
        )

    # -----------------------------------------
    # Find button at touchscreen coordinate
    # -----------------------------------------

    def _find_button(self, x, y):

        for button in self.buttons:

            position = button.get("position", {})
            size = button.get("size", {})

            bx = position.get("x", 0)
            by = position.get("y", 0)

            bw = size.get("width", 60)
            bh = size.get("height", 40)

            if (
                bx <= x < bx + bw
                and by <= y < by + bh
            ):
                return button

        return None

    # -----------------------------------------
    # Poll touchscreen
    # -----------------------------------------


    def poll(self):
        """
        Process pending touchscreen events.

        Returns:
            callback_id when a button is pressed.
            None otherwise.
        """

        self._check_backlight_timeout()

        if not self.touch.touch_pending:
            return None

        # Read touch coordinates outside the interrupt handler.
        touch_point = self.touch.poll()
        if touch_point is None:
            return None

        # A valid touch wakes the display and restarts its timeout.
        self.set_backlight(True)

        x, y = touch_point

        # Get current time for debounce
        now = time.ticks_ms()

        # Ignore rapid repeated presses
        if time.ticks_diff(
            now, self.last_press
        ) < self.debounce_ms:
            return None

        # Find button at touch coordinates
        button = self._find_button(x, y)

        if button is None:
            return None

        # Record time of button press
        self.last_press = now

        # Retrieve callback ID
        callback_id = button.get("callback_id")

        if callback_id is None:
            return None

        # Execute registered callback
        if self.callback is not None:
            self.callback(callback_id)

        return callback_id


    # -----------------------------------------
    # Change screen
    # -----------------------------------------

    def change_screen(self, filename, timeout=60):

        self.touch_active = False
        self.load_screen(filename)
        self.backlight_timeout_ms = (
            None if timeout is None else int(timeout * 1000)
        )
        self.set_backlight(True)

    # -----------------------------------------
    # List available buttons
    # -----------------------------------------

    def list_buttons(self):

        return [
            button.get("id")
            for button in self.buttons
        ]

    # -----------------------------------------
    # Get screen ID
    # -----------------------------------------

    def get_screen_id(self):

        return self.screen_id

    # -----------------------------------------
    # Set callback function
    # -----------------------------------------

    def set_callback(self, callback):

        self.callback = callback
